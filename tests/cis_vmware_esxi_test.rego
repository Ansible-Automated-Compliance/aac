package cis_esxi_8

import rego.v1

test_esxi_compliant_configuration if {
    result := compliant with input as {
        "esxi": {
            "host": {
                "time_sync": {
                    "ntp_enabled": true,
                    "secure_time_sources": true
                },
                "ssh": {
                    "disabled": true
                },
                "firewall": {
                    "enabled": true,
                    "default_deny": true,
                    "rules_reviewed": true
                },
                "certificates": {
                    "valid": true,
                    "not_expired": true,
                    "ca_signed": true
                },
                "password_policy": {
                    "complexity_required": true,
                    "min_length": 8,
                    "max_age_days": 90
                },
                "account_lockout": {
                    "enabled": true,
                    "threshold": 5,
                    "duration_minutes": 15
                },
                "session": {
                    "timeout_minutes": 30
                },
                "console_access": {
                    "restricted": true,
                    "timeout_configured": true
                },
                "snmp": {
                    "v3_only": true,
                    "community_strings_removed": true
                },
                "syslog": {
                    "enabled": true,
                    "remote_logging": true,
                    "secure_transport": true
                },
                "kernel_modules": {
                    "unauthorized_modules_blocked": true,
                    "module_loading_restricted": true
                },
                "hypervisor_scheduler": {
                    "secure_configuration": true
                },
                "memory_management": {
                    "secure_configuration": true,
                    "isolation_enabled": true
                },
                "cpu_management": {
                    "resource_allocation_controlled": true,
                    "hyperthreading_configured_securely": true
                },
                "power_management": {
                    "appropriate_policy": true
                },
                "hardware_monitoring": {
                    "health_monitoring": true,
                    "alerting_configured": true
                },
                "patch_management": {
                    "automated_updates": true,
                    "testing_procedures": true
                },
                "backup_procedures": {
                    "scheduled": true,
                    "tested_regularly": true
                },
                "disaster_recovery": {
                    "procedures_documented": true,
                    "tested_regularly": true
                },
                "compliance_monitoring": {
                    "enabled": true,
                    "reporting_configured": true
                }
            },
            "network": {
                "redundancy": {
                    "configured": true,
                    "critical_traffic_protected": true
                },
                "security_policies": {
                    "implemented": true,
                    "regularly_reviewed": true
                },
                "vlan": {
                    "properly_configured": true,
                    "isolated_appropriately": true
                },
                "vswitch": {
                    "security_policies_configured": true,
                    "promiscuous_mode_disabled": true,
                    "mac_address_changes_rejected": true,
                    "forged_transmits_rejected": true
                },
                "portgroup": {
                    "security_policies_configured": true,
                    "access_controls_implemented": true
                },
                "io_control": {
                    "enabled": true,
                    "properly_configured": true
                },
                "traffic_shaping": {
                    "configured": true
                },
                "security_monitoring": {
                    "enabled": true,
                    "alerting_configured": true
                },
                "access_control": {
                    "implemented": true,
                    "regularly_reviewed": true
                },
                "encryption": {
                    "enabled_where_appropriate": true
                },
                "segmentation": {
                    "properly_implemented": true
                },
                "virtual_security": {
                    "features_enabled": true
                },
                "intrusion_detection": {
                    "configured": true
                },
                "performance_monitoring": {
                    "configured": true
                }
            },
            "storage": {
                "access_control": {
                    "properly_configured": true,
                    "regularly_reviewed": true
                },
                "encryption": {
                    "enabled_where_appropriate": true
                },
                "multipathing": {
                    "configured_securely": true
                },
                "performance_monitoring": {
                    "configured": true
                },
                "backup_procedures": {
                    "in_place": true,
                    "tested_regularly": true
                },
                "array_integration": {
                    "secure": true
                },
                "io_control": {
                    "configured_appropriately": true
                },
                "security_policies": {
                    "implemented": true
                },
                "audit_logging": {
                    "enabled": true
                },
                "compliance_monitoring": {
                    "configured": true
                }
            },
            "vm": {
                "configuration_security": {
                    "enforced": true
                },
                "resource_allocation": {
                    "properly_controlled": true
                },
                "security_policies": {
                    "implemented": true
                },
                "network_security": {
                    "configured": true
                },
                "storage_security": {
                    "configured": true
                },
                "access_control": {
                    "properly_configured": true
                },
                "monitoring_logging": {
                    "configured": true
                },
                "backup_procedures": {
                    "in_place": true
                },
                "compliance_monitoring": {
                    "enabled": true
                },
                "security_scanning": {
                    "configured": true
                },
                "vulnerability_management": {
                    "implemented": true
                },
                "patch_management": {
                    "configured": true
                },
                "antivirus_protection": {
                    "configured": true
                },
                "data_loss_prevention": {
                    "configured": true
                }
            },
            "access_control": {
                "rbac": {
                    "implemented": true,
                    "regularly_reviewed": true
                },
                "user_account_management": {
                    "properly_configured": true
                },
                "service_account_management": {
                    "secure": true
                },
                "privileged_access_management": {
                    "implemented": true
                },
                "authentication_mechanisms": {
                    "secure": true
                },
                "authorization_policies": {
                    "properly_configured": true
                },
                "access_review_procedures": {
                    "configured": true
                },
                "access_provisioning": {
                    "automated": true
                },
                "access_monitoring": {
                    "configured": true
                },
                "emergency_access_procedures": {
                    "documented": true
                }
            },
            "logging_audit": {
                "comprehensive_audit_logging": {
                    "enabled": true
                },
                "log_forwarding": {
                    "configured_securely": true
                },
                "log_retention_policies": {
                    "implemented": true
                },
                "log_monitoring_alerting": {
                    "configured": true
                },
                "log_integrity_protection": {
                    "enabled": true
                },
                "security_event_correlation": {
                    "configured": true
                },
                "incident_response_procedures": {
                    "documented": true
                },
                "forensic_analysis_capabilities": {
                    "available": true
                },
                "compliance_reporting": {
                    "automated": true
                },
                "audit_trail_review_procedures": {
                    "configured": true
                }
            },
            "system_hardening": {
                "hardening_standards": {
                    "applied": true
                },
                "security_patches": {
                    "applied_timely": true
                },
                "vulnerability_scanning": {
                    "configured": true
                },
                "penetration_testing": {
                    "performed_regularly": true
                },
                "security_baseline_compliance": {
                    "monitored": true
                },
                "configuration_drift_detection": {
                    "enabled": true
                },
                "security_automation": {
                    "implemented": true
                },
                "threat_intelligence_integration": {
                    "configured": true
                },
                "security_metrics_kpis": {
                    "tracked": true
                },
                "continuous_security_improvement_processes": {
                    "configured": true
                }
            },
            "compliance_monitoring": {
                "compliance_framework_alignment": {
                    "documented": true
                },
                "regulatory_compliance_monitoring": {
                    "configured": true
                },
                "compliance_reporting": {
                    "automated_comprehensive": true
                },
                "compliance_audit_trails": {
                    "maintained": true
                },
                "compliance_exception_management": {
                    "implemented": true
                },
                "compliance_training_awareness_programs": {
                    "configured": true
                },
                "compliance_risk_assessment": {
                    "performed_regularly": true
                },
                "compliance_governance_processes": {
                    "documented": true
                }
            }
        }
    }
    result == true
}

