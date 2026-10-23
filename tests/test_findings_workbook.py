"""Tests for scripts/findings_workbook.py — the F4 generic findings workbook.

Pins the properties the field asked for: one column per field (no parsing
needed), a stable finding identity across runs, unassessable controls kept
apart from failures and split by cause, decisions joined without ever
editing evidence, a delta against the previous run (new / fixed / regressed /
still open), waiver and decision expiry, sampled evidence flagged, and a
published column contract that cannot drift from the code.
"""
import csv
import importlib.util
import io
import json
import pathlib
import zipfile

import pytest

_root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("findings_workbook", _root / "scripts" / "findings_workbook.py")
wb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wb)

NOW = "2026-10-13T12:00:00Z"
TENANT = "contoso.onmicrosoft.com"

CATALOG = [
    {"control_id": "1.1.3", "section": 1, "section_name": "M365 admin center", "assessment": "Automated", "levels": ["E3 Level 1"], "title_keywords": ["admins"]},
    {"control_id": "1.1.1", "section": 1, "section_name": "M365 admin center", "assessment": "Automated", "levels": ["E3 Level 1"]},
    {"control_id": "5.1.2.2", "section": 5, "section_name": "Entra admin center", "assessment": "Automated", "levels": ["E3 Level 1"]},
    {"control_id": "5.2.3.6", "section": 5, "section_name": "Entra admin center", "assessment": "Automated", "levels": ["E5 Level 1"]},
    {"control_id": "5.2.4.1", "section": 5, "section_name": "Entra admin center", "assessment": "Manual", "levels": ["E3 Level 1"]},
    {"control_id": "6.5.1", "section": 6, "section_name": "Exchange admin center", "assessment": "Automated", "levels": ["E3 Level 1"]},
    {"control_id": "6.1.2", "section": 6, "section_name": "Exchange admin center", "assessment": "Automated", "levels": ["E3 Level 1"]},
    {"control_id": "7.2.1", "section": 7, "section_name": "SharePoint admin center", "assessment": "Manual", "levels": ["E3 Level 2"]},
    {"control_id": "9.1.1", "section": 9, "section_name": "Fabric", "assessment": "Automated", "levels": ["E3 Level 1"]},
]
COVERAGE = {"evaluated": ["1.1.1", "1.1.3", "5.1.2.2", "5.2.3.6", "6.5.1", "6.1.2"],
            "requires_attestation": ["5.2.4.1"], "unresolved": ["9.1.1"], "not_implemented": []}
RISK = {"criticality": {"1.1": 4, "5.2": 4, "5.1.2": 4, "6.5": 3, "6.1": 3, "_default": 2},
        "elevators": [{"match": "legacy auth", "bump": 2, "reason": "permits legacy authentication"}]}
MIT = {"mitigations": {"1.1": {"where": "M365 admin center -> Roles", "action": "fix admins", "method": "manual"},
                       "6": {"where": "Exchange admin center", "action": "apply EXO setting", "method": "manual"},
                       "_default": {"where": "admin center", "action": "apply CIS config", "method": "manual"}}}
DECISIONS = {
    "framework": "cis_m365_v7", "review_cycle_days": 90,
    "default_owners": {"1": "Platform team", "5": "Identity team", "6": "Messaging team", "_default": "Security operations"},
    "decisions": [
        {"control_id": "6.5.1", "subject": "*", "owner": "Messaging lead", "decision": "accept",
         "justification": "scanners need basic auth until Q1", "approver": "john.smith@example.com",
         "approved": "2026-10-01", "ticket": "CHG-4411"},
        {"control_id": "1.1.3", "subject": TENANT, "owner": "Platform team", "decision": "remediate",
         "approver": "security-team@example.com", "approved": "2026-10-05", "risk_override": "critical"},
        {"control_id": "9.1.1", "subject": "*", "owner": "Data team", "decision": "accept",
         "approver": "ann.lee@example.com", "approved": "2026-07-01", "expires": "2026-09-30", "justification": "old"},
    ],
}


def _row(i, ts, sec, viols, evaluated, extra=None, host=TENANT):
    meta = {"section": sec, "evaluated_control_ids": evaluated, "controls_evaluated": len(evaluated)}
    if extra:
        meta.update(extra)
    return {"id": i, "hostname": host, "framework": "cis_m365_v7", "policy_name": f"cis_m365_v7.{sec}",
            "violations": viols, "metadata": meta, "evaluation_timestamp": ts}


