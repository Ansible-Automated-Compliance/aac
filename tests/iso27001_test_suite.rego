package tests
import rego.v1


import data.iso27001
import data.iso27001.access_control
import data.iso27001.cryptography
import data.iso27001.operations_security
import data.iso27001.communications_security
import data.iso27001.system_acquisition_maintenance

# =============================================================================
# ISO 27001:2022 COMPREHENSIVE TEST SUITE
# =============================================================================

# Test ISO 27001 overall compliance - positive case
test_iso27001_compliance_pass if {
    allow with input as compliant_iso27001_input
}

# Test ISO 27001 overall compliance - negative case
test_iso27001_compliance_fail if {
    not allow with input as non_compliant_iso27001_input
}

# =============================================================================
# ACCESS CONTROL (A.9) TESTS
# =============================================================================

# Test A.9.1 - Business requirements for access control
test_access_control_business_requirements_pass if {
    access_control.business_requirements_met with input as {
        "access_control": {
            "policy": {
                "documented": true,
                "approved": true,
                "communicated": true
            },
            "access_rules": {
                "defined": true,
                "enforced": true
            }
        }
    }
}

test_access_control_business_requirements_fail if {
    not access_control.business_requirements_met with input as {
        "access_control": {
            "policy": {
                "documented": false,
                "approved": true,
                "communicated": true
            },
            "access_rules": {
                "defined": true,
                "enforced": true
            }
        }
    }
}

# Test A.9.2 - User access management
test_user_access_management_pass if {
    access_control.user_access_management with input as {
        "user_management": {
            "registration": {
                "formal_process": true,
                "authorization_required": true,
                "documented": true
            },
            "unauthorized_users": [],
            "provisioning": {
                "least_privilege": true,
                "role_based": true,
                "approval_required": true,
                "automated_tools": true
            }
        },
        "privileged_access": {
            "allocation_restricted": true,
            "regular_review": true,
            "monitoring_enabled": true,
            "multi_factor_auth": true,
            "shared_accounts": []
        },
        "authentication": {
            "password_policy": {
                "min_length": 12,
                "complexity_required": true,
                "expiry_enabled": true,
                "history_count": 15,
                "lockout_enabled": true
            },
            "mfa": {
                "enabled": true,
                "required_for_admin": true,
                "required_for_remote": true
            },
            "secrets": {
                "encrypted_storage": true,
                "access_controlled": true,
                "regular_rotation": true,
                "secure_transmission": true
            }
        },
        "access_review": {
            "regular_schedule": true,
            "management_approval": true,
            "documented_results": true,
            "remediation_tracked": true,
            "frequency_days": 90
        },
        "access_removal": {
            "immediate_termination": true,
            "role_change_adjustment": true,
            "automated_process": true,
            "verification_required": true
        }
    }
}

# Test password policy enforcement
test_password_policy_compliant_pass if {
    access_control.password_policy_compliant with input as {
        "authentication": {
            "password_policy": {
                "min_length": 10,
                "complexity_required": true,
                "expiry_enabled": true,
                "history_count": 12,
                "lockout_enabled": true
            }
        }
    }
}

test_password_policy_compliant_fail_length if {
    not access_control.password_policy_compliant with input as {
        "authentication": {
            "password_policy": {
                "min_length": 6,  # Too short
                "complexity_required": true,
                "expiry_enabled": true,
                "history_count": 12,
                "lockout_enabled": true
            }
        }
    }
}

# Test secure logon procedures
test_secure_logon_procedures_pass if {
    access_control.secure_logon_procedures with input as {
        "logon": {
            "user_identification_required": true,
            "authentication_required": true,
            "session_timeout_configured": true,
            "failed_attempt_lockout": true,
            "warning_message_displayed": true,
            "session_timeout_minutes": 15,
            "max_failed_attempts": 3
        }
    }
}

test_secure_logon_procedures_fail_timeout if {
    not access_control.secure_logon_procedures with input as {
        "logon": {
            "user_identification_required": true,
            "authentication_required": true,
            "session_timeout_configured": true,
            "failed_attempt_lockout": true,
            "warning_message_displayed": true,
            "session_timeout_minutes": 45,  # Too long
            "max_failed_attempts": 3
        }
    }
}

# =============================================================================
# CRYPTOGRAPHY (A.10) TESTS
# =============================================================================

