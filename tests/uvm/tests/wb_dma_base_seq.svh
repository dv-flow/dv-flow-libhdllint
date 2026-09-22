// ---- base sequence: the device API, in RAL terms --------------------------
//
// Every scenario programs the device through these four calls, so the register
// semantics that need care are handled once, here, rather than in each test.
//
// THE WRITE IDIOM, and why it is not update().
//
//   r.reset();                       // model-only: desired := reset value
//   r.<field>.set(v); ...            // compose the desired value field-wise
//   r.write(st, r.get(), .parent(this));
//
// r.get() returns the composed desired value, so no bit position or offset is
// restated in this bench -- move a field in src/rdl and this follows. write()
// is unconditional, which matters: CH_EN and STOP are `hwclr`, so after a
// transfer the hardware has cleared bits the mirror still shows as 1.
// update() compares desired against that stale mirror, concludes nothing needs
// writing, and silently issues no bus cycle -- the channel would never re-arm.
// The leading reset() keeps a previous read's status bits (BUSY/DONE/ERR, which
// do_predict writes into `desired` as well as `mirrored`) out of the value.
//
// THE READ IDIOM. CHn_CSR.INT_{ERR,DONE,CHK_DONE} are `rclr`: the read CONSUMES
// the event. So a completion decode reads CHn_CSR exactly ONCE and pulls every
// bit it needs out of that single returned value via wb_dma_ral_cfg::get_field()
// -- never from the mirror, and never with a confirming second read, which would
// come back clear.
class wb_dma_base_seq extends uvm_sequence #(fwvip_wb_transaction);
    `uvm_object_utils(wb_dma_base_seq)

    wb_dma_env env;

    // How many INT_SRC polls await_completion() will do before giving up. Each
    // poll is one Wishbone read (a few clocks), so this is ~ms of sim time --
    // comfortably inside hvl_top's 5ms watchdog, and far longer than any
    // scenario here needs.
    int unsigned poll_budget = 10000;

    function new(string name = "wb_dma_base_seq");
        super.new(name);
    endfunction

    function wb_dma_regs regs();
        return env.ral.regs;
    endfunction

    // ---- interrupt routing -------------------------------------------------
    // A HARD PREREQUISITE for every scenario. INT_SRC is the masked pending
    // snapshot (int_src_a = int_msk_a & ch_int), so a channel routed to neither
    // bank never appears there at all and await_completion() would poll until it
    // gave up. Bank 0 = A (inta_o), bank 1 = B (intb_o).
    virtual task route_interrupts(bit bank, logic [30:0] mask);
        uvm_status_e  st;
        wb_dma_intmsk r = bank ? regs().int_msk_b : regs().int_msk_a;
        r.reset();
        r.ch.set(mask);
        r.write(st, r.get(), .parent(this));
        if (st != UVM_IS_OK)
            `uvm_error("SEQ", $sformatf("int_msk_%s write failed", bank ? "b" : "a"))
    endtask

    // ---- channel programming ----------------------------------------------
    // Sizes and addresses only; the mode/select bits go in with the arm, since
    // they live in CSR alongside CH_EN.
    //
    // chk_sz 0 means "always perform TOT_SZ transfers" -- one chunk, not a hang.
    virtual task program_channel(int ch, logic [31:0] src, logic [31:0] dst,
                                 int tot, int chk);
        uvm_status_e st;
        wb_dma_ch_regs b = regs().bank[ch];

        b.sz.reset();
        b.sz.tot_sz.set(tot);
        b.sz.chk_sz.set(chk);
        b.sz.write(st, b.sz.get(), .parent(this));

        b.adr0.reset();  b.adr0.addr.set(src);
        b.adr0.write(st, b.adr0.get(), .parent(this));
        b.adr1.reset();  b.adr1.addr.set(dst);
        b.adr1.write(st, b.adr1.get(), .parent(this));

        // Increment masks: all address bits participate (the two low bits are
        // word-alignment padding). This is the register's reset value, written
        // explicitly so a previous scenario's circular-buffer mask cannot leak
        // into this one.
        b.am0.reset();  b.am0.mask.set(32'hffff_fffc);
        b.am0.write(st, b.am0.get(), .parent(this));
        b.am1.reset();  b.am1.mask.set(32'hffff_fffc);
        b.am1.write(st, b.am1.get(), .parent(this));
    endtask

    // ---- arm ---------------------------------------------------------------
    // One CSR write: the interface selects, the address increments, the
    // priority, the interrupt enables, and CH_EN. INE_DONE/INE_ERR are not
    // optional here -- they are what makes the channel contribute to ch_int,
    // and therefore to INT_SRC, and therefore to await_completion().
    virtual task arm(int ch, bit src_if, bit dst_if, int prio = 0);
        uvm_status_e st;
        wb_dma_csr   c = regs().bank[ch].csr;
        c.reset();
        c.src_sel.set(src_if);
        c.dst_sel.set(dst_if);
        c.inc_src.set(1);
        c.inc_dst.set(1);
        c.prio.set(prio);
        c.ine_done.set(1);
        c.ine_err.set(1);
        c.ch_en.set(1);
        c.write(st, c.get(), .parent(this));
        if (st != UVM_IS_OK)
            `uvm_error("SEQ", $sformatf("ch%0d csr arm write failed", ch))
    endtask

    // ---- completion --------------------------------------------------------
    // THE SEAM. Today it polls INT_SRC, which the register model states is
    // read-only and free of read side effects -- the only completion condition
    // this device offers that does not consume anything. The planned
    // replacement waits on an inta_o/intb_o pin edge observed by a fwvip-gpio
    // monitor (docs §9 D1 / M5); scenarios call this and so are unaffected by
    // that swap.
    //
    // Once the channel's bit appears, CHn_CSR is read ONCE and both the cause
    // and the interrupt-source bits come out of that single value. Reading it
    // is also what CLEARS the source bits, which is what lets the next
    // iteration start from a quiet INT_SRC.
    virtual task await_completion(int ch, bit bank, output wb_dma_status_e status);
        uvm_status_e    st;
        uvm_reg_data_t  v;
        wb_dma_intsrc   src = bank ? regs().int_src_b : regs().int_src_a;
        wb_dma_csr      c   = regs().bank[ch].csr;

        status = WB_DMA_TIMEOUT;
        for (int unsigned i = 0; i < poll_budget; i++) begin
            src.read(st, v, .parent(this));
            if (wb_dma_ral_cfg::get_field(src.ch, v)[ch]) begin
                // Exactly one read. ERR wins over DONE: a channel that errored
                // must not be reported as a clean completion.
                c.read(st, v, .parent(this));
                if (wb_dma_ral_cfg::get_field(c.int_err, v))       status = WB_DMA_ERR;
                else if (wb_dma_ral_cfg::get_field(c.int_done, v)) status = WB_DMA_DONE;
                else                                              status = WB_DMA_ERR;
                return;
            end
        end
        `uvm_error("SEQ", $sformatf("ch%0d: no interrupt on bank %s within %0d polls",
                                    ch, bank ? "B" : "A", poll_budget))
    endtask
endclass
