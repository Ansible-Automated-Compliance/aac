> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: none specific — unreviewed for 320 days.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

> [!NOTE]
> **2026-10-17:** the legacy `ansible/roles/gather_*` roles this document describes were removed
> from the tree (no playbook called them). The same roles live in the `aac.cis_facts` collection
> at `collections/ansible_collections/aac/cis_facts/roles/`; the production CIS path uses
> `ansible/roles/aac_facts_collector` and `ansible/playbooks/cis_rhel9_assessment.yml`.

# CIS Benchmark Validation - Technical Components Required

**Authors:** Tim Coulter & Claude
**Date:** October 15, 2025


## Executive Summary

This document outlines all technical components required to build a complete CIS RHEL 9 Benchmark validation system. The existing OPA policy (`policies/cis_benchmarks/rhel_9/cis_rhel_9.rego`) defines **278 controls** across **6 major sections**. Our current fact collection covers the basic data gathering, but significant work remains to parse, structure, and validate this data against each control.

## Current State

### ✓ Completed Components

1. **Facts Repository Structure** - `facts-repo/`
2. **Basic Fact Collection Playbook** - Gathers raw data for 9 CIS sections
3. **Coverage Validation Playbook** - Identifies data collection gaps
4. **OPA Integration Framework** - Basic connectivity and policy loading
5. **Compliance Report Generator** - Initial reporting structure

### Coverage: 9/278 controls (~3%)

---

## Components to Build

### 1. Enhanced Fact Collection Modules

The existing policy expects **structured data** that standard Ansible facts don't provide. We need custom fact gathering for:

#### 1.1 Filesystem & Mount Options (CIS 1.1.x - 38 controls)
**Required Facts:**
- `ansible_modprobe_config` - Disabled filesystem types (squashfs, udf, usb-storage)
- `ansible_mounts` - Enhanced with partition security options
- `world_writable_files` - Find all world-writable directories
- Sticky bit validation on world-writable directories
- Removable media mount detection (/media, /mnt)

**Custom Module Needed:**
```yaml
# Example: gather_modprobe_config.py
# Parses /etc/modprobe.d/* for disabled filesystems
# Output: { "filesystem": "squashfs", "state": "disabled" }
```

**Priority:** HIGH
**Effort:** 2-3 days
**Controls Covered:** 14

#### 1.2 Package & Software Management (CIS 1.2.x, 1.3.x - 4 controls)
**Required Facts:**
- `rhsm_configured` - Red Hat Subscription Manager status
- `aide_cron_configured` - AIDE scheduled scans
- `ansible_packages` - Already provided by Ansible
- Security updates available

**Custom Module Needed:**
```python
# gather_rhsm_status.py
# Checks: subscription-manager status
# Output: { "rhsm_configured": true/false }
```

**Priority:** MEDIUM
**Effort:** 1 day
**Controls Covered:** 4

#### 1.3 Bootloader Security (CIS 1.4.x - 3 controls)
**Required Facts:**
- `grub_password_set` - GRUB password configuration
- `grub_config` - File permissions (owner, group, mode)
- `single_user_auth_required` - Single-user mode protection
- `selinux_disabled_in_grub` - SELinux grub configuration

**Custom Module Needed:**
```python
# gather_grub_security.py
# Checks: /boot/grub2/grub.cfg password, permissions
# Checks: /etc/default/grub for SELinux settings
# Output: { "grub_password_set": bool, "grub_config": {...} }
```

**Priority:** HIGH
**Effort:** 2 days
**Controls Covered:** 3

#### 1.4 Core Dumps & ASLR (CIS 1.5.x - 2 controls)
**Required Facts:**
- `ansible_sysctl` - Already provided
- `security_limits` - /etc/security/limits.conf parsing

**Custom Module Needed:**
```python
# gather_security_limits.py
# Parses: /etc/security/limits.conf
# Output: [{ "domain": "*", "limit_type": "hard", "limit_item": "core", "value": "0" }]
```

**Priority:** MEDIUM
**Effort:** 1 day
**Controls Covered:** 2

#### 1.5 SELinux Advanced (CIS 1.6.x - 8 controls)
**Required Facts:**
- `ansible_selinux` - Basic SELinux status (✓ have this)
- `selinux_unconfined_services` - Services running unconfined
- Package checks for setroubleshoot, mcstrans

