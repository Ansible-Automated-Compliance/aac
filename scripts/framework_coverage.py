#!/usr/bin/env python3
"""Measure what every catalog framework actually evaluates, at the pinned library.

Why this exists
---------------
Until 2026-11-18 the README stated coverage by hand ("Complete", "300+ controls,
full"), and an audit found the claims well above what shipped. Separately, a
framework can sit in the catalog -- selectable by a customer -- while its key
resolves to nothing in OPA, so an assessment returns an empty report. Neither
fault is visible to a test that only checks the frameworks someone remembered.

This script asks the policies themselves. For every entry in
ansible/vars/framework_catalog.yml and every OPA key it lists, it evaluates

    data.<path>.main.compliance_report        (empty input)

the query generic_framework_assessment.yml sends, with <path> taken from
opa_framework_path in site_config.yml.example (or the key itself), loading the
entry's policy_dir plus the container's opa_bridges/ directory. A key RESOLVES
when that report is an object with a numeric total_controls. The number it
reports is the number of controls the module evaluates -- not a claim about
how many controls the published standard contains.

Usage
-----
    scripts/framework_coverage.py                 # print the table
    scripts/framework_coverage.py --write         # rewrite the generated files
    scripts/framework_coverage.py --check         # fail if they are out of date
                                                  #   or a key has stopped resolving
Requires `opa` on PATH (or --opa) and the policies/ submodule checked out.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import pathlib
import subprocess
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
CATALOG = REPO / "ansible/vars/framework_catalog.yml"
SITE = REPO / "ansible/vars/site_config.yml.example"
OUT_MD = REPO / "docs/reference/FRAMEWORK_COVERAGE.md"
OUT_JSON = REPO / "docs/reference/framework_coverage.json"
BASELINE = REPO / "ansible/vars/framework_coverage_known_gaps.yml"
README = REPO / "README.md"
BEGIN = "<!-- BEGIN GENERATED: framework coverage (scripts/framework_coverage.py --write) -->"
END = "<!-- END GENERATED: framework coverage -->"

# The rows the README shows. Everything else is in docs/reference/FRAMEWORK_COVERAGE.md.
README_KEYS = [
    "cis_rhel9", "cis_rhel8", "cis_rhel10", "cis_ubuntu_2204", "cis_windows_2022",
    "cis_aws", "cis_azure", "cis_gcp", "cis_docker", "cis_kubernetes", "cis_m365_v7",
    "stig_rhel9", "stig_rhel8", "stig_windows_server_2022",
    "nist_800_53", "nist_800_171", "iso27001", "pci_dss", "nerc_cip",
]


def pin() -> str:
    out = subprocess.run(["git", "ls-tree", "HEAD", "policies"], cwd=REPO,
                         capture_output=True, text=True).stdout.split()
    return out[2][:8] if len(out) > 2 else "unknown"


def evaluate(opa: str, policies: pathlib.Path, entry: dict, key: str, path: str) -> dict:
    row = {"loader_key": entry["loader_key"], "key": key, "display_name": entry["display_name"],
           "container": entry["opa_container"], "policy_dir": entry["policy_dir"],
           "enabled_by_default": bool(entry.get("enabled_by_default")),
           "resolves": False, "counted": False, "total_controls": None, "standard": None, "reason": ""}
    pdir = policies / entry["policy_dir"]
    if not pdir.exists():
        row["reason"] = "policy_dir does not exist at the pin"
        return row
    cmd = [opa, "eval", "-f", "json", "--stdin-input", "-d", str(pdir),
           "--ignore", "tests", "--ignore", "*_test.rego", "--ignore", "test_*.rego"]
    bridges = REPO / "opa_bridges" / entry["opa_container"]
    if bridges.exists():
        cmd += ["-d", str(bridges)]
    cmd.append("data." + path.replace("/", ".") + ".main.compliance_report")
    try:
        proc = subprocess.run(cmd, input="{}", capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        row["reason"] = "opa eval timed out"
        return row
    if proc.returncode != 0:
        row["reason"] = "opa eval failed: " + (proc.stderr.strip().splitlines() or ["?"])[0][:120]
        return row
    result = json.loads(proc.stdout or "{}").get("result") or []
    if not result:
        row["reason"] = "compliance_report is undefined on empty input"
        return row
    report = result[0]["expressions"][0]["value"]
    if not isinstance(report, dict):
        row["reason"] = "compliance_report is not an object"
        return row
    row.update(resolves=True,
               standard=report.get("benchmark") or report.get("framework") or report.get("standard"))
    total = report.get("total_controls")
    if isinstance(total, bool) or not isinstance(total, (int, float)):
        row["reason"] = "the report has no numeric total_controls"
    else:
        row.update(counted=True, total_controls=int(total))
    if isinstance(row["standard"], dict):
        row["standard"] = row["standard"].get("name")
    return row


def measure(opa: str, policies: pathlib.Path) -> list[dict]:
    entries = yaml.safe_load(CATALOG.read_text())["framework_catalog_entries"]
    paths = (yaml.safe_load(SITE.read_text()) or {}).get("opa_framework_path") or {}
    jobs = [(e, k, paths.get(k, k)) for e in entries for k in (e.get("opa_keys") or [])]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(lambda j: evaluate(opa, policies, *j), jobs))
    return sorted(rows, key=lambda r: (r["container"], r["key"]))


def bundle_only() -> list[dict]:
    entries = yaml.safe_load(CATALOG.read_text())["framework_catalog_entries"]
    return [e for e in entries if not e.get("opa_keys")]


def render_md(rows: list[dict], commit: str) -> str:
    counted = [r for r in rows if r["counted"]]
    nocount = [r for r in rows if r["resolves"] and not r["counted"]]
    bad = [r for r in rows if not r["resolves"]]
    out = ["# Framework coverage, measured", "",
           "> **Generated** by `scripts/framework_coverage.py --write`. Do not edit by hand.", "",
           f"Policy library pin: `{commit}`. Of {len(rows)} catalog keys, **{len(counted)} return a report "
           f"with a control count**, {len(nocount)} return a report without one, and {len(bad)} resolve "
           "to nothing.", "",
           "\"Controls evaluated\" is the module's own `total_controls` on empty input: the number of "
           "controls it evaluates. It is not a statement about how many controls the published "
           "standard contains.", "",
           "| Key | Catalog entry | OPA service | Controls evaluated | Standard as the module names it |",
           "|---|---|---|---|---|"]
    for r in counted:
        out.append(f"| `{r['key']}` | {r['display_name']} | {r['container']} | {r['total_controls']} | {r['standard'] or ''} |")
    if nocount:
        out += ["", "## Keys whose report has no control count", "",
                "An assessment for these returns a report, but the report does not say how many controls "
                "it evaluated, so a percentage cannot be checked against a total. Each is on the "
                "`no_control_count` list in `ansible/vars/framework_coverage_known_gaps.yml`.", "",
                "| Key | Catalog entry | Policy directory |", "|---|---|---|"]
        for r in nocount:
            out.append(f"| `{r['key']}` | {r['display_name']} | `{r['policy_dir']}` |")
    if bad:
        out += ["", "## Keys that do not resolve", "",
                "A customer who selects one of these gets no report.", "",
                "| Key | Catalog entry | Policy directory | Why |", "|---|---|---|---|"]
        for r in bad:
            out.append(f"| `{r['key']}` | {r['display_name']} | `{r['policy_dir']}` | {r['reason']} |")
    bundles = bundle_only()
    if bundles:
        out += ["", "## Bundles with no assessable key", "",
                "These catalog entries can be loaded into OPA but list no key (`opa_keys: []`): an umbrella "
                "or legacy directory, a gate policy, or a benchmark assessed by its own playbook under "
                "another package. They are not counted above.", "",
                "| Loader key | Catalog entry | Policy directory |", "|---|---|---|"]
        for e in bundles:
            out.append(f"| `{e['loader_key']}` | {e['display_name']} | `{e['policy_dir']}` |")
    return "\n".join(out) + "\n"


def render_readme(rows: list[dict], commit: str) -> str:
    by = {r["key"]: r for r in rows}
    counted = sum(r["counted"] for r in rows)
    out = [BEGIN, "",
           "| Framework | Controls evaluated | Standard as the module names it |", "|---|---|---|"]
    for k in README_KEYS:
        r = by.get(k)
        if r and r["counted"]:
            out.append(f"| **{r['display_name']}** (`{k}`) | {r['total_controls']} | {r['standard'] or ''} |")
    out += ["", f"Measured at policy library pin `{commit}`: {counted} of {len(rows)} catalog keys return a "
            "report with a control count. Each number is the module's own `total_controls`, the controls it "
            "evaluates, not the size of the published standard. Every framework, and the keys that fall "
            "short: [docs/reference/FRAMEWORK_COVERAGE.md](docs/reference/FRAMEWORK_COVERAGE.md).", "", END]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--opa", default="opa")
    ap.add_argument("--policies", default=str(REPO / "policies"),
                    help="checkout of the policy library at the pinned commit (default: the submodule)")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    policies = pathlib.Path(args.policies)
    if not any(policies.iterdir()) if policies.exists() else True:
        print(f"FAIL: {policies} is empty; run: git submodule update --init policies")
        return 1
    rows = measure(args.opa, policies)
    commit = pin()
    md = render_md(rows, commit)
    block = render_readme(rows, commit)
    data = json.dumps({"pin": commit, "rows": rows}, indent=2, sort_keys=True) + "\n"
    unresolved = sorted(r["key"] for r in rows if not r["resolves"])
    nocount = sorted(r["key"] for r in rows if r["resolves"] and not r["counted"])
    gaps = (yaml.safe_load(BASELINE.read_text()) or {}) if BASELINE.exists() else {}
    known_unresolved = sorted(gaps.get("unresolved") or [])
    known_nocount = sorted(gaps.get("no_control_count") or [])

    if args.write:
        OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        OUT_MD.write_text(md)
        OUT_JSON.write_text(data)
        text = README.read_text()
        if BEGIN in text and END in text:
            text = text[:text.index(BEGIN)] + block + text[text.index(END) + len(END):]
            README.write_text(text)
        print(f"wrote {OUT_MD.relative_to(REPO)}, {OUT_JSON.relative_to(REPO)}; of {len(rows)} keys "
              f"{len(unresolved)} unresolved, {len(nocount)} without a control count")
        return 0

    if args.check:
        problems = []
        for label, now, known in (("resolve to nothing", unresolved, known_unresolved),
                                  ("return a report without a control count", nocount, known_nocount)):
            new = sorted(set(now) - set(known))
            fixed = sorted(set(known) - set(now))
            if new:
                problems.append(f"keys that {label} and are not on the known-gaps list: " + ", ".join(new))
            if fixed:
                problems.append(f"keys on the known-gaps list that no longer {label} (remove them): " + ", ".join(fixed))
        if not OUT_MD.exists() or OUT_MD.read_text() != md:
            problems.append(f"{OUT_MD.relative_to(REPO)} is out of date")
        text = README.read_text()
        if BEGIN not in text or block not in text:
            problems.append("the generated coverage block in README.md is out of date")
        for p in problems:
            print("FAIL:", p)
        if problems:
            print("\nRun: scripts/framework_coverage.py --write")
            return 1
        print(f"OK: {len(rows)} keys, {len(unresolved)} unresolved, {len(nocount)} without a control count "
              "(all on the known-gaps list); generated files are current")
        return 0

    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
