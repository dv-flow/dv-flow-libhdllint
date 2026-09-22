#****************************************************************************
#* test_qst_parser.py
#*
#* Copyright 2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may
#* not use this file except in compliance with the License.
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software
#* distributed under the License is distributed on an "AS IS" BASIS,
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#* See the License for the specific language governing permissions and
#* limitations under the License.
#*
#****************************************************************************
"""Questa Lint (AutoCheck) output -> Finding, against synthetic tool output.

All test input is synthetic inline strings -- no captured tool output, no
fixture files. This keeps the tests independent of any particular Questa
release.
"""

import pytest

from dv_flow.mgr.task_data import SeverityE
from dv_flow.libhdllint import qst_parser


def by_rule(findings):
    d = {}
    for f in findings:
        d.setdefault(f.rule, []).append(f)
    return d


def test_parses_warnings_with_rule_and_location():
    findings = qst_parser.parse([
        "** Warning: (LINT_LATCH) dummy_rtl/alu.v(44): Latch inferred for signal 'q'",
    ])
    assert len(findings) == 1
    f = findings[0]
    assert f.tool == "qst"
    assert f.tool_name == "questa_lint"
    assert f.severity == SeverityE.Warning
    assert f.path == "dummy_rtl/alu.v"
    assert f.line == 44
    assert f.msg == "Latch inferred for signal 'q'"


def test_parses_errors():
    findings = qst_parser.parse([
        "** Error: (LINT_SYNTH) dummy_rtl/mux.v(12): Synthesis issue detected",
    ])
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == SeverityE.Error
    assert f.rule == "LINT_SYNTH"
    assert f.path == "dummy_rtl/mux.v"
    assert f.line == 12


def test_note_maps_to_info_severity():
    findings = qst_parser.parse([
        "** Note: (LINT_WIDTH) dummy_rtl/fifo.v(8): Width mismatch in assignment",
    ])
    assert len(findings) == 1
    assert findings[0].severity == SeverityE.Info
    assert findings[0].rule == "LINT_WIDTH"


def test_rule_extraction():
    findings = qst_parser.parse([
        "** Warning: (LINT_LATCH) dummy_rtl/alu.v(44): Latch inferred",
        "** Error: (LINT_SYNTH) dummy_rtl/mux.v(12): Synthesis issue",
        "** Note: (LINT_WIDTH) dummy_rtl/fifo.v(8): Width mismatch",
    ])
    rules = by_rule(findings)
    assert set(rules.keys()) == {"LINT_LATCH", "LINT_SYNTH", "LINT_WIDTH"}


def test_continuation_lines_excluded():
    """Run chatter like '# Loading', '# Compiling', separator dashes, and
    '# Total:' lines are not findings."""
    findings = qst_parser.parse([
        "# Loading work.alu",
        "# Compiling dummy_rtl/alu.v",
        "------------------------------------------------------------",
        "** Warning: (LINT_LATCH) dummy_rtl/alu.v(44): Latch inferred",
        "# ** Report Summary",
        "# Total: 1 warning",
    ])
    assert len(findings) == 1
    assert findings[0].rule == "LINT_LATCH"


def test_empty_input():
    assert qst_parser.parse([]) == []


def test_paths_are_relativized():
    findings = qst_parser.parse(
        ["** Warning: (LINT_LATCH) /proj/rtl/a.v(4): Latch inferred for signal 'q'"],
        root="/proj")
    assert findings[0].path == "rtl/a.v"


def test_paths_outside_root_stay_absolute():
    findings = qst_parser.parse(
        ["** Warning: (LINT_LATCH) /opt/ip/a.v(4): Latch inferred for signal 'q'"],
        root="/proj")
    assert findings[0].path == "/opt/ip/a.v"


def test_message_without_location():
    """A finding line where the rest after the rule has no path(line): pattern."""
    findings = qst_parser.parse([
        "** Error: (LINT_ELAB) Design elaboration failed",
    ])
    assert len(findings) == 1
    assert findings[0].path == ""
    assert findings[0].line == -1
    assert findings[0].msg == "Design elaboration failed"
