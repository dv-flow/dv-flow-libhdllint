import pytest

from dv_flow.mgr.task_data import SeverityE
from dv_flow.libhdllint.finding import Finding
from dv_flow.libhdllint import gate as G
from dv_flow.libhdllint import report as R


def mkf(sev, rule="R", line=1):
    return Finding(tool="vlt", tool_name="verilator", rule=rule, severity=sev,
                   msg="m", path="rtl/a.v", line=line)


ONE_OF_EACH = [
    mkf(SeverityE.Error, "E"),
    mkf(SeverityE.Warning, "W", 2),
    mkf(SeverityE.Info, "I", 3),
]


@pytest.mark.parametrize("fail_on,expected", [
    ("none", 0),
    ("error", 1),
    ("warning", 2),
    ("any", 3),
])
def test_fail_on_thresholds(fail_on, expected):
    status, n = G.evaluate(ONE_OF_EACH, fail_on)
    assert n == expected
    assert status == (1 if expected else 0)


def test_suppressed_findings_never_gate():
    """Waived and baselined findings have already been accepted; counting them
    would make `fail_on:` a function of history rather than of this change."""
    waived = mkf(SeverityE.Error, "A")
    waived.waived = "reason"
    based = mkf(SeverityE.Error, "B", 2)
    based.baseline = True

    assert G.evaluate([waived, based], "any") == (0, 0)


def test_unknown_fail_on_is_an_error():
    with pytest.raises(G.GateError) as e:
        G.gating_findings([], "sometimes")
    assert "none, error, warning, any" in str(e.value)


def test_headline_states_what_is_being_ignored_even_on_a_pass():
    """A bare "lint passed" hides 137 accepted findings. The headline always
    says what it is not reporting."""
    waived = mkf(SeverityE.Error, "A")
    waived.waived = "r"
    based = mkf(SeverityE.Error, "B", 2)
    based.baseline = True

    s = R.summarize([waived, based], [], 0, ["vlt"], [])
    line = G.headline(s, "error")
    assert "0 new findings" in line
    assert "1 baselined" in line and "1 waived" in line


def test_headline_breaks_new_findings_down_by_severity():
    s = R.summarize(ONE_OF_EACH, [], 1, ["vlt"], [])
    line = G.headline(s, "error")
    assert "3 new findings" in line
    assert "1 error" in line and "1 warning" in line and "1 info" in line
    assert "[fail_on=error]" in line


def test_headline_mentions_dropped_duplicates():
    s = R.summarize([], [mkf(SeverityE.Warning)], 0, ["vlt"], [])
    assert "1 duplicate" in G.headline(s, "error")
