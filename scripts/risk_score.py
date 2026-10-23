#!/usr/bin/env python3
"""F1 — generic, explainable risk scoring for compliance findings.

The decisioning layer's risk function. It ranks findings so no artifact ever
shows "Risk: UNKNOWN". It is framework-agnostic: the scoring logic is generic
code; the only framework-specific knowledge is a small data config.

It reads the FINDINGS layer (compliance_findings), not raw results, because
that is where identity, state, and blast radius live. Each finding carries:
  framework, control_id, subject, finding_type (violation|evidence_gap),
  severity (often NULL for message-based frameworks), title,
  blast_radius (affected_count — how many subjects fail this control).

Risk is derived from signals that are universally present in the findings
layer, with one small per-framework fallback:
  1. severity — when the finding carries one (structured ingests set it);
     mapped by SEVERITY_WEIGHT.
  2. criticality — when severity is absent (e.g. CIS M365), a per-framework
     control-criticality by control-id prefix (the config's job).
  3. blast radius — more systems failing the same control ⇒ higher risk
     (universal; no config needed).
  4. elevators — optional per-framework keyword signals on the title
     (e.g. "legacy auth", "global admin") that raise a finding.

Evidence gaps are never scored as failures — they are surfaced separately as
"unable to assess".

EXPLAINABLE by construction: every finding returns the exact factors that
produced its band. A score a customer cannot interrogate is just a prettier
UNKNOWN.

Input (stdin), one JSON object:
  findings  list of findings (shape above; blast_radius optional, default 1)
  config    the framework risk config: {criticality{prefix:int,_default:int},
            elevators[{match,bump}]}. Absent/empty ⇒ universal defaults only.

Output (stdout): {findings:[...with risk{band,score,factors}], gaps:[...],
by_band:{...}}.
"""
from __future__ import annotations

import json
import re
import sys

# Universal (framework-independent) scoring. Severity and blast radius mean
# the same thing in every framework, so their weights live in code, not config.
SEVERITY_WEIGHT = {"critical": 5, "high": 4, "medium": 3, "low": 1, "info": 0}
BLAST_TIERS = [(10, 2, "affects 10+ systems"), (2, 1, "affects multiple systems")]
BANDS = [(8, "Critical"), (5, "High"), (3, "Medium"), (0, "Low")]
_DEFAULT_CRITICALITY = 2  # neutral base when nothing else is known


def _sort_key(cid: str):
    nums = re.findall(r"\d+", cid)
    return tuple(int(n) for n in nums) if nums else (9999,)


def _criticality(control_id: str, config: dict):
    """Longest-prefix criticality for a control id, from the framework config.
    Returns (weight, matched_prefix_or_default)."""
    crit = (config or {}).get("criticality") or {}
    best = None
    for prefix, weight in crit.items():
        if prefix == "_default":
            continue
        # Match on dotted-segment boundaries so "1.1" matches "1.1.3" but
        # not "1.10"; longest (most specific) matching prefix wins.
        if (control_id == prefix or control_id.startswith(prefix + ".")) and (
                best is None or len(prefix) > len(best[0])):
            best = (prefix, weight)
    if best:
        return int(best[1]), f"criticality {best[1]} (control family {best[0]})"
    dflt = int(crit.get("_default", _DEFAULT_CRITICALITY))
    return dflt, f"criticality {dflt} (default)"


def _band(score: int) -> str:
    for threshold, name in BANDS:
        if score >= threshold:
            return name
    return "Low"


def score_finding(f: dict, config: dict) -> dict:
    factors = []
    sev = (f.get("severity") or "").strip().lower()
    if sev in SEVERITY_WEIGHT:
        base = SEVERITY_WEIGHT[sev]
        factors.append(f"severity: {sev} (base {base})")
    else:
        base, why = _criticality(f["control_id"], config)
        factors.append(why)
    score = base

    affected = int(f.get("blast_radius") or 1)
    for threshold, bump, why in BLAST_TIERS:
        if affected >= threshold:
            score += bump
            factors.append(f"+{bump}: {why} ({affected})")
            break

    title = f.get("title") or ""
    for elev in (config or {}).get("elevators") or []:
        try:
            if re.search(elev["match"], title, re.IGNORECASE):
                bump = int(elev.get("bump", 1))
                score += bump
                factors.append(f"+{bump}: {elev.get('reason', elev['match'])}")
        except re.error:
            continue

    return {"band": _band(score), "score": score, "factors": factors}


def run(payload: dict) -> dict:
    config = payload.get("config") or {}
    scored, gaps = [], []
    for f in payload.get("findings") or []:
        if f.get("finding_type") == "evidence_gap":
            gaps.append({**f, "risk": {"band": "Unable to assess", "score": None,
                                       "factors": ["evidence gap — not an assessed failure"]}})
            continue
        scored.append({**f, "risk": score_finding(f, config)})

    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    scored.sort(key=lambda x: (order[x["risk"]["band"]], -x["risk"]["score"],
                               _sort_key(x["control_id"]), x.get("subject", "")))
    by_band = {b: 0 for b in order}
    for x in scored:
        by_band[x["risk"]["band"]] += 1
    return {"findings": scored, "gaps": gaps, "by_band": by_band,
            "evidence_gaps": len(gaps)}


def to_csv(result: dict) -> str:
    import csv
    import io
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Risk", "Score", "Control", "Subject", "Title", "Risk basis"])
    for x in result["findings"]:
        r = x["risk"]
        w.writerow([r["band"], r["score"], x["control_id"], x.get("subject", ""),
                    x.get("title", ""), "; ".join(r["factors"])])
    for g in result["gaps"]:
        w.writerow(["Unable to assess", "", g["control_id"], g.get("subject", ""),
                    g.get("title", ""), "evidence gap — facts not collected"])
    return out.getvalue()


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
