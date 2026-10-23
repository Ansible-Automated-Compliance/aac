> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx34, HOST:8181x4.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# AAP Integration Guide - Compliance System
## Ansible Automation Platform Configuration

**Last Updated**: April 2026
**AAP Version**: 2.6 (Containerized)
**AAP Host**: AAP_HOST
**Repository**: github.com:ansible-automated-compliance/aac

---

## Overview

This guide provides step-by-step instructions to integrate AAP with the OPA compliance automation system, including:
1. GitHub repository integration
2. Project creation
3. Inventory configuration
4. Credential setup
5. Job template creation
6. Workflow templates

---

## Prerequisites

### 1. AAP Access
- **URL**: https://AAP_HOST
- **Admin User**: admin
- **Password**: (from `/tmp/aap_inventory` file)

### 2. GitHub Repository
- **Repository**: github.com:ansible-automated-compliance/aac
- **Branch**: main
- **Playbooks Path**: `/playbooks/`
- **Access**: Public or private (with credentials)

### 3. System Requirements
- Passwordless sudo configured for `tcoulter`
- PostgreSQL database operational (containerized)
- OPA server running (port 8181)

---

## Part 1: GitHub Integration

### Step 1: Create GitHub Credentials (if private repo)

**If your repository is private, you'll need to create credentials:**

1. **Log into AAP**:
   ```
   https://AAP_HOST
   Username: admin
   Password: <from aap_inventory>
   ```

2. **Navigate to Credentials**:
   - Left menu → **Resources** → **Credentials**
   - Click **Add** button

3. **Configure GitHub Credential**:
   - **Name**: `GitHub Compliance Repo`
   - **Description**: `Access to ansible-automated-compliance/aac repository`
   - **Organization**: Default
   - **Credential Type**: `Source Control`

4. **Authentication Method** (choose one):

   **Option A: Personal Access Token (Recommended)**
   - **Username**: `your_github_username`
   - **Password**: `<GitHub Personal Access Token>`
   - **SCM Private Key**: (leave empty)

   To create GitHub token:
   ```
   1. Go to: https://github.com/settings/tokens
   2. Click "Generate new token (classic)"
   3. Name: "AAP Compliance Integration"
   4. Scopes: Select "repo" (full control of private repositories)
   5. Click "Generate token"
   6. Copy the token immediately (it won't be shown again)
   ```

   **Option B: SSH Key**
   - **Username**: `git`
   - **SCM Private Key**:
     ```bash
     # Generate SSH key on AAP server
     ssh AAP_HOST
     sudo -u aapuser1 ssh-keygen -t ed25519 -C "aap@AAP_HOST" -f ~/.ssh/id_aap_github

     # Display public key (add to GitHub)
     sudo -u aapuser1 cat ~/.ssh/id_aap_github.pub

     # Display private key (paste into AAP credential)
     sudo -u aapuser1 cat ~/.ssh/id_aap_github
     ```

   Then add public key to GitHub:
   ```
   1. Go to: https://github.com/settings/keys
   2. Click "New SSH key"
   3. Title: "AAP Server AAP_HOST"
   4. Paste public key
   5. Click "Add SSH key"
   ```

5. **Click Save**

---

## Part 2: Create AAP Project

### Step 2: Create Project for Compliance Playbooks

1. **Navigate to Projects**:
   - Left menu → **Resources** → **Projects**
   - Click **Add** button

2. **Configure Project**:
   - **Name**: `Compliance Automation`
   - **Description**: `OPA-based compliance automation playbooks and policies`
   - **Organization**: Default
   - **Execution Environment**: `Default execution environment`
   - **Source Control Type**: `Git`

3. **Source Control Details**:

   **For Public Repository**:
   ```
   Source Control URL: https://github.com/ansible-automated-compliance/aac.git
   Source Control Branch/Tag/Commit: main
   Source Control Credential: (leave empty)
   ```

   **For Private Repository**:
   ```
   Source Control URL: https://github.com/ansible-automated-compliance/aac.git
   # OR
   Source Control URL: https://github.com/ansible-automated-compliance/aac.git

   Source Control Branch/Tag/Commit: main
   Source Control Credential: GitHub Compliance Repo
   ```

