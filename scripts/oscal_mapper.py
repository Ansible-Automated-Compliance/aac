#!/usr/bin/env python3
"""
oscal_mapper.py — Maps AAC compliance_results rows to NIST OSCAL 1.1.2
Assessment Results JSON.

Called by export_oscal_assessment.yml via ansible.builtin.script.
Reads JSON from stdin (list of compliance_results rows).
Writes OSCAL JSON or YAML to stdout.

Environment variables:
  OSCAL_VERSION       — e.g. "1.1.2"
  FRAMEWORK           — e.g. "cis_rhel9"
  TOOL_VERSION        — e.g. "1.0.0"
  EXPORT_TIMESTAMP    — ISO 8601, e.g. "2026-05-01T00:00:00+00:00"
  OUTPUT_FORMAT       — "json" (default) or "yaml"
"""

import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone

OSCAL_VERSION = os.environ.get("OSCAL_VERSION", "1.1.2")
FRAMEWORK = os.environ.get("FRAMEWORK", "unknown")
TOOL_VERSION = os.environ.get("TOOL_VERSION", "1.0.0")
EXPORT_TIMESTAMP = os.environ.get("EXPORT_TIMESTAMP", datetime.now(timezone.utc).isoformat())
OUTPUT_FORMAT = os.environ.get("OUTPUT_FORMAT", "json")


def host_uuid(hostname) -> str:
    """Deterministic UUID derived from hostname for stable cross-report references.

    Real compliance_results rows can carry hostname NULL (estate-level and
    OCP-collation records) — surfaced on the first real-data run (job 3543).
    Those map to a stable 'estate' subject rather than crashing the export.
    """
    return str(uuid.UUID(bytes=hashlib.md5((hostname or "estate").encode()).digest()))


def ts(value) -> str:
    """Normalize timestamp to ISO 8601 string."""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def map_violation_to_finding(v: dict, obs_uuid: str) -> dict:
    control_id = v.get("control_id", "unknown")
    satisfied = v.get("severity") is None or v.get("compliant", False)
    return {
        "uuid": str(uuid.uuid4()),
        "title": f"{'Satisfied' if satisfied else 'Not satisfied'}: {control_id}",
        "description": v.get("description", ""),
        "target": {
            "type": "objective-id",
            "target-id": control_id,
            "status": {"state": "satisfied" if satisfied else "not-satisfied"},
        },
        "related-observations": [{"observation-uuid": obs_uuid}],
    }


def map_violation_to_observation(v: dict, host_uuid_val: str, ts_val: str) -> tuple[str, dict]:
    obs_uuid = str(uuid.uuid4())
    control_id = v.get("control_id", "unknown")
    severity = v.get("severity", "medium")
    remediation = v.get("remediation", "Review control and apply remediation.")

    obs = {
        "uuid": obs_uuid,
        "title": f"Control violation: {control_id}",
        "description": v.get("description", ""),
        "methods": ["AUTOMATED"],
        "subjects": [{"subject-uuid": host_uuid_val, "type": "component"}],
        "collected": ts_val,
        "relevant-evidence": [
            {
                "description": (
                    f"Severity: {severity}. "
                    f"Remediation: {remediation}"
                )
            }
        ],
    }
    return obs_uuid, obs


def _parse_string_violation(s: str) -> dict:
    """The shared Rego library emits violations as STRINGS
    ("CIS 4.2.1.1: rsyslog is not installed"). Parse the leading control id so
    string frameworks still produce OSCAL findings/observations."""
    control_id, description = "unknown", s
    if ":" in s:
        head, tail = s.split(":", 1)
        if len(head) <= 40 and len(head.split()) <= 4:
            control_id, description = head.strip(), tail.strip()
    upper = s.upper()
    severity = "critical" if "CRITICAL" in upper else ("high" if "HIGH" in upper else "medium")
    return {"control_id": control_id, "description": description, "severity": severity}


# DISA STIG modules emit object findings as {vuln_id, stig_id, severity ("CAT I"/
# "CAT II"/"CAT III"), rule_title, status, fix_text}. Fold them onto the
# control_id / description / severity / remediation keys the exporter reads, so a
# STIG row exports with its STIG id as the rule instead of "unknown".
_CAT_SEVERITY = {"cat i": "high", "cat ii": "medium", "cat iii": "low"}


