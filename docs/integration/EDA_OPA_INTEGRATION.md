> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx6, AAP-2.5/2.6x4, HOST:8181x3.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

> [!NOTE]
> **2026-10-17:** `ansible/compliance-automation-playbook.yml` and the framework roles it imported
> (`compliance_base`, `iso27001_compliance`, `pci_dss_compliance`, `soc2_compliance`) were removed
> from the tree; nothing called them. Assessments run from `ansible/playbooks/` (for example
> `cis_rhel9_assessment.yml`) through AAP job templates.

# Event Driven Ansible + OPA Integration Guide

## Overview

This guide describes how to integrate **Event Driven Ansible (EDA)** with OPA compliance validation to enable **continuous compliance monitoring** and automated revalidation when environmental changes occur.

## Architecture

```
Environmental Changes → EDA Controller → Rulebooks → Job Templates → OPA Validation → Report Generation
```

### Key Components

1. **Event Sources**: Monitor for changes in infrastructure
2. **EDA Rulebooks**: Define conditions that trigger compliance revalidation
3. **AAP Job Templates**: Execute compliance assessment playbooks
4. **OPA Policies**: Validate compliance against frameworks (CIS, FISMA, NERC-CIP, etc.)
5. **Notification System**: Alert on compliance drift

## EDA Installation (AAP 2.6)

### Prerequisites

- AAP 2.6 with Automation Controller already installed
- Access to AAP installer bundle
- Root/sudo access on AAP server

### Install EDA Controller

```bash
# On AAP 2.6 server at AAP_HOST

# 1. Extract AAP installer if not already
cd /opt
tar xvf ansible-automation-platform-setup-bundle-2.6-*.tar.gz
cd ansible-automation-platform-setup-bundle-2.6-*

# 2. Update inventory file to include EDA
vi inventory

# Add EDA configuration:
[automationedacontroller]
aap-eda.example.com ansible_connection=local

[automationedacontroller:vars]
automationedacontroller_admin_password="{{ vault_eda_admin_password }}"  # Required: set via Ansible Vault
automationedacontroller_pg_host='aap-controller.example.com'
automationedacontroller_pg_port=5432
automationedacontroller_pg_database='awx'
automationedacontroller_pg_username='awx'
automationedacontroller_pg_password="{{ vault_eda_pg_password }}"  # Required: set via Ansible Vault

# 3. Run containerized installer with EDA enabled
ansible-playbook -i inventory-growth \
  collections/ansible_collections/ansible/containerized_installer/playbooks/install.yml \
  -e eda_install=true

# 4. Verify installation
systemctl status automation-eda-controller
```

### Access EDA Controller

- **URL**: `https://AAP_HOST` (integrated with AAP UI)
- **Navigation**: Automation Decisions → Event Driven Ansible
- **Login**: Same credentials as Automation Controller

## Event Sources for Compliance Monitoring

### 1. File System Monitoring (inotify)

Detect configuration file changes that require compliance revalidation.

**Events to Monitor:**
- `/etc/security/` - Security configuration changes
- `/etc/ssh/sshd_config` - SSH configuration changes
- `/etc/audit/` - Audit configuration changes
- `/etc/pam.d/` - Authentication changes
- `/etc/firewalld/` - Firewall rule changes
- Application config files

### 2. System Log Monitoring (journald/syslog)

Monitor system logs for security-relevant events.

**Events to Monitor:**
- Package installation/removal
- Service start/stop/restart
- User account creation/modification
- Privilege escalation
- Failed authentication attempts
- Firewall rule changes

### 3. Webhook Events

Receive events from external systems.

**Event Sources:**
- CI/CD pipeline deployments
- Infrastructure as Code changes (Terraform, CloudFormation)
- Cloud provider events (AWS EventBridge, Azure Event Grid)
- Security tool alerts (SIEM, vulnerability scanners)
- Configuration management tools (Puppet, Chef, Salt)

### 4. Oracle Database Events

Monitor Oracle database for configuration changes.

**Events to Monitor:**
- Database parameter changes (`ALTER SYSTEM`)
- User account creation/modification
- Privilege grants/revokes
- Listener configuration changes
- Audit settings changes
- Password policy changes

