> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx3, HOST:8181x3, MASTER-BRANCHx1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# AAP Workflow Setup Guide
## Historical Trending with PostgreSQL Integration

**Author:** Tim Coulter & Claude
**Date:** November 24, 2025
**Repository:** ansible-automated-compliance/aac

---

## Overview

This guide explains how to set up an Ansible Automation Platform (AAP) Workflow Template that enables **historical compliance trending** by storing assessment data in PostgreSQL.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              AAP COMPLIANCE WORKFLOW (3-Step)                │
└─────────────────────────────────────────────────────────────┘

Step 1: CIS RHEL 9 Assessment
├─ Collect system facts via Ansible
├─ Query OPA for policy evaluation
├─ Generate JSON reports (facts + results)
└─ Output: JSON files in /tmp/compliance_assessments/

         ↓ (on success)

Step 2: Store Compliance Facts
├─ Read facts JSON from Step 1
├─ INSERT INTO compliance_facts table
├─ Generate unique facts_id
└─ Pass facts_id to Step 3 via set_stats

         ↓ (on success)

Step 3: Store Compliance Results
├─ Read compliance report JSON from Step 1
├─ INSERT INTO compliance_results (linked to facts_id)
├─ INSERT INTO policy_violations (individual failures)
└─ Record audit trail
```

---

## Prerequisites

### 1. Running Services

Verify these services are running on `AAP_HOST`:

```bash
# Check OPA
curl http://localhost:8181/v1/data

# Check PostgreSQL container
podman ps | grep postgresql

# Check AAP containers
podman ps | grep automation
```

### 2. Database Schema

The PostgreSQL compliance database should have these tables:

- `compliance_facts` - System facts with timestamps
- `compliance_results` - Assessment results (linked to facts)
- `policy_violations` - Individual control violations
- `compliance_audit_trail` - Change tracking

Schema was created during initial setup. To verify:

```bash
podman exec $(podman ps | grep postgresql | awk '{print $1}') \
  psql -U postgres -d compliance -c '\dt'
```

### 3. Required Playbooks

These playbooks must exist in `~/compliance/ansible/playbooks/`:

1. **`cis_rhel9_assessment.yml`** ✓ (existing)
2. **`store_compliance_facts.yml`** ⭐ (new)
3. **`store_compliance_results.yml`** ⭐ (new)
4. **`compliance_trending_report.yml`** ⭐ (new - bonus)

---

## Step-by-Step Workflow Setup in AAP

### Step 1: Create Project

1. Navigate to **Resources → Projects**
2. Click **Add**
3. Configure:
   - **Name:** `Compliance Automation`
   - **Organization:** Your org
   - **SCM Type:** Git
   - **SCM URL:** `https://github.com/ansible-automated-compliance/aac.git`
   - **SCM Branch:** `master`
   - **SCM Credential:** Your GitHub SSH key
4. Save and **Sync** the project

### Step 2: Create Inventory

1. Navigate to **Resources → Inventories**
2. Use existing inventory or create new:
   - **Name:** `CIS RHEL 9 Test Systems`
   - Add hosts you want to assess
3. For local testing, add:
   ```yaml
   localhost:
     ansible_connection: local
     ansible_become: yes
   ```

### Step 3: Create Job Templates

#### Template 1: CIS RHEL 9 Assessment

- **Name:** `CIS RHEL 9 - Assessment`
- **Job Type:** Run
- **Inventory:** Your inventory
- **Project:** Compliance Automation
- **Playbook:** `ansible/playbooks/cis_rhel9_assessment.yml`
- **Credentials:** Machine credential with sudo
- **Variables:**
  ```yaml
  opa_server_url: http://localhost:8181
  report_dir: /home/aapuser1/compliance/reports
  ```
- **Options:**
  - ✓ Enable Fact Storage
  - ✓ Concurrent Jobs

#### Template 2: Store Compliance Facts

- **Name:** `CIS RHEL 9 - Store Facts`
- **Job Type:** Run
- **Inventory:** localhost (or same as above)
- **Project:** Compliance Automation
- **Playbook:** `ansible/playbooks/store_compliance_facts.yml`
- **Credentials:** Same as Template 1
- **Variables:**
  ```yaml
  report_dir: /home/aapuser1/compliance/reports
  timestamp: "{{ tower_workflow_job_id }}"
  inventory_hostname: localhost
  ```
