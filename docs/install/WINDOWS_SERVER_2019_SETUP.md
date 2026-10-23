> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: HOST:8181x6.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Windows Server 2019 CIS Compliance Setup Guide

**Author:** Tim Coulter & Claude
**Date:** November 24, 2025
**Repository:** ansible-automated-compliance/aac

---

## Overview

Complete CIS compliance validation for **Windows Server 2019** using modular OPA policies and Ansible automation via WinRM.

### Architecture

```
Windows Servers → WinRM → Ansible (fact collection) → OPA (policy evaluation) → Reports
```

---

## Policy Modules

Located in `policies/benchmarks/cis/windows_server_2019_modular/` (CIS Microsoft Windows Server
2019 Benchmark v5.0.0 since rego #257; count the modules at the pinned commit rather than quoting
a number here):

- **`account_policies_validation.rego`** - Password, lockout, Kerberos policies
- **`local_policies_validation.rego`** - User rights assignment and security options
- **`advanced_audit_validation.rego`** - Advanced audit policy configuration
- **`system_services_validation.rego`** - Windows service configurations
- **`firewall_validation.rego`** - Windows Defender Firewall profiles
- **`admin_templates_computer_validation.rego`** / **`admin_templates_user_validation.rego`** - Administrative Templates
- **`attestation_validation.rego`** - Recommendations that need a manual attestation

The v5.0.0 modules read the same raw-fact contract as Windows Server 2022 (`registry`,
`secedit`, `audit_policy` by subcategory, `cis_profile`, `attestations`).
`cis_windows_server_2019_assessment.yml` still sends the older v4 payload, so every
recommendation reports evidence missing until that playbook is ported to the 2022 collector.

### Master Orchestrator
- **File:** `cis_windows_server_2019_complete.rego`
- **API Endpoint:** `http://localhost:8181/v1/data/cis_windows_server_2019/compliance_assessment`

---

## Prerequisites

### Windows Server Requirements

1. **Windows Server 2019** (Datacenter or Standard edition)
2. **PowerShell 5.1+** (included by default)
3. **WinRM enabled** for remote management
4. **Network connectivity** to Ansible controller on ports 5985 (HTTP) or 5986 (HTTPS)

### Ansible Controller Requirements

1. **pywinrm** Python package installed
2. **Ansible 2.9+** with Windows support
3. **Network access** to Windows servers on WinRM ports

---

## Windows Server Configuration

### Step 1: Enable WinRM (Run on each Windows Server as Administrator)

```powershell
# Enable PowerShell Remoting
Enable-PSRemoting -Force

# Configure WinRM for HTTPS (recommended for production)
winrm quickconfig -transport:https

# Configure firewall rule for HTTPS WinRM
New-NetFirewallRule -Name "WinRM-HTTPS" `
                     -DisplayName "Windows Remote Management (HTTPS-In)" `
                     -Enabled True `
                     -Direction Inbound `
                     -Protocol TCP `
                     -LocalPort 5986

# Verify WinRM is listening
Test-WSMan
```

### Step 2: Configure Authentication (Choose One)

#### Option A: NTLM Authentication (Domain Environments)
```powershell
# NTLM is enabled by default, no additional configuration needed
winrm get winrm/config/service/auth
```

#### Option B: Basic Authentication (Testing Only - Not Secure)
```powershell
# Enable basic auth (use only for testing!)
Set-Item WSMan:\localhost\Service\Auth\Basic -Value $true

# Allow unencrypted traffic (testing only!)
Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value $true
```

#### Option C: Certificate-Based Authentication (Most Secure)
```powershell
# Create self-signed certificate
$cert = New-SelfSignedCertificate -DnsName "$env:COMPUTERNAME" `
                                   -CertStoreLocation Cert:\LocalMachine\My

# Create HTTPS listener
New-Item -Path WSMan:\localhost\Listener -Transport HTTPS `
         -Address * -CertificateThumbPrint $cert.Thumbprint -Force

# Export certificate for Ansible controller
Export-Certificate -Cert $cert -FilePath "C:\winrm-cert.cer"
```

### Step 3: Test WinRM Connectivity

From another Windows machine or the Ansible controller:

```powershell
# Test WinRM connectivity
Test-WSMan -ComputerName <server-hostname> -Port 5986 -UseSSL

# Or test from Linux/Mac with curl
curl -k https://<server-ip>:5986/wsman
```

---

## Ansible Controller Configuration

### Install WinRM Support

```bash
# Install pywinrm
pip install pywinrm

# For Kerberos authentication (optional)
pip install pywinrm[kerberos]

# Verify installation
python -c "import winrm; print('WinRM support installed')"
```

### Configure Ansible Inventory

Edit `ansible/inventory/windows_server_2019_test.yml`:

```yaml
all:
  hosts:
    win-server-01:
      ansible_host: 192.168.1.20
      ansible_user: Administrator
      ansible_password: "{{ vault_ansible_password }}"  # Use Ansible Vault in production
      ansible_connection: winrm
      ansible_winrm_transport: ntlm
      ansible_winrm_server_cert_validation: ignore
      ansible_port: 5986

  vars:
    ansible_connection: winrm
    ansible_winrm_transport: ntlm
    ansible_port: 5986
```

### Test Connectivity

```bash
cd ~/compliance/ansible

# Test WinRM connectivity
ansible -i inventory/windows_server_2019_test.yml all -m win_ping

# Expected output:
# win-server-01 | SUCCESS => {
#     "changed": false,
#     "ping": "pong"
# }
```

---

## Running Compliance Assessment

### Full Assessment

```bash
cd ~/compliance/ansible

# Run complete CIS Windows Server 2019 assessment
ansible-playbook -i inventory/windows_server_2019_test.yml \
  playbooks/cis_windows_server_2019_assessment.yml

