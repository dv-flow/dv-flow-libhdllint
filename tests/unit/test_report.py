import json
import os

import pytest

from dv_flow.mgr.task_data import SeverityE
from dv_flow.libhdllint.backends import ToolRun
from dv_flow.libhdllint.finding import Finding
from dv_flow.libhdllint import gate as G
from dv_flow.libhdllint import report as R


def mkf(tool="vlt", name="verilator", rule="WIDTHTRUNC", path="rtl/a.v",
        line=10, msg="expects 4 bits", sev=SeverityE.Warning):
    return Finding(tool=tool, tool_name=name, rule=rule, severity=sev,
                   msg=msg, path=path, line=line)


def runs(*tools):
    return [ToolRun(tool=t, name=t, version="1.2.3") for t in tools]


# --------------------------------------------------------------------- dedup

def test_dedup_collapses_the_same_finding_from_two_tools():
    kept, dropped = R.dedup([mkf(tool="vlt"), mkf(tool="slang", name="slang")])
    assert len(kept) == 1 and len(dropped) == 1
    assert kept[0].tool == "slang"          # alphabetical, so it is stable
    assert dropped[0].dup_of == "slang"


def test_dedup_is_order_independent():
    a, _ = R.dedup([mkf(tool="vlt"), mkf(tool="slang", name="slang")])
    b, _ = R.dedup([mkf(tool="slang", name="slang"), mkf(tool="vlt")])
    assert a[0].tool == b[0].tool


def test_dedup_never_collapses_two_findings_from_the_same_tool():
    """The key normalizes numbers out of the message, so two different width
    mismatches on one line share a key while being two distinct defects. A
    tool-blind dedup turned a real 97-finding Verilator run into 61."""
    a = mkf(msg="expects 28 bits, RHS generates 1 bits")
    b = mkf(msg="expects 9 bits, RHS generates 1 bits")
    kept, dropped = R.dedup([a, b])
    assert a.dedup_key() == b.dedup_key()      # same key...
    assert len(kept) == 2 and dropped == []    # ...and still two findings


def test_dedup_keeps_every_copy_from_the_winning_tool():
    kept, dropped = R.dedup([
        mkf(tool="slang", name="slang", msg="expects 4 bits"),
        mkf(tool="slang", name="slang", msg="expects 8 bits"),
        mkf(tool="vlt", msg="expects 4 bits"),
    ])
    assert sorted(f.tool for f in kept) == ["slang", "slang"]
    assert [f.tool for f in dropped] == ["vlt"]


def test_dedup_keeps_findings_at_different_locations():
    kept, dropped = R.dedup([mkf(line=1), mkf(line=2)])
    assert len(kept) == 2 and dropped == []


def test_dedup_never_merges_findings_with_no_location():
    """Without a file there is no evidence two tools mean the same defect."""
    kept, dropped = R.dedup([
        mkf(tool="vlt", path="", line=-1, msg="could not open file"),
        mkf(tool="slang", name="slang", path="", line=-1, msg="could not open file"),
    ])
    assert len(kept) == 2 and dropped == []


def test_dedup_can_be_turned_off():
    kept, dropped = R.dedup([mkf(tool="vlt"), mkf(tool="slang")], enabled=False)
    assert len(kept) == 2 and dropped == []


def test_dropped_duplicates_are_returned_for_the_record():
    """Dedup is a heuristic; one that leaves no trace is not auditable."""
    _, dropped = R.dedup([mkf(tool="vlt"), mkf(tool="slang", name="slang")])
    assert dropped[0].to_dict()["dup_of"] == "slang"


# ------------------------------------------------------------------- summary

def test_summary_counts_severities_over_new_findings_only():
    waived = mkf(rule="A", line=1)
    waived.waived = "reason"
    based = mkf(rule="B", line=2, sev=SeverityE.Error)
    based.baseline = True
    findings = [waived, based, mkf(rule="C", line=3, sev=SeverityE.Error),
                mkf(rule="D", line=4)]

    s = R.summarize(findings, [], 1, ["vlt"], [])
    assert (s.total, s.new, s.waived, s.baselined) == (4, 2, 1, 1)
    assert (s.errors, s.warnings, s.infos) == (1, 1, 0)


def test_summary_passed_follows_the_gating_count():
    assert R.summarize([], [], 0, [], []).passed is True
    assert R.summarize([], [], 3, [], []).passed is False


