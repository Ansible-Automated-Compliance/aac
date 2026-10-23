> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: HOST:8181x36, RETIRED-HOSTx12, AAP-2.5/2.6x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Using OPA with AAP 2.6 at AAP_HOST
## Quick Usage Guide for Existing Implementation

Since your AAP + OPA integration is already working, here's how to use it for compliance validation.

---

## 🎯 Quick Start: Run Compliance Check

### Method 1: Via AAP Web UI

```
1. Login to AAP: https://AAP_HOST
2. Navigate to: Resources → Templates
3. Find your compliance job template
4. Click "Launch"
5. Watch the output for OPA validation results
```

### Method 2: Via AAP API

```bash
# Set your credentials
export AAP_HOST="AAP_HOST"
export AAP_TOKEN=$AAP_TOKEN  # Get from AAP UI: User → Tokens

# List available job templates
curl -X GET "https://${AAP_HOST}/api/controller/v2/job_templates/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  --insecure | jq '.results[] | {id: .id, name: .name}'

# Launch a compliance check job
curl -X POST "https://${AAP_HOST}/api/controller/v2/job_templates/YOUR_TEMPLATE_ID/launch/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}' \
  --insecure

# Monitor job output
curl -X GET "https://${AAP_HOST}/api/controller/v2/jobs/JOB_ID/stdout/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  --insecure
```

### Method 3: Via awx-cli (from AAP server)

```bash
# SSH to AAP server
ssh admin@AAP_HOST

# List templates
awx job_templates list

# Launch compliance check
awx job_templates launch --name="Your Compliance Template Name" --monitor
```

---

## 🔍 Direct OPA Queries

Since OPA is running on the AAP controller, you can query it directly:

### From AAP Server (SSH)

```bash
# SSH to AAP
ssh admin@AAP_HOST

# Test OPA health
curl http://localhost:8181/health

# List loaded policies
curl http://localhost:8181/v1/policies | jq '.result[].id'

# Query specific compliance section
curl -X POST http://localhost:8181/v1/data/cis_rhel9/filesystem/violations \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "disabled_filesystem_modules": {
        "modules": [
          {"module": "cramfs", "loaded": false, "disabled": true, "compliant": true}
        ],
        "all_compliant": true
      },
      "mount_options": {
        "tmp": {
          "exists": true,
          "has_nodev": true,
          "has_nosuid": true,
          "has_noexec": true,
          "fully_compliant": true
        }
      }
    }
  }' | jq '.'

# Get complete compliance report
curl -X POST http://localhost:8181/v1/data/cis_rhel9/report \
  -H "Content-Type: application/json" \
  -d @/path/to/facts.json | jq '.'
```

### From Remote Machine (if OPA port is open)

```bash
# Query OPA remotely (if port 8181 is accessible)
curl -X POST http://AAP_HOST:8181/v1/data/cis_rhel9/filesystem/violations \
  -H "Content-Type: application/json" \
  -d @facts.json | jq '.'
```

---

## 📝 Common OPA Query Patterns

### 1. Check if System is Compliant

```bash
# Query overall compliance status
curl -X POST http://localhost:8181/v1/data/cis_rhel9/compliant \
  -d @facts.json | jq '.result'

# Output: true or false
```

### 2. Get All Violations

```bash
# Query all violations across all sections
curl -X POST http://localhost:8181/v1/data/cis_rhel9/all_violations \
  -d @facts.json | jq '.result'

# Output: Array of violation strings
```

### 3. Get Violations by Section

```bash
# Filesystem violations
curl -X POST http://localhost:8181/v1/data/cis_rhel9/filesystem/violations \
  -d @facts.json | jq '.result'

# Logging violations
curl -X POST http://localhost:8181/v1/data/cis_rhel9/logging/violations \
  -d @facts.json | jq '.result'

# File permissions violations
curl -X POST http://localhost:8181/v1/data/cis_rhel9/file_permissions/violations \
  -d @facts.json | jq '.result'

# Service violations
curl -X POST http://localhost:8181/v1/data/cis_rhel9/services/violations \
  -d @facts.json | jq '.result'

# Network violations
curl -X POST http://localhost:8181/v1/data/cis_rhel9/network/violations \
  -d @facts.json | jq '.result'
```

