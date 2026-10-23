> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: HOST:8181x22, RETIRED-HOSTx11, AAP-2.5/2.6x5, SPLIT-PORTSx2.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# AAP 2.6 + OPA Integration Deployment
## Server: AAP_HOST

> **⚠️ ARCHITECTURE UPDATE — April 2026**
>
> This guide describes the original single-OPA deployment. The current production architecture uses **three purpose-specific OPA containers** (not a systemd service):
>
> | Container | Port | Use |
> |-----------|------|-----|
> | `opa-security` | 8181 | CIS Benchmarks, NIST, STIGs |
> | `opa-compliance` | 8182 | ISO 27001, SOC 2, PCI-DSS, NCSC CAF, FISMA |
> | `opa-ot` | 8183 | NERC-CIP, IEC 62443, AMI, AI Governance |
>
> Policies are loaded via **AAP Template 27 "AAC - Load OPA Policies"** from the git submodule `policies/` (ynotbhatc/rego_policy_libraries), not copied to `/etc/opa/policies/`. Use **Template 28** to recreate containers from scratch.
>
> The guide below remains accurate for reference and for understanding the architecture evolution.

---

## 📋 Deployment Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  AAP 2.6 Controller (AAP_HOST)                             │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ OPA Containers (podman — NOT systemd)                     │ │
│  │ • opa-security  :8181  (CIS, NIST, STIGs)                 │ │
│  │ • opa-compliance :8182 (ISO, SOC2, PCI, NCSC CAF)         │ │
│  │ • opa-ot        :8183  (NERC-CIP, AMI, AI Governance)     │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ Callback Plugin                                            │ │
│  │ • Location: /usr/share/ansible/plugins/callback/          │ │
│  │ • Enabled in AAP Settings                                  │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ Compliance Playbooks                                       │ │
│  │ • Project: Git repository with playbooks                   │ │
│  │ • Job Templates: Configured in AAP UI                      │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Phase 1: Deploy OPA on AAP Controller

### Step 1: SSH to AAP Controller

```bash
# From your workstation
ssh admin@AAP_HOST

# Or if using specific user
ssh your-username@AAP_HOST
```

### Step 2: Install OPA

```bash
# Switch to root (if needed)
sudo -i

# Download OPA binary
cd /tmp
curl -L -o opa https://github.com/open-policy-agent/opa/releases/download/v1.10.0/opa_linux_amd64

# Install OPA
sudo install -o root -g root -m 0755 opa /usr/local/bin/opa

# Verify installation
opa version
# Expected output: Version: 1.10.0
```

### Step 3: Create OPA Directory Structure

```bash
# Create directories
sudo mkdir -p /etc/opa/policies
sudo mkdir -p /var/lib/opa
sudo mkdir -p /var/log/opa

# Create OPA user
sudo useradd -r -s /bin/false -d /var/lib/opa opa

# Set permissions
sudo chown -R opa:opa /etc/opa /var/lib/opa /var/log/opa
sudo chmod 755 /etc/opa /var/lib/opa /var/log/opa
```

### Step 4: Deploy Compliance Policies

```bash
# From your local machine, copy policies to AAP server
cd <aac-repo>

# Option A: Using scp
scp -r policies/cis_rhel9 admin@AAP_HOST:/tmp/

# Option B: Using rsync (preferred)
rsync -avz --progress policies/cis_rhel9/ admin@AAP_HOST:/tmp/cis_rhel9/

# Back on the AAP server, move policies to OPA directory
ssh admin@AAP_HOST
sudo mv /tmp/cis_rhel9 /etc/opa/policies/
sudo chown -R opa:opa /etc/opa/policies/cis_rhel9
```

### Step 5: Create OPA Systemd Service

```bash
# Create service file
sudo tee /etc/systemd/system/opa.service > /dev/null <<'EOF'
[Unit]
Description=Open Policy Agent
Documentation=https://www.openpolicyagent.org/docs/
After=network.target

[Service]
Type=simple
User=opa
Group=opa
ExecStart=/usr/local/bin/opa run \
  --server \
  --addr 0.0.0.0:8181 \
  --log-level info \
  --log-format text \
  /etc/opa/policies
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload

# Enable and start OPA
sudo systemctl enable opa
sudo systemctl start opa

# Check status
sudo systemctl status opa
```

