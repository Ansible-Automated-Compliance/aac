#!/usr/bin/env python3
"""Offline verification of the response contract + OPA bundle.

Exercises shape.py and bundle.py against synthetic compliance_results rows (no DB,
no web server), asserts the fail-closed contract properties, and writes a sample
bundle to disk so `opa` can load it in a real runtime. Run: python3 tools/verify.py
"""
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.shape import host_state, hosts_summary  # noqa: E402
from app.bundle import build_bundle  # noqa: E402

NOW = dt.datetime(2026, 7, 21, 12, 0, 0, tzinfo=dt.timezone.utc)


def row(host, ip, fw, pct, compliant, ts, violations=None):
    return {
        "hostname": host, "ip_address": ip, "framework": fw,
        "compliance_percentage": pct, "compliant": compliant,
        "passed_controls": None, "failed_controls": None, "total_controls": None,
        "violations": violations, "evaluation_timestamp": ts,
    }


fresh = NOW - dt.timedelta(hours=10)     # 36000s -> fresh
old = NOW - dt.timedelta(hours=34)       # 122400s -> stale (>24h)

rows = [
    row("web-01", "192.0.2.71", "cis_rhel9", 94.67, True, fresh, ["v1", "v2"]),
    row("web-01", "192.0.2.71", "stig_rhel9", 71.0, False, old),
]

# ── Contract assertions (fail-closed) ────────────────────────────────────────
st = host_state("web-01", rows, 86400, now=NOW)
assert st["found"] is True
assert st["frameworks"]["cis_rhel9"]["stale"] is False
assert st["frameworks"]["cis_rhel9"]["age_seconds"] == 36000
assert st["frameworks"]["cis_rhel9"]["violation_count"] == 2
assert st["frameworks"]["stig_rhel9"]["stale"] is True, "34h-old row must be stale"
assert st["summary"]["worst_compliance_percentage"] == 71.0, "aggregate must be worst-case"
assert st["summary"]["all_compliant"] is False
assert st["summary"]["any_stale"] is True

# Unknown host -> found=false, empty frameworks (policy denies on this).
ghost = host_state("nope", [], 86400, now=NOW)
assert ghost["found"] is False and ghost["frameworks"] == {}
assert ghost["summary"]["all_compliant"] is False

# Missing timestamp -> infinitely stale (never reads as fresh).
nots = host_state("x", [row("x", None, "cis_rhel9", 100.0, True, None)], 86400, now=NOW)
assert nots["frameworks"]["cis_rhel9"]["stale"] is True

# NULL compliant flag -> non-compliant.
nullc = host_state("y", [row("y", None, "cis_rhel9", 100.0, None, fresh)], 86400, now=NOW)
assert nullc["frameworks"]["cis_rhel9"]["compliant"] is False

# IP-based lookup returns the same host (rows matched by db.py on hostname OR ip).
print("contract assertions: PASS")

# ── Write a sample bundle for opa to load ────────────────────────────────────
hosts = hosts_summary(rows, 86400, now=NOW)
compliance = {"hosts": {h["hostname"]: h for h in hosts}, "generated_at": NOW.isoformat()}
out = pathlib.Path("/tmp/aac_compliance_bundle.tar.gz")
out.write_bytes(build_bundle(compliance, revision="verify-sample"))
print(f"wrote sample bundle: {out} ({out.stat().st_size} bytes)")
