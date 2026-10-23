> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: none specific — unreviewed for 293 days.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Integration with OPA CIS Compliance Library

This document explains how Ansible's `gather_facts` provides comprehensive key-value data that maps directly to our OPA Rego policies for CIS compliance validation across all technology platforms.

## Overview

Ansible's `gather_facts: yes` directive automatically collects system information and creates a structured JSON data model that contains exactly the information needed to evaluate CIS benchmarks across multiple technology stacks.

## Key Integration Points

### 1. Operating Systems

**Ansible Facts Available:**
```yaml
ansible_facts:
  os_family: "RedHat"
  distribution: "CentOS" 
  distribution_version: "8.4"
  kernel: "Linux"
  architecture: "x86_64"
  selinux:
    status: "enforcing"
    mode: "enforcing"
  services:
    sshd:
      state: "running"
      status: "enabled"
  mounts:
    - mount: "/tmp"
      device: "/dev/sda2"
      fstype: "ext4"
      options: "rw,nodev,nosuid,noexec"
  interfaces: ["eth0", "lo"]
  iptables: {...}
```

**Maps to Rego Policies:**
- `policies/operating_systems/linux/redhat/` - Linux CIS controls
- `policies/operating_systems/linux/ubuntu/` - Ubuntu CIS controls  
- `policies/operating_systems/windows/server_2022/` - Windows CIS controls

### 2. Cloud Providers

**Ansible Facts Available:**
```yaml
# AWS EC2 Instance
ansible_facts:
  ec2_instance_id: "i-1234567890abcdef0"
  ec2_placement_region: "us-west-2"
  ec2_security_groups: ["sg-12345678"]
  ec2_instance_type: "t3.medium"

# Azure VM
ansible_facts:
  azure_subscription_id: "12345678-1234-1234-1234-123456789012"
  azure_resource_group: "my-rg"
  azure_location: "eastus"
```

**Maps to Rego Policies:**
- `policies/cloud_providers/aws/01_identity_access_management/` - AWS IAM controls
- `policies/cloud_providers/azure/01_identity_access_management/` - Azure IAM controls

### 3. Server Software

**Ansible Facts Available:**
```yaml
# Discovered through package facts or service detection
discovered_software:
  apache:
    installed: true
    version: "2.4.41"
    config_path: "/etc/httpd/conf/httpd.conf"
    running: true
  mysql:
    installed: true
    version: "8.0.25"
    config_path: "/etc/mysql/my.cnf"
    data_dir: "/var/lib/mysql"
  nginx:
    installed: false
```

**Maps to Rego Policies:**
- `policies/server_software/apache/` - Apache HTTP Server CIS controls
- `policies/server_software/mysql/` - MySQL Database CIS controls
- `policies/server_software/nginx/` - NGINX CIS controls

### 4. Container Platforms

**Ansible Facts Available:**
```yaml
container_runtime:
  docker:
    installed: true
    version: "20.10.7"
    daemon_config: "/etc/docker/daemon.json"
    running: true
  kubernetes:
    installed: true
    version: "v1.21.3"
    config_path: "/etc/kubernetes"
```

**Maps to Rego Policies:**
- `policies/devsecops_tools/docker/01_host_configuration/` - Docker CIS controls
- `policies/devsecops_tools/kubernetes/01_master_node_security/` - Kubernetes CIS controls

### 5. Network Devices

**Ansible Facts Available (for network equipment):**
```yaml
ansible_facts:
  network_os: "ios"
  ansible_net_hostname: "router01"
  ansible_net_version: "15.1(4)M4"
  ansible_net_platform: "cisco_ios"
  ansible_net_interfaces:
    GigabitEthernet0/0:
      description: "WAN Interface"
      ipv4: "192.168.1.1/24"
```

**Maps to Rego Policies:**
- `policies/network_devices/cisco/` - Cisco IOS CIS controls
- `policies/network_devices/juniper/` - Juniper CIS controls

### 6. Mobile Device Management

**Ansible Facts Available (via MDM integration):**
```yaml
mobile_device_facts:
  platform: "iOS"
  version: "15.1"
  device_id: "12345678-1234-1234-1234-123456789012"
  passcode_enabled: true
  encryption_enabled: true
  managed: true
```

**Maps to Rego Policies:**
- `policies/mobile_devices/ios/` - iOS CIS controls
- `policies/mobile_devices/android/` - Android CIS controls

## Usage Examples

### Basic CIS Compliance Check

```yaml
---
- name: Basic CIS Compliance Assessment
  hosts: all
  gather_facts: yes
  
  tasks:
    - name: Evaluate Linux CIS compliance
      uri:
        url: "http://opa-server:8181/v1/data/cis/linux/redhat/filesystem_compliant"
        method: POST
        body_format: json
        body:
          input:
            loaded_modules: "{{ ansible_facts['ansible_kernel_modules'] }}"
            mounts: "{{ ansible_facts['mounts'] }}"
            services: "{{ ansible_facts['services'] }}"
      register: compliance_result
```

### Multi-Platform Assessment

```yaml
---
- name: Comprehensive Multi-Platform CIS Assessment
  hosts: all
  gather_facts: yes
  
  tasks:
    # Assess different platforms based on detected technology
    - name: Check Linux compliance
      include_tasks: assess_linux.yml
      when: ansible_facts['os_family'] in ['RedHat', 'Debian']
      
    - name: Check Windows compliance  
      include_tasks: assess_windows.yml
      when: ansible_facts['os_family'] == 'Windows'
      
    - name: Check cloud provider compliance
      include_tasks: assess_cloud.yml
      when: ansible_facts['virtualization_type'] in ['xen', 'kvm'] # Cloud instances
      
    - name: Check server software compliance
      include_tasks: assess_servers.yml
      when: discovered_web_servers | length > 0
```

