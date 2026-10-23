#!/usr/bin/env python3
"""
Assemble a software-supply-chain facts document — the input contract the
`benchmarks/supply_chain/` Rego evaluates (baseline, SLSA, SSDF, coverage).

Deterministic, no network — the testable core of supply-chain fact collection.
The playbook side fetches the raw inputs (GitHub branch-protection via the API,
an SBOM file, KEV/OSV results, provenance/attestation) and hands them here to be
normalized into one document. Fail-closed: a section that is absent or unshaped
simply isn't emitted, so the Rego's `default false` reports the control
unsatisfied rather than passing on missing data.

Two concrete normalizers are provided; the rest of the contract is passed through:
  - parse_github_protection()  GitHub REST branch-protection -> the `source` facts
                               (this is the source-integrity control AAC dogfoods).
  - parse_cyclonedx_sbom()     a CycloneDX SBOM -> the `sbom` facts (PURLs).
"""
from __future__ import annotations

import json
import sys


def parse_github_protection(protection: dict, required_signatures: bool | None = None) -> dict:
    """Map a GitHub `GET /repos/{o}/{r}/branches/{b}/protection` response to the
    `source` facts. An empty/None protection object means the branch is
    unprotected (GitHub returns 404 there); the caller passes {} in that case."""
    if protection is None:
        protection = {}
    if not isinstance(protection, dict):
        raise ValueError("protection must be an object (or empty)")
    prr = protection.get("required_pull_request_reviews") or {}
    if required_signatures is None:
        # required_signatures is a separate sub-resource; accept it inline too.
        required_signatures = bool((protection.get("required_signatures") or {}).get("enabled", False))
    return {
        "branch_protection": bool(protection),
        "required_reviews": int(prr.get("required_approving_review_count", 0) or 0),
        "code_owner_review": bool(prr.get("require_code_owner_reviews", False)),
        "required_status_checks": bool(protection.get("required_status_checks")),
        "enforce_admins": bool((protection.get("enforce_admins") or {}).get("enabled", False)),
        "signed_commits": bool(required_signatures),
    }


def parse_cyclonedx_sbom(sbom: dict) -> dict:
    """Map a CycloneDX SBOM to the `sbom` facts (present + PURLs)."""
    if not isinstance(sbom, dict):
        raise ValueError("sbom must be a CycloneDX object")
    fmt = str(sbom.get("bomFormat", "")).lower()
    # `components` must be a list. A malformed SBOM (dict/string/etc. here) is
    # treated as having no parseable components rather than being miscounted —
    # keeping component_count and the PURL set deterministic and fail-closed.
    raw_components = sbom.get("components")
    components = raw_components if isinstance(raw_components, list) else []
    purls = [str(c["purl"]) for c in components if isinstance(c, dict) and c.get("purl")]
    return {
        "present": True,
        "format": "cyclonedx" if "cyclonedx" in fmt else (fmt or "unknown"),
        "components": [{"purl": p} for p in purls],
        "component_count": len(components),
    }


def assemble_facts(
    github_protection: dict | None = None,
    required_signatures: bool | None = None,
    sbom: dict | None = None,
    provenance: dict | None = None,
    signing: dict | None = None,
    dependencies: dict | None = None,
    vulnerabilities: dict | None = None,
    build: dict | None = None,
    artifact: dict | None = None,
) -> dict:
    """Assemble the supply-chain facts document. Absent sections are omitted
    (fail-closed: the Rego defaults them to unsatisfied)."""
    facts: dict = {}
    if github_protection is not None:
        facts["source"] = parse_github_protection(github_protection, required_signatures)
    if sbom is not None:
        facts["sbom"] = parse_cyclonedx_sbom(sbom)
    for key, section in (
        ("provenance", provenance), ("signing", signing), ("dependencies", dependencies),
        ("vulnerabilities", vulnerabilities), ("build", build), ("artifact", artifact),
    ):
        # Only emit shaped (object) sections. A non-dict pass-through is unshaped
        # and is dropped, so the contract stays fail-closed — as the module
        # docstring promises — instead of forwarding e.g. a bare string to the Rego.
        if isinstance(section, dict):
            facts[key] = section
    return facts


def from_sources(sources: dict) -> dict:
    """Assemble from a single 'raw sources' document (the CLI form)."""
    if not isinstance(sources, dict):
        raise ValueError("sources must be an object")
    return assemble_facts(
        github_protection=sources.get("github_protection"),
        required_signatures=sources.get("required_signatures"),
        sbom=sources.get("sbom"),
        provenance=sources.get("provenance"),
        signing=sources.get("signing"),
        dependencies=sources.get("dependencies"),
        vulnerabilities=sources.get("vulnerabilities"),
        build=sources.get("build"),
        artifact=sources.get("artifact"),
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: supply_chain_facts.py <raw-sources.json>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        sources = json.load(fh)
    json.dump(from_sources(sources), sys.stdout, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
