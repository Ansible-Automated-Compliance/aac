package performance_tests
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
# This is a simplified rule to enable generic compliance performance tests
default allow := false

allow if {
    input.selinux_status == "enforcing"
    input.firewall_enabled == true
}

# =============================================================================
# PERFORMANCE BENCHMARKING TESTS
# =============================================================================

# Test large input handling - filesystem mounts
test_large_filesystem_input_performance if {
    generated_mounts := {
        sprintf("/mount%d", [i]): {
            "device": sprintf("/dev/disk%d", [i]),
            "fstype": "ext4",
            "options": ["rw", "nodev", "nosuid", "noexec"]
        } | i := numbers.range(1, 1000)
    }
    # Include /tmp so tmp_configured checks pass
    large_mounts := object.union(generated_mounts, {
        "/tmp": {
            "device": "tmpfs",
            "fstype": "tmpfs",
            "options": ["rw", "nodev", "nosuid", "noexec"]
        }
    })

    start_time := time.now_ns()

    # Test filesystem checks with large input
    filesystem.tmp_configured with input as {"mounts": large_mounts}
    filesystem.tmp_nodev with input as {"mounts": large_mounts}
    filesystem.tmp_nosuid with input as {"mounts": large_mounts}
    filesystem.tmp_noexec with input as {"mounts": large_mounts}
    
    end_time := time.now_ns()
    duration_ms := (end_time - start_time) / 1000000
    
    # Performance assertion - should complete within 1000ms
    duration_ms < 1000
}

# Test large SSH configuration processing
test_large_ssh_config_performance if {
    large_ssh_config := array.concat(
        [sprintf("Comment%d", [i]) | i := numbers.range(1, 5000)],
        [
            "Protocol 2",
            "PermitRootLogin no",
            "MaxAuthTries 4",
            "PasswordAuthentication yes"
        ]
    )
    
    start_time := time.now_ns()
    
    # Test SSH configuration checks
    access_control.ssh_root_login_disabled with input as {"ssh_config": large_ssh_config}
    access_control.ssh_maxauthtries_limited with input as {"ssh_config": large_ssh_config}
    
    end_time := time.now_ns()
    duration_ms := (end_time - start_time) / 1000000
    
    # Should process large config within 500ms
    duration_ms < 500
}

# Test complex nested data structures
test_complex_nested_data_performance if {
    complex_input := {
        "governance": {
            "risk_calculation": {
                "standardized_methodology": true,
                "consistent_metrics": true,
                "regular_monitoring": true,
                "sub_strategies": {
                    sprintf("strategy_%d", [i]): {
                        "name": sprintf("Strategy %d", [i]),
                        "owner": sprintf("owner%d@company.com", [i]),
                        "review_date": "2024-01-01",
                        "controls": [sprintf("control_%d_%d", [i, j]) | j := numbers.range(1, 10)]
                    } | i := numbers.range(1, 100)
                }
            }
        }
    }
    
    start_time := time.now_ns()
    
    # Test NIST CSF governance checks
    govern.standardized_risk_calculation with input as complex_input
    
    end_time := time.now_ns()
    duration_ms := (end_time - start_time) / 1000000
    
    # Should handle complex nested data within 200ms
    duration_ms < 200
}

# Test high-volume user access control data
test_high_volume_access_control_performance if {
    high_volume_input := {
        "cui_access": {
            "user_authorization": {
                "all_users_authorized": true,
                "process_authorization": true,
                "device_authorization": true,
                "user_details": {
                    sprintf("user_%d", [i]): {
                        "username": sprintf("user%d", [i]),
                        "role": sprintf("role_%d", [i % 10]),
                        "last_login": "2024-01-01T00:00:00Z",
                        "permissions": [sprintf("perm_%d", [j]) | some j in numbers.range(1, 20)]
                    } | some i in numbers.range(1, 10000)
                }
            }
        }
    }
    
    start_time := time.now_ns()
    
    # Test CUI access control checks
    cui_ac.authorized_access_only with input as high_volume_input
    
    end_time := time.now_ns()
    duration_ms := (end_time - start_time) / 1000000
    
    # Should process 10,000 users within 1500ms
    duration_ms < 1500
}

