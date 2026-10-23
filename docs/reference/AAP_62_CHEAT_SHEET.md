> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: HOST:8181x22, RETIRED-HOSTx13.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# AAP + OPA Cheat Sheet
## Server: AAP_HOST

---

## 🔗 Quick Access

| Service | URL | Port |
|---------|-----|------|
| AAP Web UI | `https://AAP_HOST` | 443 |
| OPA Server | `http://localhost:8181` (from AAP server) | 8181 |
| OPA Health | `http://localhost:8181/health` | 8181 |

---

## ⚡ Common Commands

### Check OPA Status
```bash
# SSH to AAP
ssh admin@AAP_HOST

# Check OPA service
sudo systemctl status opa

# View logs
sudo journalctl -u opa -f
```

### Quick OPA Queries
```bash
# Health check
curl http://localhost:8181/health

# List policies
curl http://localhost:8181/v1/policies | jq '.'

# Test with mock data
curl -X POST http://localhost:8181/v1/data/cis_rhel9/filesystem/violations \
  -H "Content-Type: application/json" \
  -d '{"input": {"disabled_filesystem_modules": {"modules": [], "all_compliant": true}}}' \
  | jq '.result'
```

### Validate Facts File
```bash
# Upload facts and validate
scp facts.json admin@AAP_HOST:/tmp/

# SSH and validate
ssh admin@AAP_HOST
curl -X POST http://localhost:8181/v1/data/cis_rhel9/report \
  -d @/tmp/facts.json | jq '.result'
```

---

## 📊 API Endpoints

### CIS RHEL 9 Policies

| Endpoint | Purpose | Returns |
|----------|---------|---------|
| `/v1/data/cis_rhel9/compliant` | Overall compliance | `true` or `false` |
| `/v1/data/cis_rhel9/all_violations` | All violations | Array of strings |
| `/v1/data/cis_rhel9/report` | Complete report | Full compliance report |
| `/v1/data/cis_rhel9/filesystem/violations` | Filesystem violations | Array |
| `/v1/data/cis_rhel9/logging/violations` | Logging violations | Array |
| `/v1/data/cis_rhel9/file_permissions/violations` | File permission violations | Array |
| `/v1/data/cis_rhel9/services/violations` | Service violations | Array |
| `/v1/data/cis_rhel9/network/violations` | Network violations | Array |

### Example Usage
```bash
# Check if compliant
curl -X POST http://localhost:8181/v1/data/cis_rhel9/compliant \
  -d @facts.json | jq '.result'

# Get all violations
curl -X POST http://localhost:8181/v1/data/cis_rhel9/all_violations \
  -d @facts.json | jq '.result'

# Get full report
curl -X POST http://localhost:8181/v1/data/cis_rhel9/report \
  -d @facts.json | jq '.result.compliance'
```

---

## 🎮 Run from AAP

### Web UI
```
1. Go to: https://AAP_HOST
2. Login with your credentials
3. Navigate: Resources → Templates
4. Select: Your compliance template
5. Click: Launch
6. Monitor: Output for OPA validation
```

### API
```bash
# Set credentials
export AAP_TOKEN=$AAP_TOKEN

# Launch job
curl -X POST "https://AAP_HOST/api/controller/v2/job_templates/TEMPLATE_ID/launch/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  --insecure

# Check job status
curl -X GET "https://AAP_HOST/api/controller/v2/jobs/JOB_ID/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  --insecure
```

---

## 🔍 Sample Queries

### 1. Quick Compliance Check
```bash
cat > /tmp/quick_check.json <<'EOF'
{
  "hostname": "test-server",
  "collection_timestamp": "2025-10-16T10:00:00Z",
  "disabled_filesystem_modules": {
    "modules": [
      {"module": "cramfs", "loaded": false, "disabled": true, "compliant": true},
      {"module": "squashfs", "loaded": false, "disabled": true, "compliant": true}
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

curl -X POST http://localhost:8181/v1/data/cis_rhel9/filesystem/violations \
  -d @/tmp/quick_check.json | jq '.result'
```

### 2. Get Section Summary
```bash
# Check which sections are compliant
for section in filesystem logging file_permissions services network; do
  echo "=== $section ==="
  curl -s -X POST http://localhost:8181/v1/data/cis_rhel9/${section}/violations \
    -d @facts.json | jq '.result | length'
done
```

