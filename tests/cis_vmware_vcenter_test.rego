package cis_vcenter_8

import rego.v1

test_vcenter_compliant_configuration if {
    result := compliant with input as {
        "vcenter": {
            "service_account": {
                "name": "vcenter-service",
                "privileges_minimal": true
            },
            "logging": {
                "enabled": true,
                "level": "info",
                "rotation_enabled": true
            },
            "session": {
                "timeout_minutes": 30
            },
            "password_policy": {
                "min_length": 8,
                "complexity_required": true,
                "max_age_days": 90
            },
            "ssl": {
                "certificate_valid": true,
                "certificate_not_expired": true,
                "strong_cipher_suites": true,
                "weak_protocols_disabled": true
            },
            "network": {
                "firewall_enabled": true,
                "unnecessary_services_disabled": true,
                "secure_protocols_only": true
            },
            "backup": {
                "scheduled": true,
                "tested_regularly": true,
                "secure_storage": true
            },
            "database": {
                "authentication_secure": true,
                "encryption_enabled": true,
                "access_controls_configured": true
            },
            "access_control": {
                "rbac_enabled": true,
                "least_privilege": true,
                "regular_review": true
            },
            "audit": {
                "enabled": true,
                "comprehensive_coverage": true,
                "log_retention_configured": true
            },
            "management_interfaces": {
                "ssh_disabled": true,
                "console_access_restricted": true,
                "remote_access_secured": true
            },
            "time_sync": {
                "ntp_enabled": true,
                "secure_time_sources": true
            },
            "snmp": {
                "v3_only": true,
                "community_strings_secure": true
            },
            "performance_monitoring": {
                "secure_access": true,
                "data_retention_configured": true
            },
            "patch_management": {
                "automated_updates": true,
                "testing_procedures": true
            },
            "high_availability": {
                "enabled": true,
                "properly_configured": true
            },
            "disaster_recovery": {
                "procedures_documented": true,
                "tested_regularly": true
            },
            "inventory_management": {
                "access_controlled": true,
                "changes_audited": true
            },
            "api_access": {
                "authentication_required": true,
                "authorization_enforced": true,
                "rate_limiting_enabled": true
            },
            "licensing": {
                "properly_configured": true,
                "compliance_monitored": true
            },
            "sso": {
                "password_policy": {
                    "min_length": 8,
                    "complexity_required": true,
                    "max_age_days": 90,
                    "lockout_threshold": 5
                },
                "lockout_policy": {
                    "failed_attempts_threshold": 5,
                    "lockout_duration_minutes": 15
                },
                "identity_sources": {
                    "secure_connections": true,
                    "certificate_validation": true
                },
                "token_policy": {
                    "max_lifetime_hours": 24,
                    "renewal_count_limited": true
                },
                "certificates": {
                    "valid": true,
                    "not_expired": true,
                    "strong_key_length": true
                },
                "domain_join": {
                    "secure_protocols": true,
                    "service_account_minimal_privileges": true
                },
                "service_accounts": {
                    "minimal_privileges": true,
                    "regular_review": true
                },
                "audit_logging": {
                    "enabled": true,
                    "comprehensive_events": true
                },
                "global_permissions": {
                    "minimized": true,
                    "regularly_reviewed": true
                },
                "solution_users": {
                    "certificates_managed": true,
                    "rotation_scheduled": true
                },
                "idp_discovery": {
                    "secure_configuration": true
                },
                "smart_card_auth": {
                    "properly_configured": true
                }
            },
            "vsphere_client": {
                "session_timeout_minutes": 30,
                "ssl": {
                    "strong_protocols_only": true,
                    "strong_cipher_suites": true
                },
                "logging": {
                    "access_logs_enabled": true,
                    "error_logs_enabled": true
                },
                "plugins": {
                    "security_validated": true,
                    "unauthorized_disabled": true
                },
                "content_security_policy": {
                    "enabled": true,
                    "properly_configured": true
                },
                "security_headers": {
                    "hsts_enabled": true,
                    "xss_protection_enabled": true,
                    "content_type_nosniff_enabled": true
                },
                "authentication": {
                    "strong_mechanisms": true,
                    "multi_factor_supported": true
                },
                "cookies": {
                    "secure_flag": true,
                    "httponly_flag": true
                }
            },
            "inventory_service": {
                "logging": {
                    "enabled": true,
                    "appropriate_level": true
                },
                "access_controls": {
                    "authentication_required": true,
                    "authorization_enforced": true
                },
                "ssl": {
                    "enabled": true,
                    "strong_configuration": true
                },
                "database": {
                    "secure_connections": true,
                    "access_controls": true
                },
                "performance_monitoring": {
                    "enabled": true,
                    "secure_access": true
                },
                "backup": {
                    "scheduled": true,
                    "tested": true
                }
            },
            "lookup_service": {
                "ssl": {
                    "enabled": true,
                    "strong_configuration": true
                },
                "logging": {
                    "enabled": true,
                    "appropriate_level": true
                },
                "registration": {
                    "secure_protocols": true,
                    "authentication_required": true
                },
                "access_controls": {
                    "properly_configured": true
                },
                "endpoints": {
                    "secure_configuration": true
                }
            },
            "postgresql": {
                "authentication": {
                    "strong_mechanisms": true,
                    "no_trust_authentication": true
                },
                "logging": {
                    "enabled": true,
                    "comprehensive": true
                },
                "connections": {
                    "ssl_required": true,
                    "limits_configured": true
                },
                "access_controls": {
                    "role_based": true,
                    "least_privilege": true
                },
                "ssl": {
                    "enabled": true,
                    "strong_configuration": true
                },
                "backup": {
                    "automated": true,
                    "tested": true
                },
                "performance_monitoring": {
                    "enabled": true
                },
                "audit_logging": {
                    "enabled": true
                }
            },
            "photon_os": {
                "firewall": {
                    "enabled": true,
                    "rules_configured": true
                },
                "logging": {
                    "centralized": true,
                    "secure_transport": true
                },
                "access_controls": {
                    "sudo_configured": true,
                    "unnecessary_accounts_removed": true
                },
                "network_security": {
                    "secure_protocols": true,
                    "unnecessary_services_disabled": true
                },
                "time_sync": {
                    "ntp_enabled": true,
                    "secure_servers": true
                },
                "package_management": {
                    "signed_only": true,
                    "updates_automated": true
                },
                "user_accounts": {
                    "strong_passwords": true,
                    "unnecessary_accounts_removed": true
                },
                "audit_logging": {
                    "enabled": true,
                    "comprehensive": true
                },
                "kernel_security": {
                    "hardening_enabled": true,
                    "modules_restricted": true
                },
                "filesystem_security": {
                    "permissions_secure": true,
                    "mount_options_secure": true
                }
            },
            "performance_charts": {
                "logging": {
                    "enabled": true,
                    "appropriate_level": true
                },
                "ssl": {
                    "enabled": true,
                    "strong_configuration": true
                },
                "access_controls": {
                    "authentication_required": true,
                    "authorization_enforced": true
                },
                "database": {
                    "secure_connections": true,
                    "access_restricted": true
                }
            }
        }
    }
    result == true
}