V113 = "CIS 1.1.3: only 1 global admin designated; fewer than two risks lockout"
V651 = "CIS 6.5.1: modern authentication is not enabled; legacy authentication bypasses MFA"
V5236 = "CIS 5.2.3.6: system-preferred multifactor authentication is not enabled"
V5122 = "CIS 5.1.2.2: users can register applications"
GAP211 = "CIS 2.1.1: Defender policy facts were not collected (this is not a pass)"
ATT5241 = "CIS 5.2.4.1: requires attestation -- no automated procedure (this is not a pass)"
SAMPLED = {"evidence_strength": {"6.1.2": "sampled -- 200 of at most 200 mailboxes inspected"}}


def _rows_three_runs():
    rows = []
    # run 1: 1.1.3, 5.2.3.6, 6.5.1 fail
    rows += [_row(1, "2026-09-01T10:00:00Z", 1, [V113], ["1.1.1", "1.1.3"]),
             _row(2, "2026-09-01T10:00:01Z", 5, [V5236], ["5.2.3.6", "5.1.2.2"]),
             _row(3, "2026-09-01T10:00:02Z", 6, [V651], ["6.5.1", "6.1.2"], SAMPLED)]
    # run 2: 1.1.3 fixed
    rows += [_row(4, "2026-09-15T10:00:00Z", 1, [], ["1.1.1", "1.1.3"]),
             _row(5, "2026-09-15T10:00:01Z", 5, [V5236], ["5.2.3.6", "5.1.2.2"]),
             _row(6, "2026-09-15T10:00:02Z", 6, [V651], ["6.5.1", "6.1.2"], SAMPLED)]
    # run 3: 1.1.3 regressed, 5.2.3.6 fixed, 5.1.2.2 new, 6.1.2 waived, gap + attestation rows
    rows += [_row(7, "2026-10-12T09:00:00Z", 1, [V113], ["1.1.1", "1.1.3"]),
             _row(8, "2026-10-12T09:00:01Z", 5, [V5122, GAP211], ["5.2.3.6", "5.1.2.2"]),
             _row(9, "2026-10-12T09:00:02Z", 6, [V651], ["6.5.1", "6.1.2"],
                  {**SAMPLED, "waivers_applied": [{"violation": "CIS 6.1.2: mailbox auditing disabled for 3 mailboxes",
                                                   "waiver": {"reason": "service mailboxes", "approver": "jane.doe@example.com",
                                                              "expires": "2026-10-30"}}]}),
             {"id": 10, "hostname": TENANT, "framework": "cis_m365_v7", "policy_name": "cis_m365_v7.attestation",
              "violations": [ATT5241], "metadata": {"evidence_source": "attested"},
              "evaluation_timestamp": "2026-10-12T09:00:03Z"}]
    return rows


def _payload(**over):
    p = {"framework": "cis_m365_v7", "rows": _rows_three_runs(), "catalog": CATALOG, "coverage": COVERAGE,
         "risk_config": RISK, "mitigation_catalog": MIT, "decisions": DECISIONS,
         "benchmark": {"name": "CIS M365", "version": "v7.0.0"}, "now": NOW}
    p.update(over)
    return p


@pytest.fixture(scope="module")
def rep():
    return wb.build(_payload())


def _by_control(rows):
    return {r["control_id"]: r for r in rows}


# ── identity and shape ──────────────────────────────────────────────────────

def test_one_column_per_field_nothing_to_parse(rep):
    f = _by_control(rep["findings"])["6.5.1"]
    for key in ("control_id", "category", "effective_risk", "where", "action", "owner", "decision", "detail"):
        assert f[key] not in ("", None), key
    assert "Risk:" not in f["detail"] and "Remediation:" not in f["detail"]


def test_finding_identity_is_stable_across_runs(rep):
    f = _by_control(rep["findings"])["6.5.1"]
    assert f["identity"] == f"cis_m365_v7|6.5.1|{TENANT}"
    assert f["finding_id"] == wb._finding_key("cis_m365_v7", "6.5.1", TENANT)
    again = wb.build(_payload())
    assert _by_control(again["findings"])["6.5.1"]["finding_id"] == f["finding_id"]


def test_control_prefix_stripped_but_raw_kept(rep):
    f = _by_control(rep["findings"])["1.1.3"]
    assert f["control_id"] == "1.1.3" and f["control_raw"] == "CIS 1.1.3"


def test_catalog_fields_present(rep):
    f = _by_control(rep["findings"])["1.1.3"]
    assert f["category"] == "M365 admin center" and f["level"] == "L1" and f["assessment"] == "Automated"


