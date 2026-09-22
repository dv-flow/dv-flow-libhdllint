// ---- multi-channel arbitration sequence -----------------------------------
//
// Arm all four channels at distinct priorities and wait for every one to
// complete. Each channel gets its own source and destination region, so the
// test can attribute a bad copy to a specific channel.
//
// WHAT THIS ASSERTS: every channel completes, and completes with its own data
// intact -- i.e. the arbiter services all four and does not cross their
// addresses. It does NOT assert the ORDER in which they were serviced. Strict
// priority ordering is a claim about the interleaving of master-bus
// transactions, and with no reference model and no bus monitors this bench
// cannot see interleaving at all (docs §9 D3). The priorities are still
// programmed distinctly, because doing so is what exercises the priority
// encoder at all -- and it is what would make an ordering check possible later,
// without changing this sequence.
//
// The distinct priorities are also why hdl_top instances the DUT with
// pri_sel(2'h2): 8 priority levels, so the full 3-bit CSR[15:13] field is
// honoured. At the RTL default the high priority bits are ignored.
class wb_dma_arb_seq extends wb_dma_base_seq;
    `uvm_object_utils(wb_dma_arb_seq)

    int n_ch     = 4;
    int tot      = 16;
    int chunk    = 4;
    bit int_bank = 0;

    // Per-channel region stride. 0x400 bytes is far larger than any transfer
    // here, so a channel that ran away with the wrong address lands outside a
    // neighbour's region rather than silently corrupting it.
    localparam logic [31:0] CH_STRIDE = 32'h400;

    function new(string name = "wb_dma_arb_seq");
        super.new(name);
    endfunction

    function logic [31:0] src_of(int ch); return SRC_BASE + (ch * CH_STRIDE); endfunction
    function logic [31:0] dst_of(int ch); return DST_BASE + (ch * CH_STRIDE); endfunction

    task body();
        wb_dma_status_e status;

        route_interrupts(int_bank, 31'h7fff_ffff);

        // Program every channel BEFORE arming any, so all four are ready to be
        // arbitrated rather than trickling in one at a time.
        for (int ch = 0; ch < n_ch; ch++)
            program_channel(ch, src_of(ch), dst_of(ch), tot, chunk);

        // Distinct priorities: channel 0 highest index .. see note above. The
        // arm order is deliberately lowest-priority-first, so a device that
        // simply serviced arm order would not accidentally match priority order.
        for (int ch = 0; ch < n_ch; ch++)
            arm(ch, 0, 0, .prio(ch));

        // Collect all four. Awaiting them in index order is fine: each poll
        // reads INT_SRC (side-effect free), and a channel that finished earlier
        // keeps its bit set until its own CHn_CSR is read.
        for (int ch = 0; ch < n_ch; ch++) begin
            await_completion(ch, int_bank, status);
            if (status != WB_DMA_DONE)
                `uvm_error("ARB", $sformatf("channel %0d ended %s, expected WB_DMA_DONE",
                                            ch, status.name()))
            else
                env.sb.note_done();
        end
    endtask
endclass
