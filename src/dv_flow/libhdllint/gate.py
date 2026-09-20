#****************************************************************************
#* gate.py
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
"""The pass/fail decision, made in one place.

Failure is an explicit policy (`fail_on:`), not a side effect of a finding's
severity. Someone adopting lint on existing code must be able to run it, see
error-severity findings, and still get a zero exit while they work through
them -- otherwise the first thing they do is turn the task off.

The gate only ever considers *new* findings. Waived and baselined findings
have already been accepted; counting them would make `fail_on:` a function of
history rather than of this change.
"""

import dataclasses as dc
from typing import List, Optional, Tuple

from dv_flow.mgr.task_data import SeverityE

from .finding import Finding, severity_atleast


FAIL_ON_VALUES = ("none", "error", "warning", "any")

_THRESHOLD = {
    "error": SeverityE.Error,
    "warning": SeverityE.Warning,
    "any": SeverityE.Info,
}


class GateError(Exception):
    """`fail_on:` was given a value that is not a policy."""


def gating_findings(findings : List[Finding], fail_on : str) -> List[Finding]:
    """The new findings that count against `fail_on`."""
    fail_on = str(fail_on or "error").strip().lower()
    if fail_on not in FAIL_ON_VALUES:
        raise GateError("Unknown fail_on value '%s'. Expected one of: %s."
                        % (fail_on, ", ".join(FAIL_ON_VALUES)))
    if fail_on == "none":
        return []
    threshold = _THRESHOLD[fail_on]
    return [f for f in findings
            if not f.suppressed and severity_atleast(f.severity, threshold)]


def evaluate(findings : List[Finding], fail_on : str) -> Tuple[int, int]:
    """`(status, n_gating)`. Status is 0 or 1, in the shell sense."""
    gating = gating_findings(findings, fail_on)
    return (1 if gating else 0), len(gating)


def headline(summary, fail_on : str) -> str:
    """The one line a reader should be able to act on.

    It always states the accepted counts, even on a pass. "0 new (137
    baselined, 4 waived)" is a passing run that still tells the truth about
    what is being ignored; a bare "lint passed" is not.
    """
    parts = []
    if summary.baselined:
        parts.append("%d baselined" % summary.baselined)
    if summary.waived:
        parts.append("%d waived" % summary.waived)
    if summary.duplicates:
        parts.append("%d duplicate%s" % (summary.duplicates,
                                         "" if summary.duplicates == 1 else "s"))
    accepted = (" (%s)" % ", ".join(parts)) if parts else ""

    sev = []
    if summary.errors:
        sev.append("%d error%s" % (summary.errors, "" if summary.errors == 1 else "s"))
    if summary.warnings:
        sev.append("%d warning%s" % (summary.warnings, "" if summary.warnings == 1 else "s"))
    if summary.infos:
        sev.append("%d info" % summary.infos)
    detail = (": %s" % ", ".join(sev)) if sev else ""

    return "lint: %d new finding%s%s%s [fail_on=%s]" % (
        summary.new, "" if summary.new == 1 else "s", detail, accepted, fail_on)
