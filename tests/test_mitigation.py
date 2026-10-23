"""Tests for scripts/mitigation.py — the F2 mitigation function.

Pins: every finding gets a concrete mitigation (where + action), the most
specific control-prefix wins, method is carried, evidence gaps get a
collection-oriented fix, and the default fills in when nothing matches.
"""
import importlib.util
import pathlib

import yaml

_root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("mitigation", _root / "scripts" / "mitigation.py")
mi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mi)

M365 = yaml.safe_load((_root / "ansible" / "vars" / "mitigation" / "cis_m365_v7.yml").read_text())


def _f(cid, **kw):
    base = {"framework": "cis_m365_v7", "control_id": cid, "subject": "t",
            "finding_type": "violation", "title": "x"}
    base.update(kw)
    return base


def test_every_finding_gets_a_mitigation():
    out = mi.run({"findings": [_f("1.1.3"), _f("5.2.3.6"), _f("9.9.9")], "catalog": M365})
    for f in out["findings"]:
        assert f["mitigation"]["where"] and f["mitigation"]["action"]
        assert f["mitigation"]["method"] in ("manual", "automated", "governed")


def test_most_specific_prefix_wins():
    # 5.1.2.2 must match "5.1.2" (User settings), not the broader "5.1"
    out = mi.run({"findings": [_f("5.1.2.2")], "catalog": M365})
    assert "User settings" in out["findings"][0]["mitigation"]["where"]
    # a 5.1.x not under 5.1.2/3/5 falls back to the broader "5.1"
    out2 = mi.run({"findings": [_f("5.1.8.1")], "catalog": M365})
    assert out2["findings"][0]["mitigation"]["where"].endswith("Users")


def test_section_prefix_matches_subcontrols():
    out = mi.run({"findings": [_f("6.5.1"), _f("2.1.1"), _f("8.5.3")], "catalog": M365})
    by = {f["control_id"]: f["mitigation"]["where"] for f in out["findings"]}
    assert "Exchange admin center" in by["6.5.1"]
    assert "Defender" in by["2.1.1"]
    assert "Teams admin center" in by["8.5.3"]


def test_evidence_gap_gets_collection_fix():
    out = mi.run({"findings": [_f("2.1.1", finding_type="evidence_gap")], "catalog": M365})
    m = out["findings"][0]["mitigation"]
    assert "collection" in m["action"].lower() or "collect" in m["action"].lower()


def test_default_fills_in_for_unknown_control():
    out = mi.run({"findings": [_f("99.9.9")], "catalog": M365})
    assert out["findings"][0]["mitigation"]["where"]  # _default used, non-empty


def test_no_catalog_still_gives_a_pointer():
    out = mi.run({"findings": [_f("1.1.1")]})
    assert out["findings"][0]["mitigation"]["where"]  # generic default


def test_prefix_boundary_not_greedy():
    cat = {"mitigations": {"1.1": {"where": "W11", "action": "A", "method": "manual"},
                           "_default": {"where": "WD", "action": "A", "method": "manual"}}}
    assert mi.mitigate({"control_id": "1.1.3"}, cat)["where"] == "W11"
    assert mi.mitigate({"control_id": "1.10.3"}, cat)["where"] == "WD"


def test_csv_render():
    out = mi.run({"findings": [_f("6.5.1", title="legacy auth")], "catalog": M365})
    csv_text = mi.to_csv(out)
    assert "Where,Action,Method" in csv_text
    assert "Exchange admin center" in csv_text
