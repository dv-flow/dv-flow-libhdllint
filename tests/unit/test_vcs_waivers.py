#****************************************************************************
#* test_vcs_waivers.py
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
"""Lowering the one waiver format into VC Static's native `.swl` syntax.

The invariant under test throughout: lowering is PARTIAL, and whatever is not
lowered is still returned unclaimed so the post-filter handles it. A waiver
must never stop being in force because the mode changed.
"""

import os

import pytest

from dv_flow.libhdllint import vcs_waivers as V
from dv_flow.libhdllint.backends import BACKENDS, ToolRequest
from dv_flow.libhdllint.waiver import load_waivers


def w(**kw):
    kw.setdefault("reason", "because")
    return load_waivers([kw], "t")[0]


def req(tmpdir, root="/proj"):
    return ToolRequest(family="Rtl", backend=BACKENDS["vcs"],
                       rundir=str(tmpdir), root=root, exe="vc_static_shell")


# ------------------------------------------------------------ what it emits

def test_config_uses_waive_directive():
    text = V.config_text([w(rule="LINT-1")])
    waive_lines = [l for l in text.splitlines() if l.startswith("waive")]
    assert len(waive_lines) == 1
    assert "-rule LINT-1" in waive_lines[0]


def test_rule_only_waiver_has_no_file():
    line = [l for l in V.config_text([w(rule="LINT-1")]).splitlines()
            if l.startswith("waive")][0]
    assert "-file" not in line


def test_path_is_anchored_at_the_project_root():
    text = V.config_text([w(rule="LINT-1", path="rtl/*")], root="/proj")
    assert "-file /proj/rtl/*" in text


def test_absolute_path_is_passed_through():
    text = V.config_text([w(rule="LINT-1", path="/opt/ip/*")], root="/proj")
    assert "-file /opt/ip/*" in text


def test_reason_travels_into_the_generated_file():
    text = V.config_text([w(rule="LINT-1", reason="tied off by design")])
    assert '"tied off by design"' in text


# ----------------------------------------------- what it declines to lower

@pytest.mark.parametrize("kw,why", [
    ({"rule": "LINT*"},                    "a glob in rule"),
    ({"rule": ""},                         "no rule at all"),
    ({"rule": "LINT-1", "tool": "vlt"},    "scoped to another tool"),
    ({"rule": "LINT-1", "path": "a.v"},    "a bare basename path"),
])
def test_unlowerable_waivers_are_left_to_the_post_filter(kw, why, tmpdir):
    waiver = w(**kw)
    args, lowered = V.lower([waiver], req(tmpdir))
    assert lowered == [], why
    assert args == []


def test_a_waiver_for_this_tool_by_either_spelling_is_lowered(tmpdir):
    for spelling in ("", "vcs", "vc_static"):
        _, lowered = V.lower([w(rule="LINT-1", tool=spelling)], req(tmpdir))
        assert len(lowered) == 1, spelling


def test_partial_lowering_claims_only_what_it_can_express(tmpdir):
    """The invariant: the unclaimed remainder is what the post-filter still
    applies, so `native` never silently drops a waiver."""
    lowerable = w(rule="LINT-1", path="rtl/a.v")
    not_lowerable = w(rule="LINT*")
    args, lowered = V.lower([lowerable, not_lowerable], req(tmpdir))

    assert lowered == [lowerable]
    assert len(args) == 1 and os.path.isfile(args[0])


def test_the_config_file_only_contains_lowered_waivers(tmpdir):
    args, _ = V.lower([w(rule="LINT-1"), w(rule="LINT*")], req(tmpdir))
    text = open(args[0]).read()
    assert "LINT-1" in text
    assert "LINT*" not in text


def test_nothing_lowerable_writes_no_file_and_adds_no_args(tmpdir):
    """The command line must stay exactly what it would have been."""
    args, lowered = V.lower([w(rule="LINT*")], req(tmpdir))
    assert args == [] and lowered == []
    assert not os.path.isfile(os.path.join(str(tmpdir), V.CONFIG_FILE))


def test_lower_writes_into_the_backend_rundir(tmpdir):
    args, _ = V.lower([w(rule="LINT-1")], req(tmpdir))
    assert args[0] == os.path.join(str(tmpdir), V.CONFIG_FILE)


def test_the_registry_exposes_the_lowerer():
    assert callable(BACKENDS["vcs"].load_lowerer())
