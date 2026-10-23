#!/usr/bin/env python3
"""F3 — evidence-of-closure narrative for compliance findings.

The decisioning layer's retrospective "is it fixed?" function. It shows the
loop in the output: found -> resolved (proven by rescan) / waived (formally
accepted) / still open. This is what turns a report from a scan into a
solution — a reader can see, for any control, whether it is closed and how.

Distinct from F2: F2 is the fix to apply; F3 is the proof it was applied.

It reads the FINDINGS layer (compliance_findings), which is a state machine —
rows are never deleted, only transitioned (open -> resolved | waived). So a
resolved finding is still present, carrying `resolved_at` (the rescan that
proved closure) and `last_seen`. F3 reads findings of ALL statuses, not just
open.

Input (stdin), one JSON object:
  findings  list of findings, each at least {control_id, subject, status
            (open|resolved|waived), first_seen, last_seen, resolved_at,
            times_seen, title}
  now       OPTIONAL ISO timestamp for age math (defaults to current time);
            present so tests are deterministic.

Output (stdout): {summary, records[]}, where summary carries the by-state
counts, a closure rate, the oldest open age, and a plain-language verdict, and
each record is the per-finding closure story.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

_STATES = ("open", "resolved", "waived")


def _parse(ts):
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        s = str(ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _age_days(a, b):
    if not a or not b:
        return None
    return round((b - a).total_seconds() / 86400, 1)


def build(payload: dict) -> dict:
    now = _parse(payload.get("now")) or datetime.now(timezone.utc)
    findings = payload.get("findings") or []

    by_state = {s: 0 for s in _STATES}
    records = []
    open_ages = []
    recently_resolved = 0

    for f in findings:
        state = f.get("status") or "open"
        if state not in by_state:
            state = "open"
        by_state[state] += 1

        first = _parse(f.get("first_seen"))
        resolved = _parse(f.get("resolved_at"))

        if state == "open":
            age = _age_days(first, now)
            if age is not None:
                open_ages.append(age)
            proof = None
        elif state == "resolved":
            # Proven closed only when a rescan dated it. A resolved finding
            # with no resolved_at is resolved-but-undated — surfaced honestly,
            # not presented as proven.
            proof = f.get("resolved_at") if resolved else None
            if resolved and _age_days(resolved, now) is not None and _age_days(resolved, now) <= 30:
                recently_resolved += 1
        else:  # waived
            proof = None

        records.append({
            "control_id": f.get("control_id"),
            "subject": f.get("subject"),
            "title": f.get("title"),
            "state": state,
            "first_seen": f.get("first_seen"),
            "resolved_at": proof,
            "proven_closed": bool(state == "resolved" and resolved),
            "times_seen": f.get("times_seen"),
            "open_age_days": _age_days(first, now) if state == "open" else None,
        })

    total = len(findings)
    addressed = by_state["resolved"] + by_state["waived"]
    closure_rate = round(addressed * 100 / total, 1) if total else None
    oldest_open = max(open_ages) if open_ages else None

    if total == 0:
        verdict = "No findings on record for this scope."
    elif by_state["open"] == 0:
        verdict = (f"All {total} findings are closed — "
                   f"{by_state['resolved']} resolved, {by_state['waived']} waived. "
                   "Nothing open.")
    else:
        parts = [f"{by_state['open']} still open"]
        if by_state["resolved"]:
            parts.append(f"{by_state['resolved']} resolved")
        if by_state["waived"]:
            parts.append(f"{by_state['waived']} waived")
        tail = f" Oldest open finding: {oldest_open} days." if oldest_open is not None else ""
        verdict = ", ".join(parts) + f" of {total}." + tail

    # Order: open first (by oldest), then resolved, then waived.
    rank = {"open": 0, "resolved": 1, "waived": 2}
    records.sort(key=lambda r: (rank[r["state"]],
                                -(r["open_age_days"] or 0),
                                str(r["control_id"]), str(r["subject"])))

    return {
        "summary": {
            "total": total,
            "by_state": by_state,
            "closure_rate_pct": closure_rate,
            "proven_closed": by_state["resolved"],
            "recently_resolved_30d": recently_resolved,
            "oldest_open_days": oldest_open,
            "verdict": verdict,
        },
        "records": records,
    }


def to_csv(result: dict) -> str:
    import csv
    import io
    s = io.StringIO()
    w = csv.writer(s)
    w.writerow(["State", "Control", "Subject", "Title", "Proven closed",
                "Resolved at", "Open age (days)", "Times seen"])
    for r in result["records"]:
        w.writerow([r["state"], r["control_id"], r["subject"], r["title"],
                    "yes" if r["proven_closed"] else "",
                    r["resolved_at"] or "", r["open_age_days"] if r["open_age_days"] is not None else "",
                    r["times_seen"]])
    return s.getvalue()


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--format", choices=["json", "csv"], default="json")
    args = ap.parse_args()
    result = build(json.load(sys.stdin))
    if args.format == "csv":
        sys.stdout.write(to_csv(result))
    else:
        json.dump(result, sys.stdout, indent=1)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
