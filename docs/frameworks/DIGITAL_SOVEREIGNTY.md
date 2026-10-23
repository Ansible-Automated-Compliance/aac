> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx6, SPLIT-PORTSx6.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Digital Sovereignty Compliance Framework

**Standard:** Digital Sovereignty Assessment
**Policy Location:** `policies/digital_sovereignty/`
**OPA Container:** `opa-compliance` (port 8182)
**Total Controls:** 70 across 7 domains

---

## Overview

Digital sovereignty ensures an organization retains legal and operational control over its data, infrastructure, software, and personnel — free from undue foreign government access or vendor lock-in.

**Applicable Frameworks:**
- ENISA European Digital Sovereignty
- GAIA-X Trust Framework
- FedRAMP High / GovCloud (US)
- BSI C5 (Germany)
- NCSC Cloud Security Principles (UK)
- IRAP Protected (Australia)
- GDPR Chapter V (Data Transfers)

---

## Sovereignty Levels

| Level | Score | Conditions |
|-------|-------|-----------|
| `SOVEREIGN` | 100% | All 7 domains pass, zero critical/high violations |
| `HIGH_ASSURANCE` | ≥85% | No critical violations, ≤2 high violations |
| `MODERATE_ASSURANCE` | 70–84% | No critical violations |
| `LIMITED_ASSURANCE` | 50–69% | Any violation mix |
| `NON_SOVEREIGN` | <50% or any critical | Immediate remediation required |

---

## Policy Files

| File | Package | Controls |
|------|---------|----------|
| `digital_sovereignty_main.rego` | `digital_sovereignty.main` | Aggregator |
| `data_residency.rego` | `digital_sovereignty.data_residency` | DR-001 – DR-010 |
| `cryptographic_sovereignty.rego` | `digital_sovereignty.cryptographic_sovereignty` | CS-001 – CS-011 |
| `infrastructure_sovereignty.rego` | `digital_sovereignty.infrastructure_sovereignty` | IS-001 – IS-010 |
| `software_sovereignty.rego` | `digital_sovereignty.software_sovereignty` | SS-001 – SS-010 |
| `operational_sovereignty.rego` | `digital_sovereignty.operational_sovereignty` | OS-001 – OS-010 |
| `network_sovereignty.rego` | `digital_sovereignty.network_sovereignty` | NS-001 – NS-011 |
| `ai_sovereignty.rego` | `digital_sovereignty.ai_sovereignty` | AI-001 – AI-008 |

---

## Domain Details

### 1. Data Residency (DR-001 – DR-010)

Ensures regulated data stays within approved jurisdictions.

| Control | Description | Severity |
|---------|-------------|----------|
| DR-001 | Regulated data stored only in approved regions | critical |
| DR-002 | Sovereign-classified data not in public cloud | critical |
| DR-003 | Backups stored within approved jurisdiction | high |
| DR-004 | Disaster recovery replicas in approved jurisdiction | high |
| DR-005 | Metadata storage in approved jurisdiction | high |
| DR-006 | Telemetry/logs in approved jurisdiction, no vendor access | high |
| DR-007 | Cross-border transfers only between approved jurisdictions | critical |
| DR-008 | Transfer mechanisms documented for cross-border flows | medium |
| DR-009 | Data flow inventory maintained and recently reviewed | medium |
| DR-010 | Encryption keys for regulated data in approved jurisdiction | critical |

**Key input fields:** `approved_jurisdictions`, `approved_cloud_regions`, `cloud_resources`, `backup_configurations`, `dr_configurations`, `data_flows`, `metadata_storage`, `telemetry_and_logs`

---

### 2. Cryptographic Sovereignty (CS-001 – CS-011)

Ensures cryptographic keys remain under organizational control.

| Control | Description | Severity |
|---------|-------------|----------|
| CS-001 | Customer-managed keys (BYOK) for sensitive/sovereign data | critical |
| CS-002 | HYOK (Hold Your Own Key) required for sovereign-classified data | critical |
| CS-003 | No unencrypted regulated data at rest | critical |
| CS-004 | Encryption keys stored in approved jurisdiction | critical |
| CS-005 | HSM deployed (FIPS 140-2 Level 3 or higher) | high |
| CS-006 | No HSM vendor backdoor access | critical |
| CS-007 | Key rotation policy documented (≤365 days), dual control enforced | high |
| CS-008 | No key escrow with foreign entities | critical |
| CS-009 | Code signing implemented, private key in approved jurisdiction | high |
| CS-010 | Only approved encryption algorithms in use | critical |
| CS-011 | TLS 1.2+ enforced, no weak cipher suites | high |

**Key input fields:** `cloud_resources`, `hsm_configuration`, `key_management_policies`, `encryption_standards`, `encrypted_resources_in_transit`, `code_signing`

