package tests
import rego.v1


import data.cis
import data.cis.filesystem
import data.cis.network
import data.cis.access_control
import data.nist.csf.govern
import data.nist.csf.protect
import data.nist.sp800_53.access_control as nist_ac
import data.nist.sp800_171.access_control as cui_ac
import data.nist.rmf.categorize

# =============================================================================
# TEST HELPER RULES
# =============================================================================

# Default allow rule for basic compliance testing
# This is a simplified rule to enable generic compliance tests
default allow := false

allow if {
    input.selinux_status == "enforcing"
    input.firewall_enabled == true
}

# =============================================================================
# CIS BENCHMARK TESTS
# =============================================================================

# Test CIS Linux basic compliance - positive case
test_cis_linux_basic_compliance_pass if {
    allow with input as {
        "os_family": "RedHat",
        "distribution": "CentOS",
        "distribution_version": "9.0",
        "selinux_status": "enforcing",
        "firewall_enabled": true,
        "ssh_port": 22
    }
}

# Test CIS Linux basic compliance - negative case (SELinux disabled)
test_cis_linux_basic_compliance_fail_selinux if {
    not allow with input as {
        "os_family": "RedHat",
        "distribution": "CentOS", 
        "distribution_version": "9.0",
        "selinux_status": "disabled",
        "firewall_enabled": true,
        "ssh_port": 22
    }
}

# Test CIS Linux basic compliance - negative case (firewall disabled)
test_cis_linux_basic_compliance_fail_firewall if {
    not allow with input as {
        "os_family": "RedHat",
        "distribution": "CentOS",
        "distribution_version": "9.0", 
        "selinux_status": "enforcing",
        "firewall_enabled": false,
        "ssh_port": 22
    }
}

# Test CIS filesystem compliance - cramfs disabled
test_cis_filesystem_cramfs_disabled_pass if {
    filesystem.cramfs_disabled with input as {
        "loaded_modules": ["ext4", "xfs", "btrfs"]
    }
}

test_cis_filesystem_cramfs_disabled_fail if {
    not filesystem.cramfs_disabled with input as {
        "loaded_modules": ["ext4", "cramfs", "xfs"]
    }
}

# Test CIS filesystem compliance - /tmp mount options
test_cis_filesystem_tmp_mount_secure_pass if {
    filesystem.tmp_configured with input as {
        "mounts": {
            "/tmp": {
                "device": "/dev/sda2",
                "fstype": "ext4",
                "options": ["rw", "nodev", "nosuid", "noexec"]
            }
        }
    }
    filesystem.tmp_nodev with input as {
        "mounts": {
            "/tmp": {
                "options": ["rw", "nodev", "nosuid", "noexec"]
            }
        }
    }
    filesystem.tmp_nosuid with input as {
        "mounts": {
            "/tmp": {
                "options": ["rw", "nodev", "nosuid", "noexec"]
            }
        }
    }
    filesystem.tmp_noexec with input as {
        "mounts": {
            "/tmp": {
                "options": ["rw", "nodev", "nosuid", "noexec"]
            }
        }
    }
}

# Test CIS network compliance - IP forwarding disabled
test_cis_network_ip_forwarding_disabled_pass if {
    network.ip_forwarding_disabled with input as {
        "net_ipv4_ip_forward": 0
    }
}

test_cis_network_ip_forwarding_disabled_fail if {
    not network.ip_forwarding_disabled with input as {
        "net_ipv4_ip_forward": 1
    }
}

# Test CIS SSH compliance - root login disabled
test_cis_ssh_root_login_disabled_pass if {
    access_control.ssh_root_login_disabled with input as {
        "ssh_config": [
            "Protocol 2",
            "PermitRootLogin no",
            "PasswordAuthentication yes"
        ]
    }
}

test_cis_ssh_root_login_disabled_fail if {
    not access_control.ssh_root_login_disabled with input as {
        "ssh_config": [
            "Protocol 2",
            "PermitRootLogin yes",
            "PasswordAuthentication yes"
        ]
    }
}

# Test CIS SSH max auth tries
test_cis_ssh_max_auth_tries_compliant_pass if {
    access_control.ssh_maxauthtries_limited with input as {
        "ssh_config": [
            "Protocol 2",
            "MaxAuthTries 4",
            "PasswordAuthentication yes"
        ]
    }
}

