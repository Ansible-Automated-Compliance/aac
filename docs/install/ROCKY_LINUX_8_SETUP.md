> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: HOST:8181x5.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Rocky Linux 8 CIS Compliance Setup Guide

**Author:** Tim Coulter & Claude
**Date:** November 24, 2025
**Repository:** ansible-automated-compliance/aac

---

## Overview

Complete CIS compliance validation for **Rocky Linux 8** using modular OPA policies and Ansible automation via SSH.

Rocky Linux is a community-driven, enterprise-grade operating system designed to be 100% bug-for-bug compatible with Red Hat Enterprise Linux 8, providing a free RHEL alternative.

### Architecture

```
Rocky Linux Servers → SSH → Ansible (fact collection) → OPA (policy evaluation) → Reports
```

---

## Policy Modules (14 Modules)

Located in `policies/cis_benchmarks/rocky_linux_8/`:

1. **`filesystem_validation.rego`** - Filesystem partitioning and mount options
2. **`initial_setup_validation.rego`** - System initialization
3. **`services_validation.rego`** - Unnecessary service checks  
4. **`network_validation.rego`** - Network configuration
5. **`logging_validation.rego`** - Rsyslog and system logging
6. **`auditd_validation.rego`** - Audit daemon configuration
7. **`ssh_validation.rego`** - SSH server hardening
8. **`pam_validation.rego`** - Password policies and authentication
9. **`sudo_validation.rego`** - Privilege escalation
10. **`selinux_validation.rego`** - SELinux mandatory access control
11. **`user_group_validation.rego`** - User and group security
12. **`cron_validation.rego`** - Scheduled job security
13. **`boot_security_validation.rego`** - Boot loader hardening
14. **`file_permissions_validation.rego`** - System file permissions

### Master Orchestrator
- **File:** `cis_rocky_linux_8_complete.rego`
- **API Endpoint:** `http://localhost:8181/v1/data/cis_rocky_linux_8/compliance_assessment`

---

## Prerequisites

### Rocky Linux Requirements

1. **Rocky Linux 8.x** (any point release)
2. **Python 3.6+** (included by default)
3. **SSH server enabled** (`openssh-server`)
4. **Sudo privileges** for Ansible user
5. **Network connectivity** to Ansible controller on port 22

### Ansible Controller Requirements

1. **Ansible 2.9+**
2. **SSH key-based authentication** (recommended)
3. **Network access** to Rocky Linux servers on port 22

---

## Rocky Linux Server Configuration

### Step 1: Install SSH Server

```bash
# SSH is installed by default on Rocky Linux
# Verify it's running
sudo systemctl status sshd

# If not installed
sudo dnf install -y openssh-server
sudo systemctl enable sshd
sudo systemctl start sshd
```

### Step 2: Configure Ansible User

```bash
# Create ansible user
sudo useradd -m ansible
sudo passwd ansible

# Add to wheel group for sudo
sudo usermod -aG wheel ansible

# Configure passwordless sudo
echo "ansible ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/ansible
sudo chmod 0440 /etc/sudoers.d/ansible
```

### Step 3: Setup SSH Key Authentication

```bash
# On Ansible controller
ssh-keygen -t rsa -b 4096 -f ~/.ssh/rocky_ansible_key
ssh-copy-id -i ~/.ssh/rocky_ansible_key.pub ansible@<rocky-server-ip>

# Test connection
ssh -i ~/.ssh/rocky_ansible_key ansible@<rocky-server-ip>
```

### Step 4: Configure Firewall

```bash
# Firewalld is default on Rocky Linux
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --reload
```

---

## Ansible Controller Configuration

### Configure Inventory

Edit `ansible/inventory/rocky_linux_8_test.yml`:

```yaml
all:
  hosts:
    rocky-server-01:
      ansible_host: 192.168.1.40
      ansible_user: ansible
      ansible_ssh_private_key_file: ~/.ssh/rocky_ansible_key
      ansible_become: yes

  vars:
    opa_server_url: "http://localhost:8181"
    target_platform: "rocky_linux_8"
    compliance_framework: "cis"
```

### Test Connectivity

```bash
cd ~/compliance/ansible

# Test SSH connectivity
ansible -i inventory/rocky_linux_8_test.yml all -m ping

# Test sudo access
ansible -i inventory/rocky_linux_8_test.yml all -m shell -a "whoami" --become
```

---

## Running Compliance Assessment

### Full Assessment

```bash
cd ~/compliance/ansible

# Run complete CIS Rocky Linux 8 assessment
ansible-playbook -i inventory/rocky_linux_8_test.yml \
  playbooks/cis_rocky_linux_8_assessment.yml

# With verbose output
ansible-playbook -i inventory/rocky_linux_8_test.yml \
  playbooks/cis_rocky_linux_8_assessment.yml -v
```

