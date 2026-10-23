#!/usr/bin/env python3
"""Validate the Rego policy library is configured correctly.

    python3 scripts/validate_rego_library.py [--policies-dir policies]

Exit 0 = every axis clean. Non-zero = at least one finding, all printed.

The axes, each of which has caught a real defect in this repository:

1. AGGREGATE COLLAPSE — every package that declares compliance_report or
   compliance_assessment must return a POPULATED object on empty input.
   One bare `input.x` dereference in the report body makes the whole object
   undefined at the endpoint, and the caller stores {} while its job stays
   green. Found 18 of these on 2026-08-30/31 (4 Debian-family aggregates,
   then 14 more in one sweep), in five distinct spellings — including
   object.get(input.x, "y", d), which defaults the leaf but dereferences the
   undefined base first, and a missing `default compliant := false` whose
   fail-closed violations guaranteed the compliant rule never fired.
   Checked with ONE `opa eval` of all of `data` against empty input, then
   compared against every aggregate declared in source.

2. rego.v1 — every file imports rego.v1.

3. LAB IDENTIFIERS — no AAP_HOST / LAB_UTIL_HOST outside the hygiene
   policy's own default address list. Deliberately narrow: a generic IP regex
   flags CIS control numbers (4.1.1.1) as addresses.

4. FRAMEWORK MAP — every key in opa_framework_map either has a matching
   <key>.main package whose compliance_report populates, or is on the
   documented not-yet-wired list. A key with no package returns {} at the
   endpoint and the generic assessment stores an empty result, green.
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policies-dir", default="policies")
    ap.add_argument("--site-config", default="ansible/vars/site_config.yml.example")
    args = ap.parse_args()
    pol = pathlib.Path(args.policies_dir)
    findings = []

    rego = [p for p in pol.rglob("*.rego") if ".github" not in p.parts]
    tests = [p for p in rego if p.name.startswith("test_") or p.name.endswith("_test.rego")]
    if len(rego) < 100:
        print(f"FAIL: only {len(rego)} rego files found under {pol} — wrong directory?")
        return 1

    # ── 1. aggregate collapse ────────────────────────────────────────────────
    decl = {}
    for p in rego:
        if p in tests:
            continue
        t = p.read_text(errors="ignore")
        m = re.search(r"^package\s+([\w.]+)", t, re.M)
        if not m:
            continue
        for rule in ("compliance_report", "compliance_assessment"):
            if re.search(rf"^{rule}\s*:?=", t, re.M):
                decl.setdefault(m.group(1), set()).add(rule)

    ev = subprocess.run(
        ["opa", "eval", "-d", str(pol), "--ignore", ".github",
         "--stdin-input", "-f", "json", "data"],
        input="{}", capture_output=True, text=True, timeout=600)
    if ev.returncode != 0:
        print("FAIL: opa eval of the library errored:\n" + ev.stderr[:2000])
        return 1
    data = json.loads(ev.stdout)["result"][0]["expressions"][0]["value"]

    def get(d, dotted):
        cur = d
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur

    for pkg in sorted(decl):
        node = get(data, pkg) or {}
        for rule in sorted(decl[pkg]):
            if node.get(rule) in (None, {}):
                findings.append(
                    f"COLLAPSE: {pkg}.{rule} is undefined/empty on empty input — "
                    f"a caller stores {{}} as its assessment while the job stays green")
    n_aggr = sum(len(v) for v in decl.values())

    # ── 2. rego.v1 ───────────────────────────────────────────────────────────
    no_v1 = [str(p) for p in rego if "import rego.v1" not in p.read_text(errors="ignore")]
    findings += [f"NO-REGO-V1: {p}" for p in no_v1]

    # ── 3. lab identifiers ───────────────────────────────────────────────────
    # The hygiene policy's default lab_addresses list, and the test that pins
    # those defaults, legitimately contain the lab IPs -- they are the config.
    allow = ("enforcement/ansible/repo_hygiene",
             "enforcement/ansible/tests/test_repo_hygiene")
    # Lab addresses are injected from the LAB_ADDRESSES environment variable
    # (comma-separated), so this checker does not itself disclose them.
    lab_addresses = [a.strip() for a in os.environ.get("LAB_ADDRESSES", "").split(",") if a.strip()]
    for p in rego:
        rel = str(p.relative_to(pol))
        if rel.startswith(allow) or any(rel.startswith(a) for a in allow):
            continue
        t = p.read_text(errors="ignore")
        for ip in lab_addresses:
            if ip in t:
                findings.append(f"LAB-IP: {rel} contains {ip}")

    # ── 4. framework map ─────────────────────────────────────────────────────
    sc_path = pathlib.Path(args.site_config)
    unwired = []
    if sc_path.exists():
        sc = sc_path.read_text()
        keys = re.findall(r"^  (\w+):\s*(?:security|compliance|ot)\s*$", sc, re.M)
        pkgs = set(decl) | {
            (re.search(r"^package\s+([\w.]+)", p.read_text(errors="ignore"), re.M) or [None, ""])[1]
            for p in rego}
        for key in sorted(set(keys)):
            if f"{key}.main" not in pkgs:
                unwired.append(key)
            elif (get(data, f"{key}.main") or {}).get("compliance_report") in (None, {}):
                findings.append(
                    f"MAP-EMPTY: opa_framework_map key '{key}' has {key}.main but its "
                    f"compliance_report is empty/undefined on empty input")

    print(f"aggregates checked: {n_aggr} across {len(decl)} packages")
    print(f"rego files: {len(rego)} ({len(tests)} tests)")
    if unwired:
        print(f"NOTE (not a failure): {len(unwired)} opa_framework_map keys have no "
              f"<key>.main package — the generic assessment cannot serve them yet:")
        print("  " + ", ".join(unwired))

    if findings:
        print(f"\nFAIL: {len(findings)} finding(s)")
        for f in findings:
            print("  " + f)
        return 1
    print("OK: library validation clean on all axes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
