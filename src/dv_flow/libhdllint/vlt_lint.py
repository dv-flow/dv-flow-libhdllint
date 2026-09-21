#****************************************************************************
#* vlt_lint.py
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
"""The Verilator backend: build the command line, run it, parse the log.

Verilator is the reference backend. It is the one that has to be right,
because it is the one every project already has, and the one the other
backends are written against.

Two flags are always present and are worth explaining, since both look like
policy decisions taken away from the user:

* `--lint-only` -- no C++ generation, no build. This is a lint library.
* `-Wno-fatal` -- without it Verilator exits as soon as warnings accumulate
  and reports a truncated set. We want every finding in one run; whether the
  run *fails* is the gate's decision (`fail_on:`), made over the normalized
  findings after waivers and the baseline have been applied. Letting Verilator
  decide would mean a waived finding still failed the build.

Note what Verilator cannot do, because the capability registry says so and a
user will eventually ask: it parses the synthesis subset, so it does not see
class-based testbench code at all. It implements `Rtl` and no other family.
"""

import logging
import os
import time
from typing import List, Tuple

from .backends import ToolRequest, ToolRun
from .finding import Finding
from .util import exec_tool, tool_version
from . import vlt_parser

_log = logging.getLogger("hdllint.vlt")


# Profiles. Kept thin on purpose (see docs/guide/profiles.md): `default` is
# Verilator's own -Wall, not a curated list, so it tracks the tool rather than
# rotting against it. `basic` is the tool's default warning set for a first
# run on legacy code; `strict` adds the style-adjacent checks that are off
# even under -Wall.
PROFILES = {
    "basic":   [],
    "default": ["-Wall"],
    "strict":  ["-Wall", "-Wpedantic"],
}


def build_cmd(req : ToolRequest) -> Tuple[List[str], List[str]]:
    """`(cmd, notes)`. Notes are Info-level things the user should be told."""
    notes : List[str] = []

    if req.profile not in PROFILES:
        raise ValueError(
            "Unknown lint profile '%s' for verilator. Available: %s."
            % (req.profile, ", ".join(sorted(PROFILES.keys()))))

    cmd = [req.exe or "verilator", "--lint-only", "-Wno-fatal"]
    cmd.extend(PROFILES[req.profile])

    for incdir in req.incdirs:
        cmd.append("+incdir+%s" % incdir)
    for define in req.defines:
        cmd.append("+define+%s" % define)

    cmd.extend(req.args)
    cmd.extend(req.files)

    if req.top:
        # Verilator takes a single --top-module; a later one replaces the
        # earlier silently. Say so rather than letting the run quietly lint
        # one top when the flow asked for three.
        cmd.extend(["--top-module", req.top[0]])
        if len(req.top) > 1:
            notes.append(
                "verilator accepts one --top-module; linting '%s' and ignoring %s. "
                "Use a separate lint task per top to cover the others."
                % (req.top[0], ", ".join("'%s'" % t for t in req.top[1:])))
    else:
        notes.append(
            "verilator: no `top:` given, so the design is linted without a "
            "specified top. Checks that need elaboration (width, latch, "
            "unused/undriven) are only as good as the top Verilator infers.")

    return cmd, notes


async def run(ctxt, req : ToolRequest) -> Tuple[ToolRun, List[Finding], List[str]]:
    """Run Verilator over `req` and return `(run_info, findings, notes)`."""
    run_info = ToolRun(tool=vlt_parser.TOOL_ID, name=vlt_parser.TOOL_NAME)

    try:
        cmd, notes = build_cmd(req)
    except ValueError as e:
        run_info.error = str(e)
        return run_info, [], []

    run_info.cmd = cmd
    run_info.version = await tool_version(
        req.exe or "verilator", ["--version"], req.env)

    # The command file is how a user reproduces the run by hand. Verilator's
    # own -f format, so `verilator -f lint.f` works verbatim.
    with open(os.path.join(req.rundir, "lint.f"), "w") as fp:
        for arg in cmd[1:]:
            fp.write("%s\n" % arg)

    start = time.time()
    status, log_path = await exec_tool(
        ctxt, cmd, req.rundir, "lint.log", req.env)
    run_info.duration = time.time() - start
    run_info.status = status
    run_info.log = log_path

    findings = vlt_parser.parse_file(log_path, req.root)
    run_info.findings = len(findings)

    # A non-zero exit with nothing parsed means Verilator failed for a reason
    # the parser did not recognize -- a bad flag, a missing file, a crash.
    # Reporting that as "no findings" is exactly the lie the capability
    # registry exists to prevent, so it is surfaced as a run error.
    if status != 0 and not findings:
        run_info.error = (
            "verilator exited %d and produced no parsable findings; see %s"
            % (status, log_path))

    return run_info, findings, notes
