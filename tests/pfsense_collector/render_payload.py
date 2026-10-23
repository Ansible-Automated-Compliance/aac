#!/usr/bin/env python3
"""Unit harness for the payload ansible/playbooks/cis_pfsense_assessment.yml sends to OPA.

Runs the playbook's own payload tasks (Read pfsense_attest, Build OPA input payload, the
optional-section and file tasks) with Ansible's templating engine, evaluating each task's
real `when:` and `loop:`, against a fixture device. No hosts, no AAP job.

Asserts what holds at any library pin:
  1. every section the CIS pfSense v1.1.1 policy reads is sent when the device has it
     (syslog, hasync, openvpn, sshd_config, motd, attest), and the v1.0.0 keys stay;
  2. a section or file the device does not have, or that could not be read, is NOT sent
     (no empty object, no empty OpenVPN server list: the policy must see it as missing);
  3. attest defaults to {} and values are coerced to real booleans (survey strings);
  4. hostile device strings are carried verbatim and never templated.

With --opa and --policy it also scores the payloads against a policy directory
(e.g. the library at the commit that carries CIS pfSense v1.1.1) and prints the summary.

Usage: render_payload.py [--opa /path/to/opa --policy /path/to/pfsense/policy/dir]
"""
import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile

import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar
from ansible.utils.unsafe_proxy import wrap_var

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
PLAYBOOK = os.path.join(ROOT, 'ansible/playbooks/cis_pfsense_assessment.yml')
DEPLOY = os.path.join(ROOT, 'ansible/playbooks/deploy_pfsense_aws.yml')
FIRST_TASK = 'Read pfsense_attest'
LAST_TASK = 'Add message of the day text (CIS 1.3)'
SKIP = {'Fail if pfsense_attest is not a mapping'}

EVIL = "{{ lookup('pipe','id') }} {{ 31337*3 }} {% raw %}x{% endraw %}"
EVAL_MARK = '94011'
ALL_ATTEST = {k: True for k in (
    'autoconfigbackup_enabled', 'default_accounts_secured', 'local_accounts_disabled',
    'admin_default_password_changed', 'unused_rules_reviewed', 'net_snmp_secured',
    'vpn_portal_certificate_trusted')}
V111_KEYS = ('syslog', 'hasync', 'openvpn', 'sshd_config', 'motd', 'attest')
V100_KEYS = ('system', 'filter', 'interfaces', 'snmpd', 'syslogd', 'installedpackages', 'unbound',
             'miniupnpd', 'captiveportal', 'vulnerability_scan', 'vulnerable_packages',
             'version', 'platform', 'hostname')


def payload_tasks():
    play = yaml.safe_load(open(PLAYBOOK))[0]
    names = [t.get('name') for t in play['tasks']]
    tasks = play['tasks'][names.index(FIRST_TASK):names.index(LAST_TASK) + 1]
    return play['vars'], [t for t in tasks if t['name'] not in SKIP]


def tmpl(ctx, expr):
    return Templar(loader=DataLoader(), variables=ctx).template(expr)


def check_attest_gate(ctx):
    """Evaluate the playbook's fail gate on pfsense_attest_map."""
    play = yaml.safe_load(open(PLAYBOOK))[0]
    gate = next(t for t in play['tasks'] if t['name'] == 'Fail if pfsense_attest is not a mapping')
    return tmpl(ctx, '{{ %s }}' % gate['when'])


def render(config, sshd=None, motd=None, attest=None):
    """sshd / motd None means the cat failed (rc 1)."""
    pvars, tasks = payload_tasks()
    ctx = {
        'pfsense_config': wrap_var(config),
        'pfsense_hostname': 'fixture-fw',
        'pfsense_attest': pvars['pfsense_attest'] if attest is None else attest,
        'sshd_config_raw': {'rc': 1, 'stdout': ''} if sshd is None else {'rc': 0, 'stdout': wrap_var(sshd)},
        'motd_raw': {'rc': 1, 'stdout': ''} if motd is None else {'rc': 0, 'stdout': wrap_var(motd)},
    }
    for t in tasks:
        items = t.get('loop', [None])
        for item in items:
            if item is not None:
                ctx['item'] = item
            if 'when' in t and not tmpl(ctx, '{{ %s }}' % t['when']):
                continue
            for k, v in t['set_fact'].items():
                ctx[k] = tmpl(ctx, v)
            if k == 'pfsense_attest_map' and check_attest_gate(ctx):
                raise ValueError('pfsense_attest rejected: not a mapping')
        ctx.pop('item', None)
    return json.loads(json.dumps(ctx['opa_input'], default=str))


def demo_config():
    dep = yaml.safe_load(open(DEPLOY))[0]['vars']
    out = tmpl({'syslog_server': '192.0.2.20'}, dep['opnsense_config_json'])
    return out if isinstance(out, dict) else json.loads(out)