### 5. Ansible Facts Changes

Periodic fact collection to detect drift.

**Events to Monitor:**
- Installed package changes
- Service status changes
- Firewall rule changes
- User account changes
- File permission changes

## EDA Rulebook Examples

### Rulebook 1: File System Change Detection

**File**: `eda/rulebooks/compliance_file_monitoring.yml`

```yaml
---
- name: Compliance File System Monitoring
  hosts: all
  sources:
    - name: Monitor security configuration files
      ansible.eda.file:
        path:
          - /etc/security/
          - /etc/ssh/sshd_config
          - /etc/audit/auditd.conf
          - /etc/pam.d/
          - /etc/firewalld/
        recursive: true
        ignore_regexes:
          - ".*\\.swp$"
          - ".*~$"

  rules:
    - name: SSH configuration changed
      condition: event.path is match("/etc/ssh/sshd_config")
      action:
        run_job_template:
          name: "CIS RHEL 9 Compliance Validation"
          organization: "Default"
          job_args:
            extra_vars:
              compliance_trigger: "ssh_config_change"
              changed_file: "{{ event.path }}"
              change_type: "{{ event.type }}"

    - name: Security configuration changed
      condition: event.path is match("/etc/security/.*")
      action:
        run_job_template:
          name: "CIS RHEL 9 Compliance Validation"
          organization: "Default"
          job_args:
            extra_vars:
              compliance_trigger: "security_config_change"
              changed_file: "{{ event.path }}"

    - name: Firewall configuration changed
      condition: event.path is match("/etc/firewalld/.*")
      action:
        run_job_template:
          name: "CIS RHEL 9 Compliance Validation"
          organization: "Default"
          job_args:
            extra_vars:
              compliance_trigger: "firewall_change"
              changed_file: "{{ event.path }}"

    - name: Audit configuration changed
      condition: event.path is match("/etc/audit/.*")
      action:
        run_job_template:
          name: "CIS RHEL 9 Compliance Validation"
          organization: "Default"
          job_args:
            extra_vars:
              compliance_trigger: "audit_config_change"
              changed_file: "{{ event.path }}"
```

### Rulebook 2: System Event Monitoring

**File**: `eda/rulebooks/compliance_system_events.yml`

```yaml
---
- name: Compliance System Event Monitoring
  hosts: all
  sources:
    - name: Monitor systemd journal
      ansible.eda.journald:
        match:
          - "systemd"
          - "sshd"
          - "auditd"
          - "firewalld"

  rules:
    - name: Package installed or removed
      condition: >
        event.MESSAGE is match(".*installed.*|.*removed.*|.*upgraded.*") and
        event._SYSTEMD_UNIT == "packagekit.service"
      action:
        run_job_template:
          name: "CIS RHEL 9 Compliance Validation"
          organization: "Default"
          job_args:
            extra_vars:
              compliance_trigger: "package_change"
              event_message: "{{ event.MESSAGE }}"

    - name: Service state changed
      condition: >
        event._SYSTEMD_UNIT is defined and
        (event.MESSAGE is match(".*Started.*|.*Stopped.*"))
      action:
        run_job_template:
          name: "CIS RHEL 9 Compliance Validation"
          organization: "Default"
          job_args:
            extra_vars:
              compliance_trigger: "service_state_change"
              service_unit: "{{ event._SYSTEMD_UNIT }}"
              event_message: "{{ event.MESSAGE }}"

    - name: User account modification
      condition: >
        event.MESSAGE is match(".*useradd.*|.*usermod.*|.*userdel.*")
      action:
        run_job_template:
          name: "CIS RHEL 9 Compliance Validation"
          organization: "Default"
          job_args:
            extra_vars:
              compliance_trigger: "user_account_change"
              event_message: "{{ event.MESSAGE }}"
```

### Rulebook 3: Oracle Database Event Monitoring

**File**: `eda/rulebooks/compliance_oracle_events.yml`

