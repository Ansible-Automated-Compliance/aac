> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx3, SPLIT-PORTSx2, STALE-COUNTx2, OLD-AAC-VERx2, AAP-2.5/2.6x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Automated Compliance (AAC) — Architecture Assessment

**Version:** 2.6.0
**Date:** April 2026
**Classification:** Internal — Solution Architecture

---

## Executive Summary

Ansible Automated Compliance (AAC) is a unified, policy-as-code compliance automation platform built on three tightly integrated components: Ansible Automation Platform (AAP) 2.6, Open Policy Agent (OPA), and PostgreSQL. It continuously assesses infrastructure against security benchmarks and regulatory frameworks, records immutable compliance history, and triggers automated responses to compliance drift — including ticket generation in ITIL platforms.

AAC addresses a gap that no single commercial tool covers: **continuous, multi-framework compliance enforcement across Ansible automation, Terraform infrastructure-as-code, and AI-driven operations**, with a complete audit trail that satisfies regulatory auditors.

**Key metrics:**
- 505 Rego policies in git repository (loaded across 3 OPA containers)
- 338/338 CIS RHEL 9 controls (100% coverage)
- 5 policy enforcement points (vs. 2 for HashiCorp Sentinel)
- 3 purpose-specific OPA containers (Security, Compliance, OT)
- 7-table PostgreSQL schema with drift detection and reset-to-known-good
- Historical compliance tracking with 13-month retention

---

## 1. Physical Architecture

### 1.1 Three-Layer Stack

AAC is built on three integrated layers, all containerized using Podman:

```
┌─────────────────────────────────────────────────────────────────┐
│              Layer 1 — Orchestration & Collection               │
│         Ansible Automation Platform 2.6 (AAP_HOST)          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │  Controller │  │  EDA (5002) │  │  Gateway / MCP (8004)   │ │
│  │  Job Sched  │  │  Rulebooks  │  │  46 Claude Code Tools   │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└──────────────────────────────┬──────────────────────────────────┘
                               │ REST API / SSH
┌──────────────────────────────▼──────────────────────────────────┐
│              Layer 2 — Policy Decision Point                     │
│                 Three OPA Containers (Podman)                    │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │  opa-security    │  │  opa-compliance   │  │  opa-ot       │ │
│  │  Port: 8181      │  │  Port: 8182       │  │  Port: 8183   │ │
│  │  CIS, NIST, STIG │  │  ISO, SOC2, PCI   │  │  NERC-CIP     │ │
│  │  200+ policies   │  │  SOX, FISMA,      │  │  AI Governance│ │
│  │                  │  │  Sentinel, CAF    │  │  AMI, IEC 62443│ │
│  └──────────────────┘  └──────────────────┘  └───────────────┘ │
└──────────────────────────────┬──────────────────────────────────┘
                               │ JSONB writes
┌──────────────────────────────▼──────────────────────────────────┐
│              Layer 3 — Storage & Visualization                   │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐ │
│  │  PostgreSQL 15 (:5432)   │  │  Grafana (:3000)             │ │
│  │  database: compliance    │  │  5 Compliance Dashboards      │ │
│  │  JSONB facts (~180KB/sys)│  │  Historical trends           │ │
│  │  13-month retention      │  │  Executive scorecards        │ │
│  └──────────────────────────┘  └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Data Flow

**Runtime Compliance Assessment:**
```
Managed Systems
      │
      │ SSH / WinRM / API  (nightly — AAP fact collection)
      ▼
PostgreSQL — host_facts table
      │
      │ Stored facts (JSONB)  (no SSH required at evaluation time)
      ▼
OPA Container (Policy Evaluation)
      │
      │ Compliance / Security Evaluations
      ▼
Grafana (Dashboard / Trending / Executive Scorecards)
```

**Pre-Run Policy Enforcement (Sentinel):**
```
Git (Ansible playbook / Terraform plan)
      │
      │ Push / merge request
      ▼
AAP (job template triggered via EDA webhook)
      │
      │ Playbook / plan submitted for evaluation
      ▼
OPA Container (Policy Evaluation)
      │
      │ ALLOW / DENY / PENDING_APPROVAL
      ▼
Action (proceed, block, or escalate for human approval)
```

**Git Audit Sweep (Sentinel — Scheduled):**
```
AAP (periodic schedule — daily / weekly)
      │
      │ Scans all playbooks / plans in repository
      ▼
Git (source repository)
      │
      │ Playbook / plan content
      ▼
OPA Container (Policy Evaluation)
      │
      │ ALLOW / DENY / PENDING_APPROVAL
      ▼
Action (log violation, alert, or flag for remediation)
```

**Golden Image Alignment (Reset to Known Good):**
```
AAP (triggered on drift detection or on demand)
      │
      │ Retrieve approved baseline snapshot
      ▼
PostgreSQL — host_facts (golden image / baseline)
      │
      │ Diff: current state vs. baseline
      ▼
OPA Container (Policy Evaluation)
      │
      │ Delta — what changed, severity, remediation tasks
      ▼
AAP (generates and applies remediation playbook)
      │
      │ SSH — restore settings to baseline state
      ▼