**Custom Module Needed:**
```python
# gather_selinux_advanced.py
# Checks: ps -eZ | grep unconfined
# Output: [{ "service": "name", "unconfined": true }]
```

**Priority:** MEDIUM
**Effort:** 1-2 days
**Controls Covered:** 8

#### 1.6 Warning Banners (CIS 1.7.x - 6 controls)
**Required Facts:**
- `motd_configured` - /etc/motd content validation
- `issue_configured` - /etc/issue content validation
- `issue_net_configured` - /etc/issue.net content validation
- `file_permissions` - Permissions on banner files

**Custom Module Needed:**
```python
# gather_banner_config.py
# Validates: /etc/motd, /etc/issue, /etc/issue.net
# Checks: No OS info disclosed, proper permissions
# Output: { "motd_configured": bool, "file_permissions": {...} }
```

**Priority:** LOW
**Effort:** 1 day
**Controls Covered:** 6

#### 1.7 GNOME Display Manager (CIS 1.8.x - 10 controls)
**Required Facts:**
- `gdm_banner_configured` - GDM login banner
- `gdm_disable_user_list` - User list disabled
- `gdm_screen_lock_enabled` - Screen lock settings
- `gdm_automount_enabled` - Removable media automount
- `gdm_xdmcp_enabled` - XDCMP status

**Custom Module Needed:**
```python
# gather_gdm_config.py
# Checks: /etc/dconf/db/gdm.d/*
# Output: { "gdm_banner_configured": bool, ... }
```

**Priority:** LOW (if GDM not used)
**Effort:** 2 days
**Controls Covered:** 10

#### 1.8 Software Updates (CIS 1.9 - 1 control)
**Required Facts:**
- `security_updates` - Available security updates

**Custom Module Needed:**
```python
# gather_security_updates.py
# Checks: yum list updates --security
# Output: [{ "package": "name", "version": "x.y.z" }]
```

**Priority:** HIGH
**Effort:** 0.5 day
**Controls Covered:** 1

---

### 2. Network Configuration Facts (CIS 3.x - 21 controls)

#### 2.1 sysctl Parameters (15 controls)
**Required Facts:**
- `ansible_sysctl` - Kernel parameters (✓ partially have this)

**Enhancement Needed:**
```yaml
# Ensure collection of:
# - net.ipv4.conf.all.send_redirects
# - net.ipv4.ip_forward
# - net.ipv4.conf.all.accept_source_route
# - net.ipv4.conf.all.accept_redirects
# - net.ipv4.conf.all.log_martians
# - net.ipv4.icmp_echo_ignore_broadcasts
# - net.ipv4.tcp_syncookies
# - net.ipv6.conf.all.accept_ra
# ... (all network sysctl params)
```

**Priority:** HIGH
**Effort:** 1 day
**Controls Covered:** 15

#### 2.2 Firewall Configuration (6 controls)
**Required Facts:**
- `firewalld_config` - Zones, interfaces, services
- Service status (enabled/running)

**Custom Module Needed:**
```python
# gather_firewalld_detailed.py
# Checks: firewall-cmd --list-all-zones
# Output: {
#   "default_zone": "public",
#   "zones": [{ "name": "public", "interfaces": [...], "services": [...] }]
# }
```

**Priority:** HIGH
**Effort:** 1-2 days
**Controls Covered:** 6

---

### 3. Logging & Auditing Facts (CIS 4.x - 42 controls)

#### 3.1 Auditd Configuration (25 controls)
**Required Facts:**
- `auditd_config` - /etc/audit/auditd.conf settings
- `audit_rules` - All active audit rules
- `audit_grub_configured` - Audit enabled in GRUB
- `auditd_config_synced` - Runtime vs on-disk config

**Custom Module Needed:**
```python
# gather_auditd_detailed.py
# Parses: /etc/audit/auditd.conf
# Parses: /etc/audit/rules.d/*.rules
# Checks: auditctl -l
# Checks: grubby --info=ALL | grep audit
# Output: {
#   "auditd_config": { "max_log_file": "8", ... },
#   "audit_rules": ["rule1", "rule2", ...],
#   "audit_grub_configured": bool
# }
```

**Priority:** HIGH
**Effort:** 3-4 days
**Controls Covered:** 25

#### 3.2 Rsyslog & Journald (9 controls)
**Required Facts:**
- `rsyslog_config` - /etc/rsyslog.conf settings
- `journald_config` - /etc/systemd/journald.conf
- `rsyslog_logging_configured` - Logging rules present
- `rsyslog_remote_configured` - Remote logging setup
- `log_files` - All log file permissions

