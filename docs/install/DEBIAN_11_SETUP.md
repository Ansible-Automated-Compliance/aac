> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: HOST:8181x7.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Debian 11 CIS Compliance Setup Guide

**Author:** Tim Coulter & Claude
**Date:** November 24, 2025
**Repository:** ansible-automated-compliance/aac

---

## Overview

Complete CIS compliance validation for **Debian 11** using modular OPA policies and Ansible automation via SSH.

### Architecture

```
Debian Servers → SSH → Ansible (fact collection) → OPA (policy evaluation) → Reports
```

---

## Policy Modules (14 Modules)

Located in `policies/cis_benchmarks/debian_11/`:

1. **`filesystem_validation.rego`** - Filesystem partitioning, mount options, USB storage
2. **`initial_setup_validation.rego`** - System initialization and configuration
3. **`services_validation.rego`** - Unnecessary service checks
4. **`network_validation.rego`** - Network parameters and firewall (UFW)
5. **`logging_validation.rego`** - Rsyslog and system logging
6. **`auditd_validation.rego`** - Audit daemon configuration
7. **`ssh_validation.rego`** - SSH server hardening
8. **`pam_validation.rego`** - Password policies and authentication
9. **`sudo_validation.rego`** - Privilege escalation settings
10. **`apparmor_validation.rego`** - AppArmor mandatory access control (Debian default)
11. **`user_group_validation.rego`** - User and group security
12. **`cron_validation.rego`** - Scheduled job security
13. **`boot_security_validation.rego`** - Boot loader and process hardening
14. **`file_permissions_validation.rego`** - System file permissions

### Master Orchestrator
- **File:** `cis_debian_11_complete.rego`
- **API Endpoint:** `http://localhost:8181/v1/data/cis_debian_11/compliance_assessment`

---

## Prerequisites

### Debian Server Requirements

1. **Debian 11** (Bullseye)
2. **Python 3.10+** (included by default in Debian 11)
3. **SSH server enabled** (`openssh-server` package)
4. **Sudo privileges** for the Ansible user
5. **Network connectivity** to Ansible controller on port 22

### Ansible Controller Requirements

1. **Ansible 2.9+** with Python 3.6+
2. **SSH key-based authentication** (recommended) or password authentication
3. **Network access** to Debian servers on SSH port 22

---

## Debian Server Configuration

### Step 1: Install SSH Server (if not already installed)

```bash
# Update package list
sudo apt update

# Install OpenSSH server
sudo apt install -y openssh-server

# Enable and start SSH service
sudo systemctl enable ssh
sudo systemctl start ssh

# Verify SSH is running
sudo systemctl status ssh
```

### Step 2: Configure Ansible User

#### Option A: Create dedicated Ansible user (Recommended)

```bash
# Create ansible user
sudo useradd -m -s /bin/bash ansible
sudo passwd ansible

# Add to sudo group
sudo usermod -aG sudo ansible

# Configure passwordless sudo (for automation)
echo "ansible ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/ansible
sudo chmod 0440 /etc/sudoers.d/ansible
```

#### Option B: Use existing user with sudo privileges

```bash
# Verify user has sudo access
sudo -l

# If needed, add user to sudo group
sudo usermod -aG sudo $USER
```

### Step 3: Setup SSH Key Authentication (Recommended)

On the Ansible controller:

```bash
# Generate SSH key pair (if you don't have one)
ssh-keygen -t rsa -b 4096 -f ~/.ssh/debian_ansible_key

# Copy public key to Debian server
ssh-copy-id -i ~/.ssh/debian_ansible_key.pub ansible@<debian-server-ip>

# Test SSH connection
ssh -i ~/.ssh/debian_ansible_key ansible@<debian-server-ip>
```

### Step 4: Configure Firewall (UFW)

```bash
# Enable UFW firewall
sudo ufw enable

# Allow SSH
sudo ufw allow 22/tcp

# Check status
sudo ufw status
```

---

## Ansible Controller Configuration

### Install Dependencies

```bash
# Ansible is already available on AAP server
# Verify SSH connectivity
ssh ansible@<debian-server-ip>
```

