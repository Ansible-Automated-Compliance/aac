"""Tests for scripts/benchmark_concordance.py — the comparison core.

Pin the properties the comparison's credibility rests on: silence is never a
pass (missing section rows, missing attestation rows), "this is not a pass"
messages are never counted as assessed failures, coverage boundaries render
as not_covered rather than as AAC misses, crosswalked manual ids join
correctly, and the agreement classes partition the controls.
"""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "benchmark_concordance",
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "benchmark_concordance.py",
)
bc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bc)


COVERAGE = {
    "benchmark": "CIS Test Benchmark",
    "benchmark_version": "7.0.0",
    "benchmark_total_controls": 8,
    "evaluated": ["1.1.1", "1.1.2", "2.1.1", "2.1.2"],
    "requires_attestation": ["3.1.1"],
    "unresolved": ["3.2.1"],
    "not_implemented": ["3.3.1"],
    "catalog": [
        {"control_id": "1.1.1", "section": "1", "section_name": "One", "cis_assessment": "Automated"},
        {"control_id": "1.1.2", "section": "1", "section_name": "One", "cis_assessment": "Automated"},
        {"control_id": "2.1.1", "section": "2", "section_name": "Two", "cis_assessment": "Automated"},
        {"control_id": "2.1.2", "section": "2", "section_name": "Two", "cis_assessment": "Automated"},
        {"control_id": "3.1.1", "section": "3", "section_name": "Three", "cis_assessment": "Manual"},
        {"control_id": "3.2.1", "section": "3", "section_name": "Three", "cis_assessment": "Manual"},
        {"control_id": "3.3.1", "section": "3", "section_name": "Three", "cis_assessment": "Manual"},
        {"control_id": "4.1.1", "section": "4", "section_name": "Four", "cis_assessment": "Automated"},
    ],
}

ROWS = [
    {"policy_name": "cis_test.1", "violations": [
        "CIS 1.1.1: shared mailboxes allow sign-in — 3 mailboxes enabled"], "metadata": {}},
    {"policy_name": "cis_test.2", "violations": []},
    {"policy_name": "cis_test.attestation", "violations": [
        "CIS 3.1.1: SSPR enabled for all users -- no app-only read path exists, "
        "so this control requires operator attestation and none has been recorded "
        "(this is not a pass)"], "metadata": {}},
]


def _by_id(result):
    return {c["control_id"]: c for c in result["controls"]}


def test_statuses_without_manual_input():
    r = bc.concord({"aac_rows": ROWS, "coverage": COVERAGE})
    c = _by_id(r)
    assert c["1.1.1"]["aac_status"] == "fail"
    assert c["1.1.2"]["aac_status"] == "pass"          # section 1 row present
    assert c["2.1.1"]["aac_status"] == "pass"
    assert c["3.1.1"]["aac_status"] == "not_assessed"  # attestation missing
    assert c["3.2.1"]["aac_status"] == "not_covered"
    assert c["3.3.1"]["aac_status"] == "not_covered"
    # 4.1.1 is "evaluated"? No — not in evaluated set, not claimed.
    assert c["4.1.1"]["aac_status"] == "not_covered"
    assert all(x["agreement"] == "no_manual_input" for x in r["controls"])


def test_missing_section_row_is_not_a_pass():
    rows = [r for r in ROWS if r["policy_name"] != "cis_test.2"]
    c = _by_id(bc.concord({"aac_rows": rows, "coverage": COVERAGE}))
    assert c["2.1.1"]["aac_status"] == "not_assessed"
    assert "absence is not a pass" in c["2.1.1"]["aac_detail"]


def test_missing_attestation_row_is_not_attested():
    rows = [r for r in ROWS if r["policy_name"] != "cis_test.attestation"]
    c = _by_id(bc.concord({"aac_rows": rows, "coverage": COVERAGE}))
    assert c["3.1.1"]["aac_status"] == "not_assessed"


def test_admissible_attestation_reads_attested_not_pass():
    rows = [dict(ROWS[0]), dict(ROWS[1]),
            {"policy_name": "cis_test.attestation", "violations": [], "metadata": {}}]
    c = _by_id(bc.concord({"aac_rows": rows, "coverage": COVERAGE}))
    assert c["3.1.1"]["aac_status"] == "attested"


