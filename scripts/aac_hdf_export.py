#!/usr/bin/env python3
"""
Export an AAC compliance result to MITRE HDF/OHDF JSON.

The inverse of hdf_parse.py: take a normalized AAC finding set and emit a valid
Heimdall Data Format document, so an AAC assessment (OPA/Rego, or anything AAC
already ingested) can be opened in Heimdall and consumed by the MITRE SAF
tooling alongside every other scanner — the same universal shape, from the other
direction.

Input (AAC finding set):
  { "hostname": "web01", "framework": "cis_rhel9", "policy_version": "2.0.0",
    "controls": [
      { "id": "1.1.1", "title": "...", "bucket": "passed|failed|profile_error|
                                                  not_reviewed|no_impact|waived",
        "severity": "high", "impact": 0.7?, "nist": ["AC-3"], "cci": ["CCI-..."],
        "message": "..."?, "waiver_data": {...}? } ] }

`bucket` is AAC's own classification (what hdf_parse.py emits). `status` (an HDF
control status) is accepted as an alternative. Impact is taken as given, else
derived from severity; No Impact is emitted as impact 0 with no result rows.

This shares its status vocabulary with hdf_parse.py (STATUS_* / _STATUS_TO_BUCKET)
so ingest and export can never drift out of lock step.
"""
from __future__ import annotations

import json
import sys

from hdf_parse import (  # single source of truth for the status vocabulary
    STATUS_FAILED,
    STATUS_NO_IMPACT,
    STATUS_NOT_REVIEWED,
    STATUS_PASSED,
    STATUS_PROFILE_ERROR,
    _STATUS_TO_BUCKET,
)

# Inverse of _STATUS_TO_BUCKET (waived is not an HDF status — it maps to a
# skipped result carrying waiver_data, so it is handled explicitly below).
_BUCKET_TO_STATUS = {v: k for k, v in _STATUS_TO_BUCKET.items()}

# HDF control status -> the InSpec result-row status the reporter emits.
_STATUS_TO_RESULT = {
    STATUS_PASSED: "passed",
    STATUS_FAILED: "failed",
    STATUS_PROFILE_ERROR: "error",
    STATUS_NOT_REVIEWED: "skipped",
    # No Impact emits no result rows at all (impact 0).
}

# Default control impact by severity when a control gives no explicit impact.
_SEVERITY_IMPACT = {"critical": 0.9, "high": 0.7, "medium": 0.5, "low": 0.3, "none": 0.0, "info": 0.0}
_DEFAULT_IMPACT = 0.5


def _bucket_of(control: dict) -> str:
    """The AAC bucket for a control, from `bucket` or an HDF `status`."""
    b = (control.get("bucket") or "").strip().lower()
    if b:
        return b
    status = (control.get("status") or "").strip()
    return _STATUS_TO_BUCKET.get(status, "not_reviewed")


def _impact_of(control: dict, bucket: str) -> float:
    if bucket == "no_impact":
        return 0.0
    impact = control.get("impact")
    if isinstance(impact, (int, float)):
        return float(impact)
    sev = (control.get("severity") or "").strip().lower()
    return _SEVERITY_IMPACT.get(sev, _DEFAULT_IMPACT)


def _result_rows(control: dict, bucket: str) -> list[dict]:
    """The HDF result rows for a control, from its AAC bucket."""
    if bucket == "no_impact":
        return []                       # impact 0 carries no result rows
    if bucket == "waived":
        wd = control.get("waiver_data") or {}
        msg = wd.get("justification") or wd.get("message") or "waived"
        return [{"status": "skipped", "skip_message": f"Skipped due to waiver: {msg}"}]
    status = _BUCKET_TO_STATUS.get(bucket, STATUS_NOT_REVIEWED)
    result_status = _STATUS_TO_RESULT.get(status, "skipped")
    code_desc = control.get("message") or control.get("title") or control.get("id", "")
    row: dict = {"status": result_status, "code_desc": str(code_desc)}
    if result_status in ("failed", "error"):
        row["message"] = str(control.get("message") or code_desc)
    elif result_status == "skipped":
        row["skip_message"] = str(control.get("message") or "not reviewed")
    return [row]


def _control_to_hdf(control: dict) -> dict:
    bucket = _bucket_of(control)
    cid = control.get("id") or control.get("title") or ""
    tags: dict = {}
    if control.get("nist"):
        tags["nist"] = control["nist"] if isinstance(control["nist"], list) else [control["nist"]]
    if control.get("cci"):
        tags["cci"] = control["cci"] if isinstance(control["cci"], list) else [control["cci"]]
    if control.get("severity"):
        tags["severity"] = control["severity"]
    hdf: dict = {
        "id": cid,
        "title": control.get("title") or cid,
        "desc": control.get("desc", ""),
        "impact": _impact_of(control, bucket),
        "tags": tags,
        "results": _result_rows(control, bucket),
    }
    if bucket == "waived" and control.get("waiver_data"):
        hdf["waiver_data"] = control["waiver_data"]
    return hdf


def export_hdf(aac_result: dict) -> dict:
    """Build an HDF/OHDF document from an AAC finding set.

    Raises ValueError if there is no `controls` list to export.
    """
    if not isinstance(aac_result, dict) or not isinstance(aac_result.get("controls"), list):
        raise ValueError("AAC result has no 'controls' list to export")
    framework = aac_result.get("framework") or "aac"
    hostname = aac_result.get("hostname") or ""
    controls = [_control_to_hdf(c) for c in aac_result["controls"] if isinstance(c, dict)]
    return {
        # Minimal, valid HDF: SAF/Heimdall key off platform + profiles[].controls[].
        "platform": {"name": aac_result.get("platform_name", "aac"), "release": aac_result.get("platform_release", "")},
        "version": "AAC-export/1.0",
        "statistics": {},
        "profiles": [
            {
                "name": framework,
                "version": aac_result.get("policy_version", ""),
                "title": aac_result.get("policy_name", f"AAC {framework} assessment"),
                "sha256": aac_result.get("policy_sha256", ""),
                "summary": f"AAC assessment of {hostname or 'target'} against {framework}",
                "controls": controls,
                "attributes": [],
            }
        ],
        # AAC provenance kept in passthrough so a re-ingest keeps the asset identity
        # HDF itself does not carry.
        "passthrough": {
            "auxiliary_data": [{"name": "AAC", "data": {
                "hostname": hostname,
                "framework": framework,
                "exported_by": "AAC aac_hdf_export/1.0",
            }}],
        },
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: aac_hdf_export.py <aac-result.json>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        json.dump(export_hdf(json.load(fh)), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
