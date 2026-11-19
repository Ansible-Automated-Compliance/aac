"""PowerShell result shapes (pwsh.py).

ConvertTo-Json unrolls a one-element pipeline into a bare object; a policy
that iterates that "list" walks the object's field values and passes. These
tests pin the generated script and the normalisation of what it prints,
using a stand-in pwsh executable that prints recorded output (no
PowerShell, no tenant).
"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT / "collections") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "collections"))

from ansible_collections.aac.m365.plugins.module_utils import pwsh  # noqa: E402

ROW = {"Name": "Default", "Enabled": True}


# ── normalisation of recorded output ─────────────────────────────────

@pytest.mark.parametrize("printed, expected", [
    (None, []),                       # null
    ([], []),                         # zero rows
    (ROW, [ROW]),                     # one row unrolled to a bare object
    ([ROW], [ROW]),                   # one row as an array
    ([ROW, {"Name": "B"}], [ROW, {"Name": "B"}]),
    ([None, ROW, None], [ROW]),       # null rows dropped
])
def test_as_list(printed, expected):
    assert pwsh.as_list(printed) == (expected, None)


@pytest.mark.parametrize("printed", ["a string", 3, ["x", ROW], [True]])
def test_as_list_rejects_rows_that_are_not_objects(printed):
    value, err = pwsh.as_list(printed)
    assert value is None and "not objects" in err


def test_as_object():
    assert pwsh.as_object(ROW) == (ROW, None)
    assert pwsh.as_object([ROW]) == (ROW, None)
    for printed in (None, [], [ROW, ROW], "x"):
        value, err = pwsh.as_object(printed)
        assert value is None and err


# ── the generated script ─────────────────────────────────────────────

def _runner(path="/nonexistent/pwsh"):
    return pwsh.PwshRunner(service="exchange", app_id="a", organization="contoso.onmicrosoft.com",
                           cert_path="/tmp/x.pfx", cert_password="p", pwsh_path=path)


def test_list_script_collects_around_the_invocation():
    script = _runner()._wrap("Get-X | Select-Object Name", pwsh.LIST)
    assert "$aacValue = @(& { Get-X | Select-Object Name })" in script
    assert "ConvertTo-Json -InputObject $aacValue" in script
    assert "-Depth %d" % (pwsh.JSON_DEPTH + 1) in script


def test_object_script_does_not_wrap():
    script = _runner()._wrap("Get-OrganizationConfig", pwsh.OBJECT)
    assert "$aacValue = & { Get-OrganizationConfig }" in script
    assert "@(&" not in script


def test_every_script_writes_enums_as_strings_and_guards_depth():
    for shape in (pwsh.LIST, pwsh.OBJECT, pwsh.RAW):
        script = _runner()._wrap("Get-X", shape)
        assert "-EnumsAsStrings" in script
        assert "-WarningVariable aacJsonWarnings" in script
        assert pwsh.TRUNCATED_MARKER in script
        # the throw is inside try, so finally still disconnects
        assert script.index("throw") < script.index("} finally {")


def test_unknown_shape_is_refused():
    with pytest.raises(pwsh.PwshError):
        _runner().try_run("Get-X", shape="bogus")


# ── end to end through a stand-in pwsh ───────────────────────────────

@pytest.fixture
def fake_pwsh(tmp_path, monkeypatch):
    exe = tmp_path / "pwsh"
    exe.write_text(
        "#!/bin/sh\n"
        "printf '%s' \"$FAKE_STDOUT\"\n"
        "printf '%s' \"$FAKE_STDERR\" >&2\n"
        "exit ${FAKE_RC:-0}\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)

    def run(stdout="", stderr="", rc=0, shape=pwsh.LIST):
        monkeypatch.setenv("FAKE_STDOUT", stdout)
        monkeypatch.setenv("FAKE_STDERR", stderr)
        monkeypatch.setenv("FAKE_RC", str(rc))
        return _runner(str(exe)).try_run("Get-X", shape=shape)
    return run


def test_list_from_printed_json(fake_pwsh):
    assert fake_pwsh('[{"Name":"Default"}]') == ([{"Name": "Default"}], None)
    assert fake_pwsh('{"Name":"Default"}') == ([{"Name": "Default"}], None)
    assert fake_pwsh("[]") == ([], None)
    assert fake_pwsh("null") == ([], None)


def test_object_from_printed_json(fake_pwsh):
    assert fake_pwsh('{"A":1}', shape=pwsh.OBJECT) == ({"A": 1}, None)
    value, err = fake_pwsh("null", shape=pwsh.OBJECT)
    assert value is None and "no object" in err
    value, err = fake_pwsh('[{"A":1},{"A":2}]', shape=pwsh.OBJECT)
    assert value is None and "2 objects" in err


def test_depth_truncation_is_evidence_missing(fake_pwsh):
    value, err = fake_pwsh(
        "", stderr="Exception: %s: Resulting JSON is truncated as serialization has exceeded "
                   "the set depth of 7." % pwsh.TRUNCATED_MARKER, rc=1)
    assert value is None
    assert err.startswith("evidence missing:") and "depth" in err


def test_empty_stdout_is_still_an_error(fake_pwsh):
    value, err = fake_pwsh("")
    assert value is None and "no output" in err
