> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: none specific — unreviewed for 293 days.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Compliance Reporting Guide

**Authors:** Tim Coulter & Claude
**Date:** October 15, 2025


This guide shows you how to generate comprehensive compliance reports using our OPA policy framework.

## The findings workbook (start here for customer reporting)

For a report a control owner can act on and a manager can read, run the job
template **"AAC - Compliance Findings Workbook"** (registered on the
controller by `ansible/playbooks/seed_report_templates.yml`, which also seeds
the other report templates)
(`ansible/playbooks/compliance_findings_workbook.yml`) with `report_framework`
set to the framework key (`cis_m365_v7`, `cis_rhel9`, …). It reads the stored
evidence for the window, joins the framework's decisions file
(`ansible/vars/decisions/<framework>.yml`) and writes:

| Sheet | What it answers |
|---|---|
| Summary | posture verdict, counts, run provenance, delta headline |
| Findings | one row per control × subject: stable finding ID, risk (explainable), where to fix, owner, decision, expiry, delta, age, evidence row |
| Unassessable | what could not be confirmed, split by cause and by who acts (customer manual review vs vendor backlog) |
| Decisions | the decisions file joined to live findings, with expiry status and validation issues |
| Delta | new / fixed / regressed / still open against the previous run |
| Passed | controls that passed, with a sampled flag where the evidence rests on a sample |

Outputs: `.xlsx` (all sheets), one CSV per sheet, HTML, Markdown and JSON.
The column contract is published in
[`docs/operations/FINDINGS_WORKBOOK_CONTRACT.md`](FINDINGS_WORKBOOK_CONTRACT.md).
Evidence is never edited, decisions live only in the decisions file, and the
workbook is regenerated from the two after every run.

The framework-specific M365 report ("AAC - M365 CIS Findings Report") and the
generic F1/F2/F3 playbooks (risk scoring, mitigation guidance, closure report)
remain available; the workbook composes the same layers into one artifact.

## 🚀 Quick Start

### 1. Generate Complete Compliance Report
```bash
# Generate HTML report with sample data (recommended for demos)
make report

# Or manually:
python3 scripts/compliance_reporter.py --sample-data --output-format html
```

### 2. Framework-Specific Reports
```bash
# CIS Benchmarks only
make report-cis

# NIST frameworks only  
make report-nist

# ISO 27001 only
make report-iso27001

# Custom framework combination
python3 scripts/compliance_reporter.py --sample-data --frameworks cis nist_csf iso27001
```

### 3. Reports with Real Data
```bash
# Use Ansible-gathered data
ansible-playbook examples/iso27001-ansible-playbook.yml
make report-with-data INPUT_FILE=reports/iso27001-data.json

# Use custom input file
make report-with-data INPUT_FILE=my-system-data.json
```

## 📊 Report Formats

### HTML Reports (Recommended)
- **Executive dashboard** with visual compliance scores
- **Detailed breakdown** by framework and control category
- **Interactive charts** and progress bars
- **Actionable recommendations** prioritized by impact
- **Cross-framework analysis** showing control alignment

```bash
python3 scripts/compliance_reporter.py --sample-data --output-format html
```

### JSON Reports (API Integration)
- **Machine-readable** format for automation
- **Complete technical details** including OPA evaluation results
- **Structured data** for integration with SIEM/GRC tools
- **Timestamped results** for trend analysis

```bash
python3 scripts/compliance_reporter.py --sample-data --output-format json
```

### CSV Reports (Spreadsheet Analysis)
- **Tabular format** for Excel/Google Sheets
- **Summary metrics** by framework
- **Compliance percentages** and recommendation counts
- **Executive reporting** friendly format

```bash
python3 scripts/compliance_reporter.py --sample-data --output-format csv
```

## 🔍 Understanding Report Output

### Executive Summary
```
📊 EXECUTIVE SUMMARY
==================================================
Overall Compliance: 85.2%
Status: COMPLIANT
Compliant Frameworks: 4/6

📋 Framework Breakdown:
  ✅ CIS Benchmarks: 92.1%
  ✅ NIST CSF 2.0: 88.7%
  ✅ NIST SP 800-53: 81.3%
  ❌ ISO 27001:2022: 76.8%
```

### Detailed Framework Results
Each framework section includes:
- **Compliance percentage** for overall framework
- **Control-by-control breakdown** showing pass/fail status
- **Technical findings** with specific configuration issues
- **Recommendations** prioritized by security impact

### Cross-Framework Analysis
- **Common control areas** (access control, cryptography, monitoring)
- **Alignment scores** showing consistency across frameworks
- **Gap analysis** identifying areas needing attention
- **Efficiency opportunities** for multi-framework compliance

## 🛠️ Integration with Ansible

### Automated Data Collection
```bash
# Run Ansible playbook to collect system data
ansible-playbook examples/cis-ansible-playbook.yml
ansible-playbook examples/iso27001-ansible-playbook.yml

# Generate report with collected data
python3 scripts/compliance_reporter.py \
  --input-file /var/log/compliance/system-data.json \
  --output-format html
```

