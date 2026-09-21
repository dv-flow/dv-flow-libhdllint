#****************************************************************************
#* spy_parser.py
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
"""SpyGlass message output -> `Finding`s.

This is a separate, pure module on purpose: it takes text and returns
findings, so the whole parser is testable against synthetic message data with
no SpyGlass installed. Every backend follows the same split.

The format, as observed from SpyGlass text reports:

    Warning W_REDF dummy_rtl/mux.v:12 Redundant else branch in always block
    Error   SYNTH_5130 dummy_rtl/alu.v:44 Latch inferred for signal 'q'
    Info    STARC05-1.3.1.3 dummy_rtl/fifo.v:8 Width mismatch in port connection

Each message line starts with a severity keyword, then a rule id, then
optionally a `path:line` location, then the message text.

Lines that do not match this shape -- the SpyGlass banner, goal headers,
summary tallies, separator rules -- are continuation or run chatter and are
attached to the preceding finding (or discarded if there is no preceding
finding).

SpyGlass is the property of its respective owners.
"""

import re
from typing import Iterable, List, Optional

from dv_flow.mgr.task_data import SeverityE

from .finding import Finding, relpath

TOOL_ID = "spy"
TOOL_NAME = "spyglass"

# <Severity> <RuleID> [<path>:<line>] <message>
# Severity is Error, Warning, or Info. There may be extra whitespace between
# fields (SpyGlass aligns columns).
_MSG_RE = re.compile(
    r"^(?P<sev>Error|Warning|Info)\s+"
    r"(?P<rule>\S+)\s+"
    r"(?:(?P<path>[^\s:]+):(?P<line>\d+)\s+)?"
    r"(?P<msg>.+)$"
)

# Lines that are part of the SpyGlass run banner, goal summaries, or
# separator decoration. These never carry a finding.
_SKIP_RE = re.compile(
    r"^\s*(?:"
    r"SpyGlass\s+Version[:\s]"
    r"|Running\s+goal[:\s]"
    r"|Total[:\s]"
    r"|[-=]{4,}"
    r")",
    re.IGNORECASE,
)

_SEVERITY = {
    "Error": SeverityE.Error,
    "Warning": SeverityE.Warning,
    "Info": SeverityE.Info,
}


def parse(lines: Iterable[str], root: str = "") -> List[Finding]:
    """Parse SpyGlass lint output into findings.

    `root` relativizes in-project paths; paths outside it are left absolute.
    """
    findings: List[Finding] = []
    current: Optional[Finding] = None

    for line in lines:
        line = line.rstrip("\n")

        # Skip known non-message lines before attempting the message regex.
        if _SKIP_RE.match(line):
            current = None
            continue

        m = _MSG_RE.match(line)

        if m is None:
            # Continuation of the preceding finding, or run chatter.
            if current is not None and line.strip():
                current.raw += "\n" + line
            continue

        sev_str = m.group("sev")
        rule = m.group("rule")
        severity = _SEVERITY.get(sev_str, SeverityE.Warning)

        path = ""
        line_no = -1
        msg = m.group("msg").strip()

        if m.group("path") is not None:
            path = relpath(m.group("path"), root)
            line_no = int(m.group("line"))

        current = Finding(
            tool=TOOL_ID,
            tool_name=TOOL_NAME,
            rule=rule,
            severity=severity,
            msg=msg,
            path=path,
            line=line_no,
            pos=-1,
            raw=line,
        )
        findings.append(current)

    return findings


def parse_file(path: str, root: str = "") -> List[Finding]:
    with open(path, "r", errors="replace") as fp:
        return parse(fp.read().splitlines(), root)
