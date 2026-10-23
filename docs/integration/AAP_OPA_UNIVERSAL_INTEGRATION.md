> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: HOST:8181x17.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Automation Platform + OPA Universal Integration
## Multi-Framework Compliance Validation

**Support for ALL compliance frameworks**: CIS, SOC2, PCI-DSS, ISO 27001, NIST, HIPAA, FedRAMP, NERC-CIP, and custom policies

---

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Universal Design Principles](#universal-design-principles)
3. [Quick Start](#quick-start)
4. [Multi-Framework Setup](#multi-framework-setup)
5. [Usage Examples](#usage-examples)
6. [Framework-Specific Examples](#framework-specific-examples)

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│              ANSIBLE AUTOMATION PLATFORM (AAP)                     │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Playbooks: Gather facts from ANY managed infrastructure     │ │
│  │  • Linux (RHEL, Ubuntu, Debian, SLES)                        │ │
│  │  • Windows (2016, 2019, 2022)                                │ │
│  │  • Network Devices (Cisco, Juniper, Arista)                  │ │
│  │  • Cloud (AWS, Azure, GCP)                                   │ │
│  │  • Containers (Docker, Kubernetes)                           │ │
│  │  • Applications (Apache, MySQL, MongoDB)                     │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                              │                                     │
│                              ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │       UNIVERSAL CALLBACK PLUGIN (opa_compliance.py)          │ │
│  │  • Auto-detects fact type (OS, cloud, app, network)         │ │
│  │  • Routes to appropriate OPA policies                        │ │
│  │  • Handles multiple compliance frameworks                    │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────┬───────────────────────────────────┘
                                 │
                    Facts JSON (Multi-Source)
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                   OPEN POLICY AGENT (OPA) SERVER                   │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                  UNIVERSAL POLICY STRUCTURE                   │ │
│  │                                                               │ │
│  │  policies/                                                    │ │
│  │  ├── cis/                     # CIS Benchmarks                │ │
│  │  │   ├── linux/rhel9/                                        │ │
│  │  │   ├── linux/ubuntu22/                                     │ │
│  │  │   ├── windows/server2022/                                 │ │
│  │  │   ├── docker/                                             │ │
│  │  │   ├── kubernetes/                                         │ │
│  │  │   └── aws_foundations/                                    │ │
│  │  ├── soc2/                    # SOC2 Controls                 │ │
│  │  │   ├── cc_common_criteria/                                 │ │
│  │  │   ├── access_controls/                                    │ │
│  │  │   └── monitoring_logging/                                 │ │
│  │  ├── pci_dss/                 # PCI-DSS Requirements         │ │
│  │  │   ├── requirement_1_firewall/                             │ │
│  │  │   ├── requirement_2_config/                               │ │
│  │  │   └── requirement_8_access/                               │ │
│  │  ├── iso27001/                # ISO 27001 Controls           │ │
│  │  │   ├── a5_access_control/                                  │ │
│  │  │   ├── a8_asset_management/                                │ │
│  │  │   └── a12_operations_security/                            │ │
│  │  ├── nist/                    # NIST 800-53                  │ │
│  │  │   ├── access_control/                                     │ │
│  │  │   ├── audit_accountability/                               │ │
│  │  │   └── system_communications/                              │ │
│  │  ├── hipaa/                   # HIPAA Safeguards             │ │
│  │  ├── fedramp/                 # FedRAMP Controls             │ │
│  │  ├── nerc_cip/                # NERC-CIP Standards           │ │
│  │  └── custom/                  # Custom Policies              │ │
│  │      └── company_policies/                                   │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                              │                                     │
│                              ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │             DYNAMIC POLICY EVALUATION                         │ │
│  │  • Automatically applies relevant frameworks                  │ │
│  │  • Supports multiple simultaneous frameworks                  │ │
│  │  • Cross-framework mapping and correlation                    │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────┬───────────────────────────────────┘
                                 │
                    Multi-Framework Report
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                      UNIFIED REPORTING ENGINE                      │
│  • Single dashboard for all frameworks                             │
│  • Cross-framework compliance status                               │
│  • Control mapping (CIS ↔ SOC2 ↔ PCI-DSS ↔ ISO27001)            │
│  • Evidence collection for audits                                  │
└────────────────────────────────────────────────────────────────────┘
```

---

## Universal Design Principles

### 1. **Framework-Agnostic Fact Collection**
Facts are collected in a standardized format that works with any compliance framework:

```yaml
ansible_facts:
  # Universal system information
  system_info:
    hostname: "server-01"
    os_family: "RedHat"
    os_version: "9.2"
    kernel: "5.14.0"

  # Universal security controls
  access_controls:
    users: [...]
    groups: [...]
    sudo_config: {...}

  # Universal network configuration
  network_config:
    interfaces: [...]
    firewall: {...}
    routing: {...}

  # Universal logging
  logging_config:
    syslog: {...}
    audit: {...}

  # Universal services
  services: {...}

  # Universal file permissions
  file_permissions: {...}
```

### 2. **Dynamic Framework Selection**
The callback plugin automatically determines which frameworks to apply:

```python
def determine_applicable_frameworks(facts):
    """Auto-detect which compliance frameworks apply"""
    frameworks = []

    # Operating system frameworks
    if facts.get('os_family') == 'RedHat':
        frameworks.append('cis/linux/rhel')
    if facts.get('os_family') == 'Windows':
        frameworks.append('cis/windows/server2022')

    # Cloud provider frameworks
    if 'ec2_instance_id' in facts:
        frameworks.append('cis/aws_foundations')
    if 'azure_vm_id' in facts:
        frameworks.append('cis/azure_foundations')

    # Application frameworks
    if 'docker' in facts.get('services', {}):
        frameworks.append('cis/docker')
    if 'mysqld' in facts.get('services', {}):
        frameworks.append('cis/mysql')

    # Industry regulations (configured per host/inventory)
    frameworks.extend(facts.get('required_frameworks', []))

    return frameworks
```

### 3. **Multi-Framework Evaluation**
Single fact collection validates against ALL applicable frameworks:

```json
{
  "host": "webserver-01",
  "compliance_results": {
    "cis_rhel9": {
      "compliant": false,
      "violations": 15,
      "risk_level": "high"
    },
    "soc2": {
      "compliant": true,
      "violations": 0,
      "controls_met": 47
    },
    "pci_dss": {
      "compliant": false,
      "violations": 3,
      "requirements_failed": ["1.2.3", "2.2.2"]
    },
    "iso27001": {
      "compliant": true,
      "violations": 0,
      "controls_met": 23
    }
  }
}
```

---

## Quick Start

### 1. Install Universal OPA Server

```bash
# Install OPA
sudo curl -L -o /usr/local/bin/opa \
  https://github.com/open-policy-agent/opa/releases/download/v1.10.0/opa_linux_amd64
sudo chmod 755 /usr/local/bin/opa

# Create universal policy structure
sudo mkdir -p /etc/opa/policies/{cis,soc2,pci_dss,iso27001,nist,hipaa,custom}

# Deploy ALL your compliance policies
sudo cp -r policies/* /etc/opa/policies/
```

### 2. Deploy Universal Callback Plugin

Create `/usr/share/ansible/plugins/callback/opa_universal_compliance.py`:

```python
#!/usr/bin/env python3
"""
Universal OPA Compliance Callback Plugin
Supports multiple compliance frameworks simultaneously
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json
import requests
from ansible.plugins.callback import CallbackBase
from datetime import datetime

DOCUMENTATION = '''
    callback: opa_universal_compliance
    type: notification
    short_description: Universal multi-framework compliance validation
    description:
        - Validates against multiple compliance frameworks
        - Automatically detects applicable frameworks
        - Supports CIS, SOC2, PCI-DSS, ISO 27001, NIST, HIPAA, etc.
    requirements:
        - requests library
    options:
      opa_server_url:
        description: OPA server URL
        default: 'http://localhost:8181'
        env:
          - name: OPA_SERVER_URL
      required_frameworks:
        description: Comma-separated list of required frameworks
        default: 'auto'
        env:
          - name: COMPLIANCE_FRAMEWORKS
'''

class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'opa_universal_compliance'
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self):
        super(CallbackModule, self).__init__()
        self.opa_server_url = 'http://localhost:8181'
        self.required_frameworks = []

    def set_options(self, task_keys=None, var_options=None, direct=None):
        super(CallbackModule, self).set_options(
            task_keys=task_keys,
            var_options=var_options,
            direct=direct
        )
        self.opa_server_url = self.get_option('opa_server_url')

        frameworks = self.get_option('required_frameworks')
        if frameworks and frameworks != 'auto':
            self.required_frameworks = [f.strip() for f in frameworks.split(',')]

    def v2_runner_on_ok(self, result):
        """Called when a task succeeds"""
        if result._task.action in ['setup', 'gather_facts']:
            hostname = result._host.get_name()
            facts = result._result.get('ansible_facts', {})

            # Determine applicable frameworks
            frameworks = self._determine_frameworks(hostname, facts)

            if frameworks:
                self._validate_all_frameworks(hostname, facts, frameworks)

    def _determine_frameworks(self, hostname, facts):
        """Auto-detect which frameworks apply to this host"""
        frameworks = set()

        # If frameworks explicitly configured, use those
        if self.required_frameworks:
            return self.required_frameworks

        # Auto-detect from host variables
        host_frameworks = facts.get('compliance_frameworks', [])
        frameworks.update(host_frameworks)

        # Auto-detect from OS
        os_family = facts.get('ansible_os_family', '')
        if 'RedHat' in os_family:
            frameworks.add('cis/linux/rhel')
        elif 'Debian' in os_family:
            frameworks.add('cis/linux/ubuntu')
        elif 'Windows' in os_family:
            frameworks.add('cis/windows/server')

        # Auto-detect from cloud provider
        if facts.get('ansible_ec2_instance_id'):
            frameworks.add('cis/aws_foundations')
        if facts.get('azure_vm_id'):
            frameworks.add('cis/azure_foundations')

        # Auto-detect from services
        services = facts.get('ansible_facts', {}).get('services', {})
        if 'docker' in services or 'dockerd' in services:
            frameworks.add('cis/docker')
        if 'mysqld' in services:
            frameworks.add('cis/mysql')

        return list(frameworks)

    def _validate_all_frameworks(self, hostname, facts, frameworks):
        """Validate against all applicable frameworks"""
        facts['hostname'] = hostname
        facts['collection_timestamp'] = datetime.now().isoformat()

        results = {}
        total_violations = 0

        for framework in frameworks:
            framework_result = self._validate_framework(
                hostname, facts, framework
            )
            results[framework] = framework_result
            total_violations += framework_result.get('violations', 0)

        # Display summary
        self._display.banner(f"[COMPLIANCE] {hostname}")

        for framework, result in results.items():
            status = "✓ COMPLIANT" if result.get('compliant') else "✗ NON-COMPLIANT"
            color = 'green' if result.get('compliant') else 'red'
            violations = result.get('violations', 0)

            self._display.display(
                f"  {framework}: {status} ({violations} violations)",
                color=color
            )

        # Overall status
        overall_compliant = all(r.get('compliant') for r in results.values())
        overall_status = "✓ OVERALL COMPLIANT" if overall_compliant else "✗ OVERALL NON-COMPLIANT"
        overall_color = 'green' if overall_compliant else 'red'

        self._display.display(
            f"\n  {overall_status} - {len(frameworks)} frameworks, {total_violations} total violations\n",
            color=overall_color
        )

    def _validate_framework(self, hostname, facts, framework):
        """Validate against a specific framework"""
        try:
            # Query OPA for this framework
            url = f"{self.opa_server_url}/v1/data/{framework.replace('/', '.')}/report"

            response = requests.post(
                url,
                json={'input': facts},
                timeout=10
            )

            if response.status_code == 200:
                result = response.json().get('result', {})
                return {
                    'compliant': result.get('compliant', False),
                    'violations': len(result.get('violations', [])),
                    'risk_level': result.get('risk_level', 'unknown'),
                    'details': result
                }
            else:
                self._display.warning(
                    f"[OPA] Failed to validate {framework}: HTTP {response.status_code}"
                )
                return {'compliant': None, 'violations': 0, 'error': True}

        except Exception as e:
            self._display.warning(f"[OPA] Error validating {framework}: {e}")
            return {'compliant': None, 'violations': 0, 'error': True}
```

### 3. Create Universal Compliance Playbook

```yaml
---
- name: Universal Multi-Framework Compliance Check
  hosts: all
  gather_facts: false
  become: true

  vars:
    opa_server_url: "{{ lookup('env', 'OPA_SERVER_URL') | default('http://localhost:8181', true) }}"
    # Frameworks to validate (auto-detected if not specified)
    compliance_frameworks: "{{ hostvars[inventory_hostname].compliance_frameworks | default('auto') }}"

  tasks:
    - name: Gather comprehensive facts
      setup:
        gather_subset:
          - all
          - network
          - hardware
          - virtual
          - mounts
          - services

    - name: Collect additional compliance facts
      include_role:
        name: "{{ item }}"
      loop:
        - collect_security_facts
        - collect_audit_facts
        - collect_network_facts
      when: item in ansible_local.roles | default([])

    # Callback plugin automatically validates against all frameworks

    - name: Generate multi-framework report
      delegate_to: localhost
      run_once: true
      block:
        - name: Query OPA for all frameworks
          uri:
            url: "{{ opa_server_url }}/v1/data/universal/multi_framework_report"
            method: POST
            body_format: json
            body:
              input:
                hostname: "{{ inventory_hostname }}"
                facts: "{{ hostvars[inventory_hostname] }}"
                frameworks: "{{ compliance_frameworks }}"
          register: compliance_report

        - name: Save report
          copy:
            content: "{{ compliance_report.json | to_nice_json }}"
            dest: "/tmp/compliance_{{ inventory_hostname }}_{{ ansible_date_time.epoch }}.json"

        - name: Display summary
          debug:
            msg: "{{ compliance_report.json.result.summary }}"
```

---

## Multi-Framework Setup

### Directory Structure

```
/etc/opa/policies/
├── universal/
│   └── multi_framework.rego         # Universal evaluation engine
│
├── cis/
│   ├── linux/
│   │   ├── rhel9/
│   │   │   ├── filesystem.rego
│   │   │   ├── services.rego
│   │   │   └── network.rego
│   │   ├── ubuntu22/
│   │   └── debian12/
│   ├── windows/
│   │   ├── server2022/
│   │   └── server2019/
│   ├── docker/
│   ├── kubernetes/
│   └── aws_foundations/
│
├── soc2/
│   ├── cc_common_criteria/
│   ├── access_controls/
│   └── monitoring_logging/
│
├── pci_dss/
│   ├── requirement_1_firewall/
│   ├── requirement_2_config/
│   └── requirement_8_access/
│
├── iso27001/
│   ├── a5_access_control/
│   ├── a8_asset_management/
│   └── a12_operations_security/
│
├── nist/
│   ├── ac_access_control/
│   ├── au_audit_accountability/
│   └── sc_system_communications/
│
├── hipaa/
│   ├── administrative_safeguards/
│   ├── physical_safeguards/
│   └── technical_safeguards/
│
└── custom/
    └── company_policies/
        ├── password_policy.rego
        ├── patching_policy.rego
        └── encryption_policy.rego
```

### Universal Multi-Framework Policy

Create `/etc/opa/policies/universal/multi_framework.rego`:

```rego
package universal

import rego.v1

# Evaluate all applicable frameworks
multi_framework_report := {
    "host": input.hostname,
    "timestamp": time.now_ns(),
    "frameworks": framework_results,
    "summary": summary,
}

# Determine which frameworks apply
applicable_frameworks contains framework if {
    framework := input.frameworks[_]
}

applicable_frameworks contains "cis/linux/rhel" if {
    contains(input.facts.ansible_distribution, "RedHat")
}

applicable_frameworks contains "cis/aws_foundations" if {
    input.facts.ansible_ec2_instance_id
}

# Evaluate each framework
framework_results := {framework: evaluate_framework(framework) |
    some framework in applicable_frameworks
}

# Helper to evaluate a single framework
evaluate_framework(framework) := result if {
    # Use data.<framework_path>.report
    framework_path := replace(framework, "/", ".")
    framework_data := data[split(framework_path, ".")[0]]

    result := {
        "compliant": framework_data.compliant,
        "violations": framework_data.violations,
        "risk_level": framework_data.risk_level,
    }
}

# Generate summary
summary := {
    "total_frameworks": count(applicable_frameworks),
    "compliant_frameworks": count([f | framework_results[f].compliant]),
    "total_violations": sum([framework_results[f].violations | f := applicable_frameworks[_]]),
    "overall_compliant": count([f | not framework_results[f].compliant]) == 0,
    "highest_risk_level": max_risk_level,
}

# Determine highest risk level across all frameworks
max_risk_level := "critical" if {
    some result in framework_results
    result.risk_level == "critical"
} else := "high" if {
    some result in framework_results
    result.risk_level == "high"
} else := "medium" if {
    some result in framework_results
    result.risk_level == "medium"
} else := "low"
```

---

## Usage Examples

### Example 1: Validate Against Multiple Frameworks

```bash
# Specify which frameworks to validate
ansible-playbook compliance_check.yml \
  -e "compliance_frameworks=['cis/linux/rhel','soc2','pci_dss']"

# Auto-detect frameworks
ansible-playbook compliance_check.yml \
  -e "compliance_frameworks=auto"

# Set via inventory
[webservers]
web01 compliance_frameworks=['cis/linux/rhel','pci_dss']
web02 compliance_frameworks=['cis/linux/rhel','soc2']
```

### Example 2: Cross-Framework Control Mapping

```bash
# See which CIS controls map to SOC2
curl -X POST http://localhost:8181/v1/data/mappings/cis_to_soc2 \
  -d '{"input": {"cis_control": "1.1.1"}}'

# Response:
{
  "result": {
    "soc2_controls": ["CC6.1", "CC6.6"],
    "description": "Access control and configuration management"
  }
}
```

### Example 3: Industry-Specific Validation

```yaml
# Healthcare organization (HIPAA + CIS)
- hosts: healthcare_servers
  vars:
    compliance_frameworks:
      - hipaa/technical_safeguards
      - cis/linux/rhel

# Financial services (PCI-DSS + SOC2 + CIS)
- hosts: payment_servers
  vars:
    compliance_frameworks:
      - pci_dss/all_requirements
      - soc2/all_criteria
      - cis/linux/rhel

# Government/Defense (NIST + FedRAMP)
- hosts: gov_servers
  vars:
    compliance_frameworks:
      - nist/800_53
      - fedramp/moderate
```

---

## Framework-Specific Examples

### CIS Benchmarks
```bash
# Linux
curl -X POST http://localhost:8181/v1/data/cis/linux/rhel9/report -d @facts.json

# Windows
curl -X POST http://localhost:8181/v1/data/cis/windows/server2022/report -d @facts.json

# Docker
curl -X POST http://localhost:8181/v1/data/cis/docker/report -d @facts.json

# Kubernetes
curl -X POST http://localhost:8181/v1/data/cis/kubernetes/report -d @facts.json

# AWS
curl -X POST http://localhost:8181/v1/data/cis/aws_foundations/report -d @facts.json
```

### SOC 2
```bash
# All SOC2 criteria
curl -X POST http://localhost:8181/v1/data/soc2/report -d @facts.json

# Specific criteria
curl -X POST http://localhost:8181/v1/data/soc2/cc_common_criteria/report -d @facts.json
```

### PCI-DSS
```bash
# All requirements
curl -X POST http://localhost:8181/v1/data/pci_dss/report -d @facts.json

# Specific requirement
curl -X POST http://localhost:8181/v1/data/pci_dss/requirement_1_firewall/report -d @facts.json
```

### ISO 27001
```bash
# All controls
curl -X POST http://localhost:8181/v1/data/iso27001/report -d @facts.json

# Specific annex
curl -X POST http://localhost:8181/v1/data/iso27001/a5_access_control/report -d @facts.json
```

### NIST 800-53
```bash
# All control families
curl -X POST http://localhost:8181/v1/data/nist/report -d @facts.json

# Specific family
curl -X POST http://localhost:8181/v1/data/nist/ac_access_control/report -d @facts.json
```

---

## Next Steps

1. ✅ Deploy universal OPA server with all framework policies
2. ✅ Install universal callback plugin
3. ✅ Configure hosts with required frameworks
4. ✅ Create universal compliance playbook
5. ✅ Test with multiple frameworks
6. ⬜ Build cross-framework dashboards
7. ⬜ Implement control mapping
8. ⬜ Create framework-specific remediation playbooks

---

**The universal integration allows you to**:
- ✅ Validate against **multiple frameworks simultaneously**
- ✅ **Auto-detect** applicable frameworks based on infrastructure
- ✅ **Centralize** compliance management in one platform
- ✅ **Correlate** controls across frameworks
- ✅ **Scale** to any compliance requirement

Your organization can now have **one integration that handles ALL compliance needs**!
