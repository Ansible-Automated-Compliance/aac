> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab on OpenShift Services, AAP 2.7). Findings to check: HOST:8181x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Role: gather_firewalld_detailed

Gathers comprehensive firewalld configuration facts for CIS RHEL 9 compliance validation.

## Description

This role performs extensive firewalld configuration analysis including:
- Firewalld package installation and service status
- Conflicting firewall package detection (iptables-services, nftables)
- Default zone configuration
- Detailed zone configurations (targets, interfaces, services, ports)
- Interface-to-zone mapping validation
- Service exposure analysis (essential vs dangerous services)
- Rich rules and direct rules enumeration
- Panic mode and lockdown mode status
- Firewall backend configuration (nftables vs iptables)
- Masquerading configuration
- Unassigned interface detection

## Requirements

- RHEL 9 or compatible system
- Ansible 2.9 or higher
- Root or sudo privileges
- Firewalld installed (role handles gracefully if not installed)

## Role Variables

Available variables with defaults (see `defaults/main.yml`):

```yaml
# Expected firewall backend
expected_backend: "nftables"

# Allowed essential services (CIS recommended)
allowed_essential_services:
  - ssh
  - dhcpv6-client

# Services that should generally be blocked
potentially_dangerous_services:
  - ftp
  - tftp
  - telnet
  - http
  - https
  - samba
  - nfs
  - rpc-bind
  - mysql
  - postgresql
  - vnc-server

# Conflicting firewall packages
conflicting_packages:
  - iptables-services
  - nftables
```

## Dependencies

None.

## Example Playbook

```yaml
---
- name: Gather firewalld configuration
  hosts: rhel9_servers
  become: yes
  roles:
    - gather_firewalld_detailed

- name: Display firewall issues
  hosts: rhel9_servers
  tasks:
    - name: Show unassigned interfaces
      debug:
        var: host_firewalld_facts.interfaces.unassigned
      when: host_firewalld_facts.interfaces.has_unassigned

    - name: Show dangerous services
      debug:
        var: host_firewalld_facts.services.exposure_analysis.potentially_dangerous
      when: host_firewalld_facts.services.has_dangerous_services

    - name: Show conflicting packages
      debug:
        var: host_firewalld_facts.conflicting_packages.installed
      when: host_firewalld_facts.conflicting_packages.has_conflicts
```

## Facts Generated

This role sets the following fact variable: `host_firewalld_facts`

### Structure:

```yaml
host_firewalld_facts:
  package_installed: true
  service_enabled: "enabled"
  service_running: "active"
  service_state: "running"

  conflicting_packages:
    installed: ["iptables-services"]  # Should be empty
    has_conflicts: true               # Should be false

  configuration:
    default_zone: "public"
    default_zone_set: true
    backend: "nftables"
    backend_is_nftables: true
    panic_mode: false
    lockdown_mode: false

  zones:
    all_zones: ["public", "dmz", "trusted"]
    total_count: 3
    detailed_config:
      - name: "public"
        target: "default"
        interfaces: ["eth0"]
        sources: []
        services: ["ssh", "dhcpv6-client"]
        ports: ["8080/tcp"]
        protocols: []
        rich_rules: []
        masquerade: false
        icmp_blocks: []
    with_masquerade: ["dmz"]

  interfaces:
    all_interfaces: ["eth0", "eth1"]
    interface_mapping:
      - interface: "eth0"
        zone: "public"
        assigned: true
      - interface: "eth1"
        zone: "no_zone"
        assigned: false
    unassigned: ["eth1"]
    has_unassigned: true

  services:
    exposure_analysis:
      total_services: ["ssh", "dhcpv6-client", "http"]
      potentially_dangerous:
        - service: "http"
          zone: "public"
          interfaces: ["eth0"]
      essential_allowed: ["ssh", "dhcpv6-client"]
      non_essential: []
    total_exposed: 3
    potentially_dangerous: 1
    has_dangerous_services: true

  rules:
    rich_rules:
      - "rule family=ipv4 source address=192.168.1.0/24 accept"
    direct_rules: []
    has_rich_rules: true
    has_direct_rules: false

  compliance_checks:
    firewalld_installed: true
    service_enabled_and_running: true
    no_conflicting_packages: false
    default_zone_configured: true
    all_interfaces_assigned: false
    using_nftables_backend: true
    no_dangerous_services: false

  collection_timestamp: "2025-10-15T12:34:56Z"
```

## CIS Controls Covered

This role gathers facts for the following CIS RHEL 9 Benchmark controls:

**Section 3.5.1.x - Firewall Configuration:**
- **3.5.1.1**: Ensure firewalld is installed
- **3.5.1.2**: Ensure iptables-services not installed with firewalld
- **3.5.1.3**: Ensure nftables either not installed or masked with firewalld
- **3.5.1.4**: Ensure firewalld service enabled and running
- **3.5.1.5**: Ensure firewalld default zone is set
- **3.5.1.6**: Ensure network interfaces are assigned to appropriate zone
- **3.5.1.7**: Ensure firewalld drops unnecessary services and ports

