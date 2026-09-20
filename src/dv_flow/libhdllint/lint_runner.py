#****************************************************************************
#* lint_runner.py
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
"""The lint driver: the implementation behind `hdllint.Rtl` / `Tb` / `Style`.

One task does the whole pipeline:

    select tools -> run them (concurrently) -> normalize -> dedup
                 -> waivers -> baseline -> report -> gate

The tools run as coroutines inside ONE task rather than as separate task
nodes fanned out by an elaborator. That is a departure from the plan's
sketch, and the reason is the merge: cross-tool dedup, a shared baseline and
a single `fail_on` verdict all need every tool's findings at once, so a
fan-out would need a join task immediately after it, and the join would hold
all the logic anyway. What the graph fan-out would have bought -- per-tool
caching and per-tool rundirs -- is partly recovered here: each backend gets
its own subdirectory of the task rundir, with its own log and command file.
What is genuinely given up is per-tool incremental caching; that is the
honest cost, and it is revisitable without changing anything a flow file
says.
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from dv_flow.mgr import FileSet, TaskDataResult
from dv_flow.mgr.task_data import SeverityE, TaskMarker, TaskMarkerLoc

from . import backends as backends_mod
from . import baseline as baseline_mod
from . import gate as gate_mod
from . import report as report_mod
from . import waiver as waiver_mod
from .backends import SelectionError, ToolRequest, ToolRun
from .finding import Finding, relpath, sort_findings
from .util import merge_tokenize

_log = logging.getLogger("hdllint.runner")


# Source filetypes a lint backend can be handed. Include directories arrive
# as their own filetypes rather than as files.
_SOURCE_FILETYPES = ("systemVerilogSource", "verilogSource")
_INCDIR_FILETYPES = ("verilogIncDir",)
_INCLUDE_FILETYPES = ("verilogInclude", "systemVerilogInclude")


class _Inputs(object):
    """Sources, include directories and defines gathered from the task inputs."""

    def __init__(self):
        self.files : List[str] = []
        self.incdirs : List[str] = []
        self.defines : List[str] = []
        self.args_by_tool : Dict[str, List[str]] = {}
        self.incdirs_by_tool : Dict[str, List[str]] = {}
        self.defines_by_tool : Dict[str, List[str]] = {}
        self.waivers : List[waiver_mod.Waiver] = []

    def add_incdir(self, d : str):
        if d and d not in self.incdirs:
            self.incdirs.append(d)


def _gather(input) -> _Inputs:
    """Collect lint inputs from the task's dataflow.

    The filetype handling mirrors libhdlsim's `_gatherSvSources` deliberately:
    a project should be able to point its lint task at exactly the same
    `src-rtl` fileset its build uses and get the same file and include-path
    view. `wb_dma`, where every module `include`s `wb_dma_defines.v`, is the
    case that makes this non-negotiable -- get the include path wrong and the
    entire run is parse errors.
    """
    out = _Inputs()

    for it in input.inputs:
        itype = getattr(it, "type", None)

        if itype == "std.FileSet":
            filetype = getattr(it, "filetype", "")
            basedir = getattr(it, "basedir", "") or ""
            files = getattr(it, "files", []) or []
            fs_incdirs = getattr(it, "incdirs", []) or []

            for d in getattr(it, "defines", []) or []:
                if d not in out.defines:
                    out.defines.append(d)

            if filetype in _SOURCE_FILETYPES:
                for f in files:
                    out.files.append(os.path.join(basedir, f))
                for d in fs_incdirs:
                    out.add_incdir(os.path.join(basedir, d))
            elif filetype in _INCDIR_FILETYPES:
                if basedir.strip():
                    out.add_incdir(basedir)
            elif filetype in _INCLUDE_FILETYPES:
                if fs_incdirs:
                    for d in fs_incdirs:
                        out.add_incdir(os.path.join(basedir, d))
                elif basedir.strip():
                    out.add_incdir(basedir)

        elif itype == "hdllint.LintArgs":
            tool = str(getattr(it, "tool", "") or "")
            out.args_by_tool.setdefault(tool, []).extend(
                merge_tokenize(getattr(it, "args", [])))
            out.incdirs_by_tool.setdefault(tool, []).extend(
                merge_tokenize(getattr(it, "incdirs", [])))
            out.defines_by_tool.setdefault(tool, []).extend(
                merge_tokenize(getattr(it, "defines", [])))

        elif itype == "hdllint.LintWaivers":
            src = getattr(it, "src", "") or "hdllint.LintWaivers"
            inline = getattr(it, "waivers", None)
            if inline:
                out.waivers.extend(waiver_mod.load_waivers(inline, src))
            f = str(getattr(it, "file", "") or "")
            if f:
                out.waivers.extend(waiver_mod.load_waiver_file(f))

    return out


def _resolve(path : str, base : str) -> str:
    if not path:
        return ""
    return path if os.path.isabs(path) else os.path.join(base, path)


async def Lint(ctxt, input) -> TaskDataResult:
    """`hdllint.Rtl` / `hdllint.Tb` / `hdllint.Style`."""
    markers : List[TaskMarker] = []
    output : List[Any] = []
    status = 0

    def info(msg):
        markers.append(TaskMarker(msg=msg, severity=SeverityE.Info))

    def error(msg):
        markers.append(TaskMarker(msg=msg, severity=SeverityE.Error))

    p = input.params
    family = str(getattr(p, "family", "Rtl"))
    root = ctxt.root_pkgdir or ""
    start_ms = int(time.time() * 1000)

    # ---------------------------------------------------------------- inputs
    try:
        gathered = _gather(input)
    except waiver_mod.WaiverError as e:
        error(str(e))
        return TaskDataResult(status=1, markers=markers)

    if not gathered.files:
        error("No source files to lint. `%s` consumes systemVerilogSource / "
              "verilogSource filesets; add the source task to its `needs:`."
              % input.name)
        return TaskDataResult(status=1, markers=markers)

    waivers = list(gathered.waivers)
    waiver_file = _resolve(str(getattr(p, "waivers", "") or ""), input.srcdir)
    if waiver_file:
        try:
            waivers.extend(waiver_mod.load_waiver_file(waiver_file))
        except waiver_mod.WaiverError as e:
            error(str(e))
            return TaskDataResult(status=1, markers=markers)

    baseline_file = _resolve(str(getattr(p, "baseline", "") or ""), input.srcdir)
    try:
        base = baseline_mod.load_baseline(baseline_file)
    except baseline_mod.BaselineError as e:
        error(str(e))
        return TaskDataResult(status=1, markers=markers)

    # ------------------------------------------------------------ tool select
    try:
        sel = backends_mod.select(
            list(getattr(p, "tools", []) or []), family, ctxt.env)
    except SelectionError as e:
        error(str(e))
        return TaskDataResult(status=1, markers=markers)

    for b, reason in sel.skipped:
        # A skipped tool is stated, never silently omitted: a report that is
        # thin because a tool is missing must not read like a report that is
        # thin because the code is clean.
        info("%s: %s" % (b.name, reason))

    # ------------------------------------------------------------------- run
    profile = str(getattr(p, "profile", "default") or "default")
    top = [str(t) for t in (getattr(p, "top", []) or [])]
    common_args = merge_tokenize(getattr(p, "args", []))
    common_incdirs = list(gathered.incdirs) + merge_tokenize(getattr(p, "incdirs", []))
    common_defines = list(gathered.defines) + merge_tokenize(getattr(p, "defines", []))

    waiver_mode = str(getattr(p, "waiver_mode", "post") or "post").lower()
    if waiver_mode not in ("post", "native"):
        error("Unknown waiver_mode '%s'. Expected 'post' or 'native'."
              % waiver_mode)
        return TaskDataResult(status=1, markers=markers)

    # Waivers the backends now suppress themselves. Tracked by identity: a
    # lowered waiver cannot be reported as unused (the tool never emits the
    # finding, so there is nothing to match), and must not be counted as
    # `waived` either -- see the note emitted below.
    lowered_all : Dict[int, Any] = {}

    async def run_one(b):
        rundir = os.path.join(input.rundir, b.id)
        os.makedirs(rundir, exist_ok=True)
        req = ToolRequest(
            family=family,
            backend=b,
            files=list(gathered.files),
            incdirs=common_incdirs + gathered.incdirs_by_tool.get(b.id, []),
            defines=common_defines + gathered.defines_by_tool.get(b.id, []),
            top=top,
            args=(common_args
                  + gathered.args_by_tool.get("", [])
                  + gathered.args_by_tool.get(b.id, [])),
            profile=profile,
            rundir=rundir,
            root=root,
            env=ctxt.env,
            exe=backends_mod.which(b.exe, ctxt.env) or b.exe)
        try:
            fn = b.load()
        except (ImportError, AttributeError) as e:
            return (ToolRun(tool=b.id, name=b.name,
                            error="backend '%s' failed to load: %s" % (b.id, e)),
                    [], [])

        n_lowered = 0
        if waiver_mode == "native" and waivers:
            try:
                lowerer = b.load_lowerer()
            except (ImportError, AttributeError) as e:
                return (ToolRun(tool=b.id, name=b.name,
                                error="backend '%s' waiver lowering failed to "
                                      "load: %s" % (b.id, e)), [], [])
            if lowerer is not None:
                extra, lowered = lowerer(waivers, req)
                req.args = list(req.args) + list(extra)
                for w in lowered:
                    lowered_all[id(w)] = w
                n_lowered = len(lowered)

        run_info, tool_findings, notes = await fn(ctxt, req)
        run_info.lowered = n_lowered
        return run_info, tool_findings, notes

    results = await asyncio.gather(
        *[run_one(b) for b in sel.selected], return_exceptions=True)

    runs : List[ToolRun] = []
    findings : List[Finding] = []
    for b, res in zip(sel.selected, results):
        if isinstance(res, BaseException):
            _log.exception("backend %s raised", b.id, exc_info=res)
            runs.append(ToolRun(tool=b.id, name=b.name,
                                error="%s: %s" % (type(res).__name__, res)))
            continue
        run_info, tool_findings, notes = res
        runs.append(run_info)
        findings.extend(tool_findings)
        for n in notes:
            info(n)

    for b, reason in sel.skipped:
        runs.append(ToolRun(tool=b.id, name=b.name, skipped=reason))

    for r in runs:
        if r.error:
            error("%s: %s" % (r.name, r.error))
            status = 1

    # ----------------------------------------------------------- post-filters
    # Order matters. Dedup first, so a waiver written against one tool is not
    # defeated by another tool's copy of the same finding, and so baseline
    # keys are stable when the tool set changes. Waivers next, because a
    # waived finding carries a human reason and should never be recorded as
    # merely baselined. Baseline last.
    dedup_enabled = bool(getattr(p, "dedup", True))
    findings, dropped = report_mod.dedup(findings, dedup_enabled)

    n_waived = waiver_mod.apply_waivers(findings, waivers)
    n_baselined, stale = baseline_mod.apply_baseline(findings, base)

    findings = sort_findings(findings)

    fail_on = str(getattr(p, "fail_on", "error") or "error")
    try:
        gating = gate_mod.gating_findings(findings, fail_on)
    except gate_mod.GateError as e:
        error(str(e))
        return TaskDataResult(status=1, markers=markers)

    summary = report_mod.summarize(
        findings, dropped, len(gating),
        [b.id for b in sel.selected],
        [b.id for b, _ in sel.skipped])

    # ---------------------------------------------------------------- reports
    stem = str(getattr(p, "report", "lint") or "lint")
    json_path = os.path.join(input.rundir, "%s.json" % stem)

    # A lowered waiver is suppressed inside the tool, so it can never match a
    # finding here. Reporting it as unused would be a false alarm on exactly
    # the waivers that are working.
    unused = [w for w in waiver_mod.unused_waivers(waivers)
              if id(w) not in lowered_all]

    doc = report_mod.report_doc(
        findings, dropped, summary, runs, fail_on, stale, unused,
        waiver_mode=waiver_mode, lowered=len(lowered_all))
    report_mod.write_json(json_path, doc)

    report_files = ["%s.json" % stem]

    sarif_path = ""
    if bool(getattr(p, "sarif", True)):
        sarif_path = os.path.join(input.rundir, "%s.sarif" % stem)
        report_mod.write_sarif(sarif_path, findings, runs)
        report_files.append("%s.sarif" % stem)

    ctrf_path = ""
    if bool(getattr(p, "ctrf", True)):
        ctrf_path = os.path.join(input.rundir, "%s-ctrf.json" % stem)
        report_mod.write_ctrf(
            ctrf_path,
            report_mod.ctrf_doc(findings, summary, runs, gating,
                                start_ms, int(time.time() * 1000)))
        report_files.append("%s-ctrf.json" % stem)

    # --------------------------------------------------------------- baseline
    if bool(getattr(p, "update_baseline", False)):
        if not baseline_file:
            error("update_baseline was requested, but no `baseline:` file is "
                  "configured on task '%s'." % input.name)
            status = 1
        else:
            written = baseline_mod.write_baseline(
                baseline_file, findings, [b.id for b in sel.selected])
            info("Baseline written: %s (%d finding%s%s)"
                 % (relpath(baseline_file, root), written["total"],
                    "" if written["total"] == 1 else "s",
                    "" if not base.present
                    else ", was %d" % len(base)))
            # The baseline now covers everything, so the gate has nothing to
            # report. Say that, rather than printing a pass that means
            # "we just accepted all of it".
            info("Baseline updated: this run's verdict reflects the NEW "
                 "baseline, not the state before it.")
            return TaskDataResult(
                status=status,
                markers=markers,
                output=_output(ctxt, input, summary, json_path, sarif_path,
                               ctrf_path, report_files, fail_on))

    # ---------------------------------------------------------------- markers
    max_markers = int(getattr(p, "max_markers", 0) or 0)
    emitted = 0
    for f in findings:
        if f.suppressed:
            continue
        if max_markers and emitted >= max_markers:
            break
        markers.append(f.marker())
        emitted += 1

    unmarked = summary.new - emitted
    if unmarked > 0:
        # An explicit statement, not a silent truncation: a report that shows
        # 50 of 400 findings and says nothing is worse than one that shows
        # all 400.
        info("%d further finding%s not shown (max_markers=%d); all of them are "
             "in %s" % (unmarked, "" if unmarked == 1 else "s", max_markers,
                        relpath(json_path, root)))

    for w in unused:
        # A waiver matching nothing is a statement about the codebase that is
        # no longer true: either the finding was fixed (delete the waiver) or
        # it moved (fix the waiver). Either way the reader should know.
        markers.append(TaskMarker(
            severity=SeverityE.Warning,
            msg="Unused lint waiver (%s): rule='%s'%s%s -- \"%s\""
                % (w.src, w.rule,
                   ", tool='%s'" % w.tool if w.tool else "",
                   ", path='%s'" % w.path if w.path else "",
                   w.reason)))

    if stale:
        n = sum(int(e.get("count", 1)) for e in stale)
        info("%d baselined finding%s no longer occur%s; refresh the baseline "
             "with `-D %s.update_baseline=true` to shrink it."
             % (n, "" if n == 1 else "s", "s" if n == 1 else "",
                input.name))

    if lowered_all:
        # Said plainly, because it changes what the counts mean: the tool
        # never emitted these findings, so they are not in `waived` and a
        # stale one among them cannot be detected.
        info("%d waiver%s lowered into tool-native suppression (waiver_mode="
             "native); those findings are never reported, so they are not "
             "counted as waived and cannot be reported as stale. Use "
             "waiver_mode=post for exact waiver accounting."
             % (len(lowered_all), "" if len(lowered_all) == 1 else "s"))

        not_lowered = len(waivers) - len(lowered_all)
        if not_lowered:
            info("%d waiver%s could not be expressed natively and %s applied "
                 "as a post-filter (rule globs, tool-scoped waivers, "
                 "basename-only paths, and rule-less messages cannot be "
                 "lowered)."
                 % (not_lowered, "" if not_lowered == 1 else "s",
                    "was" if not_lowered == 1 else "were"))

    info(gate_mod.headline(summary, fail_on))
    info("Lint reports: %s" % ", ".join(
        relpath(os.path.join(input.rundir, f), root) for f in report_files))

    if gating:
        status = 1

    return TaskDataResult(
        status=status,
        markers=markers,
        output=_output(ctxt, input, summary, json_path, sarif_path, ctrf_path,
                       report_files, fail_on))


def _output(ctxt, input, summary, json_path, sarif_path, ctrf_path,
            report_files, fail_on) -> List[Any]:
    """The task's dataflow output.

    Two items, for two consumers:

    * `hdllint.Report` -- the verdict and the counts. It carries `passed` and
      `status` but deliberately NOT a field named `total`, because
      `std.TestRunner`'s summary treats an item with `total`+`passed` as a
      suite roll-up and one with `passed` alone as a single case verdict. A
      lint task is a case, so the count is named `findings`, and lint appears
      as one row in a project's test report with no extra wiring.
    * a `lintReport` fileset -- the report files themselves, so a publish or
      an upload task can pick them up by filetype.
    """
    item = ctxt.mkDataItem(
        type="hdllint.Report",
        passed=summary.passed,
        status="passed" if summary.passed else "failed",
        findings=summary.total,
        new=summary.new,
        waived=summary.waived,
        baselined=summary.baselined,
        duplicates=summary.duplicates,
        errors=summary.errors,
        warnings=summary.warnings,
        infos=summary.infos,
        gating=summary.gating,
        fail_on=fail_on,
        tools=list(summary.tools),
        skipped=list(summary.skipped),
        report=json_path,
        sarif=sarif_path,
        ctrf=ctrf_path)

    fs = FileSet(
        src=input.name,
        filetype="lintReport",
        basedir=input.rundir,
        files=list(report_files))

    return [item, fs]
