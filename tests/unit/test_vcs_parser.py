#****************************************************************************
#* test_vcs_parser.py
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
"""VC Static output -> Finding, against synthetic inline fixtures.

Synthetic VC Static-format text for parser testing.
"""

import pytest

from dv_flow.mgr.task_data import SeverityE
from dv_flow.libhdllint import vcs_parser


# -- helpers ----------------------------------------------------------------

def by_rule(findings):
    d = {}
    for f in findings:
        d.setdefault(f.rule, []).append(f)
    return d


# -- fixtures ---------------------------------------------------------------

SAMPLE_LINES = [
    "== VC Static Lint Report ==",
    "VC Static Version: 2024.06-SP1",
    "Warning LINT-1 dummy_rtl/mux.v:12 Redundant condition detected",
    "Error   ELAB-4 dummy_rtl/alu.v:44 Latch inferred for signal 'q'",
    "Info    STYLE-2 dummy_rtl/fifo.v:8 Signal naming convention violation",
    "---",
    "Total: 3 findings",
]


# -- tests ------------------------------------------------------------------

def test_extracts_rule_ids():
    findings = vcs_parser.parse(SAMPLE_LINES)
    rules = {f.rule for f in findings}
    assert rules == {"LINT-1", "ELAB-4", "STYLE-2"}


def test_severity_mapping():
    findings = vcs_parser.parse(SAMPLE_LINES)
    rules = by_rule(findings)
    assert rules["LINT-1"][0].severity == SeverityE.Warning
    assert rules["ELAB-4"][0].severity == SeverityE.Error
    assert rules["STYLE-2"][0].severity == SeverityE.Info


def test_file_and_line():
    findings = vcs_parser.parse(SAMPLE_LINES)
    rules = by_rule(findings)

    f = rules["LINT-1"][0]
    assert f.path == "dummy_rtl/mux.v"
    assert f.line == 12

    f = rules["ELAB-4"][0]
    assert f.path == "dummy_rtl/alu.v"
    assert f.line == 44


def test_tool_identity():
    findings = vcs_parser.parse(SAMPLE_LINES)
    for f in findings:
        assert f.tool == "vcs"
        assert f.tool_name == "vc_static"


def test_summary_lines_excluded():
    """Lines starting with '==', 'VC Static Version:', 'Total:', '---'
    must not produce findings."""
    findings = vcs_parser.parse(SAMPLE_LINES)
    assert len(findings) == 3
    assert not any("VC Static" in f.msg for f in findings)
    assert not any("Total" in f.msg for f in findings)


def test_empty_input():
    assert vcs_parser.parse([]) == []


def test_paths_are_relativized_to_the_project_root():
    lines = ["Warning LINT-1 /proj/rtl/a.v:4 Redundant condition detected"]
    findings = vcs_parser.parse(lines, root="/proj")
    assert findings[0].path == "rtl/a.v"


def test_paths_outside_the_root_stay_absolute():
    lines = ["Warning LINT-1 /opt/ip/a.v:4 Redundant condition detected"]
    findings = vcs_parser.parse(lines, root="/proj")
    assert findings[0].path == "/opt/ip/a.v"


def test_message_text():
    findings = vcs_parser.parse(SAMPLE_LINES)
    rules = by_rule(findings)
    assert rules["ELAB-4"][0].msg == "Latch inferred for signal 'q'"


def test_raw_preserves_original_line():
    findings = vcs_parser.parse(SAMPLE_LINES)
    for f in findings:
        assert f.raw  # every finding keeps its raw line
