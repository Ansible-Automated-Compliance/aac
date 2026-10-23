> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx3, HOST:8181x2.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# AAP Workflow Template Setup Guide
## Ansible Automated Compliance (AAC) - PostgreSQL Integration

**Document Version:** 1.0
**Last Updated:** November 26, 2025
**AAP Version:** 2.6

---

## Overview

This guide explains how to configure Ansible Automation Platform (AAP) 2.6 workflow templates for the complete compliance automation pipeline with PostgreSQL historical tracking.

### Workflow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   AAP Compliance Workflow                       │
└─────────────────────────────────────────────────────────────────┘

Step 1: Fact Collection
   ↓
   │  Collects system facts (Ansible gather_facts + custom modules)
   │  Output: JSON file with ~180KB of system configuration data
   │
Step 2: Store Facts in PostgreSQL
   ↓
   │  Stores facts in systems + system_facts tables
   │  Returns: system_id, facts_id
   │  Passes artifacts to next step via set_stats
   │
Step 3: OPA Policy Evaluation
   ↓
   │  Sends facts to OPA REST API for compliance evaluation
   │  Output: Compliance assessment report (JSON)
   │
Step 4: Store Assessment Results
   ↓
   │  Stores results in compliance_assessments table
   │  Links to system via system_id
   │  Returns: assessment_id, compliance_score
   │
Step 5: Generate HTML Report (Optional)
   ↓
   │  Creates executive compliance dashboard
   │  Saves to /tmp/compliance_reports/
   │
Step 6: Send Notifications (Conditional)
   └→ Only if compliance failures detected
      Sends alerts via email/Slack/ServiceNow

```

---

## Prerequisites

### 1. Database Setup

First, initialize the PostgreSQL database:

```bash
# On AAP controller
ansible-playbook -i ansible/inventory/postgres.yml \
  ansible/playbooks/postgres_database_init.yml \
  --vault-password-file ~/.vault_pass
```

This creates:
- Database: `compliance_automation`
- User: `aap_compliance` (read/write)
- User: `compliance_reporter` (read-only)
- Schema: 8 tables, 4 views, triggers

### 2. AAP Custom Credential Type

Create a custom credential type for database access:

**Credential Type Name:** `AAC Database Credential`

**Input Configuration:**
```yaml
fields:
  - id: db_host
    type: string
    label: Database Host
    default: AAP_HOST
  - id: db_port
    type: string
    label: Database Port
    default: "5432"
  - id: db_name
    type: string
    label: Database Name
    default: compliance_automation
  - id: db_user
    type: string
    label: Database User
    default: aap_compliance
  - id: db_password
    type: string
    label: Database Password
    secret: true
required:
  - db_password
```

**Injector Configuration:**
```yaml
env:
  AAC_DB_HOST: '{{ db_host }}'
  AAC_DB_PORT: '{{ db_port }}'
  AAC_DB_NAME: '{{ db_name }}'
  AAC_DB_USER: '{{ db_user }}'
  AAC_DB_PASSWORD: '{{ db_password }}'