4. **Options** (check these boxes):
   - ✅ **Clean**: Delete any local modifications prior to performing an update
   - ✅ **Delete**: Delete the local repository before performing an update
   - ✅ **Update Revision on Launch**: Update the revision before running any job

5. **Click Save**

6. **Sync Project**:
   - After saving, click the **Sync** button (circular arrows icon)
   - Wait for sync to complete (status shows green checkmark)
   - Verify: Last Job Status should show "Successful"

---

## Part 3: Configure Inventory

### Step 3: Create Compliance Hosts Inventory

1. **Navigate to Inventories**:
   - Left menu → **Resources** → **Inventories**
   - Click **Add** → **Add inventory**

2. **Configure Inventory**:
   - **Name**: `Compliance Hosts`
   - **Description**: `RHEL systems for CIS compliance scanning`
   - **Organization**: Default
   - **Instance Groups**: (leave default)
   - **Variables**: (leave empty for now)

3. **Click Save**

### Step 4: Add Host to Inventory

1. **Within the Compliance Hosts inventory**:
   - Click **Hosts** tab
   - Click **Add** button

2. **Configure Host**:
   - **Name**: `AAP_HOST`
   - **Description**: `Primary RHEL 9 system (ocptesttc)`
   - **Variables** (YAML format):
     ```yaml
     ---
     ansible_host: AAP_HOST
     ansible_user: tcoulter
     ansible_python_interpreter: /usr/bin/python3
     platform_type: rhel
     ```

3. **Click Save**

### Step 5: Create Groups (Optional but Recommended)

1. **Click Groups tab**:
   - Click **Add** button

2. **Create RHEL Hosts Group**:
   - **Name**: `rhel_hosts`
   - **Description**: `All RHEL systems`
   - **Variables**:
     ```yaml
     ---
     platform_type: rhel
     ansible_python_interpreter: /usr/bin/python3
     ```

3. **Click Save**

4. **Add Host to Group**:
   - Select the `rhel_hosts` group
   - Click **Hosts** tab
   - Click **Add** → **Add existing host**
   - Select `AAP_HOST`
   - Click **Save**

---

## Part 4: Configure Credentials

### Step 6: Create Machine Credential (SSH)

1. **Navigate to Credentials**:
   - Left menu → **Resources** → **Credentials**
   - Click **Add** button

2. **Configure SSH Credential**:
   - **Name**: `tcoulter SSH - AAP_HOST`
   - **Description**: `SSH access with passwordless sudo for compliance scanning`
   - **Organization**: Default
   - **Credential Type**: `Machine`

3. **Type Details**:
   - **Username**: `tcoulter`
   - **Password**: (leave empty - using SSH keys)
   - **SSH Private Key**:
     ```bash
     # Get SSH private key from your local machine
     cat ~/.ssh/id_rsa
     # OR
     cat ~/.ssh/id_ed25519

     # Copy the entire private key content (stored in Ansible Vault)
     # Key is stored in vault_secrets.yml via: ansible-vault encrypt_string
     ```
   - **Private Key Passphrase**: (if your SSH key has a passphrase)
   - **Privilege Escalation Method**: `sudo`
   - **Privilege Escalation Username**: (leave empty - defaults to root)
   - **Privilege Escalation Password**: (leave empty - passwordless sudo configured)

4. **Click Save**

### Step 7: Test Credential (Manual Test)

```bash
# From your local machine
ssh -i ~/.ssh/id_rsa tcoulter@AAP_HOST "sudo -n whoami"
# Should return: root

# If this fails, passwordless sudo is not configured correctly
# Re-run the setup script:
ssh AAP_HOST
sudo bash /tmp/setup_passwordless_sudo.sh
```

