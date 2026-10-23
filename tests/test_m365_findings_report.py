"""Tests for scripts/m365_findings_report.py — the decisioning core.

Pins the properties that answer the "raw data is useless" critique: every
finding is ranked (never UNKNOWN), every finding has a mitigation, risk is
explainable, evidence gaps are separated from failures, and the ordering is
risk-first and deterministic.
"""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "m365_findings_report",
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "m365_findings_report.py",
)
mr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mr)

CATALOG = [
    {"control_id": "1.1.3", "section": 1, "section_name": "M365 admin center", "assessment": "Automated", "levels": ["E3 Level 1"]},
    {"control_id": "5.1.2.2", "section": 5, "section_name": "Entra admin center", "assessment": "Automated", "levels": ["E3 Level 1"]},
    {"control_id": "6.5.1", "section": 6, "section_name": "Exchange admin center", "assessment": "Automated", "levels": ["E3 Level 1"]},
    {"control_id": "1.3.3", "section": 1, "section_name": "M365 admin center", "assessment": "Manual", "levels": ["E3 Level 2"]},
    {"control_id": "5.2.3.6", "section": 5, "section_name": "Entra admin center", "assessment": "Automated", "levels": ["E5 Level 1"]},
]

ROWS = [
    {"policy_name": "cis_m365_v7.1", "violations": [
        "CIS 1.1.3: only 1 global admin designated; fewer than two risks lockout"]},
    {"policy_name": "cis_m365_v7.5", "violations": [
        "CIS 5.1.2.2: users can register applications; any user can consent-phish other users",
        "CIS 5.2.3.6: system-preferred multifactor authentication is not enabled"]},
    {"policy_name": "cis_m365_v7.6", "violations": [
        "CIS 6.5.1: modern authentication for Exchange Online is not enabled; legacy authentication bypasses MFA"]},
    {"policy_name": "cis_m365_v7.1b", "violations": [
        "CIS 1.3.3: external sharing of calendars is available"]},
    {"policy_name": "cis_m365_v7.gap", "violations": [
        "CIS 2.1.1: Defender policy facts were not collected (this is not a pass)"]},
]


def _report():
    return mr.build_report({"rows": ROWS, "catalog": CATALOG, "tenant": "t"})


def test_no_finding_is_unranked():
    rep = _report()
    assert rep["findings"], "expected findings"
    for f in rep["findings"]:
        assert f["risk"]["band"] in ("Critical", "High", "Medium", "Low")
        assert f["risk"]["band"] != "UNKNOWN"


def test_every_finding_has_a_mitigation():
    for f in _report()["findings"]:
        assert f["mitigation"]["where"] and f["mitigation"]["action"]


def test_risk_is_explainable():
    for f in _report()["findings"]:
        assert f["risk"]["factors"], "risk must show its factors"


def test_evidence_gaps_separated_from_failures():
    rep = _report()
    cids = {f["control_id"] for f in rep["findings"]}
    assert "2.1.1" not in cids  # the gap is not a failure
    assert any(g["control_id"] == "2.1.1" for g in rep["evidence_gaps"])
    assert rep["summary"]["evidence_gaps"] == 1


def test_ordering_is_risk_first_and_deterministic():
    order = ["Critical", "High", "Medium", "Low"]
    bands = [f["risk"]["band"] for f in _report()["findings"]]
    idx = [order.index(b) for b in bands]
    assert idx == sorted(idx), "findings must be ordered highest-risk first"
    # deterministic across input order
    import random
    shuffled = list(ROWS)
    a = [f["control_id"] for f in _report()["findings"]]
    shuffled = shuffled[::-1]
    b = [f["control_id"] for f in mr.build_report(
        {"rows": shuffled, "catalog": CATALOG, "tenant": "t"})["findings"]]
    assert a == b


def test_mfa_and_legacy_auth_elevate_risk():
    rep = _report()
    by = {f["control_id"]: f for f in rep["findings"]}
    # 6.5.1 (legacy auth + MFA keywords) should outrank 1.3.3 (L2 service config)
    assert by["6.5.1"]["risk"]["score"] > by["1.3.3"]["risk"]["score"]
    assert by["5.2.3.6"]["risk"]["band"] in ("Critical", "High")


