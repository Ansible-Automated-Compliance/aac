> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab on OpenShift Services, AAP 2.7). Findings to check: none specific — unreviewed for 320 days.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Role: gather_service_config

**Authors:** Tim Coulter & Claude
**Date:** October 15, 2025

Gathers comprehensive service configuration for CIS RHEL 9 compliance validation.

## Description

This role performs extensive service and package analysis including:
- Automounter (autofs) status
- Time synchronization configuration (chronyd/ntpd)
- Unnecessary service detection
- Web server presence
- Client package audit
- X11 packages (for server systems)
- Mail Transfer Agent (MTA) configuration
- Complete enabled/active service inventory

## Requirements

- RHEL 9 or compatible system
- Ansible 2.9 or higher
- Root or sudo privileges

## Role Variables

Available variables with defaults (see `defaults/main.yml`):

```yaml
# Services that should be disabled (CIS 2.x)
unnecessary_services:
  - autofs              # Automounter
  - avahi-daemon        # Avahi Server
  - cups                # CUPS print server
  - dhcpd               # DHCP Server
  - slapd               # LDAP server
  - nfs-server          # NFS server
  - rpcbind             # RPC
  - bind                # DNS Server
  - vsftpd              # FTP Server
  - httpd               # Apache web server
  - dovecot             # IMAP/POP3 server
  - smb                 # Samba file server
  - squid               # HTTP Proxy
  - snmpd               # SNMP Server
  - ypserv              # NIS Server
  - rsh.socket          # RSH server
  - telnet.socket       # Telnet server
  - tftp.socket         # TFTP server

# Services that should be enabled
required_services:
  - chronyd             # Time synchronization
  - systemd-journald    # Logging
  - rsyslog             # Logging
  - auditd              # Auditing
  - firewalld           # Firewall

# Time synchronization services
time_sync_services:
  - chronyd
  - ntpd
  - systemd-timesyncd

# Client packages that should be removed
unnecessary_client_packages:
  - telnet
  - rsh
  - talk
  - ypbind
  - tftp
```

## Dependencies

None.

## Example Playbook

```yaml
---
- name: Gather service configuration
  hosts: rhel9_servers
  become: yes
  roles:
    - gather_service_config

- name: Display service issues
  hosts: rhel9_servers
  tasks:
    - name: Show active unnecessary services
      debug:
        var: item
      loop: "{{ host_service_facts.unnecessary_services.non_compliant }}"

    - name: Show time sync issues
      debug:
        msg:
          - "Active service: {{ host_service_facts.time_synchronization.active_service }}"
          - "Compliant: {{ host_service_facts.time_synchronization.compliant }}"
      when: not host_service_facts.time_synchronization.compliant

    - name: Show installed client packages
      debug:
        var: host_service_facts.client_packages.installed_packages
      when: host_service_facts.client_packages.any_installed
```

## Facts Generated

This role sets the following fact variable: `host_service_facts`

### Structure (abbreviated):

```yaml
host_service_facts:
  autofs:
    installed: false
    active: false
    enabled: false
    compliant: true

  time_synchronization:
    packages:
      - package: chronyd
        installed: true
        version: "chrony-4.3-1.el9.x86_64"
      - package: ntpd
        installed: false
    services:
      - service: chronyd
        active: true
        enabled: true
        state: active
    active_service: chronyd
    has_active_service: true
    compliant: true

  chronyd:
    installed: true
    version: "chrony-4.3-1.el9.x86_64"
    service_active: true
    service_enabled: true
    config:
      servers:
        - 0.rhel.pool.ntp.org
        - 1.rhel.pool.ntp.org
      pools:
        - 2.rhel.pool.ntp.org
      options: [...]
    servers_configured: 2
    pools_configured: 1
    has_time_sources: true
    compliant: true

  unnecessary_services:
    analysis:
      - service: avahi-daemon
        found: true
        active: true
        enabled: true
        state: active
        unit_file_state: enabled
        compliant: false
        risk_level: high
      - service: cups
        found: true
        active: false
        enabled: false
        compliant: true
        risk_level: low
    total_checked: 21
    found_active: 1
    found_enabled: 1
    non_compliant:
      - service: avahi-daemon
        active: true
        enabled: true
        compliant: false
        risk_level: high
    non_compliant_count: 1
    all_compliant: false

  webserver:
    packages:
      - package: httpd
        installed: false
        compliant: true
      - package: nginx
        installed: false
        compliant: true
    any_installed: false
    compliant: true

  client_packages:
    analysis:
      - package: telnet
        installed: false
        compliant: true
        severity: none
    any_installed: false
    installed_packages: []
    compliant: true

  x11:
    packages:
      - package: xorg-x11-server-common
        installed: false
    any_installed: false
    compliant: true

  mta:
    packages:
      - package: postfix
        installed: true
        version: "postfix-3.5.9-19.el9.x86_64"
    services:
      - service: postfix
        active: true
        enabled: true
        state: active
    active_mta: postfix
    has_mta: true

  all_services:
    enabled:
      services: [chronyd, firewalld, rsyslog, ...]
      count: 42
    active:
      services: [chronyd, firewalld, rsyslog, ...]
      count: 38

  compliance_checks:
    autofs_disabled: true
    time_sync_configured: true
    chronyd_running: true
    chronyd_has_servers: true
    no_unnecessary_services: false
    no_webserver: true
    no_client_packages: true
    no_x11: true

  collection_timestamp: "2025-10-15T12:34:56Z"
```

