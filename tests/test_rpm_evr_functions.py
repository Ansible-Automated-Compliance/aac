"""rpm version ordering in the database (ansible/files/rpm_evr_functions.sql).

The expected value of every case in RPMVERCMP_CASES and EVR_CASES was produced
by rpm itself (rpm 4.16 in registry.access.redhat.com/ubi9/ubi: `rpm.vercmp` in
rpm's Lua and `rpm.labelCompare` in python3-rpm), so the table is rpm's answer,
not this implementation's. Most rpmvercmp cases are the ones in rpm's own test
suite (tests/rpmvercmp.at).
"""
from __future__ import annotations

import os

import pytest

from aac_pg_helpers import sql_literal

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SQL = os.path.join(_REPO, "ansible", "files", "rpm_evr_functions.sql")

# (a, b, rpmvercmp(a, b))
RPMVERCMP_CASES = [
    ("1.0", "1.0", 0), ("1.0", "2.0", -1), ("2.0", "1.0", 1),
    ("2.0.1", "2.0.1", 0), ("2.0", "2.0.1", -1), ("2.0.1", "2.0", 1),
    ("2.0.1a", "2.0.1a", 0), ("2.0.1a", "2.0.1", 1), ("2.0.1", "2.0.1a", -1),
    ("5.5p1", "5.5p1", 0), ("5.5p1", "5.5p2", -1), ("5.5p2", "5.5p1", 1),
    ("5.5p10", "5.5p10", 0), ("5.5p1", "5.5p10", -1), ("5.5p10", "5.5p1", 1),
    ("10xyz", "10.1xyz", -1), ("10.1xyz", "10xyz", 1),
    ("xyz10", "xyz10", 0), ("xyz10", "xyz10.1", -1), ("xyz10.1", "xyz10", 1),
    ("xyz.4", "xyz.4", 0), ("xyz.4", "8", -1), ("8", "xyz.4", 1), ("xyz.4", "2", -1), ("2", "xyz.4", 1),
    ("5.5p2", "5.6p1", -1), ("5.6p1", "5.5p2", 1), ("5.6p1", "6.5p1", -1), ("6.5p1", "5.6p1", 1),
    ("6.0.rc1", "6.0", 1), ("6.0", "6.0.rc1", -1),
    ("10b2", "10a1", 1), ("10a2", "10b2", -1),
    ("1.0aa", "1.0aa", 0), ("1.0a", "1.0aa", -1), ("1.0aa", "1.0a", 1),
    ("10.0001", "10.0001", 0), ("10.0001", "10.1", 0), ("10.1", "10.0001", 0),
    ("10.0001", "10.0039", -1), ("10.0039", "10.0001", 1),
    ("4.999.9", "5.0", -1), ("5.0", "4.999.9", 1),
    ("20101121", "20101121", 0), ("20101121", "20101122", -1), ("20101122", "20101121", 1),
    ("2_0", "2_0", 0), ("2.0", "2_0", 0), ("2_0", "2.0", 0),
    ("a", "a", 0), ("a+", "a+", 0), ("a+", "a_", 0), ("a_", "a+", 0),
    ("+a", "+a", 0), ("+a", "_a", 0), ("_a", "+a", 0),
    ("+_", "+_", 0), ("_+", "+_", 0), ("_+", "_+", 0), ("+", "_", 0), ("_", "+", 0),
    # numeric against alphabetic, and upper against lower case
    ("1", "a", 1), ("a", "1", -1), ("1.a", "1.1", -1), ("A", "a", -1), ("1.0A", "1.0a", -1),
    # the two cases the old string comparison got wrong most often
    ("1.10", "1.9", 1), ("1.9", "1.10", -1), ("1.10.0", "1.9.9", 1),
    ("9", "10", -1), ("09", "10", -1), ("010", "10", 0),
    # tilde: sorts before everything, the end of the string included
    ("1.0~rc1", "1.0~rc1", 0), ("1.0~rc1", "1.0", -1), ("1.0", "1.0~rc1", 1),
    ("1.0~rc1", "1.0~rc2", -1), ("1.0~rc2", "1.0~rc1", 1),
    ("1.0~rc1~git123", "1.0~rc1~git123", 0), ("1.0~rc1~git123", "1.0~rc1", -1), ("1.0~rc1", "1.0~rc1~git123", 1),
    ("1.0~beta", "1.0~rc1", -1), ("2.0~", "2.0", -1), ("~", "1", -1),
    # caret: sorts after the end of the string, before any further segment
    ("1.0^", "1.0^", 0), ("1.0^", "1.0", 1), ("1.0", "1.0^", -1),
    ("1.0^git1", "1.0^git1", 0), ("1.0^git1", "1.0", 1), ("1.0", "1.0^git1", -1),
    ("1.0^git1", "1.0^git2", -1), ("1.0^git2", "1.0^git1", 1),
    ("1.0^git1", "1.01", -1), ("1.01", "1.0^git1", 1),
    ("1.0^20160101", "1.0^20160101", 0), ("1.0^20160101", "1.0.1", -1), ("1.0.1", "1.0^20160101", 1),
    ("1.0^20160101^git1", "1.0^20160101^git1", 0), ("1.0^20160102", "1.0^20160101^git1", 1),
    ("1.0^20160101^git1", "1.0^20160102", -1),
    ("1.0~rc1^git1", "1.0~rc1^git1", 0), ("1.0~rc1^git1", "1.0~rc1", 1), ("1.0~rc1", "1.0~rc1^git1", -1),
    ("1.0^git1~pre", "1.0^git1~pre", 0), ("1.0^git1", "1.0^git1~pre", 1), ("1.0^git1~pre", "1.0^git1", -1),
    # releases as they appear on RHEL
    ("687.61.1.el9_8", "687.64.1.el9_8", -1), ("687.64.1.el9_8", "687.64.1.el9_8", 0),
    ("687.64.1.el9_8", "687.61.1.el9_8", 1), ("687.100.1.el9_8", "687.64.1.el9_8", 1),
    # differing dist tags: the tag is compared like any other segment
    ("5.el9_8", "5.el9_7", 1), ("5.el9_7", "5.el9_8", -1), ("5.el9_10", "5.el9_9", 1),
    ("5.el9", "5.el9_8", -1), ("5.el9_8.1", "5.el9_8", 1), ("9.el9", "9.el9_4.1", -1),
    ("5.el8_10", "5.el9_8", -1), ("427.161.1.el9_4", "687.64.1.el9_8", -1),
    ("553.182.1.rt7.523.el8_10", "553.182.1.el8_10", 1),
]

