"""Unit tests for the response-shaping contract (no DB, no web server).

Run: pytest integrations/enforceauth/tests -v
Or:  python3 integrations/enforceauth/tools/verify.py   (assertion-style equivalent)
"""
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.shape import host_state, hosts_summary  # noqa: E402

NOW = dt.datetime(2026, 7, 21, 12, 0, 0, tzinfo=dt.timezone.utc)
FRESH = NOW - dt.timedelta(hours=10)   # 36000s
STALE = NOW - dt.timedelta(hours=34)   # 122400s (> 24h)


def _row(host, ip, fw, pct, compliant, ts, violations=None):
    return {
        "hostname": host, "ip_address": ip, "framework": fw,
        "compliance_percentage": pct, "compliant": compliant,
        "passed_controls": None, "failed_controls": None, "total_controls": None,
        "violations": violations, "evaluation_timestamp": ts,
    }


def test_found_host_shapes_per_framework():
    rows = [
        _row("web-01", "10.0.0.5", "cis_rhel9", 94.67, True, FRESH, ["v1", "v2"]),
        _row("web-01", "10.0.0.5", "stig_rhel9", 71.0, False, STALE),
    ]
    st = host_state("web-01", rows, 86400, now=NOW)
    assert st["found"] is True
    assert st["frameworks"]["cis_rhel9"]["age_seconds"] == 36000
    assert st["frameworks"]["cis_rhel9"]["stale"] is False
    assert st["frameworks"]["cis_rhel9"]["violation_count"] == 2
    assert st["frameworks"]["stig_rhel9"]["stale"] is True


def test_summary_aggregate_is_worst_case():
    rows = [
        _row("h", None, "cis_rhel9", 94.67, True, FRESH),
        _row("h", None, "stig_rhel9", 71.0, False, FRESH),
    ]
    st = host_state("h", rows, 86400, now=NOW)
    assert st["summary"]["worst_compliance_percentage"] == 71.0
    assert st["summary"]["all_compliant"] is False


def test_unknown_host_is_fail_closed():
    st = host_state("ghost", [], 86400, now=NOW)
    assert st["found"] is False
    assert st["frameworks"] == {}
    assert st["summary"]["all_compliant"] is False


def test_missing_timestamp_is_infinitely_stale():
    rows = [_row("h", None, "cis_rhel9", 100.0, True, None)]
    st = host_state("h", rows, 86400, now=NOW)
    assert st["frameworks"]["cis_rhel9"]["stale"] is True


def test_null_compliant_reads_as_noncompliant():
    rows = [_row("h", None, "cis_rhel9", 100.0, None, FRESH)]
    st = host_state("h", rows, 86400, now=NOW)
    assert st["frameworks"]["cis_rhel9"]["compliant"] is False


def test_hosts_summary_groups_by_host():
    rows = [
        _row("a", None, "cis_rhel9", 90.0, True, FRESH),
        _row("a", None, "stig_rhel9", 60.0, False, STALE),
        _row("b", None, "cis_rhel9", 99.0, True, FRESH),
    ]
    out = hosts_summary(rows, 86400, now=NOW)
    assert [h["hostname"] for h in out] == ["a", "b"]
    assert out[0]["frameworks"]["stig_rhel9"]["stale"] is True
