> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: HOST:8181x15, AAP-2.5/2.6x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Automation Platform (AAP) + OPA Integration Guide
## CIS RHEL 9 Compliance Validation

This guide explains how to integrate Ansible Automation Platform with Open Policy Agent (OPA) for automated CIS RHEL 9 compliance validation.

---

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Detailed Setup](#detailed-setup)
5. [Usage Examples](#usage-examples)
6. [Integration Patterns](#integration-patterns)
7. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    ANSIBLE AUTOMATION PLATFORM (AAP)                      │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │  Job Templates  │  Playbooks  │  Inventories  │  Credentials        │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                   │                                        │
│                                   ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │              CALLBACK PLUGINS (opa_compliance.py)                    │ │
│  │  • Intercepts playbook execution                                     │ │
│  │  • Collects facts from managed nodes                                 │ │
│  │  • Sends facts to OPA for validation                                 │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────┬───────────────────────────────────┘
                                       │
                         Facts JSON (CIS Controls Data)
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                   OPEN POLICY AGENT (OPA) SERVER                         │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                   CIS RHEL 9 Rego Policies                          │ │
│  │  • Section 1.1: Filesystem Configuration                             │ │
│  │  • Section 2.x: Service Configuration                                │ │
│  │  • Section 3.x: Network Configuration                                │ │
│  │  • Section 4.2: Logging Configuration                                │ │
│  │  • Section 6.1: File Permissions                                     │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                   │                                        │
│                                   ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                    POLICY EVALUATION ENGINE                          │ │
│  │  Input: System Facts → Output: Compliance Report + Violations       │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────┬───────────────────────────────────┘
                                       │
                         Compliance Report JSON
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         REPORTING & ACTIONS                              │
│  • Generate compliance reports                                           │
│  • Store results in database                                             │
│  • Trigger remediation playbooks for violations                          │
│  • Send alerts to security team                                          │
│  • Create ServiceNow/Jira tickets                                        │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### Software Requirements

- **Ansible Automation Platform 2.6**
- **Open Policy Agent 1.10.0**
- **Python 3.11+**
- **PostgreSQL 15+** (for facts storage)
- **RHEL 8/9** (for AAP controller)

### Access Requirements

- SSH access to managed RHEL 9 nodes
- AAP admin credentials
- Network connectivity between AAP and OPA (port 8181)

---

## Quick Start

### 1. Install OPA on AAP Controller

```bash
# Download and install OPA
cd /usr/local/bin
sudo curl -L -o opa https://github.com/open-policy-agent/opa/releases/download/v1.10.0/opa_linux_amd64
sudo chmod 755 opa

# Verify installation
opa version
```

### 2. Deploy CIS RHEL 9 Policies

```bash
# Create policies directory
sudo mkdir -p /etc/opa/policies/cis_rhel9

# Copy CIS RHEL 9 policies
sudo cp -r policies/cis_rhel9/* /etc/opa/policies/cis_rhel9/
```

### 3. Start OPA Server

```bash
# Start OPA as a server
opa run --server \
  --addr 0.0.0.0:8181 \
  --log-level info \
  /etc/opa/policies
```

Or create a systemd service:

```bash
sudo cat > /etc/systemd/system/opa.service <<EOF
[Unit]
Description=Open Policy Agent
After=network.target

[Service]
Type=simple
User=opa
ExecStart=/usr/local/bin/opa run --server --addr 0.0.0.0:8181 /etc/opa/policies
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now opa
```

### 4. Test OPA Server

```bash
# Test OPA health
curl http://localhost:8181/health

# Test policy evaluation
curl -X POST http://localhost:8181/v1/data/cis_rhel9/filesystem/violations \
  -H "Content-Type: application/json" \
  -d @test_data/mock_facts/webserver_noncompliant.json
```

---

## Detailed Setup

### Step 1: Create Ansible Callback Plugin

Create `/usr/share/ansible/plugins/callback/opa_compliance.py`:

```python
#!/usr/bin/env python3
"""
OPA Compliance Callback Plugin for Ansible
Validates CIS RHEL 9 compliance during playbook execution
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json
import requests
from ansible.plugins.callback import CallbackBase
from datetime import datetime

DOCUMENTATION = '''
    callback: opa_compliance
    type: notification
    short_description: Send facts to OPA for CIS RHEL 9 compliance validation
    description:
        - This callback plugin sends gathered facts to OPA for compliance validation
        - Validates against CIS RHEL 9 Benchmark policies
        - Reports compliance status and violations
    requirements:
        - requests library
    options:
      opa_server_url:
        description: OPA server URL
        default: 'http://localhost:8181'
        env:
          - name: OPA_SERVER_URL
        ini:
          - section: callback_opa_compliance
            key: server_url
      fail_on_violations:
        description: Fail playbook if violations are found
        default: False
        type: bool
        env:
          - name: OPA_FAIL_ON_VIOLATIONS
        ini:
          - section: callback_opa_compliance
            key: fail_on_violations
'''

class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'opa_compliance'
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self):
        super(CallbackModule, self).__init__()
        self.opa_server_url = 'http://localhost:8181'
        self.fail_on_violations = False
        self.host_facts = {}

    def set_options(self, task_keys=None, var_options=None, direct=None):
        super(CallbackModule, self).set_options(task_keys=task_keys,
                                                 var_options=var_options,
                                                 direct=direct)

        self.opa_server_url = self.get_option('opa_server_url')
        self.fail_on_violations = self.get_option('fail_on_violations')

    def v2_runner_on_ok(self, result):
        """Called when a task succeeds"""
        # Check if this task collected facts
        if result._task.action in ['setup', 'gather_facts']:
            hostname = result._host.get_name()
            facts = result._result.get('ansible_facts', {})

            # Store facts for this host
            self.host_facts[hostname] = facts

            # If this looks like CIS fact collection, validate with OPA
            if self._is_cis_fact_collection(facts):
                self._validate_with_opa(hostname, facts)

    def _is_cis_fact_collection(self, facts):
        """Check if facts contain CIS-specific data"""
        cis_indicators = [
            'disabled_filesystem_modules',
            'mount_options',
            'critical_files',
            'sysctl_parameters',
            'rsyslog',
            'journald'
        ]
        return any(key in facts for key in cis_indicators)

    def _validate_with_opa(self, hostname, facts):
        """Send facts to OPA for validation"""
        try:
            # Add metadata
            facts['hostname'] = hostname
            facts['collection_timestamp'] = datetime.now().isoformat()

            # Validate each section
            sections = [
                'filesystem',
                'logging',
                'file_permissions',
                'services',
                'network'
            ]

            all_violations = []

            for section in sections:
                url = f"{self.opa_server_url}/v1/data/cis_rhel9/{section}/violations"
                response = requests.post(url, json={'input': facts}, timeout=10)

                if response.status_code == 200:
                    result = response.json()
                    violations = result.get('result', [])

                    if violations:
                        all_violations.extend(violations)
                        self._display.warning(
                            f"[OPA] {hostname} - {section}: {len(violations)} violations found"
                        )
                        for violation in violations:
                            self._display.warning(f"  - {violation}")

            # Display summary
            if all_violations:
                self._display.error(
                    f"[OPA] {hostname}: NON-COMPLIANT - {len(all_violations)} total violations"
                )

                if self.fail_on_violations:
                    raise Exception(f"Compliance validation failed for {hostname}")
            else:
                self._display.display(
                    f"[OPA] {hostname}: COMPLIANT - No violations found",
                    color='green'
                )

        except requests.exceptions.RequestException as e:
            self._display.warning(f"[OPA] Failed to validate {hostname}: {e}")
        except Exception as e:
            self._display.error(f"[OPA] Error during validation: {e}")
            if self.fail_on_violations:
                raise

    def playbook_on_stats(self, stats):
        """Called when playbook completes"""
        self._display.banner("[OPA COMPLIANCE VALIDATION COMPLETE]")
```

### Step 2: Configure AAP to Use Callback Plugin

In AAP Controller:

1. **Go to Settings → Jobs**
2. **Enable the callback plugin**:
   - Add `opa_compliance` to `ANSIBLE_CALLBACK_WHITELIST`

3. **Set environment variables** (in Job Template → Extra Variables):
   ```yaml
   OPA_SERVER_URL: "http://localhost:8181"
   OPA_FAIL_ON_VIOLATIONS: false
   ```

### Step 3: Create CIS Fact Collection Playbook

Create `playbooks/cis_rhel9_compliance_check.yml`:

```yaml
---
- name: CIS RHEL 9 Compliance Validation
  hosts: rhel9_servers
  gather_facts: false
  become: true

  vars:
    opa_server_url: "{{ lookup('env', 'OPA_SERVER_URL') | default('http://localhost:8181', true) }}"

  tasks:
    # Include all CIS fact collection roles
    - name: Collect Section 1.1 - Filesystem Configuration
      include_role:
        name: cis_rhel9_section_1_filesystem
      tags: filesystem

    - name: Collect Section 4.2 - Logging Configuration
      include_role:
        name: cis_rhel9_section_4_logging
      tags: logging

    - name: Collect Section 6.1 - File Permissions
      include_role:
        name: cis_rhel9_section_6_file_permissions
      tags: file_permissions

    - name: Collect Section 2.x - Service Configuration
      include_role:
        name: cis_rhel9_section_2_services
      tags: services

    - name: Collect Section 3.x - Network Configuration
      include_role:
        name: cis_rhel9_section_3_network
      tags: network

    # The callback plugin will automatically validate facts with OPA

    - name: Generate compliance report
      delegate_to: localhost
      run_once: true
      block:
        - name: Query OPA for complete compliance report
          uri:
            url: "{{ opa_server_url }}/v1/data/cis_rhel9/report"
            method: POST
            body_format: json
            body:
              input: "{{ hostvars[inventory_hostname] }}"
            return_content: yes
          register: compliance_report

        - name: Save compliance report
          copy:
            content: "{{ compliance_report.json | to_nice_json }}"
            dest: "/tmp/cis_compliance_{{ inventory_hostname }}_{{ ansible_date_time.epoch }}.json"

        - name: Display compliance summary
          debug:
            msg:
              - "========================================="
              - "CIS RHEL 9 COMPLIANCE REPORT"
              - "========================================="
              - "Host: {{ inventory_hostname }}"
              - "Status: {{ 'COMPLIANT' if compliance_report.json.result.compliance.overall_compliant else 'NON-COMPLIANT' }}"
              - "Compliant Sections: {{ compliance_report.json.result.compliance.compliant_sections }}/5"
              - "Total Violations: {{ compliance_report.json.result.violations.total_count }}"
              - "Risk Level: {{ compliance_report.json.result.compliance.overall_risk_level | upper }}"
              - "========================================="
```

### Step 4: Create AAP Job Template

In AAP Controller:

1. **Create new Job Template**:
   - Name: `CIS RHEL 9 Compliance Check`
   - Job Type: `Run`
   - Inventory: Your RHEL 9 inventory
   - Project: Your playbook project
   - Playbook: `cis_rhel9_compliance_check.yml`
   - Credentials: Your SSH credentials
   - Extra Variables:
     ```yaml
     OPA_SERVER_URL: http://localhost:8181
     OPA_FAIL_ON_VIOLATIONS: false
     ```

2. **Enable callback plugin** in Job Template settings

3. **Save and Launch**

---

## Usage Examples

### Example 1: Scheduled Compliance Checks

Create a **Workflow** in AAP:

```
┌─────────────────────────┐
│ Collect Facts from      │
│ All RHEL 9 Servers      │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Validate with OPA       │
│ (automatic via callback)│
└───────────┬─────────────┘
            │
        ┌───┴───┐
        │       │
        ▼       ▼
   [PASS]   [FAIL]
        │       │
        │       ▼
        │   ┌─────────────────────┐
        │   │ Trigger Remediation │
        │   │ Playbook            │
        │   └─────────────────────┘
        │       │
        └───────┴───────────┐
                            ▼
                ┌───────────────────────┐
                │ Generate Report       │
                │ Send to Security Team │
                └───────────────────────┘
```

Schedule this workflow to run:
- Daily at 2 AM
- After any infrastructure changes
- Before audits

### Example 2: Continuous Compliance (Git Integration)

```bash
# Install pre-commit hook
cat > .git/hooks/pre-commit <<'EOF'
#!/bin/bash
# Validate playbook changes before commit

# Run compliance check on test inventory
ansible-playbook playbooks/cis_rhel9_compliance_check.yml \
  -i inventories/test \
  --check \
  -e "OPA_FAIL_ON_VIOLATIONS=true"

if [ $? -ne 0 ]; then
  echo "❌ Compliance validation failed. Commit rejected."
  exit 1
fi

echo "✅ Compliance validation passed."
exit 0
EOF

chmod +x .git/hooks/pre-commit
```

### Example 3: Manual Compliance Check via CLI

```bash
# Run compliance check on specific host
ansible-playbook playbooks/cis_rhel9_compliance_check.yml \
  -i inventories/production \
  -l webserver-01.example.com \
  -e "OPA_SERVER_URL=http://opa-server:8181"

# Run with verbose output
ansible-playbook playbooks/cis_rhel9_compliance_check.yml \
  -i inventories/production \
  -vv

# Run and fail on violations
ansible-playbook playbooks/cis_rhel9_compliance_check.yml \
  -i inventories/production \
  -e "OPA_FAIL_ON_VIOLATIONS=true"
```

### Example 4: Query OPA Directly

```bash
# Get violations for a specific section
curl -X POST http://localhost:8181/v1/data/cis_rhel9/filesystem/violations \
  -H "Content-Type: application/json" \
  -d @/tmp/server_facts.json | jq '.result[]'

# Get complete compliance report
curl -X POST http://localhost:8181/v1/data/cis_rhel9/report \
  -H "Content-Type: application/json" \
  -d @/tmp/server_facts.json | jq '.result'

# Check if system is compliant
curl -X POST http://localhost:8181/v1/data/cis_rhel9/compliant \
  -H "Content-Type: application/json" \
  -d @/tmp/server_facts.json | jq '.result'
```

---

## Integration Patterns

### Pattern 1: Automated Remediation

```yaml
---
- name: CIS Compliance with Auto-Remediation
  hosts: rhel9_servers
  gather_facts: false
  become: true

  tasks:
    - name: Check compliance
      include_tasks: cis_compliance_check.yml
      register: compliance_result

    - name: Remediate violations
      when: not compliance_result.compliant
      block:
        - name: Fix filesystem violations
          include_role:
            name: cis_rhel9_remediate_filesystem
          when: "'filesystem' in compliance_result.failed_sections"

        - name: Fix service violations
          include_role:
            name: cis_rhel9_remediate_services
          when: "'services' in compliance_result.failed_sections"

        # Re-check after remediation
        - name: Verify remediation
          include_tasks: cis_compliance_check.yml
```

### Pattern 2: ServiceNow Integration

```yaml
- name: Create ServiceNow ticket for violations
  when: not compliant
  servicenow.itsm.incident:
    instance:
      host: "{{ servicenow_instance }}"
      username: "{{ servicenow_user }}"
      password: "{{ servicenow_password }}"
    state: new
    short_description: "CIS RHEL 9 Compliance Violations - {{ inventory_hostname }}"
    description: |
      CIS RHEL 9 compliance violations detected:

      Host: {{ inventory_hostname }}
      Total Violations: {{ total_violations }}
      Risk Level: {{ risk_level }}

      Violations:
      {{ violations | to_nice_yaml }}
    urgency: "{{ 'high' if risk_level == 'critical' else 'medium' }}"
    impact: "{{ 'high' if risk_level == 'critical' else 'medium' }}"
```

### Pattern 3: Facts Database Storage

```yaml
- name: Store compliance results in database
  delegate_to: localhost
  postgresql_query:
    db: compliance_db
    query: |
      INSERT INTO cis_compliance_results
        (hostname, timestamp, compliant, violations, risk_level, report_json)
      VALUES
        (%s, %s, %s, %s, %s, %s)
    positional_args:
      - "{{ inventory_hostname }}"
      - "{{ ansible_date_time.iso8601 }}"
      - "{{ compliant }}"
      - "{{ total_violations }}"
      - "{{ risk_level }}"
      - "{{ compliance_report | to_json }}"
```

---

## Troubleshooting

### Issue: Callback Plugin Not Loading

**Symptom**: No OPA validation output during playbook execution

**Solution**:
```bash
# Check if plugin is in correct location
ls -la /usr/share/ansible/plugins/callback/opa_compliance.py

# Verify plugin is whitelisted
ansible-config dump | grep CALLBACK_WHITELIST

# Enable in ansible.cfg
[defaults]
callback_whitelist = opa_compliance

# Or set environment variable
export ANSIBLE_CALLBACK_WHITELIST=opa_compliance
```

### Issue: OPA Connection Refused

**Symptom**: `Connection refused` error when validating

**Solution**:
```bash
# Check OPA is running
systemctl status opa

# Test OPA connectivity
curl http://localhost:8181/health

# Check firewall
sudo firewall-cmd --list-ports | grep 8181

# Allow OPA port
sudo firewall-cmd --permanent --add-port=8181/tcp
sudo firewall-cmd --reload
```

### Issue: Policy Not Found

**Symptom**: `undefined` result from OPA

**Solution**:
```bash
# List loaded policies
curl http://localhost:8181/v1/policies

# Reload policies
sudo systemctl restart opa

# Verify policy syntax
opa test policies/cis_rhel9/
```

### Issue: Facts Not Matching Policy Structure

**Symptom**: OPA returns empty/undefined violations

**Solution**:
```bash
# Check fact structure
ansible-playbook playbooks/debug_facts.yml -vvv

# Validate JSON structure
cat /tmp/server_facts.json | jq '.'

# Test with mock data first
curl -X POST http://localhost:8181/v1/data/cis_rhel9/filesystem/violations \
  -d @test_data/mock_facts/webserver_noncompliant.json
```

---

## Next Steps

1. ✅ **Deploy OPA server** on AAP controller
2. ✅ **Install callback plugin** for automatic validation
3. ✅ **Create fact collection roles** for each CIS section
4. ✅ **Create compliance check playbook**
5. ✅ **Create AAP job template** for scheduled checks
6. ⬜ **Set up facts database** for historical tracking
7. ⬜ **Configure ServiceNow integration** for incident management
8. ⬜ **Build remediation playbooks** for common violations
9. ⬜ **Create compliance dashboard** in Grafana

---

## Additional Resources

- [CIS RHEL 9 Benchmark Documentation](https://www.cisecurity.org/benchmark/red_hat_linux)
- [Open Policy Agent Documentation](https://www.openpolicyagent.org/docs/latest/)
- [Ansible Automation Platform Documentation](https://docs.ansible.com/automation-platform/)
- [Callback Plugin Development](https://docs.ansible.com/ansible/latest/dev_guide/developing_plugins.html#callback-plugins)

---

**Questions?** Contact your security team or DevOps lead.