### Continuous Compliance Monitoring

```yaml
---
- name: Continuous CIS Compliance Monitoring
  hosts: all
  gather_facts: yes
  
  tasks:
    - name: Collect comprehensive system state
      set_fact:
        system_state:
          timestamp: "{{ ansible_date_time.iso8601 }}"
          os_facts: "{{ ansible_facts }}"
          package_facts: "{{ ansible_facts['packages'] }}"
          service_facts: "{{ ansible_facts['services'] }}"
          
    - name: Evaluate all applicable CIS policies
      uri:
        url: "http://opa-server:8181/v1/data/cis/comprehensive_assessment"
        method: POST
        body_format: json
        body:
          input: "{{ system_state }}"
      register: comprehensive_compliance
      
    - name: Store compliance results
      copy:
        content: "{{ comprehensive_compliance.json | to_nice_json }}"
        dest: "/var/log/cis-compliance/{{ inventory_hostname }}-{{ ansible_date_time.epoch }}.json"
        
    - name: Send alerts for non-compliance
      mail:
        to: "security@company.com"
        subject: "CIS Compliance Alert - {{ inventory_hostname }}"
        body: "Non-compliance detected. See attached report."
        attach: "/var/log/cis-compliance/{{ inventory_hostname }}-{{ ansible_date_time.epoch }}.json"
      when: not comprehensive_compliance.json.result
```

## Data Flow Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Target Host   │    │   Ansible       │    │   OPA Server    │
│                 │    │                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │   System    │◄├────┤ │gather_facts │ │    │ │    Rego     │ │
│ │   Facts     │ │    │ │             │ │    │ │  Policies   │ │
│ │             │ │    │ └─────────────┘ │    │ │             │ │
│ └─────────────┘ │    │        │        │    │ └─────────────┘ │
│                 │    │        ▼        │    │        ▲        │
│                 │    │ ┌─────────────┐ │    │        │        │
│                 │    │ │   JSON      │◄├────┼────────┘        │
│                 │    │ │ Structure   │ │    │                 │
│                 │    │ └─────────────┘ │    │ ┌─────────────┐ │
│                 │    │        │        │    │ │ Compliance  │ │
│                 │    │        ▼        │    │ │   Result    │ │
│                 │    │ ┌─────────────┐ │    │ │             │ │
│                 │    │ │ OPA Query   │─┼────┼►└─────────────┘ │
│                 │    │ │             │ │    │                 │
│                 │    │ └─────────────┘ │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Advanced Integration Patterns

### 1. Dynamic Policy Selection

```yaml
- name: Select appropriate CIS policies based on detected technology
  set_fact:
    applicable_policies: |
      {%- set policies = [] -%}
      {%- if ansible_facts['os_family'] == 'RedHat' -%}
        {%- set _ = policies.append('cis/linux/redhat') -%}
      {%- endif -%}
      {%- if 'docker' in ansible_facts['packages'] -%}
        {%- set _ = policies.append('cis/docker/host') -%}
      {%- endif -%}
      {%- if ansible_facts['virtualization_type'] == 'xen' -%}
        {%- set _ = policies.append('cis/aws/foundations') -%}
      {%- endif -%}
      {{ policies }}
```

### 2. Automated Remediation

```yaml
- name: Remediate CIS compliance issues
  block:
    - name: Check compliance status
      uri:
        url: "http://opa-server:8181/v1/data/cis/compliance_details"
        method: POST
        body: { "input": "{{ ansible_facts }}" }
      register: compliance_details
      
    - name: Apply remediation for failed controls
      include_tasks: "remediate_{{ item }}.yml"
      loop: "{{ compliance_details.json.result.failed_controls }}"
      when: compliance_details.json.result.failed_controls is defined
```

### 3. Custom Fact Collection

```yaml
- name: Collect additional CIS-specific facts
  setup:
    gather_subset:
      - "!all"
      - "!min"
      - network
      - hardware
      - virtual
      - mounts
      - services
    filter: "ansible_*"
    
- name: Augment with security-specific facts
  set_fact:
    security_facts:
      selinux_config: "{{ ansible_facts['selinux'] }}"
      firewall_rules: "{{ ansible_facts['iptables'] | default({}) }}"
      ssh_config: "{{ lookup('file', '/etc/ssh/sshd_config').split('\n') }}"
      loaded_modules: "{{ ansible_facts['kernel_modules'] }}"
      file_permissions:
        "/tmp": "{{ stat_results['/tmp'] }}"
        "/var": "{{ stat_results['/var'] }}"
```

## Benefits of This Integration

1. **Automated Discovery**: Ansible automatically detects installed software and configurations
2. **Standardized Data Format**: JSON structure maps directly to Rego policy inputs
3. **Scalable Assessment**: Single playbook can assess hundreds of hosts across multiple platforms
4. **Real-time Compliance**: Immediate feedback on compliance status
5. **Remediation Ready**: Failed controls can trigger automated remediation tasks
6. **Audit Trail**: Complete compliance history with timestamped results
7. **Multi-Platform**: Single framework supports all CIS benchmark technologies

## Getting Started

1. **Deploy OPA Server**: 
   ```bash
   ./start_opa.sh
   ```

2. **Run Comprehensive Assessment**:
   ```bash
   ansible-playbook examples/ansible_comprehensive_facts.yml -i inventory
   ```

3. **Review Results**: 
   ```bash
   open /tmp/comprehensive_cis_compliance_*.html
   ```

This integration provides a powerful, automated approach to CIS compliance validation across your entire technology stack using familiar Ansible workflows and comprehensive OPA policies.