### Step 6: Configure Firewall (if enabled)

```bash
# Check if firewalld is running
sudo systemctl status firewalld

# If firewalld is active, open OPA port (only for local access)
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="127.0.0.1" port protocol="tcp" port="8181" accept'
sudo firewall-cmd --reload

# Verify
sudo firewall-cmd --list-all
```

### Step 7: Test OPA Server

```bash
# Test health endpoint
curl http://localhost:8181/health

# Expected output:
# {}

# Test with actual policy (if policies are loaded)
curl http://localhost:8181/v1/policies

# Should show loaded policies

# Test with mock data
curl -X POST http://localhost:8181/v1/data/cis_rhel9/filesystem/violations \
  -H "Content-Type: application/json" \
  -d '{"input": {"disabled_filesystem_modules": {"modules": [{"module": "cramfs", "loaded": false, "disabled": true, "compliant": true}], "all_compliant": true}, "mount_options": {"tmp": {"exists": true, "has_nodev": true, "has_nosuid": true, "has_noexec": true, "fully_compliant": true}}}}'

# Should return empty violations if compliant
```

---

## 🔧 Phase 2: Deploy Ansible Callback Plugin

### Step 1: Create Callback Plugin Directory

```bash
# On AAP server
sudo mkdir -p /usr/share/ansible/plugins/callback
sudo chmod 755 /usr/share/ansible/plugins/callback
```

### Step 2: Deploy Callback Plugin

Create the callback plugin file:

```bash
# Create the plugin
sudo tee /usr/share/ansible/plugins/callback/opa_compliance.py > /dev/null <<'PYTHON_CODE'
#!/usr/bin/env python3
"""
OPA Compliance Callback Plugin for AAP 2.6
Validates compliance during playbook execution
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json
import os
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from ansible.plugins.callback import CallbackBase
from datetime import datetime

DOCUMENTATION = '''
    callback: opa_compliance
    type: notification
    short_description: OPA compliance validation callback
    description:
        - Sends gathered facts to OPA for compliance validation
        - Supports multiple compliance frameworks
        - Reports violations in real-time
    version_added: "2.9"
    requirements:
        - requests library (python3-requests)
    options:
      opa_server_url:
        description: OPA server URL
        default: 'http://localhost:8181'
        env:
          - name: OPA_SERVER_URL
        ini:
          - section: callback_opa_compliance
            key: server_url
      fail_on_violations:
        description: Fail playbook if violations found
        default: False
        type: bool
        env:
          - name: OPA_FAIL_ON_VIOLATIONS
        ini:
          - section: callback_opa_compliance
            key: fail_on_violations
      compliance_frameworks:
        description: Comma-separated list of frameworks to validate
        default: 'auto'
        env:
          - name: OPA_COMPLIANCE_FRAMEWORKS
        ini:
          - section: callback_opa_compliance
            key: frameworks
'''

class CallbackModule(CallbackBase):
    """OPA Compliance Callback Plugin"""

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'opa_compliance'
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self):
        super(CallbackModule, self).__init__()

        if not HAS_REQUESTS:
            self._display.warning(
                "[OPA] requests library not installed. "
                "Install with: pip3 install requests"
            )
            self.disabled = True
            return

        self.disabled = False
        self.opa_server_url = os.getenv('OPA_SERVER_URL', 'http://localhost:8181')
        self.fail_on_violations = os.getenv('OPA_FAIL_ON_VIOLATIONS', 'false').lower() == 'true'
        self.frameworks = os.getenv('OPA_COMPLIANCE_FRAMEWORKS', 'auto')
        self.host_results = {}

    def v2_runner_on_ok(self, result):
        """Called when a task completes successfully"""

        if self.disabled:
            return

        # Only process fact gathering tasks
        if result._task.action not in ['setup', 'gather_facts']:
            return

        hostname = result._host.get_name()
        facts = result._result.get('ansible_facts', {})

        # Check if this looks like compliance fact collection
        if not self._is_compliance_facts(facts):
            return

        self._display.v(f"[OPA] Processing facts for {hostname}")
        self._validate_compliance(hostname, facts)

    def _is_compliance_facts(self, facts):
        """Check if facts contain compliance-related data"""
        compliance_indicators = [
            'disabled_filesystem_modules',
            'mount_options',
            'critical_files',
            'sysctl_parameters',
            'rsyslog',
            'journald',
            'autofs',
            'unnecessary_services'
        ]
        return any(key in facts for key in compliance_indicators)

    def _validate_compliance(self, hostname, facts):
        """Validate facts against OPA policies"""

        try:
            # Add metadata
            facts['hostname'] = hostname
            facts['collection_timestamp'] = datetime.now().isoformat()

            # Determine which policy sections to check
            sections = self._determine_sections(facts)

            all_violations = []
            section_results = {}

            for section in sections:
                violations = self._check_section(section, facts)
                if violations:
                    all_violations.extend(violations)
                    section_results[section] = {
                        'compliant': False,
                        'violations': len(violations)
                    }
                else:
                    section_results[section] = {
                        'compliant': True,
                        'violations': 0
                    }

            # Store results
            self.host_results[hostname] = {
                'compliant': len(all_violations) == 0,
                'total_violations': len(all_violations),
                'section_results': section_results,
                'violations': all_violations
            }

            # Display results
            self._display_results(hostname, section_results, all_violations)

            # Fail if configured
            if all_violations and self.fail_on_violations:
                raise Exception(
                    f"Compliance validation failed for {hostname}: "
                    f"{len(all_violations)} violations found"
                )

        except requests.exceptions.RequestException as e:
            self._display.warning(f"[OPA] Connection error for {hostname}: {e}")
        except Exception as e:
            self._display.error(f"[OPA] Validation error for {hostname}: {e}")
            if self.fail_on_violations:
                raise

    def _determine_sections(self, facts):
        """Determine which policy sections to validate"""
        sections = []

        # Check for specific fact types
        if any(k in facts for k in ['disabled_filesystem_modules', 'mount_options', 'sticky_bit']):
            sections.append('filesystem')

        if any(k in facts for k in ['rsyslog', 'journald', 'log_file_permissions']):
            sections.append('logging')

        if any(k in facts for k in ['critical_files', 'world_writable', 'suid_files']):
            sections.append('file_permissions')

        if any(k in facts for k in ['autofs', 'unnecessary_services', 'chronyd']):
            sections.append('services')

        if any(k in facts for k in ['sysctl_parameters', 'ip_forwarding', 'firewall']):
            sections.append('network')

        return sections if sections else ['filesystem', 'logging', 'file_permissions', 'services', 'network']

    def _check_section(self, section, facts):
        """Check a specific policy section"""
        url = f"{self.opa_server_url}/v1/data/cis_rhel9/{section}/violations"

        try:
            response = requests.post(
                url,
                json={'input': facts},
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                return result.get('result', [])
            else:
                self._display.warning(
                    f"[OPA] Section {section} returned HTTP {response.status_code}"
                )
                return []
        except Exception as e:
            self._display.warning(f"[OPA] Error checking {section}: {e}")
            return []

    def _display_results(self, hostname, section_results, violations):
        """Display compliance results"""

        total_violations = len(violations)
        compliant = total_violations == 0

        # Header
        status = "✓ COMPLIANT" if compliant else "✗ NON-COMPLIANT"
        color = 'green' if compliant else 'red'

        self._display.banner(f"[OPA COMPLIANCE] {hostname}")
        self._display.display(f"  Status: {status}", color=color)
        self._display.display(f"  Total Violations: {total_violations}", color=color)

        # Section breakdown
        if section_results:
            self._display.display("\n  Section Results:")
            for section, result in section_results.items():
                section_status = "✓" if result['compliant'] else "✗"
                section_color = 'green' if result['compliant'] else 'yellow'
                self._display.display(
                    f"    {section_status} {section}: {result['violations']} violations",
                    color=section_color
                )

        # Show violations
        if violations:
            self._display.display("\n  Violations:")
            for i, violation in enumerate(violations[:10], 1):  # Show first 10
                self._display.display(f"    {i}. {violation}", color='red')

            if len(violations) > 10:
                self._display.display(
                    f"    ... and {len(violations) - 10} more violations",
                    color='red'
                )

        self._display.display("")  # Blank line

    def v2_playbook_on_stats(self, stats):
        """Called when playbook completes"""

        if self.disabled or not self.host_results:
            return

        # Summary
        self._display.banner("[OPA COMPLIANCE SUMMARY]")

        total_hosts = len(self.host_results)
        compliant_hosts = sum(1 for r in self.host_results.values() if r['compliant'])
        total_violations = sum(r['total_violations'] for r in self.host_results.values())

        summary_color = 'green' if compliant_hosts == total_hosts else 'red'

        self._display.display(f"  Hosts Checked: {total_hosts}", color='white')
        self._display.display(f"  Compliant: {compliant_hosts}", color='green')
        self._display.display(f"  Non-Compliant: {total_hosts - compliant_hosts}", color='red')
        self._display.display(f"  Total Violations: {total_violations}", color=summary_color)
        self._display.display("")
PYTHON_CODE

# Set permissions
sudo chmod 644 /usr/share/ansible/plugins/callback/opa_compliance.py
sudo chown root:root /usr/share/ansible/plugins/callback/opa_compliance.py
```