# Test A.10.1 - Cryptographic controls
test_cryptographic_policy_pass if {
    cryptography.cryptographic_policy with input as {
        "cryptography": {
            "policy": {
                "documented": true,
                "approved": true,
                "communicated": true,
                "regularly_reviewed": true,
                "approved_algorithms": ["AES", "RSA", "ECC"],
                "key_management_addressed": true,
                "encryption_requirements": true
            }
        }
    }
}

# Test key management
test_key_management_pass if {
    cryptography.key_management with input as {
        "key_management": {
            "generation": {
                "random_source_secure": true,
                "approved_algorithms": true,
                "sufficient_entropy": true,
                "documented_process": true
            },
            "approved_algorithms": ["AES", "RSA", "ECC"],
            "key_specifications": [
                {"algorithm": "AES", "min_length": 256},
                {"algorithm": "RSA", "min_length": 2048}
            ],
            "distribution": {
                "encrypted_channels": true,
                "authentication_required": true,
                "integrity_protected": true
            },
            "storage": {
                "hardware_security_modules": true,
                "access_controlled": true,
                "audit_logged": true,
                "backup_encrypted": true
            },
            "usage": {
                "purpose_specific": true,
                "access_restricted": true,
                "audit_logged": true
            },
            "rotation": {
                "regular_schedule": true,
                "automated_process": true,
                "emergency_procedures": true,
                "max_lifetime_days": 365
            },
            "destruction": {
                "secure_deletion": true,
                "verification_required": true,
                "documented_process": true,
                "audit_logged": true
            }
        }
    }
}

# Test data encryption
test_data_encryption_pass if {
    cryptography.data_encryption with input as {
        "encryption": {
            "data_at_rest": {
                "enabled": true,
                "strong_algorithms": true,
                "key_management_integrated": true
            },
            "filesystem": {
                "full_disk_encryption": true,
                "secure_boot": true
            },
            "application_data": {
                "sensitive_fields": true,
                "configuration_files": true
            },
            "data_in_transit": {
                "tls_enforced": true,
                "minimum_tls_version": "1.3",
                "certificate_validation": true,
                "perfect_forward_secrecy": true
            }
        },
        "network": {
            "ssh": {
                "protocol_version": 2,
                "strong_ciphers": true,
                "key_based_auth": true
            },
            "https": {
                "enforced": true,
                "hsts_enabled": true,
                "secure_cookies": true
            },
            "vpn": {
                "strong_encryption": true,
                "certificate_based": true
            }
        },
        "api": {
            "tls_required": true,
            "token_encryption": true,
            "payload_encryption": true,
            "certificate_pinning": true
        },
        "database": {
            "encryption": {
                "at_rest": true,
                "in_transit": true,
                "key_rotation": true,
                "transparent_encryption": true
            },
            "connections": {
                "ssl_required": true,
                "certificate_validation": true
            }
        },
        "backup": {
            "encryption": {
                "enabled": true,
                "separate_keys": true,
                "key_escrow": true,
                "integrity_verification": true
            }
        }
    }
}

# Test weak algorithms disabled
test_weak_algorithms_disabled_pass if {
    cryptography.weak_algorithms_disabled with input as {
        "cryptography": {
            "algorithms_in_use": ["AES", "RSA", "ECC", "SHA256", "TLS1.3"]
        }
    }
}

test_weak_algorithms_disabled_fail if {
    not cryptography.weak_algorithms_disabled with input as {
        "cryptography": {
            "algorithms_in_use": ["AES", "RSA", "MD5", "SHA256"]  # MD5 is weak
        }
    }
}

# =============================================================================
# OPERATIONS SECURITY (A.12) TESTS
# =============================================================================

# Test A.12.1 - Operational procedures
test_operational_procedures_pass if {
    operations_security.operational_procedures with input as {
        "operations": {
            "procedures": {
                "documented": true,
                "approved": true,
                "regularly_updated": true,
                "accessible_to_users": true,
                "version_controlled": true
            }
        },
        "change_management": {
            "formal_process": true,
            "approval_required": true,
            "testing_required": true,
            "rollback_procedures": true,
            "documentation_required": true,
            "emergency_procedures": true
        },
        "capacity": {
            "monitoring_enabled": true,
            "thresholds_defined": true,
            "forecasting_performed": true,
            "resource_allocation": true,
            "cpu_monitoring": true,
            "memory_monitoring": true,
            "disk_monitoring": true,
            "network_monitoring": true,
            "alerting_configured": true
        },
        "environments": {
            "development": {"isolated": true},
            "testing": {"isolated": true},
            "production": {"isolated": true},
            "data_flow": {
                "controlled": true,
                "sanitization": true,
                "approval_required": true
            },
            "access": {
                "role_based": true,
                "least_privilege": true,
                "production_restricted": true
            }
        }
    }
}

