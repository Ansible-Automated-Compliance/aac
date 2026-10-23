#!/usr/bin/env python3
"""Report literal connection/endpoint configuration in playbook vars, and any
`.yaml` under the playbook trees.

Companion to docs/operations/PLAYBOOK_CONFIG_STANDARDIZATION_PLAN.md — the
numbers in that document come from this scan. Intended for the
`Validate Ansible content` workflow, first in warn mode (exit code ignored),
then blocking once phases P1–P2 of the plan have landed.

Rules:
  * In ansible/playbooks/**/*.yml (recursive), a play-level `vars:` entry whose key is a
    connection/endpoint key and whose value is a literal (no Jinja) is a
    finding. Keys: pg_host pg_port pg_db pg_user pg_password, their db_* and
    postgres_* aliases, opa_*_url, grafana_url/grafana_host/grafana_port,
    mcp_url, aac_host, portal_url.
  * Role defaults (ansible/roles/*/defaults/main.yml) are scanned with the
    same key list.
  * Any *.yaml under ansible/{playbooks,roles,vars,inventory} or
    extensions/eda/rulebooks is a finding — the convention is .yml.

Allow-list (per file AND key): load_opa_routing.yml's routing_namespace /
routing_configmap name the Kubernetes objects it manages; opa-policy-deployment.yml's
opa_binary_url is a download URL template. Add a (file, key) entry with the
reason if a new legitimate literal appears.

Usage: python3 scripts/check_literal_config.py [--warn]
  exit 0 = clean; exit 1 = findings (unless --warn)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

KEYS = re.compile(
    r"^\s{0,8}(pg_(host|port|db|user|password)"
    r"|db_(host|port|name|user|password)"
    r"|postgres_(host|port|db|user|password)"
    r"|opa_[a-z_]*url|opa_(host|port)"
    r"|grafana_(url|host|port)|mcp_url|aac_host|portal_url):\s*(?P<val>\S.*)$"
)
ALLOW = {
    # (file, key) -> reason — scoped to the one legitimate assignment, so an
    # unrelated literal added to the same file is still reported.
    ("ansible/playbooks/load_opa_routing.yml", "routing_namespace"): "Kubernetes namespace this playbook manages",
    ("ansible/playbooks/load_opa_routing.yml", "routing_configmap"): "ConfigMap this playbook manages",
    ("ansible/playbooks/opa-policy-deployment.yml", "opa_binary_url"): "OPA download URL template, not an endpoint",
}
PLAYBOOK_TREES = ["ansible/playbooks", "ansible/roles", "extensions/eda/rulebooks", "ansible/vars", "ansible/inventory"]


def literal(val: str) -> bool:
    v = val.split("#", 1)[0].strip()
    return bool(v) and "{{" not in v and v not in {"~", "null", '""', "''"}


def scan() -> list[str]:
    findings: list[str] = []
    files = sorted(ROOT.glob("ansible/playbooks/**/*.yml")) + sorted(ROOT.glob("ansible/roles/*/defaults/main.yml"))
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            m = KEYS.match(line)
            if not m or not literal(m.group("val")):
                continue
            key = line.split(":", 1)[0].strip()
            if (rel, key) in ALLOW:
                continue
            findings.append(f"{rel}:{i}: {line.strip()}")
    for tree in PLAYBOOK_TREES:
        for path in sorted((ROOT / tree).rglob("*.yaml")):
            findings.append(f"{path.relative_to(ROOT).as_posix()}: .yaml under a playbook tree (convention is .yml)")
    return findings


def main() -> int:
    warn = "--warn" in sys.argv[1:]
    findings = scan()
    if not findings:
        print("OK: no literal connection config in playbook vars, no .yaml under playbook trees")
        return 0
    by_file: dict[str, int] = {}
    for f in findings:
        by_file[f.split(":", 1)[0]] = by_file.get(f.split(":", 1)[0], 0) + 1
    print(f"{'WARN' if warn else 'FAIL'}: {len(findings)} finding(s) in {len(by_file)} file(s)")
    for f in findings:
        print("  " + f)
    return 0 if warn else 1


if __name__ == "__main__":
    sys.exit(main())
