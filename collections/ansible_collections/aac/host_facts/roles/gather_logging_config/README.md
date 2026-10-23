> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab on OpenShift Services, AAP 2.7). Findings to check: HOST:8181x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Role: gather_logging_config

**Authors:** Tim Coulter & Claude
**Date:** October 15, 2025

Gathers comprehensive logging and audit configuration for CIS RHEL 9 compliance validation.

## Description

This role performs extensive logging configuration analysis including:
- rsyslog installation and service status
- rsyslog configuration (file permissions, logging rules, remote logging)
- systemd-journald configuration (compression, storage, forwarding)
- Log file permissions validation
- Log directory analysis
- Logrotate configuration
- Detection of files with excessive permissions

## Requirements

- RHEL 9 or compatible system
- Ansible 2.9 or higher
- Root or sudo privileges

## Role Variables

Available variables with defaults (see `defaults/main.yml`):

```yaml
# Expected log file permissions (CIS 4.2.1.x)
expected_log_permissions:
  /var/log/messages:
    mode: "0640"
    owner: root
    group: root
  /var/log/secure:
    mode: "0640"
    owner: root
    group: root
  /var/log/maillog:
    mode: "0640"
    owner: root
    group: root
  /var/log/cron:
    mode: "0640"
    owner: root
    group: root
  /var/log/boot.log:
    mode: "0640"
    owner: root
    group: root

# Critical journald settings (CIS 4.2.2.x)
required_journald_settings:
  Storage: persistent
  Compress: "yes"
  ForwardToSyslog: "yes"

# Critical rsyslog settings
required_rsyslog_modules:
  - imjournal
  - imuxsock

# Remote logging configuration
remote_log_host: ""  # Set if remote logging is required
remote_log_port: 514

# Log directories to check
log_directories:
  - /var/log
  - /var/log/audit
```

## Dependencies

None.

## Example Playbook

```yaml
---
- name: Gather logging configuration
  hosts: rhel9_servers
  become: yes
  roles:
    - gather_logging_config

- name: Display logging issues
  hosts: rhel9_servers
  tasks:
    - name: Show log files with incorrect permissions
      debug:
        var: item
      loop: "{{ host_logging_facts.log_file_permissions.analysis }}"
      when: not item.fully_compliant

    - name: Show files with excessive permissions
      debug:
        var: host_logging_facts.excessive_permissions.files
      when: host_logging_facts.excessive_permissions.has_issues

    - name: Show journald configuration issues
      debug:
        msg:
          - "Storage: {{ host_logging_facts.journald.storage_mode }} (expected: persistent)"
          - "Compress: {{ host_logging_facts.journald.compress_enabled }} (expected: yes)"
          - "ForwardToSyslog: {{ host_logging_facts.journald.forward_to_syslog }} (expected: yes)"
      when: not host_logging_facts.journald.compliant
```

## Facts Generated

This role sets the following fact variable: `host_logging_facts`

### Structure:

```yaml
host_logging_facts:
  rsyslog:
    installed: true
    version: "rsyslog-8.2102.0-7.el9.x86_64"
    service_active: true
    service_enabled: true
    file_create_mode: "0640"
    logging_rules_count: 12
    logging_rules:
      - "*.info;mail.none;authpriv.none;cron.none /var/log/messages"
      - "authpriv.* /var/log/secure"
      - "mail.* /var/log/maillog"
      - "cron.* /var/log/cron"
    remote_logging_configured: true
    remote_logging_configs:
      - "*.* @@logserver.example.com:514"
    remote_logging_d_configs:
      - file: /etc/rsyslog.d/remote.conf
        config: "*.* @@backup-log.example.com:514"
    compliant: true

  journald:
    config:
      Storage: persistent
      Compress: yes
      ForwardToSyslog: yes
      MaxRetentionSec: 31536000
    compress_enabled: "yes"
    storage_mode: "persistent"
    forward_to_syslog: "yes"
    service_active: true
    service_enabled: true
    compliant: true

  log_file_permissions:
    expected_files:
      - /var/log/messages
      - /var/log/secure
      - /var/log/maillog
      - /var/log/cron
      - /var/log/boot.log
    analysis:
      - file: /var/log/messages
        exists: true
        actual_mode: "0640"
        expected_mode: "0640"
        mode_compliant: true
        actual_owner: root
        expected_owner: root
        owner_compliant: true
        actual_group: root
        expected_group: root
        group_compliant: true
        fully_compliant: true
      - file: /var/log/secure
        exists: true
        actual_mode: "0644"
        expected_mode: "0640"
        mode_compliant: false
        fully_compliant: false
    all_compliant: false
    files_with_issues_count: 1

  log_directories:
    analysis:
      - directory: /var/log
        exists: true
        mode: "0755"
        owner: root
        group: root
        is_directory: true
      - directory: /var/log/audit
        exists: true
        mode: "0700"
        owner: root
        group: root
        is_directory: true

  excessive_permissions:
    files:
      - file: /var/log/old/debug.log
        mode: "0666"
        owner: root
        group: root
        issue: world or group writable
    count: 1
    has_issues: true

  logrotate:
    installed: true
    config_summary:
      raw_config: 42
      rotate_configured: true
      schedule_configured: true

  compliance_checks:
    rsyslog_installed_and_enabled: true
    journald_active_and_configured: true
    journald_forwards_to_rsyslog: true
    rsyslog_file_permissions_configured: true
    log_files_have_correct_permissions: false
    no_excessive_log_permissions: false
    remote_logging_configured: true
    logrotate_installed: true

  collection_timestamp: "2025-10-15T12:34:56Z"
```