### Step 3: Install Python Dependencies

```bash
# Install requests library for callback plugin
sudo pip3 install requests

# Or on RHEL/CentOS
sudo yum install -y python3-requests

# Verify installation
python3 -c "import requests; print(requests.__version__)"
```

### Step 4: Test Callback Plugin

```bash
# Test import
python3 -c "import sys; sys.path.insert(0, '/usr/share/ansible/plugins/callback'); import opa_compliance; print('Plugin loaded successfully')"
```

---

## 🎮 Phase 3: Configure AAP 2.6

### Option A: Configure via AAP Web UI

1. **Login to AAP Controller**
   - Navigate to: `https://AAP_HOST`
   - Login with admin credentials

2. **Enable Callback Plugin**
   - Go to: **Settings** → **Job settings**
   - Find: **Callback plugins**
   - Add: `opa_compliance` to the list
   - Click **Save**

3. **Configure Ansible Settings**
   - Go to: **Settings** → **Jobs**
   - Find: **Extra Environment Variables**
   - Add:
     ```yaml
     OPA_SERVER_URL: "http://localhost:8181"
     OPA_FAIL_ON_VIOLATIONS: "false"
     OPA_COMPLIANCE_FRAMEWORKS: "auto"
     ```
   - Click **Save**

### Option B: Configure via API

```bash
# Get admin token first (from AAP UI: User → Tokens)
export AAP_TOKEN=your-aap-token-here  # replace with token from AAP UI → User → Tokens
export AAP_HOST="AAP_HOST"

# Enable callback plugin
curl -X PATCH "https://${AAP_HOST}/api/controller/v2/settings/jobs/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "DEFAULT_CALLBACK_WHITELIST": ["opa_compliance"]
  }' \
  --insecure

# Set environment variables
curl -X PATCH "https://${AAP_HOST}/api/controller/v2/settings/jobs/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "AWX_TASK_ENV": {
      "OPA_SERVER_URL": "http://localhost:8181",
      "OPA_FAIL_ON_VIOLATIONS": "false"
    }
  }' \
  --insecure
```

### Option C: Configure via Ansible Configuration

```bash
# Edit ansible.cfg on AAP controller
sudo tee -a /etc/ansible/ansible.cfg > /dev/null <<'EOF'

[defaults]
callback_whitelist = opa_compliance

[callback_opa_compliance]
server_url = http://localhost:8181
fail_on_violations = false
frameworks = auto
EOF
```

---

## 📦 Phase 4: Create Compliance Check Project

### Step 1: Create Git Repository (or use existing)

