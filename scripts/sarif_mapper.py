#!/usr/bin/env python3
"""
sarif_mapper.py — Maps AAC compliance_results rows to SARIF 2.1.0.

SARIF (Static Analysis Results Interchange Format, OASIS) is the lingua franca
for security/compliance findings across GitHub code scanning, Azure DevOps, and
most IDEs. Emitting it lets AAC's post-deploy verdicts surface in the same
dashboards teams already use for their pre-apply IaC scanners (Checkov, Trivy,
KICS) — one finding format, plan-time through runtime.

Called by export_sarif_assessment.yml via ansible.builtin.command (stdin).
Reads JSON from stdin (list of compliance_results rows). Writes SARIF JSON to
stdout.

Because infrastructure compliance findings are not tied to a source file, each
finding is placed at a SARIF *logical* location (host + control), not a physical
file/line. That is valid SARIF and is how code-scanning renders non-file
findings.

Environment variables:
  FRAMEWORK         — e.g. "cis_rhel9"
  TOOL_VERSION      — e.g. "1.0.0"
  EXPORT_TIMESTAMP  — ISO 8601
  INFORMATION_URI   — tool homepage (optional)
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

FRAMEWORK = os.environ.get("FRAMEWORK", "unknown")
TOOL_VERSION = os.environ.get("TOOL_VERSION", "1.0.0")
EXPORT_TIMESTAMP = os.environ.get("EXPORT_TIMESTAMP", datetime.now(timezone.utc).isoformat())
INFORMATION_URI = os.environ.get("INFORMATION_URI", "https://github.com/ansible-automated-compliance/aac")

# SARIF result.level is a small closed set. Map AAC severities onto it, and also
# emit GitHub's `security-severity` (0.0-10.0) so code-scanning can rank findings.
_LEVEL = {
    "critical": "error",
    "high": "error",
    "medium": "warning",
    "low": "note",
    "info": "note",
    "informational": "note",
}
_SECURITY_SEVERITY = {
    "critical": "9.5",
    "high": "8.0",
    "medium": "5.0",
    "low": "3.0",
    "info": "1.0",
    "informational": "1.0",
}


def _severity(v: dict) -> str:
    return str(v.get("severity") or "medium").lower()


def _level(sev: str) -> str:
    return _LEVEL.get(sev, "warning")


def _rule_id(control_id: str) -> str:
    # Namespaced so several frameworks' rules never collide in one run's rule set.
    return f"{FRAMEWORK}/{control_id}"


def _parse_string_violation(s: str) -> dict:
    """The shared Rego library emits violations as STRINGS
    ("CIS 4.2.1.1: rsyslog is not installed"), not objects. Parse the leading
    control id off the message so string frameworks still produce findings."""
    control_id, description = "unknown", s
    if ":" in s:
        head, tail = s.split(":", 1)
        # A control id is a short token like "CIS 4.2.1.1", "NIST SC-28" — not a
        # full sentence.
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


def _iter_violations(row: dict):
    violations = row.get("violations") or []
    if isinstance(violations, str):
        violations = json.loads(violations)
    # Some writers (e.g. M365) store a wrapper object {"violations": [...]}
    # rather than a bare array. Unwrap it, or iterating the dict's keys would
    # yield zero findings and silently export a clean result set.
    if isinstance(violations, dict):
        violations = violations.get("violations", []) or []
    for v in violations:
        if isinstance(v, dict):
            yield _normalize_violation(v)
        elif isinstance(v, str):
            yield _parse_string_violation(v)


def build_document(rows: list) -> dict:
    rules: dict = {}          # rule_id -> rule object (deduped across hosts)
    results: list = []

    for row in rows:
        hostname = row.get("hostname") or "estate"
        for v in _iter_violations(row):
            control_id = str(v.get("control_id", "unknown"))
            rule_id = _rule_id(control_id)
            sev = _severity(v)

            if rule_id not in rules:
                rules[rule_id] = {
                    "id": rule_id,
                    "name": control_id.replace(".", "_"),
                    "shortDescription": {"text": v.get("description", control_id) or control_id},
                    "defaultConfiguration": {"level": _level(sev)},
                    "properties": {
                        "framework": FRAMEWORK,
                        "control-id": control_id,
                        "security-severity": _SECURITY_SEVERITY.get(sev, "5.0"),
                        "tags": ["compliance", FRAMEWORK],
                    },
                }

            # Stable fingerprint so re-exports of the same finding coalesce in
            # code-scanning history instead of appearing as new each run.
            fp = hashlib.sha256(f"{hostname}|{rule_id}".encode()).hexdigest()
            message = v.get("description") or f"{control_id} not satisfied on {hostname}"
            remediation = v.get("remediation")
            if remediation:
                message = f"{message} Remediation: {remediation}"

            results.append({
                "ruleId": rule_id,
                "level": _level(sev),
                "message": {"text": message},
                "locations": [{
                    "logicalLocations": [{
                        "name": control_id,
                        "fullyQualifiedName": f"{hostname}/{control_id}",
                        "kind": "resource",
                    }],
                }],
                "partialFingerprints": {"aacFindingHash/v1": fp},
                "properties": {
                    "hostname": hostname,
                    "framework": FRAMEWORK,
                    "severity": sev,
                    "policy-name": row.get("policy_name", ""),
                },
            })

    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "Ansible Automated Compliance (AAC)",
                    "version": TOOL_VERSION,
                    "informationUri": INFORMATION_URI,
                    "rules": list(rules.values()),
                    "properties": {"framework": FRAMEWORK},
                },
            },
            "results": results,
            "invocations": [{
                "executionSuccessful": True,
                "endTimeUtc": EXPORT_TIMESTAMP,
            }],
        }],
    }


def main():
    raw = sys.stdin.read().strip()
    rows = json.loads(raw) if raw else []
    if not isinstance(rows, list):
        rows = [rows]
    print(json.dumps(build_document(rows), indent=2, default=str))


if __name__ == "__main__":
    main()
