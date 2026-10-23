> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab on OpenShift Services, AAP 2.7). Findings to check: none specific — unreviewed for 320 days.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Role: gather_network_config

**Authors:** Tim Coulter & Claude
**Date:** October 15, 2025

Gathers comprehensive network and kernel parameter configuration for CIS RHEL 9 compliance validation.

## Description

This role performs extensive network security configuration analysis including:
- Kernel network parameters (sysctl)
- IP forwarding status (IPv4/IPv6)
- ICMP configuration
- IPv6 status and configuration
- Network interface inventory
- Wireless interface detection
- Routing configuration
- Firewall status
- Persistent sysctl configuration files

## Requirements

- RHEL 9 or compatible system
- Ansible 2.9 or higher
- Root or sudo privileges

## Role Variables

Available variables with defaults (see `defaults/main.yml`):

```yaml
# Expected kernel network parameters (CIS 3.x)
expected_sysctl_parameters:
  net.ipv4.ip_forward:
    value: 0
    description: "Disable IPv4 forwarding"
  net.ipv4.conf.all.send_redirects:
    value: 0
    description: "Disable sending ICMP redirects"
  net.ipv4.conf.all.accept_source_route:
    value: 0
    description: "Do not accept source routed packets"
  net.ipv4.conf.all.accept_redirects:
    value: 0
    description: "Do not accept ICMP redirects"
  net.ipv4.conf.all.log_martians:
    value: 1
    description: "Log suspicious packets"
  net.ipv4.tcp_syncookies:
    value: 1
    description: "Enable SYN flood protection"
  # ... (28 total parameters)

# IPv6 configuration
ipv6_disabled: false

# Wireless interfaces (should not exist on servers)
wireless_interface_prefixes:
  - wlan
  - wlp
```

## Dependencies

None.

## Example Playbook

```yaml
---
- name: Gather network configuration
  hosts: rhel9_servers
  become: yes
  roles:
    - gather_network_config

- name: Display network configuration issues
  hosts: rhel9_servers
  tasks:
    - name: Show non-compliant sysctl parameters
      debug:
        var: item
      loop: "{{ host_network_facts.sysctl_parameters.non_compliant_params }}"

    - name: Show IP forwarding status
      debug:
        msg:
          - "IPv4 forwarding: {{ host_network_facts.ip_forwarding.ipv4_forwarding }}"
          - "IPv6 forwarding: {{ host_network_facts.ip_forwarding.ipv6_forwarding }}"
          - "Compliant: {{ host_network_facts.ip_forwarding.fully_compliant }}"
      when: not host_network_facts.ip_forwarding.fully_compliant

    - name: Show wireless interfaces (if any)
      debug:
        var: host_network_facts.wireless_interfaces.interfaces
      when: host_network_facts.wireless_interfaces.has_wireless
```

## Facts Generated

This role sets the following fact variable: `host_network_facts`

### Structure (abbreviated):

```yaml
host_network_facts:
  sysctl_parameters:
    expected_parameters:
      - net.ipv4.ip_forward
      - net.ipv4.conf.all.send_redirects
      - net.ipv4.conf.all.accept_redirects
      # ... (28 total)
    analysis:
      - parameter: net.ipv4.ip_forward
        expected_value: "0"
        current_value: "0"
        description: "Disable IPv4 forwarding"
        compliant: true
        severity: none
      - parameter: net.ipv4.conf.all.send_redirects
        expected_value: "0"
        current_value: "1"
        description: "Disable sending ICMP redirects"
        compliant: false
        severity: high
    compliant_count: 26
    non_compliant_count: 2
    all_compliant: false
    non_compliant_params:
      - parameter: net.ipv4.conf.all.send_redirects
        current_value: "1"
        expected_value: "0"

  ip_forwarding:
    ipv4_forwarding: 0
    ipv6_forwarding: 0
    ipv4_compliant: true
    ipv6_compliant: true
    fully_compliant: true

  ipv6:
    status: enabled
    disabled: false
    address_count: 3
    compliant: true

  network_interfaces:
    all_interfaces:
      - name: ens192
        family: inet
        address: 192.168.1.100/24
      - name: ens192
        family: inet6
        address: fe80::250:56ff:fe89:abcd/64
    interface_count: 2

  wireless_interfaces:
    interfaces: []
    count: 0
    has_wireless: false
    compliant: true

  persistent_config:
    sysctl_conf:
      net.ipv4.ip_forward: 0
      net.ipv4.conf.all.send_redirects: 0
    sysctl_d_files:
      - 99-cis-hardening.conf
      - 50-network-security.conf
    sysctl_d_params:
      99-cis-hardening.conf:
        net.ipv4.tcp_syncookies: 1
        net.ipv4.conf.all.log_martians: 1

  routing:
    table:
      routes:
        - default via 192.168.1.1 dev ens192 proto static metric 100
        - 192.168.1.0/24 dev ens192 proto kernel scope link src 192.168.1.100 metric 100
      route_count: 2
      has_default_route: true

  networkmanager:
    active: true
    enabled: true

  firewall:
    type: firewalld
    active: true
    compliant: true

  compliance_checks:
    all_sysctl_compliant: false
    ip_forwarding_disabled: true
    ipv6_compliant: true
    no_wireless_interfaces: true
    firewall_active: true

  collection_timestamp: "2025-10-15T12:34:56Z"
```

