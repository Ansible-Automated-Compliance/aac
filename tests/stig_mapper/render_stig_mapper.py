#!/usr/bin/env python3
"""Unit harness for ansible/tasks/stig_linux_build_opa_input.yml and
ansible/tasks/oracle_db_build_opa_input.yml.

Renders a mapper task with Ansible's own templating engine (no playbook run,
no hosts) against a facts fixture and writes the resulting opa_input.json, then
proves the injection safety the mapper headers promise: a hostile payload in a
host-collected string survives verbatim and nothing is evaluated.

Usage: render_stig_mapper.py <task_file> <fixture.json> <out.json>
  task_file  ansible/tasks/stig_linux_build_opa_input.yml  (fixture = facts_data)
             ansible/tasks/oracle_db_build_opa_input.yml   (fixture = oracle_raw)
"""
import copy
import json
import sys

import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar
from ansible.utils.unsafe_proxy import wrap_var

EVIL = "{{ lookup('pipe','id') }} {{ 7*7 }} {% raw %}x{% endraw %}"


def render(build, ctx):
    ctx = dict(ctx)
    for key, expr in build['vars'].items():
        ctx[key] = Templar(loader=DataLoader(), variables=ctx).template(expr)
    return Templar(loader=DataLoader(), variables=ctx).template(build['set_fact']['opa_input'])


def main():
    task_file, fixture, out = sys.argv[1:4]
    tasks = yaml.safe_load(open(task_file))
    build = next(t for t in tasks if 'set_fact' in t and 'opa_input' in t['set_fact'])
    data = json.load(open(fixture))
    linux = 'stig_linux' in task_file
    key = 'facts_data' if linux else 'oracle_raw'
    base = {'opa_hostname': 'fixture-host', 'inventory_hostname': 'fixture-host'}

    opa_input = render(build, {**base, key: wrap_var(data)})
    json.dump(opa_input, open(out, 'w'), indent=1, default=str)
    print('top-level keys:', len(opa_input), sorted(opa_input)[:12], '...')

    hostile = copy.deepcopy(data)
    if linux:
        cf = hostile['custom_facts']
        cf['banners_raw'] = "=== /etc/motd ===\n" + EVIL + "\n=== /etc/issue ===\n" + EVIL + "\n=== /etc/issue.net ===\n"
        cf['sshd_config_raw'] = "port 22\nbanner " + EVIL + "\n"
        cf['stig_raw']['sysctl_raw'] = "kernel.domainname = " + EVIL + "\n" + cf['stig_raw']['sysctl_raw']
        out_h = render(build, {**base, key: wrap_var(hostile)})
        assert EVIL in out_h['login_banner']['issue'] and EVIL == out_h['ssh_config']['Banner'], 'payload altered'
        assert out_h['kernel_params']['kernel.domainname'] == EVIL, 'payload altered in kernel_params'
    else:
        hostile['sql_raw'] = hostile['sql_raw'].replace('"PRODDB"', json.dumps(EVIL), 1)
        hostile['listener_ora'] = EVIL + "\n" + hostile.get('listener_ora', '')
        out_h = render(build, {**base, key: wrap_var(hostile)})
        assert out_h['oracle']['instance_name'] == EVIL, 'payload altered in instance_name'
    blob = json.dumps(out_h, default=str)
    assert ' 49 ' not in blob and 'uid=0(' not in blob and '(root)' not in blob, 'TEMPLATE EVALUATED — injection'
    print('injection check: hostile payload preserved verbatim, nothing evaluated')


if __name__ == '__main__':
    main()
