> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab on OpenShift Services, AAP 2.7). Findings to check: HOST:8181x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Role: gather_auditd_facts

Gathers comprehensive auditd (Linux Audit Framework) configuration facts for CIS RHEL 9 compliance validation.

## Description

This role collects detailed information about the Linux Audit Framework configuration including:
- Auditd package installation status
- Auditd service status (enabled/running)
- Auditd configuration parameters from `/etc/audit/auditd.conf`
- Active audit rules from `auditctl -l`
- On-disk audit rules from `/etc/audit/rules.d/`
- GRUB audit configuration (audit=1, audit_backlog_limit)
- Privileged command detection for audit rule coverage
- Runtime vs on-disk configuration synchronization

## Requirements

- RHEL 9 or compatible system
- Ansible 2.9 or higher
- Root or sudo privileges

## Role Variables

Available variables are listed below, along with default values (see `defaults/main.yml`):

```yaml
# Directory where audit rules are stored
audit_rules_dir: /etc/audit/rules.d

# Main audit configuration file
auditd_conf_file: /etc/audit/auditd.conf

# Whether to check if running config matches on-disk config
check_config_sync: true

# Grub configuration file locations
grub_defaults_file: /etc/default/grub
grub_config_file: /boot/grub2/grub.cfg
```

## Dependencies

None.

## Example Playbook

```yaml
---
- name: Gather auditd facts for compliance
  hosts: all
  become: yes
  roles:
    - gather_auditd_facts

- name: Display collected auditd facts
  hosts: all
  tasks:
    - name: Show auditd configuration
      debug:
        var: host_auditd_facts
```

## Facts Generated

This role sets the following fact variable: `host_auditd_facts`

### Structure:

```yaml
host_auditd_facts:
  package_installed: true/false
  service_enabled: "enabled" | "disabled" | "unknown"
  service_running: "active" | "inactive" | "unknown"
  auditd_config:
    max_log_file: "8"
    max_log_file_action: "keep_logs"
    space_left_action: "email"
    action_mail_acct: "root"
    admin_space_left_action: "halt"
    # ... other auditd.conf parameters
  active_audit_rules:
    - "-w /etc/sudoers -p wa -k scope"
    - "-a always,exit -F arch=b64 ..."
    # ... all active rules from auditctl -l
  disk_audit_rules:
    - "# Rules from /etc/audit/rules.d/"
    - "-w /etc/sudoers -p wa -k scope"
    # ... rules from *.rules files
  audit_grub_configured: true/false
  audit_backlog_limit: 8192
  privileged_commands:
    - "/usr/bin/sudo"
    - "/usr/bin/su"
    # ... all SUID/SGID binaries
  config_synced: true/false
  rule_coverage:
    sudoers_changes: true/false
    user_emulation: true/false
    sudo_log: true/false
    time_change: true/false
    # ... coverage for all required rules
  collection_timestamp: "2025-10-15T12:34:56Z"
```

## CIS Controls Covered

This role gathers facts for the following CIS RHEL 9 Benchmark controls:

- **4.1.1.1**: Ensure auditd is installed
- **4.1.1.2**: Ensure auditd service is enabled and running
- **4.1.1.3**: Ensure auditing for processes that start prior to auditd is enabled
- **4.1.1.4**: Ensure audit_backlog_limit is sufficient
- **4.1.2.1**: Ensure audit log storage size is configured
- **4.1.2.2**: Ensure audit logs are not automatically deleted
- **4.1.2.3**: Ensure system is disabled when audit logs are full
- **4.1.3.1 - 4.1.3.20**: Various audit rules for system events
- **4.1.4.1**: Ensure the running and on disk configuration is the same

**Total: 25 controls**

## Usage with OPA

The facts collected by this role can be fed directly into OPA for policy evaluation:

```yaml
- name: Evaluate auditd compliance with OPA
  uri:
    url: "http://localhost:8181/v1/data/cis/rhel9/section_4/auditd"
    method: POST
    body_format: json
    body:
      input: "{{ host_auditd_facts }}"
    return_content: yes
  register: opa_audit_result
```

## License

Apache-2.0
## Author Information

Created for CIS RHEL 9 compliance automation.
