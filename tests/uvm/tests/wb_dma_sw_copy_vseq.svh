// ---- SW block-copy scenario: sweep modes x sizes x chunks -----------------
//
// The four src/dst interface-select modes (WB0/WB1 in each direction), swept
// over transfer sizes and chunk sizes, alternating the interrupt bank. Each
// iteration is independent: the source is refilled with a fresh pattern and the
// destination cleared first, so a stale result from the previous iteration
// cannot be mistaken for a correct copy.
class wb_dma_sw_copy_vseq extends wb_dma_vseq;
    `uvm_object_utils(wb_dma_sw_copy_vseq)

    function new(string name = "wb_dma_sw_copy_vseq");
        super.new(name);
    endfunction

    task body();
        int sizes[]  = '{1, 7, 16, 33};
        int chunks[] = '{0, 4, 5};

        for (int mode = 0; mode < 4; mode++) begin
            bit ss = mode[1];   // src_sel
            bit ds = mode[0];   // dst_sel
            foreach (sizes[si]) foreach (chunks[ci]) begin
                wb_dma_sw_copy_seq seq = wb_dma_sw_copy_seq::type_id::create("seq");
                int n = sizes[si];

                env.sb.reset_counts();
                // Fresh source pattern per iteration; the seed varies so a
                // transfer that silently moved nothing would leave the (cleared)
                // destination mismatching.
                env.mem.fill(ss, SRC_BASE, n, 32'hC0DE + (mode * 16) + si * 4 + ci);
                env.mem.clear(ds, DST_BASE, n);

                seq.env      = env;
                seq.src_sel  = ss;
                seq.dst_sel  = ds;
                seq.tot      = n;
                seq.chunk    = chunks[ci];
                seq.int_bank = mode[0];   // exercise both interrupt banks
                seq.start(m_sequencer);

                env.sb.check_copy(ss, SRC_BASE, ds, DST_BASE, n);
                env.sb.check_done_count(1);
            end
            `uvm_info("SWCOPY", $sformatf("mode %0d (if%0d -> if%0d) done",
                                          mode, mode[1], mode[0]), UVM_LOW)
        end
    endtask
endclass
