#****************************************************************************
#* finding.py
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
"""The normalized lint finding -- the one record every backend produces.

A backend parser's entire job is to turn its tool's output into `Finding`s.
Everything downstream (waivers, baseline, dedup, markers, lint.json, SARIF,
CTRF, the gate) is written against this record and knows nothing about any
particular tool.

Two things are deliberately NOT in the record:

* a "message id" of our own. `rule` is the *tool-native* id, verbatim
  (`WIDTHTRUNC`, `line-length`), because that is the string the user has to
  type to waive it and the string that appears in the tool's own
  documentation. Inventing a portable id on top would mean maintaining a
  translation table that is wrong the day a tool adds a rule.
* a pass/fail opinion. `severity` is the tool's severity, normalized to the
  three `SeverityE` levels. Whether a run fails is the gate's decision
  (`fail_on:`), made once, over all findings -- see gate.py.
"""

import dataclasses as dc
import os
import re
from typing import Any, Dict, List, Optional

from dv_flow.mgr.task_data import TaskMarker, TaskMarkerLoc, SeverityE


# Severity as an ordered scale, so "at least this severe" is expressible.
_SEV_ORDER = {
    SeverityE.Info: 0,
    SeverityE.Warning: 1,
    SeverityE.Error: 2,
}

_SEV_BY_NAME = {
    "info": SeverityE.Info,
    "note": SeverityE.Info,
    "warning": SeverityE.Warning,
    "warn": SeverityE.Warning,
    "error": SeverityE.Error,
    "fatal": SeverityE.Error,
}


def severity_from_str(s : str, default=SeverityE.Warning) -> SeverityE:
    """Parse a severity name. Unknown names fall back to `default` rather than
    raising: a tool that invents a new severity level should still get its
    findings reported, just conservatively classified."""
    return _SEV_BY_NAME.get(str(s or "").strip().lower(), default)


def severity_str(sev : SeverityE) -> str:
    return sev.value if isinstance(sev, SeverityE) else str(sev)


def severity_atleast(sev : SeverityE, threshold : SeverityE) -> bool:
    return _SEV_ORDER.get(sev, 0) >= _SEV_ORDER.get(threshold, 0)


# Numbers are the part of a lint message that moves without the finding
# changing: bit widths that shifted by one, an instance index, a line number
# quoted inside the text. Stripping them is what makes a baseline survive an
# ordinary edit -- see baseline.py.
_NUM_RE = re.compile(r"\d+")


def normalize_msg(msg : str) -> str:
    """A message reduced to its shape, for baseline and dedup keys."""
    return _NUM_RE.sub("#", str(msg or "")).strip()


def relpath(path : str, root : str) -> str:
    """`path` relative to `root` when it is underneath it, else unchanged.

    Reports are read on a different machine than they were produced on (CI
    annotations, a reviewer's checkout), so a path inside the project is
    always stored relative to the project root. A path outside it -- a tool's
    own header, an IP block from elsewhere -- stays absolute, because a
    `../../..` chain is not more portable, only less readable.
    """
    if not path:
        return ""
    if not root:
        return path
    try:
        ap = os.path.abspath(path)
        ar = os.path.abspath(root)
        if ap == ar or ap.startswith(ar + os.sep):
            return os.path.relpath(ap, ar).replace(os.sep, "/")
    except (ValueError, OSError):
        pass
    return path.replace(os.sep, "/")