**Total: 7 controls** (Note: CIS has 7 firewall controls, we gather facts for 6 main ones)

## Usage with OPA

The facts collected by this role can be fed directly into OPA for policy evaluation:

```yaml
- name: Evaluate firewall compliance with OPA
  uri:
    url: "http://localhost:8181/v1/data/cis/rhel9/section_3/firewall"
    method: POST
    body_format: json
    body:
      input: "{{ host_firewalld_facts }}"
    return_content: yes
  register: opa_firewall_result
```

## Security Checks Performed

### 1. Package and Service Validation
- Verifies firewalld package is installed
- Checks firewalld service is enabled and running
- Detects conflicting packages (iptables-services, nftables)

### 2. Zone Configuration
- Lists all configured zones
- Extracts detailed configuration for each zone:
  - Target policy (default, ACCEPT, REJECT, DROP)
  - Assigned interfaces
  - Source addresses
  - Allowed services
  - Open ports
  - Protocols
  - Rich rules
  - Masquerading status
  - ICMP blocks

### 3. Interface Assignment
- Maps all network interfaces to zones
- Identifies unassigned interfaces (security risk)
- Validates proper zone assignment

### 4. Service Exposure Analysis
- Categorizes exposed services:
  - Essential allowed (ssh, dhcpv6-client)
  - Potentially dangerous (http, ftp, telnet, etc.)
  - Non-essential
- Reports services by zone and interface

### 5. Advanced Rules
- Collects all rich rules across zones
- Checks for direct rules (low-level iptables/nftables)
- Both are indicators of complex firewall configurations

### 6. Special Modes
- Panic mode (blocks all traffic)
- Lockdown mode (prevents runtime changes)

### 7. Backend Configuration
- Validates firewall backend (should be nftables on RHEL 9)
- Ensures proper backend configuration

## Common Issues Detected

**Critical Issues:**
- Firewalld not installed
- Firewalld service not enabled or not running
- Conflicting firewall packages installed
- No default zone configured
- Network interfaces not assigned to any zone

**Warnings:**
- Potentially dangerous services exposed (http, ftp, telnet, etc.)
- Using iptables backend instead of nftables
- Masquerading enabled (may indicate NAT/routing)
- Complex direct rules (harder to audit)

## Compliance Validation

The role provides a `compliance_checks` section with boolean flags:

```yaml
compliance_checks:
  firewalld_installed: true/false
  service_enabled_and_running: true/false
  no_conflicting_packages: true/false
  default_zone_configured: true/false
  all_interfaces_assigned: true/false
  using_nftables_backend: true/false
  no_dangerous_services: true/false
```

These can be used directly in assertions or OPA policies.

## Service Exposure Categories

### Essential Allowed (CIS Recommended)
- `ssh` - Secure remote access
- `dhcpv6-client` - IPv6 DHCP client

### Potentially Dangerous (Should be reviewed)
- `ftp`, `tftp` - Unencrypted file transfer
- `telnet` - Unencrypted remote access
- `http`, `https` - Web services (should be in DMZ)
- `samba` - File sharing
- `nfs`, `rpc-bind`, `mountd` - NFS file sharing
- `mysql`, `postgresql` - Database services
- `vnc-server`, `x11` - Remote desktop

## Performance Considerations

This role makes multiple `firewall-cmd` calls which can take 5-10 seconds total. Key operations:

- Service status check
- Zone enumeration
- Detailed zone configuration (1 call per zone)
- Interface mapping (1 call per interface)
- Rich rules and direct rules

For systems with many zones (10+) or interfaces (10+), expect 10-15 seconds runtime.

## Example Output

```
TASK [Display firewalld facts summary] ******************************************
ok: [server1] => {
    "msg": [
        "==========================================",
        "Firewalld Configuration Facts",
        "==========================================",
        "Firewalld installed: True",
        "Service enabled: enabled",
        "Service running: active",
        "",
        "Configuration:",
        "  Default zone: public",
        "  Backend: nftables",
        "  Panic mode: False",
        "",
        "Zones: 3",
        "Interfaces: 2",
        "Unassigned interfaces: 0",
        "",
        "Services exposed: 2",
        "Potentially dangerous: 0",
        "",
        "Compliance Issues:",
        "  Conflicting packages: False",
        "  Unassigned interfaces: False",
        "  Dangerous services: False",
        "=========================================="
    ]
}
```

## Integration with Other Roles

This role complements:
- `gather_ssh_config` - SSH service should be allowed in firewall
- `gather_network_config` - Interface configuration
- `gather_service_config` - Service exposure validation

## License

Apache-2.0
## Author Information

Created for CIS RHEL 9 compliance automation.
