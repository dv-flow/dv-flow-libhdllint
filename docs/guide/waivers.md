# Waivers

One waiver format, applied uniformly across every backend.

## Format

Waivers live in a YAML file or inline on a `hdllint.LintWaivers` item:

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

### Fields

| Field    | Required | Default | Description |
|----------|----------|---------|-------------|
| `reason` | **yes**  | --      | Why the finding is acceptable |
| `rule`   | no       | `*`     | Rule id glob (fnmatch) |
| `tool`   | no       | (any)   | Backend id or tool name |
| `path`   | no       | (any)   | File path glob; `*` crosses directories |
| `line`   | no       | (any)   | Exact line number |

`reason` is required -- a waiver without one is a load error. `rule` and
`path` are fnmatch globs where `*` crosses directory separators.

## Matching

Every field is optional and defaults to "matches anything". A waiver with
only a `reason` and `rule: "*"` waives everything.

- `rule`: fnmatch against the tool's native rule id
- `tool`: matches either the backend id (`vlt`) or the tool name (`verilator`)
- `path`: fnmatch against the finding's path; the basename is also tried
- `line`: exact match when specified

First match wins. A waiver that matches nothing is reported as a stale
warning.

## `waiver_mode`

| Mode     | Behaviour |
|----------|-----------|
| `post`   | Every check runs; findings are filtered afterwards. Uniform across all backends, exact accounting. **Default.** |
| `native` | Each backend additionally lowers what it can express into its own suppression syntax. The tool then never runs the check. |

### Native lowering by tool

| Backend | Lowering support | Format |
|---------|-----------------|--------|
| `vlt`   | yes | `.vlt` config: `lint_off -rule ... -file ... -lines ...` |
| `spy`   | yes | `.swl` waiver file: `waive -rule {rule} -file {pattern} -comment "{reason}"` |
| `vcs`   | yes | `.swl` waiver file (SpyGlass-compatible) |
| `qst`   | no  | Post-filter only |
| `jg`    | no  | Post-filter only |
| `z0i`   | no  | Post-filter only |

### What cannot be lowered

These waiver patterns are always handled by the post-filter, regardless of
`waiver_mode`:

- A glob in `rule` (e.g. `WIDTH*`)
- A waiver scoped to a different tool
- A bare basename path (no `/` in the pattern)
- A waiver with no `rule` (for findings that have no rule id)

Lowering is always **partial**: whatever cannot be expressed natively is
still applied by the post-filter. Switching modes never silently drops a
waiver.

### Accounting difference

Under `post` mode, waived findings are counted and stale waivers are
detected. Under `native` mode, natively suppressed findings are never
emitted by the tool, so they cannot be counted as waived and stale waivers
among them cannot be detected. The run reports this explicitly.