def score(opa, policy, payload):
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump(payload, f)
    try:
        r = subprocess.run([opa, 'eval', '-f', 'json', '-d', policy, '-i', f.name,
                            'data.cis_pfsense.compliance_assessment'], capture_output=True, text=True, check=True)
    finally:
        os.unlink(f.name)
    v = json.loads(r.stdout)['result'][0]['expressions'][0]['value']
    return v['summary'], v['violations']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--opa')
    ap.add_argument('--policy')
    ap.add_argument('--show-violations', action='store_true')
    args = ap.parse_args()

    hard = json.load(open(os.path.join(HERE, 'fixtures/pfsense_hardened.fixture.json')))
    sim = json.load(open(os.path.join(HERE, 'fixtures/sim_device_files.fixture.json')))

    # 1. everything the v1.1.1 policy reads is sent; v1.0.0 keys are kept
    p = render(hard['config'], hard['sshd_config'], hard['motd'])
    for k in V111_KEYS + V100_KEYS:
        assert k in p, 'missing key %s' % k
    assert p['openvpn'] == hard['config']['openvpn'] and p['hasync'] == hard['config']['hasync']
    assert p['syslog'] == hard['config']['syslog'] and p['sshd_config'] == hard['sshd_config']
    assert p['system'] == hard['config']['system'] and p['filter'] == hard['config']['filter']
    print('sections sent (hardened fixture):', sorted(p))

    # 2. absent sections and unreadable files are not sent
    bare = {k: v for k, v in hard['config'].items() if k not in ('syslog', 'hasync', 'openvpn')}
    p = render(bare)
    for k in ('syslog', 'hasync', 'openvpn', 'sshd_config', 'motd'):
        assert k not in p, '%s sent although the device did not have it' % k
    p = render(hard['config'], sshd='', motd='')
    assert p['sshd_config'] == '' and p['motd'] == '', 'a readable empty file is evidence and is sent'
    print('missing-evidence check: absent sections and unreadable files are left out')

    # 3. attestations
    assert render(bare)['attest'] == {}, 'attest must default to empty'
    got = render(bare, attest={'a': 'true', 'b': 'no', 'c': True, 'd': 'yes', 'e': 'maybe', 'f': False})['attest']
    assert got == {'a': True, 'b': False, 'c': True, 'd': True, 'e': False, 'f': False}, got
    assert all(isinstance(v, bool) for v in got.values())
    assert render(bare, attest='autoconfigbackup_enabled: true\nnet_snmp_secured: "no"\n')['attest'] == \
        {'autoconfigbackup_enabled': True, 'net_snmp_secured': False}, 'survey textarea not read'
    assert render(bare, attest='')['attest'] == {}, 'blank survey textarea must mean no attestations'
    for bad in (['autoconfigbackup_enabled'], 'just text'):
        try:
            render(bare, attest=bad)
        except ValueError:
            continue
        raise AssertionError('non-mapping pfsense_attest accepted: %r' % (bad,))
    print('attest check: default empty, values coerced to booleans, non-mapping rejected')

    # 4. hostile device strings are not templated
    hostile = copy.deepcopy(hard['config'])
    hostile['system']['hostname'] = EVIL
    hostile['openvpn']['openvpn-server']['description'] = EVIL
    p = render(hostile, sshd='Banner ' + EVIL, motd=EVIL)
    assert p['motd'] == EVIL and p['sshd_config'] == 'Banner ' + EVIL
    assert p['system']['hostname'] == EVIL and p['openvpn']['openvpn-server']['description'] == EVIL
    assert EVAL_MARK not in json.dumps(p) and 'uid=' not in json.dumps(p), 'TEMPLATE EVALUATED'
    print('injection check: hostile device strings preserved verbatim, nothing evaluated')

    if args.opa and args.policy:
        demo = demo_config()
        cases = [
            ('hardened, attest={}', render(hard['config'], hard['sshd_config'], hard['motd'])),
            ('hardened, all attested', render(hard['config'], hard['sshd_config'], hard['motd'], ALL_ATTEST)),
            ('demo sim, attest={}', render(demo, sim['sshd_config'], sim['motd'])),
            ('demo sim, all attested', render(demo, sim['sshd_config'], sim['motd'], ALL_ATTEST)),
        ]
        for label, payload in cases:
            s, viols = score(args.opa, args.policy, payload)
            print('%-24s %5.1f%%  passing %s/%s' % (label, s['compliance_percentage'], s['passing_controls'], s['total_controls']))
            if args.show_violations:
                for v in viols:
                    print('    ' + v)
    print('OK')


if __name__ == '__main__':
    sys.exit(main())
