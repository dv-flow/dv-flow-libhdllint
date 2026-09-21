#****************************************************************************
#* qst_lint.py
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
"""The Questa Lint backend: build the command line, run it, parse the log.

Questa Lint uses Siemens `qverify` in AutoCheck mode. The lint flow is
driven by a ``-do`` script that compiles the design and runs the checker:

    qverify -c -do "autocheck compile -d <top>; autocheck verify -timeout 0; exit"

``-timeout 0`` disables the time limit so every check is attempted.
``-c`` suppresses the GUI.

Questa Lint does not support native waiver lowering; all waivers are
handled by the post-filter.

Questa Lint is the property of its respective owners.
"""

import logging
import os
import time
from typing import List, Tuple

from .backends import ToolRequest, ToolRun
from .finding import Finding
from .util import exec_tool, tool_version
from . import qst_parser

_log = logging.getLogger("hdllint.qst")


PROFILES = {
    "basic":   ["-autocheck_mode", "quick"],
    "default": [],
    "strict":  ["-autocheck_mode", "deep"],
}


def build_cmd(req: ToolRequest) -> Tuple[List[str], List[str]]:
    """`(cmd, notes)`. Notes are Info-level things the user should be told."""
    notes: List[str] = []

    if req.profile not in PROFILES:
        raise ValueError(
            "Unknown lint profile '%s' for questa_lint. Available: %s."
            % (req.profile, ", ".join(sorted(PROFILES.keys()))))

    # Build the -do script.
    compile_opts = ""
    if req.top:
        compile_opts = " -d %s" % req.top[0]
        if len(req.top) > 1:
            notes.append(
                "questa_lint accepts one -d top; linting '%s' and ignoring %s. "
                "Use a separate lint task per top to cover the others."
                % (req.top[0], ", ".join("'%s'" % t for t in req.top[1:])))
    else:
        notes.append(
            "questa_lint: no `top:` given, so AutoCheck will infer the top "
            "module. Checks that need elaboration may be incomplete.")

    do_script = "autocheck compile%s; autocheck verify -timeout 0; exit" % compile_opts

    cmd = [req.exe or "qverify", "-c"]
    cmd.extend(PROFILES[req.profile])

    for incdir in req.incdirs:
        cmd.extend(["+incdir+%s" % incdir])
    for define in req.defines:
        cmd.extend(["+define+%s" % define])

    cmd.extend(req.args)
    cmd.extend(req.files)
    cmd.extend(["-do", do_script])

    return cmd, notes


async def run(ctxt, req: ToolRequest) -> Tuple[ToolRun, List[Finding], List[str]]:
    """Run Questa Lint over `req` and return `(run_info, findings, notes)`."""
    run_info = ToolRun(tool=qst_parser.TOOL_ID, name=qst_parser.TOOL_NAME)

    try:
        cmd, notes = build_cmd(req)
    except ValueError as e:
        run_info.error = str(e)
        return run_info, [], []

    run_info.cmd = cmd
    run_info.version = await tool_version(
        req.exe or "qverify", ["-version"], req.env)

    # Write a shell script for reproducibility.
    with open(os.path.join(req.rundir, "lint.sh"), "w") as fp:
        fp.write("#!/bin/sh\n")
        for arg in cmd:
            fp.write("%s \\\n" % arg)

    start = time.time()
    status, log_path = await exec_tool(
        ctxt, cmd, req.rundir, "lint.log", req.env)
    run_info.duration = time.time() - start
    run_info.status = status
    run_info.log = log_path

    findings = qst_parser.parse_file(log_path, req.root)
    run_info.findings = len(findings)

    if status != 0 and not findings:
        run_info.error = (
            "qverify exited %d and produced no parsable findings; see %s"
            % (status, log_path))

    return run_info, findings, notes