```yaml
---
- name: Oracle Database Compliance Monitoring
  hosts: oracle_servers
  sources:
    - name: Monitor Oracle alert log
      ansible.eda.file:
        path: /u01/app/oracle/diag/rdbms/*/*/trace/alert_*.log

  rules:
    - name: Database parameter changed
      condition: event.message is match(".*ALTER SYSTEM.*")
      action:
        run_job_template:
          name: "CIS Oracle 19c Compliance Validation"
          organization: "Default"
          job_args:
            extra_vars:
              compliance_trigger: "oracle_parameter_change"
              alert_message: "{{ event.message }}"

    - name: User account created or modified
      condition: >
        event.message is match(".*CREATE USER.*|.*ALTER USER.*|.*GRANT.*|.*REVOKE.*")
      action:
        run_job_template:
          name: "CIS Oracle 19c Compliance Validation"
          organization: "Default"
          job_args:
            extra_vars:
              compliance_trigger: "oracle_user_change"
              alert_message: "{{ event.message }}"

    - name: Audit settings changed
      condition: event.message is match(".*AUDIT.*")
      action:
        run_job_template:
          name: "CIS Oracle 19c Compliance Validation"
          organization: "Default"
          job_args:
            extra_vars:
              compliance_trigger: "oracle_audit_change"
              alert_message: "{{ event.message }}"
```

### Rulebook 4: Webhook-Based Change Detection

**File**: `eda/rulebooks/compliance_webhook_events.yml`

```yaml
---
- name: Webhook-Based Compliance Triggers
  hosts: localhost
  sources:
    - name: Listen for infrastructure changes
      ansible.eda.webhook:
        host: 0.0.0.0
        port: 5000

  rules:
    - name: Infrastructure code deployment
      condition: event.payload.event_type == "deployment"
      action:
        run_job_template:
          name: "Multi-Framework Compliance Validation"
          organization: "Default"
          job_args:
            extra_vars:
              compliance_trigger: "iac_deployment"
              deployment_id: "{{ event.payload.deployment_id }}"
              affected_hosts: "{{ event.payload.hosts }}"

    - name: Cloud resource created
      condition: event.payload.event_type == "cloud_resource_created"
      action:
        run_job_template:
          name: "CIS Cloud Compliance Validation"
          organization: "Default"
          job_args:
            extra_vars:
              compliance_trigger: "cloud_resource_change"
              resource_type: "{{ event.payload.resource_type }}"
              resource_id: "{{ event.payload.resource_id }}"

    - name: Security scan completed
      condition: event.payload.event_type == "security_scan_complete"
      action:
        run_job_template:
          name: "Multi-Framework Compliance Validation"
          organization: "Default"
          job_args:
            extra_vars:
              compliance_trigger: "security_scan"
              scan_results: "{{ event.payload.scan_url }}"
```

### Rulebook 5: Scheduled Drift Detection

**File**: `eda/rulebooks/compliance_scheduled_drift.yml`

```yaml
---
- name: Scheduled Compliance Drift Detection
  hosts: all
  sources:
    - name: Hourly drift check
      ansible.eda.range:
        limit: 1000000  # Run indefinitely
        delay: 3600     # Every hour

  rules:
    - name: Trigger compliance validation
      condition: event.i is defined
      action:
        run_job_template:
          name: "Multi-Framework Compliance Validation"
          organization: "Default"
          job_args:
            extra_vars:
              compliance_trigger: "scheduled_drift_check"
              check_iteration: "{{ event.i }}"
```

## AAP Job Template Configuration

### Create Compliance Validation Job Templates

These job templates will be triggered by EDA rulebooks.

#### 1. CIS RHEL 9 Compliance Validation

```yaml
Name: CIS RHEL 9 Compliance Validation
Job Type: Run
Inventory: Linux Servers
Project: Compliance Automation
Playbook: ansible/compliance-automation-playbook.yml
Credentials: SSH Credentials
Extra Variables:
  run_cis_rhel9: true
  opa_server: "http://AAP_HOST:8181"
  generate_report: true
  notification_enabled: true
Options:
  - Enable Fact Storage
  - Enable Webhook
```

#### 2. CIS Oracle 19c Compliance Validation

