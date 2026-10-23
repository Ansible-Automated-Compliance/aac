#!/usr/bin/env python3
"""
Parse goss audit JSON (as emitted by ansible-lockdown's audit) into AAC's
compliance-result shape.

Input: the JSON from `goss ... validate --format json` — a document with a
`results` array (one entry per check) and a `summary`. Deterministic, no
network — the testable core of the ansible-lockdown integration.

Classification (goss `result` codes): 0 = pass, 1 = fail, 2 = skip.
  - pass  -> passed
  - fail  -> violation
  - skip  -> NEUTRAL (excluded from pass AND fail) — counting skips as failures
    is the same garbage-percentage trap as XCCDF notapplicable, so we exclude
    them.
`successful` (bool) is used as a cross-check on the `result` code.

ansible-lockdown gossfiles carry the CIS/STIG control id + description in each
check's `title`/`meta`; we surface those (and keep `meta`) so a later crosswalk
to a control framework needs no re-run.
"""
from __future__ import annotations

import json
import sys

# goss numeric result codes
_PASS, _FAIL, _SKIP = 0, 1, 2


def _title_for(entry: dict) -> str:
    """Best human label for a check: explicit title, else resource coordinates."""
    title = (entry.get("title") or "").strip()
    if title:
        return title
    rtype = entry.get("resource-type", "")
    rid = entry.get("resource-id", "")
    prop = entry.get("property", "")
    return ":".join(p for p in (rtype, rid, prop) if p) or "(unnamed check)"


def parse_goss_results(text: str) -> dict:
    """Parse goss validate --format json into AAC's compliance-result shape.

    Returns total_evaluated, passed, failed, skipped, by_status, compliance_pct,
    compliant, results[], failed_rules[]. Raises ValueError on bad input.
    """
    try:
        doc = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc
    if not isinstance(doc, dict) or "results" not in doc:
        raise ValueError("not a goss results document (no 'results' key)")
    raw = doc.get("results")
    if not isinstance(raw, list):
        raise ValueError("goss 'results' is not a list")

    results: list[dict] = []
    by_status: dict[str, int] = {"pass": 0, "fail": 0, "skip": 0, "unknown": 0}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        code = entry.get("result")
        if code == _PASS:
            status = "pass"
        elif code == _FAIL:
            status = "fail"
        elif code == _SKIP:
            status = "skip"
        else:
            # Code missing/unexpected: fall back to the boolean. `successful:
            # false` is a reliable violation signal, so classify it as fail;
            # reserve "unknown" for a genuinely absent/unknown boolean.
            succ = entry.get("successful")
            status = "pass" if succ is True else ("fail" if succ is False else "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        results.append({
            "title": _title_for(entry),
            "resource_type": entry.get("resource-type", ""),
            "resource_id": entry.get("resource-id", ""),
            "property": entry.get("property", ""),
            "result": status,
            "successful": bool(entry.get("successful", status == "pass")),
            "expected": entry.get("expected"),
            "found": entry.get("found"),
            "meta": entry.get("meta"),   # CIS/STIG control id etc. — future crosswalk
        })

    passed = by_status.get("pass", 0)
    failed_rules = [r for r in results if r["result"] in ("fail", "unknown")]
    failed = len(failed_rules)
    total_evaluated = passed + failed          # skips excluded by design
    compliance_pct = round(passed / total_evaluated * 100, 2) if total_evaluated else 0.0

    summary = doc.get("summary") if isinstance(doc.get("summary"), dict) else {}
    return {
        "total_evaluated": total_evaluated,
        "passed": passed,
        "failed": failed,
        "skipped": by_status.get("skip", 0),
        "compliance_pct": compliance_pct,
        "compliant": failed == 0,
        "by_status": by_status,
        "test_count": summary.get("test-count"),
        "failed_count_reported": summary.get("failed-count"),
        "results": results,
        "failed_rules": failed_rules,   # what goes into the violations column
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: goss_audit_parse.py <goss-results.json>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        json.dump(parse_goss_results(fh.read()), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
