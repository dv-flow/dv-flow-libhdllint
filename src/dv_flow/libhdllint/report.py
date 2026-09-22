#****************************************************************************
#* report.py
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
"""Merging findings, and writing the three report files.

One normalized finding list, three renderings, each for a different reader:

* **`lint.json`** -- the authoritative record, and the only one that contains
  everything: waived and baselined findings with their reasons, the
  duplicates that dedup dropped, and what each tool actually ran. It is what
  the baseline updater and any future triage step read.
* **`lint.sarif`** -- SARIF 2.1.0, for GitHub code scanning and for IDE
  problem lists. This is the piece no EDA vendor ships: it gets every
  backend, commercial ones included, into a code-review annotation with no
  per-tool integration. Suppressed findings are emitted *with* a SARIF
  `suppressions` entry rather than dropped, because that is how the format
  says "known and accepted" -- and it means the waiver reasons are visible in
  the same place as the findings.
* **`lint-ctrf.json`** -- CTRF, for the CI test-report UI. dv-flow's own CI
  already publishes CTRF via `ctrf-io/github-test-reporter`, so lint results
  land in the same summary as the test results with no extra wiring.

The CTRF mapping is stated once, here, because it is the one that involves a
judgement call: each finding is a "test". A finding that counts against the
gate is `failed`; one that is waived or baselined is `skipped` (CTRF's bucket
for "deliberately not run/enforced", and the closest honest fit); a new
finding below the gate threshold is `other`. A tool that ran and produced
nothing that fails contributes one `passed` entry, so a clean run is visibly
a *run* rather than an empty report.
"""

import dataclasses as dc
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from dv_flow.mgr.task_data import SeverityE

from .finding import Finding, normalize_msg, severity_str, sort_findings

REPORT_VERSION = 1

# SARIF severity levels. SARIF has no "info"; "note" is its equivalent.
_SARIF_LEVEL = {
    SeverityE.Error: "error",
    SeverityE.Warning: "warning",
    SeverityE.Info: "note",
}

_TOOL_URI = {
    "vlt": "https://verilator.org",
    "vbl": "https://github.com/chipsalliance/verible",
    "slang": "https://sv-lang.com",
    "svlint": "https://github.com/dalance/svlint",
}
_TOOL_URI["spy"] = "https://www.synopsys.com/verification/static-and-formal-verification/spyglass.html"
_TOOL_URI["z0i"] = "https://www.synopsys.com/verification/static-and-formal-verification.html"
_TOOL_URI["vcs"] = "https://www.synopsys.com/verification/static-and-formal-verification.html"
_TOOL_URI["qst"] = "https://eda.sw.siemens.com/en-US/ic/questa/formal-verification/"
_TOOL_URI["jg"] = "https://www.cadence.com/en_US/home/tools/system-design-and-verification/formal-and-static-verification/jasper-gold-verification-platform.html"


@dc.dataclass
class Summary(object):
    """The counts every rendering agrees on."""
    total      : int = 0   # findings after dedup, including suppressed
    new        : int = 0   # neither waived nor baselined
    waived     : int = 0
    baselined  : int = 0
    duplicates : int = 0   # dropped by cross-tool dedup
    errors     : int = 0   # severity counts, over NEW findings only
    warnings   : int = 0
    infos      : int = 0
    gating     : int = 0   # new findings that count against fail_on
    tools      : List[str] = dc.field(default_factory=list)
    skipped    : List[str] = dc.field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.gating == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "new": self.new,
            "waived": self.waived,
            "baselined": self.baselined,
            "duplicates": self.duplicates,
            "errors": self.errors,
            "warnings": self.warnings,
            "infos": self.infos,
            "gating": self.gating,
            "passed": self.passed,
            "tools": list(self.tools),
            "skipped": list(self.skipped),
        }


def dedup(findings : List[Finding],
          enabled : bool = True) -> Tuple[List[Finding], List[Finding]]:
    """Collapse the same finding reported by more than one tool.

    Returns `(kept, dropped)`. The dropped findings are returned rather than
    discarded so `lint.json` can record them: dedup is a heuristic -- two
    tools word the same defect differently often enough that it can over- or
    under-merge -- and a heuristic that leaves no trace is not auditable.
    `dedup: false` turns it off entirely.

    This is a CROSS-TOOL operation only. Two findings from the SAME tool that
    share a key are not duplicates: the key normalizes numbers out of the
    message, so two different width mismatches reported on one line collapse
    into one key while being two distinct defects. Dropping one of them would
    silently under-report the tool that found them both -- which is exactly
    what this saw on wb_dma, where a single Verilator run produced 97 findings
    and a tool-blind dedup reported 61.

    Which tool's copy survives is decided by tool id, alphabetically, so the
    merged report does not depend on which tool finished first.
    """
    if not enabled:
        return list(findings), []

    by_key : Dict[Any, List[Finding]] = {}
    for f in findings:
        by_key.setdefault(f.dedup_key(), []).append(f)

    kept, dropped = [], []
    for key, group in by_key.items():
        tools = set(f.tool for f in group)
        if len(tools) < 2 or key[0] == "":
            # One tool, or no file location. Without a location there is no
            # evidence two tools mean the same defect.
            kept.extend(group)
            continue
        winner = min(tools)
        for f in group:
            if f.tool == winner:
                kept.append(f)
            else:
                f.dup_of = winner
                dropped.append(f)

    return sort_findings(kept), sort_findings(dropped)


