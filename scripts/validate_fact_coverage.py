#!/usr/bin/env python3
"""
Validate CIS Fact Coverage
Compares OPA policy input requirements against collected facts
Identifies gaps that cause false compliance results
"""

import json
import sys
import argparse
from typing import Dict, List, Set

# Expected input fields by policy module
POLICY_REQUIREMENTS = {
    "cis_rhel9": {
        "ssh": [
            "permit_root_login", "max_auth_tries", "max_sessions",
            "client_alive_interval", "client_alive_count_max", "login_grace_time",
            "permit_empty_passwords", "permit_user_environment", "x11_forwarding",
            "use_pam", "protocol", "log_level", "ignore_rhosts",
            "host_based_authentication", "banner", "ciphers", "macs", "kex_algorithms"
        ],
        "selinux": ["status", "config_mode", "policy"],
        "auditd": [
            "service_enabled", "service_active", "active_rules", "rules_count",
            "config.max_log_file", "config.max_log_file_action",
            "config.space_left_action", "config.admin_space_left_action",
            "log_dir_permissions.mode", "log_dir_permissions.owner"
        ],
        "pam": [
            "pwquality.minlen", "pwquality.dcredit", "pwquality.ucredit",
            "pwquality.lcredit", "pwquality.ocredit", "pwquality.minclass",
            "login_defs.pass_max_days", "login_defs.pass_min_days",
            "login_defs.pass_warn_age", "login_defs.encrypt_method"
        ],
        "sudo": ["use_pty", "logfile", "log_exists", "timestamp_timeout"],
        "firewall": ["enabled", "type", "default_zone"],
        "sysctl": [
            "net_ipv4_ip_forward", "net_ipv4_conf_all_send_redirects",
            "net_ipv4_conf_all_accept_source_route", "net_ipv4_conf_all_accept_redirects",
            "net_ipv4_tcp_syncookies", "kernel_randomize_va_space"
        ],
        "services": [
            "enabled", "running", "telnet_enabled", "rsh_enabled",
            "avahi_enabled", "cups_enabled"
        ],
        "cron": ["crontab_permissions"],
        "user_group": [
            "uid_zero_users", "uid_zero_count", "empty_password_users",
            "root_path_contains_dot"
        ],
        "file_permissions": ["passwd", "shadow", "group", "gshadow"],
        "bootloader": ["grub_cfg_permissions", "password_set"],
        "time_synchronization": ["chronyd_enabled", "any_active"],
        "logging": ["rsyslog.enabled", "rsyslog.active", "journald.storage"]
    },
    "cis_ubuntu_22_04": {
        "ssh": [
            "permit_root_login", "max_auth_tries", "permit_empty_passwords",
            "x11_forwarding", "use_pam", "log_level"
        ],
        "apparmor": ["enabled", "status"],
        "auditd": ["service_enabled", "service_active", "active_rules"],
        "pam": [
            "pwquality.minlen", "pwquality.dcredit",
            "login_defs.pass_max_days", "login_defs.pass_min_days"
        ],
        "firewall": ["enabled"],
        "services": ["enabled", "running"],
        "user_group": ["uid_zero_users", "empty_password_users"],
        "file_permissions": ["passwd", "shadow"],
        "logging": ["rsyslog.enabled", "journald.storage"]
    },
    "cis_windows_server_2022": {
        "password_policy": ["enforce_password_history", "minimum_password_length"],
        "account_lockout_policy": ["account_lockout_duration", "account_lockout_threshold"],
        "security_options": [
            "accounts_administrator_account_status",
            "interactive_logon_do_not_display_last_user_name"
        ],
        "event_log": [
            "application.control_event_log_behavior",
            "security.control_event_log_behavior",
            "system.control_event_log_behavior"
        ],
        "advanced_audit_policy": [
            "account_logon.audit_credential_validation",
            "logon_logoff.audit_account_lockout"
        ],
        "windows_defender": ["configure_attack_surface_reduction_rules"],
        "bitlocker": ["choose_how_bitlocker_protected_operating_system_drives_can_be_recovered"]
    },
    "nerc_cip": {
        "authentication_enabled": [],
        "encryption_enabled": [],
        "access_control_configured": [],
        "audit_logging_enabled": [],
        "firmware_version": [],
        "tamper_detected": []
    }
}


