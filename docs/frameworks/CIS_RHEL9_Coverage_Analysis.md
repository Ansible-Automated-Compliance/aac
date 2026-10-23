# CIS RHEL 9 Benchmark Coverage Analysis

> **⚠️ HISTORICAL DOCUMENT — April 2026**
>
> This analysis was written when coverage was 216/338 controls (63.9%). **All 338 controls are now implemented at 100% coverage.**
>
> Current implementation: 14 core CIS modules + 3 extended hardening modules (STIG/NIST/EDA) in `policies/benchmarks/cis/os/linux/rhel_9/`. This document is retained as a historical record of the gap analysis that guided the implementation roadmap.

---

## Historical Coverage Snapshot (October 2025)

**Total Controls in CIS RHEL 9 Benchmark v2.0.0:** 338
**Controls Evaluated at time of writing:** 216 (63.9%)
**Controls NOT Evaluated at time of writing:** 122 (36.1%)

---

## Sections Currently Evaluated (216 controls)

### ✅ Section 1.1: Filesystem Configuration (50 controls)
- Disabled unnecessary filesystems (cramfs, freevxfs, jffs2, hfs, udf, vfat)
- Partition configuration (/tmp, /var, /var/tmp, /var/log, /var/log/audit, /home)
- Mount options (nodev, nosuid, noexec)
- Removable media partitions
- USB storage
- **Status:** COMPLIANT on ocptesttc

### ✅ Section 2: Services (30 controls)
- Time synchronization (chronyd/systemd-timesyncd)
- Unnecessary services (autofs, avahi, cups, DHCP, DNS, FTP, HTTP, IMAP/POP3, Samba, SNMP, etc.)
- Client package removal
- **Status:** NON-COMPLIANT on ocptesttc (missing time sync, autofs issues)

### ✅ Section 3: Network Configuration (20 controls)
- IP forwarding
- Packet redirect sending
- Source routed packets
- ICMP redirects
- Secure ICMP
- Suspicious packets logging
- IPv6 parameters
- TCP wrappers
- **Status:** COMPLIANT on ocptesttc

### ✅ Section 4.2: Logging and Auditing (17 controls)
- rsyslog configuration
- logrotate
- systemd-journald
- Log file permissions
- **Status:** NON-COMPLIANT on ocptesttc (rsyslog, journald, logrotate issues)

### ✅ Section 6.1: System File Permissions (14 controls)
- Critical system file permissions (/etc/passwd, /etc/shadow, /etc/group, /etc/gshadow)
- World-writable files
- Unowned and ungrouped files
- SUID and SGID executables
- SSH private key permissions
- **Status:** NON-COMPLIANT on ocptesttc (SSH key permissions)

---

## Sections NOT Currently Evaluated (~122 controls)

### ❌ Section 1.2-1.9: Other Initial Setup (~40 controls)

**1.2: Configure Software Updates**
- Package manager repositories
- GPG key configuration
- Automatic security updates

**1.3: Filesystem Integrity Checking**
- AIDE installation and configuration
- Filesystem integrity checks
- Scheduled integrity scans

**1.4: Secure Boot Settings**
- Bootloader password
- Authentication for single-user mode

**1.5: Additional Process Hardening**
- Core dumps
- Address space layout randomization (ASLR)
- Prelink

**1.6: Mandatory Access Controls (SELinux)**
- SELinux enabled and enforcing
- SELinux policy
- Unconfined services
- SELinux user mappings

**1.7: Command Line Warning Banners**
- /etc/motd
- /etc/issue
- /etc/issue.net
- GDM login banner

**1.8: GNOME Display Manager**
- GDM configuration
- Automatic mounting
- Automatic run
- User list disable

---

### ❌ Section 4.1: Configure System Accounting - auditd (~35-40 controls)

**Critical Missing Controls:**
- auditd service enabled
- auditd configuration parameters
- Audit log storage size
- System shutdown on audit failure
- Keep all auditing information
- Audit rules for:
  - Time changes
  - User/group modifications
  - Network environment
  - System MAC policy
  - Login/logout events
  - Session initiation
  - Permission modifications
  - Unauthorized access attempts
  - Privileged commands
  - Successful file system mounts
  - File deletion events
  - sudoers changes
  - Kernel module loading/unloading
- Audit configuration immutable

---

### ❌ Section 5: Access, Authentication and Authorization (~55 controls)

**5.1: Configure time-based job schedulers (~5 controls)**
- cron daemon enabled
- cron permissions (/etc/crontab, /etc/cron.hourly, etc.)
- at/cron restrictions
- at daemon enabled

**5.2: Configure SSH Server (~20 controls)**
- SSH Protocol 2
- SSH LogLevel
- SSH X11 forwarding disabled
- SSH MaxAuthTries
- SSH IgnoreRhosts
- SSH HostbasedAuthentication disabled
- SSH root login disabled
- SSH PermitEmptyPasswords disabled
- SSH PermitUserEnvironment disabled
- SSH Ciphers
- SSH MACs
- SSH KexAlgorithms
- SSH Idle Timeout
- SSH LoginGraceTime
- SSH warning banner
- SSH PAM enabled
- SSH AllowTcpForwarding disabled
- SSH ClientAliveCountMax

