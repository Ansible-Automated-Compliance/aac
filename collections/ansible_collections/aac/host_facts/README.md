# aac.host_facts

Collect host configuration state as structured facts for policy evaluation.
CIS Benchmarks, DISA STIGs and NERC CIP all consume the same facts, which is why
the collection and its keys are named for the host, not for one framework.

> **Source of truth.** This collection is the only copy of the eleven gatherer
> roles. The legacy `ansible/roles/gather_*` copies were removed on 2026-10-17
> after their two task-logic fixes (octal mode handling in
> `gather_filesystem_config` and `gather_logging_config`) were ported here.
> Renamed from `aac.cis_facts` 1.0.0 (keys `cis_<area>_facts`) to
> `aac.host_facts` 2.0.0 (keys `host_<area>_facts`) at the same time, while the
> collection still had no runtime consumer and the rename was free.

## What this is

Eleven roles that gather the areas a CIS RHEL assessment inspects and
emit each as a single, predictable dictionary:

| Role | Fact | Covers |
|---|---|---|
| `gather_ssh_config` | `host_ssh_facts` | sshd config, ciphers, KEX, MACs |
| `gather_auditd_facts` | `host_auditd_facts` | auditd config, rule coverage |
| `gather_pam_config` | `host_pam_facts` | authselect, pwquality, faillock |
| `gather_filesystem_config` | `host_filesystem_facts` | mount options, kernel modules |
| `gather_file_permissions` | `host_file_permissions_facts` | ownership and modes on audited paths |
| `gather_firewalld_detailed` | `host_firewalld_facts` | zones, services, rich rules |
| `gather_grub_security` | `host_grub_facts` | bootloader password, permissions |
| `gather_logging_config` | `host_logging_facts` | rsyslog, journald |
| `gather_network_config` | `host_network_facts` | sysctl, interfaces, protocols |
| `gather_service_config` | `host_service_facts` | enabled and running services |
| `gather_user_security` | `host_user_security_facts` | accounts, password ageing, sudo |

## What this deliberately is not

**These roles gather. They do not judge.**

There is no policy logic here and no opinion about what a compliant value
looks like — no thresholds, no pass/fail, no benchmark version baked in.
That separation is the point:

- the same facts can be evaluated by Open Policy Agent, by a different
  policy engine, or by your own `assert` tasks
- a benchmark revision changes the policy, not the collection
- the facts are useful for drift detection and inventory even if you are
  not running a benchmark at all

If you want the evaluation half as well, the CIS Rego policies these were
built alongside are published separately at
[rego_policy_libraries](https://github.com/ynotbhatc/rego_policy_libraries).

## Requirements

- RHEL 9 or a compatible EL 9 distribution. The roles use `rpm` and
  `authselect`, so they are RHEL-family only — they will not work on
  Debian or SUSE.
- Privilege escalation. Much of what CIS inspects is not world-readable.

## Usage

Run everything:

```yaml
- hosts: all
  become: true
  roles:
    - aac.host_facts.gather_ssh_config
    - aac.host_facts.gather_auditd_facts
    - aac.host_facts.gather_pam_config
    - aac.host_facts.gather_filesystem_config
    - aac.host_facts.gather_file_permissions
    - aac.host_facts.gather_firewalld_detailed
    - aac.host_facts.gather_grub_security
    - aac.host_facts.gather_logging_config
    - aac.host_facts.gather_network_config
    - aac.host_facts.gather_service_config
    - aac.host_facts.gather_user_security
```

Or one area, which is often all you want:

```yaml
- hosts: all
  become: true
  roles:
    - aac.host_facts.gather_ssh_config

  tasks:
    - name: Evaluate with your own policy engine
      ansible.builtin.uri:
        url: "{{ opa_url }}/v1/data/cis_rhel9/ssh/compliance_report"
        method: POST
        body_format: json
        body:
          input: "{{ host_ssh_facts }}"
```

## Relationship to CIS

This collection is not affiliated with or endorsed by the Center for
Internet Security. It collects operating-system configuration state; the
CIS Benchmarks are published by CIS and are subject to their terms of
use. No benchmark text is reproduced here.

## Licence

Apache-2.0.