## CIS Controls Covered

This role gathers facts for the following CIS RHEL 9 Benchmark controls:

**Section 3.1.x - Network Parameters (Host Only) (2 controls):**
- **3.1.1**: Ensure IP forwarding is disabled
- **3.1.2**: Ensure packet redirect sending is disabled

**Section 3.2.x - Network Parameters (Host and Router) (9 controls):**
- **3.2.1**: Ensure source routed packets are not accepted
- **3.2.2**: Ensure ICMP redirects are not accepted
- **3.2.3**: Ensure secure ICMP redirects are not accepted
- **3.2.4**: Ensure suspicious packets are logged
- **3.2.5**: Ensure broadcast ICMP requests are ignored
- **3.2.6**: Ensure bogus ICMP responses are ignored
- **3.2.7**: Ensure Reverse Path Filtering is enabled
- **3.2.8**: Ensure TCP SYN Cookies is enabled
- **3.2.9**: Ensure IPv6 router advertisements are not accepted

**Section 3.3.x - IPv6 (3 controls):**
- **3.3.1**: Ensure IPv6 is disabled (if not used)
- **3.3.2**: Ensure wireless interfaces are disabled (informational)
- **3.3.3**: Ensure IPv6 forwarding is disabled

**Additional Network Security (~6 controls):**
- Persistent sysctl configuration validation
- Network interface inventory
- Routing table analysis
- NetworkManager status
- Firewall presence check
- Wireless interface detection

**Total: ~20 controls**

## Security Checks Performed

### 1. IP Forwarding

**Parameters:**
- `net.ipv4.ip_forward`
- `net.ipv6.conf.all.forwarding`

**Expected Value:** 0 (disabled)

**Why Important:**
- **Servers should NOT forward packets** between network interfaces
- IP forwarding turns a server into a router
- If compromised, attacker can use server as pivot point to route malicious traffic
- **Exception:** Legitimate routers, VPN gateways, or containers (Docker/Kubernetes)

**Attack Scenario:**
```
Attacker compromises web server with IP forwarding enabled
→ Uses server to route traffic between DMZ and internal network
→ Bypasses firewall rules designed to prevent DMZ→Internal access
```

### 2. ICMP Redirect Handling

**Send Redirects:**
- `net.ipv4.conf.all.send_redirects = 0`
- `net.ipv4.conf.default.send_redirects = 0`

**Accept Redirects:**
- `net.ipv4.conf.all.accept_redirects = 0`
- `net.ipv6.conf.all.accept_redirects = 0`

**Secure Redirects:**
- `net.ipv4.conf.all.secure_redirects = 0`

**What are ICMP Redirects?**
- Router sends ICMP redirect to inform host of a better route
- Example: "Don't send packets to me, send them directly to 192.168.1.254"

**Why Disable?**
- **Man-in-the-Middle Attack:** Attacker sends fake redirects to hijack traffic
- **Traffic Interception:** Reroute victim's traffic through attacker's system
- **Not needed:** Static routes or DHCP provide routing information

**Attack Scenario:**
```
Attacker on same LAN sends ICMP redirect:
"For reaching 8.8.8.8, use 192.168.1.100 as gateway"
→ Victim's traffic to Google DNS now goes through attacker
→ Attacker intercepts/modifies DNS responses
```

### 3. Source Routing

**Parameters:**
- `net.ipv4.conf.all.accept_source_route = 0`
- `net.ipv6.conf.all.accept_source_route = 0`

**What is Source Routing?**
- Sender specifies the path packets should take
- Used for network diagnostics and troubleshooting

**Why Disable?**
- **Bypass Firewall Rules:** Attacker specifies route that bypasses firewall
- **Spoof Source Address:** Make packets appear from trusted source
- **No legitimate use** in modern production networks

### 4. Martian Packets

**Parameter:** `net.ipv4.conf.all.log_martians = 1`

