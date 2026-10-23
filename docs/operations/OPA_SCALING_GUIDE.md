> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: SPLIT-PORTSx25, RETIRED-HOSTx14, HOST:8181x4, STALE-COUNTx4, AAP-2.5/2.6x3, BROKEN-LINKSx3, OLD-CLUSTER-IDx2, OLD-AAC-VERx1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# OPA Scaling Guide for Enterprise Compliance

**Authors:** Tim Coulter & Claude
**Date:** April 6, 2026
**Version:** 3.2
**Repository:** https://github.com/ansible-automated-compliance/aac

## Horizontal Scaling and Performance Optimization for Large Environments
## Complete Architecture with PostgreSQL Database Integration

### Overview

This guide provides comprehensive sizing requirements and scaling strategies for deploying Open Policy Agent (OPA) in large enterprise environments with thousands of nodes and multiple compliance frameworks.

AAC uses a **three-container OPA architecture** — one container per compliance domain — to isolate policy sets, reduce blast radius, and optimize evaluation performance for different workload types.

**Part of the Ansible Automated Compliance (AAC) System** — See the main repository for:
- Ansible playbooks and AAP job templates
- 505 Rego policies across 50+ frameworks (CIS, NIST, STIGs, ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, NERC-CIP, Digital Sovereignty, Sentinel, and more)
- PostgreSQL schema and compliance history
- AAP 2.6 integration guides
- Complete documentation

### Related Documentation

- **[COMPLETE_INSTALLATION_GUIDE.md](../install/COMPLETE_INSTALLATION_GUIDE.md)** — Full system installation
- **[AAP_OPA_INTEGRATION_ARCHITECTURE.md](../architecture/AAP_OPA_INTEGRATION_ARCHITECTURE.md)** — Integration architecture
- **[ENTERPRISE_ARCHITECTURE.md](../architecture/ENTERPRISE_ARCHITECTURE.md)** — Enterprise deployment patterns

---

## 🏛️ AAC Three-Container OPA Architecture

### Production Architecture (Current Deployment)

AAC deploys three purpose-specific OPA containers, each serving a distinct compliance domain:

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Ansible Automation Platform 2.6                    │
│              (Fact collection, orchestration, scheduling)             │
└─────────────────┬───────────────────┬──────────────────┬─────────────┘
                  │                   │                  │
                  ▼                   ▼                  ▼
    ┌─────────────────────┐ ┌──────────────────┐ ┌──────────────────┐
    │    opa-security     │ │  opa-compliance  │ │     opa-ot       │
    │      :8181          │ │     :8182        │ │     :8183        │
    │                     │ │                  │ │                  │
    │  CIS Benchmarks     │ │  ISO 27001       │ │  NERC-CIP        │
    │  NIST SP 800-53     │ │  SOC 2           │ │  (CIP-002–015)   │
    │  DISA STIGs         │ │  PCI-DSS         │ │  AI Governance   │
    │  Cloud Security     │ │  SOX / FISMA     │ │  OT Security     │
    │  Container/K8s      │ │  Corporate       │ │  AMI (Smart      │
    │  Network Devices    │ │  Sentinel        │ │    Metering)     │
    │  OS Hardening       │ │  Digital         │ │  Crypto Mining   │
    │                     │ │  Sovereignty     │ │  Detection       │
    │                     │ │                  │ │                  │
    │  223 policies       │ │  89 policies     │ │  42 policies     │
    └──────────┬──────────┘ └────────┬─────────┘ └────────┬─────────┘
               │                    │                     │
               └────────────────────┼─────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   PostgreSQL (compliance DB)  │
                    │   compliance_results (JSONB)  │
                    │   compliance_facts (JSONB)    │
                    │   Historical trending data    │
                    └───────────────────────────────┘
```

### Container Assignment by Framework

| Container | Port | Frameworks | Policies |
|-----------|------|-----------|---------|
| `opa-security` | 8181 | CIS Benchmarks, NIST, STIGs, Cloud, Containers, Network Devices, OS, Mobile | 223 |
| `opa-compliance` | 8182 | ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, Corporate, Sentinel Policy Enforcement, Digital Sovereignty | 89 |
| `opa-ot` | 8183 | NERC-CIP (CIP-002 to CIP-015), AI Governance, AMI/Smart Metering, Crypto Mining Detection | 42 |

### Choosing the Right Container

```yaml
# Security scans (CIS Benchmarks, NIST, STIGs):
opa_server_url: "http://AAP_HOST:8181"

# Regulatory compliance (ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, Digital Sovereignty):
opa_server_url: "http://AAP_HOST:8182"

