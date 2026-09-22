#****************************************************************************
#* test_jg_parser.py
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
"""JasperGold superlint output -> Finding, against synthetic tool output.

All test input is synthetic inline strings -- no captured tool output, no
fixture files. This keeps the tests independent of any particular JasperGold
release.
"""

import pytest

from dv_flow.mgr.task_data import SeverityE
from dv_flow.libhdllint import jg_parser


def by_rule(findings):
    d = {}
    for f in findings:
        d.setdefault(f.rule, []).append(f)
    return d


def test_parses_csv_warning():
    findings = jg_parser.parse([
        "Warning,SUPERLINT_LATCH,dummy_rtl/alu.v,44,Latch inferred for signal 'q'",
    ])
    assert len(findings) == 1
    f = findings[0]
    assert f.tool == "jg"
    assert f.tool_name == "jaspergold"
    assert f.severity == SeverityE.Warning
    assert f.path == "dummy_rtl/alu.v"
    assert f.line == 44
    assert f.msg == "Latch inferred for signal 'q'"


def test_parses_csv_error():
    findings = jg_parser.parse([
        "Error,SUPERLINT_WIDTH,dummy_rtl/mux.v,12,Width mismatch in port connection",
    ])
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == SeverityE.Error
    assert f.rule == "SUPERLINT_WIDTH"
    assert f.path == "dummy_rtl/mux.v"
    assert f.line == 12


def test_parses_csv_info():
    findings = jg_parser.parse([
        "Info,SUPERLINT_UNUSED,dummy_rtl/fifo.v,8,Signal 'tmp' is unused",
    ])
    assert len(findings) == 1
    assert findings[0].severity == SeverityE.Info
    assert findings[0].rule == "SUPERLINT_UNUSED"


def test_parses_text_format():
    findings = jg_parser.parse([
        "[Warning] SUPERLINT_LATCH: dummy_rtl/alu.v:44: Latch inferred for signal 'q'",
    ])
    assert len(findings) == 1
    f = findings[0]
    assert f.tool == "jg"
    assert f.tool_name == "jaspergold"
    assert f.severity == SeverityE.Warning
    assert f.rule == "SUPERLINT_LATCH"
    assert f.path == "dummy_rtl/alu.v"
    assert f.line == 44
    assert f.msg == "Latch inferred for signal 'q'"


def test_rule_extraction():
    findings = jg_parser.parse([
        "Warning,SUPERLINT_LATCH,dummy_rtl/alu.v,44,Latch inferred",
        "Error,SUPERLINT_WIDTH,dummy_rtl/mux.v,12,Width mismatch",
        "Info,SUPERLINT_UNUSED,dummy_rtl/fifo.v,8,Signal unused",
    ])
    rules = by_rule(findings)
    assert set(rules.keys()) == {"SUPERLINT_LATCH", "SUPERLINT_WIDTH", "SUPERLINT_UNUSED"}


def test_header_lines_excluded():
    """CSV header line and separator dashes are not findings."""
    findings = jg_parser.parse([
        "severity,rule,path,line,message",
        "---",
        "Warning,SUPERLINT_LATCH,dummy_rtl/alu.v,44,Latch inferred",
    ])
    assert len(findings) == 1
    assert findings[0].rule == "SUPERLINT_LATCH"


def test_empty_lines_excluded():
    findings = jg_parser.parse([
        "",
        "Warning,SUPERLINT_LATCH,dummy_rtl/alu.v,44,Latch inferred",
        "",
    ])
    assert len(findings) == 1


def test_empty_input():
    assert jg_parser.parse([]) == []


def test_paths_are_relativized():
    findings = jg_parser.parse(
        ["Warning,SUPERLINT_LATCH,/proj/rtl/a.v,4,Latch inferred"],
        root="/proj")
    assert findings[0].path == "rtl/a.v"


def test_paths_outside_root_stay_absolute():
    findings = jg_parser.parse(
        ["Warning,SUPERLINT_LATCH,/opt/ip/a.v,4,Latch inferred"],
        root="/proj")
    assert findings[0].path == "/opt/ip/a.v"


def test_mixed_csv_and_text():
    """Both CSV and text format lines in the same input."""
    findings = jg_parser.parse([
        "Warning,SUPERLINT_LATCH,dummy_rtl/alu.v,44,Latch inferred",
        "[Error] SUPERLINT_WIDTH: dummy_rtl/mux.v:12: Width mismatch",
    ])
    assert len(findings) == 2
    assert findings[0].rule == "SUPERLINT_LATCH"
    assert findings[1].rule == "SUPERLINT_WIDTH"
