// Expected findings:
// expect vlt -- WIDTHTRUNC  (8-bit RHS into a 4-bit LHS)
module width_mismatch(input clk, input [7:0] a, output reg [3:0] y);
   always @(posedge clk) begin
      y <= a;
   end
endmodule
