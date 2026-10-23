"""Unit tests for scripts/ingest_scanner_findings.py (Checkov + Trivy → AAC shape)."""
from __future__ import annotations

import importlib
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))


def _mod(**env):
    # The module reads env at import time; reload under the requested env.
    for k in ("SCANNER", "SUBJECT", "POLICY_VERSION"):
        os.environ.pop(k, None)
    os.environ.update(env)
    import ingest_scanner_findings as m
    return importlib.reload(m)


_CHECKOV = {
    "check_type": "terraform",
    "results": {
        "passed_checks": [{"check_id": "CKV_AWS_20"}, {"check_id": "CKV_AWS_21"}],
        "failed_checks": [
            {"check_id": "CKV_AWS_18", "check_name": "S3 access logging", "file_path": "/main.tf",
             "resource": "aws_s3_bucket.data", "severity": "LOW"},
            {"check_id": "CKV_AWS_19", "check_name": "S3 encryption at rest", "file_path": "/main.tf",
             "resource": "aws_s3_bucket.data", "severity": "HIGH"},
        ],
    },
    "summary": {"passed": 2, "failed": 2},
}

_TRIVY = {
    "SchemaVersion": 2,
    "Results": [
        {"Target": "main.tf", "Class": "config", "Type": "terraform",
         "MisconfSummary": {"Successes": 3, "Failures": 1},
         "Misconfigurations": [
             {"ID": "AVD-AWS-0088", "Title": "S3 bucket not encrypted", "Severity": "HIGH", "Status": "FAIL"},
         ]},
    ],
}


def test_checkov_mapping():
    m = _mod(SUBJECT="infra-repo", POLICY_VERSION="3.2.0")
    out = m.build(_CHECKOV)
    assert out["framework"] == "checkov_terraform"
    assert out["policy_name"] == "Checkov"
    assert out["total_controls"] == 4
    assert out["passed_controls"] == 2
    assert out["failed_controls"] == 2
    assert out["compliance_pct"] == 50.0
    assert out["compliant"] is False
    assert out["hostname"] == "infra-repo"
    sev = {v["control_id"]: v["severity"] for v in out["violations"]}
    assert sev["CKV_AWS_19"] == "high"
    assert sev["CKV_AWS_18"] == "low"
    assert out["metadata"]["evidence_stage"] == "pre-apply"


def test_checkov_list_form():
    m = _mod()
    out = m.build([_CHECKOV, {"check_type": "dockerfile", "results": {"passed_checks": [{"check_id": "X"}], "failed_checks": []}}])
    # two check_types merge; passed accumulates (2 + 1), failed 2
    assert out["passed_controls"] == 3
    assert out["failed_controls"] == 2
    assert "dockerfile" in out["framework"] and "terraform" in out["framework"]


def test_trivy_mapping():
    m = _mod(SUBJECT="stack-a")
    out = m.build(_TRIVY)
    assert out["framework"] == "trivy_terraform"
    assert out["policy_name"] == "Trivy"
    assert out["passed_controls"] == 3
    assert out["failed_controls"] == 1
    assert out["total_controls"] == 4
    assert out["compliance_pct"] == 75.0
    assert out["violations"][0]["control_id"] == "AVD-AWS-0088"
    assert out["violations"][0]["severity"] == "high"


def test_clean_scan_is_compliant():
    m = _mod()
    out = m.build({"check_type": "terraform", "results": {"passed_checks": [{"check_id": "A"}], "failed_checks": []}})
    assert out["compliant"] is True
    assert out["compliance_pct"] == 100.0
    assert out["failed_controls"] == 0


def test_forced_scanner_env():
    m = _mod(SCANNER="trivy")
    out = m.build(_TRIVY)
    assert out["policy_name"] == "Trivy"


def test_empty_results_do_not_divide_by_zero():
    m = _mod()
    out = m.build({"check_type": "terraform", "results": {"passed_checks": [], "failed_checks": []}})
    assert out["total_controls"] == 0
    assert out["compliance_pct"] == 100.0
    assert out["compliant"] is True


def test_scanner_file_is_read_and_wins_over_stdin(tmp_path):
    # Regression for the production path: main() must read SCANNER_FILE and it
    # must take precedence over stdin (stdin here is deliberately invalid JSON).
    import json
    import subprocess

    script = os.path.join(_REPO, "scripts", "ingest_scanner_findings.py")
    plan = tmp_path / "checkov.json"
    plan.write_text(json.dumps(_CHECKOV))
    env = dict(os.environ, SCANNER_FILE=str(plan), SUBJECT="repo-x")
    for k in ("SCANNER", "POLICY_VERSION"):
        env.pop(k, None)
    proc = subprocess.run(
        [sys.executable, script],
        input="{ not: valid json ]",           # garbage on stdin — must be ignored
        env=env, capture_output=True, text=True, check=True,
    )
    out = json.loads(proc.stdout)
    assert out["framework"] == "checkov_terraform"
    assert out["hostname"] == "repo-x"
    assert out["failed_controls"] == 2
