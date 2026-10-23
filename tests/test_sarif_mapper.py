"""Unit tests for the AAC -> SARIF 2.1.0 exporter (scripts/sarif_mapper.py)."""
from __future__ import annotations

import os
import sys

# sarif_mapper reads FRAMEWORK from the environment at import time.
os.environ.setdefault("FRAMEWORK", "cis_rhel9")
os.environ.setdefault("TOOL_VERSION", "1.0.0")

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import sarif_mapper  # noqa: E402


_ROWS = [
    {
        "hostname": "web01", "framework": "cis_rhel9", "policy_name": "CIS RHEL9",
        "violations": [
            {"control_id": "1.1.1", "description": "cramfs not disabled", "severity": "high",
             "remediation": "disable cramfs"},
            {"control_id": "5.2.1", "description": "sshd weak config", "severity": "critical"},
            {"control_id": "1.7.1", "description": "motd missing", "severity": "low"},
        ],
    },
    {"hostname": "web02", "framework": "cis_rhel9", "policy_name": "CIS RHEL9", "violations": []},
    {"hostname": "web03", "framework": "cis_rhel9", "policy_name": "CIS RHEL9",
     "violations": [{"control_id": "1.1.1", "description": "cramfs not disabled", "severity": "high"}]},
]


def test_top_level_shape_is_sarif_210():
    doc = sarif_mapper.build_document(_ROWS)
    assert doc["version"] == "2.1.0"
    assert "$schema" in doc
    assert doc["runs"][0]["tool"]["driver"]["name"].startswith("Ansible Automated Compliance")


def test_rules_are_deduped_across_hosts():
    doc = sarif_mapper.build_document(_ROWS)
    rules = {r["id"] for r in doc["runs"][0]["tool"]["driver"]["rules"]}
    # 1.1.1 appears on web01 and web03 -> a single rule, namespaced by framework.
    assert rules == {"cis_rhel9/1.1.1", "cis_rhel9/5.2.1", "cis_rhel9/1.7.1"}


def test_result_count_and_levels():
    doc = sarif_mapper.build_document(_ROWS)
    results = doc["runs"][0]["results"]
    assert len(results) == 4  # 3 on web01 + 1 on web03; web02 is clean
    by_rule = {r["ruleId"]: r["level"] for r in results}
    assert by_rule["cis_rhel9/5.2.1"] == "error"   # critical -> error
    assert by_rule["cis_rhel9/1.7.1"] == "note"     # low -> note
    assert by_rule["cis_rhel9/1.1.1"] == "error"    # high -> error


def test_results_have_required_fields():
    doc = sarif_mapper.build_document(_ROWS)
    for r in doc["runs"][0]["results"]:
        assert r["ruleId"]
        assert r["level"] in ("error", "warning", "note")
        assert r["message"]["text"]
        assert r["locations"][0]["logicalLocations"][0]["fullyQualifiedName"]
        assert r["partialFingerprints"]["aacFindingHash/v1"]


def test_security_severity_present_for_code_scanning_ranking():
    doc = sarif_mapper.build_document(_ROWS)
    for rule in doc["runs"][0]["tool"]["driver"]["rules"]:
        assert "security-severity" in rule["properties"]


def test_fingerprint_is_stable_across_runs():
    a = sarif_mapper.build_document(_ROWS)["runs"][0]["results"]
    b = sarif_mapper.build_document(_ROWS)["runs"][0]["results"]
    fa = {r["partialFingerprints"]["aacFindingHash/v1"] for r in a}
    fb = {r["partialFingerprints"]["aacFindingHash/v1"] for r in b}
    assert fa == fb


def test_violations_as_json_string_are_parsed():
    import json
    row = {"hostname": "h", "violations": json.dumps([{"control_id": "9.9.9", "severity": "medium"}])}
    doc = sarif_mapper.build_document([row])
    assert doc["runs"][0]["results"][0]["ruleId"] == "cis_rhel9/9.9.9"
    assert doc["runs"][0]["results"][0]["level"] == "warning"


def test_violations_wrapper_object_is_unwrapped():
    # Some writers (M365) store {"violations": [...]} instead of a bare array;
    # iterating the dict's keys would emit zero findings (a silent clean report).
    row = {"hostname": "h", "violations": {"violations": [{"control_id": "8.8.8", "severity": "high"}]}}
    doc = sarif_mapper.build_document([row])
    results = doc["runs"][0]["results"]
    assert len(results) == 1
    assert results[0]["ruleId"] == "cis_rhel9/8.8.8"


def test_string_violations_are_parsed():
    # The Rego library emits string violations; they must still produce findings.
    row = {"hostname": "web01", "violations": [
        "CIS 4.2.1.1: rsyslog is not installed",
        "CIS 5.2.1: CRITICAL: sshd permissions wrong",
    ]}
    doc = sarif_mapper.build_document([row])
    results = doc["runs"][0]["results"]
    assert len(results) == 2
    by_rule = {r["ruleId"]: r for r in results}
    assert "cis_rhel9/CIS 4.2.1.1" in by_rule
    assert by_rule["cis_rhel9/CIS 5.2.1"]["level"] == "error"


_STIG_ROWS = [
    {"hostname": "ol9-01", "framework": "stig_oracle_linux_9", "policy_name": "DISA STIG Oracle Linux 9",
     "violations": [
         {"vuln_id": "V-271752", "stig_id": "OL09-00-002413", "severity": "CAT I", "status": "Open",
          "rule_title": "OL 9 must be configured so that the x86 Ctrl-Alt-Delete key sequence is disabled.",
          "fix_text": "systemctl mask ctrl-alt-del.target"},
         {"vuln_id": "V-271802", "stig_id": "OL09-00-002540", "severity": "CAT II", "status": "Open",
          "rule_title": "OL 9 /etc/gshadow file must be owned by root."},
     ]},
]


def test_stig_object_findings_export_under_their_stig_id():
    doc = sarif_mapper.build_document(_STIG_ROWS)
    run = doc["runs"][0]
    ids = {r["ruleId"] for r in run["results"]}
    assert ids == {"cis_rhel9/OL09-00-002413", "cis_rhel9/OL09-00-002540"}, ids
    cad = next(r for r in run["results"] if r["ruleId"].endswith("OL09-00-002413"))
    assert "Ctrl-Alt-Delete" in cad["message"]["text"]
    assert "systemctl mask" in cad["message"]["text"]
    assert cad["level"] == "error" and cad["properties"]["severity"] == "high"
    gsh = next(r for r in run["results"] if r["ruleId"].endswith("OL09-00-002540"))
    assert gsh["level"] == "warning" and gsh["properties"]["severity"] == "medium"


def test_stig_normalizer_keeps_the_original_cat_label():
    v = sarif_mapper._normalize_violation({"stig_id": "X-1", "severity": "CAT III", "rule_title": "t"})
    assert v["severity"] == "low" and v["stig_severity"] == "CAT III" and v["control_id"] == "X-1" and v["description"] == "t"
