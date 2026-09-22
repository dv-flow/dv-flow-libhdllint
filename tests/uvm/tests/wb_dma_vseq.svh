// ---- base for a SELECTABLE scenario ---------------------------------------
//
// Two layers of sequence live in this package, and they answer different
// questions:
//
//   a UNIT sequence (wb_dma_sw_copy_seq and friends) performs one programmed
//   transfer with parameters its caller supplies. It is the device API in
//   scenario form, and it is called BY the scenarios below.
//
//   a VSEQ is a whole case: it arranges memory, runs the stimulus and checks
//   the result. It takes no parameters, because there is nobody left to supply
//   them -- `+SEQ=<type>` names it and it runs. Everything that used to sit in
//   a test's run_phase lives here instead.
//
// Extending this class is what makes a sequence eligible for `+SEQ=`: the base
// test casts to it, so selecting a unit sequence by mistake is a fatal with a
// clear message rather than a sequence that runs with default parameters and
// checks nothing. That is the whole reason an empty class earns its place.
//
// `env` and the sequencer both come from the base test, so a vseq reaches the
// scoreboard and the backdoor memory agent through `env` and starts unit
// sequences on `m_sequencer` -- the sequencer it was itself started on.
virtual class wb_dma_vseq extends wb_dma_base_seq;

    function new(string name = "wb_dma_vseq");
        super.new(name);
    endfunction

endclass
