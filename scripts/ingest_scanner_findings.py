#!/usr/bin/env python3
"""
ingest_scanner_findings.py — normalize a pre-apply IaC scanner's JSON output into
AAC's compliance_results shape, so plan-time findings land on the same PostgreSQL
timeline as post-deploy verdicts (gap-analysis item #3).

Supports Checkov and Trivy (config/misconfiguration) JSON. Auto-detects the
format, or force it with SCANNER=checkov|trivy.

Input: reads the scanner JSON from the file named by SCANNER_FILE if that
environment variable is set, otherwise from stdin. SCANNER_FILE TAKES PRECEDENCE
over stdin — the Ansible caller passes the path this way because piping JSON
through Ansible's stdin templating coerces it into a Python dict-repr that is not
valid JSON. stdin remains supported for CLI piping.

Writes a single JSON object to stdout with the fields the aac_store_results role
consumes:

  { framework, policy_name, policy_version, total_controls, passed_controls,
    failed_controls, compliance_pct, compliant, hostname, violations[], metadata }

`hostname` here is the stack/repo subject (IaC has no host); pass SUBJECT to set
it, else "iac-scan".

Environment:
  SCANNER_FILE     — path to the scanner JSON; if set, read from it (wins over stdin)
  SCANNER          — checkov | trivy | auto (default auto)
  SUBJECT          — evidence subject (repo/stack id); default "iac-scan"
  POLICY_VERSION   — scanner version string; default "unknown"
"""

import json
import os
import sys

SCANNER = os.environ.get("SCANNER", "auto").lower()
SUBJECT = os.environ.get("SUBJECT", "iac-scan")
POLICY_VERSION = os.environ.get("POLICY_VERSION", "unknown")

_SEV = {"CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium", "LOW": "low", "INFO": "low", "UNKNOWN": "medium"}


def _sev(s) -> str:
    return _SEV.get(str(s or "MEDIUM").upper(), "medium")


def detect(doc) -> str:
    if SCANNER in ("checkov", "trivy"):
        return SCANNER
    if isinstance(doc, list) and doc and isinstance(doc[0], dict) and "results" in doc[0]:
        return "checkov"
    if isinstance(doc, dict):
        if "check_type" in doc or "results" in doc:
            return "checkov"
        if "Results" in doc or "SchemaVersion" in doc:
            return "trivy"
    raise ValueError("could not detect scanner format; set SCANNER=checkov|trivy")


def _from_checkov(doc):
    # Checkov emits either one object or a list of per-framework objects.
    blocks = doc if isinstance(doc, list) else [doc]
    passed = failed = 0
    violations = []
    check_types = set()
    for b in blocks:
        if not isinstance(b, dict):
            continue
        check_types.add(b.get("check_type", "iac"))
        res = b.get("results", {}) or {}
        passed += len(res.get("passed_checks", []) or [])
        for f in res.get("failed_checks", []) or []:
            violations.append({
                "control_id": f.get("check_id", "unknown"),
                "description": f.get("check_name", ""),
                "severity": _sev(f.get("severity")),
                "resource": f.get("resource", ""),
                "file": f.get("file_path", ""),
                "guideline": f.get("guideline", ""),
            })
        failed += len(res.get("failed_checks", []) or [])
    ct = "_".join(sorted(check_types)) if check_types else "iac"
    return f"checkov_{ct}", "Checkov", passed, failed, violations


def _from_trivy(doc):
    passed = failed = 0
    violations = []
    types = set()
    for r in doc.get("Results", []) or []:
        types.add(r.get("Type", "config"))
        summ = r.get("MisconfSummary") or {}
        passed += int(summ.get("Successes", 0) or 0)
        for m in r.get("Misconfigurations", []) or []:
            if str(m.get("Status", "FAIL")).upper() == "PASS":
                passed += 1
                continue
            failed += 1
            violations.append({
                "control_id": m.get("ID", "unknown"),
                "description": m.get("Title", "") or m.get("Description", ""),
                "severity": _sev(m.get("Severity")),
                "resource": r.get("Target", ""),
                "file": r.get("Target", ""),
                "guideline": (m.get("References") or [""])[0] if m.get("References") else "",
            })
    ty = "_".join(sorted(types)) if types else "config"
    return f"trivy_{ty}", "Trivy", passed, failed, violations


def build(doc) -> dict:
    kind = detect(doc)
    framework, policy_name, passed, failed, violations = (
        _from_checkov(doc) if kind == "checkov" else _from_trivy(doc)
    )
    total = passed + failed
    pct = round((passed / total) * 100, 2) if total else 100.0
    return {
        "framework": framework,
        "policy_name": policy_name,
        "policy_version": POLICY_VERSION,
        "total_controls": total,
        "passed_controls": passed,
        "failed_controls": failed,
        "compliance_pct": pct,
        "compliant": failed == 0,
        "hostname": SUBJECT,
        "violations": violations,
        "metadata": {
            "source": policy_name.lower(),
            "scanner": kind,
            "evidence_stage": "pre-apply",
            "framework": framework,
            "hostname": SUBJECT,
            "compliant": failed == 0,
        },
    }


def main():
    # Prefer reading the file directly (SCANNER_FILE) over stdin. Passing JSON
    # file content through Ansible's stdin templating coerces it into a Python
    # dict repr (single quotes), which is not valid JSON — reading the file here
    # avoids that round-trip entirely. stdin remains supported for CLI piping.
    scanner_file = os.environ.get("SCANNER_FILE", "")
    if scanner_file:
        with open(scanner_file) as fh:
            raw = fh.read().strip()
    else:
        raw = sys.stdin.read().strip()
    doc = json.loads(raw) if raw else {}
    print(json.dumps(build(doc), indent=2, default=str))


if __name__ == "__main__":
    main()
