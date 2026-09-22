// Expected findings:
// expect vlt -- LATCH  (incomplete if in a combinational always)
// expect spy -- W_LATCH / STARC05-* (latch inferred)
// expect vcs -- LINT-LATCH (latch inferred, SpyGlass-compatible mode)
// expect qst -- LINT_LATCH (AutoCheck latch detection)
// expect jg  -- SUPERLINT_LATCH (superlint latch check)
// expect z0i -- ZIN_LATCH (0-in latch detection)
module latch_dut(input sel, input d, output reg q);
   always @(*) begin
      if (sel) q = d;
   end
endmodule
