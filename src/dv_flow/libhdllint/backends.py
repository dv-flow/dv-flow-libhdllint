#****************************************************************************
#* backends.py
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
"""The capability registry, and how a `tools:` list becomes a set of backends.

This is where libhdllint departs from libhdlsim, and the departure is worth
stating plainly because anyone who knows `hdlsim` will expect the other shape.

`hdlsim` selects exactly ONE simulator: `hdlsim.sim` is a scalar, and an
`elaborate:` clause rebinds the task's `uses:` to `hdlsim.<sim>.<Family>`.
That is right for simulation -- running a design on two simulators at once is
not what anyone means by "simulate".

Lint is the opposite. Verilator's elaborated checks (width, latch,
unused/undriven, blocking-order races) and a style checker's source-level
rules barely intersect; running several tools and reading one merged report is
the normal case, not an edge case. So `hdllint.Rtl` takes `tools:` -- a LIST
-- and is itself the implementation: it resolves the list here, runs each
backend, and merges. `hdllint.<tool>.Rtl` remains first-class for a project
that wants one tool with specific flags; it is the same task with `tools:`
pinned.

Capability is sparse per (tool x family) and is stated once, in BACKENDS.
Asking a tool for a family it does not implement is an ERROR that names the
alternatives -- never a silent empty report. That is the single most likely
way a lint library can lie to a user: reporting "no findings" for a check that
never ran.
"""

import dataclasses as dc
import difflib
import importlib
import logging
import os
import shutil
from typing import Any, Callable, Dict, List, Optional, Tuple

from .finding import Finding

_log = logging.getLogger("hdllint.backends")


FAMILIES = ("Rtl", "Tb", "Style")


@dc.dataclass(frozen=True)
class Backend(object):
    """One lint tool, as this library knows it.

    `runner` is a `module:function` string resolved lazily. A backend module
    may import a tool-specific helper, and importing every backend in order to
    list the registry would make the registry the most fragile part of the
    library.
    """
    id       : str                 # the name used in `tools:`  ("vlt")
    name     : str                 # the tool's own name        ("verilator")
    exe      : str                 # executable looked up on PATH
    families : Tuple[str, ...]     # families it implements
    runner   : str                 # "module:function"
    desc     : str = ""

    # Optional native waiver lowering: "module:function" with signature
    # `lower(waivers, req) -> (extra_args, lowered_waivers)`. A backend that
    # cannot suppress natively simply leaves this None, and every waiver is
    # handled by the post-filter -- which is the default for every backend
    # regardless (see waiver_mode in lint_runner).
    lowerer  : Optional[str] = None

    def available(self, env=None) -> bool:
        return which(self.exe, env) is not None

    def load(self) -> Callable:
        return _resolve(self.runner)

    def load_lowerer(self) -> Optional[Callable]:
        return _resolve(self.lowerer) if self.lowerer else None


def _resolve(spec : str) -> Callable:
    mod_name, _, fn_name = spec.partition(":")
    return getattr(importlib.import_module(mod_name), fn_name)


# The registry. Tools not listed here do not exist as far as `tools:` is
# concerned; adding one is a row here plus a `<tool>_lint.py` runner and a
# `<tool>_parser.py`, and is documented in docs/contributing-a-backend.rst.
BACKENDS : Dict[str, Backend] = {
    "vlt": Backend(
        id="vlt",
        name="verilator",
        exe="verilator",
        families=("Rtl",),
        runner="dv_flow.libhdllint.vlt_lint:run",
        lowerer="dv_flow.libhdllint.vlt_waivers:lower",
        desc="Verilator --lint-only: elaborated RTL checks (width, latch, "
             "unused/undriven, blocking-order races). Synthesis subset -- it "
             "cannot see class-based testbench code, so it implements no Tb."),
}
BACKENDS["spy"] = Backend(
    id="spy",
    name="spyglass",
    exe="sg_shell",
    families=("Rtl", "Style"),
    runner="dv_flow.libhdllint.spy_lint:run",
    lowerer="dv_flow.libhdllint.spy_waivers:lower",
    desc="SpyGlass: design lint, CDC, style.")
BACKENDS["z0i"] = Backend(
    id="z0i",
    name="0-in",
    exe="0in",
    families=("Rtl",),
    runner="dv_flow.libhdllint.z0i_lint:run",
    desc="0-in: formal-based checker/assertion lint.")
BACKENDS["vcs"] = Backend(
    id="vcs",
    name="vc_static",
    exe="vc_static_shell",
    families=("Rtl", "Style"),
    runner="dv_flow.libhdllint.vcs_lint:run",
    lowerer="dv_flow.libhdllint.vcs_waivers:lower",
    desc="VC Static: RTL + style lint.")
BACKENDS["qst"] = Backend(
    id="qst",
    name="questa_lint",
    exe="qverify",
    families=("Rtl",),
    runner="dv_flow.libhdllint.qst_lint:run",
    desc="Questa Lint (AutoCheck): formal-based RTL lint.")
BACKENDS["jg"] = Backend(
    id="jg",
    name="jaspergold",
    exe="jg",
    families=("Rtl",),
    runner="dv_flow.libhdllint.jg_lint:run",
    desc="JasperGold superlint.")


def which(exe : str, env=None) -> Optional[str]:
    """Locate a tool, honouring the task's PATH rather than the process's.

    dv-flow tasks run with an environment the flow can extend (ivpm's
    `path-prepend`, a `std.Env` item), so asking `shutil.which` with the
    ambient PATH can report a tool as missing that the run would have found.
    """
    path = None
    if env is not None:
        try:
            path = env.get("PATH")
        except AttributeError:
            path = None
    return shutil.which(exe, path=path)


