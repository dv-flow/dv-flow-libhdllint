// ---- arbitration scenario: four channels, distinct priorities -------------
class wb_dma_arb_vseq extends wb_dma_vseq;
    `uvm_object_utils(wb_dma_arb_vseq)

    localparam int N_CH = 4;
    localparam int TOT  = 16;

    function new(string name = "wb_dma_arb_vseq");
        super.new(name);
    endfunction

    task body();
        wb_dma_arb_seq seq;

        seq = wb_dma_arb_seq::type_id::create("seq");
        seq.env   = env;
        seq.n_ch  = N_CH;
        seq.tot   = TOT;

        env.sb.reset_counts();
        // A DIFFERENT pattern per channel: if the arbiter crossed two channels'
        // addresses, a shared pattern would let the wrong data compare equal.
        for (int ch = 0; ch < N_CH; ch++) begin
            env.mem.fill(0, seq.src_of(ch), TOT, 32'hA000 + ch);
            env.mem.clear(0, seq.dst_of(ch), TOT);
        end

        seq.start(m_sequencer);

        for (int ch = 0; ch < N_CH; ch++)
            env.sb.check_copy(0, seq.src_of(ch), 0, seq.dst_of(ch), TOT);
        env.sb.check_done_count(N_CH);
    endtask
endclass