test_esxi_non_compliant_configuration if {
    result := compliant with input as {
        "esxi": {
            "host": {
                "time_sync": {
                    "ntp_enabled": false,
                    "secure_time_sources": false
                },
                "ssh": {
                    "enabled": true,
                    "secure_configuration": false,
                    "key_based_auth": false,
                    "root_login_disabled": false
                },
                "firewall": {
                    "enabled": false,
                    "default_deny": false,
                    "rules_reviewed": false
                },
                "certificates": {
                    "valid": false,
                    "not_expired": false,
                    "ca_signed": false
                }
            }
        }
    }
    result == false
}

test_esxi_violations_count if {
    violations_result := violations with input as {
        "esxi": {
            "host": {
                "time_sync": {
                    "ntp_enabled": false,
                    "secure_time_sources": false
                },
                "ssh": {
                    "enabled": true,
                    "secure_configuration": false
                },
                "firewall": {
                    "enabled": false
                }
            }
        }
    }
    count(violations_result) > 80
}

test_esxi_findings_structure if {
    findings_result := findings with input as {
        "esxi": {
            "host": {
                "time_sync": {
                    "ntp_enabled": false
                }
            }
        }
    }
    
    count(findings_result) == 1
    findings_result[0].title == "VMware ESXi 8.0 Host Security Configuration Assessment"
    findings_result[0].severity == "HIGH"
    is_string(findings_result[0].description)
    is_string(findings_result[0].details)
    is_array(findings_result[0].violations)
    is_string(findings_result[0].remediation)
}