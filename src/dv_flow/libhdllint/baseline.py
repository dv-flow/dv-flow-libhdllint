#****************************************************************************
#* baseline.py
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
"""The accepted baseline: today's findings, so tomorrow's are visible.

This is the feature that decides whether lint gets adopted on an existing
codebase or gets switched off in week two. Turning a lint tool on over code
that predates it produces hundreds of findings at once. The available
responses are: waive them all by hand (nobody does), run at a severity low
enough to be quiet (which is the same as not running it), or accept the
current state and fail only on what is added. Only the third is real.

Two design points carry the whole feature:

* **The key ignores line numbers.** A baseline keyed on `(file, line)` is
  invalidated by any edit above a finding, so within a day every entry has
  drifted and the baseline reports the entire file as new. The key is
  `(tool, rule, file, message-shape)` -- see `Finding.key`.
* **Matching is count-aware.** Three baselined `WIDTHTRUNC` in a file and
  five today means two new findings, not zero. A set membership test would
  hide the two.
"""

import dataclasses as dc
import json
import logging
import os
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from .finding import Finding

_log = logging.getLogger("hdllint.baseline")

BASELINE_VERSION = 1


class BaselineError(Exception):
    """The baseline file exists but could not be read. Raised rather than
    treated as an empty baseline: an unreadable baseline silently becomes
    "every finding is new", which fails a CI job for the wrong reason."""


@dc.dataclass
class Baseline(object):
    counts  : Counter = dc.field(default_factory=Counter)
    entries : List[Dict[str, Any]] = dc.field(default_factory=list)
    path    : str = ""
    present : bool = False

    def __len__(self):
        return sum(self.counts.values())


def load_baseline(path : str) -> Baseline:
    """Read a baseline file. A missing file is an empty baseline, not an error
    -- that is the first run, before one has been established."""
    if not path or not os.path.isfile(path):
        return Baseline(path=path, present=False)

    try:
        with open(path, "r") as fp:
            doc = json.load(fp)
    except (OSError, ValueError) as e:
        raise BaselineError("Failed to read baseline '%s': %s" % (path, e))

    if not isinstance(doc, dict) or "entries" not in doc:
        raise BaselineError(
            "Baseline '%s' is not a baseline file (no 'entries')." % path)

    version = doc.get("version", 0)
    if version != BASELINE_VERSION:
        raise BaselineError(
            "Baseline '%s' has version %s; this library writes version %d. "
            "Regenerate it with `-D <task>.update_baseline=true`."
            % (path, version, BASELINE_VERSION))

    counts = Counter()
    entries = doc.get("entries") or []
    for e in entries:
        counts[e.get("key", "")] += int(e.get("count", 1))

    return Baseline(counts=counts, entries=entries, path=path, present=True)


def apply_baseline(findings : List[Finding],
                   baseline : Baseline) -> Tuple[int, List[Dict[str, Any]]]:
    """Mark findings covered by the baseline; report what the baseline no
    longer covers.

    Returns `(n_baselined, stale)`, where `stale` lists baseline entries whose
    findings no longer occur -- either fixed, or moved out from under their
    key. Reporting the count is what lets a team watch the baseline shrink,
    which is the only thing that makes it a transition rather than a
    permanent amnesty.

    Waived findings are skipped: a finding cannot be both, and the waiver --
    which carries a human-written reason -- is the more informative of the
    two.
    """
    if not baseline.present:
        return 0, []

    remaining = Counter(baseline.counts)
    n = 0
    for f in findings:
        if f.waived is not None:
            continue
        k = f.key()
        if remaining.get(k, 0) > 0:
            remaining[k] -= 1
            f.baseline = True
            n += 1

    by_key = {e.get("key", ""): e for e in baseline.entries}
    stale = []
    for k, left in remaining.items():
        if left > 0:
            e = dict(by_key.get(k, {"key": k}))
            e["count"] = left
            stale.append(e)

    return n, stale


def baseline_doc(findings : List[Finding], tools : List[str]) -> Dict[str, Any]:
    """The baseline document for the given findings.

    Waived findings are excluded -- they are already suppressed by a reason,
    and carrying them here would mean deleting a waiver silently re-suppresses
    the finding via the baseline.

    `msg` and `path` are stored alongside the key purely so the file is
    reviewable in a pull request. Nothing reads them back.
    """
    counts = Counter()
    sample = {}
    for f in findings:
        if f.waived is not None:
            continue
        k = f.key()
        counts[k] += 1
        sample.setdefault(k, f)

    entries = []
    for k in sorted(counts.keys()):
        f = sample[k]
        entries.append({
            "key": k,
            "count": counts[k],
            "tool": f.tool,
            "rule": f.rule,
            "path": f.path,
            "severity": f.severity.value,
            "msg": f.msg,
        })

    return {
        "version": BASELINE_VERSION,
        "tools": sorted(tools),
        "total": sum(counts.values()),
        "entries": entries,
    }


def write_baseline(path : str, findings : List[Finding],
                   tools : List[str]) -> Dict[str, Any]:
    """Write the baseline file and return the document written."""
    doc = baseline_doc(findings, tools)
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    with open(path, "w") as fp:
        json.dump(doc, fp, indent=2, sort_keys=False)
        fp.write("\n")
    return doc
