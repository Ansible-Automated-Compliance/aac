> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab on OpenShift Services, AAP 2.7). Findings to check: HOST:8181x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Role: gather_file_permissions

**Authors:** Tim Coulter & Claude
**Date:** October 15, 2025

Gathers comprehensive system file permission information for CIS RHEL 9 compliance validation.

## Description

This role performs extensive file permission security analysis including:
- Critical system file permissions (/etc/passwd, /etc/shadow, etc.)
- World-writable file detection
- Unowned and ungrouped file detection
- SUID executable audit
- SGID executable audit
- SSH private key permissions
- Unusual permissions in /etc

## Requirements

- RHEL 9 or compatible system
- Ansible 2.9 or higher
- Root or sudo privileges

## Role Variables

Available variables with defaults (see `defaults/main.yml`):

```yaml
# Critical system files and their expected permissions
critical_file_permissions:
  /etc/passwd:
    mode: "0644"
    owner: root
    group: root
  /etc/shadow:
    mode: "0000"  # Accepts 0000, 0400, 0600
    owner: root
    group: root
  /etc/group:
    mode: "0644"
    owner: root
    group: root
  /etc/gshadow:
    mode: "0000"
    owner: root
    group: root

# Known legitimate SUID binaries
known_suid_binaries:
  - /usr/bin/sudo
  - /usr/bin/su
  - /usr/bin/passwd
  - /usr/bin/mount
  - /usr/bin/umount

# Search result limits
max_suid_sgid_results: 100
max_unowned_files: 50
max_world_writable_files: 50
```

## Dependencies

None.

## Example Playbook

```yaml
---
- name: Gather file permissions
  hosts: rhel9_servers
  become: yes
  roles:
    - gather_file_permissions

- name: Display permission issues
  hosts: rhel9_servers
  tasks:
    - name: Show critical files with incorrect permissions
      debug:
        var: item
      loop: "{{ host_file_permissions_facts.critical_files.analysis }}"
      when: not item.fully_compliant

    - name: Show world-writable files
      debug:
        var: host_file_permissions_facts.world_writable.files
      when: host_file_permissions_facts.world_writable.has_issues

    - name: Show unowned files
      debug:
        var: host_file_permissions_facts.unowned_files.files
      when: host_file_permissions_facts.unowned_files.has_issues

    - name: Show unknown SUID binaries requiring review
      debug:
        var: host_file_permissions_facts.suid_files.unknown_binaries
      when: host_file_permissions_facts.suid_files.requires_review
```

## Facts Generated

This role sets the following fact variable: `host_file_permissions_facts`

### Structure:

```yaml
host_file_permissions_facts:
  critical_files:
    expected_count: 17
    analysis:
      - file: /etc/passwd
        exists: true
        actual_mode: "0644"
        expected_mode: "0644"
        mode_compliant: true
        actual_owner: root
        expected_owner: root
        owner_compliant: true
        actual_group: root
        expected_group: root
        group_compliant: true
        fully_compliant: true
      - file: /etc/shadow
        exists: true
        actual_mode: "0400"
        expected_mode: "0000"
        mode_compliant: true  # 0400 acceptable for shadow files
        fully_compliant: true
    all_compliant: true
    non_compliant_count: 0

  world_writable:
    files:
      - path: /tmp/suspicious.txt
        mode: "0666"
        owner: user1
        group: users
        size: 1024
    count: 1
    has_issues: true
    compliant: false

  unowned_files:
    files:
      - path: /opt/old_app/data.db
        mode: "0644"
        uid: 1050  # No corresponding user
        gid: 1050
        size: 524288
    count: 1
    has_issues: true
    compliant: false

  ungrouped_files:
    files: []
    count: 0
    has_issues: false
    compliant: true

  suid_files:
    all_files: [...]
    total_count: 15
    known_binaries:
      - path: /usr/bin/sudo
        mode: "4755"
        owner: root
        group: root
        size: 204464
        known_binary: true
        review_required: false
    known_count: 12
    unknown_binaries:
      - path: /usr/local/bin/custom_tool
        mode: "4755"
        owner: root
        group: root
        size: 14232
        known_binary: false
        review_required: true
    unknown_count: 3
    requires_review: true

  sgid_files:
    files:
      - path: /usr/bin/write
        mode: "2755"
        owner: root
        group: tty
        size: 23712
    count: 8

  ssh_private_keys:
    analysis:
      - path: /etc/ssh/ssh_host_rsa_key
        mode: "0600"
        owner: root
        group: root
        mode_compliant: true
        owner_compliant: true
        fully_compliant: true
    all_compliant: true

  unusual_etc_permissions:
    files:
      - /etc/some_app/config.dat
    count: 1

  compliance_checks:
    critical_files_correct: true
    no_world_writable_files: false
    no_unowned_files: false
    no_ungrouped_files: true
    suid_files_reviewed: false  # Unknown SUID files found
    ssh_keys_secure: true

  collection_timestamp: "2025-10-15T12:34:56Z"
```

