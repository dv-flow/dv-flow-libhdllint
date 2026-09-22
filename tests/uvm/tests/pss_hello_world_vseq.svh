// ---- PSS Hello World: the model/testbench seam, and nothing else ---------
//
// Three interface points, in the order a testbench meets them:
//
//   pss_top::type_id()   the FACTORY -- a first-class handle to the generated
//                        root component, i.e. a constructor for the export API.
//   .create(null)        the IMPORT API -- null here, because this model calls
//                        nothing in the testbench. Lab 2 passes an
//                        implementation and that argument stops being null.
//   ep.entry_a()         the EXPORT API -- one task per action named by
//                        `export_action:` in src/pss/flow.yaml. The action is
//                        called `entry_a` in the model; that it is CALLABLE
//                        here is a property of the flow, not of the model.
//
// It runs on the initiator sequencer like every other vseq even though Hello
// World drives no bus traffic: Lab 2's PSS *does* drive registers through that
// sequencer, and keeping the shape identical means Lab 2 changes the PSS model,
// not the bench wiring.
//
// The message arrives as a bare $display line in sim.log, not as a UVM_INFO:
// PSS `message()` lowers to $display, and pssc has no switch that routes it
// through the report server.
class pss_hello_world_vseq extends wb_dma_vseq;
    `uvm_object_utils(pss_hello_world_vseq)

    function new(string name = "pss_hello_world_vseq");
        super.new(name);
    endfunction

    task body();
        export_api_if ep = pss_top::type_id().create(null);
        ep.entry_a();
    endtask
endclass