Managed System (aligned to golden image)
```

### 1.3 Deployment Topology

| Scale | Nodes | Architecture |
|-------|-------|-------------|
| POC / Dev | 1–100 | Single AAP controller, single-node OPA, single PostgreSQL |
| Small Enterprise | 100–1,000 | Single AAP controller, 3 OPA containers, PostgreSQL HA |
| Mid Enterprise | 1,000–10,000 | AAP with execution nodes, OPA cluster behind load balancer |
| Large Enterprise | 10,000–100,000+ | Multiple AAP towers (10K nodes each), distributed OPA, TimescaleDB cluster, regional data residency |

### 1.4 Network Ports

| Port | Service | Protocol | Purpose |
|------|---------|----------|---------|
| 443 | AAP Gateway | HTTPS | UI, API, auth |
| 8181 | OPA Security | HTTP | CIS, NIST, STIG evaluation |
| 8182 | OPA Compliance | HTTP | ISO, SOC2, PCI, Sentinel evaluation |
| 8183 | OPA OT | HTTP | NERC-CIP, AI Governance evaluation |
| 5432 | PostgreSQL | TCP | Compliance data storage |
| 3000 | Grafana | HTTP | Compliance dashboards |
| 8004 | MCP Server | HTTP/SSE | Claude Code integration (300+ tools) |
| 8085–8087 | Smart Meter Sim | HTTP | AMI / utility demo (electric, gas, water) |
| 8091 | Network Sim — Cisco IOS-XE | HTTP | Cisco router CIS demo (telnet, SNMPv1, no banners) |
| 8092 | Network Sim — Juniper Junos | HTTP | Juniper switch CIS demo (SNMPv1, BGP no auth) |
| 8093 | Network Sim — Palo Alto PAN-OS | HTTP | Firewall CIS demo (any/any rule, no URL filter) |
| 8094 | Network Sim — S3 Storage | HTTP | S3 CIS demo (public bucket, no encryption) |
| 5002 | EDA Webhook | HTTP | GitHub push / CI-CD event receiver |

---

## 2. Scope of Coverage

AAC organizes its 505 Rego policies into three strategic focus areas that map directly to customer organizational structures: Security, Compliance, and Utility/OT.

### 2.1 Security Focus (OPA opa-security :8181)

The security focus addresses technical hardening and configuration standards. It is the largest policy domain, serving infrastructure security teams, SOCs, and vulnerability management programs.

**CIS Benchmarks (134 policies):**

| Platform | Version | Controls | Coverage |
|----------|---------|----------|---------|
| RHEL 9 | v2.0.0 | 338/338 | 100% ✅ |
| RHEL 8 | v2.0.0 | 300+ | Complete |
| Ubuntu 22.04 | v2.0.0 | 280+ | Complete |
| Ubuntu 20.04 | v2.0.0 | 280+ | Complete |
| Debian 11 | v2.0.0 | 280+ | Complete |
| Rocky Linux 8 | v2.0.0 | 300+ | Complete |
| Windows Server 2022 | v2.0.0 | 400+ | Complete (modular) |
| Windows Server 2019 | v2.0.0 | 400+ | Complete (modular) |
| AWS Foundations | v2.0.0 | Complete | Complete |
| Azure Foundations | v2.0.0 | Complete | Complete |
| GCP Foundations | v2.0.0 | Complete | Complete |
| Docker CE/EE | v1.5.0 | Complete | Complete |
| Kubernetes | v1.8.0 | Complete | Complete |
| OpenShift 4 | v1.3.0 | Complete | Complete |
| PostgreSQL (v13/14/15) | v1.0.0 | Complete | Complete |
| MySQL 8 | v1.0.0 | Complete | Complete |
| Oracle 19c | v1.0.0 | Complete | Complete |
| Apache 2.4 | v2.4.0 | Complete | Complete |
| NGINX 1.20 | v1.0.0 | Complete | Complete |
| Cisco IOS/IOS-XE | v4.1.0 | Complete | Complete |
| Juniper Junos | v1.0.0 | Complete | Complete |
| Palo Alto PAN-OS | v1.0.0 | Complete | Complete |
| Fortinet FortiGate | v1.0.0 | Complete | Complete |

**Live Network Device Demo (Agentless — AAC Exclusive):**

Four REST-API network simulators run on the AAP controller at ports 8091–8094. AAP gathers facts via HTTP (no SSH, no device credentials) and stores them in `host_facts` with `os_family = 'network'` or `os_family = 'storage'`. OPA evaluates the stored facts against CIS policies — zero device access at evaluation time.

| Simulator | Port | Intentional CIS Violations | Tanium Gap |
|-----------|------|---------------------------|------------|
| Cisco IOS-XE router | 8091 | Telnet enabled, SNMPv1, no login banner | Tanium agent cannot install on IOS-XE |
| Juniper Junos switch | 8092 | SNMPv1, BGP no authentication, root SSH allowed | Tanium agent cannot install on Junos |
| Palo Alto PAN-OS firewall | 8093 | any/any allow rule, no URL filtering | Tanium agent cannot install on PAN-OS |
| S3 object storage | 8094 | Public bucket ACL, no server-side encryption | Tanium agent cannot install on S3 |

*Sales moment: "Show me your network device CIS compliance posture." Tanium cannot answer this question. AAC answers it in seconds with zero device credentials.*

**NIST Frameworks (5 policies):**
- NIST SP 800-53 Rev 5 — Access Control (AC family)
- NIST SP 800-171 — CUI Protection
- NIST Cybersecurity Framework 2.0 — Govern, Identify, Protect
- NIST Risk Management Framework — Categorization

**DISA STIGs (8 policies):**
- RHEL 9, RHEL 8, Ubuntu 20.04
- Windows Server 2022, 2019, 2016
- Windows 11, Windows 10

**Cryptocurrency Miner Detection:**
- Detects known mining processes (xmrig, xmr-stak, minerd)
- Identifies mining pool connections and suspicious ports (3333, 4444, 5555)
- Flags miner cron jobs and systemd services
- Supports detection-only and auto-remediation modes

### 2.2 Compliance Focus (OPA opa-compliance :8182)

The compliance focus addresses regulatory frameworks required for audit certification. It serves Chief Compliance Officers, Internal Audit, and Legal teams.

**Regulatory Frameworks (32 policies):**

| Framework | Scope | Policies |
|-----------|-------|---------|
| ISO 27001:2022 | Information Security Management System | 6 |
| SOC 2 Type II | Trust Service Criteria (Security, Availability, Processing Integrity, Confidentiality, Privacy) | 11 |
| PCI-DSS v4.0 | Payment Card Industry Data Security | 3 |
| SOX ITGC | Sarbanes-Oxley IT General Controls | 4 |
| FISMA / FedRAMP | Federal Information Security Modernization Act | 4 |
| NCSC CAF 4.0 | UK National Cyber Security Centre Cyber Assessment Framework (23 COs, 5 objectives) | 1 |
| Corporate | Organization-specific access, password, backup, and environment policies | 4 |

**Sentinel Policy Enforcement (2 policies — unique AAC capability):**

| Policy | OPA Package | Enforcement Point |
|--------|-------------|-------------------|
| sentinel_ansible | sentinel.ansible | Ansible playbook governance (git, runtime, audit) |
| sentinel_terraform | sentinel.terraform | Terraform plan governance (git, pre-apply) |

The Sentinel policies enable five enforcement points — three for Ansible and two for Terraform — compared to HashiCorp Sentinel's two Terraform-only gates.

### 2.3 Utility / OT Focus (OPA opa-ot :8183)

The utility and operational technology focus addresses critical infrastructure compliance. It serves energy utilities, water authorities, and organizations operating industrial control systems (ICS/SCADA).

**NERC-CIP (Critical Infrastructure Protection):**

| Standard | Title | Controls |
|----------|-------|---------|
| CIP-002 | BES Cyber System Categorization | Asset classification (High/Medium/Low) |
| CIP-003 | Security Management Controls | Policy and governance |
| CIP-004 | Personnel & Training | Access authorization, training records |
| CIP-005 | Electronic Security Perimeters | ESP definition, access controls |
| CIP-006 | Physical Security | Physical access controls and monitoring |
| CIP-007 | Systems Security Management | Ports/services, patch management, malware |
| CIP-008 | Incident Reporting | IR plan, documentation, reporting |
| CIP-009 | Recovery Plans | BCP, backup and restoration |
| CIP-010 | Configuration Change Management | Baseline configs, change control |
| CIP-011 | Information Protection | Data classification, handling, disposal |
| CIP-012 | Communications (High Impact only) | Real-time assessment data protection |
| CIP-013 | Supply Chain Risk Management | Vendor risk, software integrity |
| CIP-014 | Physical Security (Transmission) | Threat assessment, physical protection |
| CIP-015 | Internal Network Security Monitoring (INSM) | Network traffic monitoring, anomaly detection |

**AMI (Advanced Metering Infrastructure) Compliance:**

| Framework | Coverage |
|-----------|---------|
| NIST IR 7628 | Smart grid cybersecurity: Access Control, Audit, IA, System Comms, Config Mgmt, Incident Response |
| AMI Device Compliance | Firmware version/integrity, certificate expiry, key rotation, comms encryption, tamper detection |
| AMI Head-End Security | MDMS API gateway, database isolation, audit logging, network segmentation |

**AI Governance:**
- Risk classification: `read_only_ops` → ALLOW, `low_risk_ops` → ALLOW_WITH_LOGGING
- High-risk production actions without approval → PENDING_APPROVAL (human-in-the-loop required)
- Disabled/unauthorized AI systems → DENY
- All decisions logged to PostgreSQL for audit trail

---

## 3. Reports, Validation, and Historical Benchmarking

### 3.1 Compliance Validation (Three Enforcement Tiers)

AAC validates compliance at three distinct points in the infrastructure lifecycle:

**Tier 1 — Commit-Time Validation**
Policy checks run before code is merged. An EDA webhook receives the GitHub push event and triggers an AAP job that evaluates the Ansible playbook or Terraform plan against OPA. If the policy returns DENY, the GitHub commit status is set to FAILURE, blocking the pull request from merging.

Supported IaC types: Ansible, Terraform, CloudFormation, Azure ARM, GCP Deployment Manager.

**Tier 2 — Deployment-Time Validation**
Policy checks run immediately before infrastructure changes are applied. For Ansible, `sentinel_preflight.yml` is included as the first `pre_task` in any playbook — OPA fires before any deployment task executes. For Terraform, the same OPA check runs before `terraform apply`. Zero infrastructure changes occur if the policy returns DENY.

**Tier 3 — Runtime Continuous Validation**
Ongoing compliance monitoring of live systems, running independently of any deployment activity. Includes:
- **Scheduled sweeps** — hourly, daily, or weekly scans of all managed systems
- **Event-driven re-assessment** — triggered within seconds of a configuration change (see Section 4)
- **Audit sweeps** — periodic scans of all playbooks in the repository to find violations retrospectively

### 3.2 Compliance Reports

AAC generates three categories of reports, all sourced from the PostgreSQL `compliance_results` and `compliance_facts` tables:

**Operational Reports (real-time)**
- Per-system compliance score by framework
- Control-by-control pass/fail breakdown
- Violation list with remediation guidance
- Comparison against previous assessment (delta view)

**Executive Reports (Grafana dashboards)**
- Compliance score trends over time (weekly, monthly, quarterly)
- Framework coverage heatmap by system group
- Top-10 recurring violations across the fleet
- Mean time to remediate (MTTR) by violation severity
- Compliance score by environment (production, staging, dev)

**Audit Evidence Reports (regulatory)**
- Point-in-time compliance snapshots for any historical date
- Chain of custody: who assessed what, when, using which policy version
- Violation history with timestamps of detection and resolution
- CIS, NIST, SOC 2, PCI-DSS control mapping to individual test results
- Evidence packages suitable for external auditor submission

### 3.3 PostgreSQL Schema — Full Table Inventory

The PostgreSQL `compliance` database uses a seven-table schema that separates raw fact collection from compliance evaluation, enables change detection between snapshots, and tracks remediation lifecycle end-to-end.

#### Core Facts Store (ADR-001)

**`host_facts`** — Primary nightly fact store; feeds all compliance frameworks without re-running SSH collection.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | Row identifier |
| `host_id` | VARCHAR(255) | Unique host identifier (hostname or IP) |
| `collected_at` | TIMESTAMPTZ | When facts were gathered (UTC) |
| `facts` | JSONB | 13-domain fact blob: packages, services, users, network, ssh, audit, filesystem, kernel, selinux, pam, cron, processes, certificates |
| `os_family` | VARCHAR(50) | `'RedHat'`, `'Debian'`, `'Windows'`, `'network'`, `'storage'` |
| `os_version` | VARCHAR(50) | Distribution version string |
| `is_baseline` | BOOLEAN | `true` if this snapshot is a tagged approved baseline |
| `baseline_label` | VARCHAR(255) | Human-readable baseline name (e.g., `"Q1-2026-Gold"`) |
| `collection_job_id` | INTEGER | AAP job ID that created this snapshot |

Network and storage devices use `os_family = 'network'` or `os_family = 'storage'`. The JSONB `facts` blob holds device-specific fields (e.g., `snmp_version`, `bgp_auth`, `bucket_acl`) alongside the standard OS domains.

**`host_facts_latest`** — View returning the most recent `host_facts` row per `host_id`. Used by all compliance evaluation playbooks to avoid SSH at evaluation time.

**`sidecar_datasets`** — Organization-context data time-aligned with host fact snapshots.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | Row identifier |
| `sidecar_type` | VARCHAR(100) | Dataset category (e.g., `'digital_sovereignty'`, `'nerc_cip'`) |
| `entity_id` | VARCHAR(255) | Logical entity (country, BES asset ID, org unit) |
| `collected_at` | TIMESTAMPTZ | Collection timestamp |
| `data` | JSONB | Framework-specific context data |

**`sidecar_datasets_latest`** — View returning the most recent sidecar per `(sidecar_type, entity_id)`.

#### Compliance Results

**`compliance_results`** — Output of OPA evaluations; one row per host+framework+assessment run.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | Row identifier |
| `assessment_timestamp` | TIMESTAMPTZ | UTC timestamp of OPA evaluation |
| `hostname` | VARCHAR(255) | Target system identifier |
| `framework` | VARCHAR(100) | Framework name (e.g., `'cis_rhel9'`, `'nerc_cip'`) |
| `policy_version` | VARCHAR(100) | Rego version / git SHA evaluated |
| `compliance_score` | NUMERIC(5,2) | Percentage of controls passing |
| `passed_controls` | INTEGER | Count of passing controls |
| `failed_controls` | INTEGER | Count of failing controls |
| `violations` | JSONB | Array of violation objects with control ID, description, severity |
| `system_facts` | JSONB | Snapshot of facts used in this evaluation |
| `source_fact_id` | INTEGER | FK → `host_facts.id` (which snapshot was evaluated) |

**`compliance_facts`** — Per-control pass/fail records for drill-down reporting.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | Row identifier |
| `result_id` | INTEGER | FK → `compliance_results.id` |
| `control_id` | VARCHAR(100) | CIS/framework control identifier (e.g., `'5.2.4'`) |
| `control_title` | TEXT | Human-readable control name |
| `status` | VARCHAR(20) | `'pass'`, `'fail'`, `'not_applicable'` |
| `severity` | VARCHAR(20) | `'critical'`, `'high'`, `'medium'`, `'low'` |
| `finding` | JSONB | Actual value vs. expected value |
| `remediation` | TEXT | Step-by-step fix instructions |

#### Change Detection

**`fact_changes`** — Diff records produced by comparing consecutive `host_facts` snapshots. Enables detection of unauthorized configuration drift without re-running SSH.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | Row identifier |
| `host_id` | VARCHAR(255) | Affected host |
| `detected_at` | TIMESTAMPTZ | When the diff was computed |
| `before_fact_id` | INTEGER | FK → `host_facts.id` (earlier snapshot) |
| `after_fact_id` | INTEGER | FK → `host_facts.id` (later snapshot) |
| `change_domain` | VARCHAR(100) | Fact domain that changed (e.g., `'ssh'`, `'packages'`) |
| `change_path` | TEXT | JSON path of the changed field |
| `before_value` | JSONB | Value in the earlier snapshot |
| `after_value` | JSONB | Value in the later snapshot |
| `severity` | VARCHAR(20) | Risk rating of the change |
| `authorized` | BOOLEAN | `true` if a change ticket was linked |
| `authorized_by` | VARCHAR(255) | Authorizer identity |
| `ticket_reference` | VARCHAR(100) | Change management ticket ID (e.g., `CHG-12345`) |
| `authorized_at` | TIMESTAMPTZ | When authorization was recorded |

#### Remediation Lifecycle

**`remediation_status`** — Tracks the open/in-progress/resolved state of each compliance violation.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | Row identifier |
| `result_id` | INTEGER | FK → `compliance_results.id` |
| `control_id` | VARCHAR(100) | Control identifier |
| `host_id` | VARCHAR(255) | Affected host |
| `status` | VARCHAR(50) | `'open'`, `'in_progress'`, `'resolved'`, `'accepted_risk'` |
| `owner` | VARCHAR(255) | Assigned remediation owner |
| `due_date` | DATE | SLA deadline based on severity |
| `opened_at` | TIMESTAMPTZ | When violation was first detected |
| `resolved_at` | TIMESTAMPTZ | When resolution was confirmed (or NULL) |
| `ticket_reference` | VARCHAR(100) | Linked ServiceNow/Jira ticket |
| `notes` | TEXT | Free-form context or waiver justification |

**`remediation_actions`** — Generated and applied remediation task records for Phase 3 reset-to-known-good.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | Row identifier |
| `action_id` | VARCHAR(64) | Unique action identifier (UUID) |
| `host_id` | VARCHAR(255) | Target host |
| `baseline_label` | VARCHAR(255) | Source baseline used for restore |
| `generated_at` | TIMESTAMPTZ | When the remediation playbook was generated |
| `applied_at` | TIMESTAMPTZ | When tasks were applied (or NULL if dry-run only) |
| `dry_run` | BOOLEAN | Whether this was a dry-run (no changes applied) |
| `tasks_generated` | INTEGER | Number of restore tasks created |
| `tasks_applied` | INTEGER | Number of tasks successfully applied |
| `diff_summary` | JSONB | Summary of what was changed |
| `aap_job_id` | INTEGER | AAP job that executed the apply |

#### Benchmarking Capabilities

- **Trend analysis** — Compliance score over time per host and framework
- **Drift detection** — Unauthorized configuration changes surfaced without re-running SSH
- **Before/after comparison** — Did a remediation effort actually improve the score?
- **Baseline comparison** — Diff current facts vs. approved baseline (`AAC - Compare to Baseline`)
- **Reset to known good** — Generate and apply Ansible tasks to restore baseline state
- **Regulatory evidence** — Prove continuous monitoring for 12+ months with immutable records
- **Policy impact analysis** — Compare scores before and after a Rego policy update

**Retention:** 13 months by default (configurable). A 1,000-node environment with daily assessments generates roughly 65GB per year — manageable with standard PostgreSQL partitioning.

### 3.4 Grafana Dashboards

Five compliance dashboards are deployed at `http://AAP_HOST:3000`:

| Dashboard | UID | Focus |
|-----------|-----|-------|
| AMI Compliance Dashboard | ami-compliance-001 | Smart meter / utility (NIST IR 7628, IEC 62443) |
| NERC-CIP Compliance | nerc-cip-001 | Critical infrastructure (CIP-002 to CIP-015) |
| Digital Sovereignty | digital-sovereignty-001 | Data residency, encryption, AI governance |
| CIS RHEL 9 Compliance | cis-rhel9-001 | RHEL 9 benchmark (338 controls) |
| NCSC CAF 4.0 | ncsc-caf-001 | 23 Contributing Outcomes across 5 objectives |

All panels are backed by live PostgreSQL queries and refresh on a configurable interval. Dashboards are deployed via AAP Template 31 ("AMI - Deploy Grafana Dashboard"), which injects the live datasource UID at deploy time.

---

## 4. Event-Driven Automation (EDA)

### 4.1 Overview

Event-Driven Ansible (EDA) transforms AAC from a scheduled compliance scanner into a **continuous compliance monitoring system**. Rather than waiting for the next scheduled scan, EDA detects configuration changes within seconds and immediately triggers re-assessment. This closes the window of exposure between a change occurring and a violation being detected.

```
Configuration Change Occurs
        │
        │ (seconds)
        ▼
EDA Rulebook Detects Event
        │
        │ Evaluates conditions
        ▼
AAP Job Template Triggered
        │
        │ Fact collection + OPA evaluation
        ▼
Compliance Result Written to PostgreSQL
        │
        ├──► PASS: Log result, update dashboard
        └──► FAIL: Create ServiceNow incident + alert
```

