> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: HOST:8181x13.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# AAP + OPA Integration Quick Reference
## CIS RHEL 9 Compliance

---

## 🚀 Quick Commands

### OPA Server Management
```bash
# Start OPA server
opa run --server --addr 0.0.0.0:8181 /etc/opa/policies

# Check OPA health
curl http://localhost:8181/health

# List loaded policies
curl http://localhost:8181/v1/policies

# Reload policies (restart service)
sudo systemctl restart opa
```

### Test OPA Policies
```bash
# Test filesystem violations
curl -X POST http://localhost:8181/v1/data/cis_rhel9/filesystem/violations \
  -H "Content-Type: application/json" \
  -d @test_data/mock_facts/webserver_noncompliant.json | jq '.result'

# Get complete compliance report
curl -X POST http://localhost:8181/v1/data/cis_rhel9/report \
  -H "Content-Type: application/json" \
  -d @facts.json | jq '.result'

# Check if compliant
curl -X POST http://localhost:8181/v1/data/cis_rhel9/compliant \
  -d @facts.json | jq '.result'
```

### Run Compliance Checks
```bash
# Check single host
ansible-playbook cis_rhel9_compliance_check.yml -l host01

# Check all hosts in inventory
ansible-playbook cis_rhel9_compliance_check.yml -i production

# Fail on violations
ansible-playbook cis_rhel9_compliance_check.yml \
  -e "OPA_FAIL_ON_VIOLATIONS=true"

# Check specific section only
ansible-playbook cis_rhel9_compliance_check.yml --tags filesystem

# Generate report
./scripts/full_compliance_report.sh /tmp/server_facts.json
```

---

## 📋 Deployment Checklist

### Phase 1: OPA Setup
- [ ] Install OPA binary (`/usr/local/bin/opa`)
- [ ] Create OPA directories:
  - [ ] `/etc/opa/policies/cis_rhel9/`
  - [ ] `/var/lib/opa/`
  - [ ] `/var/log/opa/`
- [ ] Copy CIS RHEL 9 policies to `/etc/opa/policies/cis_rhel9/`
- [ ] Create OPA systemd service
- [ ] Start and enable OPA service
- [ ] Verify OPA health: `curl http://localhost:8181/health`
- [ ] Test policies with mock data

### Phase 2: AAP Integration
- [ ] Copy callback plugin to `/usr/share/ansible/plugins/callback/`
- [ ] Enable callback in AAP Settings → Jobs
- [ ] Add `opa_compliance` to callback whitelist
- [ ] Create fact collection roles (or use existing)
- [ ] Create compliance check playbook
- [ ] Test playbook manually first
- [ ] Create AAP Job Template
- [ ] Configure extra variables (OPA_SERVER_URL)
- [ ] Test job template execution

### Phase 3: Automation
- [ ] Create workflow for scheduled checks
- [ ] Set up schedule (daily/weekly)
- [ ] Configure notifications (email/Slack)
- [ ] Set up facts database (optional)
- [ ] Configure ServiceNow integration (optional)
- [ ] Create remediation playbooks
- [ ] Build compliance dashboard

### Phase 4: Testing
- [ ] Test with compliant server
- [ ] Test with non-compliant server
- [ ] Verify violations are detected
- [ ] Verify reports are generated
- [ ] Test remediation workflows
- [ ] Test failure scenarios

### Phase 5: Production
- [ ] Document procedures
- [ ] Train team members
- [ ] Deploy to production
- [ ] Monitor for issues
- [ ] Review reports regularly

---

## 🔧 Configuration Files

### OPA Systemd Service
**File**: `/etc/systemd/system/opa.service`
```ini
[Unit]
Description=Open Policy Agent
After=network.target

[Service]
Type=simple
User=opa
ExecStart=/usr/local/bin/opa run --server --addr 0.0.0.0:8181 /etc/opa/policies
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

### Ansible Callback Configuration
**File**: `/etc/ansible/ansible.cfg` or AAP Settings
```ini
[defaults]
callback_whitelist = opa_compliance

[callback_opa_compliance]
server_url = http://localhost:8181
fail_on_violations = false
```

### Job Template Extra Variables
```yaml
OPA_SERVER_URL: "http://localhost:8181"
OPA_FAIL_ON_VIOLATIONS: false
```

---

## 🎯 Common Use Cases

### 1. Pre-Production Validation
```yaml
# Before deploying changes
- name: Validate compliance before deployment
  hosts: staging
  tasks:
    - include_tasks: cis_compliance_check.yml
    - fail:
        msg: "Compliance check failed"
      when: not compliant
```

### 2. Continuous Compliance Monitoring
```bash
# Schedule in AAP Workflow
Daily at 2:00 AM:
  1. Collect facts from all RHEL 9 servers
  2. Validate with OPA (automatic via callback)
  3. Generate reports
  4. Send summary email
```

### 3. Change Validation
```yaml
# After making changes
- name: Make system changes
  include_role:
    name: configure_application

- name: Verify still compliant
  include_tasks: cis_compliance_check.yml

- name: Rollback if non-compliant
  when: not compliant
  include_role:
    name: rollback_changes
```

### 4. Audit Preparation
```bash
# Generate compliance evidence
ansible-playbook cis_rhel9_compliance_check.yml \
  -i all_rhel9_hosts \
  --extra-vars "generate_evidence=true"

