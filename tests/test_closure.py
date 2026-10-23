"""Tests for scripts/closure.py — the F3 closure-narrative function.

Pins: states are counted correctly, resolved findings are "proven closed"
only when dated by a rescan, waived is distinct from resolved, open age is
computed, the closure rate is right, and ordering puts open (oldest first)
ahead of resolved and waived.
"""
import importlib.util
import pathlib

_root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("closure", _root / "scripts" / "closure.py")
cl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cl)

NOW = "2026-10-05T00:00:00+00:00"


def _f(cid, status, **kw):
    base = {"control_id": cid, "subject": "t", "title": "x", "status": status,
            "first_seen": "2026-09-01T00:00:00+00:00", "last_seen": NOW,
            "resolved_at": None, "times_seen": 3}
    base.update(kw)
    return base


def _r(findings):
    return cl.build({"findings": findings, "now": NOW})


def test_state_counts_and_closure_rate():
    r = _r([_f("1", "open"), _f("2", "resolved", resolved_at="2026-10-01T00:00:00+00:00"),
            _f("3", "waived"), _f("4", "open")])
    s = r["summary"]
    assert s["by_state"] == {"open": 2, "resolved": 1, "waived": 1}
    assert s["closure_rate_pct"] == 50.0  # (1 resolved + 1 waived) / 4
    assert s["proven_closed"] == 1


def test_resolved_is_proven_only_when_dated():
    dated = _r([_f("1", "resolved", resolved_at="2026-10-01T00:00:00+00:00")])
    undated = _r([_f("1", "resolved", resolved_at=None)])
    assert dated["records"][0]["proven_closed"] is True
    assert undated["records"][0]["proven_closed"] is False


def test_waived_distinct_from_resolved():
    r = _r([_f("1", "waived")])
    rec = r["records"][0]
    assert rec["state"] == "waived"
    assert rec["proven_closed"] is False


def test_open_age_computed_and_oldest_reported():
    r = _r([_f("1", "open", first_seen="2026-09-01T00:00:00+00:00"),   # ~34d
            _f("2", "open", first_seen="2026-10-03T00:00:00+00:00")])  # ~2d
    ages = {rec["control_id"]: rec["open_age_days"] for rec in r["records"]}
    assert ages["1"] > ages["2"]
    assert r["summary"]["oldest_open_days"] == ages["1"]


def test_recently_resolved_window():
    r = _r([_f("1", "resolved", resolved_at="2026-10-01T00:00:00+00:00"),   # 4d ago
            _f("2", "resolved", resolved_at="2026-07-01T00:00:00+00:00")])  # >30d ago
    assert r["summary"]["recently_resolved_30d"] == 1


def test_all_closed_verdict():
    r = _r([_f("1", "resolved", resolved_at="2026-10-01T00:00:00+00:00"), _f("2", "waived")])
    assert "Nothing open" in r["summary"]["verdict"]


def test_ordering_open_oldest_first_then_resolved_then_waived():
    r = _r([_f("w", "waived"),
            _f("r", "resolved", resolved_at="2026-10-01T00:00:00+00:00"),
            _f("o1", "open", first_seen="2026-10-03T00:00:00+00:00"),
            _f("o2", "open", first_seen="2026-09-01T00:00:00+00:00")])
    states = [rec["state"] for rec in r["records"]]
    assert states == ["open", "open", "resolved", "waived"]
    # oldest open first
    assert r["records"][0]["control_id"] == "o2"


def test_empty_and_csv():
    r = _r([])
    assert r["summary"]["total"] == 0
    assert "No findings" in r["summary"]["verdict"]
    r2 = _r([_f("1", "open"), _f("2", "resolved", resolved_at="2026-10-01T00:00:00+00:00")])
    csv_text = cl.to_csv(r2)
    assert "State,Control" in csv_text
    assert "yes" in csv_text  # proven-closed marker