## CIS Controls Covered

This role gathers facts for the following CIS RHEL 9 Benchmark controls:

**Section 4.2.1.x - Configure rsyslog (7 controls):**
- **4.2.1.1**: Ensure rsyslog is installed
- **4.2.1.2**: Ensure rsyslog service is enabled and active
- **4.2.1.3**: Ensure journald is configured to send logs to rsyslog
- **4.2.1.4**: Ensure rsyslog default file permissions are configured
- **4.2.1.5**: Ensure logging is configured
- **4.2.1.6**: Ensure rsyslog is configured to send logs to a remote log host
- **4.2.1.7**: Ensure rsyslog is not configured to receive logs from a remote client (informational)

**Section 4.2.2.x - Configure journald (4 controls):**
- **4.2.2.1**: Ensure journald is configured to compress large log files
- **4.2.2.2**: Ensure journald is configured to write logs to persistent disk
- **4.2.2.3**: Ensure journald service is active
- **4.2.2.4**: Ensure journald is not configured to send logs to rsyslog (opposite of 4.2.1.3, depends on strategy)

**Section 4.2.3 - Ensure permissions on all logfiles are configured (1 control):**
- **4.2.3**: Ensure permissions on all logfiles are configured

**Additional Log Security Controls (~5 controls):**
- Log directory permissions
- Excessive permission detection
- Logrotate installation and configuration
- Remote logging validation
- Log file ownership verification

**Total: ~17 controls**

## Usage with OPA

The facts collected by this role can be fed directly into OPA for policy evaluation:

```yaml
- name: Evaluate logging compliance with OPA
  uri:
    url: "http://localhost:8181/v1/data/cis/rhel9/section_4/logging"
    method: POST
    body_format: json
    body:
      input: "{{ host_logging_facts }}"
    return_content: yes
  register: opa_logging_result
```

## Security Checks Performed

### 1. rsyslog Service Status

**Why Important:** rsyslog is the primary logging daemon on RHEL 9. It must be installed, enabled, and running to ensure logs are collected.

**Check Method:**
- `rpm -q rsyslog` - Verify installation
- `systemctl status rsyslog` - Check service status
- `systemctl is-enabled rsyslog` - Verify auto-start configuration

### 2. rsyslog File Permissions ($FileCreateMode)

**Configuration:** `/etc/rsyslog.conf`

**Expected Setting:**
```
$FileCreateMode 0640
```

**Why Important:** Controls default permissions for newly created log files. Setting to 0640 ensures:
- Owner (root) can read/write
- Group (root) can read
- Others have no access

**Security Risk if Missing:** Log files created with 0644 would be world-readable, potentially exposing sensitive information.

### 3. rsyslog Logging Rules

**Configuration:** `/etc/rsyslog.conf` and `/etc/rsyslog.d/*.conf`

