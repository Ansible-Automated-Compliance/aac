#!/usr/bin/env python3
"""Unit harness for ansible/tasks/cis_linux_build_opa_input.yml.

Renders the mapper with Ansible's own templating engine (no playbook run, no
hosts) against a facts_data fixture and writes the resulting opa_input.json.
Then runs the two safety checks the mapper's header promises:

  1. Template injection — host-collected strings arrive as module output,
     which Ansible marks AnsibleUnsafe. A hostile payload placed in the banner,
     sshd config, sudoers and logging facts must survive verbatim and nothing
     may be evaluated.
  2. Parser differential — a commented "# Defaults logfile=" / "#
     timestamp_timeout=" in sudoers must NOT read as configured.

Further checks (each would have caught a defect found in the 2026-11 gap
analysis): the running and the on-disk audit rules land in their own fields
and "No rules" is an empty running list; a large world-writable result is a
failure with a count, not missing evidence; the CIS RHEL 9 profile and
attestations are validated and pass through
(ansible/tasks/cis_rhel9_profile_attest.yml).

Usage: render_mapper.py <task_file> <fixture.json> <out.json>
Env:   CIS_RHEL9_POLICY_DIR  a rhel_9 policy directory to derive the real
       profile / attestation vocabulary from (default: the policies submodule)
"""
import copy
import glob
import json
import os
import sys
import tempfile

import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar
from ansible.utils.unsafe_proxy import wrap_var

EVIL = "{{ lookup('pipe','id') }} {{ 31337*3 }} {% raw %}x{% endraw %}"
EVAL_MARK = '94011'  # 31337*3: appears only if the payload was evaluated
# collector blocks added for CIS RHEL 9 v3.0.0 (2026-10-21)
V3_BLOCKS = ('kmod_raw', 'sysctl_raw', 'pkg_state_raw', 'config_raw', 'perms_raw', 'accounts_raw', 'fs_sweep_raw')


def render(build, facts, extra=None):
    ctx = {'facts_data': wrap_var(facts), 'opa_hostname': 'fixture-host', 'inventory_hostname': 'fixture-host'}
    ctx.update(extra or {})
    for key, expr in build['vars'].items():
        ctx[key] = Templar(loader=DataLoader(), variables=ctx).template(expr)
    return Templar(loader=DataLoader(), variables=ctx).template(build['set_fact']['opa_input'])


