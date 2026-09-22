#****************************************************************************
#* waiver.py
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
"""Waivers: one format, two ways of enforcing it.

This module defines the format and the matching semantics. It is the single
source of truth -- a project writes one waiver file and it applies to every
backend, including commercial ones that cannot be run in CI.

There are two enforcement paths, selected by `waiver_mode:`:

* **post-filter** (the default) -- every tool runs every check, and waivers
  are matched against the normalized `Finding` records afterwards. One matching
  semantics to learn and to test, uniform across backends, and exact
  accounting: waived findings are counted, and a waiver that matches nothing
  is reported as stale. What it costs is that the tool still spends the time,
  and its own log still contains the finding.

* **native lowering** (`waiver_mode: native`) -- each backend additionally
  translates the waivers it can express into its own suppression syntax
  (`<tool>_waivers.py`; see `vlt_waivers.py` for the Verilator `.vlt` form).
  The tool then never runs the check, which is the point for a tool whose
  noise or runtime makes its raw run unusable. What it costs is accounting: a
  natively suppressed finding is never emitted, so it cannot be counted or
  checked for staleness -- which the run states explicitly rather than
  reporting a misleading `waived: 0`.

The rule that keeps these from becoming two sources of truth: **lowering is
always partial and the remainder is post-filtered.** A backend's lowerer
returns the waivers it took responsibility for, and everything it could not
express exactly is still applied here. Switching modes therefore changes how
much work the tool does and how precise the accounting is -- never whether a
waiver is in force.

A waiver without a `reason` is a load error. The reason is the only part of a
waiver that is still useful in two years.
"""

import dataclasses as dc
import fnmatch
import logging
import os
from typing import Any, Dict, List, Optional

from .finding import Finding

_log = logging.getLogger("hdllint.waiver")


class WaiverError(Exception):
    """A waiver file could not be loaded. Raised rather than reported and
    skipped: silently ignoring a malformed waiver file means running with
    suppression the author believes is in effect and is not."""


@dc.dataclass
class Waiver(object):
    """One waiver rule.

    Every field except `reason` is optional and defaults to "matches
    anything". `rule: "*"` with no `path` therefore waives everything, which
    is occasionally what someone wants and should be written explicitly rather
    than arrived at by accident -- so `apply()` reports how many findings each
    waiver matched, and a waiver that matched none is flagged.
    """
    reason : str
    rule   : str = "*"
    tool   : str = ""
    path   : str = ""
    line   : int = -1
    src    : str = ""     # file (and index) this came from, for diagnostics
    hits   : int = 0

    def matches(self, f : Finding) -> bool:
        if self.tool and self.tool not in (f.tool, f.tool_name):
            return False
        if self.line >= 0 and self.line != f.line:
            return False
        if self.rule and self.rule != "*":
            if not fnmatch.fnmatch(f.rule or "", self.rule):
                return False
        if self.path:
            if not _path_matches(f.path, self.path):
                return False
        return True


def _path_matches(path : str, pattern : str) -> bool:
    """Glob a finding's path.

    Patterns are fnmatch-style, and `*` crosses directory separators -- so
    `*.v` matches `rtl/verilog/wb_dma.v`, and `**/foo.v` and `*/foo.v` behave
    identically. This is looser than a shell glob and is documented as such;
    the alternative (pathlib-style `**` semantics) makes the common case
    (`rtl/**`) silently fail to match `rtl/a/b.v` for anyone who writes
    `rtl/*`.

    The basename is also tried, so `wb_dma_defines.v` works as a pattern
    without the reader having to know where the file sits.
    """
    if not path:
        return False
    p = path.replace(os.sep, "/")
    pat = pattern.replace(os.sep, "/")
    return (fnmatch.fnmatch(p, pat)
            or fnmatch.fnmatch(os.path.basename(p), pat))


def _mk_waiver(entry : Dict[str, Any], src : str, idx : int) -> Waiver:
    if not isinstance(entry, dict):
        raise WaiverError("%s: waiver #%d is %s, expected a mapping"
                          % (src, idx, type(entry).__name__))

    known = {"rule", "tool", "path", "line", "reason"}
    unknown = sorted(set(entry.keys()) - known)
    if unknown:
        raise WaiverError("%s: waiver #%d has unknown field(s) %s; known fields are %s"
                          % (src, idx, ", ".join(unknown), ", ".join(sorted(known))))

    reason = str(entry.get("reason", "") or "").strip()
    if not reason:
        raise WaiverError(
            "%s: waiver #%d has no 'reason'. Every waiver must say why the "
            "finding is acceptable -- that is the only part of it still "
            "useful once the author has moved on." % (src, idx))

    line = entry.get("line", -1)
    try:
        line = int(line)
    except (TypeError, ValueError):
        raise WaiverError("%s: waiver #%d has a non-integer 'line': %r"
                          % (src, idx, entry.get("line")))

    return Waiver(
        reason=reason,
        rule=str(entry.get("rule", "*") or "*"),
        tool=str(entry.get("tool", "") or ""),
        path=str(entry.get("path", "") or ""),
        line=line,
        src="%s#%d" % (src, idx))


def load_waivers(entries : List[Any], src : str) -> List[Waiver]:
    """Build waivers from a list of mappings (an inline `waivers:` list)."""
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise WaiverError("%s: 'waivers' must be a list, got %s"
                          % (src, type(entries).__name__))
    return [_mk_waiver(e, src, i) for i, e in enumerate(entries)]


def load_waiver_file(path : str) -> List[Waiver]:
    """Load `waivers:` from a YAML file.

    A bare list at the top level is accepted too -- it is what people write
    the first time, and rejecting it teaches nothing.
    """
    import yaml

    if not os.path.isfile(path):
        raise WaiverError("Waiver file not found: %s" % path)

    with open(path, "r") as fp:
        try:
            doc = yaml.safe_load(fp)
        except yaml.YAMLError as e:
            raise WaiverError("%s: %s" % (path, e))

    if doc is None:
        return []
    if isinstance(doc, list):
        entries = doc
    elif isinstance(doc, dict):
        if "waivers" not in doc:
            raise WaiverError("%s: no 'waivers' key" % path)
        entries = doc["waivers"] or []
    else:
        raise WaiverError("%s: expected a mapping with a 'waivers' key, got %s"
                          % (path, type(doc).__name__))

    return load_waivers(entries, path)


def apply_waivers(findings : List[Finding], waivers : List[Waiver]) -> int:
    """Mark every finding matched by a waiver, and count the hits.

    First match wins, so the reason recorded on a finding is the one the
    reader will most likely have written for it. Returns the number of
    findings waived.
    """
    n = 0
    for f in findings:
        for w in waivers:
            if w.matches(f):
                w.hits += 1
                f.waived = w.reason
                n += 1
                break
    return n


def unused_waivers(waivers : List[Waiver]) -> List[Waiver]:
    """Waivers that matched nothing.

    Reported as a warning rather than ignored: a stale waiver is a statement
    about the codebase that is no longer true, and it hides the fact that the
    finding it was written for has either been fixed (delete it) or moved
    (fix it).
    """
    return [w for w in waivers if w.hits == 0]