# Test multiple policy evaluations simultaneously
test_concurrent_policy_evaluation_performance if {
    base_input := {
        "os_family": "RedHat",
        "distribution": "CentOS",
        "distribution_version": "9.0",
        "selinux_status": "enforcing",
        "firewall_enabled": true,
        "ssh_port": 22,
        "loaded_modules": ["ext4", "xfs", "btrfs"],
        "mounts": {
            "/tmp": {
                "device": "/dev/sda2",
                "fstype": "ext4",
                "options": ["rw", "nodev", "nosuid", "noexec"]
            }
        },
        "net_ipv4_ip_forward": 0,
        "ssh_config": [
            "Protocol 2",
            "PermitRootLogin no",
            "MaxAuthTries 4"
        ]
    }
    
    start_time := time.now_ns()
    
    # Evaluate multiple policies concurrently
    cis_result := allow with input as base_input
    filesystem_result := filesystem.cramfs_disabled with input as base_input
    network_result := network.ip_forwarding_disabled with input as base_input
    ssh_result := access_control.ssh_root_login_disabled with input as base_input
    tmp_result := filesystem.tmp_configured with input as base_input
    
    end_time := time.now_ns()
    duration_ms := (end_time - start_time) / 1000000

    # All evaluations should complete quickly
    every result in [cis_result, filesystem_result, network_result, ssh_result, tmp_result] { result }
    duration_ms < 100
}

# Test RMF categorization with extensive system data
test_rmf_categorization_performance if {
    extensive_categorization := {
        "system_categorization": {
            "confidentiality": {"impact_level": "moderate"},
            "integrity": {"impact_level": "high"},
            "availability": {"impact_level": "low"},
            "overall_impact_level": "high",
            "high_water_mark_applied": true,
            "rationale_documented": true,
            "information_types": [
                {
                    "type": sprintf("info_type_%d", [i]),
                    "confidentiality_impact": "moderate",
                    "integrity_impact": "high", 
                    "availability_impact": "low",
                    "description": sprintf("Information type %d description", [i])
                } | i := numbers.range(1, 500)
            ],
            "system_boundary": {
                "clearly_defined": true,
                "documented": true,
                "components_identified": true,
                "components": [sprintf("component_%d", [i]) | i := numbers.range(1, 200)]
            },
            "external_dependencies": [
                {
                    "service_provider": sprintf("provider_%d", [i]),
                    "categorization_level": "moderate",
                    "risk_assessment_completed": true
                } | i := numbers.range(1, 50)
            ]
        }
    }
    
    start_time := time.now_ns()
    
    # Test RMF categorization with extensive data
    categorize.high_water_mark_properly_applied with input as extensive_categorization
    categorize.information_types_identified with input as extensive_categorization
    categorize.system_boundary_defined with input as extensive_categorization
    categorize.external_dependencies_identified with input as extensive_categorization
    
    end_time := time.now_ns()
    duration_ms := (end_time - start_time) / 1000000
    
    # Should handle extensive categorization data within 800ms
    duration_ms < 800
}

# Test NIST SP 800-53 access control with large control set
test_nist_sp800_53_large_control_set_performance if {
    large_ac_input := {
        "ac_controls": {
            "session_lock": {
                "inactivity_timeout": 900,
                "pattern_hiding": true,
                "authentication_required": true
            },
            "logon_attempts": {
                "lockout_configured": true,
                "maximum_attempts": 3,
                "lockout_duration": 15,
                "attempt_history": [
                    {
                        "timestamp": sprintf("2024-01-01T%02d:%02d:00Z", [h, m]),
                        "user": sprintf("user_%d", [u]),
                        "success": (u % 3) == 0
                    } | some h in numbers.range(0, 23); some m in numbers.range(0, 59); some u in numbers.range(1, 10)
                ]
            },
            "account_management": {
                "automated_tools": true,
                "approval_process": true,
                "regular_reviews": true,
                "timely_removal": true,
                "accounts": {
                    sprintf("account_%d", [i]): {
                        "username": sprintf("user%d", [i]),
                        "created": "2024-01-01",
                        "last_review": "2024-06-01",
                        "status": "active"
                    } | i := numbers.range(1, 1000)
                }
            }
        }
    }
    
    start_time := time.now_ns()
    
    # Test multiple NIST SP 800-53 controls
    nist_ac.session_lock with input as large_ac_input
    nist_ac.unsuccessful_logon_attempts with input as large_ac_input
    nist_ac.account_management with input as large_ac_input
    
    end_time := time.now_ns()
    duration_ms := (end_time - start_time) / 1000000
    
    # Should process large control set within 600ms
    duration_ms < 600
}

