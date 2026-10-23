> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx18, SPLIT-PORTSx18, HOST:8181x2, AAP-2.5/2.6x2, STALE-COUNTx2.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# AAP 2.6 + OPA + PostgreSQL Integration Architecture

**Version:** 2.0
**Last Updated:** March 27, 2026
**Owner:** Tim Coulter & Claude AI
**Review Cycle:** Quarterly

---

## 🏗️ Architecture Overview

AAC is a **policy-as-code compliance platform** built on three tightly integrated components: Ansible Automation Platform (AAP) 2.6 for orchestration and fact collection, Open Policy Agent (OPA) for policy evaluation, and PostgreSQL for historical compliance tracking. Claude Code integrates via an MCP server that exposes 46 AAP tools over HTTP/SSE.

### Production Environment

| Service | Host:Port | Protocol | Purpose |
|---------|-----------|----------|---------|
| AAP Gateway | AAP_HOST:443 | HTTPS | Controller API, EDA, Hub |
| OPA Security | AAP_HOST:8181 | HTTP | CIS, NIST, STIGs — 167 policies |
| OPA Compliance | AAP_HOST:8182 | HTTP | ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, Sentinel — 78 policies |
| OPA OT | AAP_HOST:8183 | HTTP | NERC-CIP, AI Governance, AMI — 32 policies |
| MCP Server | AAP_HOST:8004 | HTTP/SSE | Claude Code integration (46 tools) |
| PostgreSQL | AAP_HOST:5432 | TCP | Compliance facts + results (internal only) |
| Grafana | AAP_HOST:3000 | HTTP | Compliance dashboards |
| Smart Meter Simulator | AAP_HOST:8085 | HTTP | NERC-CIP/AMI demo data (10 meters) |

---

## 🔄 Data Flow Architecture

AAC uses an **evaluate-stored-facts pattern** — OPA is NOT on the live SSH collection hot path. Facts are collected by Ansible and stored in PostgreSQL first, then evaluated against OPA separately. This decoupling is critical for scalability: OPA evaluation volume scales with query frequency, not managed host count.

### Batch Compliance Assessment (Primary Path)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AAP Controller (AAP_HOST)                    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  1. FACT COLLECTION (SSH/WinRM)                                  │    │
│  │     AAP playbooks gather system state from managed hosts         │    │
│  │     (filesystem mounts, services, SSH config, users, ...)        │    │
│  └────────────────────────────┬────────────────────────────────────┘    │
│                               │                                          │
│                               ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  2. FACT STORAGE (PostgreSQL :5432)                              │    │
│  │     Facts written to compliance_facts (JSONB, ~180 KB/system)   │    │
│  └────────────────────────────┬────────────────────────────────────┘    │
│                               │                                          │
│        ┌──────────────────────┼──────────────────────┐                  │
│        ▼                      ▼                       ▼                  │
│  ┌──────────┐          ┌──────────┐           ┌──────────┐              │
│  │  3. OPA  │          │  3. OPA  │           │  3. OPA  │              │
│  │ :8181    │          │ :8182    │           │ :8183    │              │
│  │ Security │          │Compliance│           │   OT     │              │
│  │ 167 pol. │          │  78 pol. │           │  32 pol. │              │
│  └────┬─────┘          └────┬─────┘           └────┬─────┘              │
│       │                     │                       │                    │
│       └─────────────────────┼───────────────────────┘                   │
│                             ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  4. RESULT STORAGE (PostgreSQL :5432)                            │    │
│  │     compliance_results: policy_name, % score, violations (JSONB) │   │
│  └────────────────────────────┬────────────────────────────────────┘    │
│                               │                                          │
│                               ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  5. REPORTING (Grafana :3000 → PostgreSQL)                       │    │
│  │     Historical trends, audit evidence, executive dashboards      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### EDA Real-Time Drift Detection (Secondary Path)

For high-priority security events, Event-Driven Ansible (EDA) and a local OPA sidecar on each execution node provide sub-second policy evaluation without waiting for a scheduled batch run:

```
  File system change detected (inotifywait / auditd)
          │
          ▼
  EDA rulebook fires → Ansible collects current artifact state
          │
          ▼
  Local OPA sidecar (execution node) evaluates policy
          │
          ├─→ COMPLIANT → log to PostgreSQL
          └─→ VIOLATION → alert/remediate immediately

  Trigger categories:
  ┌──────────────────────────────────────────────────────────────────┐
  │ /root/.ssh/authorized_keys, /home/*/.ssh/authorized_keys        │
  │   → authorized_keys module: detect injected SSH keys in minutes  │
  │                                                                   │
  │ /etc/crypttab, /etc/fstab, LUKS volume changes                  │
  │   → storage_encryption module: detect encryption bypass          │
  │                                                                   │
  │ /etc/pki/ca-trust, /etc/ssl/certs                               │
  │   → certificate_validation module: detect rogue CAs              │
  │                                                                   │
  │ /etc/passwd, /etc/shadow, /etc/sudoers                          │
  │   → user_group + sudo modules: detect privilege escalation       │
  └──────────────────────────────────────────────────────────────────┘
```

---

## 🧱 Component Architecture

### Full Stack Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                      Claude Code / AI Agents                      │
│  • MCP Server integration (46 tools)                              │
│  • Natural language automation                                    │
│  • Intelligent policy management                                  │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP/SSE :8004
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│              MCP Server (Model Context Protocol)                   │
│  • AAP API bridge — 46 tools across 9 categories                 │
│  • Inventory, hosts, groups, job templates, jobs, projects        │
│  • Ad-hoc commands, credentials, Ansible Galaxy                   │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTPS :443
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│              Ansible Automation Platform 2.6                       │
│  • Automation Controller — REST API, RBAC, scheduling             │
│  • Event-Driven Ansible (EDA) — drift detection rulebooks         │
│  • Automation Hub — execution environment registry                │
│  • Execution Environments — aac-compliance-ee:v1.0.0-amd64       │
└──────┬──────────────────┬──────────────────────────┬─────────────┘
       │                  │                           │
       │ fact collection  │ policy evaluation         │ results storage
       │ SSH/WinRM        │ HTTP REST                 │ TCP
       ▼                  ▼                           ▼