```yaml
Name: CIS Oracle 19c Compliance Validation
Job Type: Run
Inventory: Oracle Databases
Project: Compliance Automation
Playbook: ansible/oracle-compliance-playbook.yml
Credentials: Oracle SSH Credentials
Extra Variables:
  run_cis_oracle: true
  opa_server: "http://AAP_HOST:8181"
  generate_report: true
Options:
  - Enable Fact Storage
```

#### 3. Multi-Framework Compliance Validation

```yaml
Name: Multi-Framework Compliance Validation
Job Type: Run
Inventory: All Servers
Project: Compliance Automation
Playbook: ansible/compliance-automation-playbook.yml
Credentials: Multiple Credentials
Extra Variables:
  run_fisma: true
  run_nerc_cip: true
  run_soc2: true
  opa_server: "http://AAP_HOST:8181"
  consolidated_report: true
Options:
  - Enable Fact Storage
```

## EDA Project Setup in AAP

### 1. Create EDA Project

```bash
# In AAP UI: Automation Decisions → Projects

Name: Compliance EDA Rules
SCM Type: Git
SCM URL: https://github.com/ansible-automated-compliance/aac.git
SCM Branch: main
Options:
  - Update Revision on Launch
  - Clean
```

### 2. Create EDA Rulebook Activations

```bash
# In AAP UI: Automation Decisions → Rulebook Activations

Name: File System Compliance Monitoring
Project: Compliance EDA Rules
Rulebook: eda/rulebooks/compliance_file_monitoring.yml
Decision Environment: Default Decision Environment
Restart Policy: on-failure
Enabled: Yes

---

Name: System Event Compliance Monitoring
Project: Compliance EDA Rules
Rulebook: eda/rulebooks/compliance_system_events.yml
Decision Environment: Default Decision Environment
Restart Policy: on-failure
Enabled: Yes

---

Name: Oracle Database Compliance Monitoring
Project: Compliance EDA Rules
Rulebook: eda/rulebooks/compliance_oracle_events.yml
Decision Environment: Default Decision Environment
Restart Policy: on-failure
Enabled: Yes

---

Name: Webhook Compliance Triggers
Project: Compliance EDA Rules
Rulebook: eda/rulebooks/compliance_webhook_events.yml
Decision Environment: Default Decision Environment
Restart Policy: on-failure
Enabled: Yes
```

## Notification Configuration

### Configure Notifications for Compliance Drift

```yaml
# In AAP: Settings → Notifications

Name: Compliance Drift Alert - Email
Type: Email
Host: smtp.example.com
Port: 587
Username: compliance-alerts@example.com
Password: ********
Use TLS: Yes
Sender Email: noreply@example.com
Recipients:
  - security-team@example.com
  - compliance-team@example.com

Notification Messages:
  Started: "Compliance validation triggered: {{ job.name }}"
  Success: "Compliance validation completed: {{ job.name }}"
  Error: "Compliance validation failed: {{ job.name }}"

---

Name: Compliance Drift Alert - Slack
Type: Slack
Target URL: https://hooks.slack.com/services/YOUR/WEBHOOK/URL
Channels:
  - #compliance-alerts
  - #security-ops

---

Name: Compliance Drift Alert - Webhook
Type: Webhook
Target URL: https://your-siem.example.com/api/events
HTTP Method: POST
HTTP Headers:
  Authorization: Bearer YOUR_TOKEN
  Content-Type: application/json
```

## Testing EDA Integration

### 1. Test File Change Detection

```bash
# On monitored system
echo "Test change" >> /etc/ssh/sshd_config

# Verify in EDA Controller:
# - Rulebook activation log shows event received
# - Job template was triggered
# - Compliance validation completed
```

### 2. Test Webhook Trigger

```bash
# Send webhook event
curl -X POST http://AAP_HOST:5000/endpoint \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "deployment",
    "deployment_id": "deploy-12345",
    "hosts": ["server1.example.com", "server2.example.com"]
  }'

# Verify in EDA Controller UI
```

### 3. Test Oracle Database Event

```sql
-- On Oracle database
ALTER SYSTEM SET AUDIT_TRAIL=DB SCOPE=SPFILE;

-- This should trigger compliance revalidation
```

## Continuous Compliance Workflow

### Complete Flow