```

### 3. Create Database Credential

1. Navigate to: **Resources → Credentials → Add**
2. Name: `AAC PostgreSQL Database`
3. Credential Type: `AAC Database Credential`
4. Database Password: `{{ vault_pg_password }}`
5. Save

---

## Job Template Configuration

### Job Template 1: Enhanced Fact Collection

**Name:** `AAC - Collect System Facts`
**Job Type:** Run
**Inventory:** `<target_systems>`
**Project:** `Compliance Automation Policies`
**Playbook:** `ansible/playbooks/enhanced_cis_fact_collection.yml`
**Credentials:**
  - Machine Credential (SSH)
**Extra Variables:**
```yaml
report_dir: /tmp/compliance_facts
timestamp: "{{ lookup('pipe', 'date +%Y%m%d_%H%M%S') }}"
```
**Options:**
- [x] Enable Fact Storage
- [x] Privilege Escalation Enabled

**Description:**
Collects comprehensive system facts for compliance assessment. Gathers OS configuration, network settings, security parameters, and installed packages.

---

### Job Template 2: Store Facts in Database

**Name:** `AAC - Store Facts in PostgreSQL`
**Job Type:** Run
**Inventory:** `localhost`
**Project:** `Compliance Automation Policies`
**Playbook:** `ansible/playbooks/store_compliance_facts.yml`
**Credentials:**
  - AAC PostgreSQL Database
**Extra Variables:**
```yaml
report_dir: /tmp/compliance_facts
inventory_hostname: "{{ lookup('env', 'TARGET_HOSTNAME') }}"
timestamp: "{{ lookup('env', 'TARGET_TIMESTAMP') }}"
```
**Options:**
- [x] Enable Fact Storage

**Description:**
Stores collected facts in PostgreSQL database. Inserts/updates system record and creates new fact collection entry with JSONB storage.

---

### Job Template 3: OPA Policy Evaluation

**Name:** `AAC - CIS RHEL 9 Assessment`
**Job Type:** Run
**Inventory:** `<target_systems>`
**Project:** `Compliance Automation Policies`
**Playbook:** `ansible/playbooks/cis_rhel9_assessment.yml`
**Credentials:**
  - Machine Credential (SSH)
**Extra Variables:**
```yaml
opa_server_url: http://localhost:8181
compliance_framework: cis_rhel9
report_dir: /tmp/compliance_reports
generate_html_report: true
```
**Options:**
- [x] Privilege Escalation Enabled

**Description:**
Evaluates collected facts against CIS RHEL 9 benchmark policies using OPA. Generates compliance assessment with detailed violations and remediation guidance.

---

### Job Template 4: Store Assessment Results

**Name:** `AAC - Store Assessment Results`
**Job Type:** Run
**Inventory:** `localhost`
**Project:** `Compliance Automation Policies`
**Playbook:** `ansible/playbooks/store_compliance_results.yml`
**Credentials:**
  - AAC PostgreSQL Database
**Extra Variables:**
```yaml
report_dir: /tmp/compliance_reports
inventory_hostname: "{{ lookup('env', 'TARGET_HOSTNAME') }}"
timestamp: "{{ lookup('env', 'TARGET_TIMESTAMP') }}"
system_id: "{{ lookup('env', 'SYSTEM_ID') }}"
facts_id: "{{ lookup('env', 'FACTS_ID') }}"
```

**Description:**
Stores compliance assessment results in PostgreSQL. Links to system and facts via foreign keys. Records violations, compliance score, and detailed findings.

---

### Job Template 5: Generate Compliance Report

**Name:** `AAC - Generate HTML Report`
**Job Type:** Run
**Inventory:** `localhost`
**Project:** `Compliance Automation Policies`
**Playbook:** `ansible/playbooks/generate_html_report.yml` *(to be created)*
**Extra Variables:**
```yaml
report_format: html
report_output_dir: /tmp/compliance_reports
include_charts: true
```

**Description:**
Generates executive-level HTML compliance dashboard with compliance trends, violation summaries, and remediation priorities.

---

### Job Template 6: Send Compliance Notifications

**Name:** `AAC - Send Failure Notifications`
**Job Type:** Run
**Inventory:** `localhost`
**Project:** `Compliance Automation Policies`
**Playbook:** `ansible/playbooks/send_compliance_notifications.yml` *(to be created)*
**Credentials:**
  - Email/Slack/ServiceNow Credential
**Extra Variables:**
```yaml
notification_channels:
  - email
  - slack
compliance_threshold: 90
notification_on_failure_only: true
```

**Description:**
Sends notifications when compliance violations are detected. Integrates with email, Slack, or ServiceNow for alerting.

---

## Workflow Template Configuration

### Create Workflow Template

1. Navigate to: **Resources → Templates → Add → Add workflow template**
2. Configure workflow:

**Name:** `AAC - Complete Compliance Assessment with PostgreSQL`
**Organization:** `Default`
**Inventory:** `<your_managed_systems>`
**Extra Variables:**
```yaml
# Target system configuration
target_hostname: "{{ inventory_hostname }}"
target_timestamp: "{{ ansible_date_time.iso8601_basic_short }}"

# OPA configuration
opa_server_url: http://localhost:8181
compliance_framework: cis_rhel9

# Database configuration (injected via credential)
# db_host, db_port, db_name, db_user, db_password

# Notification configuration
send_notifications_on_failure: true
notification_threshold: 95

