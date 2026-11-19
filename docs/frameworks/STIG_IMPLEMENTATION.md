> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: HOST:8181x5, RETIRED-HOSTx1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# DISA STIG Implementation Guide

**Author:** Tim Coulter & Claude
**Date:** November 24, 2025
**Repository:** ansible-automated-compliance/aac

---

## Overview

**DISA STIG (Security Technical Implementation Guide)** compliance policies for Department of Defense (DoD) and federal systems. Each module evaluates a subset of its STIG (see the measured table below). Covers **6 operating systems** with automated assessment via OPA and Ansible.

### What is STIG?

**STIG** = Security Technical Implementation Guide
- **Publisher:** Defense Information Systems Agency (DISA)
- **Mandatory For:** All DoD information systems
- **Use Cases:** Military systems, federal agencies, defense contractors, classified systems

---

## Supported Operating Systems

| OS | Rules the module evaluates | Status |
|----|----------------------------|--------|
| **Windows Server 2022** | 103 | Assessed |
| **Windows Server 2019** | 104 | Assessed |
| **Windows Server 2016** | 103 | Assessed |
| **Windows 11** | 117 | Assessed |
| **Windows 10** | none | No module in the pinned library |
| **RHEL 9** | 104 | Assessed |
| **RHEL 8** | 53 | Assessed |
| **Ubuntu 20.04 LTS** | none reported | Module has no assessment report |

Measured 2026-11-18 at library commit `a84e39cf`: each number is the module's own
`total_controls`. Every module is a subset of its STIG; a full DISA STIG for these
platforms has several hundred rules. Earlier versions of this table gave figures of
"~280+" to "~320+" per platform and a STIG release for each; neither was measured.

---

## STIG Severity Categories

### CAT I - High Severity
- **Risk:** Immediate threat to system security
- **Examples:** Missing antivirus, disabled firewalls, unpatched critical vulnerabilities
- **Remediation:** Must be fixed immediately (typically within 15 days)

### CAT II - Medium Severity
- **Risk:** Significant security vulnerability
- **Examples:** Weak password policies, improper audit settings, insecure configurations
- **Remediation:** Must be remediated within 30 days

### CAT III - Low Severity
- **Risk:** Lower-impact security issues
- **Examples:** Missing legal banners, suboptimal log sizes, minor config issues
- **Remediation:** Should be fixed within 90 days

---

## Directory Structure

```
policies/stig/
├── windows_server_2022/
│   ├── cat_i_findings.rego          # CAT I (high) findings
│   ├── cat_ii_findings.rego         # High severity findings
│   ├── cat_iii_findings.rego        # Medium severity findings
│   └── stig_windows_server_2022_complete.rego  # Master orchestrator
│
├── windows_server_2019/
│   └── [same structure]
│
├── windows_server_2016/
│   └── [same structure]
│
├── windows_11/
│   └── [same structure]
│
├── windows_10/
│   └── [same structure]
│
├── rhel_9/
│   └── stig_rhel9_complete.rego     # Complete RHEL 9 STIG
│
├── rhel_8/
│   └── stig_rhel8_complete.rego     # Complete RHEL 8 STIG
│
└── ubuntu_20_04/
    └── stig_ubuntu_20_04_complete.rego  # Complete Ubuntu 20.04 STIG
```

---

## Quick Start

### 1. Load STIG Policies into OPA

```bash
# SSH to AAP server
ssh aapuser1@AAP_HOST

# Load Windows Server 2022 STIG
cd ~/compliance/policies/stig/windows_server_2022
for policy in *.rego; do
  curl -X PUT --data-binary @$policy \
    http://localhost:8181/v1/policies/stig_win2022_${policy}
done

# Load RHEL 9 STIG
cd ~/compliance/policies/stig/rhel_9
curl -X PUT --data-binary @stig_rhel9_complete.rego \
  http://localhost:8181/v1/policies/stig_rhel9_complete.rego

# Verify loaded
curl http://localhost:8181/v1/policies | jq '.result[].id' | grep stig
```

### 2. Test STIG Assessment

