> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab on OpenShift Services, AAP 2.7). Findings to check: none specific — unreviewed for 320 days.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Role: gather_ssh_config

Gathers comprehensive SSH server configuration facts for CIS RHEL 9 compliance validation.

## Description

This role collects detailed SSH configuration information including:
- SSH package installation status
- SSH service status (enabled/running)
- Complete sshd_config parameter parsing
- SSH host key file permissions (public and private)
- Cipher suite analysis (weak vs strong)
- MAC algorithm analysis
- Key exchange algorithm analysis
- Security-critical settings validation

## Requirements

- RHEL 9 or compatible system
- Ansible 2.9 or higher
- Root or sudo privileges

## Role Variables

See `defaults/main.yml` for configurable weak/strong algorithm lists.

## CIS Controls Covered

This role gathers facts for the following CIS RHEL 9 Benchmark controls:

- **5.2.1**: Ensure permissions on /etc/ssh/sshd_config are configured
- **5.2.2**: Ensure permissions on SSH private host key files are configured
- **5.2.3**: Ensure permissions on SSH public host key files are configured
- **5.2.4**: Ensure SSH access is limited
- **5.2.5**: Ensure SSH LogLevel is appropriate
- **5.2.6**: Ensure SSH PAM is enabled
- **5.2.7**: Ensure SSH root login is disabled
- **5.2.8**: Ensure SSH HostbasedAuthentication is disabled
- **5.2.9**: Ensure SSH PermitEmptyPasswords is disabled
- **5.2.10**: Ensure SSH PermitUserEnvironment is disabled
- **5.2.11**: Ensure SSH IgnoreRhosts is enabled
- **5.2.12**: Ensure SSH X11 forwarding is disabled
- **5.2.13**: Ensure only strong Ciphers are used
- **5.2.14**: Ensure only strong MAC algorithms are used
- **5.2.15**: Ensure only strong Key Exchange algorithms are used
- **5.2.16**: Ensure SSH Idle Timeout Interval is configured
- **5.2.17**: Ensure SSH LoginGraceTime is set to one minute or less
- **5.2.18**: Ensure SSH warning banner is configured
- **5.2.19**: Ensure SSH MaxAuthTries is set to 4 or less
- **5.2.20**: Ensure SSH MaxStartups is configured
- **5.2.21**: Ensure SSH MaxSessions is limited

**Total: 21 controls**

## Example Playbook

```yaml
---
- name: Gather SSH configuration facts
  hosts: all
  become: yes
  roles:
    - gather_ssh_config

- name: Display SSH security status
  hosts: all
  tasks:
    - name: Show weak algorithms
      debug:
        msg:
          - "Weak ciphers found: {{ host_ssh_facts.ciphers.weak_found }}"
          - "Weak MACs found: {{ host_ssh_facts.macs.weak_found }}"
          - "Weak KEX found: {{ host_ssh_facts.kex_algorithms.weak_found }}"
```

## Facts Generated

This role sets the `host_ssh_facts` variable with comprehensive SSH configuration data.

## License

Apache-2.0
## Author Information

Created for CIS RHEL 9 compliance automation.