# Report configuration
generate_html_report: true
report_retention_days: 365
```

**Options:**
- [x] Enable Concurrent Jobs: 5
- [x] Enable Webhooks (for external triggers)

**Survey (Optional):**
Add survey questions to make workflow parameterized:

| Prompt | Variable | Type | Default |
|--------|----------|------|---------|
| Target System Hostname | target_hostname | Text | (required) |
| Compliance Framework | compliance_framework | Multiple Choice | cis_rhel9 |
| Generate HTML Report? | generate_html_report | Multiple Choice (Yes/No) | Yes |
| Send Notifications? | send_notifications | Multiple Choice (Yes/No) | Yes |

---

### Workflow Visualizer Configuration

After creating the workflow template, click **Visualizer** and add nodes:

#### Node 1: START
- **Type:** Start Node
- **Convergence:** Any

#### Node 2: Collect Facts
- **Type:** Job Template
- **Template:** `AAC - Collect System Facts`
- **Convergence:** Any
- **On Success:** → Node 3

#### Node 3: Store Facts
- **Type:** Job Template
- **Template:** `AAC - Store Facts in PostgreSQL`
- **Convergence:** Any
- **On Success:** → Node 4
- **Extra Data:**
```yaml
inventory_hostname: "{{ target_hostname }}"
timestamp: "{{ target_timestamp }}"
```

#### Node 4: OPA Evaluation
- **Type:** Job Template
- **Template:** `AAC - CIS RHEL 9 Assessment`
- **Convergence:** Any
- **On Success:** → Node 5

#### Node 5: Store Results
- **Type:** Job Template
- **Template:** `AAC - Store Assessment Results`
- **Convergence:** Any
- **On Success:** → Node 6
- **Extra Data:**
```yaml
inventory_hostname: "{{ target_hostname }}"
timestamp: "{{ target_timestamp }}"
system_id: "{{ system_id }}"  # Passed from Node 3
facts_id: "{{ facts_id }}"    # Passed from Node 3
```

#### Node 6: Generate Report (Optional)
- **Type:** Job Template
- **Template:** `AAC - Generate HTML Report`
- **Convergence:** Any
- **Enabled:** `{{ generate_html_report }}`
- **On Success:** → Node 7 (if enabled)
- **On Failure:** → END

#### Node 7: Send Notifications (Conditional)
- **Type:** Job Template
- **Template:** `AAC - Send Failure Notifications`
- **Convergence:** Any
- **Enabled:** `{{ send_notifications and (compliance_score < notification_threshold) }}`
- **On Success/Failure:** → END

---

## Workflow Artifact Passing

AAP workflows pass data between job templates using `set_stats`. Here's how artifacts flow:

### From "Collect Facts" → "Store Facts":
```yaml
# In enhanced_cis_fact_collection.yml
- name: Save facts file path
  set_stats:
    data:
      facts_file: "{{ report_dir }}/{{ inventory_hostname }}_facts_{{ timestamp }}.json"
      target_hostname: "{{ inventory_hostname }}"
      target_timestamp: "{{ timestamp }}"
```

### From "Store Facts" → "Store Results":
```yaml
# In store_compliance_facts.yml
- name: Save IDs for next workflow step
  set_stats:
    data:
      system_id: "{{ system_id }}"
      facts_id: "{{ facts_id }}"
      hostname: "{{ hostname }}"
      platform: "{{ platform }}"
```

### From "OPA Evaluation" → "Store Results":
```yaml
# In cis_rhel9_assessment.yml
- name: Save assessment results
  set_stats:
    data:
      compliance_score: "{{ compliance_summary.compliance_score }}"
      total_violations: "{{ compliance_summary.total_violations }}"
      report_file: "{{ report_dir }}/{{ inventory_hostname }}_compliance_{{ timestamp }}.json"