def main():
    task_file, fixture, out = sys.argv[1:4]
    tasks = yaml.safe_load(open(task_file))
    build = next(t for t in tasks if t.get('name', '').startswith('Build CIS Linux OPA input'))
    facts = json.load(open(fixture))

    opa_input = render(build, facts)
    json.dump(opa_input, open(out, 'w'), indent=1, default=str)
    print('sections emitted:', sorted(opa_input.keys()))

    # 1. template injection
    hostile = copy.deepcopy(facts)
    cf = hostile['custom_facts']
    cf['banners_raw'] = "=== /etc/motd ===\n" + EVIL + "\n=== /etc/issue ===\n" + EVIL + "\n=== /etc/issue.net ===\n"
    cf['sshd_config_raw'] = "port 22\nbanner " + EVIL + "\n"
    cf['sudoers_raw'] = "Defaults logfile=/var/log/sudo.log\n# " + EVIL + "\n"
    cf['logging_raw'] = "=== rsyslog ===\n# " + EVIL + "\n*.* /var/log/messages\n=== journald ===\nStorage=" + EVIL + "\n"
    # the supplement blocks carry host strings too: user names, paths, cert subjects, key comments
    cf['user_group_raw'] = "pw|" + EVIL + "|0|0|/root|/bin/bash\nroot_path|/usr/bin\nend:ok\n"
    cf['certs_raw'] = "cert|30|RSA|2048|sha256WithRSAEncryption|/etc/pki/tls/certs/x.crt|CN=" + EVIL + "\nend:ok\n"
    cf['authorized_keys_raw'] = ("akfile|alice|alice|0600|/home/alice/.ssh/authorized_keys\n"
                                 "akkey|/home/alice/.ssh/authorized_keys|256|SHA256:x|ED25519|" + EVIL + "\nend:ok\n")
    out_h = render(build, hostile)
    blob = json.dumps(out_h, default=str)
    assert EVIL in out_h['ssh']['sshd_config_raw'] and EVIL in out_h['sudo']['sudoers_content'], 'payload altered'
    assert EVIL in out_h['user_group']['uid_zero_accounts'], 'payload altered (user_group)'
    assert out_h['certificates']['system_certs'][0]['subject'] == 'CN=' + EVIL, 'payload altered (certificates)'
    assert out_h['authorized_keys']['files'][0]['keys'][0]['comment'] == EVIL, 'payload altered (authorized_keys)'
    assert EVAL_MARK not in blob and 'uid=' not in blob, 'TEMPLATE EVALUATED — injection'
    print('injection check: hostile payload preserved verbatim, nothing evaluated')

    # 2. parser differential: commented sudo directives must not count
    commented = copy.deepcopy(facts)
    commented['custom_facts']['sudoers_raw'] = "# Defaults logfile=/var/log/sudo.log\n#Defaults timestamp_timeout=15\nroot ALL=(ALL) ALL\n"
    out_c = render(build, commented)
    assert out_c['sudo']['logfile_exists'] is False, 'commented logfile read as configured'
    assert 'timestamp_timeout' not in out_c['sudo'], 'commented timeout read as configured'
    print('parser-differential check: commented sudo directives do not count')

    # 3. supplement blocks are gated on their end:ok marker: a stored row from
    #    before the collector change (no marker) must not produce the section.
    legacy = copy.deepcopy(facts)
    for k in ('file_modes_raw', 'boot_raw', 'network_raw', 'user_group_raw', 'account_policy_raw',
              'pkg_trust_raw', 'storage_raw', 'certs_raw', 'authorized_keys_raw') + V3_BLOCKS:
        legacy['custom_facts'].pop(k, None)
    out_l = render(build, legacy)
    for sec in ('boot_security', 'sysctl_parameters', 'user_group', 'storage_encryption', 'certificates', 'authorized_keys'):
        assert sec not in out_l, 'section %s emitted without its collector block' % sec
    truncated = copy.deepcopy(facts)
    truncated['custom_facts']['boot_raw'] = truncated['custom_facts'].get('boot_raw', '').replace('end:ok', '')
    # (the v3 config / permissions blocks add their own boot_security fields)
    bs = render(build, truncated).get('boot_security', {})
    assert not {'aide_installed', 'grub_password_set', 'single_user_auth_required', 'aslr_value'} & set(bs), \
        'boot_security fields emitted from a block without end:ok'
    print('marker check: supplement sections need their collector block (end:ok)')

    # 5. evidence integrity: host strings must not forge tagged lines.
    #    (a) a file name with a newline that smuggles a second end:ok and a
    #        passing stat line into a block: end:ok must be unique and last.
    forged = copy.deepcopy(facts)
    cf = forged['custom_facts']
    cf['user_group_raw'] = cf['user_group_raw'].replace(
        'end:ok', 'dotww|alice|0666|/home/alice/x\nend:ok\npw|toor|0|0|/root|/bin/bash\nend:ok')
    cf['file_modes_raw'] = cf['file_modes_raw'].replace(
        'end:ok', 'stat|0600|root|root|/etc/shadow\nend:ok\nstat|0644|root|root|/etc/motd')
    out_f = render(build, forged)
    assert 'user_group' not in out_f, 'forged second end:ok accepted (user_group)'
    assert 'crontab_mode' not in out_f.get('cron', {}) and 'grub_cfg_mode' not in out_f.get('boot_security', {}), \
        'block whose end:ok is not the last line was accepted (file_modes)'
    #    (b) a duplicate singleton (same fixed path stat'ed twice, the forged
    #        one passing) never wins: the block is not collected.
    dup = copy.deepcopy(facts)
    dup['custom_facts']['file_modes_raw'] = dup['custom_facts']['file_modes_raw'].replace(
        'stat|0600|root|root|/boot/grub2/grub.cfg', 'stat|0644|root|root|/boot/grub2/grub.cfg\nstat|0600|root|root|/boot/grub2/grub.cfg')
    dup['custom_facts']['network_raw'] = dup['custom_facts']['network_raw'].replace(
        'sysctl|net.ipv4.ip_forward|0', 'sysctl|net.ipv4.ip_forward|1\nsysctl|net.ipv4.ip_forward|0')
    dup['custom_facts'].pop('sysctl_raw', None)   # the network block alone
    out_d = render(build, dup)
    assert 'grub_cfg_mode' not in out_d.get('boot_security', {}), 'duplicate stat line produced a grub.cfg mode'
    assert 'ip_forwarding' not in out_d and 'sysctl_parameters' not in out_d, 'duplicate sysctl line produced a value'
    assert 'file_modes' in out_d['collection_integrity'] and 'network' in out_d['collection_integrity'], 'rejection not recorded'
    #    (c) a hostile NAME (as an unprivileged user can create) is replaced
    #        by the collector with unsafe:<sha256 prefix>; the record is kept,
    #        still judged, and the block is NOT invalidated (no suppression).
    uns = copy.deepcopy(facts)
    uns['custom_facts']['user_group_raw'] = uns['custom_facts']['user_group_raw'].replace(
        'end:ok', 'unsafe_name|dotww\ndotww|alice|0666|unsafe:0123456789abcdef\nend:ok')
    uns['custom_facts']['storage_raw'] = uns['custom_facts']['storage_raw'].replace(
        'end:ok', 'unsafe_name|mnt\nmnt|unsafe:fedcba9876543210|unsafe:00112233aabbccdd|no|no\nend:ok')
    out_u = render(build, uns)
    assert {'user': 'alice', 'mode': '0666', 'file': 'unsafe:0123456789abcdef'} in out_u['user_group']['dotfiles_group_or_world_writable'], \
        'world-writable dotfile with a hostile name was dropped'
    assert 'unsafe:fedcba9876543210' in out_u['storage_encryption']['unencrypted_data_partitions'], 'hostile mount record dropped'
    assert 'dotww' in out_u['collection_integrity']['user_group']['unsafe_names'], 'substitution not recorded'
    print('integrity check: forged end:ok and duplicate singletons never pass; hostile names keep their record')

    # 6. incomplete evidence is never a pass (collector side is exercised for
    #    real by collector_shell_test.sh): missing command, truncated list,
    #    symlinked authorized_keys, unparsable certificate.
    inc = copy.deepcopy(facts)
    cf = inc['custom_facts']
    cf['authorized_keys_raw'] = cf['authorized_keys_raw'].replace(
        'end:ok', 'symlink|akfile|/home/bob/.ssh/authorized_keys\nakfile|bob|bob|0777|/home/bob/.ssh/authorized_keys\nend:ok')
    cf['user_group_raw'] = cf['user_group_raw'].replace(
        'end:ok', 'dotww|alice|0666|/home/alice/.real\ntruncated|dotww|bob\nend:ok')
    cf['storage_raw'] = cf['storage_raw'].replace('end:ok', 'truncated|mnt\nend:ok')
    cf['certs_raw'] = cf['certs_raw'].replace('end:ok', 'cert|unparsable|unparsable||unparsable|/etc/pki/tls/certs/broken.crt|/etc/pki/tls/certs/broken.crt\nend:ok')
    cf['network_raw'] = cf['network_raw'].replace('end:ok', 'missing_cmd|ip\nend:ok')
    cf.pop('sysctl_raw', None)   # the network block alone
    out_i = render(build, inc)
    assert {'path': '/home/bob/.ssh/authorized_keys', 'user': 'bob', 'expected_owner': 'bob', 'owner': 'bob', 'mode': '0777', 'keys': []} \
        in out_i['authorized_keys']['files'], 'symlinked authorized_keys record lost'
    dots = out_i['user_group']['dotfiles_group_or_world_writable']
    assert {'user': 'alice', 'mode': '0666', 'file': '/home/alice/.real'} in dots, "one user's truncation hid another user's finding"
    assert any(d['user'] == 'bob' and d.get('truncated') for d in dots), 'truncated dotfile list not a failing per-user entry'
    assert 'storage_encryption' not in out_i, 'truncated mount list read as complete'
    # (firewall.backend / zones come from the v3 config block; type/active from the network block)
    assert 'sysctl_parameters' not in out_i and 'type' not in out_i.get('firewall', {}), 'block with a missing command emitted'
    broken = [c for c in out_i['certificates']['system_certs'] if c['path'].endswith('broken.crt')]
    assert broken and 'days_until_expiry' not in broken[0], 'unparsable certificate skipped or given an expiry'
    trunc_ak = copy.deepcopy(facts)
    trunc_ak['custom_facts']['authorized_keys_raw'] = trunc_ak['custom_facts']['authorized_keys_raw'].replace(
        'end:ok', 'akfile|bob|bob|0600|/home/bob/.ssh/authorized_keys\n'
                  'akkey|/home/bob/.ssh/authorized_keys|1024|SHA256:b|RSA|bob@example.com\n'
                  'truncated|akkey|/home/bob/.ssh/authorized_keys\nend:ok')
    ak_files = {f['path']: f for f in render(build, trunc_ak)['authorized_keys']['files']}
    assert len(ak_files['/home/alice/.ssh/authorized_keys']['keys']) == 1 and not ak_files['/home/alice/.ssh/authorized_keys'].get('truncated'), \
        "one file's truncation touched another file"
    bob = ak_files['/home/bob/.ssh/authorized_keys']
    assert bob.get('truncated') and any(k['comment'] == '' for k in bob['keys']) and any(k.get('bits') == 1024 for k in bob['keys']), \
        'truncated key list not a failing per-file entry, or the keys read so far were lost'
    check_world_writable(build, facts)
    miss_ak = copy.deepcopy(facts)
    miss_ak['custom_facts']['authorized_keys_raw'] = 'missing_cmd|ssh-keygen\nend:ok\n'
    assert 'authorized_keys' not in render(build, miss_ak), 'authorized_keys emitted without ssh-keygen'
    print('completeness check: missing commands, truncation, symlinks and unparsable certs never pass')

    # 7. fstab evidence comes from the CONFIGURED entries, never from the live
    #    mount: an encrypted live /home with an unencrypted replacement in fstab
    #    is an unencrypted fstab data mount; an unmounted entry is still listed;
    #    root's home is judged like any other interactive account's.
    cfg = copy.deepcopy(facts)
    cfg['custom_facts']['storage_raw'] = ('fips|0\nmnt|/dev/mapper/luks-home|/home|yes|yes\n'
                                         'fstab|/dev/sdb1|/home|no|yes\nfstab|/dev/sdc1|/data|no|no\nend:ok\n')
    st = render(build, cfg)['storage_encryption']
    assert {'device': '/dev/sdb1', 'mountpoint': '/home'} in st['fstab_unencrypted_data_mounts'], \
        'live encrypted mount reported as the fstab entry'
    assert any(e['mountpoint'] == '/data' and e['device_present'] is False for e in st['fstab_entries']), 'unmounted fstab entry omitted'
    assert '/dev/mapper/luks-home' not in [e['device'] for e in st['fstab_entries']], 'live mount leaked into fstab evidence'
    nofs = copy.deepcopy(facts)
    nofs['custom_facts']['storage_raw'] = nofs['custom_facts']['storage_raw'].replace('end:ok', 'truncated|fstab\nend:ok')
    assert 'storage_encryption' not in render(build, nofs), 'unreadable fstab read as complete'
    ug = opa_input['user_group']
    assert any(h.get('user') == 'root' for h in ug.get('home_directories', ug.get('homes', []))) or 'root' in json.dumps(ug), \
        "root's home not in the home scan"
    print('configured-source check: fstab from fstab lines, root home scanned')

    # 8. CIS RHEL 9 v3.0.0 blocks: same contract as the supplement blocks.
    def v3(edit):
        f = copy.deepcopy(facts)
        edit(f['custom_facts'])
        return render(build, f)
    #    (a) each block needs its own end:ok; a forged second end:ok is rejected
    for blk, probe in (('kmod_raw', lambda o: o.get('disabled_network_modules')),
                       ('sysctl_raw', lambda o: o.get('sysctl_parameters', {}).get('persisted')),
                       ('pkg_state_raw', lambda o: o.get('pam', {}).get('package_versions')),
                       ('config_raw', lambda o: o.get('crypto_policy')),
                       ('perms_raw', lambda o: o.get('critical_files')),
                       ('accounts_raw', lambda o: o.get('user_group', {}).get('shadow_entries')),
                       ('fs_sweep_raw', lambda o: o.get('unowned_files'))):
        assert probe(opa_input), '%s: fixture field missing' % blk
        assert not probe(v3(lambda cf: cf.update({blk: cf[blk].replace('end:ok', '')}))), '%s: emitted without end:ok' % blk
        assert not probe(v3(lambda cf: cf.update({blk: cf[blk].replace('end:ok', 'end:ok\nx|y\nend:ok')}))), '%s: forged end:ok accepted' % blk
        assert not probe(v3(lambda cf: cf.update({blk: 'missing_cmd|x\n' + cf[blk]}))), '%s: emitted with a missing command' % blk
    #    (b) duplicate singletons never win
    o = v3(lambda cf: cf.update(kmod_raw=cf['kmod_raw'].replace('kmod|sctp|yes|yes|no', 'kmod|sctp|yes|no|yes\nkmod|sctp|yes|yes|no'),
                                sysctl_raw=cf['sysctl_raw'].replace('persist|net.ipv4.ip_forward|0', 'persist|net.ipv4.ip_forward|1\npersist|net.ipv4.ip_forward|0')))
    assert 'disabled_network_modules' not in o and 'persisted' not in o.get('sysctl_parameters', {}), 'duplicate v3 singleton accepted'
    assert 'kernel_modules' in o['collection_integrity'] and 'sysctl' in o['collection_integrity'], 'v3 rejection not recorded'
    #    (c) a parameter persisted nowhere is "unset" (a fail), not missing
    o = v3(lambda cf: cf.update(sysctl_raw=cf['sysctl_raw'].replace('persist|net.ipv4.tcp_syncookies|1\n', '')))
    assert o['sysctl_parameters']['persisted']['net.ipv4.tcp_syncookies'] == 'unset', 'unpersisted parameter not reported unset'
    #    (d) package state only from the RPM database: no package booleans elsewhere
    o = v3(lambda cf: cf.update(pkg_state_raw=cf['pkg_state_raw'].replace('family|rpm', 'family|other')))
    assert 'packages' not in o or 'avahi' not in o['packages'], 'package booleans emitted without an RPM database'
    #    (e) a unit service_facts reported keeps its service_facts record
    o = v3(lambda cf: cf.update(pkg_state_raw=cf['pkg_state_raw'].replace('end:ok', 'unit|chronyd.service|loaded|inactive|disabled\nend:ok')))
    assert o['services']['chronyd.service'].get('state') == facts['ansible_facts']['services']['chronyd.service']['state'], 'systemctl overrode service_facts'
    assert o['services']['nftables.service']['status'] == 'not-found', 'not-found unit not reported'
    #    (f) a capped list drops only its own field
    o = v3(lambda cf: cf.update(perms_raw=cf['perms_raw'].replace('end:ok', 'truncated|logf\nend:ok'),
                                fs_sweep_raw=cf['fs_sweep_raw'].replace('end:ok', 'truncated|priv\nend:ok')))
    assert 'log_file_permissions' not in o and 'critical_files' in o, 'truncated /var/log sweep read as complete, or it dropped the block'
    assert any(c.startswith('TRUNCATED') for c in o['auditd']['privileged_commands']) and 'unowned_files' in o, \
        'truncated privileged list read as complete (no sentinel)'
    #        an incomplete sweep: a known non-zero count still fails (emitted,
    #        truncated); zero found in an incomplete sweep is not collected
    o = v3(lambda cf: cf.update(fs_sweep_raw=cf['fs_sweep_raw'].replace('count|unowned|0', 'unowned|/srv/a\ncount|unowned|1')
                                .replace('end:ok', 'sweep_rc|1|1\ntruncated|unowned\ntruncated|ungrouped\ntruncated|nosticky\ntruncated|priv\nend:ok')))
    assert o['unowned_files']['count'] == 1 and o['unowned_files']['truncated'] is True, 'known unowned count dropped on an incomplete sweep'
    assert 'ungrouped_files' not in o and 'sticky_bit' not in o, 'zero found in an incomplete sweep read as clean'
    #        lab findings 2026-10-22: a file whose lines are all comments is
    #        collected (no active settings), absent cron.yearly is a fact,
    #        unset TMOUT / GDM idle-delay fail rather than go missing
    o = v3(lambda cf: cf.update(config_raw=cf['config_raw'].replace('txt|faillock|deny = 5\n', 'file|faillock\n').replace('txt|faillock|unlock_time = 900\n', '')
                                .replace('txt|faillock|even_deny_root\n', '').replace('txt|faillock|root_unlock_time = 60\n', ''),
                                account_policy_raw='umask|/etc/login.defs|027\nend:ok'))
    assert o['pam']['faillock_conf_raw'].startswith('# /etc/security/faillock.conf: no active settings'), 'all-comment faillock.conf not collected'
    assert o['pam']['tmout'] == 0, 'unset TMOUT not reported as 0'
    assert opa_input['cron']['cron_yearly_exists'] is False, 'absent cron.yearly not reported'
    o = v3(lambda cf: cf.update(kmod_raw=cf['kmod_raw'].replace('end:ok', 'wmod|wlan0|iwlwifi|yes|no|yes\nwmod|wlan1|unknown\nend:ok')))
    wm = o['wireless_interfaces']['modules']
    assert {'module': 'iwlwifi', 'interface': 'wlan0', 'available': True, 'disabled': False, 'loaded': True} in wm and any(m['module'] == 'unknown' and m['loaded'] for m in wm), 'wireless modules'
    o = v3(lambda cf: cf.update(perms_raw=cf['perms_raw'].replace('end:ok', 'truncated|critical\nend:ok')))
    assert 'critical_files' not in o, 'truncated permissions block accepted'
    #    (g) hostile host text in the v3 text fields stays verbatim, unevaluated
    o = v3(lambda cf: cf.update(config_raw=cf['config_raw'].replace('end:ok', 'txt|dnf|' + EVIL + '\ntxt|augenrules|' + EVIL + '\nend:ok'),
                                perms_raw=cf['perms_raw'].replace('end:ok', 'unsafe_name|logf\nf|logf|0666|root|root|unsafe:0123456789abcdef\nend:ok')))
    blob_v3 = json.dumps(o, default=str)
    assert EVAL_MARK not in blob_v3 and EVIL in o['initial_setup']['dnf_conf_raw'] and EVIL in o['auditd']['augenrules_check'], 'v3 text evaluated'
    assert any(f['file'] == 'unsafe:0123456789abcdef' for f in o['log_file_permissions']['analysis']), 'hostile log file name dropped'
    #    (h) no password hash: shadow evidence is state + aging only
    assert all(set(e) <= {'user', 'has_password', 'locked', 'last_change', 'max_days', 'warn_days', 'inactive'} for e in opa_input['user_group']['shadow_entries'])
    #    (i) GDM: an unlocked or missing key is not configured
    o = v3(lambda cf: cf.update(pkg_state_raw=cf['pkg_state_raw'].replace('pkg|gdm|no', 'pkg|gdm|yes'),
                                config_raw=cf['config_raw'].replace('end:ok', 'dconf|banner-message-enable|true\ndconf|banner-message-enable|false\n'
                                                                      'dconf|idle-delay|uint32 900\ndlock|/org/gnome/desktop/session/idle-delay\nend:ok')))
    g = o['initial_setup']
    assert g['gdm_installed'] and g['gdm_banner_configured'] is False and g['gdm_banner_override_allowed'] is True, 'conflicting dconf banner read as set'
    assert g['gdm_idle_delay'] == 900 and g['gdm_lock_override_allowed'] is True and g['gdm_lock_delay'] == 0, 'GDM lock fields (unset lock-delay is the GNOME default 0)'
    #    (j) user_group v3 fields only beside a usable user/group block
    o = v3(lambda cf: cf.update(user_group_raw=cf['user_group_raw'].replace('end:ok', '')))
    assert 'user_group' not in o and 'encrypt_method' in o['pam'], 'v3 user_group fields emitted without the passwd list'
    #    (k) banner sensitive information: an escape that prints system data or
    #        the OS id is sensitive; plain text is not (YAML -> Jinja -> regex chain)
    o = v3(lambda cf: cf.update(banners_raw='=== /etc/motd ===\nWelcome to Red Hat Enterprise Linux\n=== /etc/issue ===\n\\S\nKernel \\r on \\m\n'
                                            '=== /etc/issue.net ===\nAuthorized uses only.\n'))
    s = o['initial_setup']
    assert s['motd_contains_sensitive_info'] is True and s['issue_contains_sensitive_info'] is True, 'OS name or \\S/\\r/\\m escape not flagged'
    assert s['issue_net_contains_sensitive_info'] is False, 'plain banner flagged'
    o = v3(lambda cf: cf.update(banners_raw='=== /etc/motd ===\nThis rhel host is monitored, all access is logged.\n=== /etc/issue ===\nAuthorized \\v\n=== /etc/issue.net ===\nmrsv\n'))
    s = o['initial_setup']
    assert s['motd_contains_sensitive_info'] and s['issue_contains_sensitive_info'] and not s['issue_net_contains_sensitive_info'], 'os id / \\v / bare letters'
    print('v3 check: markers, singletons, unset persistence, RPM-only packages, per-field caps, hostile text, GDM, no hashes')

    # 4. recursive merge: supplement fields extend, never replace, the base sections
    if 'crontab_mode' in opa_input.get('cron', {}):
        assert 'crond_enabled' in opa_input['cron'], 'cron supplement replaced daemon state'
    if 'tmout' in opa_input.get('pam', {}) and facts['custom_facts'].get('pam_config_raw'):
        assert 'system_auth' in opa_input['pam'], 'pam supplement replaced system_auth'
    if 'log_permissions' in opa_input.get('auditd', {}) and facts['custom_facts'].get('auditd_active_rules_raw'):
        assert 'active_rules' in opa_input['auditd'] and 'rules' in opa_input['auditd'], 'auditd supplement replaced the rules'
    print('merge check: supplement fields extend the base sections')

    check_audit_rules(build, facts, opa_input)
    check_profile_attest(os.path.join(os.path.dirname(os.path.abspath(task_file)), 'cis_rhel9_profile_attest.yml'), build, facts)

    # Debian / Ubuntu supplement, against the Ubuntu 22.04 fixture beside this one
    ubuntu = os.path.join(os.path.dirname(os.path.abspath(fixture)), 'ubuntu2204_facts.fixture.json')
    if os.path.exists(ubuntu):
        deb_checks(build, facts, ubuntu)