**5.3: Configure privilege escalation (~10 controls)**
- sudo installed
- sudo use pty
- sudo log file
- sudo commands use pty
- sudo command timeout
- sudo re-authentication
- su command restricted
- sudo custom logfile

**5.4: Configure PAM (~15 controls)**
- Password creation requirements (pwquality)
- Password reuse limited
- Password hashing algorithm (SHA-512 or yescrypt)
- Account lockout policies
- PAM modules configuration
- Restrict access to su command

**5.5: User Accounts and Environment (~10 controls)**
- Set Shadow Password Suite parameters
- Password expiration days
- Password change minimum days
- Password expiration warning days
- Inactive password lock
- System accounts non-login
- Default user umask
- Default user shell timeout
- Root PATH integrity
- All users' home directories exist

---

### ❌ Section 6.2: User and Group Settings (~10 controls)

- Password fields are not empty
- No legacy "+" entries in passwd/shadow/group
- Root is the only UID 0 account
- Root PATH integrity
- User home directory permissions
- User dot file permissions
- Users have valid home directories
- User home directories ownership
- Duplicate UIDs
- Duplicate GIDs
- Duplicate user names
- Duplicate group names
- Netrc files permissions
- Forward files exist
- Rhosts files exist

---

## Why Only 216 Controls?

The current implementation in this compliance automation platform represents a **foundational baseline** assessment. The 216 controls were chosen because they:

1. **Can be validated remotely via Ansible facts** without requiring privileged access to auditd or PAM configuration
2. **Provide strong foundational security** covering filesystems, networks, services, and permissions
3. **Are commonly misconfigured** in production environments
4. **Don't require deep system introspection** that might impact production systems

### What's Required for Full 338 Control Coverage:

1. **Enhanced Ansible Fact Collection**
   - Auditd rules and configuration
   - SSH daemon configuration (sshd_config parsing)
   - PAM configuration files
   - Sudo configuration
   - SELinux status and policies

2. **Additional OPA Policy Development**
   - ~35 controls for Section 4.1 (auditd)
   - ~20 controls for Section 5.2 (SSH)
   - ~15 controls for Section 5.4 (PAM)
   - ~10 controls for Section 1.6 (SELinux)
   - ~10 controls for Section 5.3 (sudo)
   - ~10 controls for Section 6.2 (User/Group settings)
   - ~22 controls for other Section 1 items

3. **More Comprehensive Playbook**
   - Additional tasks to gather SSH config
   - PAM configuration collection
   - Auditd rules collection
   - SELinux policy details

---

## Current Assessment Value

Despite covering 63.9% of controls, this assessment provides **significant value**:

### ✅ Strong Coverage Areas:
- **Filesystem Security**: Complete coverage of partition hardening
- **Network Hardening**: All critical kernel parameters
- **Service Attack Surface**: Identification of unnecessary services
- **Permission Audit**: Critical system file permissions

### 🎯 Compliance Use Cases Met:
1. **Baseline Security Posture** - Identifies most common misconfigurations
2. **Infrastructure as Code Validation** - Can be integrated into CI/CD
3. **Continuous Compliance Monitoring** - Automated drift detection
4. **Multi-System Assessment** - Scalable across large environments

### ⚠️ Gaps for Full Compliance:
- Cannot certify "100% CIS RHEL 9 compliant"
- Missing audit trail configuration validation
- No SSH hardening verification
- No password policy enforcement checks
- No SELinux configuration validation

---

## Roadmap to 100% Coverage

To achieve full 338 control coverage, development work is needed on:

### Phase 1: High-Impact Controls (Priority)
1. **Section 5.2: SSH Server** (20 controls)
   - Highest security impact
   - Common attack vector
   - Relatively easy to collect and validate

2. **Section 4.1: auditd** (35-40 controls)
   - Required for compliance logging
   - Critical for incident response
   - Moderate complexity to implement

### Phase 2: Access Controls
3. **Section 5.4: PAM** (15 controls)
   - Password policies
   - Account lockout
   - Authentication controls

4. **Section 1.6: SELinux** (10 controls)
   - Mandatory access controls
   - Important for government/regulated environments

### Phase 3: Remaining Controls
5. **Section 5.3, 5.5, 6.2, and remaining Section 1** (~30 controls)
   - User management
   - Sudo configuration
   - Bootloader security
   - File integrity

---

## Conclusion

**Current State:** 216/338 controls (63.9%) provides strong **foundational compliance**

**Recommendation:**
- Use current assessment for **baseline security** and **continuous monitoring**
- Supplement with manual checks for critical missing sections (especially SSH and auditd) if pursuing full CIS certification
- Track development progress on GitHub repository for remaining control implementation

**Value Delivered:**
- Automated assessment of most critical security controls
- Scalable across enterprise environments
- Integration-ready with AAP 2.6
- PostgreSQL storage for trending and reporting
- Multi-framework support (FISMA, NERC-CIP, SOC 2, etc.)

The 122 missing controls represent an **active development area** for the compliance automation platform.
