# Cross-Tool Rule Mapping

This is an informational, best-effort mapping of common lint checks across
tools. Rule ids and coverage vary by tool version; this table is a starting
point for understanding which tools cover which checks, not a definitive
reference.

## Width mismatches

| Tool       | Rule ID(s)                |
|------------|---------------------------|
| Verilator  | `WIDTHTRUNC`, `WIDTHEXPAND` |
| SpyGlass   | `W_REDF`, `STARC05-*`     |
| VC Static  | `LINT-WIDTH`              |
| Questa     | `LINT_WIDTH`              |
| JasperGold | `SUPERLINT_WIDTH`         |
| 0-in       | `ZIN_WIDTH`               |

## Inferred latches

| Tool       | Rule ID(s)                |
|------------|---------------------------|
| Verilator  | `LATCH`                   |
| SpyGlass   | `W_LATCH`, `SYNTH_5130`   |
| VC Static  | `LINT-LATCH`              |
| Questa     | `LINT_LATCH`              |
| JasperGold | `SUPERLINT_LATCH`         |
| 0-in       | `ZIN_LATCH`               |

## Unused signals

| Tool       | Rule ID(s)                |
|------------|---------------------------|
| Verilator  | `UNUSEDSIGNAL`            |
| SpyGlass   | `W_USIG`                  |
| VC Static  | `LINT-UNUSED`             |
| Questa     | `LINT_UNUSED`             |
| JasperGold | `SUPERLINT_UNUSED`        |
| 0-in       | `ZIN_UNUSED`              |

## Undriven signals

| Tool       | Rule ID(s)                |
|------------|---------------------------|
| Verilator  | `UNDRIVEN`                |
| SpyGlass   | `W_USIG`                  |
| VC Static  | `LINT-UNDRIVEN`           |
| Questa     | `LINT_UNDRIVEN`           |
| JasperGold | `SUPERLINT_UNDRIVEN`      |
| 0-in       | `ZIN_UNDRIVEN`            |

## Notes

- Rule ids are tool-native and used verbatim in waivers. This library does
  not invent portable ids; the translation table above is documentation only.
- Coverage varies: not every tool checks every category, and the depth of
  each check differs significantly.
- Exact rule ids should be confirmed against each tool's current documentation
  and actual output.