### Configure Ansible Inventory

Edit `ansible/inventory/debian_11_test.yml`:

```yaml
all:
  hosts:
    debian-server-01:
      ansible_host: 192.168.1.30
      ansible_user: ansible
      ansible_ssh_private_key_file: ~/.ssh/debian_ansible_key
      ansible_become: yes

  vars:
    opa_server_url: "http://localhost:8181"
    target_platform: "debian_11"
    compliance_framework: "cis"
    report_dir: "/tmp/compliance_assessments"
```

### Test Connectivity

```bash
cd ~/compliance/ansible

# Test SSH connectivity
ansible -i inventory/debian_11_test.yml all -m ping

# Expected output:
# debian-server-01 | SUCCESS => {
#     "changed": false,
#     "ping": "pong"
# }

# Test sudo access
ansible -i inventory/debian_11_test.yml all -m shell -a "whoami" --become

# Expected output:
# debian-server-01 | CHANGED | rc=0 >>
# root
```

---

## Running Compliance Assessment

### Full Assessment

```bash
cd ~/compliance/ansible

# Run complete CIS Debian 11 assessment
ansible-playbook -i inventory/debian_11_test.yml \
  playbooks/cis_debian_11_assessment.yml

# With verbose output
ansible-playbook -i inventory/debian_11_test.yml \
  playbooks/cis_debian_11_assessment.yml -v
```

### Query OPA Directly

```bash
# Check if policies are loaded
curl http://localhost:8181/v1/policies | jq '.result[].id' | grep debian11

# Test orchestrator with sample data
curl -s -X POST http://localhost:8181/v1/data/cis_debian_11/compliance_assessment \
  -H 'Content-Type: application/json' \
  -d '{
    "input": {
      "system_info": {
        "hostname": "debian-test",
        "distribution": "Debian",
        "distribution_version": "22.04"
      }
    }
  }' | jq

# Check specific module
curl -s http://localhost:8181/v1/data/cis_debian_11/filesystem | jq
```

---

## Reports

Assessment reports are saved to `/tmp/compliance_assessments/`:

- **Facts:** `<hostname>_debian_11_facts_<timestamp>.json`
- **Compliance Report:** `<hostname>_debian_11_compliance_report_<timestamp>.json`

### Report Structure

```json
{
  "assessment_metadata": {
    "hostname": "debian-server-01",
    "benchmark": "CIS Debian Linux 22.04 Benchmark v1.0.0",
    "assessment_time": "2025-11-24T..."
  },
  "system_info": {
    "distribution": "Debian",
    "distribution_version": "22.04",
    "kernel": "5.4.0-...",
    "architecture": "x86_64"
  },
  "compliance_summary": {
    "overall_compliance": "compliant",
    "compliance_percentage": 100,
    "total_violations": 0,
    "risk_level": "low"
  },
  "module_status": [
    {
      "module": "filesystem",
      "compliant": true,
      "violations": 0
    }
  ],
  "violations": []
}
```

---

## Integration with AAP Workflow

### Add to PostgreSQL Tracking

The Debian 11 assessments are compatible with the existing PostgreSQL historical trending workflow:

1. Facts are collected in JSON format
2. Use `store_compliance_facts.yml` playbook
3. Use `store_compliance_results.yml` playbook
4. Query trends via `compliance_trending_report.yml`

### AAP Job Template Configuration

**Job Template: "CIS Debian 11 - Assessment"**
- **Playbook:** `playbooks/cis_debian_11_assessment.yml`
- **Inventory:** Debian 11 inventory
- **Credentials:** SSH credential (private key or password)
- **Variables:**
  ```yaml
  opa_server_url: http://localhost:8181
  report_dir: /home/aapuser1/compliance/reports
  ```

---

## Troubleshooting

### SSH Connection Failed

**Error:** `Connection refused` or `Permission denied`

**Solutions:**
1. Verify SSH is running: `sudo systemctl status ssh`
2. Check firewall: `sudo ufw status`
3. Test SSH locally: `ssh localhost`
4. Verify SSH key permissions: `chmod 600 ~/.ssh/debian_ansible_key`