def check_world_writable(build, facts):
    """CIS 7.1.11: the policy treats world_writable.truncated as evidence
    missing, so a capped list must arrive as a failure with its count."""
    def sweep(cf, edit):
        cf['fs_sweep_raw'] = edit(cf['fs_sweep_raw'])
    # (a) complete sweep, 250 files, 100 listed: a fail with the true count
    big = copy.deepcopy(facts)
    sweep(big['custom_facts'], lambda t: t.replace('count|wwfile|0', 'count|wwfile|250').replace(
        'end:ok', ''.join('wwfile|/srv/w%d\n' % i for i in range(100)) + 'truncated|wwfile\nend:ok'))
    ww = render(build, big)['world_writable']
    assert ww['count'] == 250 and len(ww['files']) == 100 and 'truncated' not in ww, 'capped world-writable list turned into missing evidence'
    assert ww['compliant'] is False and ww['sample_capped'] is True and ww['count_complete'] is True, 'capped world-writable list read as complete'
    # (b) the sweep timed out after finding files: not collected (truncated),
    #     the paths found kept as evidence, count a lower bound
    to = copy.deepcopy(facts)
    sweep(to['custom_facts'], lambda t: t.replace('count|wwfile|0', 'count|wwfile|3').replace(
        'end:ok', 'wwfile|/srv/a\nwwfile|/srv/b\nwwfile|/srv/c\nsweep_rc|1|124\ntruncated|unowned\ntruncated|ungrouped\n'
                  'truncated|nosticky\ntruncated|priv\ntruncated|wwfile\nend:ok'))
    ww = render(build, to)['world_writable']
    assert ww['truncated'] is True and ww['count'] == 3 and ww['files'] == ['/srv/a', '/srv/b', '/srv/c'] and ww['count_complete'] is False \
        and ww['compliant'] is False, 'timed-out sweep not reported as not collected, or its findings dropped'
    # (c) the sweep timed out having found nothing: not collected
    tz = copy.deepcopy(facts)
    sweep(tz['custom_facts'], lambda t: t.replace('end:ok', 'sweep_rc|1|124\ntruncated|wwfile\nend:ok'))
    ww = render(build, tz)['world_writable']
    assert ww['truncated'] is True and ww['compliant'] is False and ww['count'] == 0, 'timed-out world-writable sweep read as clean'
    # (c2) an invalid sweep block (watchdog, no end:ok) on a new row: no section,
    #      never the root-only legacy fields
    wd = copy.deepcopy(facts)
    sweep(wd['custom_facts'], lambda t: t.replace('end:ok', ''))
    assert 'world_writable' not in render(build, wd), 'invalid sweep fell back to the root-only legacy sweep'
    # (d) a stored row from before the wwfile list: the legacy fields, same rules
    def legacy(**kw):
        f = copy.deepcopy(facts)
        f['custom_facts']['fs_sweep_raw'] = '\n'.join(l for l in f['custom_facts']['fs_sweep_raw'].split('\n') if 'wwfile' not in l)
        for k in ('world_writable_files', 'world_writable_count', 'world_writable_truncated'):
            f['custom_facts'].pop(k, None)
        f['custom_facts'].update(kw)
        return render(build, f)
    ww = legacy(world_writable_files=['/tmp/w%d' % i for i in range(100)], world_writable_count='250', world_writable_truncated=True)['world_writable']
    assert ww['count'] == 250 and 'truncated' not in ww and ww['compliant'] is False and ww['source'] == 'legacy_root_filesystem_sweep', \
        'legacy capped list turned into missing evidence'
    for c in (None, ''):
        ww = legacy(world_writable_files=[], world_writable_count=c, world_writable_truncated=True)['world_writable']
        assert ww['truncated'] is True and ww['compliant'] is False, 'legacy timed-out sweep read as clean'
    ww = legacy(world_writable_files=['/tmp/x'], world_writable_count=None, world_writable_truncated=True)['world_writable']
    assert ww['truncated'] is True and ww['files'] == ['/tmp/x'] and ww['count_complete'] is False, 'legacy partial finding dropped'
    assert legacy(world_writable_files=[], world_writable_count=0, world_writable_truncated=False)['world_writable']['compliant'] is True
    assert 'world_writable' not in legacy(), 'a row without any world-writable fact must render, without the section'
    print('world-writable check: a capped list fails with its count, a timeout is not collected (findings kept)')