# Test memory efficiency with repeated evaluations
test_memory_efficiency_repeated_evaluations if {
    test_input := {
        "os_family": "RedHat",
        "selinux_status": "enforcing",
        "firewall_enabled": true,
        "ssh_port": 22
    }
    
    start_time := time.now_ns()

    # Repeat the same evaluation many times to test memory efficiency
    results := [result |
        some i in numbers.range(1, 1000)
        result := allow with input as test_input
    ]

    end_time := time.now_ns()
    duration_ms := (end_time - start_time) / 1000000

    # All results should be true and complete within reasonable time
    count(results) == 1000
    every r in results { r }
    duration_ms < 2000
}

# Test policy evaluation under resource constraints
test_resource_constrained_evaluation if {
    # Create a moderately complex input that tests multiple policies
    constrained_input := {
        "governance": {
            "risk_calculation": {
                "standardized_methodology": true,
                "consistent_metrics": true,
                "regular_monitoring": true
            }
        },
        "access_control": {
            "identity_proofing": {
                "verification_processes": true,
                "credential_binding": true,
                "assertion_mechanisms": true
            }
        },
        "ac_controls": {
            "session_lock": {
                "inactivity_timeout": 900,
                "pattern_hiding": true,
                "authentication_required": true
            }
        },
        "cui_access": {
            "user_authorization": {
                "all_users_authorized": true,
                "process_authorization": true,
                "device_authorization": true
            }
        },
        "system_categorization": {
            "confidentiality": {"impact_level": "moderate"},
            "integrity": {"impact_level": "high"},
            "availability": {"impact_level": "low"},
            "overall_impact_level": "high"
        }
    }
    
    start_time := time.now_ns()
    
    # Test multiple frameworks simultaneously
    csf_govern := govern.standardized_risk_calculation with input as constrained_input
    csf_protect := protect.identity_proofing with input as constrained_input
    sp800_53 := nist_ac.session_lock with input as constrained_input
    sp800_171 := cui_ac.authorized_access_only with input as constrained_input
    rmf_cat := categorize.high_water_mark_properly_applied with input as constrained_input
    
    end_time := time.now_ns()
    duration_ms := (end_time - start_time) / 1000000

    # All evaluations should succeed and complete within time limit
    every result in [csf_govern, csf_protect, sp800_53, sp800_171, rmf_cat] { result }
    duration_ms < 300
}

# =============================================================================
# SCALABILITY TESTS
# =============================================================================

# Test scaling with increasing data sizes
test_scalability_increasing_data_sizes if {
    # Test with small, medium, and large data sets
    small_size := 10
    medium_size := 100
    large_size := 1000
    
    # Small dataset test
    small_input := {
        "loaded_modules": [sprintf("module_%d", [i]) | i := numbers.range(1, small_size)]
    }
    small_start := time.now_ns()
    small_result := filesystem.cramfs_disabled with input as small_input
    small_duration := (time.now_ns() - small_start) / 1000000
    
    # Medium dataset test
    medium_input := {
        "loaded_modules": [sprintf("module_%d", [i]) | i := numbers.range(1, medium_size)]
    }
    medium_start := time.now_ns()
    medium_result := filesystem.cramfs_disabled with input as medium_input
    medium_duration := (time.now_ns() - medium_start) / 1000000
    
    # Large dataset test
    large_input := {
        "loaded_modules": [sprintf("module_%d", [i]) | i := numbers.range(1, large_size)]
    }
    large_start := time.now_ns()
    large_result := filesystem.cramfs_disabled with input as large_input
    large_duration := (time.now_ns() - large_start) / 1000000

    # Verify all evaluations returned a boolean result
    every result in [small_result, medium_result, large_result] { result }

    # Performance should complete within generous CI-safe limits
    large_duration < 5000

    # Scaling ratio: guard against divide-by-zero when sub-ms evaluations round to 0
    safe_small := max([small_duration, 1])
    scaling_ratio := large_duration / safe_small
    scaling_ratio < 500  # Should not be more than 500x slower for 100x data
}