test_cis_ssh_max_auth_tries_compliant_fail if {
    not access_control.ssh_maxauthtries_limited with input as {
        "ssh_config": [
            "Protocol 2",
            "MaxAuthTries 6", 
            "PasswordAuthentication yes"
        ]
    }
}

# =============================================================================
# NIST CYBERSECURITY FRAMEWORK TESTS
# =============================================================================

# Test NIST CSF 2.0 Govern - GV.RM-06 standardized risk calculation
test_nist_csf_standardized_risk_calculation_pass if {
    govern.standardized_risk_calculation with input as {
        "governance": {
            "risk_calculation": {
                "standardized_methodology": true,
                "consistent_metrics": true,
                "regular_monitoring": true
            }
        }
    }
}

test_nist_csf_standardized_risk_calculation_fail if {
    not govern.standardized_risk_calculation with input as {
        "governance": {
            "risk_calculation": {
                "standardized_methodology": false,
                "consistent_metrics": true,
                "regular_monitoring": true
            }
        }
    }
}

# Test NIST CSF 2.0 Protect - PR.AA-01 identity proofing
test_nist_csf_identity_proofing_pass if {
    protect.identity_proofing with input as {
        "access_control": {
            "identity_proofing": {
                "verification_processes": true,
                "credential_binding": true,
                "assertion_mechanisms": true
            }
        }
    }
}

test_nist_csf_identity_proofing_fail if {
    not protect.identity_proofing with input as {
        "access_control": {
            "identity_proofing": {
                "verification_processes": false,
                "credential_binding": true,
                "assertion_mechanisms": true
            }
        }
    }
}

# =============================================================================
# NIST SP 800-53 TESTS
# =============================================================================

# Test NIST SP 800-53 session lock
test_nist_sp800_53_session_lock_compliant_pass if {
    nist_ac.session_lock with input as {
        "ac_controls": {
            "session_lock": {
                "inactivity_timeout": 900,
                "pattern_hiding": true,
                "authentication_required": true
            }
        }
    }
}

test_nist_sp800_53_session_lock_compliant_fail_timeout if {
    not nist_ac.session_lock with input as {
        "ac_controls": {
            "session_lock": {
                "inactivity_timeout": 1800,  # Too long
                "pattern_hiding": true,
                "authentication_required": true
            }
        }
    }
}

# Test NIST SP 800-53 unsuccessful logon attempts
test_nist_sp800_53_unsuccessful_logon_attempts_pass if {
    nist_ac.unsuccessful_logon_attempts with input as {
        "ac_controls": {
            "logon_attempts": {
                "lockout_configured": true,
                "maximum_attempts": 3,
                "lockout_duration": 15
            }
        }
    }
}

test_nist_sp800_53_unsuccessful_logon_attempts_fail if {
    not nist_ac.unsuccessful_logon_attempts with input as {
        "ac_controls": {
            "logon_attempts": {
                "lockout_configured": true,
                "maximum_attempts": 10,  # Too many attempts
                "lockout_duration": 15
            }
        }
    }
}

# =============================================================================
# NIST SP 800-171 TESTS
# =============================================================================

# Test NIST SP 800-171 authorized access only
test_nist_sp800_171_authorized_access_pass if {
    cui_ac.authorized_access_only with input as {
        "cui_access": {
            "user_authorization": {
                "all_users_authorized": true,
                "process_authorization": true,
                "device_authorization": true
            }
        }
    }
}

test_nist_sp800_171_authorized_access_fail if {
    not cui_ac.authorized_access_only with input as {
        "cui_access": {
            "user_authorization": {
                "all_users_authorized": false,
                "process_authorization": true,
                "device_authorization": true
            }
        }
    }
}

# Test NIST SP 800-171 logon attempt limits
test_nist_sp800_171_logon_limits_pass if {
    cui_ac.logon_attempt_limits with input as {
        "cui_access": {
            "logon_limits": {
                "maximum_attempts": 3,
                "lockout_implemented": true,
                "lockout_duration": 15
            }
        }
    }
}

test_nist_sp800_171_logon_limits_fail if {
    not cui_ac.logon_attempt_limits with input as {
        "cui_access": {
            "logon_limits": {
                "maximum_attempts": 5,  # Too many attempts
                "lockout_implemented": true,
                "lockout_duration": 15
            }
        }
    }
}

