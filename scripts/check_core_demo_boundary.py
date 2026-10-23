#!/usr/bin/env python3
"""Enforce the core→demos runtime boundary (restructure Phase 5).

Rule: no file under the core trees (ansible/, extensions/, integrations/,
install/, scripts/) may READ anything under demos/ at its own runtime.
Phase 1 eliminated the five playbooks that did; this gate keeps the
boundary machine-checked — it is also the proof that the Phase 6 repo
split is safe.

What counts as a runtime read (checked in YAML values):
  - import_playbook / include_tasks / include_vars / vars_files
  - src: / file: (copy, template, unarchive, ...)
  - lookup('file'/'template'/'ini', ...) expressions
  - any playbook_dir-relative traversal that lands in demos/

Phase 6 is complete: demo content lives in the aac-demos repository and
NOTHING in core may reference demos/ — including `playbook:` values in
job-template definitions (demo templates are defined in aac-demos CaC).

Exit 0 = boundary holds; 1 = a core file reads demos/ at runtime.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
CORE_TREES = ("ansible", "extensions", "integrations", "install", "scripts")

READ_KEYS = {
    "import_playbook", "ansible.builtin.import_playbook",
    "include_tasks", "ansible.builtin.include_tasks",
    "import_tasks", "ansible.builtin.import_tasks",
    "include_vars", "ansible.builtin.include_vars",
    "src", "file", "path", "vars_files",
    "playbook",  # post-split: demo JT defs live in aac-demos, not core
}
LOOKUP_RE = re.compile(r"lookup\(\s*'(?:file|template|ini)'[^)]*demos/")


def value_hits_demos(value) -> bool:
    if isinstance(value, str):
        return "demos/" in value or LOOKUP_RE.search(value) is not None
    if isinstance(value, list):
        return any(value_hits_demos(v) for v in value)
    return False


def scan(node, findings, source):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in READ_KEYS and value_hits_demos(value):
                findings.append(f"{source}: runtime read of demos/ via '{key}': {value!r}"[:200])
            # lookups can hide in any string value
            elif isinstance(value, str) and LOOKUP_RE.search(value):
                findings.append(f"{source}: lookup() into demos/ in value of '{key}'"[:200])
            else:
                scan(value, findings, source)
    elif isinstance(node, list):
        for item in node:
            scan(item, findings, source)


def main() -> int:
    findings: list[str] = []
    checked = 0
    for tree in CORE_TREES:
        base = REPO / tree
        if not base.is_dir():
            continue
        for yml in sorted(base.rglob("*.yml")) + sorted(base.rglob("*.yaml")):
            rel = yml.relative_to(REPO)
            try:
                docs = list(yaml.safe_load_all(yml.read_text()))
            except yaml.YAMLError:
                continue  # parse validity is another gate's job
            checked += 1
            for doc in docs:
                scan(doc, findings, str(rel))

    print(f"scanned {checked} core YAML files for demos/ runtime reads")
    for f in findings:
        print(f"BOUNDARY VIOLATION: {f}")
    if not findings:
        print("OK: core never reads demos/ at runtime "
              "(job-template path strings are tolerated until the Phase 6 split)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