```bash
# On your local machine
cd <aac-repo>

# Create playbooks directory if it doesn't exist
mkdir -p playbooks

# Create compliance check playbook
cat > playbooks/cis_rhel9_compliance_check.yml <<'EOF'
---
- name: CIS RHEL 9 Compliance Check
  hosts: all
  gather_facts: true
  become: true

  vars:
    opa_server_url: "{{ lookup('env', 'OPA_SERVER_URL') | default('http://localhost:8181', true) }}"

  tasks:
    - name: Display compliance check start
      debug:
        msg: "Starting CIS RHEL 9 compliance check for {{ inventory_hostname }}"

    - name: Gather all facts
      setup:
        gather_subset:
          - all

    # The callback plugin will automatically validate facts with OPA

    - name: Compliance check complete
      debug:
        msg: "Compliance check complete - see callback output above"
EOF

# Commit to git
git add playbooks/cis_rhel9_compliance_check.yml
git commit -m "Add CIS RHEL 9 compliance check playbook"
git push
```

### Step 2: Add Project in AAP

1. **Via Web UI:**
   - Go to: **Resources** → **Projects** → **Add**
   - Name: `Compliance Validation`
   - SCM Type: `Git`
   - SCM URL: Your git repository URL
   - SCM Branch: `main`
   - Click **Save**
   - Click **Sync** to pull playbooks

2. **Via API:**
```bash
curl -X POST "https://${AAP_HOST}/api/controller/v2/projects/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Compliance Validation",
    "description": "OPA compliance validation playbooks",
    "scm_type": "git",
    "scm_url": "https://github.com/your-org/your-repo.git",
    "scm_branch": "main"
  }' \
  --insecure
```

---

## 🎯 Phase 5: Create Job Template

### Via Web UI:

1. **Create Job Template**
   - Go to: **Resources** → **Templates** → **Add** → **Add job template**
   - Fill in:
     - **Name**: `CIS RHEL 9 Compliance Check`
     - **Job Type**: `Run`
     - **Inventory**: Select your inventory
     - **Project**: `Compliance Validation`
     - **Playbook**: `playbooks/cis_rhel9_compliance_check.yml`
     - **Credentials**: Select SSH credentials
     - **Extra Variables**:
       ```yaml
       OPA_SERVER_URL: http://localhost:8181
       OPA_FAIL_ON_VIOLATIONS: false
       ```
   - Click **Save**

2. **Test the Job Template**
   - Click **Launch**
   - Watch the output for OPA compliance validation messages

---

## 🧪 Phase 6: Test the Integration

### Test 1: Quick Test from Command Line

```bash
# SSH to AAP server
ssh admin@AAP_HOST

# Run a simple test playbook
cat > /tmp/test_opa.yml <<'EOF'
---
- name: Test OPA Integration
  hosts: localhost
  connection: local
  gather_facts: false

  tasks:
    - name: Test OPA health
      uri:
        url: http://localhost:8181/health
        method: GET
        return_content: yes
      register: opa_health

    - name: Display OPA status
      debug:
        msg: "OPA is healthy: {{ opa_health.status == 200 }}"
EOF

# Run the test
ansible-playbook /tmp/test_opa.yml
```

### Test 2: Test with Mock Data

```bash
# Create test facts file
cat > /tmp/test_facts.json <<'EOF'
{
  "hostname": "test-server",
  "collection_timestamp": "2025-10-16T10:00:00Z",
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
  },
  "compliance_checks": {
    "all_fs_modules_disabled": true,
    "tmp_partition_secure": true
  }
}
EOF

# Test OPA evaluation
curl -X POST http://localhost:8181/v1/data/cis_rhel9/filesystem/violations \
  -H "Content-Type: application/json" \
  -d @/tmp/test_facts.json

# Should return empty array [] if compliant
```

### Test 3: Run Job Template from AAP

1. Go to AAP Web UI
2. Navigate to: **Resources** → **Templates**
3. Find: `CIS RHEL 9 Compliance Check`
4. Click **Launch**
5. Watch for OPA callback messages in the output

