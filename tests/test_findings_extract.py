"""Tests for scripts/findings_extract.py — the findings-identity core.

Pin the properties that make findings *actionable*: stable identity per
(framework, control, subject), correct control-id extraction for every message
family the library emits, evidence gaps distinguished from control failures,
dedup within and across rows, and no invented subjects.
"""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "findings_extract",
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "findings_extract.py",
)
fx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fx)


def _row(**kw):
    base = {
        "id": 1,
        "hostname": "host01",
        "framework": "cis_rhel9",
        "violations": [],
        "metadata": {},
        "evaluation_timestamp": "2026-09-24T00:00:00Z",
    }
    base.update(kw)
    return base


def _one(msg, **kw):
    out = fx.extract([_row(violations=[msg], **kw)])["findings"]
    assert len(out) == 1, out
    return out[0]


# ── control-id extraction per message family ─────────────────────────────────

def test_cis_os_control():
    f = _one("CIS 1.1.1: Ensure mounting of cramfs is disabled — loaded")
    assert f["control_id"] == "CIS 1.1.1"
    assert f["finding_type"] == "violation"


def test_cis_l2_control():
    assert _one("CIS L2 3.3.3: something")["control_id"] == "CIS L2 3.3.3"


def test_cis_m365_control():
    f = _one("CIS M365 5.1.2.2: Ensure third-party apps blocked", framework="cis_m365_v7")
    assert f["control_id"] == "CIS M365 5.1.2.2"


def test_attestation_bracket_families():
    cases = [
        ("IRS 1075 [Recordkeeping] RK-1: permanent records — not met", "RK-1"),
        ("BSI C5 [Compliance] COM-2: independent audits — not met", "COM-2"),
        ("CJIS [Media Protection] MP-5: sanitized — not met", "MP-5"),
        ("Cyber Essentials [Firewalls] FW-4: admin interfaces — not met", "FW-4"),
    ]
    for msg, expect in cases:
        assert _one(msg)["control_id"] == expect, msg


def test_stig_rule_id():
    assert _one("STIG RHEL-09-231010: separate /var required")["control_id"] == "RHEL-09-231010"
    assert _one("Fails V-25701 on host")["control_id"] == "V-25701"


def test_nerc_cip():
    assert _one("CIP-010 R1 baseline missing")["control_id"] == "CIP-010 R1"


def test_nist_family():
    assert _one("SC-28: data at rest unencrypted")["control_id"] == "SC-28"
    assert _one("NIST AC-6(2): least privilege")["control_id"] == "AC-6(2)"


def test_iso_annex():
    assert _one("ISO 27001 A.8.16 monitoring absent")["control_id"] == "A.8.16"


def test_fallback_is_stable_leading_clause():
    a = _one("Custom policy tripwire: detail one")
    b = _one("Custom policy tripwire: detail two")
    assert a["control_id"] == b["control_id"] == "Custom policy tripwire"


# ── evidence gaps vs violations ──────────────────────────────────────────────

def test_fail_closed_becomes_evidence_gap():
    f = _one("FAIL-CLOSED: no facts supplied for filesystem checks — cannot assess")
    assert f["finding_type"] == "evidence_gap"
    assert f["control_id"].startswith("EVIDENCE-GAP:")
    # same gap → same identity
    g = _one("FAIL-CLOSED: no facts supplied for filesystem checks — cannot assess")
    assert g["control_id"] == f["control_id"]


# ── dict (structured) violations — the OpenSCAP ingest shape ─────────────────

def test_dict_violation_uses_rule_id_and_idents():
    v = {
        "rule_id": "xccdf_org.ssgproject.content_rule_sshd_disable_root_login",
        "title": "Disable SSH Root Login",
        "result": "fail",
        "severity": "medium",
        "idents": [{"system": "https://ncp.nist.gov/cce", "value": "CCE-90638-3"}],
    }
    f = _one(v, framework="openscap_cis")
    assert f["control_id"] == v["rule_id"]
    assert f["severity"] == "medium"
    assert f["refs"]["cce"] == "CCE-90638-3"
    assert f["finding_type"] == "violation"


def test_dict_violation_flat_refs():
    v = {"rule_id": "r1", "cce": "CCE-1", "cci": ["CCI-000366"],
         "nist_800_53": ["AC-6(2)"], "severity": "high", "title": "t"}
    f = _one(v)
    assert f["refs"]["cci"] == ["CCI-000366"]
    assert f["refs"]["nist_800_53"] == ["AC-6(2)"]


# ── identity, dedup, attribution ─────────────────────────────────────────────

def test_same_control_two_hosts_two_findings():
    rows = [_row(hostname="h1", violations=["CIS 1.1.1: x"]),
            _row(hostname="h2", violations=["CIS 1.1.1: x"])]
    out = fx.extract(rows)["findings"]
    assert len(out) == 2
    assert {f["subject"] for f in out} == {"h1", "h2"}


def test_duplicate_message_dedupes_keeping_newest_result():
    rows = [
        _row(id=10, evaluation_timestamp="2026-09-01T00:00:00Z",
             violations=["CIS 1.1.1: x"]),
        _row(id=20, evaluation_timestamp="2026-09-20T00:00:00Z",
             violations=["CIS 1.1.1: x"]),
    ]
    out = fx.extract(rows)["findings"]
    assert len(out) == 1
    assert out[0]["result_id"] == 20


def test_no_subject_no_finding():
    out = fx.extract([_row(hostname="", violations=["CIS 1.1.1: x"])])
    assert out["findings"] == []
    assert out["scanned"] == []


def test_blast_radius_shape():
    """The property the whole layer exists for: one control, N subjects."""
    rows = [_row(hostname=f"h{i}", violations=["CIS M365 5.1.2.2: apps"])
            for i in range(14)]
    out = fx.extract(rows)["findings"]
    controls = {f["control_id"] for f in out}
    assert controls == {"CIS M365 5.1.2.2"}
    assert len({f["subject"] for f in out}) == 14


# ── waived + scanned sets ────────────────────────────────────────────────────

def test_waived_from_metadata():
    row = _row(violations=["CIS 1.1.1: open one"],
               metadata={"waivers_applied": ["CIS 2.2.2: waived thing"]})
    out = fx.extract([row])
    assert [f["control_id"] for f in out["findings"]] == ["CIS 1.1.1"]
    assert [f["control_id"] for f in out["waived"]] == ["CIS 2.2.2"]


def test_scanned_pairs_unique_with_ts():
    rows = [_row(hostname="h1", framework="cis_rhel9"),
            _row(hostname="h1", framework="cis_rhel9"),
            _row(hostname="h2", framework="iso27001")]
    scanned = fx.extract(rows)["scanned"]
    assert len(scanned) == 2
    assert all(s["ts"] for s in scanned)

# ── invalid subjects + legacy rule key (found on first live run) ─────────────

def test_execution_context_subjects_refused():
    for bad in ("automation-job-3602-djg92", "localhost", "127.0.0.1"):
        out = fx.extract([_row(hostname=bad, violations=["CIS 1.1.1: x"])])
        assert out["findings"] == [], bad
        assert out["scanned"] == [], bad


def test_legacy_bare_rule_key():
    v = {"rule": "xccdf_org.ssgproject.content_rule_package_aide_installed",
         "result": "fail"}
    f = _one(v, framework="cis_rhel7")
    assert f["control_id"] == v["rule"]