**Custom Module Needed:**
```python
# gather_logging_config.py
# Parses: /etc/rsyslog.conf, /etc/rsyslog.d/*
# Parses: /etc/systemd/journald.conf
# Checks: find /var/log -type f
# Output: {
#   "rsyslog_config": { "FileCreateMode": "0640" },
#   "journald_config": { "ForwardToSyslog": "yes", "Compress": "yes" },
#   "log_files": [{ "path": "/var/log/messages", "mode": "600" }]
# }
```

**Priority:** HIGH
**Effort:** 2-3 days
**Controls Covered:** 9

---

### 4. Access Control & Authentication (CIS 5.x - 65 controls)

#### 4.1 Cron Security (9 controls)
**Required Facts:**
- `file_permissions` - /etc/crontab, /etc/cron.*, /etc/cron.d permissions
- Cron access files (/etc/cron.allow, /etc/cron.deny)

**Custom Module Needed:**
```python
# gather_cron_security.py
# Checks: stat /etc/crontab /etc/cron.* /etc/cron.d
# Checks: /etc/cron.allow, /etc/cron.deny existence
# Output: { "file_permissions": {...} }
```

**Priority:** MEDIUM
**Effort:** 1 day
**Controls Covered:** 9

#### 4.2 SSH Configuration (21 controls)
**Required Facts:**
- `ssh_config` - Parsed /etc/ssh/sshd_config
- `ssh_host_keys` - SSH key file permissions
- Cipher, MAC, KexAlgorithm validation

**Custom Module Needed:**
```python
# gather_ssh_config.py
# Parses: /etc/ssh/sshd_config
# Checks: /etc/ssh/ssh_host_*_key* permissions
# Output: {
#   "ssh_config": {
#     "PermitRootLogin": "no",
#     "LogLevel": "INFO",
#     "Ciphers": ["aes256-gcm@openssh.com", ...],
#     "MACs": ["hmac-sha2-512-etm@openssh.com", ...],
#     "KexAlgorithms": ["curve25519-sha256", ...]
#   },
#   "ssh_host_keys": [{ "path": "/etc/ssh/ssh_host_rsa_key", "private": true, ... }]
# }
```

**Priority:** HIGH
**Effort:** 2-3 days
**Controls Covered:** 21

#### 4.3 PAM Configuration (8 controls)
**Required Facts:**
- `pam_config` - Parsed PAM configuration
- `authselect_config` - Authselect profile and features
- `authselect_custom_profile` - Custom profile existence

**Custom Module Needed:**
```python
# gather_pam_config.py
# Parses: /etc/pam.d/password-auth, /etc/pam.d/system-auth
# Checks: authselect current
# Checks: /etc/security/faillock.conf, /etc/security/pwquality.conf
# Output: {
#   "pam_config": {
#     "faillock": { "deny": 5, "unlock_time": 900 },
#     "pwquality": { "minlen": 14, "minclass": 4 },
#     "pwhistory": { "remember": 5 },
#     "password_hash": "sha512"
#   },
#   "authselect_config": { "profile": "custom", "features": ["with-faillock"] }
# }
```

**Priority:** HIGH
**Effort:** 3-4 days
**Controls Covered:** 8

#### 4.4 Password Policy (8 controls)
**Required Facts:**
- `login_defs` - /etc/login.defs settings
- `useradd_defaults` - /etc/default/useradd
- `pwquality_config` - /etc/security/pwquality.conf

**Custom Module Needed:**
```python
# gather_password_policy.py
# Parses: /etc/login.defs
# Parses: /etc/default/useradd
# Parses: /etc/security/pwquality.conf
# Output: {
#   "login_defs": { "PASS_MIN_DAYS": 1, "PASS_MAX_DAYS": 365, "PASS_WARN_AGE": 7 },
#   "useradd_defaults": { "INACTIVE": 30 },
#   "pwquality_config": { "minlen": 14, "dcredit": -1, ... }
# }
```

**Priority:** HIGH
**Effort:** 2 days
**Controls Covered:** 8