# Test A.12.2 - Malware protection
test_malware_protection_pass if {
    operations_security.malware_protection with input as {
        "malware_protection": {
            "antivirus": {
                "installed": true,
                "updated": true,
                "real_time_scanning": true,
                "scheduled_scans": true
            },
            "email_filtering": {
                "enabled": true,
                "attachment_scanning": true,
                "url_filtering": true
            },
            "web_filtering": {
                "enabled": true,
                "real_time_scanning": true,
                "category_blocking": true
            }
        },
        "endpoint_protection": {
            "edr_installed": true,
            "behavior_analysis": true,
            "application_control": true,
            "device_control": true
        },
        "network_protection": {
            "ips_enabled": true,
            "dns_filtering": true,
            "traffic_analysis": true
        }
    }
}

# Test A.12.3 - Backup management
test_backup_management_pass if {
    operations_security.backup_management with input as {
        "backup": {
            "regular_schedule": true,
            "automated_process": true,
            "integrity_verification": true,
            "restoration_tested": true,
            "storage": {
                "offsite_copy": true,
                "encrypted": true,
                "access_controlled": true,
                "environmental_protection": true
            },
            "retention": {
                "policy_defined": true,
                "automated_cleanup": true,
                "compliance_requirements": true,
                "daily_days": 30,
                "weekly_weeks": 12,
                "monthly_months": 12
            },
            "recovery": {
                "rto_defined": true,
                "rpo_defined": true,
                "tested_regularly": true,
                "rto_hours": 4,
                "rpo_hours": 2
            }
        }
    }
}

# Test A.12.4 - Logging and monitoring
test_logging_monitoring_pass if {
    operations_security.logging_monitoring with input as {
        "logging": {
            "enabled": true,
            "comprehensive_coverage": true,
            "centralized": true,
            "real_time": true,
            "events_captured": [
                "user_login", "user_logout", "failed_login",
                "privilege_escalation", "file_access", "configuration_changes",
                "system_errors", "security_alerts", "network_connections"
            ],
            "content": {
                "timestamp": true,
                "user_id": true,
                "source_ip": true,
                "event_type": true,
                "outcome": true,
                "additional_details": true
            },
            "protection": {
                "tamper_proof": true,
                "access_controlled": true,
                "backup_included": true,
                "integrity_monitoring": true
            },
            "retention": {
                "policy_defined": true,
                "automated_archival": true,
                "security_logs_days": 365,
                "audit_logs_days": 180,
                "system_logs_days": 90
            },
            "admin_activities": {
                "logged": true,
                "privileged_access": true,
                "configuration_changes": true,
                "separate_storage": true,
                "regular_review": true
            }
        },
        "time_sync": {
            "ntp_enabled": true,
            "authoritative_source": true,
            "synchronized_systems": true,
            "monitoring_enabled": true,
            "max_drift_seconds": 60
        }
    }
}

# =============================================================================
# COMMUNICATIONS SECURITY (A.13) TESTS
# =============================================================================