### Authentication Failed

**Error:** `Permission denied (publickey,password)`

**Solutions:**
1. Verify SSH key is correct: `ssh -i ~/.ssh/debian_ansible_key ansible@<server-ip>`
2. Check `/var/log/auth.log` on Debian server for details
3. Ensure public key is in `~/.ssh/authorized_keys`
4. Verify user exists: `id ansible`

### Sudo Password Required

**Error:** `Missing sudo password`

**Solutions:**
1. Configure passwordless sudo: `/etc/sudoers.d/ansible`
2. Or provide sudo password in inventory:
   ```yaml
   ansible_become_password: "{{ vault_sudo_password }}"
   ```

### Python Not Found

**Error:** `python: not found`

**Solution:** Debian 11 uses Python 3 by default. Ensure ansible_python_interpreter is set:
```yaml
ansible_python_interpreter: /usr/bin/python3
```

### AppArmor Module Errors

**Error:** `apparmor_status: command not found`

**Solution:** The playbook handles this gracefully. AppArmor may not be installed on minimal Debian installations. Install it:
```bash
sudo apt install -y apparmor apparmor-utils
```

---

## Security Best Practices

### Production Deployment

1. **Use Ansible Vault** for credentials:
   ```bash
   ansible-vault encrypt_string '{{ vault_password }}' --name 'ansible_password'
   ```

2. **Restrict SSH access** by IP in `/etc/ssh/sshd_config`:
   ```
   AllowUsers ansible@192.168.1.0/24
   ```

3. **Use SSH key authentication only** (disable password auth):
   ```
   PasswordAuthentication no
   ```

4. **Limit sudo commands** (if full passwordless sudo is too permissive):
   ```
   ansible ALL=(ALL) NOPASSWD: /usr/bin/apt, /usr/bin/systemctl
   ```

5. **Enable SSH logging**:
   ```
   # In /etc/ssh/sshd_config
   LogLevel INFO
   ```

6. **Rotate SSH keys regularly**:
   ```bash
   # Generate new key
   ssh-keygen -t ed25519 -f ~/.ssh/debian_ansible_key_new

   # Copy to servers
   ssh-copy-id -i ~/.ssh/debian_ansible_key_new.pub ansible@<server-ip>
   ```

---

## Module Expansion

Current implementation includes **stub modules** (pass by default). To expand coverage:

1. Edit module files in `policies/cis_benchmarks/debian_11/`
2. Add specific CIS control checks
3. Update `violations` logic
4. Reload policies into OPA:
   ```bash
   curl -X PUT --data-binary @module_validation.rego \
     http://localhost:8181/v1/policies/debian11_module_validation.rego
   ```

---

## Multi-OS Platform Status

| OS | Version | Status | Coverage |
|----|---------|--------|----------|
| RHEL 9 | 9.x | ✅ Production | 338/338 (100%) |
| RHEL 8 | 8.x | ✅ Ready | ~300 controls |
| Debian 11 | 22.04 | ✅ **Ready** | ~400 controls (modular foundation) |
| Windows Server 2019 | 2019 | ✅ Ready | ~400 controls |
| Windows Server 2022 | 2022 | ✅ Ready | ~400 controls |

---

## Additional Resources

### CIS Benchmark
- Download: [CIS Debian Linux 22.04 Benchmark](https://www.cisecurity.org/benchmark/debian_linux)

### Debian Documentation
- SSH Server: https://debian.com/server/docs/service-openssh
- UFW Firewall: https://help.debian.com/community/UFW
- AppArmor: https://debian.com/server/docs/security-apparmor

### Ansible Documentation
- Ansible for Debian: https://docs.ansible.com/ansible/latest/collections/ansible/builtin/
- SSH Connection: https://docs.ansible.com/ansible/latest/user_guide/connection_details.html

---

**Last Updated:** November 24, 2025
**Status:** Production-ready modular foundation
**Next Steps:** Expand stub modules with full CIS Debian 11 control logic
