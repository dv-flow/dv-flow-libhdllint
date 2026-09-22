# Contributing

## The development environment

```shell
pip install --upgrade --pre ivpm
ivpm update -a -d default-dev
./packages/python/bin/pytest tests
```

`ivpm update` assembles `packages/python`, a virtual environment holding the
runtime dependencies, pytest, the documentation toolchain, and Verilator from
edapack. Verilator is the reference backend and the only one the system tests
can exercise out of the box; every other backend is resolved from `PATH` at run
time and skipped (with an Info marker) when absent.

## Building the documentation

```shell
make -C docs html
```

The `Makefile` defaults `SPHINXBUILD` to `packages/python/bin/sphinx-build`, so
the docs build against the same ivpm environment. Override it for any other:
`make -C docs html SPHINXBUILD=sphinx-build`.

The task reference is generated from the flow files by
[sphinx-dv-flow](https://github.com/dv-flow/sphinx-dv-flow), which is **not on
PyPI** -- `pip install .[docs]` gets the whole toolchain except that one, and
`ivpm update -a -d default-dev` gets all of it. A page that disagrees with the
library is therefore a bug in the flow file's `desc:`/`doc:` rather than in the
page, and `docs/_build/html/dvflow-coverage.txt` lists every parameter with no
`doc:` at all.

Documentation is published to <https://dvkit.org/dv-flow/dv-flow-libhdllint/>
by `.forgejo/workflows/docs.yml`. Nothing else publishes it -- see
[`docs-pipeline`](https://dvkit.org/) for the wider picture.

## Releasing

Tag it. That is the entire procedure.

```shell
git tag v0.0.2 && git push origin v0.0.2
```

A push to a branch never publishes: branch builds are stamped with a PEP 440
local version segment (`0.0.2.dev33020374597+gh.g7775f37`), which PyPI rejects
outright. The tag *is* the version, and it must match `version` in
`pyproject.toml` and `VERSION` in `src/dv_flow/libhdllint/__init__.py` -- those
two are rewritten in place by the shared release workflow, and the spacing in
`__init__.py` (`VERSION="..."`, no spaces) is what its `sed` matches.

## Contributing a backend

Adding a lint tool backend to `dv-flow-libhdllint` is a bounded, self-contained
task. Here is the step-by-step guide.

### Prerequisites

Read `backends.py` -- it defines the registry, the `Backend` dataclass, and
the `ToolRequest`/`ToolRun` protocol.

### Step 1: Registry row

Add a `Backend` entry to the `BACKENDS` dict in `backends.py`:

```python
BACKENDS["xyz"] = Backend(
    id="xyz",
    name="my_tool",
    exe="my_tool_exe",
    families=("Rtl",),
    runner="dv_flow.libhdllint.xyz_lint:run",
    desc="My tool: what it checks.")
```

Fields:
- `id`: the short name used in `tools:` lists
- `name`: the tool's display name
- `exe`: the executable looked up on PATH
- `families`: tuple of families this tool implements (`"Rtl"`, `"Tb"`, `"Style"`)
- `runner`: `"module:function"` string for the run entry point
- `lowerer`: optional `"module:function"` for native waiver lowering
- `desc`: one-line description

### Step 2: Parser -- `xyz_parser.py`

A pure module: text in, `Finding` list out. No tool installation needed to
test.

```python
TOOL_ID = "xyz"
TOOL_NAME = "my_tool"

def parse(lines: Iterable[str], root: str = "") -> List[Finding]:
    ...

def parse_file(path: str, root: str = "") -> List[Finding]:
    with open(path, "r", errors="replace") as fp:
        return parse(fp.read().splitlines(), root)
```

Key rules:
- Map tool severities to `SeverityE.Error`, `.Warning`, `.Info`
- Exclude summary/tally lines
- Use `relpath(path, root)` for path normalization
- Attach continuation lines to the preceding finding's `raw` field

### Step 3: Runner -- `xyz_lint.py`

Builds the command line, runs the tool, parses the log.

```python
async def run(ctxt, req: ToolRequest) -> Tuple[ToolRun, List[Finding], List[str]]:
    ...
```

Key rules:
- Define `PROFILES` mapping `basic`/`default`/`strict` to tool flags
- Write a command file for reproducibility
- Use `exec_tool()` from `util.py` (not `ctxt.exec`)
- Use `tool_version()` to capture the tool version
- Report non-zero exit with no findings as an error

### Step 4: Waiver lowerer -- `xyz_waivers.py` (optional)

Only needed if the tool has a native suppression syntax.

```python
def lower(waivers: List[Waiver], req: ToolRequest) -> Tuple[List[str], List[Waiver]]:
    ...
```

Returns `(extra_args, lowered_waivers)`. Only lower waivers you can express
exactly; everything else is handled by the post-filter.

### Step 5: Flow file -- `xyz_flow.dv`

A DFM package that exports family tasks with `tools:` pinned:

```yaml
package:
  name: hdllint.xyz
  imports:
  - name: hdllint
  tasks:
  - export: Rtl
    uses: hdllint.Rtl
    with:
      tools:
        type: list
        value: [xyz]
```

### Step 6: Plugin registration -- `__ext__.py`

Add the sub-package to `dvfm_packages()`:

```python
'hdllint.xyz': os.path.join(hdllint_dir, "xyz_flow.dv"),
```

### Step 7: Report URI -- `report.py`

Add a `_TOOL_URI` entry for the SARIF driver's `informationUri`.

### Step 8: Tests

#### Unit tests -- `tests/unit/test_xyz_parser.py`

For commercial tools, use **synthetic inline strings** that replicate the
documented output format with fabricated content. Do not commit captured
tool logs.

Test:
- Rule extraction and severity mapping
- File/line/column location parsing
- Summary/continuation line exclusion
- Empty input
- Path relativization
- Messages without locations

#### System tests

Add the tool to the availability matrix in `tests/system/test_rtl_lint.py`.
System tests are gated on the tool being installed.

### Checklist

- [ ] Registry row in `backends.py`
- [ ] `xyz_parser.py` with `parse()` and `parse_file()`
- [ ] `xyz_lint.py` with `async def run()`
- [ ] `xyz_flow.dv` with pinned `tools:`
- [ ] `__ext__.py` entry
- [ ] `report.py` `_TOOL_URI` entry
- [ ] `tests/unit/test_xyz_parser.py`
- [ ] `tests/unit/test_xyz_waivers.py` (if waiver lowering)
- [ ] System test matrix updated
- [ ] No vendor names except in the tool's own `name` and `desc` fields
