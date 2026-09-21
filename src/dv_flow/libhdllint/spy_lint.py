#****************************************************************************
#* spy_lint.py
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
"""The SpyGlass backend: build the TCL script, run it, parse the log.

SpyGlass runs inside `sg_shell`, driven by a TCL script that:

1. Creates (or opens) a project.
2. Reads the RTL source and include directories.
3. Runs the selected goal (a lint profile).
4. Exports a text report that the parser can consume.

Profiles map to SpyGlass goals:

| profile   | goal                      |
|-----------|---------------------------|
| `basic`   | `lint/lint_turbo_rtl`     |
| `default` | `lint/lint_rtl`           |
| `strict`  | `lint/lint_rtl_enhanced`  |

SpyGlass implements both the `Rtl` and `Style` families.

SpyGlass is the property of its respective owners.
"""

import logging
import os
import time
from typing import List, Tuple

from .backends import ToolRequest, ToolRun
from .finding import Finding
from .util import exec_tool, tool_version
from . import spy_parser

_log = logging.getLogger("hdllint.spy")


PROFILES = {
    "basic":   "lint/lint_turbo_rtl",
    "default": "lint/lint_rtl",
    "strict":  "lint/lint_rtl_enhanced",
}

REPORT_FILE = "spyglass_lint.rpt"


def _write_tcl(req: ToolRequest, goal: str, report_path: str) -> str:
    """Write the TCL driver script and return its path."""
    tcl_path = os.path.join(req.rundir, "run_lint.tcl")
    lines: List[str] = []

    project = "lint_project"
    lines.append("new_project %s -projectwdir %s -force"
                 % (project, req.rundir.replace(os.sep, "/")))

    for incdir in req.incdirs:
        lines.append("set_option incdir {%s}" % incdir)

    for define in req.defines:
        lines.append("set_option define {%s}" % define)

    if req.top:
        lines.append("set_option top {%s}" % " ".join(req.top))

    for f in req.files:
        lines.append("read_file -type verilog {%s}" % f)

    lines.append("current_goal %s" % goal)
    lines.append("run_goal")
    lines.append("write_report -output %s" % report_path.replace(os.sep, "/"))
    lines.append("close_project -force")
    lines.append("exit")

    with open(tcl_path, "w") as fp:
        fp.write("\n".join(lines) + "\n")

    return tcl_path


def build_cmd(req: ToolRequest) -> Tuple[List[str], List[str]]:
    """`(cmd, notes)`. Notes are Info-level things the user should be told."""
    notes: List[str] = []

    if req.profile not in PROFILES:
        raise ValueError(
            "Unknown lint profile '%s' for spyglass. Available: %s."
            % (req.profile, ", ".join(sorted(PROFILES.keys()))))

    goal = PROFILES[req.profile]
    report_path = os.path.join(req.rundir, REPORT_FILE)
    tcl_path = _write_tcl(req, goal, report_path)

    cmd = [req.exe or "sg_shell", "-tcl_file", tcl_path]
    cmd.extend(req.args)

    if not req.top:
        notes.append(
            "spyglass: no `top:` given. SpyGlass will attempt to infer the "
            "top module; checks that require elaboration may be incomplete.")

    return cmd, notes


async def run(ctxt, req: ToolRequest) -> Tuple[ToolRun, List[Finding], List[str]]:
    """Run SpyGlass over `req` and return `(run_info, findings, notes)`."""
    run_info = ToolRun(tool=spy_parser.TOOL_ID, name=spy_parser.TOOL_NAME)

    try:
        cmd, notes = build_cmd(req)
    except ValueError as e:
        run_info.error = str(e)
        return run_info, [], []

    run_info.cmd = cmd
    run_info.version = await tool_version(
        req.exe or "sg_shell", ["-version"], req.env)

    start = time.time()
    status, log_path = await exec_tool(
        ctxt, cmd, req.rundir, "lint.log", req.env)
    run_info.duration = time.time() - start
    run_info.status = status
    run_info.log = log_path

    # Parse the text report if it was written; fall back to the raw log.
    report_path = os.path.join(req.rundir, REPORT_FILE)
    parse_path = report_path if os.path.isfile(report_path) else log_path

    findings = spy_parser.parse_file(parse_path, req.root)
    run_info.findings = len(findings)

    if status != 0 and not findings:
        run_info.error = (
            "sg_shell exited %d and produced no parsable findings; see %s"
            % (status, log_path))

    return run_info, findings, notes
