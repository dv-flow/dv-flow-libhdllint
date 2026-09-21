# dv-flow-libhdllint

dv-flow tasks for running HDL lint tools and reporting their findings in one
normalized form.

Status: **phase 0/1** -- the tool-independent core and the Verilator backend
are implemented and tested. **Phase 1** adds five more backends: SpyGlass,
VC Static, Questa Lint, JasperGold, and 0-in -- six backends in total.

## What it does

```yaml
- name: rtl
  uses: std.FileSet
  with: {type: verilogSource, base: rtl, include: "*.v"}

- name: lint
  uses: hdllint.Rtl
  needs: [rtl]
  with:
    top: [my_top]
```

```
$ dfm run lint
  W [verilator:WIDTHTRUNC] Operator ASSIGNW expects 1 bits ... (rtl/top.v:344)
  W [verilator:UNUSEDSIGNAL] Signal is not used: 'rst' (rtl/wb_mast.v:85)
  I lint: 2 new findings: 2 warnings [fail_on=error]
  I Lint reports: rundir/lint/lint.json, rundir/lint/lint.sarif, rundir/lint/lint-ctrf.json
```

## How it differs from `dv-flow-libhdlsim`

`hdlsim` selects exactly **one** simulator: `hdlsim.sim` is a scalar and an
`elaborate:` clause rebinds `uses:` to `hdlsim.<sim>.<Family>`.

`hdllint` does not. Lint is normally run with several tools at once, because
what each tool sees barely overlaps with what the others see. So the family
tasks take `tools:` -- a **list** -- and merge the results into one report.
An empty list (the default) means "every registered tool that implements this
family and is installed", which is what makes `uses: hdllint.Rtl` work with no
configuration. `hdllint.vlt.Rtl` is the same task with `tools:` pinned.

A **named** tool that is not installed is an error; an **auto-selected** tool
that is not installed is a skip, reported as an Info marker. Asking a tool for
a family it does not implement is an error naming the alternatives. A report
is never quietly thin.

## Families

| | `Rtl` | `Tb` | `Style` |
|---|---|---|---|
| `vlt` (Verilator) | yes | no -- synthesis subset, cannot see classes | no |
| `spy` (SpyGlass) | yes | -- | yes |
| `z0i` (0-in) | yes | -- | -- |
| `vcs` (VC Static) | yes | -- | yes |
| `qst` (Questa Lint) | yes | -- | -- |
| `jg` (JasperGold) | yes | -- | -- |

`Tb` is declared but has no backend yet. `Style` is implemented by `spy` and `vcs`.

## Reports

Three renderings of one finding list, for three readers:

| File | For |
|---|---|
| `lint.json` | The authoritative record. Everything, including waived and baselined findings with their reasons, the duplicates dedup dropped, and what each tool actually ran. |
| `lint.sarif` | SARIF 2.1.0 -- GitHub code scanning annotations and IDE problem lists. Suppressed findings are emitted *with* a SARIF `suppressions` entry, so waiver reasons are visible where the findings are. |
| `lint-ctrf.json` | CTRF -- the CI test-report UI. |

### CI

SARIF into GitHub code scanning:

```yaml
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: rundir/lint/lint.sarif
```

CTRF into the run summary, using the same action dv-flow's own CI uses for
test results:

```yaml
- uses: ctrf-io/github-test-reporter@v1
  if: always()
  with:
    report-path: 'rundir/lint/lint-ctrf.json'
```

The CTRF mapping: each finding is one "test". A finding that counts against
the gate is `failed`; one that is waived or baselined is `skipped`; a new
finding below the gate threshold is `other`. A tool that ran and contributed
no failure adds one `passed` entry -- without it a clean run renders as an
empty report, which is indistinguishable from a lint run that never happened.

## Waivers

One format, in a YAML file or inline on a `hdllint.LintWaivers` item:

```yaml
waivers:
- rule: WIDTHEXPAND
  path: "packages/wb_dma/**"
  reason: "Third-party DUT, not modified by this project"
- rule: UNUSEDSIGNAL
  path: "**/wb_dma_wb_if.v"
  line: 142
  reason: "Tied off by design; see DESIGN.md#wb-if"
```

`rule` and `path` are globs where `*` crosses directory separators; `tool` and
`line` are optional. **`reason` is required** -- a waiver without one is a load
error. A waiver that matches nothing is reported as a warning: the finding was
either fixed (delete it) or moved (fix it).

Two ways to enforce the same file, chosen with `waiver_mode:`:

* **`post`** (default) -- every check runs and findings are filtered
  afterwards. Uniform across all backends, and exact: waived findings are
  counted and stale waivers are detected.
* **`native`** -- each backend additionally lowers what it can express into
  its own syntax (Verilator gets a generated `.vlt` with
  `lint_off -rule ... -file ... -lines ...`). The tool then never runs the
  check. The cost is accounting: a natively suppressed finding is never
  emitted, so it is not counted as waived and a stale one cannot be detected
  -- the run says so rather than reporting a misleading `waived: 0`.

Lowering is always **partial**, and the remainder is post-filtered. Switching
modes changes how much work the tool does and how precise the accounting is --
never whether a waiver is in force.

## Baseline

The feature that decides whether lint gets adopted on existing code or gets
switched off in week two.

```yaml
with:
  baseline: lint-baseline.json
```

```
$ dfm run lint -D lint.update_baseline=true   # accept today's findings
$ dfm run lint
  I lint: 0 new findings (97 baselined) [fail_on=error]
```

Baseline entries are keyed on `(tool, rule, file, message-shape)` -- **not**
the line number, or any edit above a finding invalidates it. Matching is
count-aware, so three baselined and five today is two new findings. Findings
in the baseline that no longer occur are reported, so the baseline visibly
shrinks as code is fixed.

## The gate

`fail_on:` is `none` | `error` | `warning` | `any`, and only **new** findings
count -- waived and baselined ones have already been accepted. Failure is an
explicit policy rather than a side effect of severity, so someone adopting
lint can run it, see error findings, and still get a zero exit while they work
through them.

## Adding a backend

1. A row in `BACKENDS` (`backends.py`): id, tool name, executable, the
   families it implements, and its runner.
2. `<tool>_parser.py` -- text in, `Finding`s out. Pure, so it is testable with
   no tool installed.
3. `<tool>_lint.py` -- build the command line, run it, parse the log.
4. `<tool>_waivers.py` -- optional native lowering. Return only the waivers
   you can express *exactly*; the rest is post-filtered.
5. `<tool>_flow.dv` + an `__ext__.py` entry.
6. Recorded tool output in `tests/unit/data/`, with the tool version in the
   filename.

## Trademarks

All tool names are the property of their respective owners.