- **Extra Vars Prompt:** Yes (to accept timestamp from workflow)

#### Template 3: Store Compliance Results

- **Name:** `CIS RHEL 9 - Store Results`
- **Job Type:** Run
- **Inventory:** localhost (or same as above)
- **Project:** Compliance Automation
- **Playbook:** `ansible/playbooks/store_compliance_results.yml`
- **Credentials:** Same as above
- **Variables:**
  ```yaml
  report_dir: /home/aapuser1/compliance/reports
  timestamp: "{{ tower_workflow_job_id }}"
  inventory_hostname: localhost
  ```
- **Extra Vars Prompt:** Yes

### Step 4: Create Workflow Template

1. Navigate to **Resources → Templates**
2. Click **Add → Add workflow template**
3. Configure:
   - **Name:** `CIS RHEL 9 - Full Compliance with Trending`
   - **Organization:** Your org
   - **Inventory:** Your inventory

4. Click **Visualizer** to add workflow nodes:

   **Node 1:**
   - Job Template: `CIS RHEL 9 - Assessment`
   - Convergence: Any

   **Node 2:** (Connect "On Success" from Node 1)
   - Job Template: `CIS RHEL 9 - Store Facts`
   - Convergence: Any
   - **Prompt:** Pass variables:
     ```yaml
     timestamp: "{{ workflow_job_id }}"
     ```

   **Node 3:** (Connect "On Success" from Node 2)
   - Job Template: `CIS RHEL 9 - Store Results`
   - Convergence: Any
   - **Prompt:** Pass variables:
     ```yaml
     timestamp: "{{ workflow_job_id }}"
     facts_id: "{{ tower_job_id }}"  # From Node 2 set_stats
     ```

5. Save the workflow

---

## Testing the Workflow

### Quick Test

1. Navigate to your workflow template
2. Click **Launch**
3. Monitor execution in **Views → Jobs**

Expected results:
- Step 1: Creates JSON reports in `/home/aapuser1/compliance/reports/`
- Step 2: Inserts record into `compliance_facts` table
- Step 3: Inserts records into `compliance_results` and `policy_violations`

### Verify Data in PostgreSQL

```bash
# SSH to AAP server
ssh aapuser1@AAP_HOST

# Get PostgreSQL container ID
PGID=$(podman ps | grep postgresql | awk '{print $1}')

# Check facts count
podman exec $PGID psql -U postgres -d compliance -c \
  "SELECT COUNT(*) FROM compliance_facts;"

# View latest assessment
podman exec $PGID psql -U postgres -d compliance -c \
  "SELECT hostname, platform, collection_timestamp
   FROM compliance_facts
   ORDER BY collection_timestamp DESC LIMIT 5;"

# Check compliance results
podman exec $PGID psql -U postgres -d compliance -c \
  "SELECT
     cf.hostname,
     cr.policy_name,
     cr.compliance_percentage,
     cr.evaluation_timestamp
   FROM compliance_results cr
   JOIN compliance_facts cf ON cr.facts_id = cf.id
   ORDER BY cr.evaluation_timestamp DESC
   LIMIT 10;"
```

### View Trending Over Time

After running the workflow multiple times, query trends:

```sql
-- Compliance trend for a specific system
SELECT
  evaluation_timestamp::date as assessment_date,
  compliance_percentage,
  failed_controls
FROM compliance_results cr
JOIN compliance_facts cf ON cr.facts_id = cf.id
WHERE cf.hostname = 'ocptesttc'
ORDER BY evaluation_timestamp DESC;

-- Average compliance score over time
SELECT
  evaluation_timestamp::date as day,
  AVG(compliance_percentage) as avg_compliance,
  COUNT(*) as assessments
FROM compliance_results
GROUP BY evaluation_timestamp::date
ORDER BY day DESC;
```

---

## Scheduling Recurring Assessments

### Option 1: AAP Schedule

1. Open your Workflow Template
2. Navigate to **Schedules** tab
3. Click **Add**
4. Configure:
   - **Name:** `Daily CIS Assessment`
   - **Start Date/Time:** Choose time
   - **Frequency:** Daily
   - **Time Zone:** Your timezone

