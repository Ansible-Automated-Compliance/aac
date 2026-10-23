#!/usr/bin/env python3
"""
Test Data Generator for CIS and NIST Compliance Libraries

This script generates comprehensive test data sets for validating 
OPA Rego policies across all supported frameworks and technologies.
"""

import json
import random
import string
from datetime import datetime, timedelta
from typing import Dict, List, Any
import argparse
import sys

class TestDataGenerator:
    """Generate test data for compliance framework validation"""
    
    def __init__(self):
        self.timestamp = datetime.now().isoformat()
        
    def generate_cis_linux_data(self, compliant: bool = True) -> Dict[str, Any]:
        """Generate CIS Linux benchmark test data"""
        if compliant:
            return {
                "os_family": "RedHat",
                "distribution": "CentOS",
                "distribution_version": "9.0",
                "selinux_status": "enforcing",
                "firewall_enabled": True,
                "ssh_port": 22,
                "loaded_modules": ["ext4", "xfs", "btrfs"],
                "mounts": {
                    "/tmp": {
                        "device": "/dev/sda2",
                        "fstype": "ext4",
                        "options": ["rw", "nodev", "nosuid", "noexec"]
                    },
                    "/var": {
                        "device": "/dev/sda3",
                        "fstype": "ext4", 
                        "options": ["rw", "nodev"]
                    },
                    "/home": {
                        "device": "/dev/sda4",
                        "fstype": "ext4",
                        "options": ["rw", "nodev"]
                    }
                },
                "net_ipv4_ip_forward": 0,
                "net_ipv4_conf_all_send_redirects": 0,
                "net_ipv4_conf_default_send_redirects": 0,
                "ssh_config": [
                    "Protocol 2",
                    "LogLevel INFO",
                    "X11Forwarding no",
                    "MaxAuthTries 4",
                    "IgnoreRhosts yes",
                    "HostbasedAuthentication no",
                    "PermitRootLogin no",
                    "PermitEmptyPasswords no",
                    "PermitUserEnvironment no",
                    "ClientAliveInterval 300",
                    "ClientAliveCountMax 0"
                ],
                "services": {
                    "sshd": {"enabled": True, "running": True},
                    "cron": {"enabled": True, "running": True}
                }
            }
        else:
            # Non-compliant version
            return {
                "os_family": "RedHat", 
                "distribution": "CentOS",
                "distribution_version": "9.0",
                "selinux_status": "disabled",  # Non-compliant
                "firewall_enabled": False,      # Non-compliant
                "ssh_port": 22,
                "loaded_modules": ["ext4", "cramfs", "xfs"],  # Contains disabled filesystem
                "mounts": {
                    "/tmp": {
                        "device": "/dev/sda2",
                        "fstype": "ext4",
                        "options": ["rw"]  # Missing security options
                    }
                },
                "net_ipv4_ip_forward": 1,  # Non-compliant
                "ssh_config": [
                    "Protocol 2",
                    "PermitRootLogin yes",  # Non-compliant
                    "MaxAuthTries 10"       # Non-compliant
                ]
            }
    
    def generate_nist_csf_data(self, compliant: bool = True) -> Dict[str, Any]:
        """Generate NIST Cybersecurity Framework test data"""
        if compliant:
            return {
                "governance": {
                    "cybersecurity_strategy": {
                        "documented": True,
                        "approved_by_leadership": True,
                        "regularly_reviewed": True
                    },
                    "oversight_structure": {
                        "exists": True,
                        "defined_roles": True,
                        "clear_accountability": True
                    },
                    "policies": {
                        "cybersecurity_policy": {
                            "exists": True,
                            "current": True,
                            "communicated": True
                        }
                    },
                    "risk_management": {
                        "strategy_documented": True,
                        "risk_tolerance_defined": True,
                        "risk_appetite_communicated": True,
                        "regular_risk_assessments": True,
                        "risk_prioritization_process": True,
                        "risk_response_plans": True
                    },
                    "supply_chain": {
                        "risk_management_program": True,
                        "vendor_assessments": True,
                        "contractual_requirements": True
                    }
                },
                "access_control": {
                    "identity_management": {
                        "centralized_system": True,
                        "lifecycle_management": True,
                        "credential_policies": True
                    },
                    "physical_access": {
                        "controlled_access_points": True,
                        "visitor_management": True,
                        "monitoring_systems": True
                    },
                    "remote_access": {
                        "vpn_required": True,
                        "multi_factor_authentication": True,
                        "encrypted_connections": True
                    }
                }
            }
        else:
            return {
                "governance": {
                    "cybersecurity_strategy": {
                        "documented": False,  # Non-compliant
                        "approved_by_leadership": False,
                        "regularly_reviewed": False
                    },
                    "oversight_structure": {
                        "exists": False,  # Non-compliant
                        "defined_roles": False,
                        "clear_accountability": False
                    }
                },
                "access_control": {
                    "identity_management": {
                        "centralized_system": False,  # Non-compliant
                        "lifecycle_management": False,
                        "credential_policies": False
                    }
                }
            }
    
    def generate_nist_sp800_53_data(self, compliant: bool = True) -> Dict[str, Any]:
        """Generate NIST SP 800-53 test data"""
        if compliant:
            return {
                "ac_controls": {
                    "policy": {
                        "documented": True,
                        "disseminated": True,
                        "reviewed_updated": True
                    },
                    "account_management": {
                        "automated_tools": True,
                        "approval_process": True,
                        "regular_reviews": True,
                        "timely_removal": True
                    },
                    "session_lock": {
                        "inactivity_timeout": 900,  # 15 minutes
                        "pattern_hiding": True,
                        "authentication_required": True
                    },
                    "logon_attempts": {
                        "lockout_configured": True,
                        "maximum_attempts": 3,
                        "lockout_duration": 15
                    },
                    "use_notification": {
                        "banner_displayed": True,
                        "acknowledgment_required": True,
                        "monitoring_consent": True
                    },
                    "remote_access": {
                        "authorized_only": True,
                        "encrypted_connections": True,
                        "monitored_controlled": True
                    }
                }
            }
        else:
            return {
                "ac_controls": {
                    "policy": {
                        "documented": False,  # Non-compliant
                        "disseminated": False,
                        "reviewed_updated": False
                    },
                    "session_lock": {
                        "inactivity_timeout": 3600,  # Too long
                        "pattern_hiding": False,      # Non-compliant
                        "authentication_required": False
                    },
                    "logon_attempts": {
                        "lockout_configured": False,  # Non-compliant
                        "maximum_attempts": 10,       # Too many
                        "lockout_duration": 0
                    }
                }
            }
    
    def generate_nist_sp800_171_data(self, compliant: bool = True) -> Dict[str, Any]:
        """Generate NIST SP 800-171 CUI test data"""
        if compliant:
            return {
                "cui_access": {
                    "user_authorization": {
                        "all_users_authorized": True,
                        "process_authorization": True,
                        "device_authorization": True
                    },
                    "session_lock": {
                        "inactivity_timeout": 900,
                        "pattern_hiding": True,
                        "authentication_required": True
                    },
                    "logon_limits": {
                        "maximum_attempts": 3,
                        "lockout_implemented": True,
                        "lockout_duration": 15
                    },
                    "remote_access": {
                        "session_monitoring": True,
                        "access_control": True,
                        "encrypted_connections": True
                    },
                    "wireless": {
                        "pre_authorization_required": True,
                        "configuration_management": True,
                        "security_controls": True
                    },
                    "mobile_devices": {
                        "connection_controls": True,
                        "device_registration": True,
                        "security_requirements": True
                    }
                }
            }
        else:
            return {
                "cui_access": {
                    "user_authorization": {
                        "all_users_authorized": False,  # Non-compliant
                        "process_authorization": False,
                        "device_authorization": False
                    },
                    "logon_limits": {
                        "maximum_attempts": 5,  # Too many
                        "lockout_implemented": False,
                        "lockout_duration": 0
                    }
                }
            }
    
    def generate_nist_rmf_data(self, compliant: bool = True) -> Dict[str, Any]:
        """Generate NIST RMF test data"""
        if compliant:
            return {
                "system_categorization": {
                    "confidentiality": {
                        "impact_level": "moderate",
                        "rationale": "Contains PII data",
                        "loss_scenario_documented": True
                    },
                    "integrity": {
                        "impact_level": "high", 
                        "rationale": "Financial transaction processing",
                        "loss_scenario_documented": True
                    },
                    "availability": {
                        "impact_level": "moderate",
                        "rationale": "Business operations dependent",
                        "loss_scenario_documented": True
                    },
                    "overall_impact_level": "high",  # High water mark
                    "high_water_mark_applied": True,
                    "rationale_documented": True,
                    "information_types": [
                        {
                            "type": "PII",
                            "confidentiality_impact": "moderate",
                            "integrity_impact": "moderate", 
                            "availability_impact": "low"
                        },
                        {
                            "type": "Financial",
                            "confidentiality_impact": "high",
                            "integrity_impact": "high",
                            "availability_impact": "high"
                        }
                    ],
                    "system_boundary": {
                        "clearly_defined": True,
                        "documented": True,
                        "components_identified": True
                    },
                    "system_owner": {
                        "identified": True,
                        "categorization_approved": True,
                        "responsibilities_documented": True
                    }
                }
            }
        else:
            return {
                "system_categorization": {
                    "confidentiality": {
                        "impact_level": "moderate",
                        "rationale": "",  # Missing rationale
                        "loss_scenario_documented": False
                    },
                    "integrity": {
                        "impact_level": "high",
                        "rationale": "Financial transactions",
                        "loss_scenario_documented": True
                    },
                    "availability": {
                        "impact_level": "moderate", 
                        "rationale": "Business operations",
                        "loss_scenario_documented": True
                    },
                    "overall_impact_level": "moderate",  # Wrong - should be high
                    "high_water_mark_applied": False,   # Non-compliant
                    "rationale_documented": False
                }
            }
    
    def generate_cloud_provider_data(self, provider: str, compliant: bool = True) -> Dict[str, Any]:
        """Generate cloud provider specific test data"""
        if provider.lower() == "aws":
            if compliant:
                return {
                    "iam_users": [
                        {
                            "username": "admin",
                            "mfa_enabled": True,
                            "last_used": "2024-01-15T10:30:00Z",
                            "password_last_changed": "2024-01-01T00:00:00Z"
                        },
                        {
                            "username": "developer",
                            "mfa_enabled": True,
                            "last_used": "2024-01-14T14:22:00Z",
                            "password_last_changed": "2024-01-01T00:00:00Z"
                        }
                    ],
                    "iam_password_policy": {
                        "minimum_password_length": 14,
                        "require_uppercase_characters": True,
                        "require_lowercase_characters": True,
                        "require_symbols": True,
                        "require_numbers": True,
                        "max_password_age": 90,
                        "password_reuse_prevention": 24
                    },
                    "root_account": {
                        "mfa_enabled": True,
                        "hardware_mfa_enabled": True
                    },
                    "root_access_keys": []
                }
            else:
                return {
                    "iam_users": [
                        {
                            "username": "admin",
                            "mfa_enabled": False,  # Non-compliant
                            "last_used": "2023-01-15T10:30:00Z"  # Too old
                        }
                    ],
                    "iam_password_policy": {
                        "minimum_password_length": 8,  # Too short
                        "require_uppercase_characters": False,
                        "require_symbols": False
                    },
                    "root_access_keys": ["AKIA1234567890"]  # Should be empty
                }
        
        elif provider.lower() == "azure":
            if compliant:
                return {
                    "privileged_users": [
                        {"username": "admin", "mfa_enabled": True},
                        {"username": "security_admin", "mfa_enabled": True}
                    ],
                    "non_privileged_users": [
                        {"username": "user1", "mfa_enabled": True},
                        {"username": "user2", "mfa_enabled": True}
                    ],
                    "guest_users": [],
                    "mfa_settings": {
                        "allow_users_to_remember_mfa": False
                    },
                    "password_reset_policy": {
                        "methods_required": 2,
                        "reconfirm_days": 180,
                        "notify_users": True,
                        "notify_all_admins": True
                    }
                }
            else:
                return {
                    "privileged_users": [
                        {"username": "admin", "mfa_enabled": False}  # Non-compliant
                    ],
                    "guest_users": [
                        {"username": "guest1"}  # Should be empty
                    ],
                    "mfa_settings": {
                        "allow_users_to_remember_mfa": True  # Non-compliant
                    }
                }
        
        return {}
    
    def generate_performance_test_data(self, size: str = "medium") -> Dict[str, Any]:
        """Generate test data for performance testing"""
        sizes = {
            "small": {"users": 10, "mounts": 5, "services": 10, "config_lines": 50},
            "medium": {"users": 100, "mounts": 20, "services": 50, "config_lines": 200},
            "large": {"users": 1000, "mounts": 100, "services": 200, "config_lines": 1000},
            "xlarge": {"users": 10000, "mounts": 500, "services": 1000, "config_lines": 5000}
        }
        
        config = sizes.get(size, sizes["medium"])
        
        # Generate large SSH config
        ssh_config = [f"CustomOption{i} value{i}" for i in range(config["config_lines"])]
        ssh_config.extend([
            "Protocol 2",
            "PermitRootLogin no",
            "MaxAuthTries 4"
        ])
        
        # Generate multiple mounts
        mounts = {}
        for i in range(config["mounts"]):
            mounts[f"/mount{i}"] = {
                "device": f"/dev/sd{chr(97 + i % 26)}{i // 26 + 1}",
                "fstype": "ext4",
                "options": ["rw", "nodev"]
            }
        
        # Generate services
        services = {}
        for i in range(config["services"]):
            services[f"service{i}"] = {
                "enabled": i % 2 == 0,
                "running": i % 3 == 0
            }
        
        return {
            "os_family": "RedHat",
            "distribution": "CentOS",
            "distribution_version": "9.0",
            "selinux_status": "enforcing",
            "firewall_enabled": True,
            "ssh_config": ssh_config,
            "mounts": mounts,
            "services": services,
            "user_count": config["users"],
            "performance_test_size": size
        }
    
    def generate_test_suite(self) -> Dict[str, Any]:
        """Generate complete test suite with all framework data"""
        return {
            "test_metadata": {
                "generated_at": self.timestamp,
                "generator_version": "1.0.0",
                "description": "Comprehensive test data for CIS and NIST compliance validation"
            },
            "cis_tests": {
                "linux_compliant": self.generate_cis_linux_data(True),
                "linux_non_compliant": self.generate_cis_linux_data(False)
            },
            "nist_csf_tests": {
                "csf_compliant": self.generate_nist_csf_data(True),
                "csf_non_compliant": self.generate_nist_csf_data(False)
            },
            "nist_sp800_53_tests": {
                "sp800_53_compliant": self.generate_nist_sp800_53_data(True),
                "sp800_53_non_compliant": self.generate_nist_sp800_53_data(False)
            },
            "nist_sp800_171_tests": {
                "sp800_171_compliant": self.generate_nist_sp800_171_data(True),
                "sp800_171_non_compliant": self.generate_nist_sp800_171_data(False)
            },
            "nist_rmf_tests": {
                "rmf_compliant": self.generate_nist_rmf_data(True),
                "rmf_non_compliant": self.generate_nist_rmf_data(False)
            },
            "cloud_provider_tests": {
                "aws_compliant": self.generate_cloud_provider_data("aws", True),
                "aws_non_compliant": self.generate_cloud_provider_data("aws", False),
                "azure_compliant": self.generate_cloud_provider_data("azure", True),
                "azure_non_compliant": self.generate_cloud_provider_data("azure", False)
            },
            "performance_tests": {
                "small_dataset": self.generate_performance_test_data("small"),
                "medium_dataset": self.generate_performance_test_data("medium"),
                "large_dataset": self.generate_performance_test_data("large"),
                "xlarge_dataset": self.generate_performance_test_data("xlarge")
            }
        }