def check_audit_rules(build, facts, opa_input):
    """CIS 6.2.3.x: running rules (auditctl -l) and on-disk rules (rules.d)
    are two facts; each lands in its own field, or in none."""
    a = opa_input['auditd']
    assert a['rules'] != a['active_rules'], 'fixture: the two audit sources must differ'
    assert '-w /etc/group -p wa -k identity' in a['rules'] and '-w /etc/group -p wa -k identity' not in a['active_rules'], 'on-disk rule leaked into the running rules'
    assert '-w /etc/shadow -p wa -k identity' in a['active_rules'] and '-w /etc/shadow -p wa -k identity' not in a['rules'], 'running rule leaked into the on-disk rules'
    assert '-e 2' in a['rules'] and not any(r.startswith(('-e', '-c')) for r in a['active_rules']), 'control lines belong to the on-disk rules only'
    assert a['rules_files'] == ['10-base.rules', '50-identity.rules', '50-privileged.rules', '99-finalize.rules'] and '' not in a['rules']
    assert a['running_status'] == {'enabled': 2, 'failure': 1}, 'auditctl -s status'

    def with_cf(**kw):
        f = copy.deepcopy(facts)
        for k, v in kw.items():
            if v is None:
                f['custom_facts'].pop(k, None)
            else:
                f['custom_facts'][k] = v
        o = render(build, f)
        return o.get('auditd', {}), o.get('collection_integrity', {})
    # "No rules" is a collected, EMPTY running list; the on-disk rules are untouched
    au, _ = with_cf(auditd_active_rules_raw='norules\nstatus|enabled|1\nstatus|failure|1\nend:ok')
    assert au['active_rules'] == [] and au['rules'] == a['rules'] and au['running_status']['enabled'] == 1, '"No rules" is not an empty running list'
    # auditctl failing / missing / odd output: running rules NOT COLLECTED
    for raw, why in (('unreadable|auditctl -l|rc=1\nend:ok', 'failing auditctl'), ('missing_cmd|auditctl\nend:ok', 'missing auditctl'),
                     ('r|-w /etc/passwd -p wa\nWarning - something\nend:ok', 'unexpected line'), ('norules\nr|-w /x -p wa\nend:ok', 'No rules beside rules'),
                     ('r|-w /etc/passwd -p wa', 'no end:ok'), ('r|-w /x -p wa\nend:ok\nr|-w /y -p wa\nend:ok', 'forged end:ok'), ('', 'not run')):
        au, integ = with_cf(auditd_active_rules_raw=raw)
        assert 'active_rules' not in au and 'rules' in au, '%s: running rules emitted' % why
    au, integ = with_cf(auditd_active_rules_raw='unreadable|auditctl -l|rc=1\nend:ok')
    assert integ['audit_rules_running']['unreadable'] == ['auditctl -l|rc=1'], 'rejection not recorded'
    # no rules.d is a collected, empty on-disk list; an unreadable file is not collected
    au, _ = with_cf(auditd_ondisk_rules_raw='nodir|/etc/audit/rules.d\nend:ok')
    assert au['rules'] == [] and 'active_rules' in au, 'absent rules.d is not an empty on-disk list'
    au, integ = with_cf(auditd_ondisk_rules_raw='file|a.rules\nl|-w /etc/passwd -p wa\nunreadable|/etc/audit/rules.d/b.rules\nend:ok')
    assert 'rules' not in au and 'audit_rules_on_disk' in integ, 'partly unreadable rules.d read as complete'
    au, _ = with_cf(auditd_ondisk_rules_raw='file|a.rules\nl|# only a comment\nend:ok')
    assert au['rules'] == ['# only a comment'], 'comment-only rules.d must stay evaluable (a fail), not empty'
    au, _ = with_cf(auditd_ondisk_rules_raw='file|a.rules\nl|' + EVIL + '\nl|end:ok\nend:ok')
    assert au['rules'] == [EVIL, 'end:ok'] and EVAL_MARK not in json.dumps(au, default=str), 'rule text evaluated or dropped'
    # a stored row with only the legacy one-text auditd_rules_raw: neither field
    au, _ = with_cf(auditd_active_rules_raw=None, auditd_ondisk_rules_raw=None)
    assert 'rules' not in au and 'active_rules' not in au and 'config' in au, 'legacy single-source text mapped to a source it may not be'
    print('audit-rules check: running and on-disk rules apart, "No rules" empty, failures not collected')


