"""End-to-end lint runs through a real task graph, with real tools.

Availability-gated the way libhdlsim's simulator tests are: the suite runs
everywhere and exercises whatever is installed. Assertions are on the RULE IDS
a tool is expected to raise, never on total counts -- counts move with every
tool release and produce a suite that fails for no reason.
"""

import asyncio
import json
import os
import shutil

import pytest

from dv_flow.mgr import PackageLoader, TaskSetRunner
from dv_flow.mgr.task_graph_builder import TaskGraphBuilder

DATA = os.path.join(os.path.dirname(__file__), "data")
RTL = os.path.join(DATA, "rtl")


def get_available_tools():
    return [tool for exe, tool in (
        ("verilator", "vlt"),
    ) if shutil.which(exe) is not None]


AVAILABLE = get_available_tools()


def run_lint(tmpdir, name="lint", **params):
    """Build `<name>` over the fixture RTL and run it. Returns (result, rundir)."""
    rundir = os.path.join(str(tmpdir), "rundir")

    builder = TaskGraphBuilder(
        PackageLoader().load_rgy(["std", "hdllint", "hdllint.vlt"]), rundir)
    runner = TaskSetRunner(rundir)
    runner.builder = builder

    rtl = builder.mkTaskNode(
        "std.FileSet", name="rtl",
        type="verilogSource", base=RTL, include="*.v")

    lint = builder.mkTaskNode(
        params.pop("task", "hdllint.Rtl"), name=name, needs=[rtl], **params)

    asyncio.run(runner.run(lint))
    return lint.result, os.path.join(rundir, name)


def rules(result_or_path):
    """The rule ids a run reported, from its JSON report."""
    with open(result_or_path) as fp:
        doc = json.load(fp)
    return set(f["rule"] for f in doc["findings"])


def report(rundir, stem="lint"):
    return json.load(open(os.path.join(rundir, "%s.json" % stem)))


pytestmark = pytest.mark.skipif(
    not AVAILABLE, reason="no lint tool installed")


def test_finds_the_violations_the_fixtures_contain(tmpdir):
    """One assertion per violation class the fixture RTL was written for."""
    result, rundir = run_lint(tmpdir)
    found = rules(os.path.join(rundir, "lint.json"))

    assert "WIDTHTRUNC" in found      # width_mismatch.v
    assert "LATCH" in found           # latch_dut.v
    assert "UNUSEDSIGNAL" in found    # width_mismatch.v


def test_findings_carry_a_usable_location(tmpdir):
    _, rundir = run_lint(tmpdir)
    doc = report(rundir)
    width = [f for f in doc["findings"] if f["rule"] == "WIDTHTRUNC"][0]
    assert width["path"].endswith("width_mismatch.v")
    assert width["line"] > 0
    assert width["tool"] == "vlt"
    assert width["tool_name"] == "verilator"


def test_markers_carry_the_rule_id_and_the_location(tmpdir):
    """`TaskMarker` has no rule-id field, so the id rides in the message --
    which is also how the reader learns what to put in a waiver."""
    result, _ = run_lint(tmpdir)
    msgs = [m.msg for m in result.markers]
    assert any(m.startswith("[verilator:WIDTHTRUNC]") for m in msgs)

    width = [m for m in result.markers
             if m.msg.startswith("[verilator:WIDTHTRUNC]")][0]
    assert width.loc is not None and width.loc.line > 0


def test_all_three_reports_are_written(tmpdir):
    _, rundir = run_lint(tmpdir)
    for f in ("lint.json", "lint.sarif", "lint-ctrf.json"):
        assert os.path.isfile(os.path.join(rundir, f)), f


def test_sarif_is_well_formed_and_names_the_real_tool(tmpdir):
    _, rundir = run_lint(tmpdir)
    doc = json.load(open(os.path.join(rundir, "lint.sarif")))
    assert doc["version"] == "2.1.0"
    driver = doc["runs"][0]["tool"]["driver"]
    assert driver["name"] == "verilator"
    assert driver["version"]           # captured from `verilator --version`
    assert doc["runs"][0]["results"]


