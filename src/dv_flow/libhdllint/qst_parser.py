#****************************************************************************
#* qst_parser.py
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
"""Questa Lint (AutoCheck) output -> `Finding`s.

This is a separate, pure module on purpose: it takes text and returns
findings, so the whole parser is testable against synthetic tool output
with no Questa installed.

The format is the AutoCheck text report produced by `qverify`:

    ** Warning: (LINT_LATCH) dummy_rtl/alu.v(44): Latch inferred for signal 'q'
    ** Error: (LINT_SYNTH) dummy_rtl/mux.v(12): Synthesis issue detected
    ** Note: (LINT_WIDTH) dummy_rtl/fifo.v(8): Width mismatch in assignment

Each finding is a single line starting with ``** <Severity>:``.
``Note`` maps to ``Info`` severity.

Lines that are run chatter rather than findings -- ``# Loading``,
``# Compiling``, ``# ** Report``, ``# Total:``, separator dashes -- are
skipped.
"""

import re
from typing import Iterable, List

from .finding import Finding, relpath, severity_from_str

TOOL_ID = "qst"
TOOL_NAME = "questa_lint"

# ** <Severity>: (<RuleID>) <rest>
_HEAD_RE = re.compile(
    r"^\*\*\s+(?P<sev>Error|Warning|Note):\s*"
    r"\((?P<rule>[^)]+)\)\s*(?P<rest>.*)$"
)

# <path>(<line>): <message>
_LOC_RE = re.compile(
    r"^(?P<path>[^\s(].*?)\((?P<line>\d+)\):\s*(?P<msg>.*)$"
)

# Lines to skip outright.
_SKIP_RE = re.compile(
    r"^(#\s*Loading|#\s*Compiling|#\s*\*\*\s*Report|#\s*Total:|----)"
)


def parse(lines: Iterable[str], root: str = "") -> List[Finding]:
    """Parse Questa Lint AutoCheck output into findings.

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