### Sample Input Data Structure
```json
{
  "timestamp": "2024-10-01T12:00:00Z",
  "hostname": "web-server-01",
  "os_family": "RedHat",
  "distribution": "CentOS",
  "selinux_status": "enforcing",
  "firewall_enabled": true,
  "ssh_config": ["Protocol 2", "PermitRootLogin no"],
  "access_control": {
    "policy": {
      "documented": true,
      "approved": true
    }
  }
}
```

## 📈 Continuous Monitoring

### Scheduled Reporting
```bash
# Add to crontab for daily reports
0 6 * * * cd /path/to/opa-cis-demo && make report >/dev/null 2>&1

# Weekly comprehensive assessment
0 6 * * 1 cd /path/to/opa-cis-demo && make full-check && make report
```

### CI/CD Integration
The reports integrate with our GitHub Actions workflow:
```yaml
- name: Generate Compliance Report
  run: |
    python3 scripts/compliance_reporter.py --sample-data --output-format json
    python3 scripts/compliance_reporter.py --sample-data --output-format html
    
- name: Upload Reports
  uses: actions/upload-artifact@v4
  with:
    name: compliance-reports
    path: reports/
```

## 🎯 Use Cases

### 1. Executive Reporting
```bash
# Generate executive-friendly HTML report
make report
make compliance-dashboard  # Opens in browser
```

### 2. Audit Preparation
```bash
# Generate comprehensive evidence package
make report-json  # Technical details
make report-csv   # Summary for auditors
make report       # Visual presentation
```

### 3. DevSecOps Integration
```bash
# Automated compliance checks in pipeline
python3 scripts/compliance_reporter.py \
  --input-file $SYSTEM_DATA \
  --frameworks cis nist_sp800_53 \
  --output-format json | jq '.executive_summary.overall_compliance_score'
```

### 4. Risk Assessment
```bash
# Focus on specific high-risk areas
python3 scripts/compliance_reporter.py \
  --frameworks iso27001 \
  --output-format html
```

## 🔧 Customization

### Custom Input Data
Create a JSON file with your system's actual configuration:
```json
{
  "collected_by": "ansible",
  "collection_date": "2024-10-01T12:00:00Z",
  "systems": [{
    "hostname": "prod-web-01",
    "selinux_status": "enforcing",
    "firewall_enabled": true,
    "ssh_root_disabled": true,
    "disk_encryption": true,
    "backup_configured": true,
    "logging_centralized": true
  }]
}
```

### Framework Selection
Choose specific frameworks based on your compliance requirements:
```bash
# SOC 2 Type II focus (NIST frameworks)
python3 scripts/compliance_reporter.py \
  --frameworks nist_csf nist_sp800_53 nist_sp800_171

# International compliance (ISO + NIST)  
python3 scripts/compliance_reporter.py \
  --frameworks iso27001 nist_csf

# Government/Defense (CIS + NIST)
python3 scripts/compliance_reporter.py \
  --frameworks cis nist_sp800_53 nist_sp800_171
```

## 📋 Report Contents

### HTML Report Sections
1. **Header**: System info, timestamp, frameworks evaluated
2. **Executive Summary**: Overall compliance score and status
3. **Framework Details**: Individual framework breakdowns
4. **Control Matrix**: Cross-framework control mapping
5. **Recommendations**: Prioritized action items
6. **Technical Appendix**: Detailed findings and evidence

### Key Metrics Tracked
- **Compliance Percentage**: Overall and per-framework scores
- **Control Coverage**: Number of controls evaluated vs. implemented
- **Risk Score**: Weighted by control criticality and impact
- **Trend Analysis**: Compliance improvements over time
- **Gap Analysis**: Missing controls and implementation priorities

## 🚨 Troubleshooting

### Common Issues
```bash
# OPA not found
which opa  # Should return path to OPA binary
# Install: https://www.openpolicyagent.org/docs/latest/#running-opa

# Python dependencies missing
pip3 install -r requirements.txt  # If requirements.txt exists

# No input data
python3 scripts/compliance_reporter.py --sample-data  # Use sample data

# Permission errors
chmod +x scripts/*.py  # Make scripts executable
```

### Validation
```bash
# Test OPA policies
make test

# Validate individual frameworks
make test-unit

# Check policy syntax
make check-syntax
```

## 🔄 Integration Examples

### With SIEM Tools
```bash
# Generate JSON for Splunk/ELK ingestion
python3 scripts/compliance_reporter.py \
  --input-file system-data.json \
  --output-format json \
  --output-file compliance-$(date +%Y%m%d)

# Upload to centralized logging
curl -X POST "https://siem.company.com/api/compliance" \
  -H "Content-Type: application/json" \
  -d @reports/compliance-$(date +%Y%m%d).json
```

### With GRC Platforms
```bash
# Generate compliance evidence
make report-csv  # For ServiceNow GRC
make report-json # For custom GRC integrations
make report      # For compliance dashboards
```

This reporting framework provides comprehensive visibility into your compliance posture across multiple frameworks, with actionable insights for maintaining and improving your security stance.