```

---

## Scheduling Compliance Assessments

### Schedule 1: Daily Production Assessment

**Name:** `Daily Compliance Assessment - Production`
**Start Date/Time:** Today at 02:00 AM
**Frequency:** Every day
**Workflow Template:** `AAC - Complete Compliance Assessment with PostgreSQL`
**Inventory:** `Production Systems`
**Extra Variables:**
```yaml
compliance_framework: cis_rhel9
send_notifications: true
notification_threshold: 95
```

### Schedule 2: Weekly Full Infrastructure Scan

**Name:** `Weekly Full Infrastructure Compliance Scan`
**Start Date/Time:** Sunday at 01:00 AM
**Frequency:** Every week
**Workflow Template:** `AAC - Complete Compliance Assessment with PostgreSQL`
**Inventory:** `All Managed Systems`
**Extra Variables:**
```yaml
compliance_framework: cis_rhel9
generate_html_report: true
send_notifications: true
notification_threshold: 90
```

### Schedule 3: Monthly Audit Report Generation

**Name:** `Monthly Compliance Audit Report`
**Start Date/Time:** First day of month at 08:00 AM
**Frequency:** Monthly
**Workflow Template:** `AAC - Generate Audit Evidence Report` *(to be created)*

---

## Event-Driven Automation (EDA)

### Rulebook: Auto-Remediate on Compliance Drift

Create an Event-Driven Ansible rulebook to trigger assessments when configuration changes are detected:

**File:** `rulebooks/compliance_drift_detection.yml`
```yaml
---
- name: Compliance Drift Detection
  hosts: all
  sources:
    - ansible.eda.webhook:
        host: 0.0.0.0
        port: 5000

  rules:
    - name: Trigger compliance assessment on configuration change
      condition: event.payload.type == "configuration_change"
      action:
        run_workflow_template:
          name: "AAC - Complete Compliance Assessment with PostgreSQL"
          organization: "Default"
          extra_vars:
            target_hostname: "{{ event.payload.hostname }}"
            compliance_framework: "cis_rhel9"
            trigger_reason: "configuration_change_detected"
```

---

## Testing the Workflow

### 1. Manual Test Execution

```bash
# Via AWX CLI
awx workflow_job launch \
  --workflow_job_template "AAC - Complete Compliance Assessment with PostgreSQL" \
  --extra_vars '{"target_hostname": "test-server-01"}'

# Via API
curl -X POST https://aap-controller.local/api/controller/v2/workflow_job_templates/10/launch/ \
  -H "Authorization: Bearer $AAP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"extra_vars": {"target_hostname": "test-server-01"}}'
```

### 2. Verify Database Storage

```sql
-- Connect to database
psql -h AAP_HOST -U aap_compliance -d compliance_automation

-- Check system was recorded
SELECT id, hostname, os_family, os_distribution, last_seen
FROM systems
ORDER BY last_seen DESC
LIMIT 5;

-- Check fact collection
SELECT
  s.hostname,
  sf.collection_date,
  sf.fact_set_type,
  pg_size_pretty(pg_column_size(sf.ansible_facts)) as facts_size
FROM system_facts sf
JOIN systems s ON sf.system_id = s.id
ORDER BY sf.collection_date DESC
LIMIT 5;

-- Check compliance assessments
SELECT
  s.hostname,
  cf.framework_name,
  ca.assessment_date,
  ca.is_compliant,
  ca.compliance_score,
  ca.controls_failed
FROM compliance_assessments ca
JOIN systems s ON ca.system_id = s.id
JOIN compliance_frameworks cf ON ca.framework_id = cf.id
ORDER BY ca.assessment_date DESC
LIMIT 10;

-- View compliance trend
SELECT * FROM v_compliance_trends
WHERE hostname = 'test-server-01'
  AND framework_code = 'cis_rhel9'
ORDER BY assessment_day DESC
LIMIT 30;
```

### 3. Check Audit Log

```sql
SELECT
  event_timestamp,
  event_type,
  s.hostname,
  event_description,
  triggered_by,
  status
FROM audit_log al
LEFT JOIN systems s ON al.system_id = s.id
WHERE event_timestamp > NOW() - INTERVAL '1 hour'
ORDER BY event_timestamp DESC;
```

---

## Troubleshooting

### Issue: Workflow fails at "Store Facts" step

**Error:** `podman exec postgresql: No such container`

**Solution:**
The playbook assumes PostgreSQL runs in a Podman container. Update playbooks to use direct `psql` instead:

```yaml
# Replace:
podman exec postgresql psql -U postgres -d compliance_automation

# With:
psql -h {{ db_host }} -p {{ db_port }} -U {{ db_user }} -d {{ db_name }}
```

Or modify inventory to set connection method:
```yaml
postgres_connection_method: direct  # or 'podman' or 'docker'
```

### Issue: `set_stats` artifacts not passing between jobs

**Solution:**
Ensure workflow nodes are configured with **Extra Data** to accept artifacts:

```yaml
# In Node configuration → Extra Data
system_id: "{{ system_id }}"
facts_id: "{{ facts_id }}"
```

### Issue: Database connection timeouts

**Solution:**
1. Check PostgreSQL is listening on network interface:
```bash
# Edit /var/lib/pgsql/14/data/postgresql.conf
listen_addresses = '*'