---

## Part 5: Create Job Templates

### Step 8: Create Facts Collection Job Template

1. **Navigate to Templates**:
   - Left menu → **Resources** → **Templates**
   - Click **Add** → **Add job template**

2. **Configure Job Template**:
   - **Name**: `CIS Facts Collection - RHEL`
   - **Description**: `Collect CIS benchmark facts and store in PostgreSQL database`
   - **Job Type**: `Run`
   - **Inventory**: `Compliance Hosts`
   - **Project**: `Compliance Automation`
   - **Execution Environment**: `Default execution environment`
   - **Playbook**: `playbooks/collect_and_store_cis_facts_rhel.yml`
   - **Credentials**:
     - Click **Select** → Choose `tcoulter SSH - AAP_HOST`
   - **Variables** (YAML format):
     ```yaml
     ---
     postgres_host: localhost
     postgres_port: 5432
     postgres_db: compliance
     postgres_user: compliance_writer
     postgres_password: "{{ vault_pg_password }}"  # Required: set via Ansible Vault
     ```

3. **Options** (check these):
   - ✅ **Privilege Escalation**: Enabled
   - ✅ **Enable Webhook**: (optional - for GitHub webhook triggers)

4. **Click Save**

### Step 9: Create OPA Evaluation Job Template

1. **Create new Job Template**:
   - Click **Add** → **Add job template**

2. **Configure**:
   - **Name**: `OPA Compliance Evaluation`
   - **Description**: `Run OPA evaluation on collected facts`
   - **Job Type**: `Run`
   - **Inventory**: `Compliance Hosts`
   - **Project**: `Compliance Automation`
   - **Execution Environment**: `Default execution environment`
   - **Playbook**: `playbooks/opa_evaluation.yml`

   **Note**: You'll need to create this playbook (see below)

   - **Credentials**: `tcoulter SSH - AAP_HOST`
   - **Variables**:
     ```yaml
     ---
     opa_url: http://localhost:8181
     postgres_host: localhost
     postgres_db: compliance
     policy_name: cis_rhel9
     ```

3. **Options**:
   - ✅ **Privilege Escalation**: Enabled

4. **Click Save**

---

## Part 6: Create Workflow Template (Advanced)

### Step 10: Create End-to-End Compliance Workflow

1. **Navigate to Templates**:
   - Left menu → **Resources** → **Templates**
   - Click **Add** → **Add workflow template**

2. **Configure Workflow**:
   - **Name**: `Complete Compliance Scan - CIS RHEL 9`
   - **Description**: `Collect facts → Evaluate with OPA → Generate report`
   - **Organization**: Default
   - **Inventory**: `Compliance Hosts`
   - **Variables**:
     ```yaml
     ---
     target_hostname: AAP_HOST
     policy_name: cis_rhel9
     ```

3. **Click Save**

4. **Build Workflow** (in Visualizer):
   - Click **Visualizer** tab
   - Click **Start** button

   **Node 1: Facts Collection**
   - Click **+** on Start
   - **Node Type**: Job Template
   - **Job Template**: `CIS Facts Collection - RHEL`
   - **Convergence**: Any
   - Click **Save**

   **Node 2: OPA Evaluation**
   - Click **+** on "CIS Facts Collection - RHEL" node
   - **Run**: On Success
   - **Node Type**: Job Template
   - **Job Template**: `OPA Compliance Evaluation`
   - Click **Save**

   **Node 3: Notification (Optional)**
   - Click **+** on "OPA Compliance Evaluation" node
   - **Run**: Always
   - **Node Type**: Job Template
   - **Job Template**: (notification job if you have one)
   - Click **Save**

5. **Save Workflow**

---

## Part 7: Additional Playbooks Needed

### Create OPA Evaluation Playbook

You need to create this playbook in your GitHub repo:

**File**: `playbooks/opa_evaluation.yml`