### 4. Get Compliance Report

```bash
# Complete compliance report
curl -X POST http://localhost:8181/v1/data/cis_rhel9/report \
  -d @facts.json | jq '.result'

# Pretty print just the summary
curl -X POST http://localhost:8181/v1/data/cis_rhel9/report \
  -d @facts.json | jq '.result.compliance'

# Get violations only
curl -X POST http://localhost:8181/v1/data/cis_rhel9/report \
  -d @facts.json | jq '.result.violations'

# Get recommendations
curl -X POST http://localhost:8181/v1/data/cis_rhel9/report \
  -d @facts.json | jq '.result.recommendations'
```

---

## 🎮 Using OPA in Playbooks

### Pattern 1: Inline Validation

```yaml
---
- name: Check Compliance with Inline OPA Query
  hosts: target_host
  gather_facts: true
  become: true

  tasks:
    - name: Collect compliance facts
      # Your fact collection tasks here
      include_role:
        name: cis_rhel9_facts

    - name: Query OPA for compliance status
      uri:
        url: "http://localhost:8181/v1/data/cis_rhel9/compliant"
        method: POST
        body_format: json
        body:
          input: "{{ ansible_facts }}"
        return_content: yes
      delegate_to: localhost
      register: compliance_result

    - name: Display compliance status
      debug:
        msg: "System is {{ 'COMPLIANT' if compliance_result.json.result else 'NON-COMPLIANT' }}"

    - name: Fail if non-compliant
      fail:
        msg: "System failed compliance check"
      when: not compliance_result.json.result
```

### Pattern 2: Get Detailed Report

```yaml
---
- name: Generate Compliance Report
  hosts: target_host
  gather_facts: true
  become: true

  tasks:
    - name: Collect facts
      include_role:
        name: cis_rhel9_facts

    - name: Get compliance report from OPA
      uri:
        url: "http://localhost:8181/v1/data/cis_rhel9/report"
        method: POST
        body_format: json
        body:
          input: "{{ ansible_facts }}"
        return_content: yes
      delegate_to: localhost
      register: report

    - name: Save report to file
      copy:
        content: "{{ report.json | to_nice_json }}"
        dest: "/tmp/compliance_report_{{ inventory_hostname }}_{{ ansible_date_time.epoch }}.json"
      delegate_to: localhost

    - name: Display summary
      debug:
        msg:
          - "===== COMPLIANCE SUMMARY ====="
          - "Host: {{ inventory_hostname }}"
          - "Overall Compliant: {{ report.json.result.compliance.overall_compliant }}"
          - "Compliant Sections: {{ report.json.result.compliance.compliant_sections }}/5"
          - "Total Violations: {{ report.json.result.violations.total_count }}"
          - "Risk Level: {{ report.json.result.compliance.overall_risk_level | upper }}"
```

### Pattern 3: Section-by-Section Validation

```yaml
---
- name: Validate Each Section
  hosts: target_host
  gather_facts: true
  become: true

  vars:
    sections:
      - filesystem
      - logging
      - file_permissions
      - services
      - network

  tasks:
    - name: Collect facts
      include_role:
        name: cis_rhel9_facts

    - name: Check each section
      uri:
        url: "http://localhost:8181/v1/data/cis_rhel9/{{ item }}/violations"
        method: POST
        body_format: json
        body:
          input: "{{ ansible_facts }}"
        return_content: yes
      delegate_to: localhost
      register: section_results
      loop: "{{ sections }}"

    - name: Display results
      debug:
        msg: "{{ item.item }}: {{ item.json.result | length }} violations"
      loop: "{{ section_results.results }}"
```

---

## 🔧 Using Custom Ansible Module

If you have a custom `opa_validate` module installed:

```yaml
---
- name: Validate with Custom Module
  hosts: target_host
  gather_facts: true
  become: true

  tasks:
    - name: Collect facts
      include_role:
        name: cis_rhel9_facts

    - name: Validate compliance with OPA module
      opa_validate:
        opa_url: "http://localhost:8181"
        policy_path: "cis_rhel9/report"
        input_data: "{{ ansible_facts }}"
      delegate_to: localhost
      register: validation

    - name: Display validation results
      debug:
        var: validation
```

---

## 📊 Generate Reports with Script

Use the report generation script we created:

```bash
# SSH to AAP server
ssh admin@AAP_HOST

# Copy the script if not already there
# (Assuming it's at /usr/local/bin/scripts/full_compliance_report.sh)

# Run report for facts file
/usr/local/bin/scripts/full_compliance_report.sh /path/to/facts.json

# Or if you have facts in JSON format
cat /tmp/server_facts.json | \
  curl -X POST http://localhost:8181/v1/data/cis_rhel9/report \
  -H "Content-Type: application/json" \
  -d @- | jq '.result'
```

---

## 🔄 Continuous Compliance Monitoring

### Schedule Regular Checks

**In AAP:**
1. Go to: **Resources** → **Templates** → Your compliance template
2. Click **Schedules** tab
3. Click **Add**
4. Configure:
   - Name: `Daily Compliance Check`
   - Start date/time: Select time
   - Repeat frequency: `Day`
   - Repeat every: `1 day`
5. Save

**Result**: AAP will automatically run compliance checks and OPA will validate them daily

---

## 📈 Monitoring OPA Performance

```bash
# Check OPA metrics
curl http://localhost:8181/metrics

# View OPA decision logs (if configured)
curl http://localhost:8181/logs

# Check OPA bundle status (if using bundles)
curl http://localhost:8181/v1/status
```

---

## 🎯 Example: Complete Workflow

```bash
# 1. SSH to AAP server
ssh admin@AAP_HOST

# 2. Check OPA is running
curl http://localhost:8181/health

# 3. View loaded policies
curl http://localhost:8181/v1/policies | jq '.result[].id'

# 4. Test with sample data
cat > /tmp/test.json <<EOF
{
  "disabled_filesystem_modules": {
    "modules": [
      {"module": "cramfs", "loaded": false, "disabled": true, "compliant": true}
    ],
    "all_compliant": true
  },
  "mount_options": {
    "tmp": {"has_nodev": true, "has_nosuid": true, "has_noexec": true, "fully_compliant": true}
  },
  "compliance_checks": {
    "all_fs_modules_disabled": true,
    "tmp_partition_secure": true
  }
}
EOF

# 5. Validate with OPA
curl -X POST http://localhost:8181/v1/data/cis_rhel9/filesystem/violations \
  -d @/tmp/test.json | jq '.result'

# 6. If violations array is empty [], system is compliant!
```

---

## 🚨 What to Do with Results

### If Compliant (violations = [])
```
✓ System is compliant
→ No action needed
→ Document compliance for audit
→ Continue monitoring
```

### If Non-Compliant (violations exist)

```yaml
# Example remediation workflow
- name: Remediate Violations
  hosts: non_compliant_hosts
  become: true

  tasks:
    - name: Fix filesystem issues
      when: "'filesystem' in violations"
      include_role:
        name: remediate_filesystem

    - name: Fix service issues
      when: "'services' in violations"
      include_role:
        name: remediate_services

    - name: Re-validate
      include_tasks: compliance_check.yml
```

---

## 📝 Quick Reference Commands

```bash
# Health Check
curl http://localhost:8181/health

# List Policies
curl http://localhost:8181/v1/policies | jq '.result[].id'

# Check Filesystem Compliance
curl -X POST http://localhost:8181/v1/data/cis_rhel9/filesystem/violations -d @facts.json | jq '.result'

# Check Overall Compliance
curl -X POST http://localhost:8181/v1/data/cis_rhel9/compliant -d @facts.json | jq '.result'

# Get Full Report
curl -X POST http://localhost:8181/v1/data/cis_rhel9/report -d @facts.json | jq '.result'

# Count Violations
curl -X POST http://localhost:8181/v1/data/cis_rhel9/all_violations -d @facts.json | jq '.result | length'
```

