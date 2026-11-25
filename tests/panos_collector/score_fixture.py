#!/usr/bin/env python3
"""Score PAN-OS configurations through the mapper and the CIS Palo Alto policy itself.

The unit tests in collections/ansible_collections/aac/panos/tests/unit check
the mapper's output shape. This harness checks the thing that matters: that the
policy, reading that output, reaches the right verdict. It needs an `opa`
binary and the policy directory, so it is run by hand (and its result quoted in
the pull request), not by pytest.

Asserts:
  1. the hardened fixture, with licenses, site classification and attestations,
     passes every recommendation at Level 2 (79 of 79) and Level 1 (69 of 69);
  2. the same fixture without the license read reports evidence missing for
     6.8 and 6.22-6.25, and nothing else changes;
  3. without attestations exactly the 13 judgement recommendations fail;
  4. the simulator's deliberately weak configuration fails, with no secret in
     the facts.

Usage:
  score_fixture.py --opa /path/to/opa --policy policies/benchmarks/cis/network_devices/palo_alto
  score_fixture.py ... --config some_running_config.xml   # print the report for another file
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PANOS = os.path.join(ROOT, "collections/ansible_collections/aac/panos")
HARDENED = os.path.join(PANOS, "tests/unit/fixtures/panos_hardened_running_config.xml")
SIMULATED = os.path.join(ROOT, "examples/simulators/network/panos_running_config.xml")

LICENSES = (
    '<response status="success"><result><licenses>'
    "<entry><feature>PAN-DB URL Filtering</feature><expired>no</expired></entry>"
    "<entry><feature>Advanced Threat Prevention</feature><expired>no</expired></entry>"
    "<entry><feature>DNS Security</feature><expired>no</expired></entry>"
    "</licenses></result></response>")
SITE = {"untrusted_zones": ["untrust", "guest"], "internet_zones": ["untrust"],
        "url_block_categories": ["malware", "phishing", "command-and-control"]}
ATTEST = {name: True for name in (
    "management_permitted_ips_reviewed", "management_profile_permitted_ips_reviewed",
    "admin_web_certificate_valid", "vpn_certificate_valid", "ikev2_post_quantum_ppk_enabled",
    "user_mapping_verified_in_logs", "userid_account_minimal_groups",
    "userid_account_no_interactive_logon", "userid_account_no_remote_access",
    "wildfire_file_size_limits_reviewed", "wildfire_cloud_region_approved",
    "ssl_inbound_inspection_reviewed", "decryption_certificate_trusted")}
ATTESTED_IDS = {"1.2.1", "1.2.2", "1.2.5", "1.6.3", "1.7.1", "2.1", "2.5", "2.6", "2.7", "5.1", "5.7", "8.2", "8.3"}
LICENSE_IDS = {"6.8", "6.22", "6.23", "6.24", "6.25"}


def load_mapper():
    spec = importlib.util.spec_from_file_location(
        "panos_cis_facts", os.path.join(PANOS, "plugins/filter/panos_cis_facts.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def score(opa, policy, facts, level=2):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump({"panos_config": facts, "cis_profile": {"level": level}}, fh)
        path = fh.name
    try:
        out = subprocess.run(
            [opa, "eval", "-d", policy, "-i", path, "--format", "json",
             "data.cis_palo_alto_panos.main.compliance_report"],
            capture_output=True, text=True, check=True)
    finally:
        os.unlink(path)
    return json.loads(out.stdout)["result"][0]["expressions"][0]["value"]


def failed_ids(report):
    return {v.split(":")[0] for v in report["violations"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--opa", default="opa")
    ap.add_argument("--policy", default=os.path.join(ROOT, "policies/benchmarks/cis/network_devices/palo_alto"))
    ap.add_argument("--config", help="score this running configuration and print the report")
    args = ap.parse_args()
    mapper = load_mapper()

    if args.config:
        with open(args.config, encoding="utf-8") as fh:
            report = score(args.opa, args.policy, mapper.panos_cis_facts(fh.read()))
        print("%(passed_controls)s passed, %(failed_controls)s failed of %(total_controls)s" % report)
        for line in report["violations"]:
            print("  " + line)
        return 0

    with open(HARDENED, encoding="utf-8") as fh:
        hardened = fh.read()
    with open(SIMULATED, encoding="utf-8") as fh:
        simulated = fh.read()
    problems = []

    def check(label, ok, detail=""):
        print("%s  %s%s" % ("ok  " if ok else "FAIL", label, (" — " + detail) if detail and not ok else ""))
        if not ok:
            problems.append(label)

    full = mapper.panos_cis_facts(hardened, LICENSES, "vsys1", SITE, ATTEST)
    r2 = score(args.opa, args.policy, full, 2)
    check("hardened fixture passes Level 2 (79 of 79)",
          (r2["total_controls"], r2["failed_controls"]) == (79, 0), str(r2["violations"]))
    r1 = score(args.opa, args.policy, full, 1)
    check("hardened fixture passes Level 1 (69 of 69)",
          (r1["total_controls"], r1["failed_controls"]) == (69, 0), str(r1["violations"]))

    no_lic = score(args.opa, args.policy, mapper.panos_cis_facts(hardened, None, "vsys1", SITE, ATTEST))
    check("no license read: exactly 6.8 and 6.22-6.25 fail, as evidence missing",
          failed_ids(no_lic) == LICENSE_IDS and all("evidence missing" in v for v in no_lic["violations"]),
          str(sorted(failed_ids(no_lic))))

    no_att = score(args.opa, args.policy, mapper.panos_cis_facts(hardened, LICENSES, "vsys1", SITE, None))
    check("no attestations: exactly the 13 judgement recommendations fail",
          failed_ids(no_att) == ATTESTED_IDS, str(sorted(failed_ids(no_att))))

    weak_facts = mapper.panos_cis_facts(simulated, None, "vsys1", {"untrusted_zones": ["untrust"],
                                                                 "internet_zones": ["untrust"]}, None)
    weak = score(args.opa, args.policy, weak_facts)
    check("simulated weak configuration fails most recommendations",
          weak["failed_controls"] >= 60, "%s failed" % weak["failed_controls"])
    for wanted in ("1.2.3", "1.5.1", "6.2", "7.2", "7.4"):
        check("simulated weak configuration fails %s" % wanted, wanted in failed_ids(weak))
    text = json.dumps([full, weak_facts])
    check("no secret from either configuration is in the facts",
          not any(s in text for s in ("FIXTURE", "SIMULATOR", "not-a-real-hash", "simulator-community", "phash")))

    print("\n%d problem(s)" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
