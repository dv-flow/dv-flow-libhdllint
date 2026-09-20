"""Lowering the one waiver format into Verilator's native `.vlt` syntax.

The invariant under test throughout: lowering is PARTIAL, and whatever is not
lowered is still returned unclaimed so the post-filter handles it. A waiver
must never stop being in force because the mode changed.
"""

import os

import pytest

from dv_flow.libhdllint import vlt_waivers as V
from dv_flow.libhdllint.backends import BACKENDS, ToolRequest
from dv_flow.libhdllint.waiver import load_waivers


def w(**kw):
    kw.setdefault("reason", "because")
    return load_waivers([kw], "t")[0]


def req(tmpdir, root="/proj"):
    return ToolRequest(family="Rtl", backend=BACKENDS["vlt"],
                       rundir=str(tmpdir), root=root, exe="verilator")


# ------------------------------------------------------------ what it emits

def test_config_has_the_verilator_header():
    text = V.config_text([w(rule="LATCH")])
    assert text.splitlines()[0] == "`verilator_config"


def test_rule_only_waiver_lowers_to_a_global_lint_off():
    line = [l for l in V.config_text([w(rule="LATCH")]).splitlines()
            if l.startswith("lint_off")][0]
    assert line.startswith("lint_off -rule LATCH")
    assert "-file" not in line


def test_path_is_anchored_at_the_project_root():
    """Verilator matches the filename as it appears on ITS command line, which
    is absolute; waiver paths are relative to the project root. A bare
    `rtl/*` would match nothing at all."""
    text = V.config_text([w(rule="LATCH", path="rtl/*")], root="/proj")
    assert '-file "/proj/rtl/*"' in text


def test_absolute_path_is_passed_through():
    text = V.config_text([w(rule="LATCH", path="/opt/ip/*")], root="/proj")
    assert '-file "/opt/ip/*"' in text


def test_line_lowers_to_lines():
    text = V.config_text([w(rule="LATCH", path="rtl/a.v", line=142)],
                         root="/proj")
    assert "-lines 142" in text


def test_reason_travels_into_the_generated_file():
    """Someone reading the generated config should not have to go find the
    source waiver to learn why a check is off."""
    text = V.config_text([w(rule="LATCH", reason="tied off by design")])
    assert "// tied off by design" in text


# ----------------------------------------------- what it declines to lower

@pytest.mark.parametrize("kw,why", [
    ({"rule": "WIDTH*"},                 "a glob in rule"),
    ({"rule": ""},                       "no rule at all"),
    ({"rule": "LATCH", "tool": "vbl"},   "scoped to another tool"),
    ({"rule": "LATCH", "path": "a.v"},   "a bare basename path"),
])
def test_unlowerable_waivers_are_left_to_the_post_filter(kw, why, tmpdir):
    waiver = w(**kw)
    args, lowered = V.lower([waiver], req(tmpdir))
    assert lowered == [], why
    assert args == []


def test_a_waiver_for_this_tool_by_either_spelling_is_lowered(tmpdir):
    for spelling in ("", "vlt", "verilator"):
        _, lowered = V.lower([w(rule="LATCH", tool=spelling)], req(tmpdir))
        assert len(lowered) == 1, spelling


def test_partial_lowering_claims_only_what_it_can_express(tmpdir):
    """The invariant: the unclaimed remainder is what the post-filter still
    applies, so `native` never silently drops a waiver."""
    lowerable = w(rule="LATCH", path="rtl/a.v")
    not_lowerable = w(rule="WIDTH*")
    args, lowered = V.lower([lowerable, not_lowerable], req(tmpdir))

    assert lowered == [lowerable]
    assert len(args) == 1 and os.path.isfile(args[0])


def test_the_config_file_only_contains_lowered_waivers(tmpdir):
    args, _ = V.lower([w(rule="LATCH"), w(rule="WIDTH*")], req(tmpdir))
    text = open(args[0]).read()
    assert "LATCH" in text
    assert "WIDTH*" not in text


def test_nothing_lowerable_writes_no_file_and_adds_no_args(tmpdir):
    """The command line must stay exactly what it would have been."""
    args, lowered = V.lower([w(rule="WIDTH*")], req(tmpdir))
    assert args == [] and lowered == []
    assert not os.path.isfile(os.path.join(str(tmpdir), V.CONFIG_FILE))


def test_lower_writes_into_the_backend_rundir(tmpdir):
    args, _ = V.lower([w(rule="LATCH")], req(tmpdir))
    assert args[0] == os.path.join(str(tmpdir), V.CONFIG_FILE)


def test_the_registry_exposes_the_lowerer():
    assert callable(BACKENDS["vlt"].load_lowerer())
