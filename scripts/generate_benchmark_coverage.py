#!/usr/bin/env python3
"""Generate a benchmark coverage file from the policy library.

The comparison playbook (cis_benchmark_comparison.yml) needs to know, per
benchmark, which controls AAC can evaluate, which require operator
attestation, and which have no path at all — otherwise every control a
manual assessment covers and AAC does not looks like an AAC miss instead of
a declared scope boundary. That coverage is *derivable* from the policy
library: each section module declares its evaluated `controls` list, the
attestation module declares REQUIRES_ATTESTATION / UNRESOLVED /
NOT_IMPLEMENTED, and the benchmark index JSON names all recommendations.

This script derives it mechanically and writes a committed YAML artifact,
so the playbook never parses Rego at runtime and the coverage a customer
sees is the coverage that was reviewed in a PR. Re-run it whenever the
policy library advances; CI or a reviewer can diff the artifact.

Adding a benchmark = adding an entry to BENCHMARKS below, provided the
policy package follows the same conventions (per-section `"controls": [...]`
literals, an attestation module with the three named sets, and a
`data/<key>_index.json` benchmark index).

Usage:
    python3 scripts/generate_benchmark_coverage.py cis_m365_v7 \
        [--policies-root policies] [--out ansible/vars/comparison] [--check]

--check verifies the committed artifact matches what the library derives
(exit 1 on drift) without writing anything.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

# Benchmark key -> where its policy package and index live, relative to the
# policies submodule root.
BENCHMARKS = {
    "cis_m365_v7": {
        "package_dir": "benchmarks/cis/saas/m365_v7",
        "index_json": "benchmarks/cis/saas/m365_v7/data/cis_m365_v7_index.json",
        "attestation_module": "attestation_validation.rego",
    },
}

_CONTROLS_BLOCK = re.compile(r'"controls"\s*:\s*\[(.*?)\]', re.DOTALL)
_QUOTED_ID = re.compile(r'"(\d+(?:\.\d+)*)"')


def _controls_from_module(path: pathlib.Path) -> list[str]:
    """Control ids from a section module's `"controls": [...]` literal."""
    text = path.read_text()
    ids: list[str] = []
    for block in _CONTROLS_BLOCK.finditer(text):
        ids.extend(_QUOTED_ID.findall(block.group(1)))
    return ids


def _attestation_sets(path: pathlib.Path) -> dict[str, list[str]]:
    """Control ids from REQUIRES_ATTESTATION / UNRESOLVED / NOT_IMPLEMENTED."""
    text = path.read_text()
    out: dict[str, list[str]] = {}
    for name in ("REQUIRES_ATTESTATION", "UNRESOLVED", "NOT_IMPLEMENTED"):
        m = re.search(name + r"\s*:=\s*\{(.*?)\n\}", text, re.DOTALL)
        body = m.group(1) if m else ""
        # Keys are the quoted ids before a colon; an empty set has none.
        out[name.lower()] = sorted(
            set(re.findall(r'"(\d+(?:\.\d+)*)"\s*:', body)), key=_sort_key
        )
    return out


def _sort_key(cid: str) -> tuple[int, ...]:
    return tuple(int(p) for p in cid.split("."))


def derive(benchmark: str, policies_root: pathlib.Path) -> dict:
    cfg = BENCHMARKS[benchmark]
    pkg = policies_root / cfg["package_dir"]
    index = json.loads((policies_root / cfg["index_json"]).read_text())

    evaluated: set[str] = set()
    for rego in sorted(pkg.glob("*.rego")):
        if rego.name == cfg["attestation_module"]:
            continue
        evaluated.update(_controls_from_module(rego))

    att = _attestation_sets(pkg / cfg["attestation_module"])

    catalog = [
        {
            "control_id": r["control_id"],
            "section": str(r["section"]),
            "section_name": r["section_name"],
            "cis_assessment": r["assessment"],
        }
        for r in sorted(index["recommendations"], key=lambda r: _sort_key(r["control_id"]))
    ]
    all_ids = {c["control_id"] for c in catalog}

    claimed = evaluated | set(att["requires_attestation"]) | set(att["unresolved"]) | set(att["not_implemented"])
    unclaimed = sorted(all_ids - claimed, key=_sort_key)
    outside = sorted(claimed - all_ids, key=_sort_key)
    if outside:
        sys.exit(f"ERROR: policy claims ids not in the benchmark index: {outside}")

    return {
        "benchmark": index["benchmark"],
        "benchmark_version": index["version"],
        "framework": benchmark,
        "benchmark_total_controls": index["total_recommendations"],
        "generated_by": "scripts/generate_benchmark_coverage.py",
        "policy_package": cfg["package_dir"],
        "evaluated": sorted(evaluated, key=_sort_key),
        "requires_attestation": att["requires_attestation"],
        "unresolved": att["unresolved"],
        "not_implemented": att["not_implemented"],
        # Anything the policy package does not claim at all. Non-empty means
        # the package's own coverage accounting would not balance — surface
        # it rather than hiding it.
        "unclaimed": unclaimed,
        "catalog": catalog,
    }


def to_yaml(cov: dict) -> str:
    """Emit stable, readable YAML without a yaml dependency."""
    lines = ["---", "# GENERATED by scripts/generate_benchmark_coverage.py — do not hand-edit.",
             "# Re-run the generator when the policy library advances."]
    for key in ("benchmark", "benchmark_version", "framework", "benchmark_total_controls",
                "generated_by", "policy_package"):
        val = cov[key]
        lines.append(f"{key}: {json.dumps(val)}")
    for key in ("evaluated", "requires_attestation", "unresolved", "not_implemented", "unclaimed"):
        ids = cov[key]
        lines.append(f"{key}:" + (" []" if not ids else ""))
        lines.extend(f'  - "{c}"' for c in ids)
    lines.append("catalog:")
    for c in cov["catalog"]:
        lines.append(f'  - control_id: "{c["control_id"]}"')
        lines.append(f'    section: "{c["section"]}"')
        lines.append(f"    section_name: {json.dumps(c['section_name'])}")
        lines.append(f'    cis_assessment: {json.dumps(c["cis_assessment"])}')
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("benchmark", choices=sorted(BENCHMARKS))
    ap.add_argument("--policies-root", default="policies", type=pathlib.Path)
    ap.add_argument("--out", default="ansible/vars/comparison", type=pathlib.Path)
    ap.add_argument("--check", action="store_true",
                    help="verify the committed artifact matches the library")
    args = ap.parse_args()

    cov = derive(args.benchmark, args.policies_root)
    text = to_yaml(cov)
    target = args.out / f"{args.benchmark}_coverage.yml"

    if args.check:
        if not target.exists() or target.read_text() != text:
            sys.exit(f"DRIFT: {target} does not match the policy library — "
                     f"re-run scripts/generate_benchmark_coverage.py {args.benchmark}")
        print(f"OK: {target} matches the policy library")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    n = cov
    print(f"wrote {target}: {len(n['evaluated'])} evaluated, "
          f"{len(n['requires_attestation'])} attestation, "
          f"{len(n['unresolved'])} unresolved, "
          f"{len(n['not_implemented'])} not implemented, "
          f"{len(n['unclaimed'])} unclaimed, of {n['benchmark_total_controls']}")


if __name__ == "__main__":
    main()
