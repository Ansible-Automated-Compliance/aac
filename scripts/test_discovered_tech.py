"""Unit tests for scripts/discovered_tech.py (discovered facts → loader_keys)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import discovered_tech as dt  # noqa: E402


def test_os_to_tech_rhel_ubuntu_windows():
    assert dt.os_to_tech("RedHat", "RedHat", "9.3") == "rhel_9"
    assert dt.os_to_tech("RedHat", "CentOS", "8.5") == "rhel_8"
    assert dt.os_to_tech("Debian", "Ubuntu", "22.04") == "ubuntu_2204"
    assert dt.os_to_tech("Debian", "Ubuntu", "24.04") == "ubuntu_2404"
    assert dt.os_to_tech("RedHat", "Rocky", "9.2") == "rocky_9"
    assert dt.os_to_tech("RedHat", "AlmaLinux", "9.2") == "rhel_9"
    assert dt.os_to_tech("Windows", "Microsoft Windows Server 2022 Datacenter", "10.0") == "windows_2022"
    assert dt.os_to_tech("Amazon", "Amazon", "2023") == "amazon_linux_2023"


def test_os_to_tech_unknown_is_none():
    assert dt.os_to_tech("Darwin", "macOS", "14") is None
    assert dt.os_to_tech("RedHat", "RHEL", "7.9") is None  # unsupported major


def test_cloud_and_product():
    assert dt.cloud_to_tech("aws") == "aws"
    assert dt.cloud_to_tech("Microsoft Azure") == "azure"
    assert dt.cloud_to_tech("") is None
    assert dt.product_to_tech("VMware", "vCenter") == "vmware"
    assert dt.product_to_tech("", "kubernetes") == "kubernetes"
    assert dt.product_to_tech("Red Hat", "OpenShift") == "openshift"


def test_signals_to_loader_keys_end_to_end():
    signals = [
        {"os_family": "RedHat", "os_distribution": "RedHat", "os_version": "9.3", "cloud_provider": "aws"},
        {"os_family": "Windows", "os_distribution": "Windows Server 2022", "os_version": "10.0"},
        {"vendor": "VMware", "product": "vcenter", "version": "8.0"},
    ]
    keys, _ = dt.discovered_loader_keys(signals)
    # rhel_9 -> cis_rhel9 + stigs; aws -> cis_aws; windows_2022 -> cis_windows_2022 + stigs;
    # vmware -> cis_vmware
    assert {"cis_rhel9", "cis_aws", "cis_windows_2022", "cis_vmware", "stigs"}.issubset(keys)
    # A RHEL/AWS/Windows/VMware estate must NOT pull Ubuntu or OT keys.
    assert "cis_ubuntu_2204" not in keys
    assert "nerc_cip" not in keys


def test_empty_signals_yield_no_keys():
    keys, _ = dt.discovered_loader_keys([])
    # only always_on (empty by default) -> no keys
    assert keys == set()
