"""Unit tests for the AAC -> HDF exporter, incl. a parse/export round-trip."""
from __future__ import annotations

import json
import os
import sys

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from aac_hdf_export import export_hdf  # noqa: E402
from hdf_parse import parse_hdf_results  # noqa: E402

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "hdf_sample.json")


def test_export_shape_is_valid_hdf():
    result = {
        "hostname": "web01",
        "framework": "cis_rhel9",
        "policy_version": "2.0.0",
        "controls": [
            {"id": "1.1.1", "title": "cramfs disabled", "bucket": "passed", "nist": ["CM-7"], "severity": "low"},
            {"id": "5.2.1", "title": "sshd perms", "bucket": "failed", "nist": ["AC-3"], "severity": "high",
             "message": "mode 0644, expected 0600"},
        ],
    }
    hdf = export_hdf(result)
    # A minimal valid HDF: platform + profiles[].controls[] with result rows.
    assert hdf["profiles"][0]["name"] == "cis_rhel9"
    controls = hdf["profiles"][0]["controls"]
    assert {c["id"] for c in controls} == {"1.1.1", "5.2.1"}
    fail = next(c for c in controls if c["id"] == "5.2.1")
    assert fail["results"][0]["status"] == "failed"
    assert fail["impact"] == 0.7                       # derived from severity high
    assert fail["tags"]["nist"] == ["AC-3"]
    # Asset identity HDF can't hold natively is kept in passthrough.
    assert hdf["passthrough"]["auxiliary_data"][0]["data"]["hostname"] == "web01"


def test_no_impact_exports_zero_impact_no_rows():
    hdf = export_hdf({"framework": "f", "controls": [
        {"id": "x", "bucket": "no_impact"},
    ]})
    ctrl = hdf["profiles"][0]["controls"][0]
    assert ctrl["impact"] == 0.0
    assert ctrl["results"] == []


def test_export_requires_controls():
    with pytest.raises(ValueError, match="controls"):
        export_hdf({"framework": "f"})


def test_roundtrip_preserves_every_bucket():
    # Parse the HDF fixture -> AAC finding set -> export HDF -> re-parse.
    # Every control's AAC bucket must survive the round trip unchanged.
    with open(_FIXTURE, "r", encoding="utf-8") as fh:
        first = parse_hdf_results(fh.read())

    aac_set = {"hostname": "roundtrip-host", "framework": "roundtrip",
               "controls": first["controls"]}
    exported = export_hdf(aac_set)
    second = parse_hdf_results(json.dumps(exported))

    assert second["by_status"] == first["by_status"]
    assert second["total_evaluated"] == first["total_evaluated"]
    assert second["compliance_pct"] == first["compliance_pct"]
    # The waiver survives as a retained, justified exception (not silently dropped).
    assert len(second["waived"]) == 1
    assert "AAC-1234" in second["waived"][0]["waiver_data"]["justification"]