# Test A.13.1 - Network security management
test_network_security_management_pass if {
    communications_security.network_security_management with input as {
        "network": {
            "security_policy": {
                "documented": true,
                "implemented": true,
                "regularly_reviewed": true
            },
            "firewall": {
                "enabled": true,
                "default_deny": true,
                "rule_review": true,
                "logging_enabled": true,
                "high_availability": true,
                "rules": {
                    "documented": true,
                    "justified": true,
                    "minimal_access": true,
                    "regular_review": true
                }
            },
            "access_control": {
                "authentication_required": true,
                "authorization_verified": true,
                "session_management": true,
                "anomaly_detection": true
            },
            "monitoring": {
                "traffic_analysis": true,
                "intrusion_detection": true,
                "security_events": true,
                "real_time_alerts": true,
                "log_correlation": true
            },
            "segregation": {
                "implemented": true,
                "vlan_separation": true,
                "dmz_configured": true,
                "trust_zones": true
            },
            "segmentation": {
                "documented_architecture": true,
                "security_zones": true,
                "traffic_filtering": true,
                "access_controls": true
            },
            "inter_segment": {
                "controlled_communication": true,
                "traffic_inspection": true,
                "logging_enabled": true,
                "policy_enforcement": true
            }
        },
        "network_services": {
            "authentication": {
                "strong_authentication": true,
                "mutual_authentication": true,
                "certificate_based": true,
                "multi_factor": true
            },
            "configuration": {
                "hardened": true,
                "unnecessary_services_disabled": true,
                "secure_protocols_only": true,
                "regular_updates": true
            },
            "dns": {
                "dnssec_enabled": true,
                "filtering_enabled": true,
                "logging_enabled": true,
                "secure_forwarders": true
            },
            "dhcp": {
                "reservation_used": true,
                "rogue_detection": true,
                "logging_enabled": true,
                "lease_time_appropriate": true
            },
            "ntp": {
                "authenticated_sources": true,
                "encrypted_communication": true,
                "access_controlled": true
            },
            "email": {
                "encryption_enforced": true,
                "spam_filtering": true,
                "malware_scanning": true,
                "dkim_enabled": true,
                "spf_configured": true,
                "dmarc_enabled": true
            },
            "monitoring": {
                "availability": true,
                "performance": true,
                "security_events": true,
                "capacity_utilization": true
            }
        }
    }
}

# Test wireless security
test_wireless_security_pass if {
    communications_security.wireless_security with input as {
        "wireless": {
            "enabled": true,
            "encryption": {
                "wpa3_minimum": true,
                "strong_passphrase": true
            },
            "access_control": {
                "enterprise_authentication": true,
                "certificate_based": true
            },
            "monitoring": {
                "rogue_ap_detection": true,
                "intrusion_detection": true,
                "signal_analysis": true,
                "device_tracking": true
            },
            "guest_network": {
                "separated": true,
                "limited_access": true,
                "time_limited": true,
                "terms_acceptance": true
            }
        }
    }
}

# Test protocol security
test_protocol_security_pass if {
    communications_security.protocol_security with input as {
        "network": {
            "protocols": {
                "enabled": ["TLS", "SSH", "SFTP", "HTTPS", "IPSec"]
            },
            "protocol_monitoring": {
                "traffic_analysis": true,
                "anomaly_detection": true,
                "protocol_validation": true,
                "compliance_checking": true
            }
        }
    }
}

test_protocol_security_fail_insecure if {
    not communications_security.protocol_security with input as {
        "network": {
            "protocols": {
                "enabled": ["TLS", "SSH", "HTTP", "FTP"]  # HTTP and FTP are insecure
            },
            "protocol_monitoring": {
                "traffic_analysis": true,
                "anomaly_detection": true,
                "protocol_validation": true,
                "compliance_checking": true
            }
        }
    }
}

# =============================================================================
# SYSTEM ACQUISITION AND MAINTENANCE (A.14) TESTS
# =============================================================================

# Test A.14.1 - Security requirements
test_security_requirements_pass if {
    system_acquisition_maintenance.security_requirements with input as {
        "development": {
            "security_requirements": {
                "documented": true,
                "reviewed": true,
                "approved": true,
                "traceable": true,
                "areas_covered": [
                    "authentication", "authorization", "data_protection",
                    "logging", "monitoring", "incident_response",
                    "backup_recovery", "encryption", "network_security"
                ]
            },
            "requirements_validation": {
                "security_review": true,
                "stakeholder_approval": true,
                "compliance_check": true,
                "risk_assessment": true
            }
        },
        "applications": {
            "public_facing": true,
            "web": {
                "https_enforced": true,
                "hsts_enabled": true,
                "secure_headers": true,
                "input_validation": true,
                "output_encoding": true,
                "csrf_protection": true,
                "xss_protection": true,
                "sql_injection_protection": true
            },
            "api": {
                "authentication_required": true,
                "authorization_enforced": true,
                "rate_limiting": true,
                "input_validation": true,
                "output_filtering": true,
                "logging_enabled": true,
                "versioning_controlled": true
            },
            "network_protection": {
                "waf_enabled": true,
                "firewall_configured": true,
                "intrusion_detection": true,
                "traffic_filtering": true
            },
            "ddos_protection": {
                "enabled": true,
                "rate_limiting": true,
                "traffic_analysis": true,
                "automatic_mitigation": true
            },
            "transactions": {
                "enabled": true,
                "integrity_protection": true,
                "non_repudiation": true,
                "confidentiality_protection": true,
                "audit_logging": true,
                "error_handling": true,
                "timeout_controls": true
            }
        }
    }
}

