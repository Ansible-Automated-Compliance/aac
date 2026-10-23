> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: HOST:8181x6, RETIRED-HOSTx5, SPLIT-PORTSx2, AAP-2.5/2.6x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# CIS RHEL 9 Compliance Assessment - Quick Start Guide

> **Note (April 2026):** This guide predates the current architecture. AAP, OPA, and PostgreSQL all run on **AAP_HOST** (no longer on a separate database host). See `README.md` for the current setup and job template IDs.

This guide walks through running a CIS RHEL 9 compliance assessment using OPA and generating a compliance report.

## Prerequisites

- AAP, OPA, and Postgres running on `AAP_HOST` as user `aapuser1`
- Target RHEL 9 system accessible via SSH from `AAP_HOST`

## Architecture

```
AAP_HOST (aapuser1)
┌─────────────────────────────────────┐
│ AAP 2.6 Controller                  │
│ opa-security  (localhost:8181) CIS  │
│ opa-compliance (localhost:8182)     │
│ opa-ot        (localhost:8183)      │
│ PostgreSQL (compliance DB)          │
└─────────────┬───────────────────────┘
              │ SSH
              v
        RHEL 9 Target System
```

## Files Created

1. **Inventory**: `ansible/inventory/rhel9_test.yml`
   - Defines target host <TARGET_RHEL9_IP>
   - Configures connection parameters

2. **Playbook**: `ansible/playbooks/cis_rhel9_assessment.yml`
   - Gathers comprehensive facts from target system
   - Sends facts to OPA for validation
   - Generates compliance report

3. **Runner Script**: `run_cis_assessment.sh`
   - Automated script to run complete assessment
   - Checks OPA status
   - Loads CIS RHEL 9 policy into OPA
   - Executes Ansible playbook
   - Displays results

## Step-by-Step Instructions

### Step 1: SSH to the AAP Server

```bash
ssh aapuser1@AAP_HOST
cd /var/lib/awx/projects/_11__compliance_automation
```

### Step 2: Verify OPA is Running

```bash
# Check if OPA container is running
podman ps | grep opa

# Check OPA health
curl http://localhost:8181/health

# Expected output: {"status":"ok"}
```

### Step 3: Verify SSH Access to Target

```bash
# Test SSH connection to target RHEL 9 system
ssh aapuser1@<TARGET_RHEL9_IP> "hostname && cat /etc/redhat-release"

# Expected output:
# hostname of <TARGET_RHEL9_IP>
# Red Hat Enterprise Linux release 9.x
```

### Step 4: Run the Assessment

#### Option A: Using the Automated Script (Recommended)

```bash
# Make script executable (if not already)
chmod +x run_cis_assessment.sh

# Run the assessment
./run_cis_assessment.sh
```

The script will:
1. Verify OPA is running
2. Load the CIS RHEL 9 policy into OPA
3. Run the Ansible playbook
4. Display results and report location

#### Option B: Manual Execution

```bash
# 1. Load CIS RHEL 9 policy into OPA
curl -X PUT http://localhost:8181/v1/policies/cis_rhel_9 \
  --data-binary @policies/cis_benchmarks/rhel_9/cis_rhel_9.rego \
  -H "Content-Type: text/plain"

# 2. Verify policy loaded
curl http://localhost:8181/v1/policies/cis_rhel_9 | jq '.result'

# 3. Run Ansible playbook
cd ansible
ansible-playbook \
  -i inventory/rhel9_test.yml \
  playbooks/cis_rhel9_assessment.yml \
  -v
```

### Step 5: Review the Results

Reports are saved in the `reports/` directory:

```bash
# List generated reports
ls -lh reports/

# View the latest compliance report
LATEST_REPORT=$(ls -t reports/*_compliance_report_*.json | head -1)
cat $LATEST_REPORT | jq .

# View compliance summary
cat $LATEST_REPORT | jq '.compliance_summary'
```

## Understanding the Report

The compliance report contains:

### 1. Assessment Metadata
```json
{
  "assessment_metadata": {
    "hostname": "rhel9-test",
    "ip_address": "<TARGET_RHEL9_IP>",
    "assessment_time": "2024-11-04T13:30:00Z",
    "benchmark": "CIS Red Hat Enterprise Linux 9 Benchmark v1.0.0"
  }
}
```

### 2. System Information
```json
{
  "system_info": {
    "distribution": "RedHat",
    "distribution_version": "9.3",
    "kernel": "5.14.0-362.8.1.el9_3.x86_64",
    "architecture": "x86_64"
  }
}
```

### 3. Compliance Summary
```json
{
  "compliance_summary": {
    "is_compliant": false,
    "total_controls": 278,
    "total_violations": 45,
    "compliance_score": 83.81,
    "compliance_percentage": "83.81%"
  }
}
```

### 4. Violations List
```json
{
  "violations": [
    "1.1.1.1: Ensure mounting of squashfs filesystems is disabled",
    "1.1.2.2: Ensure nodev option set on /tmp partition",
    ...
  ]
}
```

## Compliance Scoring

- **Total Controls**: 278 CIS RHEL 9 controls
- **Compliance Score**: `((278 - violations) / 278) * 100`
- **Status**:
  - ✓ **COMPLIANT**: 0 violations (100%)
  - ✗ **NON-COMPLIANT**: 1+ violations (<100%)

## Viewing Results in Different Formats

### JSON (default)
```bash
cat reports/*_compliance_report_*.json | jq .
```

### Summary Only
```bash
cat reports/*_compliance_report_*.json | jq '.compliance_summary'
```

### Violations Only
```bash
cat reports/*_compliance_report_*.json | jq '.violations[]' | head -10
```

### Pretty Print
```bash
cat reports/*_compliance_report_*.json | jq -C . | less -R
```

## Storing Results in Database

To store results in Postgres (if database schema is set up):

```bash
# Connect to Postgres
podman exec -it compliance-demo-db psql -U compliance_user -d compliance_demo

# Example query to store report (simplified)
INSERT INTO compliance_assessments (hostname, assessment_time, compliance_score, violations_count)
VALUES ('rhel9-test', NOW(), 83.81, 45);
```

## Troubleshooting

### OPA Not Running
```bash
# Production: OPA containers are already running via AAP Template 28
# Demo only:
cd demo
podman-compose up -d opa-server

# Verify
curl http://localhost:8181/health
```

### SSH Connection Failed
```bash
# Test connection
ssh -v aapuser1@<TARGET_RHEL9_IP>

# Check SSH keys
ls -la ~/.ssh/

# Copy SSH key if needed
ssh-copy-id aapuser1@<TARGET_RHEL9_IP>
```

### Ansible Playbook Fails
```bash
# Run with increased verbosity
ansible-playbook \
  -i inventory/rhel9_test.yml \
  playbooks/cis_rhel9_assessment.yml \
  -vvv

# Test inventory
ansible -i inventory/rhel9_test.yml all -m ping
```

### Policy Not Loading
```bash
# Check policy syntax
opa check policies/cis_benchmarks/rhel_9/cis_rhel_9.rego

# Check OPA logs (production: opa-security / opa-compliance / opa-ot; demo: opa-demo-server)
podman logs opa-security

# Reload policy
curl -X PUT http://localhost:8181/v1/policies/cis_rhel_9 \
  --data-binary @policies/cis_benchmarks/rhel_9/cis_rhel_9.rego
```

## Next Steps

1. **Remediation**: Address violations found in the report
2. **Re-assessment**: Run assessment again after remediation
3. **Continuous Monitoring**: Schedule regular assessments
4. **Reporting**: Share reports with stakeholders
5. **Trend Analysis**: Compare reports over time

## Additional Resources

- **CIS Benchmarks**: See `policies/cis_benchmarks/rhel_9/`
- **Documentation**: See `docs/` directory
- **Examples**: See `examples/` directory
- **Main README**: See `README.md`

## Support

For issues or questions:
- Check documentation in `docs/`
- Review examples in `examples/`
- Check OPA logs (production): `podman logs opa-security` | `podman logs opa-compliance` | `podman logs opa-ot`
- Check Ansible output for error messages
