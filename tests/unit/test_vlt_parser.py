"""Verilator output -> Finding, against recorded tool output.

The fixtures in `data/` carry the Verilator version in their filename.
Verilator's message wording and rule set both move between releases, so a
fixture that cannot be attributed to a version cannot be refreshed by anyone
but the person who captured it.
"""

import os

import pytest

from dv_flow.mgr.task_data import SeverityE
from dv_flow.libhdllint import vlt_parser

DATA = os.path.join(os.path.dirname(__file__), "data")


def parse_fixture(name):
    return vlt_parser.parse_file(os.path.join(DATA, name))


def by_rule(findings):
    d = {}
    for f in findings:
        d.setdefault(f.rule, []).append(f)
    return d


def test_parses_warnings_with_rule_and_location():
    findings = parse_fixture("vlt-5.052-lint.log")
    rules = by_rule(findings)

    assert "WIDTHTRUNC" in rules
    f = rules["WIDTHTRUNC"][0]
    assert f.tool == "vlt"
    assert f.tool_name == "verilator"
    assert f.severity == SeverityE.Warning
    assert f.path == "width_mismatch.v"
    assert f.line == 5
    assert f.pos == 9
    assert f.msg.startswith("Operator ASSIGNDLY expects 4 bits")


def test_parses_every_distinct_rule_in_the_fixture():
    rules = by_rule(parse_fixture("vlt-5.052-lint.log"))
    assert set(rules.keys()) == {"MULTITOP", "WIDTHTRUNC", "UNUSEDSIGNAL", "LATCH"}


def test_continuation_lines_do_not_become_findings():
    """The source echo, the caret line and the "For warning description see..."
    footer are all continuation. A parser that treats them as findings
    multiplies every real finding by four."""
    findings = parse_fixture("vlt-5.052-lint.log")
    assert len(findings) == 4
    # ...and the continuation is kept on the finding, for parser debugging.
    widths = [f for f in findings if f.rule == "WIDTHTRUNC"]
    assert "For warning description see" in widths[0].raw


def test_syntax_error_has_no_rule_and_is_an_error():
    findings = parse_fixture("vlt-5.052-syntax-error.log")
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == SeverityE.Error
    assert f.rule == ""          # %Error: with no -CODE
    assert f.path == "syn.v"
    assert f.line == 1
    assert f.pos == 21
    assert "syntax error" in f.msg
    # No rule id -> the marker names the tool alone, and stays waivable by path
    assert f.label == "verilator"
    assert f.marker().msg.startswith("[verilator] syntax error")


def test_exiting_due_to_tally_is_not_a_finding():
    """`%Error: Exiting due to 1 error(s)` is a run tally. Counting it adds a
    phantom error to every failing run."""
    findings = parse_fixture("vlt-5.052-syntax-error.log")
    assert not any("Exiting due to" in f.msg for f in findings)


def test_message_without_a_location():
    findings = vlt_parser.parse([
        "%Error: Specified --top-module 'nope' was not found in design.",
        "        ... See the manual at https://verilator.org/ for more assistance.",
    ])
    assert len(findings) == 1
    assert findings[0].path == ""
    assert findings[0].line == -1
    assert findings[0].marker().loc is None


def test_paths_are_relativized_to_the_project_root():
    findings = vlt_parser.parse(
        ["%Warning-LATCH: /proj/rtl/a.v:4:4: Latch inferred for signal 'q'"],
        root="/proj")
    assert findings[0].path == "rtl/a.v"


def test_paths_outside_the_root_stay_absolute():
    """A `../../..` chain is not more portable than an absolute path, only
    less readable."""
    findings = vlt_parser.parse(
        ["%Warning-LATCH: /opt/ip/a.v:4:4: Latch inferred for signal 'q'"],
        root="/proj")
    assert findings[0].path == "/opt/ip/a.v"


def test_line_only_location():
    findings = vlt_parser.parse(["%Warning-FOO: a.v:12: something happened"])
    assert findings[0].path == "a.v"
    assert findings[0].line == 12
    assert findings[0].pos == -1


def test_empty_input():
    assert vlt_parser.parse([]) == []