### 4.2 Event Sources

EDA monitors five categories of events:

**1. File System Changes (inotify)**
Monitors security-critical configuration files in real time:
- `/etc/ssh/sshd_config` — SSH daemon configuration
- `/etc/security/` — PAM, limits, access controls
- `/etc/audit/auditd.conf` — Audit daemon configuration
- `/etc/pam.d/` — Authentication stack
- `/etc/firewalld/` — Firewall rules
- `/etc/sudoers.d/` — Privilege escalation rules

*Trigger latency: 5–30 seconds after file change*

**2. System Log Events (journald / syslog)**
Monitors for security-relevant system events:
- Package installation or removal (`yum install`, `rpm -i`)
- Service state changes (start, stop, restart of critical daemons)
- User account creation or modification
- Privilege escalation events (`sudo`, `su`)
- Failed authentication attempts (potential brute force)
- Kernel module loading/unloading

*Trigger latency: Real-time (within seconds of log entry)*

**3. Webhook Events (GitHub / CI-CD / Cloud)**
Receives push notifications from external systems:
- **GitHub push** — Evaluate Ansible playbooks and Terraform plans at commit time
- **CI/CD pipeline** — Validate before deployment proceeds to production
- **AWS EventBridge** — React to infrastructure changes in cloud accounts
- **Azure Event Grid** — Monitor Azure resource configuration changes
- **Security tool alerts** — SIEM and vulnerability scanner findings trigger re-assessment

