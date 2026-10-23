"""Unit tests for the goss audit parser (ansible-lockdown ingestion)."""
from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from goss_audit_parse import parse_goss_results  # noqa: E402

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "goss_audit_sample.json")


@pytest.fixture(scope="module")
def parsed() -> dict:
    with open(_FIXTURE, "r", encoding="utf-8") as fh:
        return parse_goss_results(fh.read())


def test_counts_exclude_skips(parsed):
    # Fixture: 3 pass (result 0), 1 fail (result 1), 1 skip (result 2).
    assert parsed["passed"] == 3
    assert parsed["failed"] == 1
    assert parsed["skipped"] == 1
    assert parsed["total_evaluated"] == 4      # skip NOT counted
    assert parsed["compliant"] is False


def test_compliance_pct_excludes_skips(parsed):
    # 3 passed / 4 evaluated = 75.0 — NOT 3/5 (which would wrongly count the skip).
    assert parsed["compliance_pct"] == pytest.approx(75.0)


def test_by_status(parsed):
    assert parsed["by_status"]["pass"] == 3
    assert parsed["by_status"]["fail"] == 1
    assert parsed["by_status"]["skip"] == 1


def test_failed_rules(parsed):
    assert len(parsed["failed_rules"]) == 1
    aide = parsed["failed_rules"][0]
    assert aide["title"] == "1.3.1 Ensure AIDE is installed"
    assert aide["result"] == "fail"


def test_meta_captured_for_crosswalk(parsed):
    aide = parsed["failed_rules"][0]
    assert aide["meta"]["control-id"] == "1.3.1"


def test_title_fallback_to_resource_coords(parsed):
    # The last check has no title — falls back to type:id:property.
    sysctl = next(r for r in parsed["results"] if r["resource_id"].startswith("sysctl"))
    assert sysctl["title"] == "Command:sysctl-net.ipv4.ip_forward:exit-status"


def test_summary_passthrough(parsed):
    assert parsed["test_count"] == 5
    assert parsed["failed_count_reported"] == 1


def test_result_code_missing_falls_back_to_successful():
    doc = '{"results":[{"successful":true},{"successful":false},{}]}'
    out = parse_goss_results(doc)
    assert out["passed"] == 1
    # successful:false (no code) -> classified "fail"; missing boolean -> "unknown".
    assert out["by_status"]["fail"] == 1
    assert out["by_status"]["unknown"] == 1
    # both non-pass count as violations (fail-closed).
    assert out["failed"] == 2


def test_rejects_non_goss_json():
    with pytest.raises(ValueError, match="results"):
        parse_goss_results('{"summary": {}}')


def test_rejects_garbage():
    with pytest.raises(ValueError):
        parse_goss_results("not json")
