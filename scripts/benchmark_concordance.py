#!/usr/bin/env python3
"""Concord AAC assessment results with a manual (human) benchmark assessment.

The POC proof point is not "AAC found violations" — it is "here is where the
automated assessment and your own manual assessment agree, and here is every
place they differ, with the reason". This script is that comparison's
deterministic, testable core: rows in, verdicts out, no I/O beyond
stdin/stdout (mirroring scripts/findings_extract.py — the
cis_benchmark_comparison.yml playbook owns DB access and rendering).

Input (stdin), one JSON object:
  aac_rows   compliance_results rows for ONE framework + subject (latest per
             policy_name), each at least {"policy_name", "violations",
             "metadata"}
  coverage   the generated coverage file for the benchmark (see
             scripts/generate_benchmark_coverage.py): catalog +
             evaluated / requires_attestation / unresolved / not_implemented
  manual     OPTIONAL list of the customer's manual assessment rows, already
             parsed from CSV: [{"control_id", "result", "notes"?}, ...]
  crosswalk  OPTIONAL {their_id: benchmark_id} mapping, for manual artifacts
             using a different benchmark version's numbering
  pass_values / fail_values
             OPTIONAL lowercase strings counted as manual pass / fail
             (defaults below); anything else is manual_status "other"

Output (stdout), one JSON object:
  controls   one entry per benchmark control (plus any manual-only ids that
             match nothing in the catalog):
             {control_id, section, section_name, cis_assessment,
              aac_status, aac_detail, manual_status, manual_notes, agreement}
  summary    counts per aac_status, per agreement class, and coverage totals
  evidence_gaps  violation messages that are gaps/attestation-misses, not
             assessed failures — listed so a reader sees WHY a control is
             not_assessed

AAC status per control:
  fail          a stored violation names this control as an assessed failure
  pass          in the evaluated set, no violation names it
  not_assessed  the stored message itself says it is not an assessed result
                ("(this is not a pass)": missing attestation, facts not
                collected) — never silently counted as pass OR fail
  attested      requires_attestation and no attestation violation remains
                (an admissible attestation was recorded — a human assertion,
                not a measurement; kept distinct from pass)
  not_covered   unresolved / not_implemented: AAC currently has no path

Agreement classes:
  agree_fail / agree_pass          both assessed it, same answer
  aac_fail_manual_pass / aac_pass_manual_fail   both assessed it, different
  manual_only   the manual assessment answered it; AAC did not assess it
  aac_only      AAC assessed it; the manual artifact does not mention it
  neither       nobody assessed it
"""
from __future__ import annotations

import json
import re
import sys

_CONTROL_ID = re.compile(r"CIS (?:L2 )?(?:M365 )?(\d+(?:\.\d+)*)")
_NOT_A_PASS = re.compile(r"\(this is not a pass\)", re.IGNORECASE)
_FAIL_CLOSED = re.compile(r"^FAIL-CLOSED\b", re.IGNORECASE)

DEFAULT_PASS = ["pass", "passed", "compliant", "yes", "met", "true", "ok", "implemented"]
DEFAULT_FAIL = ["fail", "failed", "non-compliant", "noncompliant", "no", "not met", "false", "open"]


def _sort_key(cid: str):
    try:
        return (0, tuple(int(p) for p in cid.split(".")))
    except ValueError:
        return (1, (cid,))


def _classify_violations(rows: list[dict]) -> tuple[set[str], set[str], list[str]]:
    """(assessed_fail_ids, not_assessed_ids, gap_messages) from stored rows.

    A message carrying "(this is not a pass)" or a FAIL-CLOSED prefix is the
    policy telling us this is an evidence gap or a missing attestation — an
    unassessed control, which is a different actionable than a failed one.
    """
    fails: set[str] = set()
    gaps: set[str] = set()
    gap_msgs: list[str] = []
    for row in rows:
        for v in row.get("violations") or []:
            if not isinstance(v, str):
                continue
            m = _CONTROL_ID.search(v)
            if _NOT_A_PASS.search(v) or _FAIL_CLOSED.match(v):
                if m:
                    gaps.add(m.group(1))
                gap_msgs.append(v)
            elif m:
                fails.add(m.group(1))
    # A control with both a real failure and a gap message is a failure.
    return fails, gaps - fails, gap_msgs