*Trigger latency: Immediate (webhook delivery)*

**4. Database Configuration Events (Oracle / PostgreSQL)**
Monitors database parameter changes:
- `ALTER SYSTEM` parameter modifications
- User account creation, modification, or privilege grants
- Listener and network configuration changes
- Audit settings and password policy modifications

*Trigger latency: 30–60 seconds via polling or direct log monitoring*

**5. Scheduled Sweeps (Fallback)**
For environments where real-time event monitoring is not deployed, or as a safety net to catch missed events:
- Hourly: Critical systems (production, high-impact BES assets)
- Daily: All managed systems
- Weekly: Full audit sweep of all repository playbooks

### 4.3 EDA Rulebook Examples

**Git Push → Ansible Validation:**
```yaml
- name: Sentinel GitHub Webhook
  hosts: all
  sources:
    - ansible.eda.webhook:
        host: 0.0.0.0
        port: 5002
  rules:
    - name: Validate Ansible playbook on push
      condition: event.payload.commits is defined
      action:
        run_job_template:
          name: "Sentinel — Validate Ansible Playbook"
          organization: "Default"
          job_args:
            extra_vars:
              sentinel_environment: "production"
```

**SSH Config Change → Immediate Re-assessment:**
```yaml
- name: SSH Config Compliance Monitor
  hosts: all
  sources:
    - ansible.eda.file:
        path: /etc/ssh/sshd_config
  rules:
    - name: Re-assess CIS compliance on SSH config change
      condition: event.path is match("/etc/ssh/sshd_config")
      action:
        run_job_template:
          name: "CIS RHEL 9 Assessment"
          organization: "Default"
```