```bash
# Query Windows Server 2022 STIG
curl -s -X POST http://localhost:8181/v1/data/stig/windows_server_2022/stig_assessment \
  -H 'Content-Type: application/json' \
  -d '{
    "input": {
      "system_info": {
        "hostname": "win-server-01",
        "os_version": "10.0.20348",
        "domain": "example.com"
      },
      "password_policy": {
        "password_history_size": 24,
        "maximum_password_age": 60,
        "minimum_password_age": 1,
        "minimum_password_length": 14,
        "complexity_enabled": true
      },
      "windows_defender": {
        "antivirus_enabled": true
      }
    }
  }' | jq

# Query RHEL 9 STIG
curl -s -X POST http://localhost:8181/v1/data/stig/rhel_9/stig_assessment \
  -H 'Content-Type: application/json' \
  -d '{
    "input": {
      "system_info": {
        "hostname": "rhel9-server-01",
        "support_status": "active"
      },
      "packages": {
        "aide_installed": true
      }
    }
  }' | jq
```

---

## Example Output

### STIG Assessment Report

```json
{
  "assessment_metadata": {
    "stig_title": "Windows Server 2022 Security Technical Implementation Guide",
    "stig_version": "Version 2, Release 1",
    "classification": "UNCLASSIFIED",
    "hostname": "win-server-01",
    "assessment_date": 1732464000000000000
  },
  "compliance_summary": {
    "overall_status": "Non-Compliant",
    "compliant": false,
    "compliance_percentage": 87,
    "risk_level": "High",
    "total_checks": 35,
    "open_findings": 5,
    "not_a_finding": 30
  },
  "severity_breakdown": {
    "cat_i": {
      "severity": "High",
      "total": 9,
      "open": 1,
      "compliant": false
    },
    "cat_ii": {
      "severity": "Medium",
      "total": 16,
      "open": 3,
      "compliant": false
    },
    "cat_iii": {
      "severity": "Low",
      "total": 10,
      "open": 1,
      "compliant": false
    }
  },
  "open_findings_details": [
    {
      "vuln_id": "V-254442",
      "stig_id": "WN22-PK-000010",
      "severity": "CAT II",
      "rule_title": "Windows Server 2022 must have the DoD Root CA certificates installed",
      "status": "Open"
    }
  ]
}
```

---

## Integration with AAP Workflow

### Create STIG Assessment Job Template

1. **In AAP Web UI:**
   - Resources → Templates → Add job template
   - **Name:** `STIG Windows Server 2022 - Assessment`
   - **Playbook:** `ansible/playbooks/stig_windows_server_2022_assessment.yml`
   - **Inventory:** Your Windows inventory
   - **Credentials:** WinRM credential

2. **Run STIG Assessment:**
   - Click Launch
   - Review STIG findings in output
   - Export to `.CKL` checklist format for auditors

---

## STIG Checklist (.CKL) Format

DISA requires STIG results in **Checklist (.CKL)** format for audit evidence.

### Generate .CKL File:

```bash
# Generate checklist from OPA results
python3 scripts/generate_stig_checklist.py \
  --input /tmp/stig_assessment_results.json \
  --output /tmp/stig_checklist.ckl \
  --stig "Windows Server 2022 V2R1"
```

### .CKL File Structure:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<CHECKLIST>
  <ASSET>
    <HOST_NAME>win-server-01</HOST_NAME>
    <HOST_IP>192.168.1.100</HOST_IP>
  </ASSET>
  <STIGS>
    <iSTIG>
      <STIG_INFO>
        <SI_DATA>
          <SID_NAME>title</SID_NAME>
          <SID_DATA>Windows Server 2022 STIG</SID_DATA>
        </SI_DATA>
      </STIG_INFO>
      <VULN>
        <STIG_DATA>
          <VULN_ATTRIBUTE>Vuln_Num</VULN_ATTRIBUTE>
          <ATTRIBUTE_DATA>V-254442</ATTRIBUTE_DATA>
        </STIG_DATA>
        <STATUS>Open</STATUS>
        <FINDING_DETAILS>DoD Root CA certificates not installed</FINDING_DETAILS>
      </VULN>
    </iSTIG>
  </STIGS>