#### 4.5 User Account Security (10 controls)
**Required Facts:**
- `users` - Enhanced user data with password ages
- `interactive_users` - Non-system users
- `current_date` - For password expiration checks
- `default_umask` - System default umask
- `shell_timeout` - TMOUT setting
- `root_login_restricted` - /etc/securetty configuration
- `su_restricted` - PAM wheel group restriction

**Custom Module Needed:**
```python
# gather_user_security.py
# Parses: /etc/passwd, /etc/shadow
# Checks: chage -l for each user
# Checks: /etc/profile, /etc/bashrc for TMOUT
# Checks: /etc/securetty
# Checks: /etc/pam.d/su for pam_wheel
# Output: {
#   "users": [{ "name": "user1", "uid": 1000, "shell": "/bin/bash", "password_last_changed": "2024-01-01" }],
#   "interactive_users": [...],
#   "default_umask": "027",
#   "shell_timeout": 900,
#   "root_login_restricted": true,
#   "su_restricted": true
# }
```

**Priority:** HIGH
**Effort:** 3-4 days
**Controls Covered:** 10

---

### 5. System Maintenance (CIS 6.x - 52 controls)

#### 5.1 File Permissions (9 controls)
**Required Facts:**
- `file_permissions` - /etc/passwd, /etc/shadow, /etc/group, etc.
- All system-critical file permissions

**Custom Module Needed:**
```python
# gather_critical_file_permissions.py
# Checks: stat /etc/passwd /etc/passwd- /etc/shadow /etc/shadow- /etc/group /etc/group- /etc/gshadow /etc/gshadow-
# Output: {
#   "file_permissions": {
#     "/etc/passwd": { "owner": "root", "group": "root", "mode": "644" },
#     ...
#   }
# }
```

**Priority:** MEDIUM
**Effort:** 1 day
**Controls Covered:** 9

#### 5.2 File Ownership & Permissions Audits (6 controls)
**Required Facts:**
- `world_writable_files` - All world-writable files
- `unowned_files` - Files with no owner
- `ungrouped_files` - Files with no group
- `suid_files` - SUID binaries
- `sgid_files` - SGID binaries

**Custom Module Needed:**
```python
# gather_file_audits.py
# Runs: find / -xdev -perm -0002 -type f  (world writable)
# Runs: find / -xdev -nouser  (unowned)
# Runs: find / -xdev -nogroup  (ungrouped)
# Runs: find / -xdev -perm -4000  (SUID)
# Runs: find / -xdev -perm -2000  (SGID)
# Output: {
#   "world_writable_files": ["/path1", ...],
#   "unowned_files": ["/path2", ...],
#   "ungrouped_files": ["/path3", ...],
#   "suid_files": ["/usr/bin/sudo", ...],
#   "sgid_files": ["/usr/bin/wall", ...]
# }
```

**Priority:** MEDIUM
**Effort:** 2 days
**Controls Covered:** 6

#### 5.3 User & Group Integrity (16 controls)
**Required Facts:**
- `passwd_users` - All users from /etc/passwd
- `shadow_users` - All users from /etc/shadow
- `groups` - All groups from /etc/group
- Duplicate UID/GID detection
- Root PATH integrity
- User home directory validation

**Custom Module Needed:**
```python
# gather_user_group_integrity.py
# Parses: /etc/passwd, /etc/shadow, /etc/group
# Checks: Duplicate UIDs, GIDs, usernames, group names
# Checks: Root PATH for ".", empty entries, world-writable dirs
# Checks: User home directories exist, ownership, permissions
# Checks: .netrc, .forward, .rhosts files in home dirs
# Output: {
#   "passwd_users": [...],
#   "shadow_users": [...],
#   "groups": [...],
#   "root_path": { "directories": ["/usr/local/bin", ...] },
#   "directory_permissions": {...},
#   "interactive_users": [...]
# }
```

**Priority:** HIGH
**Effort:** 3-4 days
**Controls Covered:** 16

---

## 6. OPA Policy Loading & Data Mapping

### 6.1 Data Transformation Layer
**Requirement:** Map collected facts to OPA policy input format

**Component Needed:**
```yaml
# transform_facts_for_opa.yml
# Ansible playbook that:
# 1. Loads collected facts JSON
# 2. Transforms to match OPA policy expected structure
# 3. Adds computed/derived fields
# 4. Outputs OPA-ready JSON
```

**Priority:** HIGH
**Effort:** 2-3 days

### 6.2 OPA Policy Enhancement
**Requirement:** Fix policy syntax for production use