```yaml
---
# OPA Compliance Evaluation Playbook
# Runs OPA evaluation on facts stored in PostgreSQL

- name: Run OPA Compliance Evaluation
  hosts: AAP_HOST
  gather_facts: no
  become: yes

  vars:
    opa_url: "{{ opa_url | default('http://localhost:8181') }}"
    postgres_host: "{{ postgres_host | default('localhost') }}"
    postgres_db: "{{ postgres_db | default('compliance') }}"
    policy_name: "{{ policy_name | default('cis_rhel9') }}"
    target_hostname: "{{ ansible_hostname | default('ocptesttc') }}"

  tasks:
    - name: Display evaluation parameters
      debug:
        msg:
          - "Running OPA evaluation for: {{ target_hostname }}"
          - "Policy: {{ policy_name }}"
          - "OPA URL: {{ opa_url }}"

    - name: Check if OPA is running
      uri:
        url: "{{ opa_url }}/health"
        method: GET
        status_code: 200
      register: opa_health

    - name: Run OPA evaluation script
      command: python3 /tmp/opa_eval_from_db.py {{ target_hostname }} {{ policy_name }}
      register: opa_result
      changed_when: false

    - name: Display evaluation results
      debug:
        msg: "{{ opa_result.stdout_lines }}"

    - name: Check for evaluation errors
      fail:
        msg: "OPA evaluation failed"
      when: opa_result.rc != 0
```

**Commit and push to GitHub**:
```bash
cd /path/to/compliance/repo
git add playbooks/opa_evaluation.yml
git commit -m "Add OPA evaluation playbook for AAP integration"
git push origin main
```

---

## Part 8: Testing the Integration

### Step 11: Test Facts Collection Job

1. **Navigate to Templates**:
   - Select `CIS Facts Collection - RHEL`
   - Click **Launch** button (rocket icon)

2. **Verify Job Execution**:
   - Watch the job output in real-time
   - Should show:
     - ✅ Ansible connecting to AAP_HOST
     - ✅ Gathering facts
     - ✅ Storing facts in PostgreSQL
     - ✅ Play recap showing success

3. **Verify in Database**:
   ```bash
   ssh AAP_HOST
   cd /tmp
   sudo -u aapuser1 podman exec postgresql psql -U postgres -d compliance -c \
     "SELECT id, hostname, collection_timestamp FROM compliance_facts ORDER BY collection_timestamp DESC LIMIT 5;"
   ```

### Step 12: Test OPA Evaluation Job

1. **Launch OPA Evaluation Job**:
   - Select `OPA Compliance Evaluation`
   - Click **Launch**

2. **Verify Execution**:
   - Check job output
   - Should show compliance percentage
   - Should show violations stored

3. **Verify Results in Database**:
   ```bash
   ssh AAP_HOST
   cd /tmp
   sudo -u aapuser1 podman exec postgresql psql -U postgres -d compliance << 'EOF'
   SELECT
     cf.hostname,
     cr.policy_name,
     cr.compliance_percentage,
     cr.passed_controls,
     cr.failed_controls,
     cr.evaluation_timestamp
   FROM compliance_results cr
   JOIN compliance_facts cf ON cr.facts_id = cf.id
   ORDER BY cr.evaluation_timestamp DESC
   LIMIT 5;
   EOF
   ```

### Step 13: Test Complete Workflow

1. **Launch Workflow**:
   - Select `Complete Compliance Scan - CIS RHEL 9`
   - Click **Launch**

2. **Watch Workflow Progress**:
   - Visualizer shows each step executing
   - Facts Collection → Success (green)
   - OPA Evaluation → Success (green)

3. **Review Output**:
   - Click on each completed job in workflow
   - Review stdout for each step
   - Verify no errors

---

## Part 9: Schedule Automated Scans

### Step 14: Create Schedule for Daily Scans

1. **Navigate to Templates**:
   - Select `Complete Compliance Scan - CIS RHEL 9` workflow

2. **Create Schedule**:
   - Click **Schedules** tab
   - Click **Add** button