**Example Required Rules:**
```
*.info;mail.none;authpriv.none;cron.none    /var/log/messages
authpriv.*                                  /var/log/secure
mail.*                                      /var/log/maillog
cron.*                                      /var/log/cron
*.emerg                                     :omusrmsg:*
```

**Why Important:** Ensures all security-relevant events are logged to appropriate files.

### 4. Remote Logging Configuration

**Configuration Syntax:**
```
# TCP (reliable)
*.* @@logserver.example.com:514

# UDP (less reliable but faster)
*.* @logserver.example.com:514
```

**Why Important:**
- **Centralized Logging:** Aggregates logs from multiple systems
- **Tamper Resistance:** Attackers can't delete logs from compromised system
- **Long-term Retention:** Central server can store logs longer than individual systems
- **Compliance:** Many frameworks (PCI-DSS, SOC2, HIPAA) require centralized logging

### 5. journald Configuration

**Configuration:** `/etc/systemd/journald.conf`

**Critical Settings:**
```ini
[Journal]
Storage=persistent
Compress=yes
ForwardToSyslog=yes
MaxRetentionSec=31536000  # 1 year
```

**Setting Explanations:**

**Storage=persistent:**
- Writes logs to `/var/log/journal/` (survives reboots)
- Alternative values: `volatile` (RAM only), `auto`, `none`
- **Why Important:** Ensures logs survive system reboots for forensic analysis

**Compress=yes:**
- Compresses rotated journal files with XZ compression
- Can reduce storage by 80-90%
- **Why Important:** Allows longer retention periods without excessive disk usage

**ForwardToSyslog=yes:**
- Sends journal entries to rsyslog
- Enables rsyslog features (remote logging, filtering, formatting)
- **Why Important:** Provides dual logging (journald + rsyslog) for redundancy

### 6. Log File Permissions

**Expected Permissions:**

| File | Mode | Owner | Group | Purpose |
|------|------|-------|-------|---------|
| /var/log/messages | 0640 | root | root | General system logs |
| /var/log/secure | 0640 | root | root | Authentication logs (sensitive) |
| /var/log/maillog | 0640 | root | root | Mail server logs |
| /var/log/cron | 0640 | root | root | Cron job logs |
| /var/log/boot.log | 0640 | root | root | Boot process logs |

**Permission Breakdown (0640):**
- **6 (owner)**: Read + Write (rw-)
- **4 (group)**: Read only (r--)
- **0 (other)**: No access (---)

**Security Risks:**
- **World-readable logs (0644):** May expose sensitive information (usernames, system details, application data)
- **Group-writable logs (0660):** Members of root group could tamper with logs
- **World-writable logs (0666):** Any user could tamper with logs, destroy audit trail

### 7. Excessive Permission Detection

**Check Method:**
- Find all `.log` files in `/var/log` recursively
- Check each file's permissions
- Flag files with:
  - World-writable (others can write)
  - Group-writable (unless explicitly approved)

**Common Issues:**
- Application logs created with overly permissive defaults
- Manual log file creation without proper umask
- Legacy configurations from older systems

### 8. Logrotate Configuration

**Configuration:** `/etc/logrotate.conf` and `/etc/logrotate.d/*.conf`

**Why Important:**
- Prevents log partitions from filling up
- Compresses old logs to save space
- Implements retention policies
- Maintains log file permissions after rotation

**Example Configuration:**
```
/var/log/messages {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    sharedscripts
    postrotate
        /usr/bin/systemctl kill -s HUP rsyslog.service >/dev/null 2>&1 || true
    endscript
}
```

## Common Issues Detected

**Critical Issues:**
- rsyslog not installed or not running
- journald not configured for persistent storage
- Log files with world-readable permissions (0644)
- Remote logging not configured (required for compliance frameworks)
- $FileCreateMode not set (defaults to 0644)

**Warnings:**
- journald not forwarding to rsyslog (limits centralized logging capability)
- Compression not enabled (wastes disk space)
- Logrotate not installed (risk of filling disk)
- Log files with excessive permissions

**Informational:**
- Number of logging rules configured
- Specific remote log hosts configured
- Journal retention settings

## Remediation Examples

### Configure rsyslog File Permissions

```bash
# Edit /etc/rsyslog.conf
echo "\$FileCreateMode 0640" >> /etc/rsyslog.conf

# Restart rsyslog
systemctl restart rsyslog
```

### Configure journald for Persistent Storage