**Issues to Address:**
1. Variable initialization conflicts (lines 36-40, array.concat overwriting)
2. Add default values for missing facts
3. Handle optional checks gracefully
4. Add policy versioning
5. Split monolithic policy into modules

**Priority:** HIGH
**Effort:** 3-5 days

### 6.3 Policy Testing Framework
**Component Needed:**
```bash
# test_opa_policies.sh
# Uses: opa test
# Tests each control with sample data
# Validates policy logic
# Ensures no false positives/negatives
```

**Priority:** MEDIUM
**Effort:** 5-7 days

---

## 7. Remediation Framework

### 7.1 Remediation Playbooks
**Requirement:** Create Ansible playbooks to fix violations

**Structure:**
```
remediation/
  ├── section_1_initial_setup/
  │   ├── 1.1_filesystem_hardening.yml
  │   ├── 1.3_aide_setup.yml
  │   ├── 1.4_grub_hardening.yml
  │   └── ...
  ├── section_2_services/
  ├── section_3_network/
  ├── section_4_logging/
  ├── section_5_access/
  └── section_6_maintenance/
```

**Priority:** MEDIUM
**Effort:** 20-30 days (for all 278 controls)

### 7.2 Selective Remediation
**Component Needed:**
```yaml
# remediate_violations.yml
# Reads: OPA compliance report
# Extracts: Failed controls
# Runs: Only relevant remediation playbooks
# Reports: Before/after state
```

**Priority:** MEDIUM
**Effort:** 3-4 days

---

## 8. Reporting & Dashboard

### 8.1 Enhanced Compliance Reporter
**Component Needed:**
```python
# scripts/advanced_compliance_reporter.py
# Generates:
# - Executive summary (% compliance)
# - Section-by-section breakdown
# - Critical vs non-critical violations
# - Trend analysis (if historical data exists)
# - Remediation priority matrix
# - Export to PDF, HTML, JSON
```

**Priority:** MEDIUM
**Effort:** 5-7 days

### 8.2 AAP Integration
**Component Needed:**
- Job Templates for each playbook
- Survey variables for configuration
- Workflow Templates for full pipeline
- Custom Execution Environments with OPA
- Scheduled compliance scans
- Notifications/webhooks for failures

**Priority:** LOW (functional but manual currently)
**Effort:** 3-5 days

---

## Priority Matrix

### Phase 1: Critical Path (30-40 days)
1. Enhanced Fact Collection Modules (15-20 days)
   - Auditd configuration (HIGH)
   - SSH configuration (HIGH)
   - PAM configuration (HIGH)
   - User security (HIGH)
   - Firewall config (HIGH)
   - Network sysctl (HIGH)

2. Data Transformation Layer (3 days)

3. OPA Policy Enhancement (5 days)

### Phase 2: Validation & Testing (10-15 days)
4. Policy Testing Framework (7 days)
5. End-to-end compliance test (3-5 days)

### Phase 3: Remediation (20-30 days)
6. Critical remediation playbooks (20 days)
   - Section 4: Auditing (HIGH)
   - Section 5: SSH/PAM (HIGH)
   - Section 1: Filesystem/SELinux (HIGH)

### Phase 4: Production (10-15 days)
7. Reporting & Dashboard (7 days)
8. AAP Integration (5 days)
9. Documentation (3 days)

---

## Total Effort Estimate

**Development:** 70-100 days (3.5-5 months)
**Testing:** 15-20 days
**Documentation:** 5-7 days

**Total:** 90-127 days (~4-6 months with 1 developer)

---

## Success Criteria

1. **100% Control Coverage** - All 278 CIS controls validated
2. **Automated Collection** - No manual data gathering required
3. **Accurate Results** - <1% false positive/negative rate
4. **Automated Remediation** - 80%+ of violations auto-fixable
5. **AAP Integration** - Full workflow in Ansible Automation Platform
6. **Compliance Reports** - Executive-ready PDF/HTML reports
7. **Audit Trail** - All compliance checks logged and timestamped

---

## Next Immediate Steps

1. **Prioritize Custom Modules** - Start with auditd, SSH, PAM
2. **Create Module Template** - Standardize custom fact module structure
3. **Set Up Test Environment** - Non-compliant RHEL 9 VM for testing
4. **Fix OPA Policy Syntax** - Resolve array.concat conflicts
5. **Build Data Transformer** - Map Ansible facts → OPA input format
