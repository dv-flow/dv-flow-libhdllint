// ---- bus-error sequence ---------------------------------------------------
//
// Arm a transfer whose source range contains an address the backing RAM is
// primed to terminate with ERR instead of ACK. The RAM's err output is wired to
// the DUT's wb0_err_i, so the engine sees a real Wishbone error termination
// mid-transfer and aborts the channel.
//
// The assertion is that the channel ends ERR -- specifically, that CHn_CSR
// reports INT_ERR and not INT_DONE. This is the scenario that justifies
// decoding the cause at all: INT_SRC alone cannot tell an abort from a
// completion, so a bench that only waited for "an interrupt" would call this a
// pass.
//
// No copy check follows: the transfer is aborted part-way by construction, so
// the destination legitimately holds a partial result.
class wb_dma_err_seq extends wb_dma_base_seq;
    `uvm_object_utils(wb_dma_err_seq)

    int tot      = 16;
    int chunk    = 4;
    bit int_bank = 0;
    // Which source word faults. Not the first: the engine should be part-way
    // into the transfer when the error arrives, not stopped before it starts.
    int err_word = 2;

    function new(string name = "wb_dma_err_seq");
        super.new(name);
    endfunction

    task body();
        wb_dma_status_e status;

        route_interrupts(int_bank, 31'h7fff_ffff);
        program_channel(0, SRC_BASE, DST_BASE, tot, chunk);

        // Arm the RAM fault before arming the channel.
        env.mem.inject_err(0, SRC_BASE + (err_word * 4));

        arm(0, 0, 0);
        await_completion(0, int_bank, status);

        if (status != WB_DMA_ERR)
            `uvm_error("ERR", $sformatf(
                "channel 0 ended %s, expected WB_DMA_ERR after a bus error at 0x%08h",
                status.name(), SRC_BASE + (err_word * 4)))
        else
            env.sb.note_done();
    endtask
endclass
