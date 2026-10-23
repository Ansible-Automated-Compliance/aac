> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: HOST:8181x6.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Windows Server 2022 CIS Compliance Setup Guide

**Author:** Tim Coulter & Claude
**Date:** November 24, 2025
**Repository:** ansible-automated-compliance/aac

---

## Overview

Complete CIS compliance validation for **Windows Server 2022** using modular OPA policies and Ansible automation via WinRM.

### Architecture

```
Windows Servers → WinRM → Ansible (fact collection) → OPA (policy evaluation) → Reports
```

---

## Policy modules (updated 2026-10-15)

`policies/benchmarks/cis/windows_server_2022_modular/` is generated from the **CIS Microsoft Windows Server 2022
Benchmark v5.1.0** workbook and covers all 408 recommendations: one module per benchmark section (1 Account
Policies, 2 Local Policies, 5 System Services, 9 Firewall, 17 Advanced Audit Policy, 18 and 19 Administrative
Templates), a shared evaluator (`lib.rego`) and the two Manual recommendations as attestations. Profile (member
server / domain controller, Level 1 / 2, Next Generation), fact contract and decision rules: the module's
`README.md` in the policies submodule.

- **Entrypoint:** `POST /v1/data/cis_windows_server_2022/main/compliance_report`
- **Collector:** `ansible/playbooks/cis_windows_server_2022_assessment.yml`, driven by the policy's
  `data/collector_manifest.json` (registry values, per-user hives, `auditpol /backup`, `secedit /export`,
  `Win32_ComputerSystem.DomainRole`). Survey / extra_vars: `cis_windows_level`, `cis_windows_next_generation`,
  `cis_windows_attestations`.

---

## Prerequisites

### Windows Server Requirements

1. **Windows Server 2022** (Datacenter or Standard edition)
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

Edit `ansible/inventory/windows_server_2022_test.yml`:

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
ansible -i inventory/windows_server_2022_test.yml all -m win_ping

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

# Run complete CIS Windows Server 2022 assessment
ansible-playbook -i inventory/windows_server_2022_test.yml \
  playbooks/cis_windows_server_2022_assessment.yml

# With verbose output
ansible-playbook -i inventory/windows_server_2022_test.yml \
  playbooks/cis_windows_server_2022_assessment.yml -v
```

### Query OPA Directly

```bash
# Check if policies are loaded
curl http://localhost:8181/v1/policies | jq '.result[].id' | grep win2022

# Empty facts must fail closed (compliant false, every in-scope recommendation failed)
curl -s -X POST http://localhost:8181/v1/data/cis_windows_server_2022/main/compliance_report \
  -H 'Content-Type: application/json' \
  -d '{"input": {"cis_profile": {"role": "member_server", "level": 2}}}' | jq '.result | {compliant, total_controls, failed_controls}'

# One section's per-recommendation results
curl -s -X POST http://localhost:8181/v1/data/cis_windows_server_2022/advanced_audit/compliance_report \
  -H 'Content-Type: application/json' -d '{"input": {}}' | jq '.result.results'
```

---

## Reports

Assessment reports are saved to `~/compliance/reports/`:

- **Facts:** `<hostname>_windows_2022_facts_<timestamp>.json`
- **Compliance Report:** `<hostname>_windows_2022_compliance_report_<timestamp>.json`

### Report Structure

```json
{
  "assessment_metadata": {
    "hostname": "win-server-01",
    "benchmark": "CIS Microsoft Windows Server 2022 Benchmark v1.0.0",
    "assessment_time": "2025-11-24T..."
  },
  "system_info": {
    "distribution": "Microsoft Windows Server 2022 Datacenter",
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

The Windows Server 2022 assessments are compatible with the existing PostgreSQL historical trending workflow:

1. Facts are collected in JSON format
2. Use `store_compliance_facts.yml` playbook
3. Use `store_compliance_results.yml` playbook
4. Query trends via `compliance_trending_report.yml`

### AAP Job Template Configuration

**Job Template: "CIS Windows Server 2022 - Assessment"**
- **Playbook:** `playbooks/cis_windows_server_2022_assessment.yml`
- **Inventory:** Windows Server 2022 inventory
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

1. Edit module files in `policies/cis_benchmarks/windows_server_2022_modular/`
2. Add specific CIS control checks
3. Update `violations` logic
4. Reload policies into OPA:
   ```bash
   curl -X PUT --data-binary @module_validation.rego \
     http://localhost:8181/v1/policies/win2022_module_validation.rego
   ```

---

## Multi-OS Platform Status

| OS | Version | Status | Coverage |
|----|---------|--------|----------|
| RHEL 9 | 9.x | ✅ Production | 338/338 (100%) |
| RHEL 8 | 8.x | ✅ Ready | ~300 controls |
| Windows Server 2022 | 2022 | ✅ **Ready** | ~400 controls (modular foundation) |

---

## Additional Resources

### CIS Benchmark
- Download: [CIS Windows Server 2022 Benchmark](https://www.cisecurity.org/benchmark/microsoft_windows_server)

### Ansible Windows Modules
- Docs: https://docs.ansible.com/ansible/latest/collections/ansible/windows/

### WinRM Configuration
- Microsoft Docs: https://docs.microsoft.com/en-us/windows/win32/winrm/portal

---

**Last Updated:** November 24, 2025
**Status:** Production-ready modular foundation
**Next Steps:** Expand stub modules with full CIS Windows Server 2022 control logic
