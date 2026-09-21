# Reports

One normalized finding list, three renderings, each for a different reader.

```
rundir/lint/lint.json         the authoritative record
rundir/lint/lint.sarif        code review and IDE problem lists
rundir/lint/lint-ctrf.json    the CI test-report UI
```

The basename comes from `report:` (default `lint`); SARIF and CTRF can be
switched off individually with `sarif: false` / `ctrf: false`.

| File | For |
|------|-----|
| `lint.json` | The authoritative record. Everything, including waived and baselined findings with their reasons, the duplicates dedup dropped, and what each tool actually ran. It is what the baseline updater and any triage step read. |
| `lint.sarif` | SARIF 2.1.0 -- GitHub code scanning annotations and IDE problem lists. |
| `lint-ctrf.json` | CTRF -- the CI test-report UI. |

## Markers, and why the files still matter

Findings also surface as dv-flow markers, which is what you see on the console.
`max_markers:` caps how many (0, the default, is no cap) and says by how much
it truncated when it does. The full set is always in the report file -- the
marker stream is a view, never the record.

## SARIF

This is the piece no EDA vendor ships: it gets every backend, commercial ones
included, into a code-review annotation with no per-tool integration.

```yaml
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: rundir/lint/lint.sarif
```

Suppressed findings are emitted **with** a SARIF `suppressions` entry rather
than dropped, because that is how the format says to express one -- and it puts
the waiver's reason in front of the reader at the place the finding is, which
is the one moment it is useful.

## CTRF

```yaml
- uses: ctrf-io/github-test-reporter@v1
  if: always()
  with:
    report-path: 'rundir/lint/lint-ctrf.json'
```

The mapping is one finding, one "test":

| Finding | CTRF status |
|---|---|
| counts against the gate | `failed` |
| waived or baselined | `skipped`, with the reason in the message |
| new, but below the `fail_on` threshold | `other` |

A tool that ran and contributed no failure adds one `passed` entry. Without it
a clean run renders as an empty report, which is indistinguishable in the UI
from a lint run that never happened.

## Dedup is recorded, not just applied

`dedup: true` (the default) collapses the same finding reported by more than
one tool, and the dropped findings are written into `lint.json` rather than
discarded. Dedup is a heuristic -- two tools word the same defect differently
often enough that it can over- or under-merge -- and a heuristic that leaves no
trace is not auditable. `dedup: false` turns it off.

It is a **cross-tool** operation only. Two findings from the same tool that
share a key are not duplicates: the key normalizes numbers out of the message,
so two different width mismatches on one line share a key while being two
distinct defects.

## The `hdllint.Report` item

The same counts reach the rest of the flow as a data item, so a downstream task
can act on a lint result without parsing a file:

`passed`, `status`, `findings`, `new`, `waived`, `baselined`, `duplicates`,
`errors`, `warnings`, `infos`, `gating`, `fail_on`, `tools`, `skipped`, and the
paths `report` / `sarif` / `ctrf`.

See the {doc}`type reference <../reference/hdllint>` for each field, and
[the gate](gate.md) for why there is no `total`.
