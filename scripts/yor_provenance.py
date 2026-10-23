#!/usr/bin/env python3
"""
yor_provenance.py — link a compliance finding back to the IaC commit that
produced it, using the git-provenance tags Yor stamps onto Terraform resources
(gap-analysis item #4).

Yor (https://github.com/bridgecrewio/yor) writes tags such as:
  yor_trace, git_commit, git_file, git_repo (or git_repository), git_org,
  git_last_modified_by, git_modifiers
onto every resource. Those tags travel into the Terraform plan JSON, so a finding
that names a resource can be joined back to the exact commit/file/author — a
provenance link no pre-apply scanner can produce, because it never sees runtime.

Two uses:
  * as a library — extract_provenance(plan_json) and enrich(violations, prov)
  * as a CLI — reads a violations JSON array from stdin, a Terraform plan JSON
    from PLAN_FILE, and writes the enriched violations array to stdout.

Environment (CLI):
  PLAN_FILE   — path to `terraform show -json` output (required for the CLI)
"""

import json
import os
import sys

# Canonical Yor tag keys (accept a couple of spellings Yor/forks use).
_TRACE = "yor_trace"
_COMMIT = ("git_commit",)
_FILE = ("git_file",)
_REPO = ("git_repo", "git_repository")
_ORG = ("git_org",)
_AUTHOR = ("git_last_modified_by", "git_modifiers")


def _first(tags: dict, keys) -> str:
    for k in keys:
        v = tags.get(k)
        if v:
            return str(v)
    return ""


def _resources(plan: dict):
    """Yield (address, tags) for every resource in a Terraform plan JSON.

    Covers both `resource_changes[]` (plan) and
    `planned_values.root_module...resources[]` (planned values), and nested
    child modules. Tags may live under `.tags` or `.tags_all`.
    """
    for rc in plan.get("resource_changes", []) or []:
        address = rc.get("address", "")
        if not address:
            continue  # never key provenance by "" — enrich() would attach it to
            # any violation whose `resource` is empty/missing.
        after = (rc.get("change", {}) or {}).get("after") or {}
        tags = after.get("tags") or after.get("tags_all") or {}
        if isinstance(tags, dict):
            yield address, tags

    def _walk_module(mod):
        for r in mod.get("resources", []) or []:
            address = r.get("address", "")
            if not address:
                continue  # same empty-address guard as resource_changes above
            vals = r.get("values", {}) or {}
            tags = vals.get("tags") or vals.get("tags_all") or {}
            if isinstance(tags, dict):
                yield address, tags
        for child in mod.get("child_modules", []) or []:
            yield from _walk_module(child)

    root = (plan.get("planned_values", {}) or {}).get("root_module")
    if isinstance(root, dict):
        yield from _walk_module(root)


def extract_provenance(plan: dict) -> dict:
    """Return {address: provenance} for every Yor-tagged resource.

    provenance keys: yor_trace, commit_ref, git_file, git_repo, git_org,
    git_author. Only resources with a non-empty address and a yor_trace or
    git_commit tag are included.
    """
    prov = {}
    for address, tags in _resources(plan):
        trace = tags.get(_TRACE)
        commit = _first(tags, _COMMIT)
        if not (trace or commit):
            continue  # not Yor-stamped
        prov[address] = {
            "yor_trace": str(trace) if trace else "",
            "commit_ref": commit,
            "git_file": _first(tags, _FILE),
            "git_repo": _first(tags, _REPO),
            "git_org": _first(tags, _ORG),
            "git_author": _first(tags, _AUTHOR),
        }
    return prov


def enrich(violations: list, prov: dict) -> list:
    """Attach provenance to each violation whose `resource` matches a tagged
    resource address. Violations without a match are returned unchanged."""
    out = []
    for v in violations:
        v = dict(v) if isinstance(v, dict) else {"description": str(v)}
        addr = v.get("resource", "")
        p = prov.get(addr)
        if p:
            v["provenance"] = p
            # Promote the commit to a top-level field so downstream reports and
            # the compliance_results row can key on it without unpacking.
            if p.get("commit_ref"):
                v["commit_ref"] = p["commit_ref"]
        out.append(v)
    return out


def main():
    raw = sys.stdin.read().strip()
    violations = json.loads(raw) if raw else []
    if isinstance(violations, dict):
        violations = violations.get("violations", [])
    plan_file = os.environ.get("PLAN_FILE", "")
    prov = {}
    if plan_file and os.path.exists(plan_file):
        with open(plan_file) as fh:
            prov = extract_provenance(json.load(fh))
    print(json.dumps(enrich(violations, prov), indent=2, default=str))


if __name__ == "__main__":
    main()