# (a, b, compare) for full [epoch:]version[-release] strings
EVR_CASES = [
    # the reference kernel CVE: fixed in 5.14.0-687.64.1.el9_8
    ("5.14.0-687.61.1.el9_8", "5.14.0-687.64.1.el9_8", -1),
    ("5.14.0-687.64.1.el9_8", "5.14.0-687.64.1.el9_8", 0),
    ("5.14.0-687.65.1.el9_8", "5.14.0-687.64.1.el9_8", 1),
    ("5.14.0-687.100.1.el9_8", "5.14.0-687.64.1.el9_8", 1),
    ("4.18.0-553.180.1.el8_10", "4.18.0-553.182.1.el8_10", -1),
    ("6.12.0-211.72.1.el10_2", "6.12.0-211.72.1.el10_2", 0),
    ("5.14.0-427.161.1.el9_4", "5.14.0-687.64.1.el9_8", -1),
    # epoch decides before anything else; a missing epoch is 0
    ("1:1.0-1", "2.0-1", 1), ("2.0-1", "1:1.0-1", -1), ("0:1.0-1", "1.0-1", 0),
    ("1:3.2.2-6.el9_5", "1:3.2.2-7.el9_5", -1), ("2:1.0-1.el9", "1:9.9-9.el9", 1),
    ("1:3.2.2-6.el9_5", "3.5.0-1.el9", 1), ("10:1.0-1", "9:1.0-1", 1),
    # version before release
    ("1.10-1.el9", "1.9-99.el9", 1), ("1.9-99.el9", "1.10-1.el9", -1),
    ("2.34-100.el9", "2.34-99.el9", 1),
    # tilde pre-releases and caret snapshots inside an EVR
    ("1.0~rc1-1.el9", "1.0-1.el9", -1), ("1.0-1.el9", "1.0~rc1-1.el9", 1),
    ("1.0~rc1-5.el9", "1.0~rc2-1.el9", -1), ("1.0^20260101-1.el9", "1.0-9.el9", 1),
    # dist tags
    ("5.1.8-9.el9_8", "5.1.8-9.el9_7", 1), ("5.1.8-9.el9", "5.1.8-9.el9_4.1", -1),
    ("5.1.8-10.el9_7", "5.1.8-9.el9_8", 1),
]