# ----------------------------------------------------------------- lint.json

def test_json_report_contains_suppressed_findings(tmpdir):
    """lint.json is the authoritative record: it is the only rendering that
    has everything, including what was suppressed and why."""
    waived = mkf(rule="A")
    waived.waived = "third-party DUT"
    s = R.summarize([waived], [], 0, ["vlt"], [])
    doc = R.report_doc([waived], [], s, runs("vlt"), "error", [], [])

    p = os.path.join(str(tmpdir), "lint.json")
    R.write_json(p, doc)
    back = json.load(open(p))

    assert back["findings"][0]["waived"] == "third-party DUT"
    assert back["summary"]["waived"] == 1
    assert back["fail_on"] == "error"
    assert back["runs"][0]["tool"] == "vlt"


def test_json_report_records_what_each_tool_ran(tmpdir):
    r = ToolRun(tool="vlt", name="verilator", cmd=["verilator", "--lint-only"],
                status=1, log="/rundir/vlt/lint.log", version="5.052")
    doc = R.report_doc([], [], R.summarize([], [], 0, ["vlt"], []),
                       [r], "error", [], [])
    assert doc["runs"][0]["cmd"] == ["verilator", "--lint-only"]
    assert doc["runs"][0]["log"] == "/rundir/vlt/lint.log"
    assert doc["runs"][0]["version"] == "5.052"


# --------------------------------------------------------------------- SARIF