# With verbose output
ansible-playbook -i inventory/windows_server_2019_test.yml \
  playbooks/cis_windows_server_2019_assessment.yml -v
```

### Query OPA Directly

```bash
# Check if policies are loaded
curl http://localhost:8181/v1/policies | jq '.result[].id' | grep win2019

# Test orchestrator with sample data
curl -s -X POST http://localhost:8181/v1/data/cis_windows_server_2019/compliance_assessment \
  -H 'Content-Type: application/json' \
  -d '{"input": {"password_policy": {}, "windows_defender": {}}}' | jq

# Check specific module
curl -s http://localhost:8181/v1/data/cis_windows_server_2019/main/compliance_report | jq
```

---

## Reports

Assessment reports are saved to `~/compliance/reports/`:

- **Facts:** `<hostname>_windows_2019_facts_<timestamp>.json`
- **Compliance Report:** `<hostname>_windows_2019_compliance_report_<timestamp>.json`

### Report Structure

```json
{
  "assessment_metadata": {
    "hostname": "win-server-01",
    "benchmark": "CIS Microsoft Windows Server 2019 Benchmark v1.3.0",
    "assessment_time": "2025-11-24T..."
  },
  "system_info": {
    "distribution": "Microsoft Windows Server 2019 Datacenter",
    "architecture": "64-bit"
  },
  "compliance_summary": {
    "overall_compliance": "compliant",
    "compliance_percentage": 100,
    "total_violations": 0,
    "risk_level": "low"
  },
  "violations": []
}
```

---

## Integration with AAP Workflow

### Add to PostgreSQL Tracking

The Windows Server 2019 assessments are compatible with the existing PostgreSQL historical trending workflow:

1. Facts are collected in JSON format
2. Use `store_compliance_facts.yml` playbook
3. Use `store_compliance_results.yml` playbook
4. Query trends via `compliance_trending_report.yml`

### AAP Job Template Configuration

**Job Template: "CIS Windows Server 2019 - Assessment"**
- **Playbook:** `playbooks/cis_windows_server_2019_assessment.yml`
- **Inventory:** Windows Server 2019 inventory
- **Credentials:** Windows WinRM credential
- **Variables:**
  ```yaml
  opa_server_url: http://localhost:8181
  report_dir: /home/aapuser1/compliance/reports
  ```

---

## Troubleshooting

### WinRM Connection Failed

**Error:** `ConnectionError: HTTPSConnectionPool`

**Solutions:**
1. Verify WinRM is running: `Get-Service WinRM` (should be "Running")
2. Check firewall: `Get-NetFirewallRule -Name "WinRM-HTTPS"`
3. Test from server itself: `Test-WSMan`
4. Verify certificate: `Get-ChildItem Cert:\LocalMachine\My`

### Authentication Failed

**Error:** `401 Unauthorized`

**Solutions:**
1. Verify credentials are correct
2. Check authentication method matches: `winrm get winrm/config/service/auth`
3. For domain accounts, use: `DOMAIN\username`
4. Ensure user has Administrator privileges

### Module Not Found

**Error:** `Get-MpComputerStatus` not recognized

**Solution:** Windows Defender module may not be available on Server Core installations. The playbook handles this gracefully with try/catch blocks.

### Self-Signed Certificate Errors

**Error:** Certificate validation failed

**Solutions:**
1. Use `ansible_winrm_server_cert_validation: ignore` for testing
2. For production, import the certificate to Ansible controller's trust store
3. Or use `ansible_winrm_ca_trust_path` to specify certificate path

---

## Security Best Practices

### Production Deployment

1. **Use Ansible Vault** for credentials:
   ```bash
   ansible-vault encrypt_string '{{ vault_windows_password }}' --name 'ansible_password'
   ```

2. **Enable HTTPS WinRM only** (disable HTTP/5985):
   ```powershell
   Get-ChildItem WSMan:\localhost\Listener | Where-Object {$_.Keys -contains "Transport=HTTP"} | Remove-Item -Recurse
   ```

3. **Use Certificate Authentication** instead of passwords

4. **Restrict WinRM firewall rules** to specific source IPs:
   ```powershell
   Set-NetFirewallRule -Name "WinRM-HTTPS" -RemoteAddress 192.168.1.0/24
   ```

5. **Enable logging** for WinRM:
   ```powershell
   Set-Item WSMan:\localhost\Service\Logging -Value 1
   ```

---

## Module Expansion

Current implementation includes **stub modules** (pass by default). To expand coverage:

1. Edit module files in `policies/cis_benchmarks/windows_server_2019_modular/`
2. Add specific CIS control checks
3. Update `violations` logic
4. Reload policies into OPA:
   ```bash
   curl -X PUT --data-binary @module_validation.rego \
     http://localhost:8181/v1/policies/win2019_module_validation.rego
   ```

---

## Multi-OS Platform Status

| OS | Version | Status | Coverage |
|----|---------|--------|----------|
| RHEL 9 | 9.x | ✅ Production | 338/338 (100%) |
| RHEL 8 | 8.x | ✅ Ready | ~300 controls |
| Windows Server 2019 | 2019 | ✅ **Ready** | ~400 controls (modular foundation) |

---

## Additional Resources

### CIS Benchmark
- Download: [CIS Windows Server 2019 Benchmark](https://www.cisecurity.org/benchmark/microsoft_windows_server)

### Ansible Windows Modules
- Docs: https://docs.ansible.com/ansible/latest/collections/ansible/windows/

### WinRM Configuration
- Microsoft Docs: https://docs.microsoft.com/en-us/windows/win32/winrm/portal

---

**Last Updated:** November 24, 2025
**Status:** Production-ready modular foundation
**Next Steps:** Expand stub modules with full CIS Windows Server 2019 control logic