</CHECKLIST>
```

---

## STIG vs CIS Comparison

| Aspect | STIG | CIS |
|--------|------|-----|
| **Authority** | DISA (DoD mandate) | Industry best practice |
| **Requirement** | Mandatory for DoD | Recommended |
| **Enforcement** | DoD IG audits | Voluntary |
| **Detail Level** | Very prescriptive | General guidance |
| **Severity** | CAT I/II/III | Scored/Not Scored |
| **Checklists** | .CKL format required | JSON/HTML reports |

**Both implemented in this repository!**

---

## Compliance Requirements by Use Case

### DoD Systems
- ✅ **STIG Mandatory**
- ✅ NIST 800-53 (via RMF)
- Optional: CIS Benchmarks

### Defense Contractors (DFARS)
- ✅ **STIG Recommended**
- ✅ NIST 800-171
- ✅ CMMC Level 3+

### Federal Civilian Agencies
- Optional: STIG
- ✅ FISMA
- ✅ NIST 800-53

### Commercial/Enterprise
- Optional: STIG
- ✅ **CIS Benchmarks**
- ✅ SOC 2, PCI-DSS, ISO 27001

---

## Remediation Workflow

### 1. Run STIG Assessment
```bash
ansible-playbook -i inventory/windows.yml \
  playbooks/stig_windows_server_2022_assessment.yml
```

### 2. Review Open Findings
- CAT I findings require immediate attention
- CAT II findings within 30 days
- CAT III findings within 90 days

### 3. Create POAM (Plan of Action and Milestones)
OPA automatically generates POAM entries for open findings:

```json
{
  "vuln_id": "V-254442",
  "scheduled_completion_date": "2025-12-24",
  "milestones": [
    "Review finding and assess impact",
    "Develop remediation plan",
    "Test in non-production",
    "Implement remediation",
    "Validate compliance"
  ]
}
```

### 4. Implement Remediation

Example: Install DoD Root CA certificates

```powershell
# On Windows Server
Import-Certificate -FilePath "C:\Certs\DoD_Root_CA_2.cer" `
  -CertStoreLocation Cert:\LocalMachine\Root
```

### 5. Re-run Assessment
```bash
# Verify remediation
ansible-playbook -i inventory/windows.yml \
  playbooks/stig_windows_server_2022_assessment.yml
```

### 6. Generate Audit Evidence
```bash
# Export .CKL checklist for auditors
python3 scripts/generate_stig_checklist.py \
  --input /tmp/stig_results.json \
  --output /tmp/stig_checklist_win2022.ckl
```

---

## Multi-Framework Assessment

Run STIG + CIS together for comprehensive coverage:

```bash
# Run both STIG and CIS assessments
ansible-playbook -i inventory/windows.yml \
  playbooks/stig_and_cis_combined_assessment.yml
```

**Benefits:**
- STIG satisfies DoD requirements
- CIS provides additional industry best practices
- Combined report shows compliance across both frameworks

---

## Additional Resources

### Official STIG Resources
- **DISA STIG Library:** https://public.cyber.mil/stigs/
- **STIG Viewer Tool:** https://public.cyber.mil/stigs/srg-stig-tools/
- **SCAP Compliance Checker:** https://public.cyber.mil/stigs/scap/

### Automation Tools
- **OPA (This Implementation):** Policy-as-Code STIG validation
- **SCAP Compliance Checker (SCC):** Official DISA tool
- **OpenSCAP:** Open-source SCAP scanner

### Related Standards
- **NIST 800-53:** Security controls (maps to STIG)
- **NIST 800-171:** CUI protection (contractor requirement)
- **RMF:** Risk Management Framework (includes STIG)

---

## Troubleshooting

### Issue: OPA policy not loading

**Error:** `rego_parse_error`

**Solution:**
```bash
# Validate policy syntax
opa check policies/stig/windows_server_2022/cat_i_findings.rego

# Fix any syntax errors
```

### Issue: Missing input data

**Error:** `undefined reference`

**Solution:** Ensure fact collection includes all required fields:
```yaml
# In playbook
- name: Collect password policy
  win_shell: |
    Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Netlogon\Parameters"
  register: password_policy
```

### Issue: .CKL file won't import into STIG Viewer

**Solution:** Validate XML format:
```bash
xmllint --noout /tmp/stig_checklist.ckl
```

---

## Next Steps

1. ✅ **Load STIG policies into OPA**
2. ✅ **Run test assessment**
3. ✅ **Review findings**
4. ⏭️ **Create AAP workflow**
5. ⏭️ **Schedule recurring assessments**
6. ⏭️ **Generate audit evidence**

---

**Status:** All 8 OS types ready for DoD STIG compliance validation!

**Last Updated:** November 24, 2025
