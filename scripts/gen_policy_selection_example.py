#!/usr/bin/env python3
"""Generate ansible/vars/policy_selection.yml.example — the checkable list of
every framework the OPA loader can load.

Sources of truth (never hand-maintain the example):
  - ansible/playbooks/load_opa_policies.yml   -> loader keys, per container
  - ansible/playbooks/seed_framework_catalog.yml -> display names, descriptions

Regenerate after adding a framework to the loader:
    python3 scripts/gen_policy_selection_example.py > \
        ansible/vars/policy_selection.yml.example

The CI gate "Loader keys have catalog rows" guarantees every loader key has
catalog metadata, so a missing description here means the gate is broken.
"""
from __future__ import annotations

import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOADER = ROOT / "ansible/playbooks/load_opa_policies.yml"
CATALOG = ROOT / "ansible/playbooks/seed_framework_catalog.yml"


def loader_containers():
    """[(container_name, [key, ...])] in loader order."""
    plays = yaml.safe_load(LOADER.read_text())
    containers = plays[0]["vars"]["opa_containers"]
    return [(c["name"], [fw["key"] for fw in c["frameworks"]]) for c in containers]


def catalog_meta():
    """loader_key -> {display_name, description, domain}."""
    plays = yaml.safe_load(CATALOG.read_text())
    meta = {}

    def walk(node):
        if isinstance(node, dict):
            if "loader_key" in node and "display_name" in node:
                meta[node["loader_key"]] = node
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(plays)
    return meta


def main():
    meta = catalog_meta()
    out = []
    out.append("---")
    out.append("# policy_selection.yml — pick the frameworks the OPA loader loads.")
    out.append("#")
    out.append("# Copy to ansible/vars/policy_selection.yml (gitignored, yours to edit),")
    out.append("# set unwanted frameworks to false, and run the loader with source=file:")
    out.append('#   "AAC - Load OPA Policies" with extra_vars: {source: file}')
    out.append("#")
    out.append("# Rules the loader enforces:")
    out.append("#   - every key here must be a real loader key (typos fail the run)")
    out.append("#   - deselected frameworks are LISTED in the job output, never silently dropped")
    out.append("#   - deselecting does not unload policies already in a running OPA —")
    out.append("#     redeploy the OPA containers (or run a database-mode reconcile) to prune")
    out.append("#")
    out.append("# This example lists every loadable framework, all enabled — identical to")
    out.append("# source=all. Regenerate: python3 scripts/gen_policy_selection_example.py")
    out.append("")
    out.append("policy_selection:")

    missing = []
    total = 0
    for cname, keys in loader_containers():
        out.append(f"  # ── {cname} " + "─" * max(4, 58 - len(cname)))
        for key in keys:
            total += 1
            m = meta.get(key)
            if m is None:
                missing.append(key)
                out.append(f"  {key}: true")
                continue
            desc = str(m.get("description", "")).strip().replace("\n", " ")
            if len(desc) > 96:
                desc = desc[:93] + "..."
            out.append(f"  # {m['display_name']} — {desc}")
            out.append(f"  {key}: true")
        out.append("")

    sys.stdout.write("\n".join(out).rstrip() + "\n")
    print(f"# {total} frameworks listed", file=sys.stderr)
    if missing:
        print(f"WARNING: no catalog row for: {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