## CIS Controls Covered

This role gathers facts for the following CIS RHEL 9 Benchmark controls:

**Section 6.1.x - Audit System File Permissions (14 controls):**
- **6.1.1**: Audit system file permissions (general)
- **6.1.2**: Ensure permissions on /etc/passwd are configured
- **6.1.3**: Ensure permissions on /etc/passwd- are configured
- **6.1.4**: Ensure permissions on /etc/group are configured
- **6.1.5**: Ensure permissions on /etc/group- are configured
- **6.1.6**: Ensure permissions on /etc/shadow are configured
- **6.1.7**: Ensure permissions on /etc/shadow- are configured
- **6.1.8**: Ensure permissions on /etc/gshadow are configured
- **6.1.9**: Ensure permissions on /etc/gshadow- are configured
- **6.1.10**: Ensure no world writable files exist
- **6.1.11**: Ensure no unowned files or directories exist
- **6.1.12**: Ensure no ungrouped files or directories exist
- **6.1.13**: Audit SUID executables
- **6.1.14**: Audit SGID executables

**Total: ~14 controls** (Note: Some CIS sections may have fewer numbered controls; this role provides comprehensive coverage)

## Usage with OPA

The facts collected by this role can be fed directly into OPA for policy evaluation:

```yaml
- name: Evaluate file permissions compliance with OPA
  uri:
    url: "http://localhost:8181/v1/data/cis/rhel9/section_6/file_permissions"
    method: POST
    body_format: json
    body:
      input: "{{ host_file_permissions_facts }}"
    return_content: yes
  register: opa_file_permissions_result
```

## Security Checks Performed

### 1. Critical System File Permissions

**Why Important:** These files control authentication, authorization, and system access. Incorrect permissions can allow unauthorized users to:
- Read password hashes (/etc/shadow)
- Modify user accounts (/etc/passwd)
- Escalate privileges
- Create backdoor accounts

**Critical Files Checked:**

| File | Expected Mode | Purpose | Security Risk if Wrong |
|------|---------------|---------|------------------------|
| /etc/passwd | 0644 | User account database | Tampering creates backdoor accounts |
| /etc/passwd- | 0644 | Backup of passwd | Same as above |
| /etc/group | 0644 | Group database | Unauthorized group membership |
| /etc/group- | 0644 | Backup of group | Same as above |
| /etc/shadow | 0000/0400/0600 | Password hashes | Password cracking if world-readable |
| /etc/shadow- | 0000/0400/0600 | Backup of shadow | Same as above |
| /etc/gshadow | 0000/0400/0600 | Group passwords | Group password exposure |
| /etc/gshadow- | 0000/0400/0600 | Backup of gshadow | Same as above |
| /etc/ssh/sshd_config | 0600 | SSH server config | Unauthorized access if modified |
| /etc/crontab | 0600 | Scheduled tasks | Privilege escalation |
| /etc/cron.d | 0700 | Cron job configs | Privilege escalation |

**Permission Breakdown:**

**0644 (rw-r--r--):**
- Owner (root): Read + Write
- Group (root): Read only
- Others: Read only
- **Used for:** Files that users need to read but shouldn't modify (passwd, group)

**0600 (rw-------):**
- Owner (root): Read + Write
- Group: No access
- Others: No access
- **Used for:** Sensitive configuration files

**0000/0400 (r--------):**
- Owner (root): Read only or no access
- Group: No access
- Others: No access
- **Used for:** Password hash files (shadow, gshadow)

### 2. World-Writable Files

**What:** Files where the "others" permission includes write (mode ends in 2, 3, 6, or 7)

**Why Dangerous:**
- **Data Tampering:** Any user can modify file contents
- **Code Injection:** Attacker can inject malicious code into scripts/configs
- **Privilege Escalation:** If a privileged process reads the file, attacker can control its behavior
- **Denial of Service:** Attacker can corrupt or delete data

**Check Method:**
```bash
find / -xdev -type f -perm -0002 -print
```

**Exceptions:**
- Files in /tmp with sticky bit (mode 1666) may be acceptable if application requires it
- Named pipes and sockets may have different requirements

### 3. Unowned Files

**What:** Files where the UID doesn't correspond to any user in /etc/passwd

**How This Happens:**
- User account deleted but files not cleaned up
- Files restored from backup with non-existent UIDs
- Files created by removed application
- Migration from another system

**Why Dangerous:**
- **Security Blind Spot:** No clear responsibility for file security
- **Privilege Escalation:** If UID is reused for new user, they inherit files
- **Compliance Violation:** Most frameworks require all files have valid owners

**Check Method:**
```bash
find / -xdev -nouser -print
```

