#!/usr/bin/env python3
"""
discovered_tech.py — turn DISCOVERED technology signals (host_facts_latest,
inventory_catalog) into the loader_keys that should be enabled, so framework
enablement follows what an environment actually runs (gap: the "Piece #23"
bridge). Reuses the declared tech→framework map + derive() so there is one
authoritative mapping.

Input: a JSON array on stdin, each element a discovered signal:
  {"os_family":"RedHat","os_distribution":"RedHat","os_version":"9.3",
   "cloud_provider":"aws"}                       # from host_facts_latest
  {"vendor":"VMware","product":"vcenter","version":"8.0"}   # inventory_catalog

Output (stdout): the unioned loader_keys, one per line (feed to the loader's
frameworks_to_load, or upsert into customer_frameworks). A per-key trace is
written to stderr.

Env: none. The tech→framework map is read from customer_profiles/_tech_framework_map.yml
via derive_customer_frameworks.load_map().
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_customer_frameworks import derive, load_map  # noqa: E402


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def os_to_tech(os_family, os_distribution, os_version) -> str | None:
    """Map a discovered OS to a tech key in _tech_framework_map.yml (or None)."""
    fam, dist, ver = _norm(os_family), _norm(os_distribution), _norm(os_version)
    major = ""
    m = re.match(r"(\d+)", str(os_version or ""))
    if m:
        major = m.group(1)
    blob = f"{fam} {dist}"

    if "ubuntu" in blob:
        return {"20": "ubuntu_2004", "22": "ubuntu_2204", "24": "ubuntu_2404"}.get(major)
    if "debian" in blob:
        return "debian_11" if major in ("11", "") else None
    if "rocky" in blob:
        return {"8": "rocky_8", "9": "rocky_9"}.get(major)
    if "amazon" in blob or "amzn" in blob:
        return "amazon_linux_2023" if major == "2023" else None
    # RHEL and RHEL-compatibles that aren't Rocky (CentOS, AlmaLinux, RedHat)
    if any(x in blob for x in ("rhel", "red hat", "redhat", "centos", "almalinux")):
        return {"8": "rhel_8", "9": "rhel_9", "10": "rhel_10"}.get(major)
    if "windows" in blob:
        if "2022" in f"{dist} {ver}":
            return "windows_2022"
        if "2019" in f"{dist} {ver}":
            return "windows_2019"
        return None
    return None


def cloud_to_tech(cloud_provider) -> str | None:
    c = _norm(cloud_provider)
    if not c:
        return None
    if "aws" in c or "amazon" in c:
        return "aws"
    if "azure" in c or "microsoft" in c:
        return "azure"
    if "gcp" in c or "google" in c:
        return "gcp"
    return None


def product_to_tech(vendor, product) -> str | None:
    blob = f"{_norm(vendor)} {_norm(product)}"
    if "openshift" in blob:
        return "openshift"
    if "kubernetes" in blob or "k8s" in blob:
        return "kubernetes"
    if "vmware" in blob or "vcenter" in blob or "esxi" in blob:
        return "vmware"
    if "docker" in blob:
        return "docker"
    return None


def signals_to_tech(signals: list) -> set:
    """Union of tech keys implied by a list of discovered signals."""
    tech: set = set()
    for s in signals or []:
        if not isinstance(s, dict):
            continue
        t = os_to_tech(s.get("os_family"), s.get("os_distribution"), s.get("os_version"))
        if t:
            tech.add(t)
        t = cloud_to_tech(s.get("cloud_provider"))
        if t:
            tech.add(t)
        t = product_to_tech(s.get("vendor"), s.get("product"))
        if t:
            tech.add(t)
    return tech


def discovered_loader_keys(signals: list, mapping: dict | None = None) -> tuple[set, dict]:
    """Discovered signals → tech keys → loader_keys (via the shared derive())."""
    mapping = mapping or load_map()
    tech = signals_to_tech(signals)
    profile = {"tech_stack": sorted(tech), "compliance_goals": [], "overrides": {}}
    keys, trace = derive(profile, mapping)
    return keys, trace


def main() -> int:
    # Prefer a file (SIGNALS_FILE) over stdin — passing JSON through Ansible's
    # stdin templating coerces it to a Python dict-repr and breaks json.loads.
    import os
    sig_file = os.environ.get("SIGNALS_FILE", "")
    if sig_file:
        with open(sig_file) as fh:
            raw = fh.read().strip()
    else:
        raw = sys.stdin.read().strip()
    signals = json.loads(raw) if raw else []
    if isinstance(signals, dict):
        signals = [signals]
    keys, trace = discovered_loader_keys(signals)
    for k in sorted(keys):
        print(k)
    print(json.dumps(trace, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