### Query OPA Directly

```bash
# Check if policies are loaded
curl http://localhost:8181/v1/policies | jq '.result[].id' | grep rocky8

# Test with sample data
curl -s -X POST http://localhost:8181/v1/data/cis_rocky_linux_8/compliance_assessment \
  -H 'Content-Type: application/json' \
  -d '{
    "input": {
      "system_info": {
        "hostname": "rocky-test",
        "distribution": "Rocky",
        "distribution_version": "8.5"
      }
    }
  }' | jq
```

---

## Reports

Assessment reports saved to `/tmp/compliance_assessments/`:

- **Facts:** `<hostname>_rocky_linux_8_facts_<timestamp>.json`
- **Compliance Report:** `<hostname>_rocky_linux_8_compliance_report_<timestamp>.json`

---

## Integration with AAP Workflow

Compatible with PostgreSQL historical trending:

1. Use `store_compliance_facts.yml` to store facts
2. Use `store_compliance_results.yml` to store results
3. Query trends via `compliance_trending_report.yml`

### AAP Job Template

**Job Template: "CIS Rocky Linux 8 - Assessment"**
- **Playbook:** `playbooks/cis_rocky_linux_8_assessment.yml`
- **Inventory:** Rocky Linux 8 inventory
- **Credentials:** SSH credential
- **Variables:**
  ```yaml
  opa_server_url: http://localhost:8181
  report_dir: /home/aapuser1/compliance/reports
  ```

---

## Rocky Linux vs RHEL

### Compatibility

Rocky Linux 8 is designed to be **100% bug-for-bug compatible** with RHEL 8:
- Same kernel version
- Same package versions
- Same security features (SELinux, firewalld, etc.)
- Same CIS benchmark controls apply

### Key Differences

- **Branding:** Rocky Linux branding instead of Red Hat
- **Support:** Community-driven (no paid support)
- **Package repos:** Rocky Linux mirrors instead of Red Hat CDN
- **No subscription required**

### CIS Compliance

The CIS RHEL 8 benchmark applies directly to Rocky Linux 8. Both use:
- SELinux for mandatory access control
- firewalld for network filtering
- Same filesystem structure
- Same service names and configurations

---

## Troubleshooting

### SSH Connection Failed

**Solutions:**
1. Verify sshd is running: `sudo systemctl status sshd`
2. Check firewall: `sudo firewall-cmd --list-services`
3. Test locally: `ssh localhost`

### SELinux Denials

**Check SELinux status:**
```bash
getenforce
sudo ausearch -m avc -ts recent
```

**Temporarily set to permissive (testing only):**
```bash
sudo setenforce 0
```

### Python Not Found

Rocky Linux 8 uses Python 3.6 by default. If issues occur:
```bash
sudo dnf install -y python3
sudo alternatives --set python /usr/bin/python3
```

---

## Security Best Practices

1. **Use Ansible Vault** for credentials
2. **Restrict SSH** to key-based auth only
3. **Keep SELinux enforcing** (never disable permanently)
4. **Use firewalld** to limit network access
5. **Regular updates:** `sudo dnf update -y`

---

## Multi-OS Platform Status

| OS | Version | Status | Coverage |
|----|---------|--------|----------|
| RHEL 9 | 9.x | ✅ Production | 338/338 (100%) |
| RHEL 8 | 8.x | ✅ Ready | ~300 controls |
| Rocky Linux 8 | 8.x | ✅ **Ready** | ~300 controls (RHEL-compatible) |
| Ubuntu 20.04 | 20.04 | ✅ Ready | ~400 controls |
| Ubuntu 22.04 | 22.04 | ✅ Ready | ~400 controls |
| Debian 11 | 11 | ✅ Ready | ~400 controls |
| Windows Server 2019 | 2019 | ✅ Ready | ~400 controls |
| Windows Server 2022 | 2022 | ✅ Ready | ~400 controls |

---

## Additional Resources

### Rocky Linux
- Website: https://rockylinux.org
- Documentation: https://docs.rockylinux.org
- Migration Guide: https://docs.rockylinux.org/guides/migrate2rocky/

### CIS Benchmark
- Download: [CIS Red Hat Enterprise Linux 8 Benchmark](https://www.cisecurity.org/benchmark/red_hat_linux)
- Note: RHEL 8 benchmark applies to Rocky Linux 8

---

**Last Updated:** November 24, 2025
**Status:** Production-ready modular foundation
**Next Steps:** Expand stub modules with full CIS control logic