def test_not_a_pass_message_never_counts_as_assessed_failure():
    r = bc.concord({"aac_rows": ROWS, "coverage": COVERAGE})
    c = _by_id(r)
    assert c["3.1.1"]["aac_status"] == "not_assessed"
    assert len(r["evidence_gaps"]) == 1
    # And a control with BOTH a real failure and a gap message is a failure.
    rows = ROWS + [{"policy_name": "cis_test.1", "violations": [
        "CIS 1.1.1: facts partially collected (this is not a pass)"], "metadata": {}}]
    c2 = _by_id(bc.concord({"aac_rows": rows, "coverage": COVERAGE}))
    assert c2["1.1.1"]["aac_status"] == "fail"


def test_no_rows_at_all_assesses_nothing():
    c = _by_id(bc.concord({"aac_rows": [], "coverage": COVERAGE}))
    assert {x["aac_status"] for x in c.values()} <= {"not_assessed", "not_covered"}


def test_manual_join_and_agreement_classes():
    manual = [
        {"control_id": "1.1.1", "result": "Fail", "notes": "seen in portal"},
        {"control_id": "1.1.2", "result": "Pass"},
        {"control_id": "2.1.1", "result": "FAIL"},
        {"control_id": "3.2.1", "result": "pass"},
        {"control_id": "9.9.9", "result": "pass"},
    ]
    r = bc.concord({"aac_rows": ROWS, "coverage": COVERAGE, "manual": manual})
    c = _by_id(r)
    assert c["1.1.1"]["agreement"] == "agree_fail"
    assert c["1.1.2"]["agreement"] == "agree_pass"
    assert c["2.1.1"]["agreement"] == "aac_pass_manual_fail"
    assert c["3.2.1"]["agreement"] == "manual_only"      # AAC has no path
    assert c["2.1.2"]["agreement"] == "aac_only"         # not in their sheet
    assert c["9.9.9"]["aac_status"] == "not_in_benchmark"
    s = r["summary"]
    assert s["both_assessed"] == 3 and s["agree"] == 2
    assert s["agreement_rate_pct"] == 66.7
    # Agreement classes partition the whole control set.
    assert sum(s["agreement_counts"].values()) == len(r["controls"])


def test_crosswalk_maps_old_numbering():
    manual = [{"control_id": "5.9", "result": "fail"}]
    r = bc.concord({"aac_rows": ROWS, "coverage": COVERAGE,
                    "manual": manual, "crosswalk": {"5.9": "1.1.1"}})
    assert _by_id(r)["1.1.1"]["agreement"] == "agree_fail"


def test_custom_pass_fail_values_and_other():
    manual = [{"control_id": "1.1.1", "result": "Deficient"},
              {"control_id": "1.1.2", "result": "Satisfactory"},
              {"control_id": "2.1.1", "result": "N/A"}]
    r = bc.concord({"aac_rows": ROWS, "coverage": COVERAGE, "manual": manual,
                    "pass_values": ["satisfactory"], "fail_values": ["deficient"]})
    c = _by_id(r)
    assert c["1.1.1"]["agreement"] == "agree_fail"
    assert c["1.1.2"]["agreement"] == "agree_pass"
    assert c["2.1.1"]["manual_status"] == "other"
    assert c["2.1.1"]["agreement"] == "aac_only"         # unparseable ≠ assessed


def test_l2_prefixed_violation_messages_extract():
    rows = [{"policy_name": "cis_test.1", "violations": [
        "CIS L2 1.1.2: guest access unrestricted — 4 guests"], "metadata": {}},
        ROWS[1], ROWS[2]]
    c = _by_id(bc.concord({"aac_rows": rows, "coverage": COVERAGE}))
    assert c["1.1.2"]["aac_status"] == "fail"


def test_duplicate_manual_rows_keep_parseable_verdict():
    manual = [{"control_id": "1.1.1", "result": "fail"},
              {"control_id": "1.1.1", "result": "see notes"}]
    c = _by_id(bc.concord({"aac_rows": ROWS, "coverage": COVERAGE, "manual": manual}))
    assert c["1.1.1"]["manual_status"] == "fail"
