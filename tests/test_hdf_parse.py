"""Unit tests for the HDF/OHDF parser (MITRE SAF ingestion)."""
from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from hdf_parse import parse_hdf_results  # noqa: E402

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "hdf_sample.json")


@pytest.fixture(scope="module")
def parsed() -> dict:
    with open(_FIXTURE, "r", encoding="utf-8") as fh:
        return parse_hdf_results(fh.read())


def test_by_status_buckets(parsed):
    # V-1,V-7 pass; V-2,V-6 fail; V-5 error; V-4 not-reviewed; V-3 no-impact; V-8 waived.
    bs = parsed["by_status"]
    assert bs["passed"] == 2
    assert bs["failed"] == 2
    assert bs["profile_error"] == 1
    assert bs["not_reviewed"] == 1
    assert bs["no_impact"] == 1
    assert bs["waived"] == 1


def test_violations_include_error_exclude_neutral(parsed):
    # Failed (V-2, V-6) + Profile Error (V-5) are violations; not-reviewed/no-impact are not.
    ids = sorted(v["id"] for v in parsed["failed_rules"])
    assert ids == ["V-2", "V-5", "V-6"]
    assert parsed["failed"] == 3


def test_denominator_excludes_neutral_and_waived(parsed):
    # passed(2) + violations(3) = 5. not_reviewed, no_impact, waived all excluded.
    assert parsed["total_evaluated"] == 5
    assert parsed["compliance_pct"] == pytest.approx(40.0)
    assert parsed["compliant"] is False


def test_strict_pct_counts_not_reviewed_against(parsed):
    # 2 / (5 + 1 not_reviewed) = 33.33 — the stricter, separate number.
    assert parsed["compliance_pct_strict"] == pytest.approx(33.33, abs=0.01)
    # And it must be lower than the primary number, never higher.
    assert parsed["compliance_pct_strict"] <= parsed["compliance_pct"]


def test_no_impact_only_on_explicit_zero(parsed):
    # V-7 omits impact entirely and must be evaluated (passed), NOT excluded as no-impact.
    v7 = next(c for c in parsed["controls"] if c["id"] == "V-7")
    assert v7["bucket"] == "passed"
    assert v7["status"] == "Passed"


def test_mixed_results_roll_up_to_failed(parsed):
    v6 = next(c for c in parsed["controls"] if c["id"] == "V-6")
    assert v6["status"] == "Failed"
    assert v6["bucket"] == "failed"


def test_waiver_retained_not_hidden(parsed):
    assert len(parsed["waived"]) == 1
    w = parsed["waived"][0]
    assert w["id"] == "V-8"
    assert w["bucket"] == "waived"
    assert "AAC-1234" in w["waiver_data"]["justification"]


def test_multiprofile_deduped_prefers_evaluated(parsed):
    # V-1 appears in both the primary (with a passed result) and the inherited
    # profile (no results). It must be counted once, as passed.
    v1 = [c for c in parsed["controls"] if c["id"] == "V-1"]
    assert len(v1) == 1
    assert v1[0]["bucket"] == "passed"
    assert len(parsed["controls"]) == 8   # V-1..V-8, no double-count


def test_nist_crosswalk_carried_through(parsed):
    v2 = next(c for c in parsed["controls"] if c["id"] == "V-2")
    assert v2["nist"] == ["AC-3", "CM-6"]
    assert v2["cci"] == ["CCI-000213"]
    # Violation records carry the evidence messages.
    assert any("0600" in m for m in v2["messages"])


def test_platform_and_profile_metadata(parsed):
    assert parsed["platform"] == {"name": "redhat", "release": "9.2"}
    assert parsed["hdf_version"] == "5.22.3"
    names = {p["name"] for p in parsed["profiles"]}
    assert names == {"aac-test-profile", "inherited-baseline"}


def test_rejects_non_hdf_json():
    with pytest.raises(ValueError, match="profiles"):
        parse_hdf_results('{"results": []}')


def test_rejects_garbage():
    with pytest.raises(ValueError):
        parse_hdf_results("not json")
