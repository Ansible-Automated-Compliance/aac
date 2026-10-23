#!/usr/bin/env python3
"""
Parse MITRE HDF/OHDF JSON (the MITRE SAF "Heimdall Data Format") into AAC's
compliance-result shape.

Input: an HDF evaluation document — the output of `inspec ... --reporter json`
(InSpec HDF is a superset) or `saf convert <scanner>2hdf` (Prowler, Nessus,
Burp, Snyk, Twistlock, Zap, …). Deterministic, no network — the testable core
of the MITRE SAF ingestion. HDF is how the SAF ecosystem normalizes 30+
scanners onto one schema tagged with NIST 800-53, so ingesting HDF folds all of
them into the AAC program with one parser.

Shape (the parts we read):
  { "platform": {"name","release"}, "version": "<inspec/hdf version>",
    "statistics": {...},
    "profiles": [ { "name","version","sha256","title","parent_profile"?,
                    "controls": [ { "id","title","desc","impact",
                                    "tags": {"nist":[...],"cci":[...],"severity"},
                                    "results": [ {"status","code_desc","message","skip_message"} ],
                                    "waiver_data": {...}? } ] } ] }

── Classification — the trap this parser exists to get right ─────────────
A control's status is rolled up from its result rows, then mapped to AAC the
SAME WAY the OpenSCAP and goss parsers map theirs, so all three write a
comparable `compliance_percentage` into the same column:

  HDF control status   AAC bucket     matches
  ------------------   -----------    -------------------------------------
  Passed               passed
  Failed               VIOLATION
  Profile Error        VIOLATION      XCCDF `error` is a violation too
  No Impact            excluded       XCCDF `notapplicable` (impact == 0)
  Not Reviewed         excluded       XCCDF `notchecked` / goss `skip`
  (waived)             excluded+kept  waived-never-hidden: own bucket, retained

  denominator (total_evaluated) = passed + failed + profile_error
  compliance_pct                = passed / total_evaluated

`compliance_pct_strict` is the same numerator over a denominator that ALSO
counts Not Reviewed against you — the stricter reading a Heimdall status panel
shows. It is emitted as a SEPARATE, labeled number so the primary
`compliance_pct` stays comparable across every ingested source; it is not
claimed to be byte-identical to a given Heimdall build's math.

No Impact is applied only when `impact` is EXPLICITLY 0 — a control that omits
impact is treated as evaluated (fail-closed), never silently excluded.
"""
from __future__ import annotations

import json
import sys

# ── Canonical HDF control statuses (single source of truth) ──────────────
# The #9 HDF *export* uses the inverse of this map, so it lives in one place.
STATUS_PASSED = "Passed"
STATUS_FAILED = "Failed"
STATUS_PROFILE_ERROR = "Profile Error"
STATUS_NO_IMPACT = "No Impact"
STATUS_NOT_REVIEWED = "Not Reviewed"

# AAC bucket for each control status.
_STATUS_TO_BUCKET = {
    STATUS_PASSED: "passed",
    STATUS_FAILED: "failed",
    STATUS_PROFILE_ERROR: "profile_error",
    STATUS_NO_IMPACT: "no_impact",
    STATUS_NOT_REVIEWED: "not_reviewed",
}
# Buckets that count as a violation, a pass, or the compliance denominator.
_VIOLATION_BUCKETS = {"failed", "profile_error"}
_PASS_BUCKETS = {"passed"}
_DENOMINATOR_BUCKETS = _PASS_BUCKETS | _VIOLATION_BUCKETS  # not_reviewed/no_impact/waived excluded


def _control_status(control: dict) -> str:
    """Roll a control's result rows up to one HDF status.

    Precedence for an evaluated control (impact != 0): an error anywhere makes
    it indeterminate (Profile Error); else any failure makes it Failed; else a
    pass makes it Passed; else (only skips / no rows) it is Not Reviewed.
    """
    impact = control.get("impact", None)
    # Only an EXPLICIT zero impact is No Impact — a missing impact is evaluated.
    if isinstance(impact, (int, float)) and impact == 0:
        return STATUS_NO_IMPACT
    statuses = [
        (r.get("status") or "").strip().lower()
        for r in (control.get("results") or [])
        if isinstance(r, dict)
    ]
    if any(s == "error" for s in statuses):
        return STATUS_PROFILE_ERROR
    if any(s == "failed" for s in statuses):
        return STATUS_FAILED
    if any(s == "passed" for s in statuses):
        return STATUS_PASSED
    return STATUS_NOT_REVIEWED


def _waiver_of(control: dict) -> dict | None:
    """Return the control's waiver_data if it carries a real waiver, else None.

    InSpec waivers arrive as skipped rows with a `waiver_data` object; treating
    them as plain Not Reviewed would drop the justification, so they get their
    own retained bucket (waived-never-hidden).
    """
    wd = control.get("waiver_data")
    if not isinstance(wd, dict) or not wd:
        return None
    if wd.get("skipped_due_to_waiver") or wd.get("justification") or wd.get("message"):
        return wd
    return None


