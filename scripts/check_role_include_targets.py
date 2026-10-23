#!/usr/bin/env python3
"""Verify every include_tasks / import_tasks target inside a role exists.

The class of defect this catches: a role's tasks/main.yml includes task
files that were never written. Three roles shipped broken this way for
months (compliance_base, fisma_compliance, nerc_cip_compliance) because
nothing parsed include targets — syntax-check passes, YAML parses, and
the failure only appears at runtime when the include executes.

Scope: ansible/roles/*/tasks/*.yml (and handlers/). Targets that are
templated ({{ ... }}) can't be resolved statically and are skipped with
a note. Plain-string targets must exist relative to the role's tasks/
directory (Ansible's resolution rule for include_tasks inside a role).

Exit 0 = clean, 1 = at least one missing target.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
ROLES = REPO / "ansible" / "roles"

INCLUDE_KEYS = (
    "include_tasks",
    "import_tasks",
    "ansible.builtin.include_tasks",
    "ansible.builtin.import_tasks",
)


def targets_in(node, found):
    """Recursively collect include/import targets from parsed YAML."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in INCLUDE_KEYS:
                # value may be a string or {file: ...}
                if isinstance(value, dict):
                    value = value.get("file")
                if isinstance(value, str):
                    found.append(value)
            else:
                targets_in(value, found)
    elif isinstance(node, list):
        for item in node:
            targets_in(item, found)


def main() -> int:
    failures = []
    skipped_templated = 0
    for role_dir in sorted(p for p in ROLES.iterdir() if p.is_dir()):
        for sub in ("tasks", "handlers"):
            base = role_dir / sub
            if not base.is_dir():
                continue
            for yml in sorted(base.rglob("*.yml")):
                try:
                    docs = list(yaml.safe_load_all(yml.read_text()))
                except yaml.YAMLError:
                    continue  # YAML validity is another check's job
                found: list[str] = []
                for doc in docs:
                    targets_in(doc, found)
                for target in found:
                    if "{{" in target:
                        skipped_templated += 1
                        continue
                    if not (yml.parent / target).exists() and not (base / target).exists():
                        failures.append(
                            f"{yml.relative_to(REPO)}: includes '{target}' which does not exist"
                        )

    for f in failures:
        print(f"MISSING: {f}")
    print(
        f"checked roles under {ROLES.relative_to(REPO)}; "
        f"{len(failures)} missing target(s); {skipped_templated} templated target(s) skipped"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