# Test secure development practices
test_secure_development_pass if {
    system_acquisition_maintenance.development_support_security with input as secure_development_input
}

# Helper function for secure development input
secure_development_input := {
    "development": {
        "policy": {
            "documented": true,
            "approved": true,
            "communicated": true,
            "regularly_updated": true,
            "practices_covered": [
                "secure_coding", "code_review", "security_testing",
                "vulnerability_assessment", "threat_modeling", "dependency_management"
            ]
        },
        "change_control": {
            "formal_process": true,
            "approval_required": true,
            "impact_assessment": true,
            "testing_required": true,
            "rollback_procedures": true,
            "documentation_required": true,
            "multi_level_approval": true,
            "security_review": true,
            "business_approval": true,
            "technical_approval": true
        },
        "technical_review": {
            "platform_changes": true,
            "security_impact": true,
            "compatibility_check": true,
            "performance_impact": true,
            "documentation_updated": true
        },
        "software_packages": {
            "modification_restricted": true,
            "vendor_support_maintained": true,
            "security_updates": true,
            "configuration_controlled": true
        },
        "engineering": {
            "defense_in_depth": true,
            "least_privilege": true,
            "fail_secure": true,
            "separation_of_duties": true,
            "input_validation": true,
            "secure_defaults": true
        },
        "environment": {
            "isolated": true,
            "access_controlled": true,
            "monitored": true,
            "hardened": true
        },
        "tools": {
            "approved_tools_only": true,
            "regularly_updated": true,
            "vulnerability_scanned": true,
            "license_compliant": true
        },
        "source_code": {
            "version_control": true,
            "access_controlled": true,
            "backup_protected": true,
            "integrity_monitoring": true,
            "intellectual_property_protected": true
        },
        "outsourced": {
            "enabled": false
        },
        "security_testing": {
            "static_analysis": true,
            "dynamic_analysis": true,
            "interactive_testing": true,
            "penetration_testing": true,
            "ci_cd_integrated": true,
            "automated_scanning": true,
            "manual_testing": true,
            "continuous_monitoring": true
        },
        "vulnerability_mgmt": {
            "scanning_enabled": true,
            "dependency_scanning": true,
            "remediation_tracking": true,
            "risk_assessment": true
        },
        "acceptance_testing": {
            "security_criteria": true,
            "functional_testing": true,
            "performance_testing": true,
            "user_acceptance": true,
            "security_sign_off": true,
            "documentation_complete": true
        },
        "test_data": {
            "production_data_restricted": true,
            "data_masking": true,
            "synthetic_data_preferred": true,
            "access_controlled": true,
            "retention_controlled": true,
            "secure_disposal": true
        },
        "devsecops": {
            "implemented": true
        },
        "cicd": {
            "security_scanning": true,
            "dependency_checking": true,
            "code_quality_gates": true,
            "security_approval_gates": true,
            "audit_logging": true
        },
        "containers": {
            "base_image_scanning": true,
            "vulnerability_scanning": true,
            "runtime_protection": true,
            "secrets_management": true,
            "network_isolation": true
        },
        "iac": {
            "security_scanning": true,
            "compliance_checking": true,
            "version_controlled": true,
            "peer_review_required": true
        },
        "secrets": {
            "centralized_management": true,
            "encryption_at_rest": true,
            "rotation_automated": true,
            "access_controlled": true,
            "audit_logged": true
        },
        "supply_chain": {
            "risk_assessment": true,
            "vendor_verification": true,
            "dependency_scanning": true,
            "license_compliance": true,
            "integrity_verification": true,
            "vulnerability_monitoring": true
        }
    }
}

# =============================================================================
# INTEGRATION AND CROSS-FRAMEWORK TESTS
# =============================================================================

# Test comprehensive ISO 27001 compliance with all controls
test_comprehensive_iso27001_compliance if {
    iso27001.allow with input as compliant_iso27001_input
}

