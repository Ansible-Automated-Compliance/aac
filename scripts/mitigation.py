#!/usr/bin/env python3
"""F2 — generic mitigation / remediation guidance for compliance findings.

The decisioning layer's "what to do" function. It pairs each finding with its
fix — where to go, what to do, and the method (manual / automated / governed)
— so a finding reads as a plan, not just a problem. Its absence is precisely
"I cannot use it as it is".

Framework-agnostic by construction: the logic is generic; the guidance itself
is a per-framework mitigation catalog (data). It reads the FINDINGS layer
(compliance_findings) — the same foundation as F1 — and annotates each finding
with its mitigation. F1 (risk) and F2 (mitigation) are independent passes over
the same findings; F4 composes them into reports.

Input (stdin), one JSON object:
  findings  list of findings, each at least {framework, control_id, subject,
            finding_type, title}
  catalog   the framework mitigation catalog: {mitigations:{prefix:{where,
            action, method}}} with a "_default" entry. Absent/empty ⇒ a
            single generic default is used.

Output (stdout): {findings:[...with "mitigation":{where,action,method}]}.

Evidence gaps get a collection-oriented mitigation ("collect the facts"),
since the fix for "unable to assess" is to enable the collection, not to
change a control.
"""
from __future__ import annotations

import json
import sys

_GENERIC = {"where": "the relevant admin console",
            "action": "apply the benchmark-recommended configuration for this control",
            "method": "manual"}
_GAP = {"where": "the assessment collector",
        "action": "enable or fix fact collection for this area so the control can be assessed",
        "method": "manual"}


def _match_prefix(control_id: str, table: dict):
    """Longest dotted-segment-boundary prefix match (so '1.1' matches '1.1.3'
    but not '1.10'). Returns the matched value or None."""
    best = None
    for prefix, value in table.items():
        if prefix == "_default":
            continue
        if (control_id == prefix or control_id.startswith(prefix + ".")) and (
                best is None or len(prefix) > len(best[0])):
            best = (prefix, value)
    return best[1] if best else None


def mitigate(finding: dict, catalog: dict) -> dict:
    table = (catalog or {}).get("mitigations") or {}
    if finding.get("finding_type") == "evidence_gap":
        return dict(_GAP)
    hit = _match_prefix(finding["control_id"], table)
    if hit:
        return {"where": hit.get("where", _GENERIC["where"]),
                "action": hit.get("action", _GENERIC["action"]),
                "method": hit.get("method", "manual")}
    return dict(table.get("_default") or _GENERIC)


def run(payload: dict) -> dict:
    catalog = payload.get("catalog") or {}
    out = [{**f, "mitigation": mitigate(f, catalog)}
           for f in payload.get("findings") or []]
    return {"findings": out}


def to_csv(result: dict) -> str:
    import csv
    import io
    s = io.StringIO()
    w = csv.writer(s)
    w.writerow(["Control", "Subject", "Title", "Where", "Action", "Method"])
    for f in result["findings"]:
        m = f["mitigation"]
        w.writerow([f["control_id"], f.get("subject", ""), f.get("title", ""),
                    m["where"], m["action"], m["method"]])
    return s.getvalue()


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--format", choices=["json", "csv"], default="json")
    args = ap.parse_args()
    result = run(json.load(sys.stdin))
    if args.format == "csv":
        sys.stdout.write(to_csv(result))
    else:
        json.dump(result, sys.stdout, indent=1)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