**Remediation:**
- Assign to appropriate user: `chown newowner:newgroup <file>`
- Delete if no longer needed
- Document if intentional (rare)

### 4. Ungrouped Files

**What:** Files where the GID doesn't correspond to any group in /etc/group

**Same issues as unowned files but for group ownership.**

**Check Method:**
```bash
find / -xdev -nogroup -print
```

### 5. SUID (Set User ID) Executables

**What SUID Does:**
- When SUID bit is set (mode 4xxx), executable runs with owner's privileges instead of caller's
- Example: `/usr/bin/passwd` is owned by root with SUID bit
  - Regular user runs `passwd`
  - Process runs as root (not user)
  - Allows user to change their own password in /etc/shadow (root-only file)

**Why Dangerous:**
- **Privilege Escalation:** Vulnerability in SUID binary = instant root access
- **Attack Surface:** Every SUID root binary is a potential privilege escalation vector
- **Historical Exploits:** Many CVEs involve SUID binaries (sudo, pkexec, etc.)

**Identification:**
```bash
find / -xdev -type f -perm -4000 -print
```

**Known Legitimate SUID Binaries:**
- `/usr/bin/sudo` - Administrative command execution
- `/usr/bin/su` - Switch user
- `/usr/bin/passwd` - Change passwords
- `/usr/bin/chage` - Password aging
- `/usr/bin/gpasswd` - Group password administration
- `/usr/bin/newgrp` - Change current group
- `/usr/bin/mount` - Mount filesystems
- `/usr/bin/umount` - Unmount filesystems
- `/usr/bin/crontab` - Cron job management
- `/usr/bin/pkexec` - PolicyKit authentication
- `/usr/sbin/unix_chkpwd` - PAM password checking
- `/usr/libexec/openssh/ssh-keysign` - SSH host-based authentication

**Red Flags (Unknown SUID Binaries):**
- Files in /tmp, /var/tmp, /home
- Custom applications with SUID
- Recently modified SUID binaries
- SUID shell scripts (especially dangerous)

**Security Best Practice:**
- Minimize SUID binaries
- Use capabilities instead where possible
- Regular audits to detect new SUID files
- Remove SUID bit if not needed: `chmod u-s <file>`

### 6. SGID (Set Group ID) Executables

**What SGID Does:**
- When SGID bit is set (mode 2xxx), executable runs with group's privileges
- Less dangerous than SUID but still risky

**Common SGID Binaries:**
- `/usr/bin/write` - Send messages to other users (group tty)
- `/usr/bin/wall` - Write to all users (group tty)
- `/usr/bin/screen` - Terminal multiplexer (group utmp)

**Identification:**
```bash
find / -xdev -type f -perm -2000 -print
```

### 7. SSH Private Key Permissions

**Files:** `/etc/ssh/ssh_host_*_key`

**Expected Permissions:** 0600 (rw-------)

**Why Critical:**
- **Host Authentication:** These are the SSH server's private keys
- **If Leaked:** Attacker can impersonate the server (man-in-the-middle attacks)
- **Compliance:** All security frameworks require private keys be protected

**Types of SSH Host Keys:**
- `ssh_host_rsa_key` - RSA algorithm
- `ssh_host_ecdsa_key` - ECDSA algorithm
- `ssh_host_ed25519_key` - Ed25519 algorithm (recommended)

## Common Issues Detected

**Critical Issues:**
- /etc/shadow readable by non-root (mode 0644 instead of 0000/0400/0600)
- /etc/passwd writable by non-root (mode 0666)
- SSH private keys with incorrect permissions
- World-writable files in system directories
- Unknown SUID root binaries

**Warnings:**
- Unowned files from deleted users
- Ungrouped files from deleted groups
- Excessive number of SUID binaries
- SGID binaries in unusual locations

**Informational:**
- Total SUID/SGID binary count
- Unusual permissions in /etc (not 644, 755, 600, 400)

## Remediation Examples

### Fix Critical File Permissions

```bash
# /etc/passwd (must be world-readable, root writable only)
chmod 0644 /etc/passwd
chown root:root /etc/passwd

# /etc/shadow (must be root-only readable)
chmod 0000 /etc/shadow
chown root:root /etc/shadow
# OR
chmod 0400 /etc/shadow  # Read-only for root

# /etc/group
chmod 0644 /etc/group
chown root:root /etc/group

# /etc/gshadow
chmod 0000 /etc/gshadow
chown root:root /etc/gshadow

# SSH server configuration
chmod 0600 /etc/ssh/sshd_config
chown root:root /etc/ssh/sshd_config

# SSH private keys
chmod 0600 /etc/ssh/ssh_host_*_key
chown root:root /etc/ssh/ssh_host_*_key

# Cron files
chmod 0600 /etc/crontab
chmod 0700 /etc/cron.d /etc/cron.daily /etc/cron.hourly /etc/cron.weekly /etc/cron.monthly
```