def test_renderers_run_and_mark_sample():
    rep = _report()
    md = mr.render_markdown(rep, sample=True)
    html = mr.render_html(rep, sample=True)
    assert "SAMPLE" in md and "SAMPLE" in html
    assert "Remediation" in md and "Remediation" in html
    assert "UNKNOWN" not in md and "UNKNOWN" not in html
    # posture verdict present
    assert rep["summary"]["verdict"] in md


def test_l1_outranks_equivalent_l2():
    cat = [{"control_id": "1.3.1", "section": 1, "section_name": "x", "assessment": "Automated", "levels": ["E3 Level 1"]},
           {"control_id": "1.3.2", "section": 1, "section_name": "x", "assessment": "Automated", "levels": ["E3 Level 2"]}]
    rows = [{"policy_name": "cis_m365_v7.1", "violations": [
        "CIS 1.3.1: setting A is permissive", "CIS 1.3.2: setting B is permissive"]}]
    by = {f["control_id"]: f for f in mr.build_report({"rows": rows, "catalog": cat, "tenant": "t"})["findings"]}
    assert by["1.3.1"]["risk"]["score"] > by["1.3.2"]["risk"]["score"]


def test_executive_view_renders_posture_and_top_risks():
    rows = ROWS + [
        {"policy_name": "cis_m365_v7.5", "violations": [], "passed_controls": 48,
         "failed_controls": 5, "metadata": {"controls_evaluated": 53}},
    ]
    rep = mr.build_report({"rows": rows, "catalog": CATALOG, "tenant": "t"})
    assert rep["summary"]["compliance_pct"] is not None
    html = mr.render_exec_html(rep, sample=True)
    assert "Executive Summary" in html
    assert "Top risks" in html
    assert "UNKNOWN" not in html
    # the headline score is present
    assert f'{rep["summary"]["compliance_pct"]}%' in html


def test_exec_score_absent_when_no_counts():
    rep = mr.build_report({"rows": ROWS, "catalog": CATALOG, "tenant": "t"})
    assert rep["summary"]["compliance_pct"] is None
    html = mr.render_exec_html(rep, sample=False)
    assert ">—<" in html  # score falls back to em-dash, no crash


def test_csv_export_structure_and_balance():
    rows = [
        {"policy_name": "cis_m365_v7.1", "passed_controls": 20, "failed_controls": 3,
         "violations": ["CIS 1.1.3: only 1 global admin designated"]},
        {"policy_name": "cis_m365_v7.5", "passed_controls": 1, "failed_controls": 2,
         "violations": ["CIS 5.1.2.2: users can register applications",
                        "CIS 5.2.3.6: system-preferred MFA is not enabled"]},
    ]
    cat = CATALOG + [{"control_id": "1.1.1", "section": 1, "section_name": "M365 admin center", "assessment": "Automated", "levels": ["E3 Level 1"]}]
    csv_text = mr.build_csv({"rows": rows, "catalog": cat, "tenant": "acme"})
    assert "SUMMARY BY CATEGORY" in csv_text
    assert "Category,Total Controls,Passed,Failed,Unable to Assess" in csv_text
    assert "DETAIL" in csv_text
    assert "Category,Control,Status,Profile level,Benchmark assessment,Risk,Risk score,Risk basis,Where to fix,Action,Method,Detail" in csv_text
    # each category row must balance: total = passed + failed + unable
    import csv as _csv, io
    reader = list(_csv.reader(io.StringIO(csv_text)))
    hdr = reader.index(["Category", "Total Controls", "Passed", "Failed", "Unable to Assess"])
    for r in reader[hdr + 1:]:
        if not r or r[0] in ("", "DETAIL"):
            break
        total, p, f, u = int(r[1]), int(r[2]), int(r[3]), int(r[4])
        assert total == p + f + u, f"row {r} does not balance"
    # detail is one column per field: risk and remediation are columns, not
    # a sentence to parse
    detail = reader[reader.index(["DETAIL"]) + 1:]
    hdr = detail[0]
    row = next(r for r in detail[1:] if r and r[hdr.index("Control")] == "1.1.3")
    assert row[hdr.index("Status")] == "Failed"
    assert row[hdr.index("Risk")] in ("Critical", "High", "Medium", "Low")
    assert row[hdr.index("Where to fix")] and row[hdr.index("Action")]
    assert "Risk:" not in row[hdr.index("Detail")]