---

### 3. Infrastructure Sovereignty (IS-001 – IS-010)

Ensures physical and logical infrastructure remains under sovereign control.

| Control | Description | Severity |
|---------|-------------|----------|
| IS-001 | Foreign CLOUD Act / surveillance law risk mitigated (encryption before upload) | high |
| IS-002 | Sovereign workloads not subject to unmitigated foreign government access | critical |
| IS-003 | Single cloud provider ≤ configured concentration limit | high |
| IS-004 | Total foreign provider exposure ≤ configured limit | high |
| IS-005 | Critical hardware supply chain audited | high |
| IS-006 | No known hardware backdoors in critical components | critical |
| IS-007 | Firmware origin acceptable (approved jurisdiction or audited) | high |
| IS-008 | DNS and CDN under sovereign control | medium |
| IS-009 | Exit strategy documented and portability tested | medium |
| IS-010 | Data portability uses open formats | medium |

**Key input fields:** `infrastructure_components`, `cloud_providers`, `hardware_components`, `network_infrastructure`, `concentration_limits`, `exit_strategy`

---

### 4. Software Sovereignty (SS-001 – SS-010)

Ensures software provenance, update control, and supply chain integrity.

| Control | Description | Severity |
|---------|-------------|----------|
| SS-001 | SBOM maintained in SPDX or CycloneDX format | high |
| SS-002 | SBOM coverage ≥95%, updated within 30 days | medium |
| SS-003 | Critical software from approved jurisdiction or fully audited | high |
| SS-004 | No uncontrolled automatic vendor updates | critical |
| SS-005 | Software update sources within approved jurisdiction | high |
| SS-006 | Vendor telemetry disabled or controllable | high |
| SS-007 | All artifacts signed with keys in approved jurisdiction | critical |
| SS-008 | Integrity verified (hash validation) on every deployment | critical |
| SS-009 | Private package registry in approved jurisdiction, dependencies pinned | high |
| SS-010 | Source code repositories hosted in approved jurisdiction | high |

**Key input fields:** `software_components`, `sbom`, `update_mechanisms`, `code_repositories`, `software_provenance`, `dependency_management`

---

### 5. Operational Sovereignty (OS-001 – OS-010)

Ensures personnel and operational procedures prevent unauthorized foreign access.

| Control | Description | Severity |
|---------|-------------|----------|
| OS-001 | All privileged personnel security-vetted | critical |
| OS-002 | Privileged personnel located in approved jurisdiction | high |
| OS-003 | No privileged access for personnel with foreign government connections | critical |
| OS-004 | All vendor access monitored, logged, and recorded | high |
| OS-005 | Vendor access to sensitive data requires explicit approval | high |
| OS-006 | Support contracts include right to refuse foreign government access | high |
| OS-007 | PAM solution deployed with credential vaulting and session recording | high |
| OS-008 | Foreign access request policy documented with legal review | high |
| OS-009 | Remote operations use in-jurisdiction VPN and jump hosts only | high |
| OS-010 | Privileged access reviews conducted at least quarterly | medium |

**Key input fields:** `personnel`, `vendor_access`, `support_contracts`, `privileged_access_management`, `foreign_access_requests`, `remote_operations`

---

### 6. Network Sovereignty (NS-001 – NS-011)

Ensures network routing, DNS, and traffic remain under sovereign control.

| Control | Description | Severity |
|---------|-------------|----------|
| NS-001 | DNS resolver under organizational control in approved jurisdiction | critical |
| NS-002 | DNSSEC enabled | high |
| NS-003 | Public/foreign DNS providers blocked | high |
| NS-004 | RPKI deployed with route origin validation | high |
| NS-005 | BGP peers reviewed, routes documented | medium |
| NS-006 | Sensitive traffic encrypted if transiting foreign countries | critical |
| NS-007 | Internet egress through single inspected point in approved jurisdiction | high |
| NS-008 | NetFlow/traffic monitoring with ≥90-day retention | medium |
| NS-009 | Network anomaly detection enabled | high |
| NS-010 | Alerting on unexpected foreign destination connections | high |
| NS-011 | All regulated network segments in approved jurisdictions, encrypted | high |

**Key input fields:** `bgp_configuration`, `dns_configuration`, `internet_egress`, `traffic_routing`, `network_monitoring`, `network_segments`, `private_connectivity`

---

### 7. AI/ML Sovereignty (AI-001 – AI-008)

Ensures AI services and ML pipelines do not expose data to foreign control.

