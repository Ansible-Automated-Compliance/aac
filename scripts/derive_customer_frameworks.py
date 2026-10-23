#!/usr/bin/env python3
"""Derive the framework keys to load for a customer profile.

Reads a customer profile YAML, walks the tech / compliance mappings
in customer_profiles/_tech_framework_map.yml, applies overrides, and
emits the unioned framework key set.

Usage:
    scripts/derive_customer_frameworks.py customer_profiles/examples/acme_bank.yml
    scripts/derive_customer_frameworks.py --format=ansible profile.yml

Output formats:
    plain     — newline-separated keys (default). Suitable for piping.
    ansible   — comma-separated single line. Drops into
                `load_opa_policies.yml`'s `frameworks_to_load` extra_var.
    yaml      — full breakdown showing what each tech / compliance
                entry contributed. Useful for debugging an unexpected
                bundle size.

Exit codes:
    0     success
    1     profile or map file missing or malformed (parse error, empty,
          or top level isn't a mapping)
    2     profile references a tech / compliance / framework key that
          isn't known. That covers two cases: (a) the profile names a
          tech or compliance entry the mapping doesn't have, and (b)
          derivation produced a framework key the OPA loader doesn't
          understand (typo in the mapping, stale override, etc.).
          Fail loud — better than silently dropping coverage.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("error: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = REPO_ROOT / "customer_profiles" / "_tech_framework_map.yml"
LOADER_PATH = REPO_ROOT / "ansible" / "playbooks" / "load_opa_policies.yml"


def _load_yaml_strict(path: Path, label: str) -> Any:
    """Load YAML with explicit error handling. Exit 1 on missing,
    malformed, empty, or non-mapping payloads — what the docstring
    promises."""
    if not path.exists():
        print(f"error: {label} not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        with path.open() as fp:
            data = yaml.safe_load(fp)
    except yaml.YAMLError as exc:
        print(f"error: {label} is malformed YAML ({path}): {exc}", file=sys.stderr)
        sys.exit(1)
    if data is None:
        print(f"error: {label} is empty: {path}", file=sys.stderr)
        sys.exit(1)
    return data


def load_map() -> dict:
    data = _load_yaml_strict(MAP_PATH, "framework map")
    if not isinstance(data, dict):
        print(f"error: framework map must be a YAML mapping ({MAP_PATH})", file=sys.stderr)
        sys.exit(1)
    return data


def load_profile(path: Path) -> dict:
    data = _load_yaml_strict(path, "profile")
    if not isinstance(data, dict):
        print(f"error: profile must be a YAML mapping ({path})", file=sys.stderr)
        sys.exit(1)
    return data


def load_loader_known_keys() -> set[str]:
    """Walk load_opa_policies.yml's opa_containers[*].frameworks[*].key
    and return the set of keys the loader can actually load. Used to
    validate derivation output — silent unknown keys would defeat the
    "fail loud" intent."""
    data = _load_yaml_strict(LOADER_PATH, "loader playbook")
    # Top-level is a list of plays; opa_containers lives under one
    # play's `vars`.
    plays = data if isinstance(data, list) else [data]
    keys: set[str] = set()
    for play in plays:
        if not isinstance(play, dict):
            continue
        containers = (play.get("vars") or {}).get("opa_containers") or []
        for c in containers:
            for fw in (c or {}).get("frameworks", []) or []:
                k = fw.get("key") if isinstance(fw, dict) else None
                if k:
                    keys.add(k)
    if not keys:
        print(
            f"error: could not extract any framework keys from {LOADER_PATH} "
            f"— file shape changed?",
            file=sys.stderr,
        )
        sys.exit(1)
    return keys


def derive(profile: dict, mapping: dict) -> tuple[set[str], dict]:
    """Return (final_framework_keys, derivation_trace).

    The trace records what each input contributed so the operator
    can see why a key landed (or didn't) in the bundle.
    """
    tech_to = mapping.get("tech_to_frameworks", {}) or {}
    compl_to = mapping.get("compliance_to_frameworks", {}) or {}
    always_on = set(mapping.get("always_on", []) or [])

    trace: dict[str, list[str]] = {}
    derived: set[str] = set(always_on)
    for k in always_on:
        trace.setdefault(k, []).append("always_on")

    # Tech contributions
    for tech in profile.get("tech_stack", []) or []:
        if tech not in tech_to:
            print(
                f"error: tech '{tech}' is not in tech_to_frameworks; "
                f"add it to {MAP_PATH.name} or remove from the profile",
                file=sys.stderr,
            )
            sys.exit(2)
        for fw in tech_to[tech]:
            derived.add(fw)
            trace.setdefault(fw, []).append(f"tech:{tech}")

    # Compliance contributions
    for goal in profile.get("compliance_goals", []) or []:
        if goal not in compl_to:
            print(
                f"error: compliance goal '{goal}' is not in "
                f"compliance_to_frameworks; add it to {MAP_PATH.name} "
                f"or remove from the profile",
                file=sys.stderr,
            )
            sys.exit(2)
        for fw in compl_to[goal]:
            derived.add(fw)
            trace.setdefault(fw, []).append(f"compliance:{goal}")

    # Overrides
    overrides = profile.get("overrides", {}) or {}
    for fw in overrides.get("add", []) or []:
        derived.add(fw)
        trace.setdefault(fw, []).append("override:add")
    for fw in overrides.get("remove", []) or []:
        derived.discard(fw)
        # Mark the trace too so the operator sees why a key dropped.
        trace.setdefault(fw, []).append("override:remove")

    return derived, trace


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("profile", help="path to customer profile YAML")
    p.add_argument(
        "--format",
        choices=("plain", "ansible", "yaml"),
        default="plain",
        help="output format (default: plain)",
    )
    args = p.parse_args()

    mapping = load_map()
    profile = load_profile(Path(args.profile))
    derived, trace = derive(profile, mapping)

    # The "remove" override marks a key in the trace even though it's
    # NOT in the final set. Strip removed keys from the output but
    # keep them in the trace.
    final = sorted(derived)

    # Validate that every derived key is something the OPA loader
    # actually knows. Without this, a typo in _tech_framework_map.yml
    # or an overrides.add value silently produces a key the Ansible
    # filter in load_opa_policies.yml will drop — exactly the silent
    # coverage-loss case the script is supposed to prevent.
    known_keys = load_loader_known_keys()
    unknown = [k for k in final if k not in known_keys]
    if unknown:
        print(
            "error: derivation produced framework keys the OPA loader "
            f"doesn't recognize: {', '.join(unknown)}. "
            f"Fix the mapping or override; see {LOADER_PATH.name} "
            "for the authoritative key list.",
            file=sys.stderr,
        )
        sys.exit(2)

    if args.format == "plain":
        print("\n".join(final))
    elif args.format == "ansible":
        print(",".join(final))
    else:  # yaml
        payload = {
            "profile": profile.get("name", str(args.profile)),
            "framework_keys": final,
            "derivation": {
                fw: sources for fw, sources in sorted(trace.items())
            },
            "count": len(final),
            # library_size = how many framework keys the OPA loader can
            # load total — the right denominator for "you're loading
            # N of M frameworks". Counting mapping entries instead
            # double-counts (one fw key is reachable via many techs)
            # and underreports keys reachable only via always_on /
            # overrides.
            "library_size": len(known_keys),
        }
        yaml.safe_dump(payload, sys.stdout, sort_keys=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