def _manual_index(manual: list[dict], crosswalk: dict[str, str],
                  pass_values: list[str], fail_values: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in manual:
        cid = str(row.get("control_id", "")).strip()
        if not cid:
            continue
        cid = crosswalk.get(cid, cid)
        raw = str(row.get("result", "")).strip()
        lowered = raw.lower()
        if lowered in pass_values:
            status = "pass"
        elif lowered in fail_values:
            status = "fail"
        else:
            status = "other"
        # Last row for an id wins, but never let a parseable verdict be
        # overwritten by an unparseable one.
        if cid in out and status == "other" and out[cid]["status"] != "other":
            continue
        out[cid] = {"status": status, "raw": raw,
                    "notes": str(row.get("notes", "")).strip()}
    return out


def _agreement(aac: str, manual: str | None) -> str:
    aac_assessed = aac in ("pass", "fail")
    man_assessed = manual in ("pass", "fail")
    if aac_assessed and man_assessed:
        if aac == manual:
            return f"agree_{aac}"
        return f"aac_{aac}_manual_{manual}"
    if man_assessed:
        return "manual_only"
    if aac_assessed:
        return "aac_only"
    return "neither"


def concord(payload: dict) -> dict:
    coverage = payload["coverage"]
    evaluated = set(coverage.get("evaluated") or [])
    attestation = set(coverage.get("requires_attestation") or [])
    no_path = set(coverage.get("unresolved") or []) | set(coverage.get("not_implemented") or [])
    catalog = {c["control_id"]: c for c in coverage.get("catalog") or []}

    fails, gaps, gap_msgs = _classify_violations(payload.get("aac_rows") or [])
    # A "pass" claim for a control needs its section's row to actually be in
    # the window — an absent section is an unassessed section, and silence
    # must never read as a pass. policy_name is "<framework>.<section>".
    sections_present = {
        str(row.get("policy_name", "")).rsplit(".", 1)[-1]
        for row in payload.get("aac_rows") or []
    }
    manual = _manual_index(
        payload.get("manual") or [],
        payload.get("crosswalk") or {},
        [v.lower() for v in payload.get("pass_values") or DEFAULT_PASS],
        [v.lower() for v in payload.get("fail_values") or DEFAULT_FAIL],
    )
    has_manual = bool(payload.get("manual"))
    has_rows = bool(payload.get("aac_rows"))

    all_ids = set(catalog) | set(manual) | fails | gaps
    controls = []
    for cid in sorted(all_ids, key=_sort_key):
        cat = catalog.get(cid)
        if cid in fails:
            aac_status, detail = "fail", "assessed failure stored in compliance_results"
        elif cid in gaps:
            aac_status, detail = "not_assessed", "stored result says this is not an assessed pass/fail (evidence gap or attestation not recorded)"
        elif cid in attestation:
            # No remaining attestation violation for it: either an admissible
            # attestation exists, or no assessment rows were supplied at all.
            if has_rows and "attestation" in sections_present:
                aac_status, detail = "attested", "operator attestation on record (human assertion, not a measurement)"
            else:
                aac_status, detail = "not_assessed", "requires operator attestation; no attestation row in the window"
        elif cid in evaluated:
            if not has_rows:
                aac_status, detail = "not_assessed", "no assessment rows supplied"
            elif (cat or {}).get("section", "") in sections_present:
                aac_status, detail = "pass", "evaluated; no stored violation names this control"
            else:
                aac_status, detail = "not_assessed", (
                    f"no stored row for section {(cat or {}).get('section', '?')} "
                    "in the window — absence is not a pass")
        elif cid in no_path:
            aac_status, detail = "not_covered", "AAC currently has no automated or attestation path for this control"
        elif cat is None:
            aac_status, detail = "not_in_benchmark", "id not in the benchmark catalog (version mismatch? add a crosswalk entry)"
        else:
            aac_status, detail = "not_covered", "not claimed by the policy package"

        man = manual.get(cid)
        controls.append({
            "control_id": cid,
            "section": (cat or {}).get("section", ""),
            "section_name": (cat or {}).get("section_name", ""),
            "cis_assessment": (cat or {}).get("cis_assessment", ""),
            "aac_status": aac_status,
            "aac_detail": detail,
            "manual_status": (man or {}).get("status", "not_in_manual" if has_manual else "not_supplied"),
            "manual_raw": (man or {}).get("raw", ""),
            "manual_notes": (man or {}).get("notes", ""),
            "agreement": _agreement(aac_status, (man or {}).get("status")) if has_manual else "no_manual_input",
        })

    by_aac: dict[str, int] = {}
    by_agreement: dict[str, int] = {}
    for c in controls:
        by_aac[c["aac_status"]] = by_aac.get(c["aac_status"], 0) + 1
        by_agreement[c["agreement"]] = by_agreement.get(c["agreement"], 0) + 1

    both = sum(by_agreement.get(k, 0) for k in
               ("agree_pass", "agree_fail", "aac_fail_manual_pass", "aac_pass_manual_fail"))
    agree = by_agreement.get("agree_pass", 0) + by_agreement.get("agree_fail", 0)

    return {
        "controls": controls,
        "evidence_gaps": gap_msgs,
        "summary": {
            "benchmark": coverage.get("benchmark", ""),
            "benchmark_version": coverage.get("benchmark_version", ""),
            "benchmark_total_controls": coverage.get("benchmark_total_controls", len(catalog)),
            "aac_status_counts": by_aac,
            "agreement_counts": by_agreement,
            "both_assessed": both,
            "agree": agree,
            "agreement_rate_pct": round(agree * 100 / both, 1) if both else None,
            "manual_rows_supplied": len(payload.get("manual") or []),
            "manual_controls_matched": sum(1 for c in controls if c["manual_status"] in ("pass", "fail", "other")),
        },
    }


def _read_manual_csv(path: str, col_control: str, col_result: str,
                     col_notes: str) -> list[dict]:
    import csv
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            sys.exit(f"ERROR: {path} is empty — no CSV header row")
        headers = {h.strip().lower(): h for h in reader.fieldnames}
        missing = [c for c in (col_control, col_result) if c.lower() not in headers]
        if missing:
            sys.exit(f"ERROR: {path} has no column(s) {missing}; "
                     f"found {reader.fieldnames}. Set the column-mapping "
                     "variables to match the artifact's headers.")
        rows = []
        for r in reader:
            rows.append({
                "control_id": (r.get(headers[col_control.lower()]) or "").strip(),
                "result": (r.get(headers[col_result.lower()]) or "").strip(),
                "notes": (r.get(headers[col_notes.lower()]) or "").strip()
                if col_notes and col_notes.lower() in headers else "",
            })
        return rows


def _read_crosswalk_csv(path: str) -> dict[str, str]:
    import csv
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        cols = [h.strip().lower() for h in reader.fieldnames or []]
        if not {"their_id", "benchmark_id"} <= set(cols):
            sys.exit(f"ERROR: crosswalk {path} needs columns their_id,benchmark_id; "
                     f"found {reader.fieldnames}")
        return {
            r[(reader.fieldnames or [])[cols.index("their_id")]].strip():
            r[(reader.fieldnames or [])[cols.index("benchmark_id")]].strip()
            for r in reader if r
        }


def _write_csvs(result: dict, out_dir: str, tag: str, with_manual: bool) -> list[str]:
    import csv
    import os
    written = []
    verdicts = os.path.join(out_dir, f"aac_control_verdicts-{tag}.csv")
    with open(verdicts, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["control_id", "section", "section_name", "cis_assessment",
                    "aac_status", "aac_detail"])
        for c in result["controls"]:
            if c["aac_status"] == "not_in_benchmark":
                continue
            w.writerow([c["control_id"], c["section"], c["section_name"],
                        c["cis_assessment"], c["aac_status"], c["aac_detail"]])
    written.append(verdicts)
    if with_manual:
        conc = os.path.join(out_dir, f"benchmark_concordance-{tag}.csv")
        with open(conc, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["control_id", "section", "section_name", "cis_assessment",
                        "aac_status", "manual_status", "manual_raw", "agreement",
                        "aac_detail", "manual_notes"])
            for c in result["controls"]:
                w.writerow([c["control_id"], c["section"], c["section_name"],
                            c["cis_assessment"], c["aac_status"], c["manual_status"],
                            c["manual_raw"], c["agreement"], c["aac_detail"],
                            c["manual_notes"]])
        written.append(conc)
    return written


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manual-csv", help="customer manual-assessment CSV")
    ap.add_argument("--manual-col-control", default="control_id")
    ap.add_argument("--manual-col-result", default="result")
    ap.add_argument("--manual-col-notes", default="notes")
    ap.add_argument("--crosswalk-csv", help="CSV with columns their_id,benchmark_id")
    ap.add_argument("--csv-out-dir", help="also write verdict/concordance CSVs here")
    ap.add_argument("--csv-tag", default="run", help="filename tag for CSV outputs")
    args = ap.parse_args()

    payload = json.load(sys.stdin)
    if args.manual_csv:
        payload["manual"] = _read_manual_csv(
            args.manual_csv, args.manual_col_control,
            args.manual_col_result, args.manual_col_notes)
    if args.crosswalk_csv:
        payload["crosswalk"] = _read_crosswalk_csv(args.crosswalk_csv)

    result = concord(payload)
    if args.csv_out_dir:
        result["csv_files"] = _write_csvs(
            result, args.csv_out_dir, args.csv_tag, bool(payload.get("manual")))
    json.dump(result, sys.stdout, indent=1)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