| Control | Description | Severity |
|---------|-------------|----------|
| AI-001 | Regulated data not sent to foreign-controlled SaaS AI services | critical |
| AI-002 | Training opt-out enabled for all AI services | high |
| AI-003 | AI provider data retention ≤30 days | high |
| AI-004 | AI inference runs within approved jurisdiction | high |
| AI-005 | ML training data stays within approved jurisdiction | critical |
| AI-006 | ML training infrastructure in approved jurisdiction | high |
| AI-007 | Foreign-government-origin ML models audited for backdoors | critical |
| AI-008 | AI governance policy documented with shadow AI controls and human oversight | high |

**Key input fields:** `ai_services`, `ml_training`, `ml_models`, `ai_governance`, `ai_output_controls`

---

## OPA API Usage

**Load policies into OPA:**
```bash
# Load all digital sovereignty policies
cd policies/digital_sovereignty/
for policy in *.rego; do
  curl -X PUT --data-binary @"$policy" \
    "http://AAP_HOST:8182/v1/policies/$(basename $policy .rego)"
done
```

**Run full assessment:**
```bash
curl -X POST http://AAP_HOST:8182/v1/data/digital_sovereignty/main/report \
  -H 'Content-Type: application/json' \
  -d @examples/digital_sovereignty/compliant.json | jq .
```

**Check overall compliance only:**
```bash
curl -X POST http://AAP_HOST:8182/v1/data/digital_sovereignty/main/overall_compliant \
  -H 'Content-Type: application/json' \
  -d @examples/digital_sovereignty/compliant.json
```

**Check sovereignty level:**
```bash
curl -X POST http://AAP_HOST:8182/v1/data/digital_sovereignty/main/sovereignty_level \
  -H 'Content-Type: application/json' \
  -d @examples/digital_sovereignty/compliant.json
```

**Query a single domain:**
```bash
# Data residency only
curl -X POST http://AAP_HOST:8182/v1/data/digital_sovereignty/data_residency/report \
  -H 'Content-Type: application/json' \
  -d @examples/digital_sovereignty/compliant.json
```

---

## Report Structure

```json
{
  "standard": "Digital Sovereignty Assessment",
  "overall_compliant": true,
  "sovereignty_level": "SOVEREIGN",
  "sovereignty_score": 100,
  "domains_passing": 7,
  "domains_total": 7,
  "domains": {
    "data_residency":              { "compliant": true,  "details": { ... } },
    "cryptographic_sovereignty":   { "compliant": true,  "details": { ... } },
    "infrastructure_sovereignty":  { "compliant": true,  "details": { ... } },
    "software_sovereignty":        { "compliant": true,  "details": { ... } },
    "operational_sovereignty":     { "compliant": true,  "details": { ... } },
    "network_sovereignty":         { "compliant": true,  "details": { ... } },
    "ai_sovereignty":              { "compliant": true,  "details": { ... } }
  },
  "violation_summary": {
    "total": 0,
    "critical": 0,
    "high": 0,
    "medium": 0
  },
  "applicable_frameworks": [ "ENISA European Digital Sovereignty", "..." ]
}
```

---

## Ansible Integration

```yaml
- name: Digital Sovereignty Assessment
  hosts: localhost
  connection: local
  vars:
    opa_server_url: "http://AAP_HOST:8182"
    sovereignty_input: "{{ lookup('file', 'examples/digital_sovereignty/compliant.json') | from_json }}"

  tasks:
    - name: Run digital sovereignty assessment
      uri:
        url: "{{ opa_server_url }}/v1/data/digital_sovereignty/main/report"
        method: POST
        body_format: json
        body: "{{ sovereignty_input }}"
      register: sovereignty_result

    - name: Show sovereignty level
      debug:
        msg: "Sovereignty Level: {{ sovereignty_result.json.result.sovereignty_level }} ({{ sovereignty_result.json.result.sovereignty_score }}%)"

    - name: Fail if non-sovereign
      fail:
        msg: "Organization is NON_SOVEREIGN — {{ sovereignty_result.json.result.violation_summary.critical }} critical violations"
      when: sovereignty_result.json.result.sovereignty_level == "NON_SOVEREIGN"
```

---

## Example Data

Pre-built examples are in `examples/digital_sovereignty/`:

| File | Description |
|------|-------------|
| `compliant.json` | Australian government scenario — all 7 domains pass (SOVEREIGN) |
| `non_compliant.json` | Common failure scenarios — demonstrates violation detection |

Use these as templates for building organization-specific assessment inputs.

---

## Adding to AAP

To add digital sovereignty assessments to AAP job templates, reference:
- **OPA Container:** `opa-compliance` on port 8182
- **Policy endpoint:** `/v1/data/digital_sovereignty/main/report`
- **Credential:** Vault credential ID 10 for any secrets
- **Example playbook pattern:** See Ansible Integration section above