def test_ctrf_summary_is_consistent(tmpdir):
    _, rundir = run_lint(tmpdir)
    doc = json.load(open(os.path.join(rundir, "lint-ctrf.json")))
    s = doc["results"]["summary"]
    assert doc["reportFormat"] == "CTRF"
    assert s["tests"] == len(doc["results"]["tests"])
    assert s["stop"] >= s["start"]


def test_the_command_and_log_are_recorded(tmpdir):
    """When a parser produces a surprising finding, the first question is what
    was actually run and the second is what the tool actually said."""
    _, rundir = run_lint(tmpdir)
    doc = report(rundir)
    run = doc["runs"][0]
    assert run["cmd"][1] == "--lint-only"
    assert os.path.isfile(run["log"])
    assert os.path.isfile(os.path.join(rundir, "vlt", "lint.f"))


def test_fail_on_none_reports_without_failing(tmpdir):
    """Someone adopting lint must be able to see error findings and still get
    a zero exit while they work through them."""
    result, rundir = run_lint(tmpdir, fail_on="none")
    assert result.status == 0
    assert report(rundir)["summary"]["new"] > 0


def test_fail_on_warning_fails_the_task(tmpdir):
    result, _ = run_lint(tmpdir, fail_on="warning")
    assert result.status != 0


def test_waivers_suppress_markers_but_stay_in_the_report(tmpdir):
    _, rundir = run_lint(tmpdir, fail_on="warning", tools=["vlt"])
    assert report(rundir)["summary"]["new"] > 0

    wf = os.path.join(str(tmpdir), "waivers.yaml")
    with open(wf, "w") as fp:
        fp.write("waivers:\n"
                 "- rule: WIDTHTRUNC\n"
                 "  reason: fixture is deliberately truncating\n")

    result2, rundir2 = run_lint(tmpdir.mkdir("w2"), fail_on="warning",
                                waivers=wf)
    doc = report(rundir2)
    assert doc["summary"]["waived"] >= 1
    waived = [f for f in doc["findings"] if f.get("waived")]
    assert all(f["rule"] == "WIDTHTRUNC" for f in waived)
    assert not any(m.msg.startswith("[verilator:WIDTHTRUNC]")
                   for m in result2.markers)


def waiver_file(tmpdir, body):
    p = os.path.join(str(tmpdir), "waivers.yaml")
    with open(p, "w") as fp:
        fp.write(body)
    return p


def test_native_lowering_suppresses_inside_the_tool(tmpdir):
    """`waiver_mode: native` must reach Verilator itself -- the finding should
    be absent from the tool's own log, not merely filtered out of ours."""
    wf = waiver_file(tmpdir, "waivers:\n"
                             "- rule: LATCH\n"
                             "  reason: deliberate in the fixture\n")

    _, rundir = run_lint(tmpdir.mkdir("native"), waivers=wf,
                         waiver_mode="native")

    log = open(os.path.join(rundir, "vlt", "lint.log")).read()
    assert "LATCH" not in log

    doc = report(rundir)
    assert not any(f["rule"] == "LATCH" for f in doc["findings"])
    assert doc["waiver_mode"] == "native"
    assert doc["waivers_lowered"] == 1
    assert doc["runs"][0]["waivers_lowered"] == 1
    # The generated config is kept, so the suppression is inspectable.
    assert os.path.isfile(os.path.join(rundir, "vlt", "waivers.vlt"))


def test_native_and_post_agree_on_which_findings_remain(tmpdir):
    """The two modes differ in accounting and in how much work the tool does
    -- never in whether a waiver is in force."""
    body = ("waivers:\n"
            "- rule: LATCH\n"
            "  reason: deliberate in the fixture\n")

    _, post_dir = run_lint(tmpdir.mkdir("p"),
                           waivers=waiver_file(tmpdir.mkdir("wp"), body))
    _, native_dir = run_lint(tmpdir.mkdir("n"),
                             waivers=waiver_file(tmpdir.mkdir("wn"), body),
                             waiver_mode="native")

    def reported(d):
        return sorted((f["rule"], f["path"], f["line"])
                      for f in report(d)["findings"] if not f.get("waived"))

    assert reported(post_dir) == reported(native_dir)


