#****************************************************************************
#* vlt_parser.py
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
"""Verilator lint output -> `Finding`s.

This is a separate, pure module on purpose: it takes text and returns
findings, so the whole parser is testable against recorded tool output with no
Verilator installed. Every backend follows the same split, and the recorded
fixtures in `tests/unit/data/` carry the tool version in their filename --
Verilator's message wording and rule set both move between releases, and a
fixture nobody can attribute to a version is a fixture nobody can refresh.

This deliberately does NOT reuse `dv_flow.libhdlsim.log_parser`, which handles
the same `%Warning-CODE:` shape. That parser's product is a marker -- a
string, with the code folded into the message -- and this one's product is a
record with the rule as a field. The two will keep diverging (waivers need the
rule; a build log does not), and sharing across package boundaries would tie
each library's release to the other's.

The format, as of Verilator 5.x:

    %Warning-WIDTHTRUNC: path/file.v:4:9: Operator ASSIGNDLY expects 4 bits...
                                : ... note: In instance 'w'
        4 |       y <= a;
          |         ^~
                         ... For warning description see https://...
    %Error: path/file.v:1:21: syntax error, unexpected ';', expecting ')'
    %Error: Specified --top-module 'nope' was not found in design.
    %Error: Exiting due to 1 error(s)

Three shapes, and the last two matter:

* `%Error:` with no `-CODE` -- syntax errors and driver-level complaints.
  They get an empty `rule`, because inventing one would mean inventing an id
  that appears in no Verilator document.
* `%Error: Exiting due to N error(s)` is a tally, not a finding. Reporting it
  would add one phantom error to every failing run.
* Everything not starting with `%` is continuation (the source echo, the
  caret, the "For warning description see..." footer) and is attached to the
  preceding finding's `raw`.
"""

import re
from typing import Iterable, List, Optional

from dv_flow.mgr.task_data import SeverityE

from .finding import Finding, relpath

TOOL_ID = "vlt"
TOOL_NAME = "verilator"

# %<Kind>[-<CODE>]: <rest>
_HEAD_RE = re.compile(r"^%(?P<kind>Error|Warning)(?:-(?P<rule>[A-Za-z0-9_]+))?:\s*(?P<rest>.*)$")

# <path>:<line>:<col>: <msg>   /   <path>:<line>: <msg>
_LOC_RE = re.compile(r"^(?P<path>[^\s].*?):(?P<line>\d+)(?::(?P<pos>\d+))?:\s*(?P<msg>.*)$")

# Run tallies, not findings.
_TALLY_RE = re.compile(r"^Exiting due to \d+ (error|warning)")

_SEVERITY = {"Error": SeverityE.Error, "Warning": SeverityE.Warning}


def parse(lines : Iterable[str], root : str = "") -> List[Finding]:
    """Parse Verilator lint output into findings.

    `root` relativizes in-project paths; paths outside it are left absolute.
    """
    findings : List[Finding] = []
    current : Optional[Finding] = None

    for line in lines:
        line = line.rstrip("\n")
        m = _HEAD_RE.match(line)

        if m is None:
            # Continuation of the finding above, or run chatter before the
            # first one. Keep it with the finding so a surprising result can
            # be traced back to what Verilator actually printed.
            if current is not None and line.strip():
                current.raw += "\n" + line
            continue

        rest = m.group("rest").strip()

        if _TALLY_RE.match(rest):
            current = None
            continue

        kind = m.group("kind")
        rule = m.group("rule") or ""
        severity = _SEVERITY.get(kind, SeverityE.Warning)

        path, line_no, pos, msg = "", -1, -1, rest
        loc = _LOC_RE.match(rest)
        if loc is not None:
            path = relpath(loc.group("path"), root)
            line_no = int(loc.group("line"))
            pos = int(loc.group("pos")) if loc.group("pos") else -1
            msg = loc.group("msg").strip()

        current = Finding(
            tool=TOOL_ID,
            tool_name=TOOL_NAME,
            rule=rule,
            severity=severity,
            msg=msg,
            path=path,
            line=line_no,
            pos=pos,
            raw=line)
        findings.append(current)

    return findings


def parse_file(path : str, root : str = "") -> List[Finding]:
    with open(path, "r", errors="replace") as fp:
        return parse(fp.read().splitlines(), root)