def implementing(family : str) -> List[Backend]:
    """Registered backends implementing `family`, in registry order."""
    return [b for b in BACKENDS.values() if family in b.families]


class SelectionError(Exception):
    """A `tools:` list could not be resolved. Raised, not reported-and-skipped:
    continuing would produce a report that looks clean because a tool the user
    asked for never ran."""


@dc.dataclass
class Selection(object):
    selected : List[Backend] = dc.field(default_factory=list)
    skipped  : List[Tuple[Backend, str]] = dc.field(default_factory=list)


def select(tools : List[str], family : str, env=None) -> Selection:
    """Resolve a `tools:` list for `family`.

    An EMPTY list means "whatever is available", which is what makes
    `uses: hdllint.Rtl` work with no configuration at all. An explicitly named
    tool is different in kind: naming it is a statement that the run needs it,
    so a missing executable is an error rather than a skip.

      empty list, tool implements the family, not installed -> skipped (Info)
      named tool, not installed                             -> error
      named tool, does not implement the family             -> error
      unknown tool name                                     -> error, with a
                                                               near-match hint
      nothing left to run                                   -> error
    """
    if family not in FAMILIES:
        raise SelectionError(
            "Unknown lint family '%s'. Known families: %s."
            % (family, ", ".join(FAMILIES)))

    candidates = implementing(family)
    sel = Selection()

    tools = [t for t in (tools or []) if str(t).strip()]

    # Named tools are diagnosed first and individually, even when the family
    # has no backends at all: "vlt does not implement Tb" tells the reader
    # what to change, and the registry-wide message does not.
    if not tools:
        if not candidates:
            raise SelectionError(
                "No registered backend implements the '%s' family. "
                "Registered backends: %s."
                % (family, _capability_table()))
        for b in candidates:
            if b.available(env):
                sel.selected.append(b)
            else:
                sel.skipped.append(
                    (b, "'%s' not found on PATH; skipped" % b.exe))
        if not sel.selected:
            raise SelectionError(
                "No lint tool available for the '%s' family. Install one of: "
                "%s. (Looked for: %s.)"
                % (family,
                   ", ".join("%s (%s)" % (b.id, b.name) for b in candidates),
                   ", ".join(b.exe for b in candidates)))
        return sel

    seen = set()
    for t in tools:
        t = str(t).strip()
        if t in seen:
            continue
        seen.add(t)

        if t not in BACKENDS:
            hint = ""
            near = difflib.get_close_matches(t, list(BACKENDS.keys()), n=1)
            if near:
                hint = " Did you mean '%s'?" % near[0]
            raise SelectionError(
                "Unknown lint tool '%s'. Available: %s.%s"
                % (t, ", ".join(sorted(BACKENDS.keys())), hint))

        b = BACKENDS[t]
        if family not in b.families:
            alts = [c.id for c in candidates]
            raise SelectionError(
                "Lint tool '%s' (%s) does not implement the '%s' family; it "
                "implements: %s. Tools implementing '%s': %s."
                % (t, b.name, family, ", ".join(b.families),
                   family, ", ".join(alts) if alts else "(none)"))

        if not b.available(env):
            raise SelectionError(
                "Lint tool '%s' was requested but its executable '%s' was not "
                "found on PATH. Install it, or drop it from `tools:` to let "
                "the available tools be selected automatically."
                % (t, b.exe))

        sel.selected.append(b)

    return sel


def _capability_table() -> str:
    return "; ".join(
        "%s -> %s" % (b.id, ", ".join(b.families)) for b in BACKENDS.values())


# ---------------------------------------------------------------------------
# What a backend is handed, and what it gives back
# ---------------------------------------------------------------------------

@dc.dataclass
class ToolRequest(object):
    """Everything a backend needs, already normalized.

    Backends receive this rather than the dv-flow task input, so a backend can
    be exercised from a unit test without building a graph.
    """
    family   : str
    backend  : Backend
    files    : List[str] = dc.field(default_factory=list)
    incdirs  : List[str] = dc.field(default_factory=list)
    defines  : List[str] = dc.field(default_factory=list)
    top      : List[str] = dc.field(default_factory=list)
    args     : List[str] = dc.field(default_factory=list)
    profile  : str = "default"
    rundir   : str = ""     # the backend's own directory, already created
    root     : str = ""     # project root, for relativizing paths
    env      : Any = None
    exe      : str = ""


@dc.dataclass
class ToolRun(object):
    """What one backend did, for the report's `runs:` section.

    Recording the command and the log path is not decoration: when a parser
    produces a surprising finding, the first question is always what was
    actually run, and the second is what the tool actually said.
    """
    tool     : str
    name     : str
    cmd      : List[str] = dc.field(default_factory=list)
    status   : int = 0
    duration : float = 0.0
    log      : str = ""
    version  : str = ""
    findings : int = 0
    lowered  : int = 0      # waivers this tool now suppresses natively
    skipped  : str = ""     # non-empty when the tool did not run
    error    : str = ""     # non-empty when the tool failed to run at all

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "tool": self.tool,
            "name": self.name,
            "status": self.status,
            "duration": round(self.duration, 3),
            "findings": self.findings,
        }
        if self.lowered:
            d["waivers_lowered"] = self.lowered
        if self.cmd:
            d["cmd"] = list(self.cmd)
        if self.log:
            d["log"] = self.log
        if self.version:
            d["version"] = self.version
        if self.skipped:
            d["skipped"] = self.skipped
        if self.error:
            d["error"] = self.error
        return d
