import os

import pytest

from dv_flow.mgr.task_data import SeverityE
from dv_flow.libhdllint.finding import Finding
from dv_flow.libhdllint import waiver as W


def mkf(rule="WIDTHTRUNC", path="rtl/a.v", line=10, tool="vlt",
        tool_name="verilator", msg="something"):
    return Finding(tool=tool, tool_name=tool_name, rule=rule,
                   severity=SeverityE.Warning, msg=msg, path=path, line=line)


def test_rule_glob():
    w = W.load_waivers([{"rule": "WIDTH*", "reason": "r"}], "t")
    assert W.apply_waivers([mkf(rule="WIDTHTRUNC"), mkf(rule="LATCH")], w) == 1


def test_path_glob_crosses_directory_separators():
    """`*` crossing `/` is looser than a shell glob, and is the documented
    behaviour: `rtl/*` matching `rtl/a/b.v` is what people expect from a
    waiver file, and the strict alternative fails silently."""
    w = W.load_waivers([{"rule": "*", "path": "rtl/*", "reason": "r"}], "t")
    assert W.apply_waivers([mkf(path="rtl/sub/deep/a.v")], w) == 1


def test_path_matches_bare_basename():
    w = W.load_waivers([{"rule": "*", "path": "a.v", "reason": "r"}], "t")
    assert W.apply_waivers([mkf(path="rtl/sub/a.v")], w) == 1


def test_tool_may_be_the_id_or_the_tool_name():
    for spelling in ("vlt", "verilator"):
        w = W.load_waivers([{"rule": "*", "tool": spelling, "reason": "r"}], "t")
        assert W.apply_waivers([mkf()], w) == 1


def test_tool_mismatch_does_not_waive():
    w = W.load_waivers([{"rule": "*", "tool": "vbl", "reason": "r"}], "t")
    assert W.apply_waivers([mkf()], w) == 0


def test_line_pins_the_waiver():
    w = W.load_waivers([{"rule": "*", "line": 10, "reason": "r"}], "t")
    assert W.apply_waivers([mkf(line=10), mkf(line=11)], w) == 1


def test_reason_is_recorded_on_the_finding():
    w = W.load_waivers([{"rule": "*", "reason": "third-party DUT"}], "t")
    f = mkf()
    W.apply_waivers([f], w)
    assert f.waived == "third-party DUT"
    assert f.suppressed


def test_first_match_wins():
    w = W.load_waivers([
        {"rule": "*", "reason": "first"},
        {"rule": "*", "reason": "second"},
    ], "t")
    f = mkf()
    W.apply_waivers([f], w)
    assert f.waived == "first"
    assert w[1].hits == 0


def test_missing_reason_is_a_load_error():
    """A waiver without a reason is the one thing that is always wrong: the
    reason is the only part still useful once the author has moved on."""
    with pytest.raises(W.WaiverError) as e:
        W.load_waivers([{"rule": "WIDTHTRUNC"}], "t")
    assert "reason" in str(e.value)


def test_blank_reason_is_a_load_error():
    with pytest.raises(W.WaiverError):
        W.load_waivers([{"rule": "X", "reason": "   "}], "t")


def test_unknown_field_is_a_load_error():
    """A typo'd field name means a waiver that silently matches far more than
    intended (`paht:` -> no path constraint at all)."""
    with pytest.raises(W.WaiverError) as e:
        W.load_waivers([{"rule": "X", "paht": "y", "reason": "r"}], "t")
    assert "paht" in str(e.value)


def test_non_integer_line_is_a_load_error():
    with pytest.raises(W.WaiverError):
        W.load_waivers([{"rule": "X", "line": "ten", "reason": "r"}], "t")


def test_unused_waivers_are_reported():
    w = W.load_waivers([
        {"rule": "LATCH", "reason": "used"},
        {"rule": "GONE", "reason": "stale"},
    ], "t")
    W.apply_waivers([mkf(rule="LATCH")], w)
    unused = W.unused_waivers(w)
    assert [u.reason for u in unused] == ["stale"]


def test_load_from_file(tmpdir):
    p = os.path.join(str(tmpdir), "waivers.yaml")
    with open(p, "w") as fp:
        fp.write("waivers:\n- rule: WIDTHTRUNC\n  reason: legacy\n")
    w = W.load_waiver_file(p)
    assert len(w) == 1 and w[0].reason == "legacy"
    assert w[0].src.startswith(p)


def test_load_from_file_accepts_a_bare_list(tmpdir):
    p = os.path.join(str(tmpdir), "waivers.yaml")
    with open(p, "w") as fp:
        fp.write("- rule: WIDTHTRUNC\n  reason: legacy\n")
    assert len(W.load_waiver_file(p)) == 1


def test_missing_file_is_an_error():
    with pytest.raises(W.WaiverError):
        W.load_waiver_file("/nonexistent/waivers.yaml")


def test_empty_file_is_no_waivers(tmpdir):
    p = os.path.join(str(tmpdir), "waivers.yaml")
    open(p, "w").close()
    assert W.load_waiver_file(p) == []
