#****************************************************************************
#* test_z0i_parser.py
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
"""0-in lint output -> Finding, against synthetic tool output.

All test input is synthetic inline strings -- no captured tool output, no
fixture files. This keeps the tests independent of any particular 0-in
release.
"""

import pytest

from dv_flow.mgr.task_data import SeverityE
from dv_flow.libhdllint import z0i_parser


def by_rule(findings):
    d = {}
    for f in findings:
        d.setdefault(f.rule, []).append(f)
    return d


def test_parses_warnings_with_rule_and_location():
    findings = z0i_parser.parse([
        "Warning: [ZIN_LATCH] dummy_rtl/alu.v:44: Latch inferred for signal 'q'",
    ])
    assert len(findings) == 1
    f = findings[0]
    assert f.tool == "z0i"
    assert f.tool_name == "0-in"
    assert f.severity == SeverityE.Warning
    assert f.path == "dummy_rtl/alu.v"
    assert f.line == 44
    assert f.msg == "Latch inferred for signal 'q'"


def test_parses_errors():
    findings = z0i_parser.parse([
        "Error: [ZIN_WIDTH] dummy_rtl/mux.v:12: Width mismatch detected",
    ])
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == SeverityE.Error
    assert f.rule == "ZIN_WIDTH"
    assert f.path == "dummy_rtl/mux.v"
    assert f.line == 12


def test_parses_info():
    findings = z0i_parser.parse([
        "Info: [ZIN_UNUSED] dummy_rtl/fifo.v:8: Signal 'tmp' is never read",
    ])
    assert len(findings) == 1
    assert findings[0].severity == SeverityE.Info
    assert findings[0].rule == "ZIN_UNUSED"


def test_rule_extraction():
    findings = z0i_parser.parse([
        "Warning: [ZIN_LATCH] dummy_rtl/alu.v:44: Latch inferred",
        "Error: [ZIN_WIDTH] dummy_rtl/mux.v:12: Width mismatch",
        "Info: [ZIN_UNUSED] dummy_rtl/fifo.v:8: Signal unused",
    ])
    rules = by_rule(findings)
    assert set(rules.keys()) == {"ZIN_LATCH", "ZIN_WIDTH", "ZIN_UNUSED"}


def test_noise_lines_excluded():
    """Run chatter like '0-in Version:', 'Loading:', 'Total:', and separator
    dashes are not findings."""
    findings = z0i_parser.parse([
        "0-in Version: 4.2.1",
        "Loading: dummy_rtl/alu.v",
        "------------------------------------------------------------",
        "Warning: [ZIN_LATCH] dummy_rtl/alu.v:44: Latch inferred",
        "Total: 1 warning",
    ])
    assert len(findings) == 1
    assert findings[0].rule == "ZIN_LATCH"


def test_empty_input():
    assert z0i_parser.parse([]) == []


def test_paths_are_relativized():
    findings = z0i_parser.parse(
        ["Warning: [ZIN_LATCH] /proj/rtl/a.v:4: Latch inferred for signal 'q'"],
        root="/proj")
    assert findings[0].path == "rtl/a.v"


def test_paths_outside_root_stay_absolute():
    findings = z0i_parser.parse(
        ["Warning: [ZIN_LATCH] /opt/ip/a.v:4: Latch inferred for signal 'q'"],
        root="/proj")
    assert findings[0].path == "/opt/ip/a.v"


def test_message_without_location():
    """A finding line where the rest after the rule has no path:line: pattern."""
    findings = z0i_parser.parse([
        "Error: [ZIN_ELAB] Design elaboration failed",
    ])
    assert len(findings) == 1
    assert findings[0].path == ""
    assert findings[0].line == -1
    assert findings[0].msg == "Design elaboration failed"