def main():
    parser = argparse.ArgumentParser(description="Generate test data for compliance frameworks")
    parser.add_argument("--framework", choices=["cis", "nist-csf", "nist-sp800-53", "nist-sp800-171", "nist-rmf", "all"], 
                       default="all", help="Framework to generate test data for")
    parser.add_argument("--compliant", action="store_true", help="Generate compliant test data only")
    parser.add_argument("--non-compliant", action="store_true", help="Generate non-compliant test data only")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--performance", choices=["small", "medium", "large", "xlarge"], 
                       help="Generate performance test data of specified size")
    
    args = parser.parse_args()
    
    generator = TestDataGenerator()
    
    if args.performance:
        test_data = generator.generate_performance_test_data(args.performance)
    elif args.framework == "all":
        test_data = generator.generate_test_suite()
    else:
        # Generate specific framework data
        if args.framework == "cis":
            if args.non_compliant:
                test_data = generator.generate_cis_linux_data(False)
            else:
                test_data = generator.generate_cis_linux_data(True)
        elif args.framework == "nist-csf":
            if args.non_compliant:
                test_data = generator.generate_nist_csf_data(False)
            else:
                test_data = generator.generate_nist_csf_data(True)
        # Add other framework-specific generation...
    
    # Output the test data
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(test_data, f, indent=2)
        print(f"Test data written to {args.output}")
    else:
        print(json.dumps(test_data, indent=2))

if __name__ == "__main__":
    main()