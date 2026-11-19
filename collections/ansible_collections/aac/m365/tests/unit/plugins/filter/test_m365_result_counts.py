"""Stored passed / failed / not-evaluated counts (persist.yml).

The two recorded reports in tests/unit/fixtures are real `opa eval`
outputs of the library's cis_m365_v7 orchestrator (OPA 1.8.0):

  cis_m365_v7_report_empty.json    input {} -- nothing collected
  cis_m365_v7_report_partial.json  synthetic Exchange, Defender, Teams and
                                   Entra facts only (sections 1, 3, 4, 7, 9
                                   not collected)

The old persist arithmetic (controls_evaluated minus the ids named in
violations) stored 129 passed controls for the empty report.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

UNIT = Path(__file__).resolve().parents[2]
FIXTURES = UNIT / "fixtures"
_spec = importlib.util.spec_from_file_location(
    "m365_results", UNIT.parents[1] / "plugins" / "filter" / "m365_results.py")
m365_results = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m365_results)
counts = m365_results.m365_result_counts


def _report(name):
    return json.loads((FIXTURES / name).read_text())


def _old_passed(report):
    total = 0
    for sec in report["sections_evaluated"]:
        ids = {m.group(1) for v in sec["violations"]
               for m in [re.search(r"CIS ([0-9]+(?:\.[0-9]+)*)", v)] if m}
        total += max(sec["controls_evaluated"] - len(ids), 0)
    return total


def _totals(result):
    secs = result["sections"].values()
    return (sum(s["passed"] for s in secs), sum(s["failed"] for s in secs),
            sum(s["not_evaluated"] for s in secs))


def test_empty_input_stores_no_passes():
    report = _report("cis_m365_v7_report_empty.json")
    assert _old_passed(report) == 129          # the defect being fixed
    result = counts(report)
    passed, failed, not_evaluated = _totals(result)
    assert passed == 0
    assert failed == 0
    assert not_evaluated == report["controls_evaluated"] == 144
    assert all(s["compliance_percentage"] == 0 for s in result["sections"].values())
    assert result["ledger"]["passed"] == 0
    assert result["ledger"]["failed"] == 0
    assert result["ledger"]["not_attested"] == 16


def test_partly_evaluated_report():
    report = _report("cis_m365_v7_report_partial.json")
    result = counts(report)
    s = result["sections"]
    # Sections with nothing collected: never a pass.
    for sid in ("3", "4", "7", "9"):
        assert s[sid]["passed"] == 0
        assert s[sid]["not_evaluated"] == s[sid]["declared_evaluated"]
        assert s[sid]["count_basis"] == "fallback_conservative"
    # Section 1 carries a fail-closed message that names one id for a whole
    # missing collector, so nothing in it can be counted as evaluated.
    assert s["1"]["passed"] == 0 and s["1"]["count_basis"] == "fallback_conservative"
    # Section 2 was fully collected: every control is either failed or passed.
    assert s["2"]["count_basis"] == "fallback_exact"
    assert s["2"]["not_evaluated"] == 0
    assert "2.1.11" in s["2"]["failed_control_ids"]
    # Every declared control is counted exactly once.
    for sec in report["sections_evaluated"]:
        c = s[sec["section"]]
        assert c["passed"] + c["failed"] + c["not_evaluated"] == len(sec["controls"])


def _section(controls, violations, **extra):
    sec = {"section": "2", "controls": controls, "controls_evaluated": len(controls),
           "section_total_controls": 21, "violations": violations,
           "facts_present": True, "unavailable_facts": {}}
    sec.update(extra)
    return sec


def test_all_evaluated_section():
    sec = _section(["2.1.1", "2.1.2", "2.1.3"],
                   ["CIS 2.1.2: malware filter policy 'Default' has the filter disabled"])
    c = counts({"sections_evaluated": [sec]})["sections"]["2"]
    assert (c["passed"], c["failed"], c["not_evaluated"]) == (2, 1, 0)
    assert c["compliance_percentage"] == 66.7
    assert c["count_basis"] == "fallback_exact"


def test_enumerated_gap_blocks_exactly_the_listed_controls():
    sec = _section(
        ["2.1.1", "2.1.2", "2.1.3", "2.1.11", "2.1.12"],
        ["CIS 2.1.2: could not be evaluated -- access denied (blocks 2.1.2, 2.1.3, 2.1.11) (this is not a pass)"],
        unavailable_facts={"malware_filter_policies": "access denied"})
    c = counts({"sections_evaluated": [sec]})["sections"]["2"]
    assert c["not_evaluated_control_ids"] == ["2.1.11", "2.1.2", "2.1.3"]
    assert c["passed_control_ids"] == ["2.1.1", "2.1.12"]
    assert c["count_basis"] == "fallback_exact"


def test_unenumerated_gap_makes_the_section_conservative():
    sec = _section(["5.1.2.2", "5.1.2.3", "5.1.3.1"],
                   ["CIS 5.1.2.2: could not be evaluated -- 403 (this is not a pass)"],
                   unavailable_facts={"authorization_policy": "403"})
    c = counts({"sections_evaluated": [sec]})["sections"]["2"]
    assert c["passed"] == 0 and c["not_evaluated"] == 3


def test_multi_id_prefix_counts_every_id():
    sec = _section(["2.1.8", "2.1.9", "2.1.10"],
                   ["CIS 2.1.8/2.1.9/2.1.10: SPF, DKIM and DMARC for domain 'contoso.com' could not be "
                    "evaluated -- evidence missing: timed out (this is not a pass)"])
    c = counts({"sections_evaluated": [sec]})["sections"]["2"]
    assert c["not_evaluated"] == 3 and c["passed"] == 0


def test_failed_wins_over_not_evaluated():
    sec = _section(["2.4.1", "2.4.2"],
                   ["CIS 2.4.1: priority account protection is not enabled for the tenant",
                    "CIS 2.4.1: could not be evaluated -- no session (blocks 2.4.1) (this is not a pass)"])
    c = counts({"sections_evaluated": [sec]})["sections"]["2"]
    assert c["failed_control_ids"] == ["2.4.1"]
    assert c["not_evaluated"] == 0
    assert c["passed_control_ids"] == ["2.4.2"]


def test_unavailable_fact_without_a_message_is_not_a_pass():
    sec = _section(["7.2.1", "7.2.2"], [], unavailable_facts={"tenant": "PnP failed"})
    c = counts({"sections_evaluated": [sec]})["sections"]["2"]
    assert c["passed"] == 0 and c["not_evaluated"] == 2


def test_control_results_are_preferred_when_present():
    sec = _section(["2.1.1", "2.1.2", "2.1.3", "2.1.4", "2.1.5"],
                   ["CIS 2.1.2: could not be evaluated -- x (this is not a pass)"])
    report = {"sections_evaluated": [sec], "control_results": [
        {"control_id": "2.1.1", "status": "pass"},
        {"control_id": "2.1.2", "status": "evidence_missing"},
        {"control_id": "2.1.3", "status": "fail"},
        {"id": "2.1.4", "status": "not_applicable"},
        # 2.1.5 not mentioned -> not evaluated, never passed
        {"control_id": "5.1.2.2", "status": "pass"},   # other section, ignored
    ]}
    c = counts(report)["sections"]["2"]
    assert c["count_basis"] == "control_results"
    assert c["passed_control_ids"] == ["2.1.1"]
    assert c["failed_control_ids"] == ["2.1.3"]
    assert c["not_evaluated_control_ids"] == ["2.1.2", "2.1.5"]
    assert c["not_applicable_control_ids"] == ["2.1.4"]
    assert c["compliance_percentage"] == 25.0      # 1 of 4 applicable


def test_control_results_unknown_status_is_not_a_pass():
    sec = _section(["2.1.1"], [], control_results=[{"control_id": "2.1.1", "status": "PASSISH"}])
    c = counts({"sections_evaluated": [sec]})["sections"]["2"]
    assert c["passed"] == 0 and c["not_evaluated"] == 1


def test_waived_failure_is_not_a_pass():
    sec = _section(["2.1.1", "2.1.2"], [], waivers_applied=[{"id": "w1"}],
                   control_results=[{"control_id": "2.1.1", "status": "fail"},
                                    {"control_id": "2.1.2", "status": "pass"}])
    c = counts({"sections_evaluated": [sec]})["sections"]["2"]
    assert c["waived_control_ids"] == ["2.1.1"]
    assert c["passed_control_ids"] == ["2.1.2"]
    assert c["failed"] == 0


def test_ledger_reads_attestations_and_observed():
    report = _report("cis_m365_v7_report_empty.json")
    report["no_collector_path"]["attested_control_ids"] = ["5.2.4.1", "1.1.2"]
    att = [{"control_id": "5.2.4.1", "observed": True},
           {"control_id": "1.1.2", "observed": False}]
    led = counts(report, attestations=att)["ledger"]
    assert led["passed_control_ids"] == ["5.2.4.1"]
    assert led["failed_control_ids"] == ["1.1.2"]
    assert led["not_attested"] == 14
    assert led["total"] == 16
