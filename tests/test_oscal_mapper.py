"""Unit tests for the AAC -> OSCAL 1.1.2 exporter (scripts/oscal_mapper.py)."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("FRAMEWORK", "stig_oracle_database_19c")
os.environ.setdefault("TOOL_VERSION", "1.0.0")

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import oscal_mapper  # noqa: E402


_ROWS = [
    {"hostname": "proddb", "framework": "stig_oracle_database_19c", "policy_name": "DISA STIG Oracle Database 19c",
     "policy_version": "V1R6", "total_controls": 96, "passed_controls": 95, "failed_controls": 1,
     "compliance_percentage": 99.0, "compliant": False, "evaluation_timestamp": "2026-10-13T12:00:00Z",
     "violations": [{"vuln_id": "V-270540", "stig_id": "O19C-00-009200", "severity": "CAT II", "status": "Open",
                     "rule_title": "The Oracle REMOTE_OS_ROLES parameter must be set to FALSE."}]},
]


def test_stig_object_finding_targets_its_stig_id():
    doc = oscal_mapper.build_document(_ROWS)
    res = doc["assessment-results"]["results"][0]
    findings = [f for f in res["findings"] if f["target"]["target-id"] != "all"]
    assert findings, res["findings"]
    f = findings[0]
    assert f["target"]["target-id"] == "O19C-00-009200", f["target"]
    assert f["target"]["status"]["state"] == "not-satisfied"
    assert "REMOTE_OS_ROLES" in f["description"]
    obs = res["observations"][0]
    assert "Severity: medium" in obs["relevant-evidence"][0]["description"] if obs.get("relevant-evidence") else True


def test_string_violation_still_parses():
    v = oscal_mapper._parse_string_violation("CIS 1.3.1: AIDE is not installed")
    assert v["control_id"] == "CIS 1.3.1"