## CIS Controls Covered

This role gathers facts for the following CIS RHEL 9 Benchmark controls:

**Section 1.1.23 - Disable Automounting:**
- **1.1.23**: Ensure autofs services are not enabled

**Section 2.1.x - Time Synchronization (2 controls):**
- **2.1.1**: Ensure time synchronization is in use
- **2.1.1.1**: Ensure chronyd is running and enabled

**Section 2.2.x - Special Purpose Services (~20 controls):**
- **2.2.1**: Ensure X Window System is not installed
- **2.2.2**: Ensure Avahi Server is not installed
- **2.2.3**: Ensure CUPS is not installed
- **2.2.4**: Ensure DHCP Server is not installed
- **2.2.5**: Ensure LDAP server is not installed
- **2.2.6**: Ensure DNS server is not installed
- **2.2.7**: Ensure FTP server is not installed
- **2.2.8**: Ensure HTTP server is not installed
- **2.2.9**: Ensure IMAP and POP3 server is not installed
- **2.2.10**: Ensure Samba is not installed
- **2.2.11**: Ensure HTTP Proxy Server is not installed
- **2.2.12**: Ensure net-snmp is not installed
- **2.2.13**: Ensure NIS server is not installed
- **2.2.14**: Ensure telnet server is not installed
- **2.2.15**: Ensure mail transfer agent is configured for local-only mode
- **2.2.16**: Ensure rsync service is not installed
- **2.2.17**: Ensure NFS is not installed
- **2.2.18**: Ensure RPC is not installed

**Section 2.3.x - Service Clients (~7 controls):**
- **2.3.1**: Ensure NIS Client is not installed
- **2.3.2**: Ensure rsh client is not installed
- **2.3.3**: Ensure talk client is not installed
- **2.3.4**: Ensure telnet client is not installed
- **2.3.5**: Ensure LDAP client is not installed
- **2.3.6**: Ensure TFTP client is not installed

**Total: ~30 controls**

## Security Rationale

### Why Disable Unnecessary Services?

**Attack Surface Reduction:**
- Each running service is a potential entry point for attackers
- Vulnerabilities in unused services can be exploited
- Reduces memory/CPU usage

**Example:** Avahi-daemon (zero-conf networking)
- Broadcasts system information on network
- Not needed on servers
- Historical vulnerabilities (CVE-2017-6519, CVE-2021-3468)

### Time Synchronization Importance

**Security Impact:**
- **Log Correlation:** Accurate timestamps critical for incident response
- **Certificate Validation:** SSL/TLS certificates expire; wrong time = validation failures
- **Kerberos Authentication:** Requires time sync within 5 minutes
- **Compliance:** Most frameworks require accurate time

**chronyd vs ntpd vs systemd-timesyncd:**
- **chronyd:** Recommended for RHEL 9, better for systems that disconnect/reconnect
- **ntpd:** Legacy, still used in some environments
- **systemd-timesyncd:** Minimal client, less accurate

**Only ONE should be active** - multiple time sync daemons conflict

### Dangerous Services

**High Risk Services (should never be on servers):**

**rsh/rlogin/rexec:**
- Send credentials in cleartext
- No encryption
- Use SSH instead

**Telnet:**
- Cleartext protocol
- No encryption
- Use SSH instead

**FTP (vsftpd):**
- Credentials in cleartext (unless FTPS/SFTP)
- Complex firewall rules (active/passive modes)
- Use SFTP/SCP instead

**TFTP (trivial FTP):**
- No authentication
- No encryption
- Used for network booting only

**NIS (ypbind/ypserv):**
- Insecure authentication
- Replaced by LDAP
- Legacy system

**SNMP v1/v2 (snmpd):**
- Community strings in cleartext
- Information disclosure
- Use SNMP v3 if needed

