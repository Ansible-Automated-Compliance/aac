> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: SPLIT-PORTSx2.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Automated Compliance (AAC) — Requirements

**Version:** 1.0
**Date:** May 2026
**Status:** Draft — see Section 7 for open decisions

---

## 1. Purpose and Scope

AAC is a compliance automation platform that continuously assesses infrastructure against regulatory and security frameworks, stores results historically, and produces audit-ready evidence.

**What AAC does:**
- Collects system facts via Ansible without modifying managed systems
- Evaluates facts against Policy-as-Code rules (Open Policy Agent / Rego)
- Stores results in PostgreSQL for historical trending and audit trails
- Surfaces compliance posture via Grafana dashboards and PDF reports
- Triggers enforcement workflows via EDA on drift detection
- Exposes all AAP operations to AI tooling via MCP

**What AAC does not do:**
- Auto-remediate without explicit approval
- Replace network security controls (firewalls, IDS/IPS)
- Provide real-time host monitoring (assessment is periodic/on-demand)

**Supported frameworks (50+):**

| Domain | Frameworks |
|--------|-----------|
| Security | CIS RHEL 8/9/10, CIS Ubuntu 22.04, CIS Windows 2022, CIS Docker, CIS Kubernetes, CIS AWS/Azure/GCP, NIST 800-53, NIST CSF, DISA STIG RHEL 9 |
| Federal | FISMA, FedRAMP, CMMC, NIST 800-82 |
| Management | ISO 27001, SOC 2, Corporate Governance |
| Financial | PCI-DSS, SOX |
| Privacy | GDPR, HIPAA, HITRUST, CFR Part 11 |
| Critical Infrastructure | NERC-CIP (CIP-002–CIP-015), IEC 62443, AMI/NIST IR 7628 |
| Regional/Sector | DORA, NIS2, NY DFS, SEC Cyber, SWIFT CSP, TISAX, NCSC CAF, Digital Sovereignty |
| Enforcement | Ansible, Terraform, Git (Sentinel) |
| Governance | AI Governance, NIST AI RMF, MCP tool-call enforcement |
| Threat Detection | Crypto miner detection |

---

## 2. Infrastructure Requirements

### 2.1 Compute

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 8 cores | 16 cores |
| RAM | 16 GB | 32 GB |
| Disk | 100 GB | 200 GB |
| Architecture | x86_64 | x86_64 |

> **Note:** aarch64 (ARM/Apple Silicon) is not supported. The custom Execution Environment includes Terraform 1.10.5 compiled for amd64.

### 2.2 Operating System

- RHEL 9.x required on the AAP controller host
- Rocky Linux 9 and AlmaLinux 9 are acceptable substitutes
- Active Red Hat subscription required (for AAP container images and EE base images)
- SELinux must be set to **Enforcing** — this is not negotiable; several container volume mounts depend on SELinux context relabeling (`:z` flag)

### 2.3 Software Prerequisites (controller host)

| Software | Version | Notes |
|----------|---------|-------|
| Ansible Automation Platform | 2.6 (containerized) | Containerized installer bundle |
| Podman | 4.x | Never Docker |
| Python | 3.11+ | Required for AAP and ansible-runner |
| curl / bash | Any current | Required by seed scripts |
| systemd | Any current | Required for user-level container auto-restart |

### 2.4 Network

**Inbound (controller host):**

| Port | Protocol | Service | Exposure |
|------|----------|---------|----------|
| 443 | HTTPS | AAP Gateway + Controller | Required — all AAP access |
| 3000 | HTTP | Grafana | Internal / demo |
| 8004 | HTTP | MCP server | Internal — Bearer token auth |
| 8085–8087 | HTTP | Smart meter simulators | Internal — demo only |
| 8181 | HTTP | OPA Security | Internal — controller only |
| 8182 | HTTP | OPA Compliance | Internal — controller only |
| 8183 | HTTP | OPA OT | Internal — controller only |

**Note:** PostgreSQL (5432) is published on the host interface by the container runtime. External access must be blocked at the host firewall — no inbound rule for 5432 should be permitted.

**Outbound (controller host):**

| Destination | Purpose |
|-------------|---------|
| github.com | AAP project sync (Rego policies and playbooks) |
| quay.io | AAP EE and base images |
| registry.redhat.io | RHEL UBI base images |
| registry.access.redhat.com | AAP component images |
| AWS EC2 APIs (optional) | Compliance lab targets |

**Managed nodes:** No inbound connectivity required. AAP initiates all SSH connections outbound from the controller.

---

## 3. Account and Credential Requirements

### 3.1 System Accounts

