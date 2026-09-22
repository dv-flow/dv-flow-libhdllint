// ---- bus-error scenario ---------------------------------------------------
//
// One scenario, run once. The RAM's injected-error arming is sticky (there is
// no disarm), so this stays a single-iteration case rather than a sweep -- a
// second iteration would inherit the fault address from the first.
class wb_dma_err_vseq extends wb_dma_vseq;
    `uvm_object_utils(wb_dma_err_vseq)

    localparam int TOT = 16;

    function new(string name = "wb_dma_err_vseq");
        super.new(name);
    endfunction

    task body();
        wb_dma_err_seq seq;

        seq = wb_dma_err_seq::type_id::create("seq");
        seq.env = env;
        seq.tot = TOT;

        env.sb.reset_counts();
        env.mem.fill(0, SRC_BASE, TOT, 32'hE00D);
        env.mem.clear(0, DST_BASE, TOT);

        seq.start(m_sequencer);

        // No check_copy: the transfer aborts part-way by construction. The
        // assertion is the CAUSE, and it lives in the sequence. What is checked
        // here is that the channel reported exactly one (errored) completion --
        // i.e. it did not hang, and did not report twice.
        env.sb.check_done_count(1);
    endtask
endclass