# Helper function for compliant ISO 27001 input
compliant_iso27001_input := {
    "access_control": {
        "policy": {
            "documented": true,
            "approved": true,
            "communicated": true
        },
        "access_rules": {
            "defined": true,
            "enforced": true
        }
    },
    "user_management": {
        "registration": {
            "formal_process": true,
            "authorization_required": true,
            "documented": true
        },
        "unauthorized_users": [],
        "provisioning": {
            "least_privilege": true,
            "role_based": true,
            "approval_required": true,
            "automated_tools": true
        }
    },
    "privileged_access": {
        "allocation_restricted": true,
        "regular_review": true,
        "monitoring_enabled": true,
        "multi_factor_auth": true,
        "shared_accounts": []
    },
    "authentication": {
        "password_policy": {
            "min_length": 12,
            "complexity_required": true,
            "expiry_enabled": true,
            "history_count": 15,
            "lockout_enabled": true
        },
        "mfa": {
            "enabled": true,
            "required_for_admin": true,
            "required_for_remote": true
        },
        "secrets": {
            "encrypted_storage": true,
            "access_controlled": true,
            "regular_rotation": true,
            "secure_transmission": true
        }
    },
    "cryptography": {
        "policy": {
            "documented": true,
            "approved": true,
            "communicated": true,
            "regularly_reviewed": true,
            "approved_algorithms": ["AES", "RSA", "ECC"],
            "key_management_addressed": true,
            "encryption_requirements": true
        },
        "algorithms_in_use": ["AES", "RSA", "ECC", "SHA256", "TLS1.3"],
        "quantum_resistance": {
            "assessment_completed": true,
            "migration_plan": true,
            "timeline_defined": true
        }
    },
    "operations": {
        "procedures": {
            "documented": true,
            "approved": true,
            "regularly_updated": true,
            "accessible_to_users": true,
            "version_controlled": true
        }
    },
    "network": {
        "security_policy": {
            "documented": true,
            "implemented": true,
            "regularly_reviewed": true
        },
        "protocols": {
            "enabled": ["TLS", "SSH", "SFTP", "HTTPS", "IPSec"]
        }
    },
    "development": secure_development_input.development
}

# Helper function for non-compliant ISO 27001 input
non_compliant_iso27001_input := {
    "access_control": {
        "policy": {
            "documented": false,  # Non-compliant
            "approved": true,
            "communicated": true
        },
        "access_rules": {
            "defined": true,
            "enforced": true
        }
    },
    "cryptography": {
        "algorithms_in_use": ["AES", "RSA", "MD5"]  # MD5 is weak
    }
}

# Test edge cases and boundary conditions
test_iso27001_edge_cases if {
    # Test minimum acceptable password length
    access_control.password_policy_compliant with input as {
        "authentication": {
            "password_policy": {
                "min_length": 8,  # Minimum acceptable
                "complexity_required": true,
                "expiry_enabled": true,
                "history_count": 12,
                "lockout_enabled": true
            }
        }
    }
    
    # Test maximum acceptable session timeout
    access_control.secure_logon_procedures with input as {
        "logon": {
            "user_identification_required": true,
            "authentication_required": true,
            "session_timeout_configured": true,
            "failed_attempt_lockout": true,
            "warning_message_displayed": true,
            "session_timeout_minutes": 30,  # Maximum acceptable
            "max_failed_attempts": 5
        }
    }
}

# Performance test with large datasets
test_iso27001_large_dataset_performance if {
    large_input := {
        "user_management": {
            "registration": {
                "formal_process": true,
                "authorization_required": true,
                "documented": true
            },
            "unauthorized_users": [],
            "provisioning": {
                "least_privilege": true,
                "role_based": true,
                "approval_required": true,
                "automated_tools": true
            },
            "users": {
                sprintf("user_%d", [i]): {
                    "username": sprintf("user%d", [i]),
                    "role": sprintf("role_%d", [i % 20]),
                    "last_access": "2024-01-01",
                    "mfa_enabled": true
                } | i := numbers.range(1, 1000)
            }
        },
        "access_control": {
            "policy": {
                "documented": true,
                "approved": true,
                "communicated": true
            },
            "access_rules": {
                "defined": true,
                "enforced": true
            }
        }
    }
    
    # Should handle large user base efficiently
    access_control.user_registration_process with input as large_input
}