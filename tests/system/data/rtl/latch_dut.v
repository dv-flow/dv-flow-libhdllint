// Expected findings:
// expect vlt -- LATCH  (incomplete if in a combinational always)
module latch_dut(input sel, input d, output reg q);
   always @(*) begin
      if (sel) q = d;
   end
endmodule