# Results saved to /var/compliance/reports/
```

---

## 📊 Understanding Results

### Compliance Report Structure
```json
{
  "metadata": {
    "benchmark": "CIS Red Hat Enterprise Linux 9 Benchmark",
    "benchmark_version": "v2.0.0",
    "total_controls_covered": 216
  },
  "compliance": {
    "overall_compliant": false,
    "compliant_sections": 2,
    "total_sections": 5,
    "compliance_percentage": 40,
    "overall_risk_level": "high"
  },
  "violations": {
    "total_count": 15,
    "critical_count": 3,
    "high_count": 7
  }
}
```

### Risk Levels
- **CRITICAL**: Immediate action required (shadow file readable, IP forwarding enabled)
- **HIGH**: Address soon (unnecessary services running, missing mount options)
- **MEDIUM**: Should remediate (minor configuration issues)
- **LOW**: Informational (best practices)

### Section Compliance
- **Section 1.1 (Filesystem)**: Mount options, partitions, filesystem modules
- **Section 2.x (Services)**: Service configuration, unnecessary packages
- **Section 3.x (Network)**: Kernel parameters, IP forwarding, firewall
- **Section 4.2 (Logging)**: rsyslog, journald, log permissions
- **Section 6.1 (File Permissions)**: Critical files, SUID/SGID, ownership

---

## 🐛 Troubleshooting Quick Fixes

### OPA Not Responding
```bash
# Check status
sudo systemctl status opa

# Check logs
sudo journalctl -u opa -f

# Restart service
sudo systemctl restart opa
```

### Callback Plugin Not Working
```bash
# Verify plugin location
ls -la /usr/share/ansible/plugins/callback/opa_compliance.py

# Test import
python3 -c "import sys; sys.path.insert(0, '/usr/share/ansible/plugins/callback'); import opa_compliance"

# Check whitelist
ansible-config dump | grep CALLBACK_WHITELIST
```

### No Violations Detected (False Negative)
```bash
# Verify fact structure
ansible -m setup hostname | grep -A 50 disabled_filesystem_modules

# Test OPA directly
opa eval --data policies/cis_rhel9/ --input facts.json 'data.cis_rhel9.filesystem.violations'

# Check policy syntax
opa test policies/cis_rhel9/
```

### Too Many Violations (Need Filtering)
```bash
# Run specific section only
ansible-playbook cis_rhel9_compliance_check.yml --tags network

# Exclude certain controls
ansible-playbook cis_rhel9_compliance_check.yml \
  --skip-tags "autofs,x11"

# Set baseline exceptions in policies
```

---

## 📞 Support Resources

### Log Locations
- **OPA Logs**: `journalctl -u opa`
- **AAP Job Logs**: AAP UI → Jobs → Select Job → Output
- **Compliance Reports**: `/tmp/cis_compliance_*.json`
- **Fact Files**: `/tmp/ansible_facts_*.json`

### Useful Debug Commands
```bash
# View full OPA evaluation trace
opa eval --explain full --data policies/ --input facts.json 'data.cis_rhel9.report'

# Run playbook in check mode
ansible-playbook cis_rhel9_compliance_check.yml --check

# Increase verbosity
ansible-playbook cis_rhel9_compliance_check.yml -vvv

# Debug callback plugin
export ANSIBLE_CALLBACK_PLUGINS=/usr/share/ansible/plugins/callback
export ANSIBLE_DEBUG=1
ansible-playbook playbook.yml
```

### API Endpoints
| Endpoint | Purpose | Method |
|----------|---------|--------|
| `/health` | OPA health check | GET |
| `/v1/data/cis_rhel9/compliant` | Overall compliance status | POST |
| `/v1/data/cis_rhel9/report` | Complete report | POST |
| `/v1/data/cis_rhel9/filesystem/violations` | Filesystem violations | POST |
| `/v1/data/cis_rhel9/services/violations` | Service violations | POST |
| `/v1/data/cis_rhel9/network/violations` | Network violations | POST |
| `/v1/policies` | List loaded policies | GET |

---

## 📈 Monitoring & Metrics

### Key Metrics to Track
- **Compliance Rate**: Percentage of compliant systems
- **Violation Trends**: Violations over time
- **Time to Remediate**: Average time to fix violations
- **Critical Issues**: Count of critical risk violations
- **Coverage**: Percentage of systems being monitored

### Sample Dashboard Queries
```bash
# Compliance rate
curl -s http://localhost:8181/v1/data/cis_rhel9/compliance_percentage | jq '.result'

# Total violations
curl -s http://localhost:8181/v1/data/cis_rhel9/violations | jq '.result | length'

# Risk level distribution
curl -s http://localhost:8181/v1/data/cis_rhel9/report | \
  jq '.result.violations | group_by(.risk_level) | map({risk: .[0].risk_level, count: length})'
```

---

## ✅ Success Criteria

Your integration is successful when:

1. ✅ OPA server responds to health checks
2. ✅ Policies load without errors
3. ✅ Mock data validation returns expected results
4. ✅ Callback plugin executes during playbook runs
5. ✅ Violations are detected and reported correctly
6. ✅ Reports are generated in correct format
7. ✅ AAP job templates run successfully
8. ✅ Team can interpret compliance reports
9. ✅ Remediation workflows are in place
10. ✅ Regular compliance checks are scheduled

---

**Last Updated**: 2025-10-16
**Version**: 1.0
**Maintainer**: Security & Compliance Team