def _tags(control: dict) -> dict:
    tags = control.get("tags") if isinstance(control.get("tags"), dict) else {}
    nist = tags.get("nist")
    cci = tags.get("cci")
    return {
        "nist": nist if isinstance(nist, list) else ([nist] if nist else []),
        "cci": cci if isinstance(cci, list) else ([cci] if cci else []),
        "severity": tags.get("severity", ""),
    }


def _messages(control: dict) -> list[str]:
    """The human-facing evidence lines for a non-passing control."""
    out = []
    for r in control.get("results") or []:
        if not isinstance(r, dict):
            continue
        msg = r.get("message") or r.get("skip_message") or r.get("code_desc")
        if msg:
            out.append(str(msg).strip())
    return out


def parse_hdf_results(text: str) -> dict:
    """Parse an HDF/OHDF document into AAC's compliance-result shape.

    Returns counts, compliance_pct (+ strict variant), by_status, per-control
    records, the violations set, the waived set, and platform/profile identity.
    Raises ValueError on input that is not an HDF document.
    """
    try:
        doc = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("profiles"), list):
        raise ValueError("not an HDF document (no 'profiles' array)")

    # ── Collect controls across all profiles, deduped by id ──────────────
    # HDF can carry a primary profile plus inherited/dependency profiles;
    # flat iteration double-counts. Keep one entry per control id, preferring
    # the one that actually has result rows (the evaluated instance).
    by_id: dict[str, dict] = {}
    profile_meta: list[dict] = []
    for prof in doc["profiles"]:
        if not isinstance(prof, dict):
            continue
        profile_meta.append({
            "name": prof.get("name", ""),
            "version": prof.get("version", ""),
            "title": prof.get("title", ""),
            "sha256": prof.get("sha256", ""),
            "parent_profile": prof.get("parent_profile", ""),
        })
        pname = prof.get("name", "")
        for ctrl in prof.get("controls") or []:
            if not isinstance(ctrl, dict):
                continue
            cid = ctrl.get("id") or ctrl.get("title") or ""
            if not cid:
                continue
            has_results = bool(ctrl.get("results"))
            prev = by_id.get(cid)
            if prev is None or (has_results and not prev.get("results")):
                enriched = dict(ctrl)
                enriched["_profile"] = pname
                by_id[cid] = enriched

    controls: list[dict] = []
    by_status: dict[str, int] = {
        "passed": 0, "failed": 0, "profile_error": 0,
        "not_reviewed": 0, "no_impact": 0, "waived": 0,
    }
    for cid, ctrl in by_id.items():
        status = _control_status(ctrl)
        bucket = _STATUS_TO_BUCKET.get(status, "not_reviewed")
        waiver = _waiver_of(ctrl)
        if waiver is not None:
            # A documented, retained exception — not counted pass or fail.
            bucket = "waived"
        by_status[bucket] = by_status.get(bucket, 0) + 1
        tags = _tags(ctrl)
        rec = {
            "id": cid,
            "title": (ctrl.get("title") or "").strip() or cid,
            "impact": ctrl.get("impact"),
            "severity": tags["severity"],
            "status": status,          # HDF control status
            "bucket": bucket,          # AAC classification
            "nist": tags["nist"],      # 800-53 crosswalk carried through
            "cci": tags["cci"],
            "profile": ctrl.get("_profile", ""),
        }
        if bucket in _VIOLATION_BUCKETS:
            rec["messages"] = _messages(ctrl)
        if waiver is not None:
            rec["waiver_data"] = waiver
        controls.append(rec)

    passed = by_status["passed"]
    violations = [c for c in controls if c["bucket"] in _VIOLATION_BUCKETS]
    failed = len(violations)
    total_evaluated = passed + failed                    # neutral + waived excluded
    # Strict denominator also counts Not Reviewed against the score.
    total_strict = total_evaluated + by_status["not_reviewed"]
    compliance_pct = round(passed / total_evaluated * 100, 2) if total_evaluated else 0.0
    compliance_pct_strict = round(passed / total_strict * 100, 2) if total_strict else 0.0

    platform = doc.get("platform") if isinstance(doc.get("platform"), dict) else {}
    waived = [c for c in controls if c["bucket"] == "waived"]

    return {
        "total_evaluated": total_evaluated,
        "passed": passed,
        "failed": failed,
        "compliance_pct": compliance_pct,
        "compliance_pct_strict": compliance_pct_strict,   # Not Reviewed counted against — labeled, secondary
        "compliant": failed == 0,
        "by_status": by_status,               # full breakdown incl. no_impact/not_reviewed/waived
        "controls": controls,
        "failed_rules": violations,           # what goes into the violations column
        "waived": waived,                     # retained exceptions, surfaced not hidden
        "platform": {"name": platform.get("name", ""), "release": platform.get("release", "")},
        "hdf_version": doc.get("version", ""),
        "profiles": profile_meta,
        "statistics": doc.get("statistics") if isinstance(doc.get("statistics"), dict) else {},
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: hdf_parse.py <hdf-results.json>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        json.dump(parse_hdf_results(fh.read()), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