def test_post_mode_counts_waivers_that_native_mode_cannot(tmpdir):
    """The honest difference, pinned: post-filtering knows how many findings
    a waiver suppressed; native lowering cannot, because the tool never
    emitted them."""
    body = ("waivers:\n"
            "- rule: LATCH\n"
            "  reason: deliberate in the fixture\n")

    _, post_dir = run_lint(tmpdir.mkdir("p"),
                           waivers=waiver_file(tmpdir.mkdir("wp"), body))
    _, native_dir = run_lint(tmpdir.mkdir("n"),
                             waivers=waiver_file(tmpdir.mkdir("wn"), body),
                             waiver_mode="native")

    assert report(post_dir)["summary"]["waived"] == 1
    assert report(native_dir)["summary"]["waived"] == 0
    assert report(native_dir)["waivers_lowered"] == 1


def test_native_mode_falls_back_to_post_filtering_for_what_it_cannot_lower(tmpdir):
    """A rule glob has no `-rule` equivalent, so it must still be enforced by
    the post-filter -- switching modes may not turn a waiver off."""
    wf = waiver_file(tmpdir, "waivers:\n"
                             "- rule: 'LATC*'\n"
                             "  reason: glob, not lowerable\n")

    _, rundir = run_lint(tmpdir.mkdir("native"), waivers=wf,
                         waiver_mode="native")
    doc = report(rundir)

    assert doc["waivers_lowered"] == 0
    assert doc["summary"]["waived"] == 1          # ...still in force
    assert "LATCH" in open(os.path.join(rundir, "vlt", "lint.log")).read()


def test_unknown_waiver_mode_is_an_error(tmpdir):
    result, _ = run_lint(tmpdir, waiver_mode="sometimes")
    assert result.status != 0
    assert any("Unknown waiver_mode" in m.msg for m in result.markers)


def test_baseline_accepts_todays_findings_then_passes(tmpdir):
    """The adoption story, end to end: establish a baseline over existing
    findings, then run clean against it."""
    bl = os.path.join(str(tmpdir), "lint-baseline.json")

    result, rundir = run_lint(tmpdir.mkdir("update"), fail_on="warning",
                              baseline=bl, update_baseline=True)
    assert os.path.isfile(bl)
    assert json.load(open(bl))["total"] > 0

    result2, rundir2 = run_lint(tmpdir.mkdir("check"), fail_on="warning",
                                baseline=bl)
    doc = report(rundir2)
    assert result2.status == 0
    assert doc["summary"]["new"] == 0
    assert doc["summary"]["baselined"] > 0


def test_named_backend_task_behaves_like_the_family(tmpdir):
    """`hdllint.vlt.Rtl` is the family task with `tools:` pinned -- same
    waivers, same baseline, same reports."""
    _, rundir = run_lint(tmpdir, task="hdllint.vlt.Rtl")
    doc = report(rundir)
    assert doc["summary"]["tools"] == ["vlt"]
    assert "WIDTHTRUNC" in set(f["rule"] for f in doc["findings"])


def test_profile_basic_is_quieter_than_strict(tmpdir):
    """Profiles have to actually differ, or they are decoration."""
    _, basic_dir = run_lint(tmpdir.mkdir("basic"), profile="basic")
    _, strict_dir = run_lint(tmpdir.mkdir("strict"), profile="strict")
    assert report(basic_dir)["summary"]["total"] \
        < report(strict_dir)["summary"]["total"]


def test_requesting_a_family_no_tool_implements_is_an_error(tmpdir):
    """Not a silent empty report."""
    result, _ = run_lint(tmpdir, task="hdllint.Tb")
    assert result.status != 0
    assert any("does not implement" in m.msg or "No registered backend" in m.msg
               for m in result.markers)


def test_no_sources_is_an_error_naming_the_fix(tmpdir):
    rundir = os.path.join(str(tmpdir), "rundir")
    builder = TaskGraphBuilder(
        PackageLoader().load_rgy(["std", "hdllint"]), rundir)
    runner = TaskSetRunner(rundir)
    runner.builder = builder

    lint = builder.mkTaskNode("hdllint.Rtl", name="lint")
    asyncio.run(runner.run(lint))

    assert lint.result.status != 0
    assert any("No source files to lint" in m.msg for m in lint.result.markers)