### 3. Generate HTML Report
```bash
# Get report and format as HTML
curl -X POST http://localhost:8181/v1/data/cis_rhel9/report \
  -d @facts.json | jq -r '.result |
  "<h1>Compliance Report</h1>
  <p>Host: \(.metadata.hostname // "N/A")</p>
  <p>Status: \(.compliance.overall_compliant)</p>
  <p>Violations: \(.violations.total_count)</p>
  <p>Risk Level: \(.compliance.overall_risk_level)</p>"' > report.html
```

---

## 🛠️ Troubleshooting

### OPA Not Responding
```bash
# Check service
sudo systemctl status opa

# Restart
sudo systemctl restart opa

# View logs
sudo journalctl -u opa -n 100
```

### Policy Not Found
```bash
# List loaded policies
curl http://localhost:8181/v1/policies | jq '.result[].id'

# Check policy directory
ls -la /etc/opa/policies/cis_rhel9/

# Reload policies
sudo systemctl restart opa
```

### Validation Returns Empty
```bash
# Check input structure
cat facts.json | jq '.'

# Test with minimal input
echo '{"input": {}}' | \
  curl -X POST http://localhost:8181/v1/data/cis_rhel9/compliant -d @-

# View policy evaluation trace
opa eval --explain full \
  --data /etc/opa/policies/cis_rhel9/ \
  --input facts.json \
  'data.cis_rhel9.filesystem.violations'
```

---

## 📋 Compliance Report Structure

```json
{
  "metadata": {
    "benchmark": "CIS Red Hat Enterprise Linux 9 Benchmark",
    "benchmark_version": "v2.0.0",
    "total_controls_covered": 216,
    "evaluation_timestamp": "..."
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
    "high_count": 7,
    "all_violations": ["...", "..."]
  },
  "section_compliance": {
    "section_1_1_filesystem": {
      "compliant": false,
      "violation_count": 3
    },
    ...
  },
  "recommendations": [
    {
      "priority": "critical",
      "section": "File Permissions",
      "issue": "...",
      "action": "..."
    }
  ]
}
```

---

## 🎯 One-Liners

```bash
# Quick health check
curl -s http://localhost:8181/health && echo "✓ OPA is healthy"

# Count total violations
curl -s -X POST http://localhost:8181/v1/data/cis_rhel9/all_violations \
  -d @facts.json | jq '.result | length'

# Check if compliant (exit 0 if yes, 1 if no)
curl -s -X POST http://localhost:8181/v1/data/cis_rhel9/compliant \
  -d @facts.json | jq -e '.result' > /dev/null && echo "COMPLIANT" || echo "NON-COMPLIANT"

# Get risk level
curl -s -X POST http://localhost:8181/v1/data/cis_rhel9/report \
  -d @facts.json | jq -r '.result.compliance.overall_risk_level'

# List all violations
curl -s -X POST http://localhost:8181/v1/data/cis_rhel9/all_violations \
  -d @facts.json | jq -r '.result[]'
```

---

## 🔐 Security Notes

1. **OPA Port**: Only accessible from localhost (127.0.0.1) by default
2. **AAP Access**: Use HTTPS and valid credentials
3. **Facts Data**: May contain sensitive system information
4. **API Tokens**: Rotate regularly, use with caution

---

## 📞 Quick Support

```bash
# Check all services
sudo systemctl status opa aap-controller

# View recent logs
sudo journalctl -xe | tail -50

# Test network connectivity
ping -c 1 AAP_HOST
curl -I https://AAP_HOST

# Validate OPA policies
opa test /etc/opa/policies/cis_rhel9/
```

---

## 🚀 Example Workflow

```bash
# 1. Collect facts from target
ansible target_host -m setup > /tmp/facts.json

# 2. Upload to AAP server
scp /tmp/facts.json admin@AAP_HOST:/tmp/

# 3. SSH to AAP
ssh admin@AAP_HOST

# 4. Validate with OPA
curl -X POST http://localhost:8181/v1/data/cis_rhel9/report \
  -d @/tmp/facts.json | jq '.result.compliance'

# 5. View violations
curl -X POST http://localhost:8181/v1/data/cis_rhel9/all_violations \
  -d @/tmp/facts.json | jq -r '.result[]'
```

---

## 📚 Additional Resources

- **Full Integration Guide**: `AAP_OPA_UNIVERSAL_INTEGRATION.md`
- **Deployment Guide**: `AAP_62_DEPLOYMENT_GUIDE.md`
- **Usage Guide**: `AAP_62_USAGE_GUIDE.md`
- **OPA Documentation**: https://www.openpolicyagent.org/docs/
- **AAP Documentation**: https://docs.ansible.com/automation-controller/

---

**Server**: AAP_HOST
**OPA Endpoint**: http://localhost:8181
**Status**: ✅ Operational