┌─────────────┐  ┌────────────────────────────┐  ┌───────────────┐
│   Managed   │  │  Three-Container OPA Tier   │  │  PostgreSQL   │
│   Systems   │  │                             │  │     :5432     │
│             │  │  opa-security  :8181        │  │               │
│  RHEL 9     │  │    CIS, NIST, STIGs         │  │ compliance_   │
│  Ubuntu     │  │    167 policies             │  │ facts (JSONB) │
│  Windows    │  │                             │  │               │
│  AWS EC2    │  │  opa-compliance :8182       │  │ compliance_   │
│  Kubernetes │  │    ISO 27001, SOC 2,        │  │ results       │
│  Network    │  │    PCI-DSS, FISMA, Sentinel  │  │ (JSONB)       │
│  OT/SCADA   │  │    78 policies              │  │               │
│             │  │                             │  │ host_facts    │
│             │  │  opa-ot        :8183        │  │               │
│             │  │    NERC-CIP, AMI, AI Gov    │  │ sidecar_      │
│             │  │    32 policies              │  │ datasets      │
└─────────────┘  └────────────────────────────┘  └───────────────┘
```

---

## 🗄️ Three-Container OPA Architecture

### Container Assignment by Framework

| Container | Port | Frameworks | Policies | Use `opa_server_url` |
|-----------|------|-----------|---------|----------------------|
| `opa-security` | 8181 | CIS Benchmarks, NIST SP 800-53, DISA STIGs, Cloud, Containers, Network | 167 | Security scans, CIS assessments |
| `opa-compliance` | 8182 | ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, Corporate, Sentinel, Digital Sovereignty | 78 | Regulatory audits |
| `opa-ot` | 8183 | NERC-CIP (CIP-002–015), AMI/Smart Metering, AI Governance, Crypto Mining Detection | 32 | OT/Critical Infrastructure |

### Key OPA Endpoints

| Framework | Container | Endpoint |
|-----------|-----------|---------|
| CIS RHEL 9 (338 controls) | opa-security | `POST :8181/v1/data/cis_rhel9/compliance_assessment` |
| CIS RHEL 9 Extended Hardening | opa-security | `GET :8181/v1/data/cis_rhel9/extended_hardening_summary` |
| CIS RHEL 9 Storage Encryption | opa-security | `POST :8181/v1/data/cis_rhel9/storage_encryption/compliance_report` |
| CIS RHEL 9 Certificate Validation | opa-security | `POST :8181/v1/data/cis_rhel9/certificate_validation/compliance_report` |
| CIS RHEL 9 Authorized Keys (EDA) | opa-security | `POST :8181/v1/data/cis_rhel9/authorized_keys/compliance_report` |
| NIST SP 800-53 | opa-security | `POST :8181/v1/data/nist_sp_800_53` |
| ISO 27001 | opa-compliance | `POST :8182/v1/data/iso27001` |
| SOC 2 | opa-compliance | `POST :8182/v1/data/soc2` |
| Digital Sovereignty | opa-compliance | `POST :8182/v1/data/digital_sovereignty/<domain>` |
| Sentinel (Ansible) | opa-compliance | `POST :8182/v1/data/sentinel/ansible` |
| Sentinel (Terraform) | opa-compliance | `POST :8182/v1/data/sentinel/terraform` |
| NERC-CIP (full) | opa-ot | `POST :8183/v1/data/nerc_cip_main` |
| CIP-015 INSM | opa-ot | `POST :8183/v1/data/nerc_cip_cip015/cip_015_compliance_report` |
| AI Governance | opa-ot | `POST :8183/v1/data/ai_governance` |

### Policy Library Structure

The `policies/` directory is a **git submodule** → [ynotbhatc/rego_policy_libraries](https://github.com/ynotbhatc/rego_policy_libraries)

```
policies/                          ← submodule (510 policy files, 587 incl. tests)
├── benchmarks/
│   ├── cis/                       ← CIS Benchmarks (200+ files)
│   │   ├── os/linux/rhel_9/       ← 19 files: 14 core CIS + 3 extended hardening
│   │   │                              (storage_encryption, certificate_validation,
│   │   │                               authorized_keys) + orchestrator + base
│   │   ├── os/linux/rhel_8/       ← 14 files
│   │   ├── os/linux/ubuntu_22_04/ ← 15 files
│   │   ├── os/windows/            ← Server 2016/2019/2022, Win 10/11
│   │   ├── cloud/                 ← AWS, Azure, GCP
│   │   ├── containers/            ← Docker, Kubernetes, OpenShift
│   │   ├── databases/             ← MySQL, Oracle, PostgreSQL
│   │   └── network/               ← Cisco, Juniper, Palo Alto, Fortinet, Arista
│   └── stig/                      ← DISA STIGs (8 files)
│
├── frameworks/
│   ├── federal/                   ← NIST, FISMA, FedRAMP, CMMC
│   ├── management/                ← ISO 27001, SOC 2, Corporate
│   ├── financial/                 ← PCI-DSS, SOX
│   ├── privacy/                   ← GDPR, HIPAA
│   ├── critical_infrastructure/   ← NERC-CIP, IEC 62443, AMI/NIST IR 7628
│   └── sovereignty/               ← Digital Sovereignty (7 domains)
│
├── enforcement/                   ← Sentinel: Ansible, Terraform, Dockerfile, K8s, Git
├── governance/                    ← AI governance, MCP tool-call enforcement
└── threat_detection/              ← Crypto miner detection
```

---

## 🔑 CIS RHEL 9 Policy Architecture (100% Coverage)

### 14 Core Modules (338 CIS v2.0.0 Controls)

| # | Module | Section | Controls |
|---|--------|---------|----------|
| 1 | `filesystem_validation` | CIS 1.1 | Partitioning, mount options |
| 2 | `initial_setup_validation` | CIS 1.2, 1.7-1.8 | Banners, GPG, crypto policy |
| 3 | `boot_security_validation` | CIS 1.3-1.5 | AIDE, GRUB, process hardening |
| 4 | `selinux_validation` | CIS 1.6 | SELinux enforcing |
| 5 | `services_validation` | CIS 2 | Unnecessary services |
| 6 | `network_validation` | CIS 3 | Firewall, kernel params |
| 7 | `auditd_validation` | CIS 4.1 | Audit rules |
| 8 | `logging_validation` | CIS 4.2 | rsyslog, journald |
| 9 | `cron_validation` | CIS 5.1 | Job scheduler permissions |
| 10 | `ssh_validation` | CIS 5.2 | SSH server hardening |
| 11 | `sudo_validation` | CIS 5.3 | Privilege escalation |
| 12 | `pam_validation` | CIS 5.4-5.5 | Password policies, account lockout |
| 13 | `file_permissions_validation` | CIS 6.1 | System file permissions |
| 14 | `user_group_validation` | CIS 6.2 | User/group security |

### 3 Extended Hardening Modules (STIG/NIST — separate from CIS score)

These modules cover controls from DISA STIG and NIST SP 800-53 not included in the CIS RHEL 9 v2.0.0 baseline. They are evaluated via `extended_hardening_summary` and do not affect the 338-control `compliant` rule.

| Module | Standards | Primary EDA Drift Trigger |
|--------|-----------|--------------------------|
| `storage_encryption_validation` | STIG RHEL-09-231xxx/672xxx, NIST SC-28 | `/etc/crypttab`, LUKS volume changes |
| `certificate_validation` | NIST SC-17/IA-5/SC-13, CIS 1.8 | `/etc/pki/ca-trust`, `/etc/ssl/certs` |
| `authorized_keys_validation` | CIS 5.2, STIG RHEL-09-255xxx, NIST IA-3 | `/root/.ssh/authorized_keys`, `/home/*/.ssh/authorized_keys` |

**Orchestrator endpoints:**
```
GET  :8181/v1/data/cis_rhel9/compliant                        → true/false (338-control CIS only)
GET  :8181/v1/data/cis_rhel9/hardening_compliant              → true/false (extended only)
GET  :8181/v1/data/cis_rhel9/fully_hardened_compliant         → true/false (CIS + extended)
POST :8181/v1/data/cis_rhel9/extended_hardening_summary       → full extended report
POST :8181/v1/data/cis_rhel9/compliance_assessment            → CIS 338-control assessment
```

---

## 🔌 MCP Server Integration

The MCP server provides Claude Code with 46 tools for direct AAP control via HTTP/SSE.

### Tool Categories

| Category | Count | Key Tools |
|----------|-------|-----------|
| **Inventory** | 4 | `list_inventories`, `create_inventory` |
| **Inventory Sources** | 6 | `sync_inventory_source`, `create_inventory_source` |
| **Hosts** | 7 | `list_hosts`, `get_host_details`, `get_host_facts` |
| **Groups** | 6 | `list_groups`, `create_group`, `add_host_to_group` |
| **Job Templates** | 3 | `list_job_templates`, `create_job_template` |
| **Jobs** | 5 | `run_job`, `job_status`, `job_logs`, `list_jobs` |
| **Ad-Hoc Commands** | 3 | `run_adhoc_command`, `get_adhoc_command_output` |
| **Projects** | 6 | `list_projects`, `update_project` |
| **Ansible Galaxy** | 5 | `search_galaxy_collections`, `suggest_ansible_content` |

### MCP Configuration (~/.claude.json)

```json
{
  "mcpServers": {
    "aap": {
      "type": "sse",
      "url": "http://AAP_HOST:8004/sse",
      "headers": {
        "Authorization": "Bearer <token>"
      }
    }
  }
}
```

**Note:** The MCP token is a gateway-issued bearer token. Rotate via AAP Template 40 (AAC - Rotate MCP Token) when expired.

---

## 🗄️ PostgreSQL Schema

All containers running as Podman on AAP_HOST. Schema managed by the `aac_compliance_db` Ansible role (Template 23).

```sql
-- compliance_facts: raw system facts from AAP (one row per collection run)
CREATE TABLE compliance_facts (
    id                   BIGSERIAL PRIMARY KEY,
    hostname             VARCHAR(255) NOT NULL,
    platform             VARCHAR(50)  NOT NULL,
    facts_version        VARCHAR(20)  NOT NULL DEFAULT '1.0.0',
    collection_timestamp TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    facts_data           JSONB        NOT NULL,       -- ~180 KB per RHEL 9 full scan
    checksum             VARCHAR(64),
    CONSTRAINT unique_hostname_timestamp UNIQUE (hostname, collection_timestamp)
);

-- compliance_results: OPA evaluation outputs per framework per run
CREATE TABLE compliance_results (
    id                    BIGSERIAL PRIMARY KEY,
    policy_name           VARCHAR(255) NOT NULL,
    policy_version        VARCHAR(100) NOT NULL,      -- varchar(100) — NERC-CIP versions are long
    total_controls        INTEGER      NOT NULL,
    passed_controls       INTEGER      NOT NULL,
    failed_controls       INTEGER      NOT NULL,
    compliance_percentage NUMERIC(5,2) NOT NULL,
    violations            JSONB,
    metadata              JSONB,                      -- hostname, platform, org, sovereignty_level, etc.
    assessment_date       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- host_facts: deduplicated latest facts view (via sidecar_datasets for EDA)
-- sidecar_datasets: streaming data from EDA real-time collectors
```

### Key Indexes

```sql
CREATE INDEX idx_results_policy     ON compliance_results(policy_name);
CREATE INDEX idx_results_timestamp  ON compliance_results(assessment_date DESC);
CREATE INDEX idx_results_compliance ON compliance_results(compliance_percentage);
CREATE INDEX idx_results_metadata   ON compliance_results USING GIN (metadata);
CREATE INDEX idx_facts_hostname     ON compliance_facts(hostname);
CREATE INDEX idx_facts_timestamp    ON compliance_facts(collection_timestamp DESC);
CREATE INDEX idx_facts_jsonb        ON compliance_facts USING GIN (facts_data);
```

---

## 📡 Event-Driven Ansible (EDA) Integration

EDA connects real-time system events to AAC policy enforcement:

```yaml
# Example EDA rulebook — authorized_keys drift detection
---
- name: SSH Key Injection Detection
  hosts: all
  sources:
    - name: file_monitor
      ansible.eda.file_watch:
        path: /root/.ssh/authorized_keys
        recursive: false

  rules:
    - name: Authorized keys changed
      condition: event.type == "modified" or event.type == "created"
      action:
        run_job_template:
          name: "EDA - SSH Key Audit"
          extra_vars:
            target_host: "{{ event.src_path | dirname | dirname | basename }}"
            trigger_path: "{{ event.src_path }}"
```

EDA passes collected facts to OPA at `opa-security :8181/v1/data/cis_rhel9/authorized_keys/compliance_report`. If `age_minutes < threshold` and the fingerprint is not in `approved_fingerprints`, the violation fires immediately.

---

## 🔄 Deployment Architecture

### `aac_opa_containers` Role

Manages all three OPA containers via the `aac_opa_containers` Ansible role. Supports horizontal scaling via HAProxy when `replicas > 1`:

```yaml
# Scale security tier to 3 replicas (HAProxy auto-deployed on :8181)
aac_opa_containers:
  - name: opa-security
    port: 8181
    policy_subdir: security
    replicas: 3                # backends: 8191, 8192, 8193
    backend_base_port: 8191
  - name: opa-compliance
    port: 8182
    policy_subdir: compliance
    replicas: 1
    backend_base_port: 8201
  - name: opa-ot
    port: 8183
    policy_subdir: ot
    replicas: 1
    backend_base_port: 8211
```

When `replicas > 1`, HAProxy sits on the canonical port; callers see no URL change.

### Ansible Roles for Infrastructure

| Role | Called By | Purpose |
|------|-----------|---------|
| `aac_opa_containers` | Template 28, Template 80 | Deploy 3 OPA containers, dirs, SELinux, health check, systemd |
| `aac_compliance_db` | Template 23, Template 79, Template 80 | Deploy PostgreSQL, initialize schema, `compliance_reader` role |
| `aac_mcp_server` | Template 80 | Deploy `aap-mcp` container, token via env file, systemd linger |

---

## 🔐 Security Configuration

### Credential Management (Ansible Vault)

All credentials are encrypted in `ansible/vars/vault_secrets.yml`. Never stored as plaintext.

```bash
# View vault contents
ansible-vault view ansible/vars/vault_secrets.yml --vault-password-file ~/.vault_pass

# Edit vault
ansible-vault edit ansible/vars/vault_secrets.yml --vault-password-file ~/.vault_pass
```

| Variable | Purpose |
|----------|---------|
| `compliance_db_password` | PostgreSQL writer (postgres user) |
| `compliance_reader_password` | PostgreSQL read-only user |
| `vault_aap_local_mcp_token` | MCP Bearer token (local AAP) |
| `aws_access_key` / `aws_secret_key` | AWS API credentials |
| `grafana_admin_password` | Grafana admin ($GRAFANA_PASSWORD) |

### RBAC

AAP credentials used by job templates:
- **Credential ID 10:** Ansible Vault — decrypts `vault_secrets.yml`
- **Credential ID 5:** AWS Compliance Lab (encrypted API keys)
- **Credential ID 8:** AWS Lab SSH Key (encrypted private key)
- **EE ID 6:** `aac-compliance-ee:v1.0.0-amd64` — `community.postgresql` + tools

---

## 📊 Monitoring

### Verify All Services

```bash
# OPA health (all three containers)
for port in 8181 8182 8183; do
  echo -n "OPA :$port → "
  curl -s http://AAP_HOST:$port/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))"
done

# OPA policy counts
curl -s http://AAP_HOST:8181/v1/policies | python3 -c "import sys,json; print('security:', len(json.load(sys.stdin)['result']))"
curl -s http://AAP_HOST:8182/v1/policies | python3 -c "import sys,json; print('compliance:', len(json.load(sys.stdin)['result']))"
curl -s http://AAP_HOST:8183/v1/policies | python3 -c "import sys,json; print('ot:', len(json.load(sys.stdin)['result']))"

# MCP server (requires auth)
curl -s --max-time 5 -H "Authorization: Bearer $AAP_TOKEN" \
  http://AAP_HOST:8004/sse | head -c 200

# AAP controller
curl -sk -H "Authorization: Bearer $AAP_TOKEN" \
  https://AAP_HOST/api/controller/v2/ping/ | python3 -m json.tool

# PostgreSQL (via AAP ad-hoc or template)
# Template 38: Sentinel Demo - Pre-flight Check (validates all services)
```

### AAP Templates for Infrastructure Management

| ID | Name | Purpose |
|----|------|---------|
| 25 | AAC - OPA Policy Report | Policy load counts by framework |
| 27 | AAC - Load OPA Policies | Reload all 505 policies into 3 containers |
| 28 | AAC - Deploy OPA Containers | Recreate all 3 containers from scratch |
| 38 | Sentinel Demo - Pre-flight Check | GO/NO-GO all services |
| 39 | AAC - Demo Stability Setup | Install systemd units for all 8 demo containers |
| 40 | AAC - Rotate MCP Token | Token rotation |
| 80 | AAC - Deploy Infrastructure | OPA + DB + MCP in one click |

---

## 🔗 Current Production State (March 27, 2026)

| Component | Status | Details |
|-----------|--------|---------|
| AAP Gateway | ✅ Healthy | https://AAP_HOST/api/gateway/v1/ping/ |
| OPA Security :8181 | ✅ Healthy | 167 policies (CIS, NIST, STIGs) |
| OPA Compliance :8182 | ✅ Healthy | 78 policies (ISO/SOC2/PCI/SOX/FISMA/Sentinel/DS) |
| OPA OT :8183 | ✅ Healthy | 32 policies (NERC-CIP, AI Gov, AMI, crypto detection) |
| PostgreSQL :5432 | ✅ Healthy | compliance_results, compliance_facts, host_facts, sidecar_datasets |
| MCP Server :8004 | ✅ Healthy | SSE endpoint, token in vault_aap_local_mcp_token (rotates) |
| Smart Meter :8085 | ✅ Healthy | 10 meters, NERC-CIP/AMI demo data |
| Grafana :3000 | ✅ Healthy | AMI Compliance Dashboard |
| CIS RHEL 9 | ✅ Complete | 338/338 core controls + 3 extended hardening modules |
| NERC-CIP | ✅ Working | Template 26 end-to-end, CIP-002 through CIP-015 |
| Sentinel Demo | ✅ Working | 5 enforcement points, `demos/sentinel/run_demo.sh` |
| EDA Drift Detection | ✅ Deployed | authorized_keys, storage_encryption, certificate_validation |

---

**Architecture Owner:** Tim Coulter & Claude AI
**Last Updated:** March 27, 2026
**Integration Status:** Production (6/6 validation tests passing)
**Policy Library:** git submodule → ynotbhatc/rego_policy_libraries (505 files)