def test_title_prefers_finding_text_over_catalog_keywords(rep):
    f = _by_control(rep["findings"])["1.1.3"]
    assert f["title"].startswith("only 1 global admin")


# ── risk, remediation, sampling ─────────────────────────────────────────────

def test_every_open_finding_is_ranked_and_explained(rep):
    for f in rep["findings"]:
        assert f["risk_band"] in wb.BANDS and f["risk_basis"]
        assert f["where"] and f["action"]


def test_risk_override_sets_effective_risk_but_keeps_derived(rep):
    f = _by_control(rep["findings"])["1.1.3"]
    assert f["risk_override"] == "Critical" and f["effective_risk"] == "Critical"
    assert f["risk_band"] != "Critical" or f["risk_score"] >= 8


def test_sampled_evidence_is_flagged(rep):
    f = _by_control(rep["findings"])["6.1.2"]
    assert f["sampled"] == "yes" and "sampled" in f["evidence_strength"]
    assert rep["summary"]["sampled"] == 1


def test_blast_radius_counts_subjects():
    rows = _rows_three_runs() + [_row(11, "2026-10-12T09:30:00Z", 6, [V651], ["6.5.1"], host="other.onmicrosoft.com")]
    r = wb.build(_payload(rows=rows))
    radii = {(f["control_id"], f["subject"]): f["blast_radius"] for f in r["findings"]}
    assert radii[("6.5.1", TENANT)] == 2 and radii[("6.5.1", "other.onmicrosoft.com")] == 2


# ── unassessable ────────────────────────────────────────────────────────────

def test_unassessable_is_separate_and_split_by_cause(rep):
    u = {r["control_id"]: r for r in rep["unassessable"]}
    assert "2.1.1" not in _by_control(rep["findings"])
    assert u["2.1.1"]["reason"] == "facts_not_collected" and u["2.1.1"]["who_acts"] == "vendor"
    assert u["5.2.4.1"]["reason"] == "attestation_required" and u["5.2.4.1"]["who_acts"] == "customer"
    assert u["9.1.1"]["reason"] == "collector_not_built"
    assert u["7.2.1"]["reason"] == "benchmark_manual" and u["7.2.1"]["subject"] == "*"
    assert set(rep["summary"]["unassessable_by_reason"]) >= {"facts_not_collected", "attestation_required",
                                                             "collector_not_built", "benchmark_manual"}


def test_unassessable_carries_default_owner(rep):
    u = {r["control_id"]: r for r in rep["unassessable"]}
    assert u["5.2.4.1"]["owner"] == "Identity team"


# ── decisions ───────────────────────────────────────────────────────────────

def test_default_owner_by_section_and_override_per_finding(rep):
    f = _by_control(rep["findings"])
    assert f["5.1.2.2"]["owner"] == "Identity team"        # default by section
    assert f["6.5.1"]["owner"] == "Messaging lead"         # decision wins
    assert f["5.1.2.2"]["decision_status"] == "undecided"


def test_accept_without_expiry_is_defaulted_and_flagged(rep):
    d = {r["control_id"]: r for r in rep["decisions"]}
    assert d["6.5.1"]["expires"] == "2026-12-30"           # approved 10-01 + 90 days
    assert "defaulted" in d["6.5.1"]["issues"]
    assert _by_control(rep["findings"])["6.5.1"]["expires"] == "2026-12-30"


def test_team_alias_approver_is_flagged(rep):
    d = {r["control_id"]: r for r in rep["decisions"]}
    assert "not a named person" in d["1.1.3"]["issues"]
    assert d["6.5.1"]["issues"].count("named person") == 0


def test_expired_and_unmatched_decisions_are_visible(rep):
    d = {r["control_id"]: r for r in rep["decisions"]}
    assert d["9.1.1"]["status"] == "unmatched" and d["9.1.1"]["days_to_expiry"] < 0
    assert rep["summary"]["decisions"]["unmatched"] == 1


def test_waiver_from_evidence_shows_as_accepted_and_expiring(rep):
    f = _by_control(rep["findings"])["6.1.2"]
    assert f["status"] == "waived" and f["decision"] == "accept"
    assert f["approver"] == "jane.doe@example.com" and f["decision_status"] == "expiring"


def test_evidence_rows_are_never_modified():
    payload = _payload()
    before = json.dumps(payload["rows"], sort_keys=True)
    wb.build(payload)
    assert json.dumps(payload["rows"], sort_keys=True) == before