3. **Configure Schedule**:
   - **Name**: `Daily CIS Compliance Scan`
   - **Description**: `Run full compliance scan daily at 2 AM`
   - **Start Date/Time**: Select tomorrow's date at 02:00
   - **Local Time Zone**: Select your timezone
   - **Repeat frequency**: `Daily`
   - **Run every**: `1 day`
   - **On days**: Every day
   - **End**: Never

4. **Variables** (optional overrides):
   ```yaml
   ---
   # Override any workflow variables here
   ```

5. **Click Save**

---

## Part 10: GitHub Webhook Integration (Optional)

### Step 15: Configure GitHub Webhook for Auto-Updates

This allows GitHub to notify AAP when code changes, triggering auto-sync.

1. **Get Webhook URL from AAP**:
   - In AAP, go to **Projects**
   - Select `Compliance Automation`
   - Copy the **Webhook URL** (if available)

2. **Configure in GitHub**:
   - Go to: https://github.com/ansible-automated-compliance/aac/settings/hooks
   - Click **Add webhook**
   - **Payload URL**: (paste AAP webhook URL)
   - **Content type**: `application/json`
   - **Secret**: (webhook secret from AAP)
   - **Events**: Select `Just the push event`
   - Click **Add webhook**

3. **Enable in AAP Project**:
   - Projects → `Compliance Automation`
   - Check: ✅ **Update Revision on Launch**
   - Save

Now, when you push to GitHub, AAP will automatically sync the project.

---

## Part 11: Troubleshooting

### Common Issues and Solutions

#### Issue 1: Project Sync Fails

**Symptoms**: Red X on project sync status

**Solutions**:
```bash
# Check if AAP can reach GitHub
ssh AAP_HOST
sudo -u aapuser1 curl -I https://github.com

# Check DNS resolution
sudo -u aapuser1 nslookup github.com

# Check if credential is correct
# Re-create credential with correct token/key

# Check AAP logs
ssh AAP_HOST
sudo -u aapuser1 podman logs awx_task 2>&1 | grep -i error
```

#### Issue 2: Job Fails - SSH Connection

**Symptoms**: "Failed to connect to host"

**Solutions**:
```bash
# Test SSH connection manually
ssh -i ~/.ssh/id_rsa tcoulter@AAP_HOST

# Verify SSH key in AAP credential matches
# Check /var/log/secure on target for SSH errors
ssh AAP_HOST
sudo tail -f /var/log/secure

# Verify ansible_host variable in inventory
# Check firewall rules
```

#### Issue 3: Job Fails - Sudo Permission Denied

**Symptoms**: "sudo: a password is required"

**Solutions**:
```bash
# Re-verify passwordless sudo
ssh AAP_HOST "sudo -n whoami"

# Check sudoers file
ssh AAP_HOST
sudo cat /etc/sudoers.d/tcoulter

# Re-run setup if needed
sudo bash /tmp/setup_passwordless_sudo.sh
```

#### Issue 4: Playbook Not Found

**Symptoms**: "Could not find playbook"

**Solutions**:
```bash
# Verify playbook exists in GitHub repo
# Check path in job template matches repo structure
# Sync project again (click sync button)

# Check AAP project directory
ssh AAP_HOST
sudo -u aapuser1 ls -la /var/lib/awx/projects/
```

#### Issue 5: Database Connection Fails

**Symptoms**: "could not connect to server"

**Solutions**:
```bash
# Verify PostgreSQL container is running
ssh AAP_HOST
sudo -u aapuser1 podman ps | grep postgresql

# Verify database is accessible
sudo -u aapuser1 podman exec postgresql psql -U postgres -d compliance -c "SELECT 1;"

# Check variables in job template
# Ensure postgres_host: localhost (not AAP_HOST)
```

---

## Part 12: Best Practices

### Security Best Practices

