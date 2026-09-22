// ---- base test: build the env, run the selected vseq, report the verdict --
//
// A uvm_test in this bench is a broad CATEGORY: an env configuration plus a
// verdict policy. The SCENARIO is a wb_dma_vseq named by `+SEQ=` -- so a new
// case is a new sequence and a new matrix cell in tests/uvm/flow.yaml, and the
// test hierarchy stays the size it is. A second test class is justified when the
// env or the pass/fail rule differs, never when the stimulus does.
class wb_dma_base_test extends uvm_test;
    `uvm_component_utils(wb_dma_base_test)

    wb_dma_env env;

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        env = wb_dma_env::type_id::create("env", this);
    endfunction

    // The one place a scenario is started. Everything a scenario needs from the
    // bench -- the env handle and the sequencer -- is supplied here, which is
    // what lets a vseq take no parameters at all.
    task run_phase(uvm_phase phase);
        string      seq_name;
        uvm_object  obj;
        wb_dma_vseq vseq;

        if (!$value$plusargs("SEQ=%s", seq_name))
            `uvm_fatal("NOSEQ",
                       "+SEQ=<vseq-type> is required (see tests/uvm/flow.yaml)")

        // create_object_by_name RETURNS NULL for a name no type registered --
        // it does not error. Unchecked, a typo in a matrix cell would run an
        // empty test and report a pass, which is the one failure mode plusarg
        // selection introduces. Both checks below are that guard.
        obj = uvm_factory::get().create_object_by_name(
                  seq_name, get_full_name(), "vseq");
        if (obj == null)
            `uvm_fatal("NOSEQ", $sformatf(
                "no sequence type '%s' is registered with the factory", seq_name))
        if (!$cast(vseq, obj))
            `uvm_fatal("BADSEQ", $sformatf(
                "'%s' is not a wb_dma_vseq -- only a vseq is selectable", seq_name))

        vseq.env = env;

        phase.raise_objection(this);
        vseq.start(env.m_init.m_seqr);
        phase.drop_objection(this);
    endtask

    function void report_phase(uvm_phase phase);
        // The scoreboard's own count plus anything `uvm_error raised elsewhere
        // (a sequence's cause check, a failed register access). Reading the
        // report server is what keeps those from passing silently.
        uvm_report_server srv = uvm_report_server::get_server();
        int unsigned errs = env.sb.errors + srv.get_severity_count(UVM_ERROR)
                                          + srv.get_severity_count(UVM_FATAL);
        if (errs == 0)
            `uvm_info("RESULT", "** TEST PASSED **", UVM_LOW)
        else
            $display("** TEST FAILED (%0d errors) **", errs);
    endfunction
endclass
