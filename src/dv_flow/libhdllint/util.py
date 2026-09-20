#****************************************************************************
#* util.py
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
import asyncio
import logging
import os
import shlex
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger("hdllint.util")


def merge_tokenize(input : Any) -> List[str]:
    """Flatten a list-or-string parameter into argv tokens.

    Matches libhdlsim's helper of the same name, so `args: "-Wall -Wpedantic"`
    and `args: [-Wall, -Wpedantic]` mean the same thing here as they do there.
    """
    merged : List[str] = []
    if input is None:
        return merged
    if isinstance(input, str):
        merged.extend(shlex.split(input))
    else:
        for elem in input:
            merged.extend(shlex.split(str(elem)))
    return merged


async def exec_tool(ctxt, cmd : List[str], rundir : str,
                    logfile : str, env=None) -> Tuple[int, str]:
    """Run a lint tool, capturing its output. Returns `(status, log_path)`.

    This does NOT use `TaskRunCtxt.exec`, and the reason is specific: that
    helper adds an error marker whenever the command exits non-zero. For a
    compiler that is right. For a lint tool it is not -- Verilator exits
    non-zero precisely *because* it found something, which is the normal
    outcome of a successful lint run. Emitting "Command failed" on top of the
    findings would mean every real lint run reports an error it did not have.

    The jobserver token is still acquired when the runner exposes one, so lint
    processes are gated by `-j` the same way compiles are. It is reached for
    defensively: an older dv-flow-mgr without a jobserver simply runs
    ungated.
    """
    log_path = os.path.join(rundir, logfile)

    jobserver = getattr(getattr(ctxt, "runner", None), "_jobserver", None)
    if jobserver is not None:
        await jobserver.acquire()
    try:
        with open(log_path, "w") as fp:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=fp,
                stderr=asyncio.subprocess.STDOUT,
                cwd=rundir,
                env=env)
            status = await proc.wait()
    finally:
        if jobserver is not None:
            jobserver.release()

    return status, log_path


async def tool_version(exe : str, args : List[str], env=None) -> str:
    """The tool's version string, best-effort.

    Recorded in the report and in the SARIF driver so a finding can be tied to
    the tool release that produced it -- rule names and message wording do
    change between releases, and a parser fixture without a version is a
    fixture nobody can reproduce. Failure is not an error: a tool that has no
    version flag still lints.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            exe, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env)
        out, _ = await proc.communicate()
        return out.decode("utf-8", errors="replace").strip().splitlines()[0]
    except (OSError, IndexError) as e:
        _log.debug("version query for %s failed: %s" % (exe, e))
        return ""


def read_lines(path : str) -> List[str]:
    with open(path, "r", errors="replace") as fp:
        return fp.read().splitlines()