| Account | Host | Privileges | Purpose |
|---------|------|-----------|---------|
| `aapuser1` | AAP controller | Passwordless sudoers | Runs all AAP and container operations |
| `ec2-user` | RHPDS EC2 demo host | Passwordless sudoers | Runs containers on the EC2 demo host |
| `postgres` | PostgreSQL container | Superuser | Schema management, backup/restore |
| `compliance` | PostgreSQL | Read/write | Compliance result storage (AAP job templates) |
| `compliance_reader` | PostgreSQL | Read-only | Grafana datasource |

### 3.2 External Credentials Required

| Credential | Where Used | Required |
|------------|-----------|----------|
| Red Hat account + offline token | AAP Galaxy, EE base image pull | Yes |
| GitHub PAT (`repo` + `read:packages` scopes) | AAP project sync, EE build | Yes |
| quay.io account | Custom EE push/pull | Yes — for EE builds |
| AWS access key + secret | Compliance lab EC2 targets | No — only if using AWS lab |

### 3.3 Vault Variables

All secrets are stored in `ansible/vars/vault_secrets.yml`. This file is **not** Ansible-vault encrypted in the repository — it is plaintext YAML, gitignored, and must be created from `vault_secrets.yml.example`.

| Variable | Category | Purpose |
|----------|----------|---------|
| `vault_redhat_username` | Personal | Red Hat registry login |
| `vault_redhat_offline_token` | Personal | Red Hat API token (JWT) |
| `vault_github_pat` | Personal | GitHub PAT |
| `vault_quay_username` | Personal | quay.io login |
| `vault_quay_password` | Personal | quay.io password |
| `aws_lab_access_key` | Local Lab | AWS access key (permanent lab) |
| `aws_lab_secret_key` | Local Lab | AWS secret key |
| `aws_local_account_id` | Local Lab | AWS account ID |
| `aws_local_account_name` | Local Lab | Friendly account name |
| `aws_local_iam_user` | Local Lab | IAM username |
| `aws_rhpds_access_key` | RHPDS | AWS access key (changes per cluster) |
| `aws_rhpds_secret_key` | RHPDS | AWS secret key |
| `aws_rhpds_account_id` | RHPDS | AWS account ID |
| `aws_rhpds_account_name` | RHPDS | Friendly account name |
| `aws_rhpds_iam_user` | RHPDS | IAM username |
| `vault_aap_admin_password` | Site | AAP admin UI password |
| `vault_windows_admin_password` | Site | Windows EC2 Administrator |
| `vault_aap_local_mcp_token` | Site | MCP Bearer token (rotated; does not expire by TTL) |
| `vault_aap_ocp_mcp_token` | Site | MCP Bearer token for RHPDS AAP |
| `vault_ocp_login_token` | Site | OpenShift login token (RHPDS) |
| `compliance_db_password` | Defaults | PostgreSQL compliance user |
| `compliance_reader_password` | Defaults | PostgreSQL Grafana read-only user |
| `grafana_admin_password` | Defaults | Grafana admin UI — no special characters (bash SSH quoting limitation) |

### 3.4 AAP Credentials (post-install)

After installation, AAP holds the following credentials internally:

| ID | Name | Type | Used By |
|----|------|------|---------|
| 3 | Compliance SSH Credential | Machine | All fact-collection job templates |
| 4 | GitHub PAT | Source Control | Project sync |
| 5 | AWS Compliance Lab | AWS | AWS lab job templates |
| 8 | Ansible Vault | Vault | All job templates needing vault vars |
| 15 | AWS RHPDS Provisioning | AWS | RHPDS provisioning templates |

---

## 4. Security Requirements

**Decided:**

- SELinux must be **Enforcing** on all hosts running AAC containers
- Container runtime must be **Podman** — Docker is not supported
- All AAP operations produce an audit trail (AAP job history is authoritative)
- Assessment is **read-only** — no playbook modifies managed system state without explicit approval
- MCP server requires **Bearer token authentication** on all requests
- PostgreSQL is published on the host interface — external access must be blocked at the host firewall (no inbound rule for port 5432)
- OPA endpoints (8181–8183) are **internal only** — not exposed beyond the controller host

**Open — see Section 7:**

- Host security baseline (item 7.1)
- Vault password delivery model (item 7.2)
- Container user isolation model (item 7.4)

---

## 5. Functional Requirements

### 5.1 Compliance Assessment

- AAC must assess any managed host against any supported framework on demand and on schedule
- Assessments must be **non-destructive** — no write operations to managed systems
- Assessment results must include: hostname, framework, total controls, passed, failed, compliance percentage, violation detail, and timestamp
- Results must be stored in PostgreSQL as JSONB for historical querying
- A single host may be assessed against multiple frameworks in parallel

