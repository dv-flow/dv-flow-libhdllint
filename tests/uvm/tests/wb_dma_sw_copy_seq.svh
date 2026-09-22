// ---- single-channel SW block-copy sequence -------------------------------
//
// Program channel 0, arm it, wait for the completion interrupt, assert the
// channel ended DONE. The memory comparison is the test's job (it happens after
// the sequence, through the backdoor); this sequence owns the device
// interaction and the cause check.
//
// Asserting on the CAUSE, not just on "an interrupt arrived", is the point:
// INT_SRC is cause-blind -- a completion and an abort set the same bit -- so a
// channel that errored would otherwise pass.
class wb_dma_sw_copy_seq extends wb_dma_base_seq;
    `uvm_object_utils(wb_dma_sw_copy_seq)

    bit src_sel  = 0;
    bit dst_sel  = 0;
    int tot      = 16;
    int chunk    = 4;     // 0 => whole transfer in one chunk
    bit int_bank = 0;     // 0 = A (inta_o), 1 = B (intb_o)

    function new(string name = "wb_dma_sw_copy_seq");
        super.new(name);
    endfunction

    task body();
        wb_dma_status_e status;

        // Route every channel to the selected bank. Without this the channel
        // raises nothing that reaches INT_SRC. 31 bits, not 32 -- INTMSK.ch is
        // a 31-bit field.
        route_interrupts(int_bank, 31'h7fff_ffff);

        program_channel(0, SRC_BASE, DST_BASE, tot, chunk);
        arm(0, src_sel, dst_sel);
        await_completion(0, int_bank, status);

        if (status != WB_DMA_DONE)
            `uvm_error("SWCOPY", $sformatf(
                "channel 0 ended %s, expected WB_DMA_DONE", status.name()))
        else
            env.sb.note_done();
    endtask
endclass
