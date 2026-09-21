"""SpyGlass output -> Finding, against synthetic message data.

Synthetic SpyGlass-format text for parser testing. These are NOT captured
tool output -- they are hand-written strings that follow the documented
SpyGlass message format, so the tests remain valid without a SpyGlass
installation and without distributing proprietary log files.
"""

import pytest

from dv_flow.mgr.task_data import SeverityE
from dv_flow.libhdllint import spy_parser


# ------------------------------------------------------------------ helpers

def by_rule(findings):
    d = {}
    for f in findings:
        d.setdefault(f.rule, []).append(f)
    return d


# ------------------------------------------------- synthetic message blocks

# A representative mix of severity levels, rule ids, and locations.
BASIC_MESSAGES = [
    "Warning W_REDF dummy_rtl/mux.v:12 Redundant else branch in always block",
    "Error   SYNTH_5130 dummy_rtl/alu.v:44 Latch inferred for signal 'q'",
    "Info    STARC05-1.3.1.3 dummy_rtl/fifo.v:8 Width mismatch in port connection",
]

# A block that includes header/summary/separator lines that must be excluded.
NOISY_BLOCK = [
    "SpyGlass Version: S-2021.09",
    "------------------------------------------------------------",
    "Running goal: lint/lint_rtl",
    "Warning W_REDF dummy_rtl/mux.v:12 Redundant else branch in always block",
    "  continued explanation of the warning",
    "Total: 1 Warning(s), 0 Error(s)",
    "------------------------------------------------------------",
]

# A message without a file:line location.
NO_LOCATION = [
    "Warning W_NOFILE Design has no testbench wrapper",
]


# ------------------------------------------------------------------- tests

def test_parses_rule_id():
    findings = spy_parser.parse(BASIC_MESSAGES)
    rules = by_rule(findings)
    assert "W_REDF" in rules
    assert "SYNTH_5130" in rules
    assert "STARC05-1.3.1.3" in rules


def test_severity_mapping():
    findings = spy_parser.parse(BASIC_MESSAGES)
    rules = by_rule(findings)
    assert rules["W_REDF"][0].severity == SeverityE.Warning
    assert rules["SYNTH_5130"][0].severity == SeverityE.Error
    assert rules["STARC05-1.3.1.3"][0].severity == SeverityE.Info


def test_file_and_line_location():
    findings = spy_parser.parse(BASIC_MESSAGES)
    rules = by_rule(findings)
    f = rules["W_REDF"][0]
    assert f.path == "dummy_rtl/mux.v"
    assert f.line == 12
    assert f.pos == -1  # SpyGlass messages do not carry a column


def test_tool_identity():
    findings = spy_parser.parse(BASIC_MESSAGES)
    assert all(f.tool == "spy" for f in findings)
    assert all(f.tool_name == "spyglass" for f in findings)


def test_summary_and_header_lines_excluded():
    """The SpyGlass banner, goal headers, tally lines, and separator rules
    are not findings. A parser that treats them as findings manufactures
    phantom errors on every run."""
    findings = spy_parser.parse(NOISY_BLOCK)
    assert len(findings) == 1
    assert findings[0].rule == "W_REDF"


def test_continuation_lines_attached_to_finding():
    """Lines that follow a finding and do not match the message pattern are
    continuation text, kept with the finding for traceability."""
    findings = spy_parser.parse(NOISY_BLOCK)
    assert "continued explanation" in findings[0].raw


def test_empty_input():
    assert spy_parser.parse([]) == []


def test_paths_are_relativized_to_the_project_root():
    findings = spy_parser.parse(
        ["Warning W_REDF /proj/rtl/a.v:4 Redundant else branch"],
        root="/proj")
    assert findings[0].path == "rtl/a.v"


def test_paths_outside_the_root_stay_absolute():
    findings = spy_parser.parse(
        ["Warning W_REDF /opt/ip/a.v:4 Redundant else branch"],
        root="/proj")
    assert findings[0].path == "/opt/ip/a.v"


def test_message_without_a_location():
    """Some SpyGlass messages are design-wide and carry no file:line."""
    findings = spy_parser.parse(NO_LOCATION)
    assert len(findings) == 1
    f = findings[0]
    assert f.path == ""
    assert f.line == -1
    assert f.marker().loc is None


def test_every_distinct_rule_parsed():
    findings = spy_parser.parse(BASIC_MESSAGES)
    rules = set(f.rule for f in findings)
    assert rules == {"W_REDF", "SYNTH_5130", "STARC05-1.3.1.3"}