---

## 🆘 Need Help?

### Check OPA Status
```bash
# On AAP server
sudo systemctl status opa
sudo journalctl -u opa -n 50
```

### Test OPA Policy
```bash
# Syntax check
opa test /etc/opa/policies/cis_rhel9/

# View policy evaluation
opa eval --explain full \
  --data /etc/opa/policies/cis_rhel9/ \
  --input facts.json \
  'data.cis_rhel9.report'
```

### Debug Playbook
```bash
# Run with verbose output
ansible-playbook playbook.yml -vvv

# Check callback plugin
export ANSIBLE_DEBUG=1
ansible-playbook playbook.yml
```

---

## 🎉 You're Ready!

Your OPA integration is working. You can now:

✅ Run compliance checks from AAP
✅ Query OPA directly for validation
✅ Generate compliance reports
✅ Integrate OPA queries into playbooks
✅ Schedule automated compliance scans
✅ Remediate violations automatically

**Your OPA server is running at**: `http://localhost:8181` (on AAP_HOST)

**To validate facts**: POST JSON to `http://localhost:8181/v1/data/cis_rhel9/<section>/violations`

**For full report**: POST JSON to `http://localhost:8181/v1/data/cis_rhel9/report`

---

## 🔔 Event Driven Ansible (EDA) Integration

For **continuous compliance monitoring** and automated revalidation when environmental changes occur, use Event Driven Ansible.

### EDA Installation and Setup

**Quick Setup:**
```bash
# On AAP server at AAP_HOST
export CONTROLLER_PASSWORD=YOUR_ADMIN_PASSWORD
sudo ./aap-integration/eda-setup/install_and_seed_eda.sh
```

This installs EDA Controller and seeds it with:
- Pre-configured compliance rulebooks
- Job templates for all frameworks
- Inventory groups
- Notification templates

### EDA Use Cases

**1. File System Change Detection**
- Monitors `/etc/ssh/sshd_config`, `/etc/audit/`, `/etc/firewalld/` for changes
- Automatically triggers compliance revalidation

**2. System Event Monitoring**
- Detects package installations/removals
- Monitors service state changes
- Tracks user account modifications
- Triggers compliance validation automatically

**3. Oracle Database Monitoring**
- Monitors Oracle alert logs for parameter changes
- Detects user/privilege changes
- Watches listener configuration changes
- Triggers CIS Oracle 19c validation

**4. Webhook-Based Triggers**
- CI/CD pipeline deployments
- Cloud resource changes
- Security scan completions
- Manual compliance checks

**5. Scheduled Drift Detection**
- Hourly drift checks
- Daily comprehensive scans
- Critical infrastructure 30-minute checks

### Accessing EDA Controller

```
URL: https://AAP_HOST
Navigate to: Automation Decisions → Event Driven Ansible
Username: admin
Password: [your CONTROLLER_PASSWORD]
```

### View Active Rulebooks

```
AAP UI → Automation Decisions → Rulebook Activations
```

Shows:
- Active/inactive rulebooks
- Event counts
- Triggered jobs
- Last event timestamp

### View Event Stream

```
AAP UI → Automation Decisions → Event Streams
```

Real-time view of:
- Events received by rulebooks
- Triggered compliance validations
- Event sources status

### Testing EDA Integration

**Test File Change Detection:**
```bash
# On monitored system
echo "Test change" >> /etc/ssh/sshd_config

# Verify in AAP:
# - Event Stream shows event
# - Job template triggered
# - Compliance validation completed
```

**Test Webhook Trigger:**
```bash
curl -X POST http://AAP_HOST:5000/endpoint \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "deployment",
    "deployment_id": "deploy-12345",
    "hosts": ["server1.example.com"]
  }'
```

### EDA Documentation

For complete EDA integration guide:
- **docs/integration/EDA_OPA_INTEGRATION.md** - Comprehensive integration documentation
- **aap-integration/eda-setup/README.md** - Installation and setup guide
- **eda/rulebooks/** - Pre-configured rulebook definitions