def check_profile_attest(task_file, build, facts):
    """cis_rhel9_profile_attest.yml: render its own expressions against a stub
    policy and (when available) the real one; then the mapper pass-through."""
    try:   # lookups (fileglob, file) need the plugin loader outside a playbook run
        from ansible.plugins.loader import init_plugin_loader
        init_plugin_loader()
    except ImportError:
        pass
    tasks = yaml.safe_load(open(task_file))
    vocab_t, valid_t = tasks[0], tasks[1]
    assert tasks[2]['when'] == '_cis_rhel9_selection_errors | length > 0', 'fail task condition changed'

    def run(policy_dir, **kv):
        ctx = {'cis_rhel9_policy_dir': policy_dir, 'playbook_dir': '/nonexistent'}
        ctx.update(kv)
        t = lambda e: Templar(loader=DataLoader(), variables=ctx).template(e)
        for k, e in vocab_t['vars'].items():
            ctx[k] = t(e)
        ctx['_cis_rhel9_vocab'] = t(vocab_t['ansible.builtin.set_fact']['_cis_rhel9_vocab'])
        for k, e in valid_t['vars'].items():
            ctx[k] = t(e)
        sf = valid_t['ansible.builtin.set_fact']
        return t(sf['_cis_rhel9_selection_errors']), t(sf['cis_rhel9_selection']), ctx['_cis_rhel9_vocab']

    stub = tempfile.mkdtemp()
    open(os.path.join(stub, 'a.rego'), 'w').write(
        'package x\nprofiles := {"level1_server": {"platform": "server", "level": 1}, "level2_server": {"platform": "server", "level": 2}, '
        '"level1_workstation": {"platform": "workstation", "level": 1}, "level2_workstation": {"platform": "workstation", "level": 2}}\n')
    open(os.path.join(stub, 'b.rego'), 'w').write('package y\nr if input.attest.gpg_keys_reviewed == true\nq if input.attest.suid_sgid_files_reviewed == true\n')
    empty = tempfile.mkdtemp()

    err, sel, voc = run(stub)
    assert err == [] and sel == {'profile': 'level1_server', 'attest': {}, 'attestation_records': []}, (err, sel)
    assert voc['profiles'] == ['level1_server', 'level1_workstation', 'level2_server', 'level2_workstation'] and voc['attest'] == ['gpg_keys_reviewed', 'suid_sgid_files_reviewed']
    err, sel, _ = run(stub, cis_rhel9_profile='level2_server', cis_rhel9_attestations={
        'gpg_keys_reviewed': True, 'suid_sgid_files_reviewed': {'attested': True, 'attested_by': 'auditor', 'evidence_ref': 'CHG-1'}})
    assert err == [] and sel['profile'] == 'level2_server' and sel['attest'] == {'gpg_keys_reviewed': True, 'suid_sgid_files_reviewed': True}, (err, sel)
    assert {'name': 'suid_sgid_files_reviewed', 'attested': True, 'attested_by': 'auditor', 'evidence_ref': 'CHG-1'} in sel['attestation_records']
    err, sel, _ = run(stub, cis_rhel9_attestations='gpg_keys_reviewed: true\nsuid_sgid_files_reviewed: false\n')   # a survey text field
    assert err == [] and sel['attest'] == {'gpg_keys_reviewed': True, 'suid_sgid_files_reviewed': False}, (err, sel)
    for kv, why in (({'cis_rhel9_profile': 'level3_server'}, 'unknown profile'), ({'cis_rhel9_profile': 'level1'}, 'alias outside the vocabulary'),
                    ({'cis_rhel9_attestations': {'not_a_policy_name': True}}, 'unknown attestation'),
                    ({'cis_rhel9_attestations': {'gpg_keys_reviewed': 'true'}}, 'string "true"'),
                    ({'cis_rhel9_attestations': {'gpg_keys_reviewed': {'attested_by': 'x'}}}, 'record without attested'),
                    ({'cis_rhel9_attestations': ['gpg_keys_reviewed']}, 'a list')):
        err, sel, _ = run(stub, **kv)
        assert err, '%s accepted' % why
        assert all(v is True or v is False for v in sel['attest'].values()), 'non-boolean attestation passed through'
    err, _, _ = run(empty, cis_rhel9_profile='level2_server')
    assert err and 'could not read' in err[0], 'unreadable vocabulary not reported'
    assert run(empty)[0] == [], 'default profile without attestations needs no vocabulary'

    # the real library: four profiles and the attestation names it reads
    real = os.environ.get('CIS_RHEL9_POLICY_DIR') or os.path.join(os.path.dirname(task_file), '../../policies/benchmarks/cis/rhel_9')
    if glob.glob(os.path.join(real, '*.rego')):
        err, sel, voc = run(real, cis_rhel9_profile='level2_workstation', cis_rhel9_attestations={'gpg_keys_reviewed': True})
        assert err == [] and voc['profiles'] == ['level1_server', 'level1_workstation', 'level2_server', 'level2_workstation'], (err, voc['profiles'])
        print('profile/attest vocabulary from %s: %d profiles, %d attestation names' % (real, len(voc['profiles']), len(voc['attest'])))
    else:
        print('profile/attest vocabulary: SKIPPED the real library (no rego under %s; set CIS_RHEL9_POLICY_DIR)' % real)

    # mapper pass-through: booleans reach the input; nothing without cis_selection
    _, sel, _ = run(stub, cis_rhel9_profile='level2_server', cis_rhel9_attestations={'gpg_keys_reviewed': True})
    o = render(build, facts, {'cis_selection': sel})
    assert o['profile'] == 'level2_server' and o['attest'] == {'gpg_keys_reviewed': True} and o['attest']['gpg_keys_reviewed'] is True
    assert json.loads(json.dumps(o, default=str))['attest']['gpg_keys_reviewed'] is True, 'attestation not a JSON true'
    assert 'profile' not in render(build, facts) and 'attest' not in render(build, facts, {'cis_selection': {}}), 'selection added without cis_selection'
    print('profile/attest check: vocabulary from the policy, unknown values fail, booleans pass through')


