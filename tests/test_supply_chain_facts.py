"""Unit tests for the supply-chain facts collector/normalizer."""
from __future__ import annotations

import json
import os
import sys

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from supply_chain_facts import (  # noqa: E402
    assemble_facts,
    from_sources,
    parse_cyclonedx_sbom,
    parse_github_protection,
)

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "supply_chain_raw_sources.json")


def test_github_protection_maps_source():
    p = {
        "required_pull_request_reviews": {"required_approving_review_count": 1, "require_code_owner_reviews": True},
        "required_status_checks": {"contexts": ["ci"]},
        "enforce_admins": {"enabled": False},
    }
    s = parse_github_protection(p, required_signatures=True)
    assert s["branch_protection"] is True
    assert s["required_reviews"] == 1
    assert s["code_owner_review"] is True
    assert s["required_status_checks"] is True
    assert s["enforce_admins"] is False
    assert s["signed_commits"] is True


def test_github_protection_unprotected():
    # GitHub returns 404 for an unprotected branch; the caller passes {}.
    s = parse_github_protection({})
    assert s["branch_protection"] is False
    assert s["required_reviews"] == 0
    assert s["code_owner_review"] is False
    assert s["signed_commits"] is False


def test_github_protection_signatures_inline():
    s = parse_github_protection({"required_signatures": {"enabled": True}})
    assert s["signed_commits"] is True


def test_cyclonedx_sbom():
    sbom = {"bomFormat": "CycloneDX", "components": [{"purl": "pkg:pypi/requests@2.31"}, {"name": "no-purl"}]}
    f = parse_cyclonedx_sbom(sbom)
    assert f["present"] is True
    assert f["format"] == "cyclonedx"
    assert f["components"] == [{"purl": "pkg:pypi/requests@2.31"}]  # component with no PURL is not counted as a PURL
    assert f["component_count"] == 2


def test_assemble_omits_absent_sections():
    # Fail-closed: absent inputs are omitted, so the Rego defaults them to unsatisfied.
    facts = assemble_facts(github_protection={"required_pull_request_reviews": {}})
    assert "source" in facts
    assert "sbom" not in facts
    assert "vulnerabilities" not in facts


def test_from_sources_round_trip():
    with open(_FIXTURE, "r", encoding="utf-8") as fh:
        sources = json.load(fh)
    facts = from_sources(sources)
    assert facts["source"]["code_owner_review"] is True
    assert facts["source"]["signed_commits"] is True
    assert facts["source"]["required_reviews"] == 1
    assert len(facts["sbom"]["components"]) == 2
    assert facts["sbom"]["format"] == "cyclonedx"
    assert facts["artifact"]["capabilities"] == ["auth", "crypto"]


def test_cyclonedx_components_not_a_list():
    # A malformed SBOM whose `components` is not a list must not miscount:
    # treat it as zero parseable components (deterministic + fail-closed).
    f = parse_cyclonedx_sbom({"bomFormat": "CycloneDX", "components": {"purl": "pkg:pypi/x@1"}})
    assert f["present"] is True
    assert f["component_count"] == 0
    assert f["components"] == []


def test_cyclonedx_purl_coerced_to_str():
    # A non-string PURL is coerced so the facts contract is uniform.
    f = parse_cyclonedx_sbom({"bomFormat": "CycloneDX", "components": [{"purl": 12345}]})
    assert f["components"] == [{"purl": "12345"}]
    assert all(isinstance(c["purl"], str) for c in f["components"])


def test_assemble_drops_non_dict_passthrough():
    # Only shaped (object) sections are emitted; a non-dict is unshaped and dropped.
    facts = assemble_facts(
        github_protection={"required_pull_request_reviews": {}},
        signing="yes",              # not an object -> must not appear
        build={"hardened": True},   # object -> appears
    )
    assert "signing" not in facts
    assert facts["build"] == {"hardened": True}


def test_from_sources_rejects_non_dict():
    # Malformed top-level JSON (e.g. a list) is rejected consistently with the
    # other entry points, rather than raising an opaque AttributeError.
    with pytest.raises(ValueError):
        from_sources([])
    with pytest.raises(ValueError):
        from_sources("not-an-object")


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        parse_github_protection("not-an-object")
    with pytest.raises(ValueError):
        parse_cyclonedx_sbom([])
