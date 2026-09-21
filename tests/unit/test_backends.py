"""Tool selection, and above all its diagnostics.

Selection is the single most likely place for this library to lie to a user,
because every failure mode has a plausible-looking quiet outcome: an empty
report. Each test here pins one of those to a message that names the problem
and the way out.
"""

import pytest

from dv_flow.libhdllint import backends as B


class FakeEnv(dict):
    pass


def env_with(*names, tmpdir):
    """A PATH containing executables with the given names."""
    import os
    import stat
    d = str(tmpdir)
    for n in names:
        p = os.path.join(d, n)
        with open(p, "w") as fp:
            fp.write("#!/bin/sh\nexit 0\n")
        os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
    return FakeEnv(PATH=d)


def empty_env(tmpdir):
    import os
    return FakeEnv(PATH=os.path.join(str(tmpdir), "empty"))


# ------------------------------------------------------------------ registry

def test_registry_is_the_single_source_of_capability():
    assert "vlt" in B.BACKENDS
    vlt = B.BACKENDS["vlt"]
    assert vlt.name == "verilator" and vlt.exe == "verilator"
    assert vlt.families == ("Rtl",)
    # All six backends are registered.
    assert set(B.BACKENDS.keys()) == {"vlt", "spy", "z0i", "vcs", "qst", "jg"}


def test_implementing_lists_backends_per_family():
    rtl_ids = [b.id for b in B.implementing("Rtl")]
    assert "vlt" in rtl_ids
    assert "spy" in rtl_ids
    assert "z0i" in rtl_ids
    assert "vcs" in rtl_ids
    assert "qst" in rtl_ids
    assert "jg" in rtl_ids
    assert len(rtl_ids) == 6
    # Verilator parses the synthesis subset and cannot see class-based code,
    # so it must not appear under Tb.
    assert [b.id for b in B.implementing("Tb")] == []


def test_implementing_style_backends():
    """Only spy and vcs implement Style."""
    style_ids = [b.id for b in B.implementing("Style")]
    assert set(style_ids) == {"spy", "vcs"}


@pytest.mark.parametrize("backend_id", list(B.BACKENDS.keys()))
def test_backend_runner_is_resolvable(backend_id):
    """The registry names its runner as a string and resolves it lazily;
    a typo there would otherwise surface only at run time."""
    assert callable(B.BACKENDS[backend_id].load())


@pytest.mark.parametrize("backend_id", [
    bid for bid, b in B.BACKENDS.items() if b.lowerer])
def test_backend_lowerer_is_resolvable(backend_id):
    """Backends that declare a lowerer must be importable."""
    assert callable(B.BACKENDS[backend_id].load_lowerer())


# ----------------------------------------------------------------- selection

def test_empty_tools_selects_whatever_is_installed(tmpdir):
    env = env_with("verilator", "sg_shell", "0in", "vc_static_shell",
                    "qverify", "jg", tmpdir=tmpdir)
    sel = B.select([], "Rtl", env)
    ids = [b.id for b in sel.selected]
    assert "vlt" in ids
    assert len(ids) == 6
    assert len(sel.skipped) == 0


def test_named_tool_is_selected(tmpdir):
    sel = B.select(["vlt"], "Rtl", env_with("verilator", tmpdir=tmpdir))
    assert [b.id for b in sel.selected] == ["vlt"]


def test_duplicate_names_are_collapsed(tmpdir):
    sel = B.select(["vlt", "vlt"], "Rtl", env_with("verilator", tmpdir=tmpdir))
    assert len(sel.selected) == 1


def test_blank_entries_are_ignored(tmpdir):
    sel = B.select(["", "  "], "Rtl", env_with("verilator", tmpdir=tmpdir))
    assert [b.id for b in sel.selected] == ["vlt"]


def test_unknown_tool_is_an_error_with_a_near_match_hint(tmpdir):
    with pytest.raises(B.SelectionError) as e:
        B.select(["vlr"], "Rtl", env_with("verilator", tmpdir=tmpdir))
    msg = str(e.value)
    assert "Unknown lint tool 'vlr'" in msg
    assert "Did you mean 'vlt'?" in msg


def test_family_a_tool_does_not_implement_is_an_error(tmpdir):
    """Never a silent empty report: reporting "no findings" for a check that
    never ran is the worst thing a lint library can do."""
    with pytest.raises(B.SelectionError) as e:
        B.select(["vlt"], "Tb", env_with("verilator", tmpdir=tmpdir))
    msg = str(e.value)
    assert "does not implement the 'Tb' family" in msg
    assert "it implements: Rtl" in msg