### 4.4 Automated Remediation Workflow

When EDA detects a violation, it can trigger a multi-step response:

1. **Assess** — Re-run OPA evaluation to confirm the violation
2. **Record** — Write violation to PostgreSQL with timestamp and context
3. **Alert** — Create ServiceNow incident and/or send Slack/email notification
4. **Remediate** — If auto-remediation is enabled and risk level permits, run remediation playbook
5. **Re-assess** — After remediation, re-run assessment to confirm resolution
6. **Close** — Update ServiceNow incident with resolution evidence and close

Auto-remediation requires OPA approval (using the AI Governance policy) for high-risk actions in production environments, enforcing human-in-the-loop for critical changes.

---

## 5. ITIL Platform Integration

### 5.1 ServiceNow — Primary ITIL Integration

AAC integrates with ServiceNow via the `servicenow.itsm` Ansible collection, providing bidirectional data flow between compliance assessments and the ITIL process framework.

**CMDB Synchronization:**
Every compliance assessment updates the corresponding Configuration Item (CI) in the ServiceNow CMDB:

```yaml
- name: Sync compliance status to ServiceNow CMDB
  servicenow.itsm.configuration_item:
    instance: "{{ snow_instance }}"
    sys_id: "{{ item.sys_id }}"
    data:
      u_compliance_status: "{{ item.compliance_status }}"
      u_compliance_score:  "{{ item.compliance_score }}"
      u_last_assessed:     "{{ item.assessment_date }}"
      u_policy_version:    "{{ item.policy_version }}"
      u_violations:        "{{ item.violation_count }}"
```