### Remove World-Writable Permission

```bash
# Find and fix world-writable files
find / -xdev -type f -perm -0002 -print | while read file; do
  chmod o-w "$file"
  echo "Fixed: $file"
done

# Or for a specific file
chmod o-w /path/to/file
```

### Fix Unowned Files

```bash
# Assign to root
chown root:root /path/to/unowned/file

# Or assign to specific user/group
chown appuser:appgroup /path/to/unowned/file

# Delete if obsolete
rm -f /path/to/unowned/file
```

### Remove Unnecessary SUID Bit

```bash
# Remove SUID bit from specific file
chmod u-s /path/to/suid/binary

# Find and review all SUID files
find / -xdev -type f -perm -4000 -print | while read file; do
  echo "$file is SUID"
  ls -l "$file"
  # Decide: keep, remove SUID, or delete
done
```

### Audit SUID Binaries Systematically

```bash
# Create baseline of known SUID files
find / -xdev -type f -perm -4000 -print | sort > /root/suid_baseline.txt

# Later, compare to detect new SUID files
find / -xdev -type f -perm -4000 -print | sort > /root/suid_current.txt
diff /root/suid_baseline.txt /root/suid_current.txt
```

## Performance Considerations

This role makes extensive filesystem searches:
- Searches all local filesystems for world-writable files (limited to 50 results)
- Searches all local filesystems for unowned files (limited to 50 results)
- Searches all local filesystems for ungrouped files (limited to 50 results)
- Searches all local filesystems for SUID executables (limited to 100 results)
- Searches all local filesystems for SGID executables (limited to 100 results)

**Typical runtime:** 10-30 seconds per host (depends on filesystem size)

**Optimization:**
- All searches limited by `head -N` to prevent excessive results
- Uses `-xdev` to prevent crossing filesystem boundaries
- Errors redirected to /dev/null to suppress permission denied messages
- Stat operations batched per search type

**For very large filesystems:**
- Consider increasing timeout values
- Adjust max result limits if needed
- Run during maintenance windows

## Example Output

```
TASK [Display file permissions summary] **************************************
ok: [server1] => {
    "msg": [
        "==========================================",
        "File Permissions Facts",
        "==========================================",
        "Critical System Files:",
        "  Total Checked: 17",
        "  Compliant: 16",
        "  Non-Compliant: 1",
        "",
        "Security Issues:",
        "  World-Writable Files: 2",
        "  Unowned Files: 1",
        "  Ungrouped Files: 0",
        "",
        "SUID/SGID Executables:",
        "  SUID Files: 15",
        "    Known Safe: 12",
        "    Requires Review: 3",
        "  SGID Files: 8",
        "",
        "SSH Private Keys:",
        "  Total: 3",
        "  Compliant: 3",
        "",
        "Compliance Summary:",
        "  Critical Files: False",
        "  No World-Writable: False",
        "  No Unowned Files: False",
        "  SSH Keys Secure: True",
        "=========================================="
    ]
}
```

## Integration with Other Roles

This role complements:
- `gather_user_security` - User account configuration and policies
- `gather_pam_config` - Password policies enforced via PAM
- `gather_ssh_config` - SSH configuration (uses data from ssh_private_keys check)
- `gather_filesystem_config` - Filesystem mount options and partitioning

## Advanced SUID/SGID Analysis

### Understanding the Risk

**Low Risk SUID Binaries:**
- Well-maintained, frequently audited (sudo, su, passwd)
- Part of base OS distribution
- Digital signature verified
- Long history of security updates

**High Risk SUID Binaries:**
- Custom/third-party applications
- Outdated versions with known CVEs
- Shell scripts with SUID (especially dangerous)
- Files in writable directories (/tmp, /var/tmp)
- Recently created/modified SUID files

### Defense in Depth

**Layer 1 - Minimize SUID:**
```bash
# Use capabilities instead of SUID where possible
# Example: ping doesn't need SUID with capabilities
setcap cap_net_raw+ep /usr/bin/ping
chmod u-s /usr/bin/ping
```

**Layer 2 - Filesystem Protection:**
```bash
# Mount partitions with nosuid option
# In /etc/fstab:
/dev/mapper/vg-home  /home  xfs  defaults,nosuid  0 0
```

**Layer 3 - Monitoring:**
```bash
# Use auditd to monitor SUID file creation
auditctl -w /usr/bin -p wa -k suid_monitoring
auditctl -w /usr/sbin -p wa -k suid_monitoring
```

**Layer 4 - SELinux/AppArmor:**
- Confines SUID binaries even if compromised
- Limits damage from privilege escalation

## License

Apache-2.0
## Author Information

Created by Tim Coulter & Claude for CIS RHEL 9 compliance automation.
