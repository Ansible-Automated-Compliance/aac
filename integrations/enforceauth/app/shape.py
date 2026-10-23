"""Pure transforms: compliance_results rows -> the authorization-context contract.

Kept free of DB and web dependencies so the response shape can be unit-tested
directly (see tests/test_shape.py). The contract these produce is the same one
the EnforceAuth policy (policy/enforceauth_authz.rego) consumes.
"""
from __future__ import annotations

from datetime import datetime, timezone


def _age_seconds(ts, now: datetime) -> int:
    """Seconds between an assessment timestamp and now. Naive timestamps from
    compliance_results are treated as UTC (the schema default is UTC)."""
    if ts is None:
        # No timestamp is indistinguishable from infinitely old -> always stale.
        return 2**31 - 1
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0, int((now - ts).total_seconds()))


def _iso(ts) -> str | None:
    if ts is None:
        return None
    if isinstance(ts, str):
        return ts
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.isoformat()


def _framework_entry(row: dict, max_age_seconds: int, now: datetime) -> dict:
    age = _age_seconds(row.get("evaluation_timestamp"), now)
    pct = row.get("compliance_percentage")
    pct = float(pct) if pct is not None else 0.0
    violations = row.get("violations")
    violation_count = len(violations) if isinstance(violations, list) else None
    return {
        "framework": row["framework"],
        # Fail-safe: a NULL/absent compliant flag is treated as non-compliant.
        "compliant": bool(row.get("compliant")) if row.get("compliant") is not None else False,
        "compliance_percentage": pct,
        "passed_controls": row.get("passed_controls"),
        "failed_controls": row.get("failed_controls"),
        "total_controls": row.get("total_controls"),
        "violation_count": violation_count,
        "evaluation_timestamp": _iso(row.get("evaluation_timestamp")),
        "age_seconds": age,
        "stale": age > max_age_seconds,
    }


def host_state(host_key: str, rows: list[dict], max_age_seconds: int,
               now: datetime | None = None) -> dict:
    """Build the per-host authorization-context document.

    An unknown host returns found=false with an empty frameworks map — the
    consuming policy denies on absence, so this stays fail-closed.
    """
    now = now or datetime.now(timezone.utc)
    frameworks = {}
    hostname = None
    ip_address = None
    for row in rows:
        hostname = hostname or row.get("hostname")
        ip_address = ip_address or row.get("ip_address")
        frameworks[row["framework"]] = _framework_entry(row, max_age_seconds, now)

    pcts = [f["compliance_percentage"] for f in frameworks.values()]
    summary = {
        "framework_count": len(frameworks),
        # Worst-case aggregate — a "best score" summary would be fail-open.
        "worst_compliance_percentage": min(pcts) if pcts else None,
        "all_compliant": all(f["compliant"] for f in frameworks.values()) if frameworks else False,
        "any_stale": any(f["stale"] for f in frameworks.values()) if frameworks else False,
    }
    return {
        "host_key": host_key,
        "hostname": hostname,
        "ip_address": ip_address,
        "found": len(frameworks) > 0,
        "generated_at": now.isoformat(),
        "max_age_seconds": max_age_seconds,
        "frameworks": frameworks,
        "summary": summary,
    }


def hosts_summary(rows: list[dict], max_age_seconds: int,
                  now: datetime | None = None) -> list[dict]:
    """Collapse all-host rows into one entry per host with per-framework scores."""
    now = now or datetime.now(timezone.utc)
    by_host: dict[str, dict] = {}
    for row in rows:
        key = row.get("hostname")
        if not key:
            continue
        entry = by_host.setdefault(key, {
            "hostname": key,
            "ip_address": row.get("ip_address"),
            "frameworks": {},
        })
        age = _age_seconds(row.get("evaluation_timestamp"), now)
        pct = row.get("compliance_percentage")
        entry["frameworks"][row["framework"]] = {
            "compliance_percentage": float(pct) if pct is not None else 0.0,
            "compliant": bool(row.get("compliant")) if row.get("compliant") is not None else False,
            "age_seconds": age,
            "stale": age > max_age_seconds,
        }
    return sorted(by_host.values(), key=lambda h: h["hostname"])