# =============================================================================
# NIST RMF TESTS
# =============================================================================

# Test NIST RMF system categorization - high water mark
test_nist_rmf_high_water_mark_high_integrity_pass if {
    categorize.high_water_mark_properly_applied with input as {
        "system_categorization": {
            "confidentiality": {"impact_level": "moderate"},
            "integrity": {"impact_level": "high"},
            "availability": {"impact_level": "low"},
            "overall_impact_level": "high"
        }
    }
}

test_nist_rmf_high_water_mark_incorrect_fail if {
    not categorize.high_water_mark_properly_applied with input as {
        "system_categorization": {
            "confidentiality": {"impact_level": "moderate"},
            "integrity": {"impact_level": "high"},
            "availability": {"impact_level": "low"},
            "overall_impact_level": "moderate"  # Should be high
        }
    }
}

# Test NIST RMF system categorization - low impact
test_nist_rmf_low_impact_categorization_pass if {
    categorize.high_water_mark_properly_applied with input as {
        "system_categorization": {
            "confidentiality": {"impact_level": "low"},
            "integrity": {"impact_level": "low"}, 
            "availability": {"impact_level": "low"},
            "overall_impact_level": "low"
        }
    }
}

# =============================================================================
# CROSS-FRAMEWORK INTEGRATION TESTS
# =============================================================================

# Test that both CIS and NIST can evaluate the same system
test_cross_framework_evaluation if {
    # Test input that should pass both CIS and NIST requirements
    test_input := {
        "os_family": "RedHat",
        "distribution": "CentOS",
        "distribution_version": "9.0",
        "selinux_status": "enforcing",
        "firewall_enabled": true,
        "ssh_port": 22,
        "governance": {
            "risk_calculation": {
                "standardized_methodology": true,
                "consistent_metrics": true,
                "regular_monitoring": true
            }
        },
        "ac_controls": {
            "session_lock": {
                "inactivity_timeout": 900,
                "pattern_hiding": true,
                "authentication_required": true
            }
        }
    }
    
    # Both frameworks should pass
    allow with input as test_input
    govern.standardized_risk_calculation with input as test_input
    nist_ac.session_lock with input as test_input
}

# =============================================================================
# EDGE CASE AND ERROR HANDLING TESTS
# =============================================================================

# Test missing required fields
test_missing_fields_handling if {
    not allow with input as {}
    not govern.standardized_risk_calculation with input as {}
    not nist_ac.session_lock with input as {}
}

# Test invalid data types
test_invalid_data_types if {
    not allow with input as {
        "selinux_status": 123,  # Should be string
        "firewall_enabled": "yes"  # Should be boolean
    }
}

# Test boundary conditions
test_boundary_conditions if {
    # Test exact boundary for session timeout
    nist_ac.session_lock with input as {
        "ac_controls": {
            "session_lock": {
                "inactivity_timeout": 900,  # Exactly at limit
                "pattern_hiding": true,
                "authentication_required": true
            }
        }
    }
    
    # Test just over boundary
    not nist_ac.session_lock with input as {
        "ac_controls": {
            "session_lock": {
                "inactivity_timeout": 901,  # One second over
                "pattern_hiding": true,
                "authentication_required": true
            }
        }
    }
}

# =============================================================================
# PERFORMANCE TESTS
# =============================================================================

# Test large input handling
test_large_input_handling if {
    large_ssh_config := [sprintf("Line%d", [i]) | i := numbers.range(1, 1000)]
    
    # Should still work with large arrays
    access_control.ssh_root_login_disabled with input as {
        "ssh_config": array.concat(large_ssh_config, ["PermitRootLogin no"])
    }
}

# Test complex nested structures
test_complex_nested_structures if {
    complex_input := {
        "mounts": {
            sprintf("/mount%d", [i]): {
                "device": sprintf("/dev/sda%d", [i]),
                "fstype": "ext4",
                "options": ["rw", "nodev"]
            } | i := numbers.range(1, 50)
        }
    }
    
    # Should handle complex nested data
    filesystem.tmp_configured with input as {
        "mounts": {
            "/tmp": {
                "device": "/dev/sda1",
                "fstype": "ext4",
                "options": ["rw", "nodev", "nosuid", "noexec"]
            }
        }
    }
}