1. **Change Detected**
   - File system change (inotify)
   - System event (journald)
   - External webhook
   - Scheduled check

2. **EDA Rulebook Evaluation**
   - Event matches rule condition
   - Rule action executed

3. **Job Template Triggered**
   - Compliance validation playbook runs
   - Facts collected from target systems
   - OPA policies evaluated

4. **Results Processing**
   - Compliance report generated
   - Violations identified
   - Compliance score calculated

5. **Notifications Sent**
   - Email to compliance team
   - Slack message to security channel
   - SIEM event generated
   - Ticket created (if configured)

6. **Remediation (Optional)**
   - Auto-remediation playbook triggered for approved changes
   - Manual remediation workflow initiated

## Best Practices

### 1. Event Filtering

Avoid alert fatigue by filtering events intelligently:

```yaml
rules:
  - name: Only significant changes
    condition: >
      event.path is match("/etc/ssh/sshd_config") and
      event.type in ["created", "modified"] and
      event.size > 0
    action: ...
```

### 2. Debouncing

Prevent rapid-fire revalidations:

```yaml
rules:
  - name: Debounced validation
    condition: event.path is match("/etc/security/.*")
    throttle:
      once_within: 5 minutes
    action: ...
```

### 3. Compliance Severity Levels

Route events based on criticality:

```yaml
rules:
  - name: Critical change - immediate validation
    condition: event.path == "/etc/ssh/sshd_config"
    action:
      run_job_template:
        name: "CIS RHEL 9 Compliance Validation - Priority"

  - name: Non-critical change - batched validation
    condition: event.path is match("/etc/profile\\.d/.*")
    throttle:
      once_within: 1 hour
    action: ...
```

### 4. Multi-Stage Validation

Validate different compliance frameworks based on event type:

```yaml
rules:
  - name: SSH change affects multiple frameworks
    condition: event.path == "/etc/ssh/sshd_config"
    actions:
      - run_job_template:
          name: "CIS RHEL 9 Compliance"
      - run_job_template:
          name: "FISMA Compliance"
      - run_job_template:
          name: "SOC 2 Compliance"
```

## Monitoring and Troubleshooting

### View EDA Logs

```bash
# On AAP server
journalctl -u automation-eda-controller -f

# Via CLI
ansible-rulebook --rulebook eda/rulebooks/compliance_file_monitoring.yml --verbose
```

### Check Activation Status

```bash
# In AAP UI: Automation Decisions → Rulebook Activations
# - Shows active/inactive status
# - Event count
# - Last event timestamp
# - Triggered jobs
```

### Debug Rulebook

```bash
# Test rulebook locally
ansible-rulebook \
  --rulebook eda/rulebooks/compliance_file_monitoring.yml \
  --inventory inventory/hosts.yml \
  --verbose
```

## Integration with OPA

EDA triggers compliance validation, which queries OPA for policy evaluation:

```
EDA Event → Job Template → Ansible Playbook → Gather Facts → OPA Evaluation → Report
```

### Example Playbook Task

```yaml
- name: Validate compliance via OPA
  uri:
    url: "http://{{ opa_server }}/v1/data/cis_rhel9/compliant"
    method: POST
    body_format: json
    body: "{{ ansible_facts }}"
    return_content: yes
  register: compliance_result

- name: Send notification if non-compliant
  ansible.builtin.debug:
    msg: "Compliance drift detected!"
  when: not compliance_result.json.result
```

## Compliance Drift Dashboard

Create custom dashboard in AAP showing:
- Recent compliance events
- Triggered validations
- Compliance status by host
- Trend analysis

## References

- [Event Driven Ansible Documentation](https://access.redhat.com/documentation/en-us/red_hat_ansible_automation_platform/2.6/html/getting_started_with_event-driven_ansible)
- [EDA Rulebook Syntax](https://ansible.readthedocs.io/projects/rulebook/)
- [OPA REST API](https://www.openpolicyagent.org/docs/latest/rest-api/)
- [AAP 2.6 Installation Guide](https://access.redhat.com/documentation/en-us/red_hat_ansible_automation_platform/2.6)

## License

Same as parent repository.