**Avahi (avahi-daemon):**
- Broadcasts services on network
- Not needed on servers
- Information leakage

### Medium Risk Services (may be needed)

**HTTP/HTTPS (httpd/nginx):**
- Legitimate if server hosts web applications
- Should be hardened and kept updated
- CIS flags presence, admin must justify

**Samba (smb):**
- Windows file sharing
- Legitimate for file servers
- Many historical vulnerabilities

**Mail Transfer Agent (postfix/sendmail):**
- **Local-only mode acceptable:** System sends alerts via email
- **Open relay DANGEROUS:** Can be abused for spam
- CIS requires local-only configuration

### Client Packages

**Why remove client packages?**
- Prevents users from using insecure protocols
- Reduces attack surface
- Examples:
  - `telnet` package allows users to telnet to systems
  - `rsh` package allows rlogin/rsh connections

## Remediation Examples

### Disable Unnecessary Services

```bash
# Stop and disable a service
systemctl stop avahi-daemon
systemctl disable avahi-daemon
systemctl mask avahi-daemon  # Prevents accidental re-enable

# Verify
systemctl status avahi-daemon
```

### Remove Unnecessary Packages

```bash
# Remove telnet client
dnf remove -y telnet

# Remove X11 (servers don't need GUI)
dnf remove -y xorg-x11-server-*

# Remove insecure service packages
dnf remove -y rsh telnet ypbind tftp
```

### Configure chronyd

```bash
# Install chronyd
dnf install -y chrony

# Configure time servers
cat >> /etc/chrony.conf <<EOF
# Use public NTP servers
server 0.rhel.pool.ntp.org iburst
server 1.rhel.pool.ntp.org iburst
server 2.rhel.pool.ntp.org iburst
server 3.rhel.pool.ntp.org iburst

# Or use organizational NTP servers
# server ntp1.example.com iburst
# server ntp2.example.com iburst
EOF

# Enable and start
systemctl enable chronyd
systemctl start chronyd

# Verify
chronyc sources
chronyc tracking
```

### Configure Postfix for Local-Only

```bash
# Edit /etc/postfix/main.cf
sed -i 's/^inet_interfaces = .*/inet_interfaces = localhost/' /etc/postfix/main.cf

# Restart postfix
systemctl restart postfix

# Verify (should only listen on 127.0.0.1)
ss -tlnp | grep :25
```

## Performance Considerations

This role makes several system calls:
- Multiple `systemctl` status checks (~30 services)
- Package queries via `rpm -q` (~15 packages)
- `systemctl list-unit-files` for all enabled services
- `systemctl list-units` for all active services
- File reads (chrony.conf)

**Typical runtime:** 8-15 seconds per host

## Example Output

```
TASK [Display service configuration summary] *********************************
ok: [server1] => {
    "msg": [
        "==========================================",
        "Service Configuration Facts",
        "==========================================",
        "Time Synchronization:",
        "  Active Service: chronyd",
        "  Compliant: True",
        "",
        "chronyd:",
        "  Installed: True",
        "  Active: True",
        "  Enabled: True",
        "  Servers: 4",
        "  Pools: 0",
        "",
        "Unnecessary Services:",
        "  Total Checked: 21",
        "  Found Active: 2",
        "  Found Enabled: 2",
        "  Non-Compliant: 2",
        "",
        "Package Compliance:",
        "  Web Server Installed: False",
        "  Client Packages Installed: False",
        "  X11 Installed: False",
        "",
        "All Services:",
        "  Enabled: 42",
        "  Active: 38",
        "",
        "Compliance Summary:",
        "  autofs Disabled: True",
        "  Time Sync: True",
        "  No Unnecessary Services: False",
        "  No Web Server: True",
        "=========================================="
    ]
}
```

## Integration with Other Roles

This role complements:
- `gather_network_config` - Network service configuration
- `gather_firewalld_detailed` - Firewall rules for running services
- `gather_auditd_facts` - Auditing of service starts/stops

## Advanced Service Hardening

### Service Isolation with systemd

```bash
# Example: Isolate a web server service
cat > /etc/systemd/system/httpd.service.d/hardening.conf <<EOF
[Service]
# Filesystem isolation
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=/var/www /var/log/httpd

# Network isolation
PrivateNetwork=no
RestrictAddressFamilies=AF_INET AF_INET6

# Privilege restrictions
NoNewPrivileges=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes

# Capability restrictions
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE
EOF

systemctl daemon-reload
systemctl restart httpd
```

## License

Apache-2.0
## Author Information

Created by Tim Coulter & Claude for CIS RHEL 9 compliance automation.
