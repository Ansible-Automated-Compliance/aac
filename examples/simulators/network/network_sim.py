#!/usr/bin/env python3
"""
AAC Network Infrastructure Simulator
Simulates Cisco IOS-XE, Juniper Junos, Palo Alto PAN-OS, and S3 storage
for AAC compliance demo without requiring real network hardware.

Each device type is served on a separate port:
  8091 — Cisco IOS-XE router
  8092 — Juniper Junos switch
  8093 — Palo Alto PAN-OS firewall
  8094 — S3-compatible storage (bucket inventory)

Intentional CIS violations baked into each device for demo impact.
"""
import json
import logging
import os
import threading
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.WARNING, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def _days_ago(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── Cisco IOS-XE Facts ──────────────────────────────────────────────────────
# CIS violations: telnet enabled (CIS 1.1.3), no exec-timeout (CIS 1.2.1),
# SNMP v1 community (CIS 3.3.1), no service password-encryption (CIS 1.1.1)

CISCO_FACTS = {
    "ansible_network_os": "cisco.ios.ios",
    "device_type": "router",
    "hostname": "cisco-core-rtr-01",
    "platform": "Cisco IOS-XE",
    "model": "CSR1000V",
    "serial": "9TKUZGAHFW6",
    "ios_version": "17.3.4a",
    "image": "bootflash:packages.conf",
    "uptime": "47 days, 3 hours, 12 minutes",
    "running_config_hash": "sha256:a1b2c3d4e5f6",
    "interfaces": [
        {"name": "GigabitEthernet1", "ip": "10.0.0.1", "mask": "255.255.255.0",
         "status": "up", "protocol": "up", "description": "WAN Uplink"},
        {"name": "GigabitEthernet2", "ip": "192.168.1.1", "mask": "255.255.255.0",
         "status": "up", "protocol": "up", "description": "LAN Core"},
        {"name": "Loopback0", "ip": "10.255.255.1", "mask": "255.255.255.255",
         "status": "up", "protocol": "up", "description": "Router-ID"},
    ],
    "ssh_config": {
        "version": "2",
        "timeout": 0,          # CIS violation: should be ≤ 60 seconds
        "retries": 5,
        "enabled": True,
    },
    "telnet": {
        "enabled": True,       # CIS violation: telnet should be disabled
        "vty_lines": ["vty 0 4", "vty 5 15"],
    },
    "snmp": {
        "version": "v1",       # CIS violation: SNMPv1 should not be used
        "communities": [
            {"name": "public", "permission": "ro"},   # CIS violation: 'public' community string
            {"name": "private", "permission": "rw"},  # CIS violation: 'private' community string
        ],
        "traps_enabled": False,
    },
    "ntp": {
        "servers": ["pool.ntp.org"],
        "authentication_enabled": False,  # CIS violation: NTP auth should be enabled
        "synchronized": True,
    },
    "aaa": {
        "authentication_login": "local",
        "authorization_exec": "none",     # CIS violation: exec authorization should be configured
        "accounting": False,              # CIS violation: accounting should be enabled
    },
    "logging": {
        "enabled": True,
        "buffered_size": 16384,
        "trap_level": "informational",
        "hosts": ["192.168.1.100"],
        "source_interface": "Loopback0",
    },
    "password_policy": {
        "service_password_encryption": False,  # CIS violation: should be enabled
        "enable_secret_set": True,
        "min_length": 0,                       # CIS violation: no minimum password length
    },
    "banners": {
        "login": "",           # CIS violation: login banner should be configured
        "motd": "",            # CIS violation: MOTD banner should be configured
        "exec": "",
    },
    "acls": [
        {"name": "ACL_MGMT", "type": "standard",
         "entries": [
             {"seq": 10, "action": "permit", "source": "192.168.1.0/24"},
             {"seq": 20, "action": "permit", "source": "any"},  # CIS violation: any permitted
         ]},
    ],
    "routing": {
        "bgp": {"enabled": False},
        "ospf": {"enabled": True, "process_id": 1, "authentication": False},  # CIS violation
        "static_routes": [{"prefix": "0.0.0.0/0", "next_hop": "10.0.0.254"}],
    },
    "cis_benchmark": "CIS Cisco IOS-XE 16.x Benchmark v1.1.0",
    "collected_at": _days_ago(0),
}

# ─── Juniper Junos Facts ──────────────────────────────────────────────────────
# CIS violations: SNMP v1 (CIS 3.3), no login class restrictions (CIS 2.1),
# no NTP auth (CIS 3.1), BGP without authentication (CIS 4.1)

JUNIPER_FACTS = {
    "ansible_network_os": "junipernetworks.junos.junos",
    "device_type": "switch",
    "hostname": "juniper-core-sw-01",
    "platform": "Juniper Junos",
    "model": "EX4300-48P",
    "serial": "CW3714050094",
    "junos_version": "21.2R3.5",
    "uptime": "31 days, 7 hours",
    "interfaces": [
        {"name": "ge-0/0/0", "description": "Uplink-to-Router", "status": "up",
         "speed": "1Gbps", "duplex": "full", "vlan": "trunk"},
        {"name": "ge-0/0/1", "description": "Server-Farm-A", "status": "up",
         "speed": "1Gbps", "duplex": "full", "vlan": "100"},
        {"name": "ge-0/0/2", "description": "UNUSED", "status": "down",
         "speed": "1Gbps", "duplex": "full", "vlan": "1"},
    ],
    "vlans": [
        {"id": 1,   "name": "default",     "interfaces": ["ge-0/0/2"]},  # CIS: unused ports on vlan 1
        {"id": 100, "name": "server-farm", "interfaces": ["ge-0/0/1"]},
        {"id": 200, "name": "management",  "interfaces": []},
    ],
    "ssh": {
        "enabled": True,
        "version": "v2",
        "root_login": "allow",    # CIS violation: root login should be denied
        "max_sessions": 10,
    },
    "telnet": {"enabled": True},  # CIS violation: should be disabled
    "snmp": {
        "version": "v1v2c",       # CIS violation: only SNMPv3 should be used
        "community": "public",    # CIS violation: default community string
        "v3_users": [],
    },
    "ntp": {
        "servers": ["192.168.1.100"],
        "authentication": False,   # CIS violation: NTP auth required
        "synchronized": True,
    },
    "syslog": {
        "enabled": True,
        "hosts": ["192.168.1.100"],
        "facility": "any",
        "severity": "info",
    },
    "user_accounts": [
        {"name": "admin",   "class": "super-user", "auth": "sha256"},
        {"name": "netops",  "class": "operator",   "auth": "sha256"},
        {"name": "monitor", "class": "read-only",  "auth": "none"},  # CIS: no auth
    ],
    "bgp": {
        "enabled": True,
        "local_as": 65001,
        "peers": [
            {"peer_as": 65002, "ip": "10.0.0.254",
             "authentication": False,   # CIS violation: BGP MD5 auth required
             "state": "Established"},
        ],
    },
    "spanning_tree": {
        "enabled": True,
        "mode": "rstp",
        "bpdu_guard": False,      # CIS violation: BPDU guard should be enabled
        "root_guard": False,      # CIS violation: root guard should be enabled
    },
    "cis_benchmark": "CIS Juniper Junos OS Benchmark v1.0.0",
    "collected_at": _days_ago(0),
}

# ─── Palo Alto PAN-OS Facts ───────────────────────────────────────────────────
# CIS violations: permissive outbound policy (CIS 5.1), no URL filtering (CIS 6.1),
# no antivirus profile (CIS 6.2), admin using default password (CIS 1.1)

PALOALTO_FACTS = {
    "ansible_network_os": "paloaltonetworks.panos.panos",
    "device_type": "firewall",
    "hostname": "paloalto-fw-01",
    "platform": "Palo Alto PAN-OS",
    "model": "PA-VM",
    "serial": "015351000185439",
    "panos_version": "10.2.3",
    "uptime": "22 days, 14 hours",
    "ha_mode": "standalone",
    "interfaces": [
        {"name": "ethernet1/1", "zone": "untrust", "ip": "203.0.113.1/30",
         "type": "layer3", "status": "up"},
        {"name": "ethernet1/2", "zone": "trust",   "ip": "10.10.0.1/24",
         "type": "layer3", "status": "up"},
        {"name": "ethernet1/3", "zone": "dmz",     "ip": "172.16.0.1/24",
         "type": "layer3", "status": "up"},
    ],
    "zones": [
        {"name": "untrust", "type": "layer3", "log_setting": "default"},
        {"name": "trust",   "type": "layer3", "log_setting": "default"},
        {"name": "dmz",     "type": "layer3", "log_setting": "default"},
    ],
    "security_policies": [
        {"name": "Allow-Outbound", "from": "trust", "to": "untrust",
         "source": "any", "destination": "any", "application": "any",
         "action": "allow",                  # CIS violation: overly permissive
         "log_start": False, "log_end": True,
         "url_filtering": None,              # CIS violation: no URL filtering
         "antivirus": None,                  # CIS violation: no AV profile
         "vulnerability": None},             # CIS violation: no vuln protection
        {"name": "Allow-DMZ-Inbound", "from": "untrust", "to": "dmz",
         "source": "any", "destination": "any", "application": ["web-browsing", "ssl"],
         "action": "allow",
         "log_start": False, "log_end": True,
         "url_filtering": None,
         "antivirus": "default",
         "vulnerability": "strict"},
        {"name": "Deny-All", "from": "any", "to": "any",
         "source": "any", "destination": "any", "application": "any",
         "action": "deny",
         "log_start": True, "log_end": True,
         "url_filtering": None,
         "antivirus": None,
         "vulnerability": None},
    ],
    "nat_policies": [
        {"name": "Outbound-NAT", "from": "trust", "to": "untrust",
         "source": "10.10.0.0/24", "nat_type": "dynamic-ip-and-port"},
    ],
    "admin_accounts": [
        {"name": "admin",    "role": "superuser",
         "password_profile": "default",         # CIS violation: should use strong profile
         "auth_profile": "local"},
        {"name": "netadmin", "role": "deviceadmin",
         "password_profile": "strong",
         "auth_profile": "ldap"},
    ],
    "management": {
        "permitted_ips": [],    # CIS violation: management access unrestricted
        "https": True,
        "http": True,           # CIS violation: HTTP should be disabled
        "ssh": True,
        "telnet": False,
        "snmp": True,
        "snmp_version": "v2c",  # CIS violation: SNMPv3 required
    },
    "threat_prevention": {
        "antivirus_enabled": False,     # CIS violation
        "anti_spyware_enabled": True,
        "vulnerability_protection": True,
        "url_filtering_enabled": False, # CIS violation
        "wildfire_enabled": False,      # CIS violation
        "dns_security_enabled": False,
    },
    "logging": {
        "syslog_servers": ["192.168.1.100"],
        "log_forwarding_profile": "default",
        "traffic_logs": True,
        "threat_logs": True,
        "config_logs": True,
    },
    "certificates": {
        "self_signed_mgmt": True,       # CIS violation: should use CA-signed cert
        "ssl_decryption_enabled": False, # CIS: consider enabling for visibility
    },
    "cis_benchmark": "CIS Palo Alto Firewall 10 Benchmark v1.0.0",
    "collected_at": _days_ago(0),
}

# ─── S3 Storage Facts ─────────────────────────────────────────────────────────
# CIS violations: public bucket (CIS 2.1.1), no versioning (CIS 2.1.2),
# no MFA delete (CIS 2.1.3), no default encryption (CIS 2.1.4), no access logs (CIS 2.1.5)

S3_FACTS = {
    "device_type": "object_storage",
    "platform": "S3-Compatible Storage",
    "endpoint": "http://AAP_HOST:9000",
    "region": "us-east-1",
    "buckets": [
        {
            "name": "compliance-reports",
            "region": "us-east-1",
            "created": _days_ago(180),
            "public_access": {
                "block_public_acls": True,
                "block_public_policy": True,
                "ignore_public_acls": True,
                "restrict_public_buckets": True,
            },
            "versioning": {"enabled": True, "mfa_delete": False},  # CIS: MFA delete off
            "encryption": {"enabled": True, "algorithm": "AES256"},
            "logging": {"enabled": True, "target_bucket": "compliance-logs"},
            "lifecycle_rules": [{"id": "expire-old", "expiration_days": 365}],
            "tags": {"Environment": "production", "DataClass": "confidential"},
        },
        {
            "name": "app-uploads",
            "region": "us-east-1",
            "created": _days_ago(90),
            "public_access": {
                "block_public_acls": False,       # CIS violation: public access allowed
                "block_public_policy": False,     # CIS violation
                "ignore_public_acls": False,      # CIS violation
                "restrict_public_buckets": False, # CIS violation
            },
            "versioning": {"enabled": False, "mfa_delete": False},  # CIS violation
            "encryption": {"enabled": False},                         # CIS violation
            "logging": {"enabled": False},                            # CIS violation
            "lifecycle_rules": [],
            "tags": {"Environment": "production"},                    # CIS: missing DataClass
        },
        {
            "name": "dev-scratch",
            "region": "us-east-1",
            "created": _days_ago(30),
            "public_access": {
                "block_public_acls": False,   # CIS violation
                "block_public_policy": False, # CIS violation
                "ignore_public_acls": False,
                "restrict_public_buckets": False,
            },
            "versioning": {"enabled": False, "mfa_delete": False},
            "encryption": {"enabled": False},                     # CIS violation
            "logging": {"enabled": False},                        # CIS violation
            "lifecycle_rules": [],
            "tags": {},                                           # CIS: no tags
        },
    ],
    "iam_policies": [
        {"name": "compliance-reader", "effect": "Allow",
         "actions": ["s3:GetObject", "s3:ListBucket"],
         "resources": ["arn:aws:s3:::compliance-reports/*"]},
        {"name": "public-read-policy", "effect": "Allow",
         "principal": "*",                    # CIS violation: public principal
         "actions": ["s3:GetObject"],
         "resources": ["arn:aws:s3:::app-uploads/*"]},
    ],
    "account_settings": {
        "block_public_access_account_level": False,  # CIS violation: should be True
        "cloudtrail_s3_logging": False,              # CIS violation
    },
    "cis_benchmark": "CIS Amazon Web Services Foundations Benchmark v2.0.0",
    "collected_at": _days_ago(0),
}


# ─── HTTP Server ──────────────────────────────────────────────────────────────

DEVICE_MAP = {
    8091: ("cisco",    CISCO_FACTS),
    8092: ("juniper",  JUNIPER_FACTS),
    8093: ("paloalto", PALOALTO_FACTS),
    8094: ("s3",       S3_FACTS),
}


def make_handler(device_name, facts):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # suppress per-request logs

        def do_GET(self):
            if self.path in ("/facts", "/api/facts", "/"):
                body = json.dumps(facts, indent=2).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/health":
                body = json.dumps({"status": "healthy", "device": device_name}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

    return Handler


def run_server(port, device_name, facts):
    handler = make_handler(device_name, facts)
    server = HTTPServer(("0.0.0.0", port), handler)
    print(f"[{device_name:10s}] listening on :{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    threads = []
    for port, (name, facts) in DEVICE_MAP.items():
        t = threading.Thread(target=run_server, args=(port, name, facts), daemon=True)
        t.start()
        threads.append(t)

    print("AAC Network Simulator running. Ctrl-C to stop.", flush=True)
    print("  :8091 Cisco IOS-XE router", flush=True)
    print("  :8092 Juniper Junos switch", flush=True)
    print("  :8093 Palo Alto PAN-OS firewall", flush=True)
    print("  :8094 S3 storage buckets", flush=True)

    for t in threads:
        t.join()