# A side with no release: only epoch and version are compared.
NO_RELEASE_CASES = [
    ("3.2.4-1.el9", "3.2.4", 0), ("3.2.4", "3.2.4-1.el9", 0),
    ("3.2.3-9.el9", "3.2.4", -1), ("3.2.5-1.el9", "3.2.4", 1), ("1:1.0-1", "2.0", 1),
]


def _compare_all(pg, function, cases):
    values = ",".join("(%d,%s,%s)" % (i, sql_literal(a), sql_literal(b)) for i, (a, b, _) in enumerate(cases))
    rows = pg.rows("SELECT n, %s(a, b) FROM (VALUES %s) AS t(n, a, b) ORDER BY n" % (function, values))
    return {int(n): int(r) for n, r in rows}


@pytest.fixture(scope="module")
def pg(aac_pg):
    with open(_SQL, encoding="utf-8") as fh:
        sql = fh.read()
    aac_pg.run(sql)
    aac_pg.run(sql)  # idempotent: a second apply must not fail
    return aac_pg


@pytest.fixture(scope="module")
def vercmp_results(pg):
    return _compare_all(pg, "aac_rpmvercmp", RPMVERCMP_CASES)


@pytest.fixture(scope="module")
def evr_results(pg):
    return _compare_all(pg, "aac_evr_cmp", EVR_CASES + NO_RELEASE_CASES)


@pytest.mark.parametrize("n", range(len(RPMVERCMP_CASES)),
                         ids=["%s_vs_%s" % (a, b) for a, b, _ in RPMVERCMP_CASES])
def test_rpmvercmp(vercmp_results, n):
    a, b, expected = RPMVERCMP_CASES[n]
    assert vercmp_results[n] == expected, "aac_rpmvercmp(%r, %r)" % (a, b)


@pytest.mark.parametrize("n", range(len(EVR_CASES + NO_RELEASE_CASES)),
                         ids=["%s_vs_%s" % (a, b) for a, b, _ in EVR_CASES + NO_RELEASE_CASES])
def test_evr_cmp(evr_results, n):
    a, b, expected = (EVR_CASES + NO_RELEASE_CASES)[n]
    assert evr_results[n] == expected, "aac_evr_cmp(%r, %r)" % (a, b)


def test_comparison_is_antisymmetric(pg):
    """cmp(a, b) == -cmp(b, a) for every pair in both tables."""
    pairs = [(a, b) for a, b, _ in RPMVERCMP_CASES]
    values = ",".join("(%s,%s)" % (sql_literal(a), sql_literal(b)) for a, b in pairs)
    bad = pg.rows("SELECT a, b FROM (VALUES %s) AS t(a, b) "
                  "WHERE aac_rpmvercmp(a, b) <> -aac_rpmvercmp(b, a)" % values)
    assert bad == []


def test_null_in_null_out(pg):
    assert pg.value("SELECT (aac_evr_cmp(NULL, '1.0-1') IS NULL)::text") == "true"
    assert pg.value("SELECT (aac_rpmvercmp('1.0', NULL) IS NULL)::text") == "true"


@pytest.mark.parametrize("epoch, version, release, expected", [
    (None, "5.14.0", "687.64.1.el9_8", "5.14.0-687.64.1.el9_8"),
    ("0", "5.14.0", "687.64.1.el9_8", "5.14.0-687.64.1.el9_8"),
    ("1", "3.2.2", "6.el9_5", "1:3.2.2-6.el9_5"),
    (None, "3.0.11-1~deb12u2", None, "3.0.11-1~deb12u2"),
    (None, None, "1.el9", ""),
])
def test_evr_text_form(pg, epoch, version, release, expected):
    got = pg.value("SELECT COALESCE(aac_evr(%s, %s, %s), '')"
                   % (sql_literal(epoch), sql_literal(version), sql_literal(release)))
    assert got == expected