test_vcenter_non_compliant_configuration if {
    result := compliant with input as {
        "vcenter": {
            "service_account": {
                "name": "root",
                "privileges_minimal": false
            },
            "logging": {
                "enabled": false,
                "level": "debug",
                "rotation_enabled": false
            },
            "session": {
                "timeout_minutes": 0
            },
            "password_policy": {
                "min_length": 4,
                "complexity_required": false,
                "max_age_days": 365
            },
            "ssl": {
                "certificate_valid": false,
                "certificate_not_expired": false,
                "strong_cipher_suites": false,
                "weak_protocols_disabled": false
            },
            "network": {
                "firewall_enabled": false,
                "unnecessary_services_disabled": false,
                "secure_protocols_only": false
            },
            "backup": {
                "scheduled": false,
                "tested_regularly": false,
                "secure_storage": false
            },
            "database": {
                "authentication_secure": false,
                "encryption_enabled": false,
                "access_controls_configured": false
            },
            "access_control": {
                "rbac_enabled": false,
                "least_privilege": false,
                "regular_review": false
            },
            "audit": {
                "enabled": false,
                "comprehensive_coverage": false,
                "log_retention_configured": false
            }
        }
    }
    result == false
}

test_vcenter_violations_count if {
    violations_result := violations with input as {
        "vcenter": {
            "service_account": {
                "name": "root",
                "privileges_minimal": false
            },
            "logging": {
                "enabled": false,
                "level": "debug",
                "rotation_enabled": false
            },
            "session": {
                "timeout_minutes": 0
            }
        }
    }
    count(violations_result) > 50
}

test_vcenter_findings_structure if {
    findings_result := findings with input as {
        "vcenter": {
            "service_account": {
                "name": "root",
                "privileges_minimal": false
            }
        }
    }
    
    count(findings_result) == 1
    findings_result[0].title == "VMware vCenter Server 8.0 Security Configuration Assessment"
    findings_result[0].severity == "HIGH"
    is_string(findings_result[0].description)
    is_string(findings_result[0].details)
    is_array(findings_result[0].violations)
    is_string(findings_result[0].remediation)
}