def test_named_tool_that_is_not_installed_is_an_error(tmpdir):
    """Naming a tool is a statement that the run needs it. Skipping it would
    produce a green run that checked less than was asked for."""
    with pytest.raises(B.SelectionError) as e:
        B.select(["vlt"], "Rtl", empty_env(tmpdir))
    msg = str(e.value)
    assert "'verilator' was not found on PATH" in msg
    assert "drop it from `tools:`" in msg


def test_auto_selected_tool_that_is_not_installed_is_skipped_not_fatal(tmpdir):
    """The auto case is different in kind: the flow said "whatever is
    available"."""
    B.BACKENDS["_fake"] = B.Backend(
        id="_fake", name="fake", exe="definitely-not-installed",
        families=("Rtl",), runner="dv_flow.libhdllint.vlt_lint:run")
    try:
        env = env_with("verilator", "sg_shell", "0in", "vc_static_shell",
                        "qverify", "jg", tmpdir=tmpdir)
        sel = B.select([], "Rtl", env)
        selected_ids = [b.id for b in sel.selected]
        skipped_ids = [b.id for b, _ in sel.skipped]
        assert "_fake" in skipped_ids
        assert "_fake" not in selected_ids
        fake_reason = [r for b, r in sel.skipped if b.id == "_fake"][0]
        assert "not found on PATH" in fake_reason
    finally:
        del B.BACKENDS["_fake"]


def test_no_tool_available_at_all_is_an_error_naming_what_to_install(tmpdir):
    with pytest.raises(B.SelectionError) as e:
        B.select([], "Rtl", empty_env(tmpdir))
    msg = str(e.value)
    assert "No lint tool available for the 'Rtl' family" in msg
    assert "vlt (verilator)" in msg


def test_family_with_no_backend_at_all_is_an_error():
    with pytest.raises(B.SelectionError) as e:
        B.select([], "Tb", None)
    assert "No registered backend implements the 'Tb' family" in str(e.value)


def test_unknown_family_is_an_error():
    with pytest.raises(B.SelectionError) as e:
        B.select([], "Nonsense", None)
    assert "Unknown lint family" in str(e.value)


def test_which_honours_the_task_environment(tmpdir):
    """Tasks run with a PATH the flow can extend; asking the ambient PATH can
    report a tool as missing that the run would have found."""
    env = env_with("some-lint-tool", tmpdir=tmpdir)
    assert B.which("some-lint-tool", env) is not None
    assert B.which("some-lint-tool", empty_env(tmpdir)) is None


# -------------------------------------------------- multi-tool selection

def test_selection_across_multiple_tools(tmpdir):
    """Selecting two named tools returns both in order."""
    env = env_with("verilator", "sg_shell", tmpdir=tmpdir)
    sel = B.select(["vlt", "spy"], "Rtl", env)
    assert [b.id for b in sel.selected] == ["vlt", "spy"]


def test_auto_selection_with_multiple_tools_installed(tmpdir):
    """With two Rtl tools on PATH, both are selected."""
    env = env_with("verilator", "sg_shell", tmpdir=tmpdir)
    sel = B.select([], "Rtl", env)
    ids = [b.id for b in sel.selected]
    assert "vlt" in ids
    assert "spy" in ids


def test_style_selection_only_returns_style_backends(tmpdir):
    env = env_with("sg_shell", "vc_static_shell", tmpdir=tmpdir)
    sel = B.select([], "Style", env)
    ids = [b.id for b in sel.selected]
    assert set(ids) == {"spy", "vcs"}


def test_multi_tool_dedup_with_fabricated_findings():
    """Cross-tool dedup collapses shared findings, keeping the first tool
    alphabetically."""
    from dv_flow.libhdllint.finding import Finding
    from dv_flow.libhdllint import report as R
    from dv_flow.mgr.task_data import SeverityE

    f1 = Finding(tool="spy", tool_name="spyglass", rule="W_REDF",
                 severity=SeverityE.Warning, msg="Width mismatch",
                 path="rtl/a.v", line=10)
    f2 = Finding(tool="vlt", tool_name="verilator", rule="WIDTHTRUNC",
                 severity=SeverityE.Warning, msg="Width mismatch",
                 path="rtl/a.v", line=10)
    kept, dropped = R.dedup([f1, f2])
    # Same (path, line, normalized msg) -> one dropped
    assert len(kept) == 1
    assert len(dropped) == 1
    # Alphabetically first tool wins
    assert kept[0].tool == "spy"
    assert dropped[0].tool == "vlt"
    assert dropped[0].dup_of == "spy"
