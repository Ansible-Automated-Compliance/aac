#!/usr/bin/env python3
"""Fail if a runtime file hardcodes an in-cluster service endpoint.

Endpoints (OPA URLs, the compliance DB host, Grafana) must come from
`ansible/vars/site_config.yml` (per environment) — never a literal baked into a
playbook or role. A hardcoded in-cluster default is portable *looking* but wrong
at a customer whose topology differs: it silently targets an assumed address
instead of the configured one, which surfaced in the field as a connection reset
hours into a run rather than a clear configuration error.

This guard scans the `ansible/` runnable surface for `*.svc.cluster.local`
literals and flags any that are not in the places the value legitimately lives:
the config files themselves and comments/documentation.

Allowed (the value belongs here):
  - ansible/vars/site_config.yml and *.example
  - ansible/vars/profiles/*.yml
  - comment lines and Markdown

Everything else is a finding. Prints how many files it examined so a
vacuous pass (scanning nothing) fails loudly, matching the repo's CI philosophy.

(The aac.m365 collection is handled in its own change; extend SCAN_ROOTS to
collections/ in a follow-up once that lands.)
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SCAN_ROOTS = ["ansible"]
NEEDLE = re.compile(r"[A-Za-z0-9_.-]+\.svc\.cluster\.local")

# Paths where an endpoint literal is the correct, intended content.
ALLOWED_PREFIXES = (
    "ansible/vars/site_config.yml",
    "ansible/vars/profiles/",
)


def _allowed(rel: str) -> bool:
    if rel.endswith(".example") or rel.endswith(".md"):
        return True
    return any(rel.startswith(p) for p in ALLOWED_PREFIXES)


def _strip_comment(line: str, suffix: str) -> str:
    """Drop a trailing comment so a documented example doesn't trip the scan.
    `.py` and `.yml`/`.sh` all use `#`."""
    if suffix in (".py", ".yml", ".yaml", ".sh"):
        return line.split("#", 1)[0]
    return line


def main() -> int:
    findings: list[str] = []
    examined = 0
    for root in SCAN_ROOTS:
        for path in (REPO / root).rglob("*"):
            if not path.is_file() or path.suffix not in (".yml", ".yaml", ".py", ".sh"):
                continue
            rel = path.relative_to(REPO).as_posix()
            if _allowed(rel):
                continue
            examined += 1
            for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if NEEDLE.search(_strip_comment(line, path.suffix)):
                    findings.append(f"{rel}:{n}: {line.strip()}")

    print(f"checked {examined} runtime files under {', '.join(SCAN_ROOTS)}/ for hardcoded endpoints")
    if examined < 50:
        print(f"FAIL: only {examined} files examined — the scan matched too little to trust")
        return 1
    if findings:
        print(f"FAIL: {len(findings)} hardcoded in-cluster endpoint(s) found — source these from site_config:")
        for f in findings:
            print("  " + f)
        return 1
    print("OK: no hardcoded in-cluster endpoints in the ansible/ runtime surface")
    return 0


if __name__ == "__main__":
    sys.exit(main())
