"""Lowering the one waiver format into SpyGlass native `.swl` syntax.

The invariant under test throughout: lowering is PARTIAL, and whatever is not
lowered is still returned unclaimed so the post-filter handles it. A waiver
must never stop being in force because the mode changed.
"""

import os

import pytest

from dv_flow.libhdllint import spy_waivers as S
from dv_flow.libhdllint.backends import BACKENDS, ToolRequest
from dv_flow.libhdllint.waiver import load_waivers


def w(**kw):
    kw.setdefault("reason", "because")
    return load_waivers([kw], "t")[0]


def req(tmpdir, root="/proj"):
    return ToolRequest(family="Rtl", backend=BACKENDS["spy"],
                       rundir=str(tmpdir), root=root, exe="sg_shell")


# ------------------------------------------------------------ what it emits

def test_config_has_the_spyglass_header():
    text = S.config_text([w(rule="W_REDF")])
    assert text.splitlines()[0] == "# SpyGlass waiver file"


def test_rule_only_waiver_lowers_to_a_global_waive():
    line = [l for l in S.config_text([w(rule="W_REDF")]).splitlines()
            if l.startswith("waive")][0]
    assert "waive -rule W_REDF" in line
    assert "-file" not in line


def test_path_is_anchored_at_the_project_root():
    text = S.config_text([w(rule="W_REDF", path="rtl/*")], root="/proj")
    assert '-file "/proj/rtl/*"' in text


def test_absolute_path_is_passed_through():
    text = S.config_text([w(rule="W_REDF", path="/opt/ip/*")], root="/proj")
    assert '-file "/opt/ip/*"' in text


def test_line_lowers_to_line_arg():
    text = S.config_text([w(rule="W_REDF", path="rtl/a.v", line=42)],
                         root="/proj")
    assert "-line 42" in text


def test_reason_travels_into_the_generated_file():
    text = S.config_text([w(rule="W_REDF", reason="tied off by design")])
    assert '-comment "tied off by design"' in text


# ----------------------------------------------- what it declines to lower

@pytest.mark.parametrize("kw,why", [
    ({"rule": "WIDTH*"},                  "a glob in rule"),
    ({"rule": ""},                        "no rule at all"),
    ({"rule": "W_REDF", "tool": "vlt"},   "scoped to another tool"),
    ({"rule": "W_REDF", "path": "a.v"},   "a bare basename path"),
])
def test_unlowerable_waivers_are_left_to_the_post_filter(kw, why, tmpdir):
    waiver = w(**kw)
    args, lowered = S.lower([waiver], req(tmpdir))
    assert lowered == [], why
    assert args == []


def test_a_waiver_for_this_tool_by_either_spelling_is_lowered(tmpdir):
    for spelling in ("", "spy", "spyglass"):
        _, lowered = S.lower([w(rule="W_REDF", tool=spelling)], req(tmpdir))
        assert len(lowered) == 1, spelling


def test_partial_lowering_claims_only_what_it_can_express(tmpdir):
    """The invariant: the unclaimed remainder is what the post-filter still
    applies, so `native` never silently drops a waiver."""
    lowerable = w(rule="W_REDF", path="rtl/a.v")
    not_lowerable = w(rule="WIDTH*")
    args, lowered = S.lower([lowerable, not_lowerable], req(tmpdir))

    assert lowered == [lowerable]
    assert len(args) == 1 and os.path.isfile(args[0])


def test_the_config_file_only_contains_lowered_waivers(tmpdir):
    args, _ = S.lower([w(rule="W_REDF"), w(rule="WIDTH*")], req(tmpdir))
    text = open(args[0]).read()
    assert "W_REDF" in text
    assert "WIDTH*" not in text


def test_nothing_lowerable_writes_no_file_and_adds_no_args(tmpdir):
    """The command line must stay exactly what it would have been."""
    args, lowered = S.lower([w(rule="WIDTH*")], req(tmpdir))
    assert args == [] and lowered == []
    assert not os.path.isfile(os.path.join(str(tmpdir), S.CONFIG_FILE))


def test_lower_writes_into_the_backend_rundir(tmpdir):
    args, _ = S.lower([w(rule="W_REDF")], req(tmpdir))
    assert args[0] == os.path.join(str(tmpdir), S.CONFIG_FILE)


def test_the_registry_exposes_the_lowerer():
    assert callable(BACKENDS["spy"].load_lowerer())