# Edit /var/lib/pgsql/14/data/pg_hba.conf
host  compliance_automation  aap_compliance  192.0.2.0/24  md5
```

2. Restart PostgreSQL:
```bash
sudo systemctl restart postgresql-14
```

3. Verify firewall allows port 5432:
```bash
sudo firewall-cmd --add-service=postgresql --permanent
sudo firewall-cmd --reload
```

---

## Performance Optimization

### 1. Database Indexing

The schema includes indexes on frequently queried columns. Monitor query performance:

```sql
-- Show slow queries
SELECT
  query,
  calls,
  mean_exec_time,
  total_exec_time
FROM pg_stat_statements
WHERE mean_exec_time > 1000  -- queries slower than 1 second
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Add indexes if needed
CREATE INDEX CONCURRENTLY idx_assessments_system_date
ON compliance_assessments(system_id, assessment_date DESC);
```

### 2. Workflow Concurrency

Limit concurrent workflow executions to prevent database connection exhaustion:

**Workflow Template → Options:**
- Instance Groups: `default` (limit to specific execution nodes)
- Forks: `5` (max parallel fact collections)
- Job Slicing: Enable for large inventories (10 slices max)

### 3. Fact Collection Optimization

For large environments (1000+ systems):

**Use Smart Inventory:** Group systems by OS type and assess in batches:
```yaml
# Smart inventory filter
ansible_distribution == "RedHat" and ansible_distribution_major_version == "9"
```

**Schedule Batches:** Stagger assessments across the day:
- Batch 1 (RHEL 9): 02:00 AM
- Batch 2 (RHEL 8): 04:00 AM
- Batch 3 (Ubuntu): 06:00 AM

---

## Integration with External Tools

### Grafana Dashboard

Create read-only database connection for Grafana:

**Data Source Configuration:**
- Type: PostgreSQL
- Host: `AAP_HOST:5432`
- Database: `compliance_automation`
- User: `compliance_reporter`
- Password: `{{ vault_pg_password }}`
- SSL Mode: Disable (or configure for production)

**Sample Dashboard Query (Compliance Trend):**
```sql
SELECT
  assessment_date AS "time",
  hostname,
  compliance_score
FROM v_compliance_trends
WHERE $__timeFilter(assessment_date)
ORDER BY assessment_date
```

### ServiceNow Integration

Create incident tickets for critical violations:

**Playbook:** `ansible/playbooks/servicenow_ticket_creation.yml`
```yaml
- name: Create ServiceNow incident for critical violations
  servicenow.itsm.incident:
    instance:
      host: "{{ servicenow_instance }}"
      username: "{{ servicenow_user }}"
      password: "{{ servicenow_password }}"
    state: new
    short_description: "Critical compliance violation detected: {{ violation.control_id }}"
    description: "{{ violation.violation_message }}"
    urgency: high
    impact: high
    assigned_to: "{{ violation.assigned_to | default('compliance_team') }}"
```

---

## Next Steps

1. **Initialize PostgreSQL Database:**
   ```bash
   ansible-playbook -i ansible/inventory/postgres.yml \
     ansible/playbooks/postgres_database_init.yml
   ```

2. **Create AAP Custom Credential Type and Credential**

3. **Import Job Templates** (via AAP UI or awx-cli)

4. **Create Workflow Template** using Visualizer

5. **Test Workflow** with single system

6. **Schedule Production Assessments**

7. **Configure Grafana Dashboards** for compliance visibility

8. **Set up Event-Driven Automation** for drift detection

---

## Reference Documentation

- [AAP Workflow Documentation](https://docs.ansible.com/automation-controller/latest/html/userguide/workflows.html)
- [PostgreSQL Performance Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)
- [OPA REST API Reference](https://www.openpolicyagent.org/docs/latest/rest-api/)
- [Ansible set_stats Module](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/set_stats_module.html)

---

**Document Maintained By:** Compliance Automation Team
**Last Review:** November 26, 2025
**Status:** Production Ready
