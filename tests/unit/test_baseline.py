import json
import os

import pytest

from dv_flow.mgr.task_data import SeverityE
from dv_flow.libhdllint.finding import Finding
from dv_flow.libhdllint import baseline as B


def mkf(rule="WIDTHTRUNC", path="rtl/a.v", line=10, msg="expects 4 bits"):
    return Finding(tool="vlt", tool_name="verilator", rule=rule,
                   severity=SeverityE.Warning, msg=msg, path=path, line=line)


def established(tmpdir, findings, name="baseline.json"):
    p = os.path.join(str(tmpdir), name)
    B.write_baseline(p, findings, ["vlt"])
    return B.load_baseline(p)


def test_missing_file_is_an_empty_baseline():
    b = B.load_baseline("/nonexistent/baseline.json")
    assert not b.present and len(b) == 0


def test_roundtrip_marks_the_same_findings(tmpdir):
    findings = [mkf(), mkf(rule="LATCH", path="rtl/b.v", line=4)]
    b = established(tmpdir, findings)

    again = [mkf(), mkf(rule="LATCH", path="rtl/b.v", line=4)]
    n, stale = B.apply_baseline(again, b)
    assert n == 2 and stale == []
    assert all(f.baseline for f in again)


def test_baseline_survives_an_edit_above_the_finding(tmpdir):
    """The point of the location-tolerant key. Inserting a line above a
    finding moves it; a line-keyed baseline would call it new."""
    b = established(tmpdir, [mkf(line=10)])

    moved = [mkf(line=47)]
    n, stale = B.apply_baseline(moved, b)
    assert n == 1 and stale == []


def test_numbers_in_the_message_are_normalized(tmpdir):
    """Widths and indices quoted in a message move without the finding
    changing."""
    b = established(tmpdir, [mkf(msg="expects 4 bits, RHS generates 8 bits")])
    n, _ = B.apply_baseline(
        [mkf(msg="expects 5 bits, RHS generates 9 bits")], b)
    assert n == 1


def test_a_different_rule_is_new(tmpdir):
    b = established(tmpdir, [mkf(rule="WIDTHTRUNC")])
    n, stale = B.apply_baseline([mkf(rule="LATCH")], b)
    assert n == 0
    assert len(stale) == 1


def test_a_different_file_is_new(tmpdir):
    b = established(tmpdir, [mkf(path="rtl/a.v")])
    n, _ = B.apply_baseline([mkf(path="rtl/b.v")], b)
    assert n == 0


def test_matching_is_count_aware(tmpdir):
    """Three baselined and five today is two new findings. A set-membership
    test would report zero and hide the regression."""
    b = established(tmpdir, [mkf(line=1), mkf(line=2), mkf(line=3)])

    today = [mkf(line=i) for i in range(5)]
    n, stale = B.apply_baseline(today, b)
    assert n == 3
    assert sum(1 for f in today if not f.baseline) == 2
    assert stale == []


def test_fewer_findings_than_baselined_is_reported_as_stale(tmpdir):
    """This is what lets a team watch the baseline shrink -- the only thing
    that makes it a transition rather than a permanent amnesty."""
    b = established(tmpdir, [mkf(line=1), mkf(line=2), mkf(line=3)])

    n, stale = B.apply_baseline([mkf(line=1)], b)
    assert n == 1
    assert sum(int(e["count"]) for e in stale) == 2


def test_waived_findings_are_not_baselined(tmpdir):
    """A finding cannot be both, and the waiver carries a human reason."""
    b = established(tmpdir, [mkf()])
    f = mkf()
    f.waived = "third-party"
    n, _ = B.apply_baseline([f], b)
    assert n == 0 and f.baseline is False


def test_waived_findings_are_not_written_to_the_baseline(tmpdir):
    """Otherwise deleting a waiver silently re-suppresses via the baseline."""
    waived = mkf(rule="LATCH")
    waived.waived = "reason"
    doc = B.baseline_doc([mkf(), waived], ["vlt"])
    assert doc["total"] == 1
    assert all(e["rule"] != "LATCH" for e in doc["entries"])


def test_unreadable_baseline_is_an_error_not_an_empty_one(tmpdir):
    """An unreadable baseline silently becoming "everything is new" fails a
    CI job for the wrong reason."""
    p = os.path.join(str(tmpdir), "baseline.json")
    with open(p, "w") as fp:
        fp.write("{not json")
    with pytest.raises(B.BaselineError):
        B.load_baseline(p)


def test_wrong_version_is_an_error(tmpdir):
    p = os.path.join(str(tmpdir), "baseline.json")
    with open(p, "w") as fp:
        json.dump({"version": 99, "entries": []}, fp)
    with pytest.raises(B.BaselineError) as e:
        B.load_baseline(p)
    assert "update_baseline" in str(e.value)


def test_baseline_file_is_stable_across_writes(tmpdir):
    """A baseline whose byte order moves run to run produces a spurious diff
    in every pull request that touches lint."""
    a = os.path.join(str(tmpdir), "a.json")
    b = os.path.join(str(tmpdir), "b.json")
    f1 = [mkf(rule="B"), mkf(rule="A"), mkf(rule="C")]
    f2 = [mkf(rule="C"), mkf(rule="A"), mkf(rule="B")]
    B.write_baseline(a, f1, ["vlt"])
    B.write_baseline(b, f2, ["vlt"])
    assert open(a).read() == open(b).read()