**What are Martian Packets?**
- Packets with impossible or reserved source addresses
- Examples:
  - Source: 127.0.0.1 (loopback) arriving on external interface
  - Source: 0.0.0.0, 255.255.255.255
  - Source: 10.0.0.0/8 arriving on Internet interface (when you don't use 10.0.0.0/8)

**Why Log?**
- **Attack Detection:** Spoofed packets, reconnaissance, DoS attacks
- **Misconfiguration:** Routing problems, asymmetric routing
- **Forensics:** Evidence of attack attempts

### 5. Broadcast ICMP

**Parameter:** `net.ipv4.icmp_echo_ignore_broadcasts = 1`

**Attack:** Smurf Attack
```
Attacker sends ICMP echo request to broadcast address (192.168.1.255)
→ Spoofs source address as victim (192.168.1.100)
→ All 254 hosts on network respond to victim
→ Victim receives 254x amplified traffic (DoS)
```

**Mitigation:** Ignore broadcast ICMP, preventing participation in Smurf attacks

### 6. Bogus ICMP Responses

**Parameter:** `net.ipv4.icmp_ignore_bogus_error_responses = 1`

**What:** Malformed ICMP error messages that don't correspond to any sent packet

**Why Ignore:**
- **Resource Exhaustion:** Processing invalid ICMP wastes CPU
- **Kernel Vulnerabilities:** Historical bugs triggered by malformed ICMP
- **Attack Tool Signatures:** Certain attacks generate bogus ICMP

### 7. Reverse Path Filtering (RPF)

**Parameter:**
- `net.ipv4.conf.all.rp_filter = 1`
- `net.ipv4.conf.default.rp_filter = 1`

**What is RPF?**
- Kernel checks if reply packet would go back out same interface
- **Strict Mode (1):** Drop if incoming interface != outgoing interface for reply
- **Loose Mode (2):** Drop only if no route back to source exists

**Why Important:**
- **Prevents IP Spoofing:** Attacker can't send packets with fake source IPs
- **Anti-DDoS:** Makes reflection/amplification attacks harder

**Example:**
```
Packet arrives on eth0 with source 8.8.8.8
Kernel checks: Would reply to 8.8.8.8 go out eth0?
If no → Packet is spoofed → DROP
```

### 8. TCP SYN Cookies

**Parameter:** `net.ipv4.tcp_syncookies = 1`

**Attack:** TCP SYN Flood
```
Attacker sends thousands of SYN packets (connection requests)
→ Server allocates resources for each half-open connection
→ Server's connection table fills up
→ Legitimate users can't connect (DoS)
```

**Mitigation: SYN Cookies**
- Don't allocate resources until connection completes
- Encode connection info in TCP sequence number
- **Tradeoff:** Disables some TCP options (window scaling) during attack

### 9. IPv6 Router Advertisements

**Parameters:**
- `net.ipv6.conf.all.accept_ra = 0`
- `net.ipv6.conf.default.accept_ra = 0`

**What are Router Advertisements (RA)?**
- IPv6 routers announce their presence
- Provide network prefix, default gateway, DNS servers

**Why Disable on Servers?**
- **Rogue Router Attack:** Attacker sends fake RAs with malicious default gateway/DNS
- **Server Config Should Be Static:** Servers shouldn't auto-configure from RAs
- **Man-in-the-Middle:** Attacker becomes default gateway via fake RA

### 10. IPv6 Status

**Why Disable IPv6?**
- If not using IPv6, it's unnecessary attack surface
- Historical vulnerabilities in IPv6 stack
- Dual-stack complexity (must secure both IPv4 and IPv6)

**Why Keep IPv6 Enabled?**
- Modern standard (IPv4 exhaustion)
- Some applications require it
- Disabling doesn't eliminate risk (tunneling attacks: 6to4, Teredo)

**CIS Recommendation:** Disable if not used, otherwise properly secure it

## Common Issues Detected

**Critical Issues:**
- IP forwarding enabled on non-router systems
- ICMP redirects accepted (enables MITM attacks)
- Source routing accepted (firewall bypass)
- TCP SYN cookies disabled (vulnerable to SYN flood)
- Reverse path filtering disabled (IP spoofing possible)

**Warnings:**
- Martian packets not logged (blind to spoofing attempts)
- Broadcast ICMP not ignored (Smurf attack participant)
- IPv6 router advertisements accepted
- Wireless interfaces detected on server

**Informational:**
- IPv6 enabled but not used (address_count > 0 but no traffic)
- Multiple sysctl configuration files (potential conflicts)
- NetworkManager active (may override manual network config)

## Remediation Examples

### Configure Sysctl Parameters Temporarily

```bash
# Disable IP forwarding
sysctl -w net.ipv4.ip_forward=0
sysctl -w net.ipv6.conf.all.forwarding=0

# Disable ICMP redirects
sysctl -w net.ipv4.conf.all.send_redirects=0
sysctl -w net.ipv4.conf.all.accept_redirects=0
sysctl -w net.ipv6.conf.all.accept_redirects=0

# Enable reverse path filtering
sysctl -w net.ipv4.conf.all.rp_filter=1

# Enable SYN cookies
sysctl -w net.ipv4.tcp_syncookies=1

# Verify
sysctl net.ipv4.ip_forward
```

### Configure Sysctl Parameters Persistently

```bash
# Create CIS hardening sysctl file
cat > /etc/sysctl.d/99-cis-network-hardening.conf <<EOF
# CIS 3.1.1 - Disable IP forwarding
net.ipv4.ip_forward = 0
net.ipv6.conf.all.forwarding = 0

# CIS 3.1.2 - Disable packet redirect sending
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0

# CIS 3.2.1 - Disable source routed packets
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0
net.ipv6.conf.default.accept_source_route = 0

# CIS 3.2.2 - Disable ICMP redirects
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0

# CIS 3.2.3 - Disable secure ICMP redirects
net.ipv4.conf.all.secure_redirects = 0
net.ipv4.conf.default.secure_redirects = 0

# CIS 3.2.4 - Log suspicious packets
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1

# CIS 3.2.5 - Ignore broadcast ICMP
net.ipv4.icmp_echo_ignore_broadcasts = 1

# CIS 3.2.6 - Ignore bogus ICMP responses
net.ipv4.icmp_ignore_bogus_error_responses = 1

# CIS 3.2.7 - Enable reverse path filtering
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1

# CIS 3.2.8 - Enable TCP SYN cookies
net.ipv4.tcp_syncookies = 1

# CIS 3.2.9 - Disable IPv6 router advertisements
net.ipv6.conf.all.accept_ra = 0
net.ipv6.conf.default.accept_ra = 0
EOF

# Apply settings
sysctl -p /etc/sysctl.d/99-cis-network-hardening.conf

# Verify
sysctl -a | grep -E '^(net\.ipv4\.|net\.ipv6\.)'
```

### Disable IPv6 Completely

```bash
# Method 1: Kernel parameter (requires reboot)
# Edit /etc/default/grub
GRUB_CMDLINE_LINUX="... ipv6.disable=1"

# Regenerate grub config
grub2-mkconfig -o /boot/grub2/grub.cfg

# Reboot
reboot

# Method 2: Sysctl (runtime, doesn't survive reboot alone)
cat > /etc/sysctl.d/99-disable-ipv6.conf <<EOF
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
EOF

sysctl -p /etc/sysctl.d/99-disable-ipv6.conf
```

## Performance Considerations

This role makes several system calls:
- `sysctl -a` - Read all kernel parameters (~2000 parameters)
- `ip` commands - Interface and routing information
- File reads (/etc/sysctl.conf, /etc/sysctl.d/*.conf)
- Service status checks (NetworkManager, firewall)

**Typical runtime:** 3-6 seconds per host

## Example Output

```
TASK [Display network configuration summary] *********************************
ok: [server1] => {
    "msg": [
        "==========================================",
        "Network Configuration Facts",
        "==========================================",
        "Sysctl Parameters:",
        "  Total Checked: 28",
        "  Compliant: 26",
        "  Non-Compliant: 2",
        "",
        "IP Forwarding:",
        "  IPv4: 0 (Expected: 0)",
        "  IPv6: 0 (Expected: 0)",
        "  Compliant: True",
        "",
        "IPv6 Status:",
        "  Status: enabled",
        "  Addresses: 3",
        "  Compliant: True",
        "",
        "Network Interfaces:",
        "  Total: 2",
        "  Wireless: 0",
        "",
        "Firewall:",
        "  Type: firewalld",
        "  Active: True",
        "",
        "Compliance Summary:",
        "  Sysctl Parameters: False",
        "  IP Forwarding Disabled: True",
        "  No Wireless: True",
        "  Firewall Active: True",
        "=========================================="
    ]
}
```

## Integration with Other Roles

This role complements:
- `gather_firewalld_detailed` - Firewall rules and zone configuration
- `gather_service_config` - Network service status
- `gather_logging_config` - Log martian packets to syslog

## License

Apache-2.0
## Author Information

Created by Tim Coulter & Claude for CIS RHEL 9 compliance automation.