def test_evr_parts(pg):
    assert pg.rows("SELECT aac_evr_epoch('1:3.2.2-6.el9_5'), aac_evr_version('1:3.2.2-6.el9_5'), "
                   "aac_evr_release('1:3.2.2-6.el9_5'), aac_evr_epoch('5.14.0-687.64.1.el9_8')") \
        == [["1", "3.2.2", "6.el9_5", "0"]]


def test_evr_max_picks_the_newest_installed_build(pg):
    assert pg.value("SELECT aac_evr_max(ARRAY['5.14.0-687.58.1.el9_8','5.14.0-687.64.1.el9_8',"
                    "'5.14.0-687.61.1.el9_8'])") == "5.14.0-687.64.1.el9_8"
    assert pg.value("SELECT aac_evr_max(ARRAY['2.0-1','1:1.0-1'])") == "1:1.0-1"
    assert pg.value("SELECT COALESCE(aac_evr_max(ARRAY[]::text[]), 'none')") == "none"


@pytest.mark.parametrize("evr, tag, stream", [
    ("5.14.0-687.64.1.el9_8", "el9_8", "el9"),
    ("4.18.0-553.182.1.el8_10", "el8_10", "el8"),
    ("6.12.0-211.72.1.el10_2", "el10_2", "el10"),
    ("4.18.0-553.182.1.rt7.523.el8_10", "el8_10", "el8"),
    ("5.1.8-9.el9", "el9", "el9"),
    ("5.1.8-9.el9_4.1", "el9_4", "el9"),
    ("6.14.5-300.fc42", "fc42", "fc42"),
    ("1.2.3-4", "", ""),
    ("3.0.11-1~deb12u2", "", ""),
])
def test_dist_tag_and_stream(pg, evr, tag, stream):
    assert pg.rows("SELECT COALESCE(aac_rpm_dist_tag(%s), ''), COALESCE(aac_rpm_stream(%s), '')"
                   % (sql_literal(evr), sql_literal(evr))) == [[tag, stream]]


@pytest.mark.parametrize("package, uname, expected", [
    ("kernel", "5.14.0-687.61.1.el9_8.x86_64", "5.14.0-687.61.1.el9_8"),
    ("kernel-core", "5.14.0-687.61.1.el9_8.aarch64", "5.14.0-687.61.1.el9_8"),
    ("kernel-modules-core", "5.14.0-687.61.1.el9_8.x86_64", "5.14.0-687.61.1.el9_8"),
    # userland packages built from the kernel source are not the running kernel
    ("kernel-tools", "5.14.0-687.61.1.el9_8.x86_64", ""),
    ("kernel-headers", "5.14.0-687.61.1.el9_8.x86_64", ""),
    ("bash", "5.14.0-687.61.1.el9_8.x86_64", ""),
    # a realtime kernel is the kernel-rt packages, not `kernel`
    ("kernel-rt", "5.14.0-687.61.1.el9_8.x86_64+rt", "5.14.0-687.61.1.el9_8"),
    ("kernel", "5.14.0-687.61.1.el9_8.x86_64+rt", ""),
    ("kernel-rt-core", "4.18.0-553.182.1.rt7.523.el8_10.x86_64", "4.18.0-553.182.1.rt7.523.el8_10"),
    ("kernel", "4.18.0-553.182.1.rt7.523.el8_10.x86_64", ""),
    ("kernel-rt", "5.14.0-687.61.1.el9_8.x86_64", ""),
    # not an rpm kernel release
    ("kernel", "", ""), ("kernel", "Darwin", ""),
])
def test_booted_kernel_build(pg, package, uname, expected):
    assert pg.value("SELECT COALESCE(aac_kernel_booted_evr_for(%s, %s), '')"
                    % (sql_literal(package), sql_literal(uname))) == expected