1. **Change Default Passwords**:
   ```bash
   # On AAP_HOST
   sudo -u aapuser1 podman exec postgresql psql -U postgres -d compliance << 'EOF'
   ALTER USER compliance_writer WITH PASSWORD 'new_secure_password';
   ALTER USER compliance_reader WITH PASSWORD 'new_secure_password';
   EOF
   ```

2. **Use AAP Credentials for Secrets**:
   - Store DB passwords in AAP credentials, not in plain text
   - Use credential injection in job templates

3. **Rotate SSH Keys Regularly**:
   - Generate new SSH key every 90 days
   - Update AAP credential

4. **Enable Audit Logging**:
   - AAP logs all job executions
   - Review logs periodically

### Operational Best Practices

1. **Version Control Everything**:
   - All playbooks in Git
   - Tag releases (v1.0, v1.1, etc.)
   - Use branches for testing

2. **Test in Dev First**:
   - Create separate inventory for dev/test
   - Test changes before running in prod

3. **Monitor Job Success Rates**:
   - Check AAP dashboard regularly
   - Set up notifications for failures

4. **Backup AAP Configuration**:
   ```bash
   # Export AAP configuration
   awx-manage export --all > /tmp/aap_backup.json
   ```

---

## Part 13: Quick Reference

### Essential URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| AAP Web UI | https://AAP_HOST | admin / (from aap_inventory) |
| GitHub Repo | https://github.com/ansible-automated-compliance/aac | (your GitHub account) |
| OPA Server | http://AAP_HOST:8181 | (no auth) |
| PostgreSQL | localhost:5432 | postgres / (local only) |

### Key AAP Commands (CLI)

```bash
# SSH to AAP server
ssh AAP_HOST

# Check AAP containers
sudo -u aapuser1 podman ps

# View AAP logs
sudo -u aapuser1 podman logs awx_task
sudo -u aapuser1 podman logs awx_web

# Restart AAP (if needed)
sudo -u aapuser1 podman restart awx_task awx_web

# Backup AAP database
sudo -u aapuser1 podman exec postgresql pg_dump -U awx awx > /tmp/aap_backup.sql
```

### Common Workflow

**Daily Operations**:
1. Log into AAP: https://AAP_HOST
2. Check dashboard for job status
3. Review any failed jobs
4. Launch manual scans if needed

**After Code Changes**:
1. Push to GitHub
2. AAP auto-syncs project (if webhook configured)
3. Test job template with new code
4. Schedule/run production jobs

**Monthly Maintenance**:
1. Review audit logs
2. Check database size
3. Backup compliance database
4. Update playbooks as needed

---

## Part 14: Next Steps

### After Integration Complete

1. **✅ Extend to More Hosts**:
   - Add additional RHEL systems to inventory
   - Run facts collection across fleet
   - Compare compliance across systems

2. **✅ Add More Policies**:
   - NIST 800-53
   - PCI-DSS
   - HIPAA
   - SOC 2

3. **✅ Create Dashboards**:
   - Grafana dashboard for compliance trends
   - Query PostgreSQL compliance_trends view
   - Visualize compliance over time

4. **✅ Automated Remediation**:
   - Create remediation playbooks
   - Link to violations
   - Auto-fix common issues

5. **✅ Reporting**:
   - Weekly compliance reports
   - Email notifications
   - Export to PDF/CSV

---

## Support

**Documentation References**:
- Main README: `<aac-repo>/COMPLIANCE_SYSTEM_README.md`
- OPA Scaling Guide: `<docs-dir>/OPA_SCALING_GUIDE.md`
- This Guide: `<aac-repo>/AAP_INTEGRATION_GUIDE.md`

**Troubleshooting**:
- Check AAP logs: `sudo -u aapuser1 podman logs awx_task`
- Check PostgreSQL: `sudo -u aapuser1 podman logs postgresql`
- Check OPA: `curl http://AAP_HOST:8181/health`

**Repository**: github.com:ansible-automated-compliance/aac

---

*Last Updated: April 2026*
*Maintained by: Claude & Tim Coulter*
