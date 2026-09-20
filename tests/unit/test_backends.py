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


def test_implementing_lists_backends_per_family():
    assert [b.id for b in B.implementing("Rtl")] == ["vlt"]
    # Verilator parses the synthesis subset and cannot see class-based code,
    # so it must not appear under Tb.
    assert [b.id for b in B.implementing("Tb")] == []


def test_backend_runner_is_resolvable():
    """The registry names its runner as a string and resolves it lazily;
    a typo there would otherwise surface only at run time."""
    assert callable(B.BACKENDS["vlt"].load())


# ----------------------------------------------------------------- selection

def test_empty_tools_selects_whatever_is_installed(tmpdir):
    sel = B.select([], "Rtl", env_with("verilator", tmpdir=tmpdir))
    assert [b.id for b in sel.selected] == ["vlt"]
    assert sel.skipped == []


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
        sel = B.select([], "Rtl", env_with("verilator", tmpdir=tmpdir))
        assert [b.id for b in sel.selected] == ["vlt"]
        assert [b.id for b, _ in sel.skipped] == ["_fake"]
        assert "not found on PATH" in sel.skipped[0][1]
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