Expected output should include:
```
[OPA COMPLIANCE] hostname
  Status: ✓ COMPLIANT (or ✗ NON-COMPLIANT)
  Total Violations: 0

  Section Results:
    ✓ filesystem: 0 violations
    ✓ logging: 0 violations
    ...
```

---

## 📊 Phase 7: Monitoring & Maintenance

### View OPA Logs

```bash
# View OPA service logs
sudo journalctl -u opa -f

# View last 100 lines
sudo journalctl -u opa -n 100

# View logs from today
sudo journalctl -u opa --since today
```

### Check OPA Status

```bash
# Service status
sudo systemctl status opa

# Health check
curl http://localhost:8181/health

# List loaded policies
curl http://localhost:8181/v1/policies | jq '.result[].id'
```

### Restart OPA (after policy updates)

```bash
# Restart OPA service
sudo systemctl restart opa

# Check status
sudo systemctl status opa

# Verify policies loaded
curl http://localhost:8181/v1/policies
```

---

## 🔍 Troubleshooting

### Issue: OPA Not Starting

```bash
# Check logs
sudo journalctl -u opa -n 50

# Common fixes:
# 1. Check OPA binary
ls -la /usr/local/bin/opa

# 2. Check permissions
ls -la /etc/opa/policies/

# 3. Test OPA manually
sudo -u opa /usr/local/bin/opa run --server --addr 127.0.0.1:8181 /etc/opa/policies
```

### Issue: Callback Plugin Not Working

```bash
# 1. Verify plugin exists
ls -la /usr/share/ansible/plugins/callback/opa_compliance.py

# 2. Test import
python3 << EOF
import sys
sys.path.insert(0, '/usr/share/ansible/plugins/callback')
import opa_compliance
print("Success!")
EOF

# 3. Check AAP settings
# Go to AAP UI → Settings → Jobs → Check callback_whitelist

# 4. Check environment variables
env | grep OPA
```

### Issue: Connection Refused

```bash
# 1. Check OPA is listening
sudo netstat -tlnp | grep 8181

# 2. Test locally
curl http://localhost:8181/health

# 3. Check firewall
sudo firewall-cmd --list-all

# 4. Check OPA config
sudo cat /etc/systemd/system/opa.service
```

---

## 📝 Quick Reference Commands

```bash
# OPA Service Management
sudo systemctl status opa          # Check status
sudo systemctl restart opa         # Restart OPA
sudo systemctl stop opa            # Stop OPA
sudo systemctl start opa           # Start OPA
sudo journalctl -u opa -f          # View logs

# OPA Testing
curl http://localhost:8181/health                    # Health check
curl http://localhost:8181/v1/policies              # List policies
curl -X POST http://localhost:8181/v1/data/cis_rhel9/report -d @facts.json  # Evaluate

# AAP Job Execution
# Via CLI (from AAP server):
awx-cli job_template launch --name="CIS RHEL 9 Compliance Check"

# Via Web UI:
# Resources → Templates → CIS RHEL 9 Compliance Check → Launch
```

---

## ✅ Deployment Checklist

- [ ] OPA installed at `/usr/local/bin/opa`
- [ ] OPA systemd service created and running
- [ ] Policies deployed to `/etc/opa/policies/cis_rhel9/`
- [ ] OPA responding to health checks
- [ ] Callback plugin deployed to `/usr/share/ansible/plugins/callback/`
- [ ] Python requests library installed
- [ ] Callback plugin enabled in AAP settings
- [ ] Environment variables configured
- [ ] Git project created in AAP
- [ ] Job template created and tested
- [ ] Test run successful with OPA validation output

---

## 🎉 You're Done!

Your AAP 2.6 instance at **AAP_HOST** is now integrated with OPA for compliance validation!

**Next steps:**
1. Create additional compliance check playbooks
2. Schedule regular compliance scans
3. Set up alerting for violations
4. Build compliance dashboards

**For support:**
- Check logs: `sudo journalctl -u opa -f`
- Test OPA: `curl http://localhost:8181/health`
- Review callback output in AAP job logs