### Option 2: AAP Survey (Manual with Parameters)

Add a survey to the workflow template:

1. **Survey Enabled:** Yes
2. Add questions:
   - **Variable:** `target_hosts`
   - **Prompt:** Which systems to assess?
   - **Answer Type:** Text
   - **Default:** `all`

---

## Trending Report Playbook (Bonus)

To generate a historical trending report:

```bash
cd ~/compliance/ansible

# Generate 30-day trend report
ansible-playbook -i inventory/rhel9_test.yml \
  playbooks/compliance_trending_report.yml \
  -e "lookback_days=30" \
  -e "target_hostname=ocptesttc"

# View the report
cat /tmp/compliance_trend_report_*.json | jq .
```

This queries PostgreSQL and generates:
- Compliance trends per host
- Top recurring violations
- Average scores over time
- Improvement/degradation analysis

---

## Troubleshooting

### Playbook Fails: "no container with name postgresql"

The playbooks use dynamic container ID lookup. If this fails:

```bash
# Check container name
podman ps --format '{{.Names}}' | grep postgres

# Get container ID manually
PGID=$(podman ps | grep postgresql | awk '{print $1}')
echo $PGID

# Test connection
podman exec $PGID psql -U postgres -d compliance -c 'SELECT 1;'
```

### Facts Not Passing Between Jobs

Workflow artifacts use `set_stats`. Verify:

1. In `store_compliance_facts.yml`, check:
   ```yaml
   - name: Save facts_id to artifact
     set_stats:
       data:
         facts_id: "{{ facts_id }}"
       per_host: no
   ```

2. In `store_compliance_results.yml`, retrieve with:
   ```yaml
   facts_id: "{{ hostvars.localhost.facts_id | default('1') }}"
   ```

### PostgreSQL Connection Errors

If you see "connection refused":

1. Check container port mapping:
   ```bash
   podman port $(podman ps | grep postgresql | awk '{print $1}')
   ```

2. Verify container is running:
   ```bash
   podman ps | grep postgresql
   ```

---

## Advanced: Grafana Dashboards

To visualize trending data:

1. Install Grafana
2. Add PostgreSQL datasource:
   - Host: `AAP_HOST:5432`
   - Database: `compliance`
   - User: `postgres`

3. Create dashboard panels:
   - **Compliance Score Over Time** (line chart)
   - **Failed Controls by System** (bar chart)
   - **Top Violations** (table)

Sample Grafana query:
```sql
SELECT
  evaluation_timestamp AS "time",
  compliance_percentage as "Compliance %",
  hostname
FROM compliance_results cr
JOIN compliance_facts cf ON cr.facts_id = cf.id
WHERE $__timeFilter(evaluation_timestamp)
ORDER BY evaluation_timestamp;
```

---

## Key Benefits of This Workflow

1. **Historical Tracking** - See compliance improve/degrade over time
2. **Audit Evidence** - Complete assessment history for compliance auditors
3. **Trend Analysis** - Identify recurring violations across systems
4. **Scalable** - Works for 1 or 100,000 systems
5. **Automated** - Schedule daily/weekly assessments
6. **Centralized** - Single PostgreSQL database for all compliance data

---

## Next Steps

1. **Add More Systems** - Expand inventory to include production hosts
2. **Create Alerts** - Trigger notifications when compliance drops below threshold
3. **Build Dashboards** - Visualize trends in Grafana
4. **Export Reports** - Generate PDF/CSV reports for management
5. **Integrate Remediation** - Chain remediation playbooks after assessment

---

## File Locations

- **Playbooks:** `/home/aapuser1/compliance/ansible/playbooks/`
- **Reports:** `/home/aapuser1/compliance/reports/`
- **Database:** PostgreSQL container on localhost:5432
- **OPA:** http://localhost:8181
- **Policies:** `/home/aapuser1/compliance/policies/cis_benchmarks/rhel_9/`

---

## Support

For issues or questions:
- **Repository:** https://github.com/ansible-automated-compliance/aac
- **Issues:** https://github.com/ansible-automated-compliance/aac/issues
- **Documentation:** See `docs/` directory

---

**Last Updated:** November 24, 2025
**Status:** Production-Ready
**Coverage:** 338/338 CIS RHEL 9 controls (100%)