def test_emit_waivers_from_accepted_decisions_keeps_defaulted_expiry():
    out = {w["control_id"]: w for w in wb.emit_waivers(DECISIONS, "cis_m365_v7", now=NOW)}
    assert set(out) == {" 6.5.1:", " 9.1.1:"}
    assert all(w["framework"] == "cis_m365_v7" and w["approver"] for w in out.values())
    assert out[" 6.5.1:"]["expires"] == "2026-12-30"      # defaulted in the report → exported too
    assert out[" 9.1.1:"]["expires"] == "2026-09-30"
    assert all(w["expires"] for w in out.values()), "an entry without expiry never matches in OPA"


# ── delta ───────────────────────────────────────────────────────────────────

def test_delta_new_fixed_regressed_still_open(rep):
    d = {(r["control_id"], r["change"]) for r in rep["delta"]}
    assert ("1.1.3", "regressed") in d
    assert ("5.2.3.6", "fixed") in d
    assert ("5.1.2.2", "new") in d
    assert ("6.5.1", "still open") in d
    assert rep["summary"]["delta"] == {"new": 2, "fixed": 1, "regressed": 1, "still_open": 1}


def test_first_run_has_no_delta():
    r = wb.build(_payload(rows=_rows_three_runs()[:3]))
    assert r["delta"] == [] and all(f["delta"] == "first run" for f in r["findings"])


def test_age_and_times_seen(rep):
    f = _by_control(rep["findings"])["6.5.1"]
    assert f["times_seen"] == 3 and f["age_days"] == 42


def test_rows_seconds_apart_form_one_run(rep):
    assert rep["summary"]["previous_runs"][TENANT].startswith("2026-09-15")
    assert rep["summary"]["latest_runs"][TENANT].startswith("2026-10-12")


# ── passed and summary ──────────────────────────────────────────────────────

def test_passed_derived_from_evaluated_ids(rep):
    p = {r["control_id"] for r in rep["passed"]}
    assert p == {"1.1.1", "5.2.3.6"}
    s = rep["summary"]
    assert s["passed"] == 2 and s["failed"] == 3 and s["waived"] == 1


def test_verdict_mentions_regression(rep):
    assert "regressed" in rep["summary"]["verdict"]


# ── renderers and contract ──────────────────────────────────────────────────

def test_xlsx_is_a_valid_package_with_all_sheets(rep, tmp_path):
    path = tmp_path / "wb.xlsx"
    wb.write_xlsx(rep, path)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert "[Content_Types].xml" in names and "xl/workbook.xml" in names
        assert sum(n.startswith("xl/worksheets/sheet") for n in names) == len(wb.SHEETS)
        book = z.read("xl/workbook.xml").decode()
        for name, _ in wb.SHEETS:
            assert f'name="{name}"' in book
        sheet2 = z.read("xl/worksheets/sheet2.xml").decode()
        assert "Finding ID" in sheet2 and "<autoFilter" in sheet2


def test_csv_headers_match_contract(rep):
    for name, cols in wb.SHEETS[1:]:
        header = next(csv.reader(io.StringIO(wb.sheet_csv(rep, name))))
        assert header == [lbl for _, lbl, _ in cols], name


def test_published_contract_matches_generated_section_exactly():
    doc = (_root / "docs" / "operations" / "FINDINGS_WORKBOOK_CONTRACT.md").read_text()
    generated = wb.print_contract().strip()
    assert generated in doc, "docs/operations/FINDINGS_WORKBOOK_CONTRACT.md must embed --print-contract verbatim"
    # And the sheet names in the xlsx are the contract's, in order
    assert [n for n, _ in wb.SHEETS] == ["Summary", "Findings", "Unassessable", "Decisions", "Delta", "Passed"]


def test_html_and_markdown_render(rep):
    html = wb.render_html(rep)
    md = wb.render_markdown(rep)
    assert "Findings Workbook" in html and "regressed" in html
    assert "## Findings" in md and "## Unassessable" in md and "## Delta" in md


def test_no_rows_yields_empty_but_valid_report():
    r = wb.build(_payload(rows=[]))
    assert r["findings"] == [] and r["summary"]["subject_count"] == 0
    assert any(u["reason"] == "not_evaluated" for u in r["unassessable"])


# ── hardening ───────────────────────────────────────────────────────────────