CMDB fields updated per assessment:
- Compliance status (Compliant / Non-Compliant / Not Assessed)
- Compliance score (percentage)
- Last assessment timestamp
- Active violation count
- Policy version used for assessment
- Framework(s) evaluated

**Incident Creation on Violation:**
When a compliance assessment returns violations, AAC automatically creates a ServiceNow incident with full context:

| Incident Field | Value |
|----------------|-------|
| Category | Security |
| Subcategory | Compliance |
| Priority | Based on violation severity (P1=Critical, P2=High, P3=Medium) |
| Short Description | `Compliance failure: {hostname} — {framework}` |
| Description | Host, framework, violation count, violation details, assessment timestamp |
| Assignment Group | Compliance Team (configurable) |
| CI | Linked to CMDB CI record |
| Evidence | PostgreSQL record ID for audit trail |

**Change Request Integration:**
When a remediation playbook is triggered, AAC can create or reference a ServiceNow Change Request (CR) to maintain ITIL change management traceability:
- Pre-change: Assessment result attached as evidence of non-compliance
- During change: CR status updated to "In Progress"
- Post-change: Re-assessment result attached, CR closed with compliance evidence

**Problem Management:**
Recurring violations (same control failing across multiple assessment cycles) automatically escalate to Problem records in ServiceNow, triggering root cause analysis workflows.

### 5.2 Jira — Development Team Integration

For organizations using Jira for remediation tracking, AAC creates Jira issues directly from violation data:

```yaml
- name: Create Jira remediation ticket
  uri:
    url: "https://{{ jira_instance }}/rest/api/2/issue"
    method: POST
    headers:
      Authorization: "Bearer {{ jira_token }}"
    body_format: json
    body:
      fields:
        project:     { key: "COMPLIANCE" }
        issuetype:   { name: "Bug" }
        summary:     "CIS violation: {{ control_id }} on {{ hostname }}"
        description: "{{ violation_detail }}\n\nRemediation: {{ remediation_steps }}"
        priority:    { name: "{{ severity }}" }
        labels:      ["compliance", "{{ framework }}", "{{ hostname }}"]
```

Each Jira issue includes:
- Control ID and description (e.g., CIS 5.2.4 — Ensure SSH MaxAuthTries is 4 or less)
- Current value vs. required value
- Step-by-step remediation instructions
- Link to the PostgreSQL assessment record for audit traceability
- Assignee based on system ownership (pulled from CMDB)

### 5.3 Traceability Model

AAC provides end-to-end traceability from detection to resolution:

```
Detection
  └── PostgreSQL: compliance_results record (ID, timestamp, violation details)
        └── ServiceNow Incident: INC-XXXXXXX (linked to PostgreSQL ID)
              └── ServiceNow Change: CHG-XXXXXXX (linked to Incident)
                    └── AAP Job: remediation playbook run (job ID, output log)
                          └── PostgreSQL: re-assessment record (confirms resolution)
                                └── ServiceNow: Incident closed with evidence
```

Every step in this chain is time-stamped, linked to the previous step, and queryable from PostgreSQL. Auditors can trace any compliance finding from initial detection through remediation to verified resolution, with full evidence at each step.

### 5.4 Splunk / SIEM Integration

Compliance events are streamed to Splunk via HTTP Event Collector (HEC) for correlation with security events:

```
Compliance assessment result → Splunk HEC → compliance:assessment sourcetype
```

Splunk correlation searches can join compliance data with:
- Authentication logs (identify who made the change that caused the violation)
- Network logs (identify connections that exploited the compliance gap)
- Vulnerability scan data (cross-reference compliance violations with CVEs)

---

## 6. Scalability and Enterprise Deployment

### 6.1 Horizontal Scale Pattern

For environments exceeding 5,000 nodes, AAC scales horizontally:

```
Regional AAP Tower (EMEA)     Regional AAP Tower (APAC)
  10,000 nodes                  10,000 nodes
        │                             │
        └──────────┬──────────────────┘
                   │
        Central PostgreSQL Cluster
        (TimescaleDB, partitioned by region + month)
                   │
        Central OPA Cluster (load-balanced)
                   │
        Central Grafana (unified global dashboard)
```

Each regional tower manages its local nodes independently, while all results flow to a single PostgreSQL cluster for global reporting and audit evidence.

### 6.2 OPA Container Segregation

The three-OPA-container architecture provides domain isolation, independent scaling, and separate upgrade cycles:

| Container | Port | Domain | Scale Trigger |
|-----------|------|--------|--------------|
| opa-security | 8181 | CIS, NIST, STIG | High-frequency assessments, large node count |
| opa-compliance | 8182 | ISO, SOC2, PCI, SOX, FISMA, Sentinel | Regulatory audit periods, policy updates |
| opa-ot | 8183 | NERC-CIP, AI Governance | Utility/OT environments, AI system growth |

---

## 7. Summary Capability Matrix

