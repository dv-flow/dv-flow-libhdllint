#****************************************************************************
#* z0i_parser.py
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
"""0-in lint output -> `Finding`s.

This is a separate, pure module on purpose: it takes text and returns
findings, so the whole parser is testable against synthetic tool output
with no 0-in installed.

The format is the 0-in text report:

    Warning: [ZIN_LATCH] dummy_rtl/alu.v:44: Latch inferred for signal 'q'
    Error: [ZIN_WIDTH] dummy_rtl/mux.v:12: Width mismatch detected
    Info: [ZIN_UNUSED] dummy_rtl/fifo.v:8: Signal 'tmp' is never read

Each finding is a single line: ``<Severity>: [<Rule>] <path>:<line>: <msg>``.
Lines without a location are also accepted (the path and line are left
empty / -1).

Lines that are run chatter -- ``0-in Version:``, ``Loading:``,
``Total:``, separator dashes -- are skipped.
"""

import re
from typing import Iterable, List

from .finding import Finding, relpath, severity_from_str

TOOL_ID = "z0i"
TOOL_NAME = "0-in"

# <Severity>: [<Rule>] <rest>
_HEAD_RE = re.compile(
    r"^(?P<sev>Error|Warning|Info):\s*"
    r"\[(?P<rule>[^\]]+)\]\s*(?P<rest>.*)$"
)

# <path>:<line>: <message>
_LOC_RE = re.compile(
    r"^(?P<path>[^\s:][^:]*):(?P<line>\d+):\s*(?P<msg>.*)$"
)

# Lines to skip outright.
_SKIP_RE = re.compile(
    r"^(0-in Version:|Loading:|Total:|----)"
)


def parse(lines: Iterable[str], root: str = "") -> List[Finding]:
    """Parse 0-in lint output into findings.

    `root` relativizes in-project paths; paths outside it are left absolute.
    """
    findings: List[Finding] = []

    for line in lines:
        line = line.rstrip("\n")

        if not line.strip():
            continue
        if _SKIP_RE.match(line):
            continue

        m = _HEAD_RE.match(line)
        if m is None:
            continue

        sev = severity_from_str(m.group("sev"))
        rule = m.group("rule")
        rest = m.group("rest").strip()

        path, line_no, msg = "", -1, rest
        loc = _LOC_RE.match(rest)
        if loc is not None:
            path = relpath(loc.group("path"), root)
            line_no = int(loc.group("line"))
            msg = loc.group("msg").strip()

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