# OT / Critical Infrastructure (NERC-CIP, AMI, smart metering):
opa_server_url: "http://AAP_HOST:8183"
```

### Key OPA Endpoints by Framework

| Framework | Container | Endpoint |
|-----------|-----------|---------|
| CIS RHEL 9 | opa-security | `POST :8181/v1/data/cis_rhel9/compliance_assessment` |
| CIS RHEL 9 Extended Hardening | opa-security | `GET :8181/v1/data/cis_rhel9/extended_hardening_summary` |
| CIS RHEL 9 Storage Encryption | opa-security | `POST :8181/v1/data/cis_rhel9/storage_encryption/compliance_report` |
| CIS RHEL 9 Certificates | opa-security | `POST :8181/v1/data/cis_rhel9/certificate_validation/compliance_report` |
| CIS RHEL 9 Authorized Keys (EDA) | opa-security | `POST :8181/v1/data/cis_rhel9/authorized_keys/compliance_report` |
| NIST SP 800-53 | opa-security | `POST :8181/v1/data/nist_sp_800_53` |
| ISO 27001 | opa-compliance | `POST :8182/v1/data/iso27001` |
| Digital Sovereignty | opa-compliance | `POST :8182/v1/data/digital_sovereignty/<domain>` |
| Sentinel Ansible | opa-compliance | `POST :8182/v1/data/sentinel/ansible/result` |
| Sentinel Terraform | opa-compliance | `POST :8182/v1/data/sentinel/terraform/result` |
| NERC-CIP | opa-ot | `POST :8183/v1/data/nerc_cip_main` |
| CIP-015 INSM | opa-ot | `POST :8183/v1/data/nerc_cip_cip015/cip_015_compliance_report` |

### Data Flow

**Batch evaluation (primary path — PostgreSQL-stored facts):**
```
1. Ansible playbook runs     → Collects facts from target systems via SSH
2. Facts stored              → Written to PostgreSQL compliance_facts (JSONB)
3. OPA evaluates policy      → Stored facts POSTed to appropriate OPA container
4. Results stored            → Written to PostgreSQL compliance_results (JSONB)
5. Reporting                 → Grafana dashboards query PostgreSQL
```

> **Important:** OPA is NOT on the live SSH collection hot path. Facts are stored first in PostgreSQL, then evaluated against OPA. This means OPA horizontal scaling is driven by evaluation query volume, not by the number of managed hosts.

**EDA real-time drift detection (secondary path — execution node sidecar):**
```
1. File change detected      → inotifywait/auditd fires on /root/.ssh, /etc/crypttab, etc.
2. EDA rulebook triggers     → Ansible collects current state of changed artifact
3. Local OPA sidecar         → Facts POSTed to execution-node-local OPA (sub-second latency)
4. Drift evaluated           → Authorized keys injection? Encryption removed? Cert revoked?
5. Remediate/alert           → OPA decision drives immediate response before central sync
```

**Drift detection trigger categories:**
| Trigger | File/Resource | Policy Module |
|---------|--------------|---------------|
| SSH key injection | `/root/.ssh/authorized_keys`, `/home/*/.ssh/authorized_keys` | `authorized_keys` |
| Storage encryption change | `/etc/crypttab`, `/etc/fstab`, LUKS volume add/remove | `storage_encryption` |
| Certificate revocation/expiry | `/etc/pki/ca-trust`, `/etc/ssl/certs` | `certificate_validation` |
| Password file modification | `/etc/passwd`, `/etc/shadow` | `pam`, `user_group` |

---

## 📦 Policy Inventory (505 Rego Files)

### By Framework

| Category | Files | Container |
|----------|-------|-----------|
| CIS Benchmarks | 200+ | opa-security |
| SOC 2 | 11 | opa-compliance |
| DISA STIGs | 8 | opa-security |
| OS Policies | 6 | opa-security |
| ISO 27001 | 6 | opa-compliance |
| NIST | 5 | opa-security |
| CIS Oracle | 5 | opa-security |
| SOX | 4 | opa-compliance |
| FISMA | 4 | opa-compliance |
| Corporate | 4 | opa-compliance |
| Digital Sovereignty | 10+ | opa-compliance |
| Server Software | 3 | opa-security |
| PCI-DSS | 3 | opa-compliance |
| NERC-CIP + AMI + IEC 62443 | 18+ | opa-ot |
| Sentinel | 2 | opa-compliance |
| GDPR / HIPAA / Privacy | 14+ | opa-compliance |
| AI Governance + MCP | 6 | opa-ot / opa-compliance |
| Threat Detection | 1 | opa-ot |
| Other | Various | Various |

### CIS Benchmark Coverage

| Platform | Files | Coverage |
|----------|-------|---------|
| RHEL 9 | 19 (14 core + 3 extended hardening + orchestrator + base) | 338/338 controls (100%) ✅ + STIG/NIST extended |
| RHEL 8 | 14 | Full |
| Ubuntu 22.04 | 15 | Full |
| Ubuntu 20.04 | 15 | Full |
| Debian 11 | 15 | Full |
| Rocky Linux 8 | 14 | Full |
| Windows Server 2022 | 10 | Modular |
| Windows Server 2019 | 10 | Modular |
| Network Devices | 5 | Cisco, Juniper, Fortinet, Palo Alto, Arista |
| Cloud (AWS/Azure/GCP) | 3 | Foundations |
| Containers (Docker/K8s) | 2 | Full |
| PostgreSQL | 3 | v13, v14, v15 |

### Digital Sovereignty Framework

9 domains, 90 controls total:

| Domain | Controls | Key Frameworks |
|--------|----------|----------------|
| Data Residency | 10 | GDPR Ch.V, IRAP, DPDP |
| Cryptographic Sovereignty | 11 | BSI C5, FedRAMP, ENISA |
| Infrastructure Sovereignty | 13 | GAIA-X, CLOUD Act mitigation |
| Software Sovereignty | 10 | ENISA, SBOM (CycloneDX/SPDX) |
| Operational Sovereignty | 10 | IRAP, NCSC, personnel vetting |
| Network Sovereignty | 11 | BGP/RPKI, DNSSEC, egress control |
| AI/ML Sovereignty | 10 | ENISA AI Act, shadow AI controls |
| Breach Notification Sovereignty | 10 | GDPR Art. 33, NIS2, APRA CPS 234 |
| Geopolitical Event Triggers | 5 | IRAP, NCSC, country exit procedures |

Sovereignty levels (ascending): `NON_SOVEREIGN` → `LIMITED_ASSURANCE` → `MODERATE_ASSURANCE` → `HIGH_ASSURANCE` → `SOVEREIGN`

---

## 🗄️ PostgreSQL Database Architecture

### Deployed Schema

The production database is a single PostgreSQL 15 instance running as a Podman container on the AAP controller (AAP_HOST, port 5432).

```sql
-- Compliance Results (all framework assessments stored here)
-- Policy version is varchar(100) to accommodate long version strings
CREATE TABLE compliance_results (
    id BIGSERIAL PRIMARY KEY,
    policy_name VARCHAR(255) NOT NULL,
    policy_version VARCHAR(100) NOT NULL,
    total_controls INTEGER NOT NULL,
    passed_controls INTEGER NOT NULL,
    failed_controls INTEGER NOT NULL,
    compliance_percentage NUMERIC(5,2) NOT NULL,
    violations JSONB,
    metadata JSONB,
    assessment_date TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Key metadata fields stored in JSONB per framework:
-- CIS/NIST/STIG:    hostname, platform, os_version, ip_address
-- Digital Sovereignty: organization, sovereignty_level, domains_assessed, domains_passing,
--                      critical_count, high_count, input_file
-- NERC-CIP:         bes_cyber_system_count, cip_version, environment
-- AMI:              framework (nist_ir7628|device|headend), meter_count

-- Compliance Facts (raw system facts from Ansible)
CREATE TABLE compliance_facts (
    id BIGSERIAL PRIMARY KEY,
    hostname VARCHAR(255) NOT NULL,
    platform VARCHAR(50) NOT NULL,
    facts_version VARCHAR(20) NOT NULL DEFAULT '1.0.0',
    collection_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    facts_data JSONB NOT NULL,
    checksum VARCHAR(64),
    CONSTRAINT unique_hostname_timestamp UNIQUE (hostname, collection_timestamp)
);

-- Indexes
CREATE INDEX idx_results_policy ON compliance_results(policy_name);
CREATE INDEX idx_results_timestamp ON compliance_results(assessment_date DESC);
CREATE INDEX idx_results_compliance ON compliance_results(compliance_percentage);
CREATE INDEX idx_results_metadata ON compliance_results USING GIN (metadata);
CREATE INDEX idx_facts_hostname ON compliance_facts(hostname);
CREATE INDEX idx_facts_timestamp ON compliance_facts(collection_timestamp DESC);
CREATE INDEX idx_facts_jsonb ON compliance_facts USING GIN (facts_data);
```

### Sample Queries

```sql
-- Latest Digital Sovereignty assessments by organization
SELECT
    metadata->>'organization' AS org,
    metadata->>'sovereignty_level' AS level,
    compliance_percentage,
    assessment_date
FROM compliance_results
WHERE policy_name = 'Digital Sovereignty'
ORDER BY assessment_date DESC
LIMIT 10;

-- Compliance trend for a specific framework
SELECT
    DATE_TRUNC('day', assessment_date) AS day,
    AVG(compliance_percentage) AS avg_pct,
    COUNT(*) AS runs
FROM compliance_results
WHERE policy_name = 'NERC-CIP'
GROUP BY 1 ORDER BY 1 DESC;

-- Systems with critical violations
SELECT
    metadata->>'hostname' AS host,
    policy_name,
    (metadata->>'critical_count')::int AS criticals,
    assessment_date
FROM compliance_results
WHERE (metadata->>'critical_count')::int > 0
ORDER BY criticals DESC, assessment_date DESC;
```

### Database Sizing Requirements

#### Small Environment (1–100 Nodes)
- **PostgreSQL Instance**: 1 primary (Podman container)
- **CPU**: 4 vCPU
- **Memory**: 8 GB RAM
- **Storage**: 50 GB SSD
- **IOPS**: 3,000
- **Connections**: 100 max
- **Facts Storage**: ~5 GB (≈50 MB per 100 hosts)
- **Backup**: Daily snapshots

#### Medium Environment (100–1,000 Nodes)
- **PostgreSQL Instance**: 1 primary + 1 read replica
- **CPU**: 8 vCPU
- **Memory**: 16 GB RAM
- **Storage**: 200 GB SSD
- **IOPS**: 10,000
- **Connections**: 500 max
- **Facts Storage**: ~50 GB
- **Backup**: Hourly WAL archiving + daily snapshots

#### Large Environment (1,000–10,000 Nodes)
- **PostgreSQL Instance**: 1 primary + 2 read replicas
- **CPU**: 16 vCPU
- **Memory**: 64 GB RAM
- **Storage**: 1 TB SSD
- **IOPS**: 20,000
- **Connections**: 1,000 max (pgBouncer recommended)
- **Facts Storage**: ~500 GB
- **Backup**: Continuous WAL + hourly snapshots

#### Enterprise Environment (10,000+ Nodes)
- **PostgreSQL Instance**: 1 primary + 3+ read replicas (multi-region)
- **CPU**: 32 vCPU
- **Memory**: 128 GB RAM
- **Storage**: 5 TB SSD (auto-scaling)
- **IOPS**: 50,000+
- **Connections**: 5,000 max (pgBouncer HA)
- **Facts Storage**: ~2.5 TB (50,000 hosts × 2yr retention)
- **Backup**: Continuous replication + point-in-time recovery
- **Partitioning**: Monthly table partitions via pg_partman

### PostgreSQL Configuration (Optimized for Compliance Workloads)

```ini
# postgresql.conf

# Memory (for 64 GB host)
shared_buffers = 16GB                    # 25% of RAM
effective_cache_size = 48GB              # 75% of RAM
work_mem = 64MB
maintenance_work_mem = 2GB

# Checkpoint
checkpoint_completion_target = 0.9
wal_buffers = 16MB
max_wal_size = 4GB

# SSD optimization
random_page_cost = 1.1
effective_io_concurrency = 200

# Connections
max_connections = 1000                   # With pgBouncer
shared_preload_libraries = 'pg_stat_statements,auto_explain'

# JSONB optimization
gin_pending_list_limit = 4MB

# Logging
log_min_duration_statement = 1000
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '

# Replication (for HA)
wal_level = replica
max_wal_senders = 10
hot_standby = on
```

### Connection Pooling with pgBouncer

```ini
# pgbouncer.ini

[databases]
compliance = host=postgres-primary port=5432 dbname=compliance

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = scram-sha-256
pool_mode = transaction
max_client_conn = 5000
default_pool_size = 100
reserve_pool_size = 25
server_lifetime = 3600
server_idle_timeout = 600
```

---

## 🎯 Complete Environment Sizing Matrix

### Small Environment (1–100 Nodes)

**OPA Tier (3 containers):**
- **Deployment**: All 3 containers on single host (same as AAP controller)
- **CPU**: 1 vCPU per container (3 vCPU total)
- **Memory**: 1 GB RAM per container (3 GB total)
- **Storage**: 5 GB SSD per container
- **Policy Evaluation**: ~100 evaluations/sec combined
- **Response Time**: <50ms

**PostgreSQL Tier:**
- **Database**: 1 primary instance (Podman container, co-located)
- **CPU**: 4 vCPU
- **Memory**: 8 GB RAM
- **Storage**: 50 GB SSD, 3,000 IOPS

**AAP Tier:**
- **AAP Workers**: 1 execution node (AAP controller)
- **CPU**: 4 vCPU
- **Memory**: 8 GB RAM
- **Facts Collection Frequency**: Weekly
- **Concurrent Collections**: 10 hosts
- **Execution Environment**: `quay.io/rh-ee-tcoulter/aac-compliance-ee:v1.2.0`

**High Availability**: Optional
**Estimated Monthly Cost**: $200–400 (AWS/Azure)

---

### Medium Environment (100–1,000 Nodes)

**OPA Tier (3 containers):**
- **Deployment**: 3 containers on dedicated OPA host (separate from AAP)
- **CPU**: 2 vCPU per container (6 vCPU total)
- **Memory**: 4 GB RAM per container (12 GB total)
- **Storage**: 25 GB SSD per container
- **Policy Evaluation**: ~500 evaluations/sec combined
- **Response Time**: <100ms

**PostgreSQL Tier:**
- **Database**: 1 primary + 1 read replica
- **CPU**: 8 vCPU
- **Memory**: 16 GB RAM
- **Storage**: 200 GB SSD, 10,000 IOPS
- **Backup**: Hourly WAL archiving

**AAP Tier:**
- **AAP Workers**: 2–4 execution nodes
- **CPU**: 4 vCPU per worker
- **Memory**: 8 GB RAM per worker
- **Facts Collection Frequency**: Daily
- **Concurrent Collections**: 50 hosts

**High Availability**: Required
**Estimated Monthly Cost**: $800–1,500 (AWS/Azure)

---

### Large Environment (1,000–10,000 Nodes)

**OPA Tier (3 container sets, each load-balanced):**
- **Deployment**: 3–5 instances per container type (9–15 total)
- **CPU**: 4 vCPU per instance
- **Memory**: 8 GB RAM per instance
- **Storage**: 50 GB SSD per instance
- **Policy Evaluation**: ~2,000 evaluations/sec combined
- **Response Time**: <200ms
- **Load Balancer**: HAProxy or NGINX in front of each container type

**PostgreSQL Tier:**
- **Database**: 1 primary + 2 read replicas
- **CPU**: 16 vCPU
- **Memory**: 64 GB RAM
- **Storage**: 1 TB SSD, 20,000 IOPS
- **Connection Pooling**: pgBouncer required

**AAP Tier:**
- **AAP Workers**: 4–8 execution nodes
- **CPU**: 8 vCPU per worker
- **Memory**: 16 GB RAM per worker
- **Facts Collection Frequency**: Daily (staggered by host group)
- **Concurrent Collections**: 100 hosts

**High Availability**: Multi-zone
**Estimated Monthly Cost**: $3,000–6,000 (AWS/Azure)

---

### Enterprise Environment (10,000+ Nodes)

**OPA Tier (auto-scaling per container type):**
- **Deployment**: 5–15+ instances per container type (15–45 total), Kubernetes HPA
- **CPU**: 8 vCPU per instance
- **Memory**: 16 GB RAM per instance
- **Storage**: 100 GB SSD per instance
- **Policy Evaluation**: ~5,000+ evaluations/sec combined
- **Response Time**: <300ms
- **Deploy on**: OpenShift or Kubernetes with HPA

**PostgreSQL Tier:**
- **Database**: 1 primary + 3+ read replicas (multi-region)
- **CPU**: 32 vCPU
- **Memory**: 128 GB RAM
- **Storage**: 5 TB SSD (auto-scaling), 50,000+ IOPS
- **Partitioning**: Monthly table partitions
- **Connection Pooling**: pgBouncer with HA

**AAP Tier:**
- **AAP Workers**: 10+ execution nodes (auto-scaling)
- **CPU**: 16 vCPU per worker
- **Memory**: 32 GB RAM per worker
- **Facts Collection Frequency**: Daily (continuous rolling window)
- **Concurrent Collections**: 500 hosts

**High Availability**: Global multi-region
**Estimated Monthly Cost**: $10,000–25,000 (AWS/Azure)

---

## 🏗️ Deployment Models

### Model 1: Single-Host (Development / Demo)

All components on one RHEL 9 host (current AAC demo at AAP_HOST):

```
┌─────────────────────────────────────────┐
│          AAP_HOST (8 vCPU, 32 GB)  │
│                                         │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │   AAP    │ │ PostgreSQL│ │ Grafana │ │
│  │  (443)   │ │  (5432)  │ │ (3000)  │ │
│  └──────────┘ └──────────┘ └─────────┘ │
│                                         │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │opa-sec   │ │opa-comp  │ │ opa-ot  │ │
│  │  (8181)  │ │  (8182)  │ │ (8183)  │ │
│  └──────────┘ └──────────┘ └─────────┘ │
│                                         │
│  ┌──────────┐ ┌──────────┐             │
│  │MCP Server│ │Smart Meter│             │
│  │  (8004)  │ │  (8085)  │             │
│  └──────────┘ └──────────┘             │
└─────────────────────────────────────────┘
```

**All components run as Podman containers.** Suitable for proof-of-concept and demos up to ~100 nodes.

### Model 2: OpenShift / Kubernetes (RHPDS / Production)

Deployed on OpenShift (RHPDS cluster). Each OPA container type runs as an OpenShift Deployment:

```bash
# AAP on OCP
aap-controller-aap.apps.cluster-9d56n-2.dynamic.redhatworkshops.io

# OPA on OCP (single instance for small/medium environments)
opa-aap.apps.cluster-9d56n-2.dynamic.redhatworkshops.io
```

For larger environments, deploy each container type separately and use a Service per type to enable independent scaling.

### Model 3: Distributed Enterprise

Dedicated nodes per tier with load balancers in front of each OPA container type:

```
Internet / Corporate Network
         │
         ▼
┌─────────────────────────────────────────────────┐
│              AAP 2.6 Controller Cluster          │
│           (HA — 2+ controllers + mesh)           │
└─────────────────┬───────────────────────────────┘
                  │
    ┌─────────────┼──────────────┐
    ▼             ▼              ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│ LB:8181  │  │ LB:8182  │  │ LB:8183  │
│ (sec)    │  │ (comp)   │  │ (ot)     │
│ 3-5 pods │  │ 3-5 pods │  │ 1-3 pods │
└──────────┘  └──────────┘  └──────────┘
                  │
                  ▼
      ┌──────────────────────┐
      │  PostgreSQL HA       │
      │  Primary + Replicas  │
      │  pgBouncer pooler    │
      └──────────────────────┘
```

---

## 🏗️ Horizontal Scaling (Kubernetes / OpenShift)

### OPA Deployment per Container Type

```yaml
---
# opa-compliance deployment (scales independently from opa-security)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: opa-compliance
spec:
  replicas: 3
  selector:
    matchLabels:
      app: opa-compliance
  template:
    metadata:
      labels:
        app: opa-compliance
    spec:
      containers:
      - name: opa
        image: openpolicyagent/opa:latest
        ports:
        - containerPort: 8181
        args:
          - "run"
          - "--server"
          - "--addr=0.0.0.0:8181"
        resources:
          requests:
            cpu: "2"
            memory: "4Gi"
          limits:
            cpu: "8"
            memory: "16Gi"
        livenessProbe:
          httpGet:
            path: /health
            port: 8181
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health?ready=true
            port: 8181
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: opa-compliance
spec:
  type: ClusterIP
  selector:
    app: opa-compliance
  ports:
  - port: 8182
    targetPort: 8181
```

### Horizontal Pod Autoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: opa-compliance-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: opa-compliance
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 30
      policies:
      - type: Percent
        value: 100
        periodSeconds: 15
    scaleDown:
      stabilizationWindowSeconds: 300
```

### AAP site_config.yml for Scaled Deployment

```yaml
# ansible/vars/site_config.yml

# Point to load-balanced OPA endpoints (or OpenShift routes)
opa_security_url:    "http://opa-security-lb:8181"
opa_compliance_url:  "http://opa-compliance-lb:8182"
opa_ot_url:          "http://opa-ot-lb:8183"

# AAP
aap_url:              "https://aap-controller.internal"
aap_project_name:     "Compliance Automation"
aap_inventory_name:   "Compliance Infrastructure"
aap_ee_name:          "AAC Compliance EE"
aap_vault_credential_name: "Ansible Vault"

# PostgreSQL
pg_host:    "postgres-pgbouncer.internal"
pg_port:    6432
pg_db:      "compliance"
```

---

## 📊 Performance Benchmarks

### Policy Evaluation Performance (Per OPA Container)

| Environment | Policies | Rules | Eval Time | Memory | CPU |
|-------------|----------|-------|-----------|--------|-----|
| 100 nodes | 42 | ~800 | 10–20ms | 1 GB | 20% |
| 1,000 nodes | 42 | ~800 | 20–50ms | 2 GB | 40% |
| 10,000 nodes | 42 | ~800 | 50–100ms | 4 GB | 60% |
| 50,000 nodes | 42 | ~800 | 100–200ms | 8 GB | 75% |

> Note: opa-security has 223 policies and will trend slightly higher for RHEL 9 assessments (19 modules including extended hardening). opa-ot (42 policies) includes NERC-CIP CIP-002–015, AMI/NIST IR 7628, and AI Governance. OPA is NOT on the live SSH collection hot path — it evaluates pre-stored PostgreSQL facts, so evaluation load scales with query frequency, not managed host count.

### AAP Fact Collection Throughput

| Forks | Hosts/min | 1,000 Hosts | 10,000 Hosts |
|-------|-----------|-------------|--------------|
| 10 | 10 | 100 min | 1,000 min |
| 50 | 50 | 20 min | 200 min |
| 100 | 100 | 10 min | 100 min |
| 500 | 500 | 2 min | 20 min |

### Digital Sovereignty Assessment Timing

Full 7-domain assessment (70 controls) against opa-compliance:
- **Avg job time**: 15–25 seconds (includes 7 OPA queries + PostgreSQL INSERT)
- **OPA query time**: 2–5ms per domain
- **Bottleneck**: AAP task overhead, not OPA evaluation

---

## 🔧 Optimization Strategies

### 1. Policy Loading — Use AAP Job Template

Don't reload policies manually. Use the AAP job template:

```
AAP → Templates → AAC - Load OPA Policies (ID 27)
```

This loads all 505 policies across all three containers from the git checkout. Run after any `git push` to the policy repository.

### 2. Bundle Management Optimization

```yaml
# OPA config.yaml for bundle-based policy loading (production alternative to REST API)
bundles:
  compliance-policies:
    resource: "/v1/bundles/policies"
    persist: true
    polling:
      min_delay_seconds: 300
      max_delay_seconds: 600
    caching:
      max_size_bytes: 1073741824  # 1 GB cache
```

### 3. Memory Optimization

```yaml
# Kubernetes env vars for OPA container
env:
  - name: GOMEMLIMIT
    value: "14GiB"  # Leave 2 GB headroom for OS
  - name: GOGC
    value: "100"    # Standard GC pressure
```

### 4. Decision Logging (Production)

```yaml
decision_logs:
  console: false  # Disable console logging in production
  service: "decision-log-service"
  reporting:
    min_delay_seconds: 60
    max_delay_seconds: 120
    upload_size_limit_bytes: 1048576
  mask_decision: true
```

### 5. NGINX Load Balancer for OPA Containers

```nginx
upstream opa_compliance {
    least_conn;
    keepalive 32;
    server opa-compliance-1:8181 max_fails=3 fail_timeout=30s;
    server opa-compliance-2:8181 max_fails=3 fail_timeout=30s;
    server opa-compliance-3:8181 max_fails=3 fail_timeout=30s;
}

server {
    listen 8182;
    location / {
        proxy_pass http://opa_compliance;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_connect_timeout 5s;
        proxy_read_timeout 10s;
    }
}
```

---

## 🌐 Multi-Region Deployment

For global enterprises with Digital Sovereignty requirements, deploy OPA containers in-region to keep policy evaluation within the approved jurisdiction:

```yaml
# AU Region — for IRAP/Digital Sovereignty assessments
opa_compliance_au: "http://opa-compliance.ap-southeast-2.internal:8182"

# EU Region — for GDPR/ENISA assessments
opa_compliance_eu: "http://opa-compliance.eu-central-1.internal:8182"

# US Region — for FedRAMP/FISMA assessments
opa_compliance_us: "http://opa-compliance.us-east-1.internal:8182"
```

> **Digital Sovereignty note**: When assessing digital sovereignty, the OPA container itself must run in the approved jurisdiction. Sending regulated data to an OPA instance in a foreign region violates the very controls being evaluated.

### Traffic Routing (Istio)

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: opa-compliance-routing
spec:
  hosts:
  - opa-compliance
  http:
  - match:
    - headers:
        jurisdiction: { exact: AU }
    route:
    - destination: { host: opa-compliance-au }
  - match:
    - headers:
        jurisdiction: { exact: EU }
    route:
    - destination: { host: opa-compliance-eu }
  - route:
    - destination: { host: opa-compliance-us }
      weight: 100
```

---

## 📈 Monitoring and Metrics

### Prometheus Scrape Config

```yaml
scrape_configs:
- job_name: 'opa-security'
  static_configs:
  - targets: ['opa-security:8181']
  metrics_path: /metrics

- job_name: 'opa-compliance'
  static_configs:
  - targets: ['opa-compliance:8182']
  metrics_path: /metrics

- job_name: 'opa-ot'
  static_configs:
  - targets: ['opa-ot:8183']
  metrics_path: /metrics
```

### Key Grafana PromQL Queries

```promql
# Request rate per container
rate(opa_http_request_duration_seconds_count[5m])

# 95th percentile latency
histogram_quantile(0.95, rate(opa_http_request_duration_seconds_bucket[5m]))

# Error rate
rate(opa_http_request_duration_seconds_count{code!~"2.."}[5m]) /
rate(opa_http_request_duration_seconds_count[5m])

# Policy count per container
opa_info
```

### Grafana Compliance Dashboards

AAC ships with pre-built Grafana dashboards connected to PostgreSQL:

| Dashboard UID | Name | Data Source |
|---------------|------|-------------|
| `aac-compliance-001` | AAC Compliance Overview | PostgreSQL |
| `ami-compliance-001` | AMI / Smart Metering | PostgreSQL |
| `nerc-cip-001` | NERC-CIP Critical Infrastructure | PostgreSQL |

Access at: `http://AAP_HOST:3000` (admin / $GRAFANA_PASSWORD)

---

## 🔄 Disaster Recovery

### Policy Backup

OPA policies live in git — the repository IS the backup:

```bash
# Policies are in git; recovery is a fresh load
git clone https://github.com/ansible-automated-compliance/aac.git

# Reload all policies via AAP
# Templates → AAC - Load OPA Policies → Launch
```

### Container Recovery

```bash
# Recreate all three OPA containers
# Templates → AAC - Deploy OPA Containers → Launch

# Or manually with podman:
podman run -d --name opa-security   -p 8181:8181 --restart=always \
  openpolicyagent/opa:latest run --server --addr :8181
podman run -d --name opa-compliance -p 8182:8181 --restart=always \
  openpolicyagent/opa:latest run --server --addr :8181
podman run -d --name opa-ot         -p 8183:8181 --restart=always \
  openpolicyagent/opa:latest run --server --addr :8181
```

### PostgreSQL Backup

```bash
# AAP backup (before any DB changes):
cd /opt/ansible-automation-platform/ansible-automation-platform-containerized-setup-bundle-2.6-1-x86_64
ansible-playbook -i inventory \
  collections/ansible_collections/ansible/containerized_installer/playbooks/backup.yml

# Manual PostgreSQL backup:
podman exec postgresql pg_dump -U postgres compliance | \
  gzip > compliance-$(date +%Y%m%d).sql.gz
```

---

## 💰 Cost Optimization

### Instance Sizing (AWS EC2 Reference)

| Instance | vCPU | Memory | Monthly | Recommended Use |
|----------|------|--------|---------|----------------|
| t3.medium | 2 | 4 GB | $30 | Development OPA container |
| t3.large | 2 | 8 GB | $60 | Single OPA container, small env |
| m5.large | 2 | 8 GB | $70 | OPA container, medium env |
| m5.xlarge | 4 | 16 GB | $140 | Per OPA container, large env |
| m5.2xlarge | 8 | 32 GB | $280 | Enterprise OPA container |
| r5.xlarge | 4 | 32 GB | $185 | PostgreSQL primary |
| r5.2xlarge | 8 | 64 GB | $370 | PostgreSQL large env |

### Spot Instance Strategy

OPA is stateless — all policy state is re-loadable from git. Spot instances are safe for OPA containers (not for PostgreSQL primary):

```yaml
# Karpenter provisioner — prefer spot for OPA workloads
spec:
  requirements:
    - key: "karpenter.sh/capacity-type"
      operator: In
      values: ["spot", "on-demand"]
  weight: 10  # Prefers spot
```

---

## 🚨 Troubleshooting

### Check Container Health

```bash
# Verify all three OPA containers healthy
curl -s http://AAP_HOST:8181/health && echo " opa-security OK"
curl -s http://AAP_HOST:8182/health && echo " opa-compliance OK"
curl -s http://AAP_HOST:8183/health && echo " opa-ot OK"

# Policy counts
curl -s http://AAP_HOST:8181/v1/policies | python3 -c "import sys,json; print('security:', len(json.load(sys.stdin)['result']))"
curl -s http://AAP_HOST:8182/v1/policies | python3 -c "import sys,json; print('compliance:', len(json.load(sys.stdin)['result']))"
curl -s http://AAP_HOST:8183/v1/policies | python3 -c "import sys,json; print('ot:', len(json.load(sys.stdin)['result']))"
```

### Reload Policies After git Push

Always push to git before syncing AAP — AAP pulls from GitHub:

```bash
git push origin main
# Then: AAP → Projects → Compliance Automation → Sync
# Then: AAP → Templates → AAC - Load OPA Policies → Launch
```

### High Latency

```bash
# Check OPA metrics
curl http://AAP_HOST:8182/metrics | grep latency

# Check container resource usage
podman stats opa-compliance --no-stream
```

### Policy Evaluation Returns Empty Result

Common causes:
1. **Policy not loaded** — check `GET /v1/policies` for the policy ID
2. **Wrong container** — Digital Sovereignty is on `:8182`, not `:8181`
3. **Rego v1 `report` undefined** — query package root, not `/report` suffix (known Rego v1 behavior)
4. **Input structure mismatch** — verify `input` key wraps the data in POST body

---

## 📋 Capacity Planning Checklist

- [ ] Three OPA containers sized and deployed (security / compliance / OT)
- [ ] All 505 policies loaded via AAC - Load OPA Policies (Template 27)
- [ ] PostgreSQL schema initialized (Template 114 — AAC - Initialize PostgreSQL Database)
- [ ] Grafana dashboards deployed (Template 31 for AMI, manual for others)
- [ ] AAP execution environment set to `aac-compliance-ee:v1.2.0` (EE ID 6)
- [ ] Vault credential attached to all assessment job templates
- [ ] Auto-scaling configured (if Kubernetes/OpenShift deployment)
- [ ] Load balancers configured per OPA container type (large+ environments)
- [ ] PostgreSQL pgBouncer deployed (large+ environments)
- [ ] Backup and DR procedures tested
- [ ] Monitoring (Prometheus/Grafana) operational
- [ ] Network bandwidth to OPA containers verified (<10ms latency)
- [ ] Load testing conducted at target concurrent assessment volume

---

This guide reflects the AAC v2.3.x production architecture as of March 27, 2026.
For installation, see `docs/install/COMPLETE_INSTALLATION_GUIDE.md`.
For AAP job template reference, see `CLAUDE.md` (AAP Job Templates section).
