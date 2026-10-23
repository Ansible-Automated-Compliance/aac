"""Unit tests for scripts/yor_provenance.py (Yor git-provenance enrichment)."""
from __future__ import annotations

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import yor_provenance as yp  # noqa: E402


# A Terraform plan with one Yor-tagged resource (resource_changes form) and one
# in planned_values (a child module), plus one untagged resource.
_PLAN = {
    "resource_changes": [
        {"address": "aws_s3_bucket.data", "type": "aws_s3_bucket",
         "change": {"actions": ["create"], "after": {"tags": {
             "yor_trace": "trace-123", "git_commit": "abc123def",
             "git_file": "s3.tf", "git_repo": "ynotbhatc/infra",
             "git_org": "ynotbhatc", "git_last_modified_by": "tcoulter",
         }}}},
        {"address": "aws_instance.untagged", "type": "aws_instance",
         "change": {"actions": ["create"], "after": {"tags": {"Name": "x"}}}},
    ],
    "planned_values": {"root_module": {"child_modules": [
        {"resources": [
            {"address": "module.net.aws_security_group.web", "type": "aws_security_group",
             "values": {"tags_all": {"git_commit": "99ff00", "git_file": "net/sg.tf"}}},
        ]},
    ]}},
}


def test_extract_only_yor_tagged():
    prov = yp.extract_provenance(_PLAN)
    assert set(prov) == {"aws_s3_bucket.data", "module.net.aws_security_group.web"}
    assert "aws_instance.untagged" not in prov  # no Yor trace/commit -> skipped


def test_extract_fields():
    prov = yp.extract_provenance(_PLAN)
    s3 = prov["aws_s3_bucket.data"]
    assert s3["commit_ref"] == "abc123def"
    assert s3["git_file"] == "s3.tf"
    assert s3["git_repo"] == "ynotbhatc/infra"
    assert s3["yor_trace"] == "trace-123"
    assert s3["git_author"] == "tcoulter"


def test_tags_all_and_child_module_resolved():
    prov = yp.extract_provenance(_PLAN)
    sg = prov["module.net.aws_security_group.web"]
    assert sg["commit_ref"] == "99ff00"
    assert sg["git_file"] == "net/sg.tf"


def test_enrich_matches_by_resource():
    prov = yp.extract_provenance(_PLAN)
    violations = [
        {"control_id": "CKV_AWS_19", "resource": "aws_s3_bucket.data", "severity": "high"},
        {"control_id": "CKV_AWS_23", "resource": "aws_instance.untagged", "severity": "medium"},
        {"control_id": "CKV_AWS_24", "resource": "unknown.resource", "severity": "low"},
    ]
    out = yp.enrich(violations, prov)
    assert out[0]["commit_ref"] == "abc123def"
    assert out[0]["provenance"]["git_file"] == "s3.tf"
    assert "provenance" not in out[1]  # untagged resource
    assert "provenance" not in out[2]  # unknown resource


def test_enrich_is_nondestructive_on_no_plan():
    violations = [{"control_id": "X", "resource": "aws_s3_bucket.data"}]
    out = yp.enrich(violations, {})
    assert out == violations
    assert "provenance" not in out[0]


def test_empty_plan_yields_no_provenance():
    assert yp.extract_provenance({}) == {}


def test_empty_address_is_not_keyed():
    # A resource with Yor tags but no address must NOT create a ""-keyed entry —
    # enrich() would otherwise attach it to any violation whose resource is empty.
    plan = {
        "resource_changes": [
            {"change": {"actions": ["create"], "after": {"tags": {
                "yor_trace": "t", "git_commit": "abc"}}}},  # no "address"
        ],
        "planned_values": {"root_module": {"resources": [
            {"values": {"tags": {"git_commit": "def"}}},  # no "address"
        ]}},
    }
    prov = yp.extract_provenance(plan)
    assert prov == {}
    assert "" not in prov
    # And a violation with an empty/missing resource gets no provenance.
    out = yp.enrich([{"control_id": "X", "resource": ""}, {"control_id": "Y"}], prov)
    assert all("provenance" not in v for v in out)