```bash
# Edit /etc/systemd/journald.conf
cat > /etc/systemd/journald.conf <<EOF
[Journal]
Storage=persistent
Compress=yes
ForwardToSyslog=yes
MaxRetentionSec=31536000
EOF

# Restart systemd-journald
systemctl restart systemd-journald
```

### Fix Log File Permissions

```bash
# Fix individual file
chmod 0640 /var/log/messages
chown root:root /var/log/messages

# Fix all log files in /var/log
find /var/log -type f -name "*.log" -exec chmod 0640 {} \;
find /var/log -type f -name "*.log" -exec chown root:root {} \;
```

### Configure Remote Logging

```bash
# Create remote logging configuration
cat > /etc/rsyslog.d/remote.conf <<EOF
# Send all logs to remote server via TCP (reliable)
*.* @@logserver.example.com:514

# Optional: Send critical alerts to backup server
*.crit @@backup-logserver.example.com:514
EOF

# Restart rsyslog
systemctl restart rsyslog

# Verify configuration
logger -p user.info "Test message from $(hostname)"
# Check remote server to confirm receipt
```

### Install and Configure Logrotate

```bash
# Install logrotate if missing
dnf install -y logrotate

# Create custom logrotate configuration
cat > /etc/logrotate.d/custom-app <<EOF
/var/log/custom-app/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 root root
    sharedscripts
    postrotate
        /usr/bin/systemctl reload custom-app.service > /dev/null 2>&1 || true
    endscript
}
EOF

# Test logrotate configuration
logrotate -d /etc/logrotate.conf
```

## Performance Considerations

This role makes several system calls:
- Package queries (rsyslog, logrotate)
- Service status checks (rsyslog, systemd-journald)
- File reads (/etc/rsyslog.conf, /etc/systemd/journald.conf, /etc/logrotate.conf)
- Directory traversal (find all .log files in /var/log)
- Stat operations on all log files

**Typical runtime:** 5-10 seconds per host

**Optimization:**
- Uses `find` with file type and pattern filters to minimize stat calls
- Slurp only reads configuration files once
- Systemd module caches service status

## Example Output

```
TASK [Display logging configuration summary] *********************************
ok: [server1] => {
    "msg": [
        "==========================================",
        "Logging Configuration Facts",
        "==========================================",
        "rsyslog:",
        "  Installed: True",
        "  Service Active: True",
        "  Service Enabled: True",
        "  FileCreateMode: 0640",
        "  Logging Rules: 12",
        "  Remote Logging: True",
        "",
        "journald:",
        "  Service Active: True",
        "  Storage Mode: persistent",
        "  Compress: yes",
        "  Forward to Syslog: yes",
        "",
        "Log File Permissions:",
        "  Compliant Files: 4/5",
        "  Excessive Permissions: 1 files",
        "",
        "Compliance Summary:",
        "  rsyslog: True",
        "  journald: True",
        "  Log Permissions: False",
        "  Remote Logging: True",
        "=========================================="
    ]
}
```

## Integration with Other Roles

This role complements:
- `gather_auditd_facts` - Audit logging on /var/log/audit
- `gather_filesystem_config` - /var/log partition verification
- `gather_file_permissions` - System file permissions including log files

## Logging Architecture Decision Tree

```
┌─────────────────────────────────────┐
│  RHEL 9 Logging Architecture        │
└─────────────────────────────────────┘
                 │
                 ▼
    ┌────────────────────────┐
    │  systemd-journald      │
    │  (Primary collector)   │
    │  Storage=persistent    │
    │  Compress=yes          │
    └────────────────────────┘
                 │
                 │ ForwardToSyslog=yes
                 ▼
    ┌────────────────────────┐
    │  rsyslog               │
    │  (Processing & routing)│
    │  $FileCreateMode 0640  │
    └────────────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
┌──────────────┐   ┌──────────────┐
│ Local Files  │   │ Remote Server│
│ /var/log/*   │   │ @@logserver  │
│ (Short term) │   │ (Long term)  │
└──────────────┘   └──────────────┘
        │
        ▼
┌──────────────┐
│  logrotate   │
│  (Rotation)  │
└──────────────┘
```

## License

Apache-2.0
## Author Information

Created by Tim Coulter & Claude for CIS RHEL 9 compliance automation.