@dc.dataclass
class Finding(object):
    """One lint finding, from one tool, normalized.

    `tool` is the backend id as it appears in `tools:` (`vlt`), and `tool_name`
    the tool's own name (`verilator`) as it should appear in a report. Keeping
    both means `lint.json` reads naturally and a waiver can be written against
    either.
    """
    tool      : str = ""
    tool_name : str = ""
    rule      : str = ""
    severity  : SeverityE = SeverityE.Warning
    msg       : str = ""
    path      : str = ""
    line      : int = -1
    pos       : int = -1

    # Set by the post-filters, not by parsers.
    waived    : Optional[str] = None   # the waiver's reason, when suppressed
    baseline  : bool = False           # present in the accepted baseline
    dup_of    : Optional[str] = None   # the tool that reported this first

    raw       : str = ""               # the tool's own text, for parser debugging

    @property
    def suppressed(self) -> bool:
        """True when this finding must not become a marker and must not fail
        the gate. Note `dup_of` is NOT suppression -- a duplicate is dropped
        from the merged list entirely (and recorded), rather than carried as a
        suppressed entry."""
        return self.waived is not None or self.baseline

    @property
    def label(self) -> str:
        """`tool:rule`, or just the tool when the finding has no rule id.

        Some messages genuinely have no id -- a Verilator syntax error is
        `%Error:` with nothing after the dash. Those are reported as
        `[verilator]`, and are waivable by path rather than by rule.
        """
        return "%s:%s" % (self.tool_name or self.tool, self.rule) if self.rule \
            else (self.tool_name or self.tool)

    @property
    def location(self) -> str:
        if not self.path:
            return ""
        if self.line < 0:
            return self.path
        if self.pos < 0:
            return "%s:%d" % (self.path, self.line)
        return "%s:%d:%d" % (self.path, self.line, self.pos)

    def marker(self) -> TaskMarker:
        """This finding as a dv-flow marker.

        `TaskMarker` has no field for a rule id, so it goes in the message as
        a `[tool:rule]` prefix. That matches what libhdlsim's log parser
        already does with simulator message codes, and it doubles as telling
        the reader the exact string they need in order to waive the finding.
        """
        msg = "[%s] %s" % (self.label, self.msg)
        if self.path:
            return TaskMarker(
                msg=msg,
                severity=self.severity,
                loc=TaskMarkerLoc(path=self.path, line=self.line, pos=self.pos))
        return TaskMarker(msg=msg, severity=self.severity)

    def key(self) -> str:
        """Baseline identity: tool, rule, file, and the message *shape*.

        The line number is deliberately absent. A baseline keyed on line
        numbers is invalidated by any edit above a finding, which makes it
        useless within a day of being adopted.
        """
        return "|".join((self.tool, self.rule, self.path, normalize_msg(self.msg)))

    def dedup_key(self):
        """Cross-tool identity: the same defect as seen by two tools.

        The tool is not part of the key -- that is the entire point. Two tools
        reporting the same width truncation at the same place is one finding.
        """
        return (self.path, self.line, normalize_msg(self.msg))

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "tool": self.tool,
            "tool_name": self.tool_name,
            "rule": self.rule,
            "severity": severity_str(self.severity),
            "msg": self.msg,
            "path": self.path,
            "line": self.line,
            "pos": self.pos,
        }
        if self.waived is not None:
            d["waived"] = self.waived
        if self.baseline:
            d["baseline"] = True
        if self.dup_of is not None:
            d["dup_of"] = self.dup_of
        if self.raw:
            d["raw"] = self.raw
        return d

    @staticmethod
    def from_dict(d : Dict[str, Any]) -> 'Finding':
        return Finding(
            tool=d.get("tool", ""),
            tool_name=d.get("tool_name", ""),
            rule=d.get("rule", ""),
            severity=severity_from_str(d.get("severity", "warning")),
            msg=d.get("msg", ""),
            path=d.get("path", ""),
            line=int(d.get("line", -1)),
            pos=int(d.get("pos", -1)),
            waived=d.get("waived", None),
            baseline=bool(d.get("baseline", False)),
            dup_of=d.get("dup_of", None),
            raw=d.get("raw", ""))


def sort_findings(findings : List[Finding]) -> List[Finding]:
    """Stable report order: file, then line, then column, then tool, then rule.

    A report whose order depends on which tool finished first is a report that
    produces a spurious diff on every run.
    """
    return sorted(findings, key=lambda f: (
        f.path or "", f.line if f.line >= 0 else 1 << 30,
        f.pos if f.pos >= 0 else 1 << 30, f.tool or "", f.rule or "", f.msg or ""))