def summarize(findings : List[Finding], dropped : List[Finding],
              gating : int, tools : List[str],
              skipped : List[str]) -> Summary:
    s = Summary(total=len(findings), duplicates=len(dropped),
                gating=gating, tools=list(tools), skipped=list(skipped))
    for f in findings:
        if f.waived is not None:
            s.waived += 1
        elif f.baseline:
            s.baselined += 1
        else:
            s.new += 1
            if f.severity == SeverityE.Error:
                s.errors += 1
            elif f.severity == SeverityE.Warning:
                s.warnings += 1
            else:
                s.infos += 1
    return s


# ---------------------------------------------------------------------------
# lint.json -- the authoritative record
# ---------------------------------------------------------------------------

def report_doc(findings : List[Finding], dropped : List[Finding],
               summary : Summary, runs : List[Any],
               fail_on : str, stale_baseline : List[Dict[str, Any]],
               unused_waivers : List[Any],
               waiver_mode : str = "post",
               lowered : int = 0) -> Dict[str, Any]:
    return {
        "version": REPORT_VERSION,
        "fail_on": fail_on,
        # How waivers were applied, and how many the tools took over. Without
        # this, a `waived: 0` under native lowering reads as "no waiver
        # matched" when it means "the tools suppressed them before we looked".
        "waiver_mode": waiver_mode,
        "waivers_lowered": lowered,
        "summary": summary.to_dict(),
        "runs": [r.to_dict() for r in runs],
        "findings": [f.to_dict() for f in findings],
        "duplicates": [f.to_dict() for f in dropped],
        "stale_baseline": stale_baseline,
        "unused_waivers": [
            {"rule": w.rule, "tool": w.tool, "path": w.path,
             "line": w.line, "reason": w.reason, "src": w.src}
            for w in unused_waivers],
    }


def write_json(path : str, doc : Dict[str, Any]) -> str:
    _mkdir(path)
    with open(path, "w") as fp:
        json.dump(doc, fp, indent=2)
        fp.write("\n")
    return path


# ---------------------------------------------------------------------------
# SARIF 2.1.0
# ---------------------------------------------------------------------------

def sarif_doc(findings : List[Finding], runs : List[Any]) -> Dict[str, Any]:
    """One SARIF run per tool that produced findings.

    Rules are collected per run from the findings themselves. We do not ship a
    rule catalogue per tool: it would be a second thing to keep in step with
    every tool release, and SARIF consumers accept rules discovered from
    results.
    """
    by_tool : Dict[str, List[Finding]] = {}
    for f in findings:
        by_tool.setdefault(f.tool, []).append(f)

    run_info = {r.tool: r for r in runs}

    sarif_runs = []
    for tool in sorted(by_tool.keys()):
        group = by_tool[tool]
        info = run_info.get(tool)
        name = group[0].tool_name or tool

        rules : List[Dict[str, Any]] = []
        rule_index : Dict[str, int] = {}
        for f in group:
            if f.rule and f.rule not in rule_index:
                rule_index[f.rule] = len(rules)
                rules.append({
                    "id": f.rule,
                    "name": f.rule,
                    "shortDescription": {"text": f.rule},
                    "defaultConfiguration": {
                        "level": _SARIF_LEVEL.get(f.severity, "warning")},
                })

        results = []
        for f in group:
            result : Dict[str, Any] = {
                "level": _SARIF_LEVEL.get(f.severity, "warning"),
                "message": {"text": f.msg},
            }
            if f.rule:
                result["ruleId"] = f.rule
                result["ruleIndex"] = rule_index[f.rule]
            if f.path:
                region : Dict[str, Any] = {}
                if f.line > 0:
                    region["startLine"] = f.line
                if f.pos > 0:
                    region["startColumn"] = f.pos
                loc : Dict[str, Any] = {
                    "physicalLocation": {
                        "artifactLocation": {"uri": f.path},
                    }
                }
                if region:
                    loc["physicalLocation"]["region"] = region
                result["locations"] = [loc]
            if f.suppressed:
                # SARIF's own way of saying "known and accepted". Consumers
                # (GitHub code scanning among them) hide these rather than
                # annotating them, and the justification travels with them.
                result["suppressions"] = [{
                    "kind": "external",
                    "justification": (f.waived if f.waived is not None
                                      else "Present in the accepted lint baseline"),
                }]
            results.append(result)

        driver : Dict[str, Any] = {"name": name, "rules": rules}
        if tool in _TOOL_URI:
            driver["informationUri"] = _TOOL_URI[tool]
        if info is not None and info.version:
            driver["version"] = info.version

        sarif_runs.append({
            "tool": {"driver": driver},
            "results": results,
        })

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": sarif_runs,
    }