def test_formula_injection_is_neutralised_in_csv_and_xlsx(tmp_path):
    rows = _rows_three_runs()
    rows[6]["violations"] = ["CIS 1.1.3: =HYPERLINK(\"http://evil\",\"click\") only 1 admin"]
    r = wb.build(_payload(rows=rows))
    title = _by_control(r["findings"])["1.1.3"]["title"]
    assert title.startswith("=")                       # the report keeps the evidence verbatim
    csv_text = wb.sheet_csv(r, "Findings")
    assert "'=HYPERLINK" in csv_text and ",=HYPERLINK" not in csv_text
    path = tmp_path / "x.xlsx"
    wb.write_xlsx(r, path)
    with zipfile.ZipFile(path) as z:
        sheet = z.read("xl/worksheets/sheet2.xml").decode()
    assert "&#x27;=HYPERLINK" in sheet or "'=HYPERLINK" in sheet
    assert "<f>" not in sheet                           # no formula cells ever
    assert wb._cell_safe(12) == 12 and wb._cell_safe("plain") == "plain"


def test_emitted_waivers_are_anchored_not_prefix_matches():
    out = wb.emit_waivers({"decisions": [
        {"control_id": "CIS 1.1", "decision": "accept", "approver": "a@b", "expires": "2027-01-01"},
        {"control_id": "RHEL-09-211010", "decision": "accept", "approver": "a@b", "expires": "2027-01-01"},
        {"control_id": "", "decision": "accept", "approver": "a@b"},
    ]}, "cis_rhel9")
    ids = [w["control_id"] for w in out]
    assert ids == [" 1.1:", "RHEL-09-211010"]
    assert " 1.1:" in "CIS 1.1: separate /tmp" and " 1.1:" in "CIS L2 1.1: x"
    assert " 1.1:" not in "CIS 1.1.3: admins" and " 1.1:" not in "CIS 11.1: x"


# ── review fixes (PR #811) ──────────────────────────────────────────────────

def test_expired_evidence_waiver_reopens_the_finding():
    rows = _rows_three_runs()
    rows[8]["metadata"]["waivers_applied"][0]["waiver"]["expires"] = "2026-10-01"   # before NOW
    r = wb.build(_payload(rows=rows))
    f = _by_control(r["findings"])["6.1.2"]
    assert f["status"] == "open" and f["decision_status"] == "expired"
    assert r["summary"]["failed"] == 4 and r["summary"]["waived"] == 0


def test_fixed_requires_latest_run_to_evaluate_the_control():
    rows = _rows_three_runs()
    # latest run: 6.5.1 no longer in violations, but recorded as an evidence gap
    rows[8]["violations"] = ["CIS 6.5.1: Exchange facts were not collected (this is not a pass)"]
    r = wb.build(_payload(rows=rows))
    assert ("6.5.1", "fixed") not in {(d["control_id"], d["change"]) for d in r["delta"]}
    assert any(u["control_id"] == "6.5.1" and u["reason"] == "facts_not_collected" for u in r["unassessable"])
    # latest run drops the control from the evaluated list entirely → not fixed either
    rows = _rows_three_runs()
    rows[8]["violations"] = []
    rows[8]["metadata"]["evaluated_control_ids"] = ["6.1.2"]
    r = wb.build(_payload(rows=rows))
    assert ("6.5.1", "fixed") not in {(d["control_id"], d["change"]) for d in r["delta"]}


def test_regressed_requires_a_verified_pass_in_between():
    rows = _rows_three_runs()
    # previous run recorded 1.1.3 as a gap instead of a clean pass
    rows[3]["violations"] = ["CIS 1.1.3: admin facts were not collected (this is not a pass)"]
    r = wb.build(_payload(rows=rows))
    assert _by_control(r["findings"])["1.1.3"]["delta"] == "still open"
    assert r["summary"]["delta"]["regressed"] == 0


def test_wrapped_violation_payload_is_unwrapped():
    rows = _rows_three_runs()
    rows[6]["violations"] = {"violations": [V113]}
    r = wb.build(_payload(rows=rows))
    ids = {f["control_id"] for f in r["findings"]}
    assert "1.1.3" in ids and "violations" not in ids


def test_catalog_omissions_are_per_subject():
    rows = _rows_three_runs() + [
        _row(11, "2026-10-12T09:30:00Z", 1, [], ["1.1.1"], host="other.onmicrosoft.com")]   # omits 1.1.3
    r = wb.build(_payload(rows=rows))
    u = {(x["control_id"], x["subject"]) for x in r["unassessable"]}
    assert ("1.1.3", "other.onmicrosoft.com") in u          # omitted by one subject only
    assert ("1.1.3", TENANT) not in u and ("1.1.3", "*") not in u
    assert ("7.2.1", "*") in u                               # untouched by every subject → one row
