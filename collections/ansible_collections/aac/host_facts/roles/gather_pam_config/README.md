# gather_pam_config

Gather PAM and authselect configuration as facts for CIS RHEL evaluation.

## What it collects

Emits a single `host_pam_facts` dictionary covering the authselect profile
in use, `pwquality` settings, `faillock` configuration and the PAM stack
files the benchmark inspects.

## Requirements

RHEL 9 or a compatible EL 9 distribution. Reads system configuration, so
it needs privilege escalation.

## Example

```yaml
- hosts: all
  become: true
  roles:
    - aac.host_facts.gather_pam_config

  tasks:
    - name: Show what was collected
      ansible.builtin.debug:
        var: host_pam_facts
```

## Note

This role gathers only. It makes no judgement about whether a value is
compliant — that belongs in whatever policy engine evaluates the facts.