def write_sarif(path : str, findings : List[Finding], runs : List[Any]) -> str:
    _mkdir(path)
    with open(path, "w") as fp:
        json.dump(sarif_doc(findings, runs), fp, indent=2)
        fp.write("\n")
    return path


# ---------------------------------------------------------------------------
# CTRF -- the CI test-report rendering
# ---------------------------------------------------------------------------

CTRF_SPEC_VERSION = "0.0.0"


def _ctrf_status(f : Finding, gating_keys) -> str:
    if f.suppressed:
        return "skipped"
    if id(f) in gating_keys:
        return "failed"
    return "other"


def ctrf_doc(findings : List[Finding], summary : Summary, runs : List[Any],
             gating : List[Finding], start_ms : int, stop_ms : int,
             report_id : Optional[str] = None) -> Dict[str, Any]:
    """Findings as a CTRF report.

    Each finding is one CTRF "test", named `<tool>:<rule> <file>:<line>` so
    that the CI UI shows the rule and the location in the row title and the
    message in the detail. Every tool that ran without contributing a failure
    adds one `passed` entry -- without it, a clean lint run renders as an
    empty report, which is indistinguishable from a lint run that never
    happened.
    """
    gating_keys = set(id(f) for f in gating)

    tests : List[Dict[str, Any]] = []
    failed_tools = set(f.tool for f in gating)

    for f in findings:
        status = _ctrf_status(f, gating_keys)
        name = "%s %s" % (f.label, f.location or "<no location>")
        test : Dict[str, Any] = {
            "name": name,
            "status": status,
            "duration": 0,
            "suite": f.tool_name or f.tool,
            "message": f.msg,
        }
        if f.path:
            test["filePath"] = f.path
            if f.line > 0:
                test["line"] = f.line
        tags = [t for t in (f.tool_name or f.tool, f.rule, severity_str(f.severity)) if t]
        test["tags"] = tags
        extra : Dict[str, Any] = {
            "tool": f.tool,
            "rule": f.rule,
            "severity": severity_str(f.severity),
        }
        if f.waived is not None:
            extra["waived"] = f.waived
            test["message"] = "%s [waived: %s]" % (f.msg, f.waived)
        if f.baseline:
            extra["baseline"] = True
            test["message"] = "%s [baselined]" % f.msg
        test["extra"] = extra
        tests.append(test)

    for r in runs:
        if r.skipped:
            tests.append({
                "name": "%s: skipped" % r.name,
                "status": "skipped",
                "duration": 0,
                "suite": r.name,
                "message": r.skipped,
                "tags": [r.name],
            })
        elif r.tool not in failed_tools:
            tests.append({
                "name": "%s: clean" % r.name,
                "status": "passed",
                "duration": int(r.duration * 1000),
                "suite": r.name,
                "message": "%s reported no findings that fail the gate" % r.name,
                "tags": [r.name],
            })

    counts = {"passed": 0, "failed": 0, "skipped": 0, "pending": 0, "other": 0}
    for t in tests:
        counts[t["status"]] = counts.get(t["status"], 0) + 1

    return {
        "reportFormat": "CTRF",
        "specVersion": CTRF_SPEC_VERSION,
        "reportId": report_id or str(uuid.uuid4()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_ms / 1000.0)),
        "generatedBy": "dv-flow-libhdllint",
        "results": {
            "tool": {"name": "hdllint"},
            "summary": {
                "tests": len(tests),
                "passed": counts["passed"],
                "failed": counts["failed"],
                "pending": counts["pending"],
                "skipped": counts["skipped"],
                "other": counts["other"],
                "start": start_ms,
                "stop": stop_ms,
            },
            "tests": tests,
            "extra": summary.to_dict(),
        },
    }


def write_ctrf(path : str, doc : Dict[str, Any]) -> str:
    _mkdir(path)
    with open(path, "w") as fp:
        json.dump(doc, fp, indent=2)
        fp.write("\n")
    return path


def _mkdir(path : str):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
