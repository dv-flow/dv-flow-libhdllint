// Expected findings:
// expect vlt -- WIDTHTRUNC  (8-bit RHS into a 4-bit LHS)
// expect spy -- W_REDF / STARC05-* (width mismatch in assignment)
// expect vcs -- LINT-WIDTH (width mismatch, SpyGlass-compatible mode)
// expect qst -- LINT_WIDTH (AutoCheck width check)
// expect jg  -- SUPERLINT_WIDTH (superlint width mismatch)
// expect z0i -- ZIN_WIDTH (0-in width mismatch)
module width_mismatch(input clk, input [7:0] a, output reg [3:0] y);
   always @(posedge clk) begin
      y <= a;
   end
endmodule