def test_sarif_shape():
    doc = R.sarif_doc([mkf()], runs("vlt"))
    assert doc["version"] == "2.1.0"
    assert len(doc["runs"]) == 1

    run = doc["runs"][0]
    driver = run["tool"]["driver"]
    assert driver["name"] == "verilator"
    assert driver["version"] == "1.2.3"
    assert driver["informationUri"] == "https://verilator.org"
    assert driver["rules"][0]["id"] == "WIDTHTRUNC"

    result = run["results"][0]
    assert result["ruleId"] == "WIDTHTRUNC"
    assert result["ruleIndex"] == 0
    assert result["level"] == "warning"
    loc = result["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "rtl/a.v"
    assert loc["region"]["startLine"] == 10


def test_sarif_one_run_per_tool():
    doc = R.sarif_doc([mkf(tool="vlt"), mkf(tool="vbl", name="verible", line=20)],
                      runs("vlt", "vbl"))
    assert sorted(r["tool"]["driver"]["name"] for r in doc["runs"]) \
        == ["verible", "verilator"]


def test_sarif_severity_mapping():
    levels = {}
    for sev, rule in ((SeverityE.Error, "E"), (SeverityE.Warning, "W"),
                      (SeverityE.Info, "I")):
        doc = R.sarif_doc([mkf(rule=rule, sev=sev)], runs("vlt"))
        levels[rule] = doc["runs"][0]["results"][0]["level"]
    # SARIF has no "info"; "note" is its equivalent.
    assert levels == {"E": "error", "W": "warning", "I": "note"}


def test_sarif_emits_suppressed_findings_as_suppressions():
    """SARIF's own way of saying "known and accepted". Dropping them instead
    would mean the waiver reasons live nowhere a reviewer can see them."""
    waived = mkf(rule="A")
    waived.waived = "third-party DUT"
    based = mkf(rule="B", line=20)
    based.baseline = True

    doc = R.sarif_doc([waived, based], runs("vlt"))
    results = {r["ruleId"]: r for r in doc["runs"][0]["results"]}
    assert results["A"]["suppressions"][0]["justification"] == "third-party DUT"
    assert "baseline" in results["B"]["suppressions"][0]["justification"].lower()


def test_sarif_new_findings_have_no_suppressions():
    doc = R.sarif_doc([mkf()], runs("vlt"))
    assert "suppressions" not in doc["runs"][0]["results"][0]


def test_sarif_rules_are_not_duplicated():
    doc = R.sarif_doc([mkf(line=1), mkf(line=2)], runs("vlt"))
    assert len(doc["runs"][0]["tool"]["driver"]["rules"]) == 1


def test_sarif_finding_without_a_rule_omits_ruleid():
    doc = R.sarif_doc([mkf(rule="", msg="syntax error")], runs("vlt"))
    result = doc["runs"][0]["results"][0]
    assert "ruleId" not in result
    assert result["message"]["text"] == "syntax error"


def test_sarif_finding_without_a_location_omits_locations():
    doc = R.sarif_doc([mkf(path="", line=-1)], runs("vlt"))
    assert "locations" not in doc["runs"][0]["results"][0]


# ---------------------------------------------------------------------- CTRF

def ctrf_of(findings, fail_on="error", tool_runs=None):
    gating = G.gating_findings(findings, fail_on)
    s = R.summarize(findings, [], len(gating), ["vlt"], [])
    return R.ctrf_doc(findings, s, tool_runs or runs("vlt"), gating,
                      1000, 2000, report_id="fixed")


def test_ctrf_shape():
    doc = ctrf_of([mkf(sev=SeverityE.Error)])
    assert doc["reportFormat"] == "CTRF"
    assert doc["specVersion"] == R.CTRF_SPEC_VERSION
    assert doc["results"]["tool"]["name"] == "hdllint"
    assert doc["results"]["summary"]["start"] == 1000
    assert doc["results"]["summary"]["stop"] == 2000


def test_ctrf_summary_counts_match_the_test_list():
    doc = ctrf_of([mkf(sev=SeverityE.Error), mkf(line=20)])
    s = doc["results"]["summary"]
    tests = doc["results"]["tests"]
    assert s["tests"] == len(tests)
    assert s["failed"] == sum(1 for t in tests if t["status"] == "failed")
    assert s["skipped"] == sum(1 for t in tests if t["status"] == "skipped")
    assert s["other"] == sum(1 for t in tests if t["status"] == "other")
    assert s["passed"] == sum(1 for t in tests if t["status"] == "passed")


def test_ctrf_gating_finding_is_failed_and_carries_its_location():
    doc = ctrf_of([mkf(sev=SeverityE.Error)])
    t = [t for t in doc["results"]["tests"] if t["status"] == "failed"][0]
    assert t["name"] == "verilator:WIDTHTRUNC rtl/a.v:10"
    assert t["filePath"] == "rtl/a.v"
    assert t["line"] == 10
    assert t["suite"] == "verilator"
    assert t["extra"]["rule"] == "WIDTHTRUNC"


def test_ctrf_new_finding_below_the_threshold_is_other_not_failed():
    """A warning under `fail_on: error` did not fail anything, and calling it
    `passed` would be a lie. CTRF's `other` is the honest bucket."""
    doc = ctrf_of([mkf(sev=SeverityE.Warning)], fail_on="error")
    statuses = {t["status"] for t in doc["results"]["tests"]}
    assert "failed" not in statuses
    assert "other" in statuses


def test_ctrf_waived_and_baselined_are_skipped_with_the_reason():
    waived = mkf(rule="A", sev=SeverityE.Error)
    waived.waived = "third-party DUT"
    based = mkf(rule="B", line=20, sev=SeverityE.Error)
    based.baseline = True

    doc = ctrf_of([waived, based])
    tests = {t["extra"]["rule"]: t for t in doc["results"]["tests"]
             if "extra" in t and "rule" in t["extra"]}
    assert tests["A"]["status"] == "skipped"
    assert "third-party DUT" in tests["A"]["message"]
    assert tests["B"]["status"] == "skipped"
    assert "baselined" in tests["B"]["message"]


def test_ctrf_clean_run_reports_the_tool_as_passed():
    """Without this a clean lint run renders as an empty report, which is
    indistinguishable from a lint run that never happened."""
    doc = ctrf_of([])
    tests = doc["results"]["tests"]
    assert len(tests) == 1
    assert tests[0]["status"] == "passed"
    assert "clean" in tests[0]["name"]


def test_ctrf_reports_a_skipped_tool_as_skipped():
    r = ToolRun(tool="vbl", name="verible",
                skipped="'verible-verilog-lint' not found on PATH; skipped")
    doc = ctrf_of([], tool_runs=[r])
    t = doc["results"]["tests"][0]
    assert t["status"] == "skipped"
    assert "not found on PATH" in t["message"]


def test_ctrf_tool_with_failures_gets_no_clean_entry():
    doc = ctrf_of([mkf(sev=SeverityE.Error)])
    assert not any(t["name"].endswith(": clean") for t in doc["results"]["tests"])


def test_ctrf_writes(tmpdir):
    p = os.path.join(str(tmpdir), "lint-ctrf.json")
    R.write_ctrf(p, ctrf_of([mkf()]))
    back = json.load(open(p))
    assert back["reportFormat"] == "CTRF"