def _normalize_violation(v: dict) -> dict:
    if not isinstance(v, dict):
        return v
    out = dict(v)
    if "control_id" not in out:
        for k in ("stig_id", "vuln_id", "id", "control", "rule_id", "recommendation"):
            if out.get(k):
                out["control_id"] = str(out[k])
                break
    if "description" not in out:
        for k in ("rule_title", "title", "text", "msg", "message", "finding"):
            if out.get(k):
                out["description"] = str(out[k])
                break
    if "remediation" not in out and out.get("fix_text"):
        out["remediation"] = str(out["fix_text"])
    sev = str(out.get("severity") or "").strip().lower()
    if sev in _CAT_SEVERITY:
        out["stig_severity"] = out["severity"]
        out["severity"] = _CAT_SEVERITY[sev]
    return out


def row_to_result(row: dict) -> dict:
    h_uuid = host_uuid(row.get("hostname"))
    ts_val = ts(row.get("evaluation_timestamp", EXPORT_TIMESTAMP))
    violations: list = row.get("violations") or []
    if isinstance(violations, str):
        violations = json.loads(violations)

    observations = []
    findings = []

    for v in violations[:50]:
        if isinstance(v, str):
            v = _parse_string_violation(v)
        if not isinstance(v, dict):
            continue
        v = _normalize_violation(v)
        obs_uuid, obs = map_violation_to_observation(v, h_uuid, ts_val)
        observations.append(obs)
        findings.append(map_violation_to_finding(v, obs_uuid))

    # Overall satisfied finding if compliant
    if row.get("compliant") and int(row.get("passed_controls", 0)) > 0:
        findings.append({
            "uuid": str(uuid.uuid4()),
            "title": f"Assessment passed: {row.get('policy_name', FRAMEWORK)}",
            "description": (
                f"{row.get('passed_controls', 0)} of "
                f"{row.get('total_controls', 0)} controls satisfied. "
                f"Compliance: {row.get('compliance_percentage', 0)}%"
            ),
            "target": {
                "type": "objective-id",
                "target-id": f"{FRAMEWORK}.overall",
                "status": {"state": "satisfied"},
            },
            "related-observations": [],
        })

    return {
        "uuid": str(uuid.uuid4()),
        "title": f"{row.get('policy_name', FRAMEWORK)} — {row['hostname']}",
        "description": (
            f"Automated compliance assessment of {row['hostname']} against "
            f"{FRAMEWORK} ({row.get('policy_name', '')}). "
            f"Score: {row.get('compliance_percentage', 0)}% "
            f"({row.get('passed_controls', 0)}/{row.get('total_controls', 0)} controls passed)."
        ),
        "start": ts_val,
        "end": ts_val,
        "reviewed-controls": {
            "control-selections": [
                {
                    "description": f"{FRAMEWORK} controls assessed on {row['hostname']}",
                    "include-all": {},
                }
            ]
        },
        "subjects": [
            {
                "uuid": h_uuid,
                "type": "component",
                "title": row.get("hostname") or "estate",
                "description": f"Managed host: {row['hostname']}",
                "props": [
                    {"name": "hostname", "value": row.get("hostname") or "estate"},
                    {"name": "framework", "value": FRAMEWORK},
                    {"name": "policy-name", "value": row.get("policy_name", "")},
                    {"name": "policy-version", "value": row.get("policy_version", "")},
                ],
            }
        ],
        "observations": observations,
        "findings": findings,
    }


def build_document(rows: list[dict]) -> dict:
    results = [row_to_result(r) for r in rows]
    return {
        "assessment-results": {
            "uuid": str(uuid.uuid4()),
            "metadata": {
                "title": f"AAC Compliance Assessment — {FRAMEWORK}",
                "last-modified": EXPORT_TIMESTAMP,
                "version": TOOL_VERSION,
                "oscal-version": OSCAL_VERSION,
                "props": [
                    {"name": "framework", "value": FRAMEWORK},
                    {"name": "generated-by", "value": "Ansible Automated Compliance (AAC)"},
                ],
                "remarks": (
                    "Generated by Ansible Automated Compliance (AAC). "
                    "Data sourced from PostgreSQL compliance_results table. "
                    "Assessment performed via OPA policy evaluation."
                ),
            },
            "import-ap": {
                "href": f"#assessment-plan-{FRAMEWORK}",
                "remarks": "Assessment plan derived from AAC job template and OPA policy configuration.",
            },
            "results": results,
        }
    }


def main():
    raw = sys.stdin.read().strip()
    rows = json.loads(raw) if raw else []

    doc = build_document(rows)

    if OUTPUT_FORMAT == "yaml":
        try:
            import yaml
            print(yaml.dump(doc, default_flow_style=False, allow_unicode=True))
        except ImportError:
            # Fall back to JSON if PyYAML not available
            print(json.dumps(doc, indent=2, default=str))
    else:
        print(json.dumps(doc, indent=2, default=str))


if __name__ == "__main__":
    main()
