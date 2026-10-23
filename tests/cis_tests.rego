package cis_tests
import rego.v1


import data.cis
import data.cis.filesystem
import data.cis.network
import data.cis.access_control

# Test basic CIS compliance
test_basic_compliance if {
    allow with input as {
        "os_family": "RedHat",
        "distribution": "CentOS",
        "distribution_version": "9.0",
        "selinux_status": "enforcing",
        "firewall_enabled": true,
        "ssh_port": 22
    }
}

test_basic_compliance_fail_selinux if {
    not allow with input as {
        "os_family": "RedHat",
        "distribution": "CentOS",
        "distribution_version": "9.0",
        "selinux_status": "disabled",
        "firewall_enabled": true,
        "ssh_port": 22
    }
}

# Test filesystem compliance
test_filesystem_cramfs_disabled if {
    filesystem.cramfs_disabled with input as {
        "loaded_modules": ["ext4", "xfs"]
    }
}

test_filesystem_cramfs_enabled_fail if {
    not filesystem.cramfs_disabled with input as {
        "loaded_modules": ["ext4", "cramfs", "xfs"]
    }
}

test_tmp_mount_configured if {
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

# Test network compliance
test_ip_forwarding_disabled if {
    network.ip_forwarding_disabled with input as {
        "net_ipv4_ip_forward": 0
    }
}

test_ip_forwarding_enabled_fail if {
    not network.ip_forwarding_disabled with input as {
        "net_ipv4_ip_forward": 1
    }
}

test_tcp_syn_cookies_enabled if {
    network.tcp_syn_cookies with input as {
        "net_ipv4_tcp_syncookies": 1
    }
}

# Test access control compliance
test_ssh_root_login_disabled if {
    access_control.ssh_root_login_disabled with input as {
        "ssh_config": [
            "Protocol 2",
            "PermitRootLogin no",
            "PasswordAuthentication yes"
        ]
    }
}

test_ssh_root_login_enabled_fail if {
    not access_control.ssh_root_login_disabled with input as {
        "ssh_config": [
            "Protocol 2",
            "PermitRootLogin yes", 
            "PasswordAuthentication yes"
        ]
    }
}

test_ssh_max_auth_tries_compliant if {
    access_control.ssh_maxauthtries_limited with input as {
        "ssh_config": [
            "Protocol 2",
            "MaxAuthTries 4",
            "PasswordAuthentication yes"
        ]
    }
}

test_ssh_max_auth_tries_non_compliant if {
    not access_control.ssh_maxauthtries_limited with input as {
        "ssh_config": [
            "Protocol 2", 
            "MaxAuthTries 6",
            "PasswordAuthentication yes"
        ]
    }
}