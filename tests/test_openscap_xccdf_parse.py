"""Unit tests for the OpenSCAP XCCDF results parser (AAC OpenSCAP integration)."""
from __future__ import annotations

import os
import sys

import pytest

# Make scripts/ importable regardless of where pytest is invoked from.
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from openscap_xccdf_parse import parse_xccdf_results  # noqa: E402

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "openscap_xccdf_sample.xml")


@pytest.fixture(scope="module")
def parsed() -> dict:
    with open(_FIXTURE, "r", encoding="utf-8") as fh:
        return parse_xccdf_results(fh.read())


def test_counts_exclude_neutral_statuses(parsed):
    # Fixture has: 1 pass, 1 fail, 1 error, 1 notapplicable.
    # fail + error count as failed; notapplicable is neutral (excluded).
    assert parsed["passed"] == 1
    assert parsed["failed"] == 2               # fail + error
    assert parsed["total_evaluated"] == 3      # notapplicable NOT counted
    assert parsed["compliant"] is False


def test_compliance_pct_uses_evaluated_denominator(parsed):
    # 1 passed / 3 evaluated = 33.33 — NOT 1/4 (which would wrongly count NA).
    assert parsed["compliance_pct"] == pytest.approx(33.33, abs=0.01)


def test_by_status_records_raw_counts(parsed):
    assert parsed["by_status"]["pass"] == 1
    assert parsed["by_status"]["fail"] == 1
    assert parsed["by_status"]["error"] == 1
    assert parsed["by_status"]["notapplicable"] == 1


def test_failed_rules_are_fail_and_error(parsed):
    ids = {r["rule_id"] for r in parsed["failed_rules"]}
    assert "xccdf_org.ssgproject.content_rule_package_aide_installed" in ids   # fail
    assert "xccdf_org.ssgproject.content_rule_audit_rules_login_events" in ids  # error
    assert len(parsed["failed_rules"]) == 2


def test_titles_resolved_from_benchmark(parsed):
    aide = next(r for r in parsed["failed_rules"]
                if r["rule_id"].endswith("aide_installed"))
    assert aide["title"] == "Install AIDE"       # resolved, not the raw id


def test_idents_captured_for_future_crosswalk(parsed):
    sshd = next(r for r in parsed["rule_results"]
                if r["rule_id"].endswith("sshd_disable_root_login"))
    systems = {i["value"] for i in sshd["idents"]}
    assert "CCE-90775-0" in systems
    assert "CCI-000366" in systems


def test_metadata_fields(parsed):
    assert parsed["profile"] == "xccdf_org.ssgproject.content_profile_stig"
    assert parsed["benchmark_id"] == "xccdf_org.ssgproject.content_benchmark_RHEL-9"
    assert parsed["score"] == pytest.approx(50.0)


def test_xccdf_1_1_namespace_also_parses():
    # Same shape, older 1.1 namespace — must parse namespace-agnostically.
    xml = """<?xml version="1.0"?>
    <Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1" id="b">
      <Rule id="r1"><title>Rule One</title></Rule>
      <TestResult id="tr">
        <rule-result idref="r1" severity="low"><result>pass</result></rule-result>
      </TestResult>
    </Benchmark>"""
    out = parse_xccdf_results(xml)
    assert out["passed"] == 1 and out["failed"] == 0
    assert out["rule_results"][0]["title"] == "Rule One"


def test_rejects_doctype_dtd():
    # Defense against entity-expansion / XXE — DTDs are refused outright.
    malicious = ('<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY x "y">]>'
                 '<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.2"/>')
    with pytest.raises(ValueError, match="DOCTYPE"):
        parse_xccdf_results(malicious)


def test_rejects_garbage():
    with pytest.raises(ValueError):
        parse_xccdf_results("not xml at all")


def test_rejects_non_oscap_xml():
    with pytest.raises(ValueError, match="TestResult"):
        parse_xccdf_results('<html><body>nope</body></html>')
