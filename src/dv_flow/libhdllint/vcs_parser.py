#****************************************************************************
#* vcs_parser.py
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
"""VC Static lint output -> `Finding`s.

This is a separate, pure module on purpose: it takes text and returns
findings, so the whole parser is testable against synthetic text with no
VC Static installed.

VC Static in SpyGlass-compatible mode emits one finding per line in the
format:

    <Severity> <RuleID> <path>:<line> <message>

For example:

    Warning LINT-1 dummy_rtl/mux.v:12 Redundant condition detected
    Error   ELAB-4 dummy_rtl/alu.v:44 Latch inferred for signal 'q'
    Info    STYLE-2 dummy_rtl/fifo.v:8 Signal naming convention violation

Summary and decoration lines (lines starting with ``==``,
``VC Static Version:``, ``Total:``, ``---``) are excluded.
"""

import re
from typing import Iterable, List, Optional

from dv_flow.mgr.task_data import SeverityE

from .finding import Finding, relpath

TOOL_ID = "vcs"
TOOL_NAME = "vc_static"

# <Severity> <RuleID> <path>:<line> <message>
_LINE_RE = re.compile(
    r"^(?P<sev>Error|Warning|Info)\s+"
    r"(?P<rule>\S+)\s+"
    r"(?P<path>[^\s:]+):(?P<line>\d+)\s+"
    r"(?P<msg>.+)$"
)

# Lines that are run decoration, not findings.
_SKIP_PREFIXES = ("==", "VC Static Version:", "Total:", "---")

_SEVERITY = {
    "Error": SeverityE.Error,
    "Warning": SeverityE.Warning,
    "Info": SeverityE.Info,
}


def parse(lines: Iterable[str], root: str = "") -> List[Finding]:
    """Parse VC Static lint output into findings.

    `root` relativizes in-project paths; paths outside it are left absolute.
    """
    findings: List[Finding] = []

    for line in lines:
        line = line.rstrip("\n")

        if any(line.startswith(p) for p in _SKIP_PREFIXES):
            continue

        m = _LINE_RE.match(line)
        if m is None:
            continue

        severity = _SEVERITY.get(m.group("sev"), SeverityE.Warning)
        path = relpath(m.group("path"), root)
        line_no = int(m.group("line"))

        findings.append(Finding(
            tool=TOOL_ID,
            tool_name=TOOL_NAME,
            rule=m.group("rule"),
            severity=severity,
            msg=m.group("msg").strip(),
            path=path,
            line=line_no,
            raw=line,
        ))

    return findings


def parse_file(path: str, root: str = "") -> List[Finding]:
    with open(path, "r", errors="replace") as fp:
        return parse(fp.read().splitlines(), root)
