#!/usr/bin/env python3
"""Unit harness for ansible/tasks/pqc_build_opa_input.yml.

Renders the mapper task with Ansible's own templating engine (no playbook run,
no hosts) against a collector-shaped fixture and writes the resulting
opa_input.json, then proves the injection safety the mapper header promises: a
hostile payload in a host-collected string survives verbatim and nothing is
evaluated.

Usage: render_pqc_mapper.py <fixture.json> <out.json> [task_file]
  fixture.json  {"pqc_raw": {"stdout_lines": [...]}, "pqc_attestations": {...}, ...}
"""
import copy
import json
import os
import sys

import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar
from ansible.utils.unsafe_proxy import wrap_var

EVIL = "{{ lookup('pipe','id') }} {{ 7*7 }} {% raw %}x{% endraw %}"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TASK = os.path.join(HERE, "..", "..", "ansible", "tasks", "pqc_build_opa_input.yml")


def render(build, ctx):
    ctx = dict(ctx)
    for key, expr in build["vars"].items():
        ctx[key] = Templar(loader=DataLoader(), variables=ctx).template(expr)
    return Templar(loader=DataLoader(), variables=ctx).template(build["set_fact"]["opa_input"])


def main():
    fixture, out = sys.argv[1:3]
    task_file = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_TASK
    tasks = yaml.safe_load(open(task_file))
    build = next(t for t in tasks if "set_fact" in t and "opa_input" in t["set_fact"])
    data = json.load(open(fixture))
    ctx = {"opa_hostname": data.get("opa_hostname", "fixture-host")}
    for k, v in data.items():
        ctx[k] = wrap_var(v) if k == "pqc_raw" else v
    result = render(build, ctx)
    json.dump(result, open(out, "w"), indent=2)
    rows = result["pqc"]["crypto_inventory"]
    print(f"rendered {out}: {len(rows)} crypto_inventory rows, "
          f"collector_ok={result['system_info']['collector_ok']}, "
          f"profile={result['pqc'].get('profile', '(absent)')}")

    # injection safety: a hostile value in a certificate path, a kex name and a
    # TLS group must come out byte-identical and never be evaluated
    evil = copy.deepcopy(data)
    lines = evil["pqc_raw"]["stdout_lines"]
    lines.insert(0, f"cert|/etc/pki/tls/certs/{EVIL}.pem|rsaEncryption|2048||sha256WithRSAEncryption")
    lines.insert(1, f"kex|{EVIL}")
    lines.insert(2, f"tls|8443|{EVIL}|TLSv1.3")
    ctx2 = dict(ctx)
    ctx2["pqc_raw"] = wrap_var(evil["pqc_raw"])
    r2 = render(build, ctx2)
    blob = json.dumps(r2)
    assert EVIL in blob, "hostile payload did not survive verbatim"
    assert "49" not in json.dumps([r["algorithm"] for r in r2["pqc"]["crypto_inventory"]]), "7*7 was evaluated"
    assert "uid=" not in blob, "lookup('pipe') was evaluated"
    print("injection check: hostile payload survived verbatim, nothing evaluated")


if __name__ == "__main__":
    main()