def flatten_dict(d: Dict, parent_key: str = '', sep: str = '.') -> Dict:
    """Flatten nested dictionary keys"""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def get_nested_value(d: Dict, key: str, default=None):
    """Get value from nested dict using dot notation"""
    keys = key.split('.')
    value = d
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return default
    return value


def validate_facts(facts: Dict, policy: str) -> Dict:
    """Validate facts against policy requirements"""

    if policy not in POLICY_REQUIREMENTS:
        return {"error": f"Unknown policy: {policy}"}

    requirements = POLICY_REQUIREMENTS[policy]
    results = {
        "policy": policy,
        "total_sections": len(requirements),
        "sections": {},
        "missing_fields": [],
        "present_fields": [],
        "coverage_percentage": 0
    }

    total_fields = 0
    present_fields = 0

    for section, fields in requirements.items():
        section_data = facts.get(section, {})
        section_results = {
            "present": section in facts,
            "fields_required": len(fields),
            "fields_present": 0,
            "missing": [],
            "values": {}
        }

        for field in fields:
            total_fields += 1
            value = get_nested_value(section_data, field)

            if value is not None:
                present_fields += 1
                section_results["fields_present"] += 1
                section_results["values"][field] = value
                results["present_fields"].append(f"{section}.{field}")
            else:
                section_results["missing"].append(field)
                results["missing_fields"].append(f"{section}.{field}")

        results["sections"][section] = section_results

    results["total_fields"] = total_fields
    results["fields_present"] = present_fields
    results["coverage_percentage"] = round((present_fields / total_fields * 100), 2) if total_fields > 0 else 0

    return results


def print_report(results: Dict):
    """Print validation report"""
    print("\n" + "=" * 70)
    print(f"FACT COVERAGE VALIDATION REPORT - {results['policy'].upper()}")
    print("=" * 70)

    print(f"\nOverall Coverage: {results['coverage_percentage']}%")
    print(f"Fields Present: {results['fields_present']}/{results['total_fields']}")

    print("\n" + "-" * 70)
    print("SECTION DETAILS:")
    print("-" * 70)

    for section, data in results["sections"].items():
        status = "✓" if data["present"] and data["fields_present"] == data["fields_required"] else "⚠" if data["present"] else "✗"
        print(f"\n{status} {section}: {data['fields_present']}/{data['fields_required']} fields")

        if data["missing"]:
            print(f"  Missing: {', '.join(data['missing'][:5])}")
            if len(data["missing"]) > 5:
                print(f"           ... and {len(data['missing']) - 5} more")

    if results["missing_fields"]:
        print("\n" + "-" * 70)
        print("MISSING FIELDS (will cause false compliance):")
        print("-" * 70)
        for field in results["missing_fields"][:20]:
            print(f"  - {field}")
        if len(results["missing_fields"]) > 20:
            print(f"  ... and {len(results['missing_fields']) - 20} more")

    print("\n" + "=" * 70)

    # Recommendations
    if results["coverage_percentage"] < 50:
        print("RECOMMENDATION: Fact collection is severely incomplete.")
        print("Many CIS controls cannot be properly evaluated.")
    elif results["coverage_percentage"] < 80:
        print("RECOMMENDATION: Fact collection needs improvement.")
        print("Some CIS controls may show false compliance.")
    else:
        print("RECOMMENDATION: Good fact coverage.")
        print("Most CIS controls can be properly evaluated.")

    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Validate CIS fact coverage")
    parser.add_argument("--facts-file", help="JSON file containing collected facts")
    parser.add_argument("--facts-json", help="JSON string of facts")
    parser.add_argument("--policy", default="cis_rhel9",
                        choices=list(POLICY_REQUIREMENTS.keys()),
                        help="Policy to validate against")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    # Load facts
    if args.facts_file:
        with open(args.facts_file, 'r') as f:
            facts = json.load(f)
    elif args.facts_json:
        facts = json.loads(args.facts_json)
    else:
        # Read from stdin
        facts = json.load(sys.stdin)

    # Validate
    results = validate_facts(facts, args.policy)

    # Output
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_report(results)

    # Exit code based on coverage
    if results["coverage_percentage"] < 50:
        sys.exit(2)
    elif results["coverage_percentage"] < 80:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
