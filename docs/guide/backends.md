# Backends

`dv-flow-libhdllint` supports six lint tool backends, each identified by a
short id used in `tools:` lists.

## Capability table

| Backend ID | Tool          | Executable         | `Rtl` | `Tb` | `Style` |
|------------|---------------|--------------------|-------|------|---------|
| `vlt`      | Verilator     | `verilator`        | yes   | --   | --      |
| `spy`      | SpyGlass      | `sg_shell`         | yes   | --   | yes     |
| `z0i`      | 0-in          | `0in`              | yes   | --   | --      |
| `vcs`      | VC Static     | `vc_static_shell`  | yes   | --   | yes     |
| `qst`      | Questa Lint   | `qverify`          | yes   | --   | --      |
| `jg`       | JasperGold    | `jg`               | yes   | --   | --      |

## Selection semantics

The `tools:` parameter on a family task (`hdllint.Rtl`, etc.) is a list.

- **Empty list** (the default): every registered backend that implements the
  requested family and whose executable is on PATH is selected. Backends
  whose executable is missing are skipped with an Info marker.
- **Named tools**: each named tool must be registered, must implement the
  requested family, and must have its executable on PATH. Any violation is
  an error, not a silent skip.
- **Unknown tool name**: an error, with a near-match hint when possible.
- **Nothing selected**: an error naming what to install.

The distinction matters: an empty `tools:` means "best effort", and a named
tool means "I need this". A run must never report "no findings" because a
tool the user asked for was silently absent.

## Per-tool sub-packages

Each backend has a sub-package (`hdllint.vlt`, `hdllint.spy`, etc.) that
exports the same family tasks with `tools:` pinned:

```yaml
- name: lint
  uses: hdllint.spy.Rtl
  needs: [rtl]
  with:
    top: [my_top]
```

This is the same task as `hdllint.Rtl` with `tools: [spy]` -- same waivers,
same baseline, same reports.

## Adding a backend

See {doc}`../contributing`.

## Trademarks

All tool names are the property of their respective owners.
