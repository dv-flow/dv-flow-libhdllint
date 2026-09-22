#****************************************************************************
#* z0i_lint.py
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
"""The 0-in backend: build the command line, run it, parse the log.

0-in is invoked as:

    0in -lint <files> -top <top>

The three profiles control the depth of checking:

* ``basic`` -- default checks (no extra flags).
* ``default`` -- ``-full`` (all standard checks enabled).
* ``strict`` -- ``-full -all`` (every check including advisory).

0-in does not support native waiver lowering; all waivers are handled by
the post-filter.

0-in is the property of its respective owners.
"""

import logging
import os
import time
from typing import List, Tuple

from .backends import ToolRequest, ToolRun
from .finding import Finding
from .util import exec_tool, tool_version
from . import z0i_parser

_log = logging.getLogger("hdllint.z0i")


PROFILES = {
    "basic":   [],
    "default": ["-full"],
    "strict":  ["-full", "-all"],
}


def build_cmd(req: ToolRequest) -> Tuple[List[str], List[str]]:
    """`(cmd, notes)`. Notes are Info-level things the user should be told."""
    notes: List[str] = []

    if req.profile not in PROFILES:
        raise ValueError(
            "Unknown lint profile '%s' for 0-in. Available: %s."
            % (req.profile, ", ".join(sorted(PROFILES.keys()))))

    cmd = [req.exe or "0in", "-lint"]
    cmd.extend(PROFILES[req.profile])

    for incdir in req.incdirs:
        cmd.extend(["+incdir+%s" % incdir])
    for define in req.defines:
        cmd.extend(["+define+%s" % define])

    cmd.extend(req.args)
    cmd.extend(req.files)

    if req.top:
        cmd.extend(["-top", req.top[0]])
        if len(req.top) > 1:
            notes.append(
                "0-in accepts one -top; linting '%s' and ignoring %s. "
                "Use a separate lint task per top to cover the others."
                % (req.top[0], ", ".join("'%s'" % t for t in req.top[1:])))
    else:
        notes.append(
            "0-in: no `top:` given, so the design is linted without a "
            "specified top. Checks that need elaboration may be incomplete.")

    return cmd, notes


async def run(ctxt, req: ToolRequest) -> Tuple[ToolRun, List[Finding], List[str]]:
    """Run 0-in lint over `req` and return `(run_info, findings, notes)`."""
    run_info = ToolRun(tool=z0i_parser.TOOL_ID, name=z0i_parser.TOOL_NAME)

    try:
        cmd, notes = build_cmd(req)
    except ValueError as e:
        run_info.error = str(e)
        return run_info, [], []

    run_info.cmd = cmd
    run_info.version = await tool_version(
        req.exe or "0in", ["-version"], req.env)

    # Write a command file for reproducibility.
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

    findings = z0i_parser.parse_file(log_path, req.root)
    run_info.findings = len(findings)

    if status != 0 and not findings:
        run_info.error = (
            "0in exited %d and produced no parsable findings; see %s"
            % (status, log_path))

    return run_info, findings, notes