def deb_checks(build, rhel_facts, ubuntu_fixture):
    """Debian / Ubuntu supplement (deb block, 2026-11-19): the CIS Ubuntu field
    names are emitted only from a valid deb block that reports family|deb."""
    deb_only = {'sysctl', 'sysctl_persisted', 'ufw', 'limits', 'apport', 'aide', 'pending_updates', 'apparmor'}
    # an RPM host: no deb block, or one that says family|other, changes nothing
    base = render(build, rhel_facts)
    assert not deb_only & set(base), 'Debian-only sections on the RHEL fixture: %s' % sorted(deb_only & set(base))
    other = copy.deepcopy(rhel_facts)
    other['custom_facts']['deb_raw'] = 'family|other\nend:ok\n'
    assert render(build, other) == base, 'a family|other deb block changed the RHEL input'

    facts = json.load(open(ubuntu_fixture))
    o = render(build, facts)
    assert deb_only <= set(o), 'missing Debian sections: %s' % sorted(deb_only - set(o))
    assert o['packages']['ufw'] is True and o['packages']['gdm3'] is False and o['initial_setup']['gdm_installed'] is False
    assert o['user_group']['passwd_content'].split('\n')[0] == 'root:x:0:0::/root:/bin/bash', o['user_group']['passwd_content'][:60]
    assert o['user_group']['group_content'].split('\n')[0] == 'root:x:0:' and o['user_group']['uid_min'] == 1000
    assert 'pam_unix.so' in o['pam']['common_auth'] and o['pam']['tmout_readonly'] is False and o['pam']['tmout_exported'] is False
    assert o['sysctl']['kernel.randomize_va_space'] == '2' and o['sysctl_persisted']['fs.suid_dumpable'] == 'unset'
    assert o['ssh']['config_files'][0] == {'path': '/etc/ssh/sshd_config', 'mode': '0644', 'pw_name': 'root', 'gr_name': 'root'}
    assert o['apparmor'] == {'profiles': {'loaded': 32, 'enforce': 30, 'complain': 2}, 'processes': {'unconfined': 0}}
    assert o['boot_security']['grub_cfg_linux_lines'][0].lstrip().startswith('linux')
    assert o['sudo']['default_timestamp_timeout'] == 15 and o['chronyd']['pools_configured'] == 4 and o['chronyd']['process_users'] == ['_chrony']
    assert o['user_group']['interactive_homes'] == [{'user': 'root', 'exists': True, 'owner': 'root', 'mode': '0700', 'home': '/root'}]
    assert {'user': 'root', 'mode': '0644', 'owner': 'root', 'group': 'root', 'primary_group': 'root', 'path': '/root/.bashrc'} in o['user_group']['dotfiles']
    # an absent or all-comment file is collected as a comment naming it (not met, not missing)
    assert o['limits']['limits_raw'].startswith('# ') and o['apport']['default_raw'] == '# /etc/default/apport not present'
    assert o['aide']['cron_raw'].startswith('# no aide entry') and o['aide']['aidecheck']['timer_unit_file_state'] == 'not-found'
    assert o['initial_setup']['issue_exists'] is True and 'Ubuntu' in o['initial_setup']['issue_content'] and o['initial_setup']['motd_exists'] is False
    assert [f['path'] for f in o['initial_setup']['motd_extra_files']] == ['/etc/update-motd.d/00-header', '/etc/update-motd.d/10-help-text']
    assert 'cron_yearly_mode' not in o['cron'], '/etc/cron.yearly is absent in the fixture: no mode may be reported'

    def with_deb(fn):
        f = copy.deepcopy(facts)
        f['custom_facts']['deb_raw'] = fn(f['custom_facts']['deb_raw'])
        return render(build, f)

    # no end:ok, a forged second end:ok, or a duplicated singleton: not collected
    for why, fn in (('without end:ok', lambda s: s.replace('end:ok', '')),
                    ('with a forged end:ok', lambda s: s.replace('end:ok', 'end:ok\npkg|aide|yes\nend:ok')),
                    ('with a duplicated package line', lambda s: s.replace('pkg|ufw|yes', 'pkg|ufw|no\npkg|ufw|yes')),
                    ('with a missing command', lambda s: s.replace('family|deb', 'family|deb\nmissing_cmd|systemctl'))):
        bad = with_deb(fn)
        assert not (deb_only - {'apparmor'}) & set(bad) and 'ufw' not in bad.get('packages', {}) and bad['user_group']['passwd_content'] == '', \
            'deb block %s was accepted' % why
    # a capped list is no field (evidence missing); the rest of the block stands
    t = with_deb(lambda s: s.replace('end:ok', 'truncated|dotf\ntruncated|pwd\nend:ok'))
    assert 'dotfiles' not in t['user_group'] and t['user_group']['passwd_content'] == '' and 'interactive_homes' in t['user_group'] and 'ufw' in t
    # hostile text is carried verbatim and never evaluated
    h = with_deb(lambda s: s.replace('txt|issue|', 'txt|issue|' + EVIL + ' ', 1).replace('dotf|root|0644|root|root|root|/root/.bashrc', 'dotf|root|0644|root|root|root|/root/' + EVIL))
    assert EVIL in h['initial_setup']['issue_content'] and any(d['path'] == '/root/' + EVIL for d in h['user_group']['dotfiles']), 'payload altered (deb)'
    assert EVAL_MARK not in json.dumps(h, default=str), 'TEMPLATE EVALUATED — injection (deb)'
    # the passwd password field is a class, never text: x, empty, or * for anything else
    c = with_deb(lambda s: s.replace('pwd|daemon|x|', 'pwd|daemon|other|').replace('pwd|bin|x|', 'pwd|bin|empty|'))
    rows = c['user_group']['passwd_content'].split('\n')
    assert 'daemon:*:1:1::/usr/sbin:/usr/sbin/nologin' in rows and 'bin::2:2::/bin:/usr/sbin/nologin' in rows
    # ufw not installed, and chrony neither installed nor configured, are facts
    u = with_deb(lambda s: s.replace('ufw_probe|yes', 'ufw_probe|absent').replace('pkg|chrony|yes', 'pkg|chrony|no')
                 .replace('chrony_servers|0', 'nofile|chrony_conf').replace('chrony_pools|4\n', ''))
    assert u['ufw']['status_verbose'] == '# ufw is not installed' and u['chronyd']['servers_configured'] == 0 and u['chronyd']['pools_configured'] == 0
    # a failed probe is no field
    assert 'status_verbose' not in with_deb(lambda s: s.replace('ufw_probe|yes', 'ufw_probe|failed'))['ufw']
    assert 'pending_updates' not in with_deb(lambda s: s.replace('pending_probe|yes', 'pending_probe|failed'))
    # /etc/cron.yearly present; GDM installed with its dconf keys and locks
    g = with_deb(lambda s: s.replace('absent|cron_yearly', 'cy|0700|root|root').replace('pkg|gdm3|no', 'pkg|gdm3|yes').replace(
        'end:ok', 'gdm_profile|yes\ndconf|banner-message-enable|true\ndconf|idle-delay|uint32 900\ndconf|lock-delay|uint32 5\n'
        'dconf|lock-enabled|true\ndlock|/org/gnome/desktop/session/idle-delay\ngdmconf|xdmcp_enable|true\nend:ok'))
    i = g['initial_setup']
    assert g['cron']['cron_yearly_mode'] == '0700' and g['cron']['cron_yearly_owner'] == 'root' and g['cron']['cron_yearly_group'] == 'root'
    assert i['gdm_installed'] is True and i['gdm_dconf_profile_exists'] is True and i['gdm_banner_configured'] is True and i['gdm_lock_enabled'] is True
    assert i['gdm_idle_delay'] == 900 and i['gdm_lock_delay'] == 5 and i['gdm_xdmcp_enabled'] is True and i['gdm_disable_user_list'] is False
    assert i['gdm_dconf_locks'] == ['/org/gnome/desktop/session/idle-delay']
    print('deb check: Ubuntu fields only from a valid family|deb block; RPM input unchanged; caps, probes and hostile text handled')


if __name__ == '__main__':
    main()
