#!/usr/bin/env python3
"""Verify every AAP template name an EDA rulebook dispatches to is defined
somewhere in this repository.

The failure class this kills: EDA rulebooks dispatch by TEMPLATE NAME
(`run_job_template` / `run_workflow_template`). A template that was
renamed, or whose seeder was never run on a given controller, makes the
rulebook a SILENT no-op — the event fires, nothing runs, nothing errors
(handover audit §2; the inventory-groups incident recorded there is the
same class). This check is static: a name referenced by a rulebook must
also appear somewhere outside extensions/eda/ (a seeder, CaC file,
bootstrap, or demo script that creates or documents it). It cannot prove
the template exists on a live controller — the runtime complement is the
per-controller seeder — but it catches renames and orphaned references
at PR time, where they are cheap.

Exit 0 = every referenced name is defined/known; 1 = orphans found.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
RULEBOOKS = REPO / "extensions" / "eda" / "rulebooks"

DISPATCH_KEYS = ("run_job_template", "run_workflow_template")


def collect_refs(node, refs, source):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in DISPATCH_KEYS and isinstance(value, dict):
                name = value.get("name")
                if isinstance(name, str) and name.strip():
                    refs.setdefault(name.strip(), set()).add(source)
            else:
                collect_refs(value, refs, source)
    elif isinstance(node, list):
        for item in node:
            collect_refs(item, refs, source)


def main() -> int:
    refs: dict[str, set] = {}
    for rb in sorted(RULEBOOKS.glob("*.yml")):
        try:
            docs = list(yaml.safe_load_all(rb.read_text()))
        except yaml.YAMLError as exc:
            print(f"WARN: {rb.name} does not parse: {exc}")
            continue
        for doc in docs:
            collect_refs(doc, refs, rb.name)

    allow_file = RULEBOOKS / "known_unseeded.yml"
    allowed = set()
    if allow_file.exists():
        doc = yaml.safe_load(allow_file.read_text()) or {}
        allowed = {e["name"] for e in doc.get("known_unseeded", []) if isinstance(e, dict)}

    orphans = []
    for name in sorted(refs):
        if name in allowed:
            print(f"ALLOWED (known_unseeded.yml): '{name}'")
            continue
        # A name is "defined" if it appears anywhere in the repo outside
        # extensions/eda/ — the seeders, CaC files, bootstrap playbooks
        # and demo docs all state template names verbatim.
        hit = subprocess.run(
            ["git", "grep", "-l", "--fixed-strings", name,
             "--", ":(exclude)extensions/eda/"],
            cwd=REPO, capture_output=True, text=True,
        )
        if hit.returncode != 0 or not hit.stdout.strip():
            orphans.append(name)

    print(f"rulebook template references: {len(refs)}; orphaned: {len(orphans)}")
    for name in orphans:
        used_by = ", ".join(sorted(refs[name]))
        print(f"ORPHAN: '{name}' (referenced by {used_by}) "
              f"is defined nowhere outside extensions/eda/ — renamed or never seeded?")
    return 1 if orphans else 0


if __name__ == "__main__":
    sys.exit(main())