| Capability | AAC | HashiCorp Sentinel | Chef InSpec | Tanium | Commercial (Qualys/Tenable) |
|------------|-----|-------------------|-------------|--------|----------------------------|
| Ansible policy enforcement | ✅ 3 points | ❌ | ❌ | ❌ | ❌ |
| Terraform policy enforcement | ✅ 2 points | ✅ 2 points | ❌ | ❌ | ❌ |
| AI action governance | ✅ | ❌ | ❌ | ❌ | ❌ |
| CIS Benchmarks (OS) | ✅ 15+ platforms | ❌ | ✅ | ✅ | ✅ |
| Network device CIS (agentless) | ✅ Cisco/Juniper/PAN-OS | ❌ | Partial | ❌ agent required | Partial |
| NERC-CIP (CIP-002–015) | ✅ | ❌ | Partial | ❌ | Partial |
| AMI / Smart Grid | ✅ | ❌ | ❌ | ❌ | ❌ |
| Drift detection (no SSH) | ✅ DB diff engine | ❌ | ❌ | ✅ | Partial |
| Reset to known good | ✅ automated | ❌ | ❌ | ✅ | ❌ |
| Historical compliance tracking | ✅ 13 months | ❌ | ❌ | ✅ | ✅ (licensed) |
| ServiceNow ITIL integration | ✅ | ❌ | ❌ | ✅ | ✅ (licensed) |
| Event-driven re-assessment | ✅ EDA | ❌ | ❌ | ✅ | ❌ |
| Grafana executive dashboards | ✅ | ❌ | ❌ | ✅ | ✅ (licensed) |
| Crypto miner detection | ✅ | ❌ | ❌ | ✅ | Partial |
| Open source policy engine | ✅ OPA | ✅ Sentinel | ✅ InSpec | ❌ Proprietary | ❌ Proprietary |

---

## 8. Recommended Run Order for New Deployments

### Phase 1 — Core Infrastructure

| Step | Template ID | Name | Purpose |
|------|-------------|------|---------|
| 1 | 28 | AAC - Deploy OPA Containers | Create all three OPA containers with policy mounts |
| 2 | 27 | AAC - Load OPA Policies | Load all 209 Rego policies from git |
| 3 | 23 | Initialize PostgreSQL Database | Create base compliance schema |
| 4 | 39 | AAC - Demo Stability Setup | Install systemd units for reboot persistence |
| 5 | 38 | Sentinel Demo - Pre-flight Check | Validate all services are GO before demo |
| 6 | — | Run first compliance assessment | Target systems: CIS RHEL 9 (10), Ubuntu (12), Windows (13) |

### Phase 2 — Extended Schema + Drift Detection

| Step | Template ID | Name | Purpose |
|------|-------------|------|---------|
| 7 | 59 | AAC - Seed Phase 2 Templates | Creates templates 60–63 via Controller API |
| 8 | 60 | AAC - Migrate Schema v2 | Adds `is_baseline`/`baseline_label` to `host_facts`; creates `remediation_status`, `fact_changes`, `remediation_actions` |
| 9 | 80 | AAC - Gather Facts (Nightly) | SSH fact collection → `host_facts` table (schedule: 02:00 UTC) |
| 10 | 61 | AAC - Collect Facts | On-demand fact collection with explicit host survey |
| 11 | 62 | AAC - Evaluate Stored Facts | DB facts → OPA → `compliance_results` + `remediation_status` (no SSH) |
| 12 | 64 | AAC - Seed Drift Detection | Creates templates 65–67 + workflow 69 |
| 13 | 65 | AAC - Detect Fact Drift | Python diff on consecutive snapshots → `fact_changes` |
| 14 | 69 | AAC - Collect and Assess (WF) | Workflow: Collect (61) → Detect Drift (65) → Evaluate (62) |

### Phase 3 — Baseline + Reset to Known Good

| Step | Template ID | Name | Purpose |
|------|-------------|------|---------|
| 15 | 70 | AAC - Seed Phase 3 | Creates templates 71–75 + workflow 75 |
| 16 | 71 | AAC - Set Baseline | Tag a fact snapshot as an approved baseline |
| 17 | 72 | AAC - Compare to Baseline | Diff current facts vs. approved baseline |
| 18 | 73 | AAC - Generate Remediation Playbook | Python generator → Ansible restore tasks |
| 19 | 74 | AAC - Apply Remediation | Apply generated tasks (with dry-run safety gate) |
| 20 | 75 | AAC - Reset to Known Good (WF) | Workflow: Compare (72) → Generate (73) → Apply (74) |

### Optional Modules

| Template ID | Name | Purpose |
|-------------|------|---------|
| 30 | AMI - Deploy Smart Meter Containers | Electric/gas/water meter simulators (:8085–8087) |
| 29 | AMI - Full Compliance Audit and Store | NIST IR 7628, Device, Head-End → PostgreSQL |
| 83 | AAC - Deploy Network Simulators | Cisco/Juniper/PAN-OS/S3 simulators (:8091–8094) |
| 84 | AAC - Gather Network Facts | Network device facts → `host_facts` |
| 53 | AAC - Seed Digital Sovereignty Workflow | 7-domain sovereignty assessment workflow |
| 26 | AAC - NERC CIP Compliance Report | CIP-002 through CIP-015 assessment |
| 7 | Configure EDA rulebooks | Continuous drift monitoring (EDA source) |
| 8 | Configure ServiceNow integration | Incident creation on violation |

---

*Document generated from AAC v2.4.0 source documentation. All policy counts and template IDs reflect the current production environment at AAP_HOST as of March 19, 2026.*
