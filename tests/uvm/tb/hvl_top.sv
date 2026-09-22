// HVL top for the RTL UVM testbench. The DUT is the OpenCores wb_dma_top Verilog
// RTL, instanced in hdl_top; this file is the class-side connection and nothing
// else -- it seats the three virtual interfaces the env needs and calls
// run_test().
//
// The register front door is bound with fwvip_wb_initiator_config_p, the
// VIRTUAL-INTERFACE specialization of the initiator config: it drives the host
// transactor's task API (request()/response()) directly. That is what keeps the
// bench free of the fw-hdl class layer -- the alternative specialization
// (fwvip_wb_initiator_config_ap) holds a wb_proto_if handle and exists for
// class-model DUTs, which this bench does not have. (fw-hdl is still a
// compile-time dependency of the fw-proto-wb transactors; no bench class
// references it. See docs §11.)
`include "uvm_macros.svh"

module hvl_top;
    import uvm_pkg::*;
    import fwvip_wb_xtor_pkg::*;
    import fwvip_wb_pkg::*;
    import wb_dma_env_pkg::*;
    import wb_dma_tests_pkg::*;

    // Signal-level DUT + host xtor + RAMs live in hdl_top.
    hdl_top hdl_top();

    initial begin
        // Register front door: the fwvip-wb initiator agent over the host
        // transactor's task-API interface. The RAL's default_map is pointed at
        // this agent's sequencer in the env (see wb_dma_ral_cfg).
        fwvip_wb_initiator_config_p #(
            virtual wb_initiator_xtor_if #(32, 32), 32, 32)::set(
                null, "uvm_test_top.env.m_init*", "cfg", hdl_top.u_host.u_if);

        // Data memories: the two combinational RAMs backing the DUT's master
        // ports, published for backdoor peek/poke by wb_dma_mem_agent.
        uvm_config_db #(virtual wb_ram_slv #(32, 32))::set(null, "*", "ram0", hdl_top.u_ram0);
        uvm_config_db #(virtual wb_ram_slv #(32, 32))::set(null, "*", "ram1", hdl_top.u_ram1);

        // No sim time before run_test(): reset is released by the concurrent
        // initial in hdl_top; the first register access blocks on the bus until
        // then.
        run_test();
    end

    // Waveform dump, gated by the +trace runtime plusarg. The image must have
    // been built trace-enabled, which is what `-D build=dbg` does:
    // flags-elab-dbg (hdlsim.SimElabArgsDbg) adds the Verilator tracer flag and
    // flags-run-dbg passes +trace=waves.<fmt>, so the file name matches the
    // format the image was built with. A bare +trace falls back to waves.fst.
    // Dumping from HERE (not hdl_top) captures the whole hierarchy.
    initial begin
        string tracefile;
        if ($value$plusargs("trace=%s", tracefile)) begin
            $dumpfile(tracefile);
            $dumpvars(0, hvl_top);
        end else if ($test$plusargs("trace")) begin
            $dumpfile("waves.fst");
            $dumpvars(0, hvl_top);
        end
    end

    // Sim-time watchdog.
    initial begin
        #5ms;
        $fatal(1, "[hvl_top] TIMEOUT");
    end
endmodule
