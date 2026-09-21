#****************************************************************************
#* jg_parser.py
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
"""JasperGold superlint output -> `Finding`s.

This is a separate, pure module on purpose: it takes text and returns
findings, so the whole parser is testable against synthetic tool output
with no JasperGold installed.

JasperGold superlint reports come in two shapes:

CSV format (the default report file):

    Warning,SUPERLINT_LATCH,dummy_rtl/alu.v,44,Latch inferred for signal 'q'
    Error,SUPERLINT_WIDTH,dummy_rtl/mux.v,12,Width mismatch in port connection
    Info,SUPERLINT_UNUSED,dummy_rtl/fifo.v,8,Signal 'tmp' is unused

Text format (console/log output):

    [Warning] SUPERLINT_LATCH: dummy_rtl/alu.v:44: Latch inferred for signal 'q'
    [Error] SUPERLINT_WIDTH: dummy_rtl/mux.v:12: Width mismatch in port connection

Both shapes are accepted so a single parser handles whichever mode
produced the log. Header lines (``severity,rule,...``), separator dashes,
and empty lines are skipped.
"""

import re
from typing import Iterable, List

from .finding import Finding, relpath, severity_from_str

TOOL_ID = "jg"
TOOL_NAME = "jaspergold"

# CSV: <severity>,<rule>,<path>,<line>,<message>
_CSV_RE = re.compile(
    r"^(?P<sev>Error|Warning|Info),"
    r"(?P<rule>[^,]+),"
    r"(?P<path>[^,]+),"
    r"(?P<line>\d+),"
    r"(?P<msg>.+)$"
)

# Text: [<severity>] <rule>: <path>:<line>: <message>
_TEXT_RE = re.compile(
    r"^\[(?P<sev>Error|Warning|Info)\]\s+"
    r"(?P<rule>[^:]+?):\s+"
    r"(?P<path>[^\s:][^:]*):(?P<line>\d+):\s+"
    r"(?P<msg>.+)$"
)

# Header / noise lines.
_SKIP_RE = re.compile(r"^(severity,|---)")


def parse(lines: Iterable[str], root: str = "") -> List[Finding]:
    """Parse JasperGold superlint output into findings.

    `root` relativizes in-project paths; paths outside it are left absolute.
    """
    findings: List[Finding] = []

    for line in lines:
        line = line.rstrip("\n")

        if not line.strip():
            continue
        if _SKIP_RE.match(line):
            continue

        m = _CSV_RE.match(line)
        if m is None:
            m = _TEXT_RE.match(line)
        if m is None:
            continue

        sev = severity_from_str(m.group("sev"))
        rule = m.group("rule").strip()
        path = relpath(m.group("path").strip(), root)
        line_no = int(m.group("line"))
        msg = m.group("msg").strip()

        findings.append(Finding(
            tool=TOOL_ID,
            tool_name=TOOL_NAME,
            rule=rule,
            severity=sev,
            msg=msg,
            path=path,
            line=line_no,
            pos=-1,
            raw=line,
        ))

    return findings


def parse_file(path: str, root: str = "") -> List[Finding]:
    with open(path, "r", errors="replace") as fp:
        return parse(fp.read().splitlines(), root)