### 5.2 Policy Management

- All compliance logic must be implemented as Rego v1 policies in OPA — no compliance decisions hardcoded in playbooks
- Policies must be loadable and reloadable without restarting OPA containers
- Three separate OPA instances must be maintained: security (:8181), compliance (:8182), OT (:8183)
- Policy routing must be automatic based on framework key — playbooks must not hardcode OPA URLs

### 5.3 Historical Tracking

- All assessment results must be persisted with `evaluation_timestamp`
- PostgreSQL schema must support querying compliance trend over time per host and per framework
- The compliance database must survive AAP restarts and upgrades

### 5.4 Reporting

- Grafana dashboards must display current compliance posture and historical trends
- PDF report generation must be available for audit evidence (via AAP job template)
- Reports must be accessible without direct database access

### 5.5 Drift Detection and Enforcement

- EDA rulebooks must detect configuration drift via webhooks and filesystem events (local) or webhooks only (RHPDS)
- On drift detection, an enforcement workflow must be triggered automatically within the EDA activation's scope
- Enforcement actions must be logged in AAP with full job output for audit trail

### 5.6 Scheduling

- Nightly fact collection must run automatically (default: 02:00 UTC)
- NERC-CIP continuous monitoring must run on a 30-minute interval
- All schedules must be configurable via AAP without modifying playbooks

### 5.7 Integration

- All AAP operations must be accessible via MCP tools (Claude/AI tooling integration)
- Webhook endpoints must be available on defined ports (5000–5003 for EDA; 8004 for MCP)
- AWS EC2 integration must support dynamic inventory (IP changes on start/stop)

---

## 6. Deployment Requirements

**Decided:**

- Installation must be executable by a single operator with the credentials listed in Section 3.2
- The complete install must result in a verifiable state (all services healthy, all templates present, policies loaded)
- Installation must be idempotent — re-running install playbooks must not break a working install
- All 50+ job templates must be seeded automatically — no manual template creation required after install
- The Rego policy library is managed as a git submodule — policies are not bundled in the installer

**Open — see Section 7:**

- Deployment method / distribution model (item 7.3)

---

## 7. Open Decisions

These items are explicitly unresolved. Documentation that depends on them is marked as pending. No implementation should assume an answer until these are decided.

### 7.1 Host Security Baseline

**Question:** Which hardening standard applies to the AAC controller host itself?

Options: DISA STIG for RHEL 9, CIS Benchmark Level 1, CIS Benchmark Level 2, or an internal baseline.

**Impact:** Affects install prerequisites (some STIG controls conflict with AAP containerized installer), sudoers model, and whether AAC can assess its own host.

---

### 7.2 Vault Password Delivery

**Question:** How is the Ansible Vault password provided to AAP job templates at runtime?

Current state: `~/.vault_pass` file on the controller host, referenced by AAP Vault credential (ID 8).

Options:
- (a) File on controller host — current approach; simple but the password is a file on disk
- (b) AAP Vault credential with inline password — stored in AAP database, no file on disk
- (c) External secret store (HashiCorp Vault, CyberArk) — enterprise-grade; requires additional infrastructure

**Impact:** Install instructions in Section 3.3 cannot be finalized until this is decided. Option (a) is documented now; switching to (b) or (c) changes the install procedure.

---

### 7.3 Deployment Method

**Question:** Is "clone the GitHub repository and run the installer" the intended production deployment model for AAC?

Options:
- (a) GitHub-connected self-install — current approach; requires GitHub PAT and internet access
- (b) Packaged installer (tar.gz or RPM) — air-gapped friendly; requires a build/release pipeline
- (c) OpenShift Operator — cloud-native; requires OCP; aligns with RHPDS demo environment

**Impact:** Drives the entire scope of Section 6 and the install guides. If (a) is the answer, the existing install documentation is the right surface to fix. If (b) or (c), the current install guides describe an intermediate step, not the product.

---

### 7.4 Container User Isolation

**Question:** Is running all containers as `aapuser1` the intended security model, or should each service run as a dedicated system account?

Current state: All podman containers run under `aapuser1` (rootless).

Options:
- (a) Single `aapuser1` account — current approach; operationally simple
- (b) Per-service accounts (`opa-svc`, `mcp-svc`, etc.) — principle of least privilege; more complex sudoers configuration

**Impact:** Affects the account model in Section 3.1 and any future security baseline alignment (item 7.1).

---

*Document derived from AAC codebase as of May 2026. Sections 2, 3, and 5 reflect implemented behavior. Sections 4 and 6 reflect decided requirements; open items are in Section 7.*
