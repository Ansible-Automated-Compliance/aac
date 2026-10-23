"""Tests for scripts/risk_score.py — the F1 generic risk function.

Pins the properties F1 must guarantee: no finding is unranked, severity is
used when present and criticality fills in when it is absent, blast radius and
elevators raise risk, evidence gaps are never scored as failures, ordering is
risk-first and deterministic, and every score is explainable.
"""
import importlib.util
import pathlib

import yaml

_root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("risk_score", _root / "scripts" / "risk_score.py")
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)

M365 = yaml.safe_load((_root / "ansible" / "vars" / "risk" / "cis_m365_v7.yml").read_text())


def _f(**kw):
    base = {"framework": "cis_m365_v7", "control_id": "1.3.3", "subject": "tenant",
            "finding_type": "violation", "severity": None, "title": "x", "blast_radius": 1}
    base.update(kw)
    return base


def test_no_finding_is_unranked():
    out = rs.run({"findings": [_f(), _f(control_id="5.2.3.6")], "config": M365})
    for x in out["findings"]:
        assert x["risk"]["band"] in ("Critical", "High", "Medium", "Low")


def test_severity_used_when_present():
    # a finding WITH severity ignores criticality and scores by severity
    out = rs.run({"findings": [_f(severity="critical", control_id="9.9.9")], "config": M365})
    x = out["findings"][0]
    assert x["risk"]["band"] in ("Critical", "High")
    assert any("severity: critical" in fct for fct in x["risk"]["factors"])


def test_criticality_fills_in_when_severity_absent():
    # M365 findings have no severity -> criticality drives the base
    out = rs.run({"findings": [_f(control_id="5.2.3.6", title="MFA not enabled")], "config": M365})
    x = out["findings"][0]
    assert any("criticality" in fct for fct in x["risk"]["factors"])
    assert x["risk"]["band"] in ("Critical", "High")  # 5.2 base 4 + MFA elevator


def test_blast_radius_raises_risk():
    low = rs.run({"findings": [_f(control_id="1.3.3", blast_radius=1)], "config": M365})["findings"][0]
    high = rs.run({"findings": [_f(control_id="1.3.3", blast_radius=15)], "config": M365})["findings"][0]
    assert high["risk"]["score"] > low["risk"]["score"]
    assert any("10+" in fct for fct in high["risk"]["factors"])


def test_elevators_raise_risk():
    plain = rs.run({"findings": [_f(control_id="6.1.1", title="setting is off")], "config": M365})["findings"][0]
    legacy = rs.run({"findings": [_f(control_id="6.5.1", title="legacy authentication bypasses MFA")], "config": M365})["findings"][0]
    assert legacy["risk"]["score"] > plain["risk"]["score"]


def test_evidence_gaps_not_scored_as_failures():
    out = rs.run({"findings": [_f(finding_type="evidence_gap", control_id="2.1.1")], "config": M365})
    assert out["findings"] == []
    assert out["evidence_gaps"] == 1
    assert out["gaps"][0]["risk"]["band"] == "Unable to assess"


def test_ordering_risk_first_and_deterministic():
    findings = [_f(control_id="1.3.3"), _f(control_id="5.2.3.6", title="MFA off"),
                _f(control_id="6.5.1", title="legacy authentication")]
    a = [x["control_id"] for x in rs.run({"findings": findings, "config": M365})["findings"]]
    b = [x["control_id"] for x in rs.run({"findings": findings[::-1], "config": M365})["findings"]]
    assert a == b
    order = ["Critical", "High", "Medium", "Low"]
    bands = [x["risk"]["band"] for x in rs.run({"findings": findings, "config": M365})["findings"]]
    assert [order.index(x) for x in bands] == sorted(order.index(x) for x in bands)


def test_explainable_every_finding_shows_factors():
    out = rs.run({"findings": [_f(), _f(control_id="5.2.3.6")], "config": M365})
    for x in out["findings"]:
        assert x["risk"]["factors"], "every risk must list its factors"


def test_works_with_no_config_universal_defaults():
    # severity-only scoring with no framework config at all
    out = rs.run({"findings": [_f(severity="high", control_id="x"), _f(severity=None, control_id="y")]})
    assert out["findings"][0]["risk"]["band"] in ("Critical", "High", "Medium", "Low")
    # no-severity, no-config -> neutral default criticality, still ranked
    assert all(x["risk"]["band"] in ("Critical", "High", "Medium", "Low") for x in out["findings"])


def test_prefix_boundary_not_greedy():
    # criticality prefix "1.1" must not match "1.10.x" (no such control, but
    # the matcher must be boundary-correct regardless)
    cfg = {"criticality": {"1.1": 4, "_default": 1}}
    hit = rs.score_finding({"control_id": "1.1.3", "severity": None, "title": ""}, cfg)
    miss = rs.score_finding({"control_id": "1.10.3", "severity": None, "title": ""}, cfg)
    assert hit["score"] == 4
    assert miss["score"] == 1
