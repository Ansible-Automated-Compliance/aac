# Ansible Automated Compliance (AAC)

**Tagline:** Policy-as-Code Compliance at Enterprise Scale

> **Support boundary.** AAC is an independent open-source project that runs on Red Hat Ansible
> Automation Platform. It is not a Red Hat product and is not supported by Red Hat or by the
> Ansible project; the name says what it does, not who backs it. Support comes from the
> maintainers in `.github/CODEOWNERS` and the community through issues and pull requests. Red Hat
> supports Ansible Automation Platform itself under your subscription. See `install/SUPPORT_MATRIX.md`
> for which install paths the maintainers stand behind.

[![AAP 2.6+](https://img.shields.io/badge/AAP-2.6%2B_(2.7_reference)-red.svg)](https://www.redhat.com/en/technologies/management/ansible)
[![OPA](https://img.shields.io/badge/OPA-Rego_v1-green.svg)](https://www.openpolicyagent.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue.svg)](https://www.postgresql.org/)
[![Frameworks](https://img.shields.io/badge/Frameworks-55+-orange.svg)](#compliance-frameworks)
[![Policies](https://img.shields.io/badge/Rego_Policies-729-brightgreen.svg)](https://github.com/ynotbhatc/rego_policy_libraries)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**Repository:** https://github.com/ansible-automated-compliance/aac  
**Policy Library:** https://github.com/ynotbhatc/rego_policy_libraries  
**Demos:** the demo environments repository (`aac-demos`: runbooks, demo playbooks, RHPDS provisioning) is maintained by the project maintainers and is not published. References to it in these documents describe the maintainers' demo material, available on request.  
**Version:** 2.8.0 (authoritative source: the `VERSION` file) | **Last Updated:** 2026-10-07

---

## What Is AAC?

AAC is a complete enterprise compliance automation platform that continuously assesses your infrastructure against regulatory requirements, detects drift in real time, enforces policy gates in CI/CD pipelines, and delivers audit-ready evidence — all from a single control plane.

Built on **Ansible Automation Platform 2.6+** (2.7 is the reference deployment), **Open Policy Agent**, and **PostgreSQL**, AAC replaces point-in-time manual audits with continuous, automated compliance at scale. Every assessment is stored historically, every violation is tracked to resolution, and every dashboard is live.

### Why It Matters

| | Manual Compliance | Commercial Tools | **AAC** |
|---|---|---|---|
| **Coverage** | Partial, delayed | Usually 1–2 frameworks | **55+ frameworks** |
| **Frequency** | Annual or quarterly | Periodic scans | **Continuous, real-time** |
| **Remediation** | Manual | Alerts only | **Automated rollback + enforcement** |
| **Historical trending** | Spreadsheets | Limited | **Full time-series in PostgreSQL** |
| **Audit evidence** | Manual collection | PDF exports | **Automated, dashboard-ready** |


---

## Platform Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                    Ansible Automated Compliance (AAC)                   │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Analyzed Targets (see "What AAC Analyzes" below):                    │
│     Hosts · OSes · Network · Databases · Apps · Storage · Cloud · K8s  │
│     Smart Meters / SCADA · Containers · CI/CD pipelines                │
│              │  SSH · WinRM · API · SNMP · Cloud SDK · K8s API         │
│              ▼                                                          │
│   ┌────────────────────────────────────────────────────────┐           │
│   │         Ansible Automation Platform 2.6+ (2.7 ref)      │           │
│   │   Controller · EDA (drift detection) · MCP · Gateway   │           │
│   └──────────────┬────────────────────┬────────────────────┘           │
│                  │ store facts         │ CI/CD policy gates             │
│                  ▼                     ▼                                │
│   ┌──────────────────┐   ┌─────────────────────────────────┐           │
│   │   PostgreSQL 15  │   │   Three Domain-Specific OPAs    │           │
│   │                  │   │  opa-security    (CIS/NIST)     │           │
│   │                  │◄──│  opa-compliance  (ISO/SOC2/…)   │           │
│   │  compliance_     │   │  opa-ot          (NERC/AMI)     │           │
│   │  results (JSONB) │   └─────────────────────────────────┘           │
│   │  compliance_     │                                                  │
│   │  facts           │                                                  │
│   │  remediation_    │                                                  │
│   │  rates           │                                                  │
│   │  technical_debt  │                                                  │
│   └────────┬─────────┘                                                 │
│            ▼                                                            │
│   ┌──────────────────────────────────────────────────────┐             │
│   │                  Grafana Dashboards                   │             │
│   │  NCSC CAF 4.0  │  Technical Debt  │  AMI/NERC-CIP   │             │
│   │  AAC Compliance│  Sovereignty     │  NERC-CIP        │             │
│   └──────────────────────────────────────────────────────┘             │
└────────────────────────────────────────────────────────────────────────┘
```

**OPA topology varies by deployment profile.** On OpenShift each OPA is its own Service —
all listening on 8181, distinguished by *service name*. On a single-host container
deployment the three OPAs bind host ports 8181/8182/8183. Playbooks resolve endpoints from
the environment profile (`opa_framework_map` + `resolve_opa_url.yml`) — never hardcode
either form.

---

## What AAC Analyzes

AAC is **target-agnostic** — anything Ansible can collect facts from, OPA can evaluate. The
policy library covers eleven target categories today, with overlapping framework families per
category. Add a target type by writing the fact-collection playbook + the matching Rego package;
the rest (storage, dashboards, evidence export) is handled by the platform.

| Target category | Examples | Fact collection | Framework coverage today |
|---|---|---|---|
| **Hosts / Servers** | RHEL 8/9/10, Oracle Linux 8/9, Ubuntu 22.04, Amazon Linux, Rocky Linux, SUSE | Ansible `gather_facts` over SSH | CIS, STIG (RHEL and Oracle Linux: `stig_linux_assessment.yml`), NIST 800-53, NCSC CAF, ISO 27001 |
| **Operating systems (Windows)** | Windows Server 2019/2022, Windows 10/11 | Ansible facts over WinRM | CIS Windows, STIG Windows, MS Security Baselines |
| **Network equipment** | Cisco IOS/NX-OS, Arista, Juniper, F5, pfSense, VyOS | `ansible.netcommon`, SSH, SNMP, NETCONF | CIS network-device benchmarks, NERC CIP-005/007 |
| **Databases** | PostgreSQL (active), Oracle Database 19c (active: `stig_oracle_database_19c_assessment.yml`, the STIG's own queries as SYSDBA), MySQL/MariaDB, MongoDB, SQL Server | `community.postgresql`, `sqlplus`, vendor SDKs | CIS DBMS benchmarks, DISA STIG Oracle Database 19c, PCI-DSS 8/10, HIPAA technical safeguards |
| **Applications** | Web servers (Apache, Nginx), runtimes (Java, Python), middleware | Module-based introspection + config file evaluation | CIS application benchmarks, ISO 27001 A.14, Sentinel enforcement |
| **Storage** | NetApp, NAS/SAN arrays, S3/object stores, encrypted volumes | Vendor REST APIs + `ansible.builtin` storage facts | NIST SC-28, ISO 27001 A.10, HIPAA §164.312(a)(2)(iv) |
| **Smart meters / AMI** | Smart meter endpoints, head-end systems, MDMS | Smart Meter simulator + REST APIs | NIST IR 7628 (all 7 domains), NERC CIP-002→015, IEC 62443 |
| **Cloud providers** | AWS (active), Azure, GCP | `amazon.aws`, `azure.azcollection`, `google.cloud` | CIS AWS / Azure / GCP, FedRAMP, SOC 2 CC6 |
| **Kubernetes / OpenShift** | OCP 4.14+, generic K8s clusters, admission controllers | `kubernetes.core`, `community.okd` | CIS Kubernetes, STIG K8s, STIG OpenShift 4, NIST 800-190 |
| **Containers** | Container images, Containerfiles, podman / Docker runtimes | Image inspection, Dockerfile / Containerfile static analysis | CIS Docker, CIS Containerd, supply-chain SLSA controls |
| **CI/CD pipelines** | Ansible playbooks, Terraform plans, Git commits, GitHub Actions, AI-agent actions | Pre-task hooks, webhook ingestion via EDA, plan-JSON inspection | Sentinel enforcement (Ansible + Terraform + AI), MCP governance, EU AI Act |

**Common across all targets:** each assessment writes a row to `compliance_results` (PostgreSQL,
JSONB) with hostname, framework, controls passed/failed, violations, and timestamp. The same
PostgreSQL → Grafana → evidence-export path applies regardless of target category — auditors
get one schema for the whole fleet rather than per-tool point views.

**Roadmap target types** (policy work in progress): identity providers (LDAP / IdP), secrets
managers (HashiCorp Vault / AWS Secrets Manager), message brokers (Kafka, RabbitMQ), VoIP /
unified comms, IoT sensors beyond AMI. Submit a target-type request via GitHub issue.

---

## Grafana Compliance Dashboards

AAC ships eight Grafana dashboard definitions (`grafana/dashboards/`) that turn PostgreSQL
compliance data into executive-ready evidence. All dashboards use a fixed datasource UID
(`aac-compliance-db`). The `AAC_Infra_DeployAllDashboards` job template automatically
deploys the five core dashboards; the other three are deployed individually by passing
`dashboard_file` as an extra var to the same template.

| Dashboard (JSON) | Deploy | Description |
|-----------|--------|-------------|
| **AAC Compliance** (`aac_compliance_dashboard`) | auto | Overall compliance posture across all assessed frameworks — score, pass/fail breakdown, per-host drill-down. Includes CIS benchmark results; the policy set evaluates 224 distinct CIS RHEL 9 control IDs of the benchmark's 338 — see [CIS coverage](#cis-coverage-and-the-assessment-contract). |
| **NCSC CAF 4.0 Compliance** (`ncsc_caf_dashboard`) | auto | Maps all 23 Cyber Outcomes (B2–D1) across Phase 1 technical and Phase 2 governance pillars. Single-pane view for UK CNI compliance. |
| **AMI Compliance** (`ami_compliance_dashboard`) | auto | Advanced Metering Infrastructure controls — NIST IR 7628, IEC 62443, device and head-end posture. |
| **NERC-CIP** (`nerc_cip_dashboard`) | auto | NERC-CIP critical infrastructure controls, CIP-002 through CIP-015. |
| **Digital Sovereignty** (`digital_sovereignty_dashboard`) | auto | 7-domain, 70-control sovereignty framework — data residency, cryptographic controls, infrastructure independence, supply chain, operational, network, and AI/ML sovereignty. |
| **Technical Debt Heatmap** (`technical_debt_heatmap`) | via `dashboard_file` | OPA-scored remediation backlog. Quantifies financial exposure and prioritises fixes by risk-weighted cost. |
| **AMI Executive** (`ami_executive_dashboard`) | via `dashboard_file` | Executive-level rollup of the AMI compliance data. |
| **NERC-CIP Unified** (`nerc_cip_unified_dashboard`) | via `dashboard_file` | Combined NERC-CIP view across hosts and CIP standards. |

> Dashboards are provisioned via the Grafana REST API by
> `ansible/playbooks/deploy_grafana_dashboard.yml` (the playbook behind
> `AAC_Infra_DeployAllDashboards`). To redeploy: run that template from AAP.

---

## Policy Library (Separate Repository)

All Rego policies live in a dedicated repository and are included here as a **git submodule**
at `policies/`. This separation keeps the policy library independently versioned, testable,
and reusable across projects.

**Policy library:** https://github.com/ynotbhatc/rego_policy_libraries

```bash
# Clone this repo with policies included
git clone --recurse-submodules https://github.com/ansible-automated-compliance/aac.git

# Update policies to latest
git submodule update --remote policies/
```

### Policy Library Coverage

| Domain | Path | Policies | Frameworks |
|--------|------|----------|------------|
| CIS Benchmarks | `benchmarks/cis/` | 265 | RHEL 9/8/10, Ubuntu, Windows, AWS, Azure, GCP, Docker, K8s |
| DISA STIGs | `benchmarks/stig/` | 67 | RHEL 8/9, Oracle Linux 8/9, Oracle Database 19c, Oracle MySQL 8.0, Ubuntu 20/22, SLES 15, Amazon Linux 2023, Windows 10/11 + Server 2016–2025, K8s, OpenShift 4, VMware vSphere 8, Cisco IOS-XE, MS SQL 2016, PostgreSQL 16, Apache |
| Federal | `frameworks/federal/` | 93 | NIST 800-53, FISMA, FedRAMP, CMMC, **NIST SP 800-171 r3**, **NIST SSDF**, **Zero Trust**, **CJIS**, **IRS 1075**, **CISA CPG** |
| Management | `frameworks/management/` | 62 | ISO 27001, SOC 2, Corporate governance, **CSA CCM v4.0** |
| Financial | `frameworks/financial/` | 23 | PCI-DSS, SOX |
| Privacy | `frameworks/privacy/` | 26 | GDPR, HIPAA, **ISO 27701**, **CCPA/CPRA** |
| Critical Infrastructure | `frameworks/critical_infrastructure/` | 51 | NERC-CIP (CIP-002–015), AMI/NIST IR 7628, IEC 62443 |
| Digital Sovereignty | `frameworks/sovereignty/` | 12 | 7-domain, 70 controls |
| Enforcement | `enforcement/` | 17 | Ansible, Terraform, Dockerfile, Kubernetes, Git |
| Governance | `governance/` | 21 | AI governance, MCP tool-call controls, **EU AI Act (2024/1689)** |
| Threat Detection | `threat_detection/` | 1 | Crypto mining (xmrig, 20+ miners) |

*(Per-domain counts measured at the pinned submodule commit, 2026-10-07; remaining files
sit in shared/other paths.)*

**Total: 722 policy files** (959 including tests) across **55+ frameworks** — all using Rego v1
syntax with `import rego.v1`. Counted at the pinned submodule commit; the number drifts with every
merge, so count it rather than quoting it:

```bash
PINNED=$(git ls-tree HEAD policies | awk '{print $3}')
cd policies && git ls-tree -r "$PINNED" --name-only \
  | grep '\.rego$' | grep -vcE '(^|/)(test_|.*_test\.rego$)'
```

> The policy library has its own CI (OPA unit tests, Scorecard badge, OpenSSF Best Practices).
> PRs to policies go to `ynotbhatc/rego_policy_libraries`; this repo tracks the submodule pointer.

### CIS coverage and the assessment contract

**Coverage is measured, not claimed.** CIS RHEL 9 v2.0.0 defines 338 controls; the policy set
references **224 distinct CIS control IDs** in its violation messages. A single rule can cover more
than one control, so 224 is a floor rather than a ceiling — but the platform does not assert 100%
coverage it has not measured. Every benchmark's `compliance_report` publishes a `controls_basis`
field stating what its `total_controls` number actually counts.

```bash
# Count the control IDs a benchmark evaluates
grep -rhoE 'CIS (L2 )?[0-9]+(\.[0-9]+)*' policies/benchmarks/cis/rhel_9 --include='*.rego' \
  | sed -E 's/CIS L2 /CIS /' | sort -u | wc -l
```

**Assessments fail closed.** CIS controls are phrased "violate if the fact says X", so an
assessment run with no facts would once report near-total compliance for something it never
measured. Every benchmark bridge now gates on fact presence: no facts yields 0%, zero controls
passed, every control counted failed, and an explicit `FAIL-CLOSED: no facts supplied` violation.
The Generic Framework Assessment playbook also fails the job rather than storing an empty row.

*Known limitation:* the gate detects a completely empty input, not a partial one. Sparse or
wrong-shaped facts can still under-report violations.

**Derived policy sets are labelled.** `debian_11`, `rocky_linux_9` and `ubuntu_24_04` contain
controls copied from `ubuntu_20_04`, `rocky_linux_8` and `ubuntu_22_04` respectively. They report
the benchmark they actually implement, plus `derived: true`, `derived_from` and `applied_to`, and
carry a README documenting provenance. Treat their results as an approximate baseline, not a
platform-specific attestation.

**Adding a framework key is two-sided.** A key in `opa_framework_map` (`ansible/vars/site_config.yml`)
must have a matching `package <key>.main` defining `compliance_report`. Without it OPA returns `{}`.
Verify with **empty** input before trusting a new key:

```bash
opa eval -d policies/<dir> -f pretty 'data.<key>.main.compliance_report'
```

All 19 registered `cis_*` keys are verified in both directions — fail-closed on empty input,
evaluating normally on real facts.

---

## Repository Structure

```
compliance/
├── policies/                    # ⚠ Git submodule → ynotbhatc/rego_policy_libraries
│                                #   Rego v1 policies across 55+ frameworks
│                                #   Clone with: git clone --recurse-submodules
│
├── ansible/
│   ├── playbooks/               # AAP playbooks (provision, deploy, assess, report, notify)
│   ├── roles/                   # Ansible roles (aac_compliance_db, aac_opa_containers,
│   │                            #   aac_store_results, aac_facts_collector, aac_mcp_server)
│   ├── config_as_code/          # Config-as-code YAML (AAP resources declared as data)
│   ├── tasks/                   # Shared task files (resolve_opa_url.yml, etc.)
│   └── vars/                    # site_config.yml + vault_secrets.yml (both gitignored —
│                                #   created from .example files by scripts/aac-configure.sh)
│
├── extensions/eda/rulebooks/    # EDA rulebooks (drift detection, webhooks, governance)
│
├── install/                     # Install methods: standard/ (canonical), existing-aap/,
│   │                            #   config-as-code/, rhpds/ (pointer → aac-demos)
│   └── SUPPORT_MATRIX.md        # Which paths exist, their tier, what has been tested
│
├── opa_bridges/                 # AAC-side alias modules mapping opa_framework_map keys
│                                #   to the (vendor-neutral) policy library entrypoints
│
├── integrations/                # Customer-facing integration docs + code (7 integrations
│                                #   incl. Terraform Enterprise, Vault, AWS SSM — see OVERVIEW.md)
│
├── services/
│   ├── aac_portal_bridge/       # Bridge service for the AAC Customer Portal
│   └── mcp-server/              # MCP server exposing the AAP API to AI clients
│
├── grafana/
│   └── dashboards/              # 8 Grafana dashboard JSON files
│
├── customer_profiles/           # Per-customer assessment profiles (template + examples)
│
├── docs/                        # Architecture, install, operations, reports, strategy
├── scripts/                     # Setup and utility scripts (incl. aac-configure.sh)
├── tests/                       # OPA unit tests
├── examples/                    # Sample fact JSON files for OPA testing
├── VERSION                      # Single source of truth for the version
├── CHANGELOG.md · RELEASING.md  # Release history + versioning policy
├── CLAUDE.md                    # Contributor contract (conventions, gates, PR rules)
└── README.md                    # This file
```

**Demo content lives in the separate aac-demos
repository** (restructure Phase 6, 2026-09), which pins this repo as its `product/`
submodule at release tags. `aac-demo-datacenter` is likewise its own repository.

---

## Compliance Frameworks

### Security Benchmarks (OPA service: `opa-security`)

| Framework | Coverage | Highlights |
|-----------|----------|------------|
| **CIS RHEL 9** | 224 of 338 control IDs referenced ([measured](#cis-coverage-and-the-assessment-contract)) | + 3 extended STIG/NIST hardening modules; EDA drift detection |
| **CIS RHEL 8** | 300+ controls | Full v2.0.0 coverage |
| **CIS Ubuntu 22.04** | 280+ controls | Full v2.0.0 coverage |
| **CIS Windows Server 2022** | 400+ controls | Full v2.0.0 coverage |
| **CIS AWS** | Complete | All CIS AWS Foundations controls |
| **CIS Azure** | Complete | Azure Security Benchmark |
| **CIS GCP** | Complete | Google Cloud Platform baseline |
| **CIS Docker** | Complete | Container runtime hardening |
| **CIS Kubernetes** | Complete | K8s cluster hardening |
| **NIST 800-53** | Complete | All control families |
| **DISA STIG** | RHEL 8/9, Oracle Linux 8/9, Oracle Database 19c (collectors shipped), Windows | DoD security requirements — see `docs/frameworks/ORACLE_STIG_ASSESSMENT.md` |

### Regulatory Compliance (OPA service: `opa-compliance`)

| Framework | Industry | Key Controls |
|-----------|----------|-------------|
| **ISO 27001** | Global | ISMS — all 93 Annex A controls |
| **SOC 2** | Technology/SaaS | Trust Service Criteria (CC, A, C, PI, P) |
| **PCI-DSS** | Financial/Retail | 12 requirements, 250+ sub-controls |
| **SOX** | Public Companies | ITGC — access, change, operations |
| **FISMA** | US Government | NIST 800-53 baseline + continuous monitoring |
| **FedRAMP** | US Government Cloud | High / Moderate / Low baselines |
| **CMMC 2.0** | Defense contractors | Levels 1–3 |
| **GDPR** | EU/Global | Data protection + privacy controls |
| **HIPAA** | Healthcare | Technical + administrative safeguards |
| **NCSC CAF 4.0** | UK CNI | 23 Cyber Outcomes across B2–D1 |
| **DORA** | EU Financial | ICT risk management + resilience |
| **NIS2** | EU Critical Sectors | Network and information security |
| **NY DFS (NYDFS)** | US Financial | 23 NYCRR 500 cybersecurity requirements |
| **SEC Cyber** | US Public Companies | 2023 SEC cybersecurity rules |
| **SWIFT CSP** | Global Banking | SWIFT Customer Security Programme |
| **HITRUST CSF** | Healthcare/Regulated | 49 control categories |
| **TISAX** | Automotive | VDA ISA information security |
| **CFR Part 11** | Life Sciences/FDA | Electronic records & signatures |
| **Digital Sovereignty** | Global | 7 domains, 70 controls |
| **AI Governance** | All industries | 5 risk categories + PENDING_APPROVAL gate |
| **Sentinel / AAC Comply** | All industries | Ansible + Terraform + Git policy gates |
| **CSA CCM v4.0** | Cloud/SaaS | 16 domains, 197 controls (A&A, AIS, BCR, CEK, DSP, GRC, IAM, IVS, LOG, TVM, UEM…) |
| **ISO/IEC 27701:2019** | Global/Privacy | PIMS — PII Controller (Art. 7), PII Processor (Art. 8), Data Subject Rights |
| **NIST SP 800-171 Rev 3** | US Defense Contractors | 14 families, 110 CUI requirements — complete DoD supply chain coverage |
| **CCPA / CPRA** | California/US | Consumer rights, sensitive PI, data minimization, DPAs (2023 amendments) |
| **EU AI Act (2024/1689)** | EU/Global AI | Prohibited practices, high-risk requirements, transparency, GPAI, deployer obligations |

### OT / Critical Infrastructure (OPA service: `opa-ot`)

| Framework | Domain | Coverage |
|-----------|--------|----------|
| **NERC-CIP** | Energy/Utilities | CIP-002 through CIP-015 + CIP-015 INSM |
| **AMI / NIST IR 7628** | Smart Grid | Device, head-end, and network security |
| **IEC 62443** | Industrial Automation | Security levels 1–4 |
| **NIST 800-82** | ICS/SCADA | Industrial control system security |
| **Crypto Mining Detection** | All industries | xmrig, xmr-stak, 20+ miners across process/network/cron/systemd |

---

## Live Demo Environments

**All demo content lives in the aac-demos
repository** — runbooks, demo playbooks, demo EDA rulebooks, and the RHPDS provisioning
stack. It pins this repo as its `product/` submodule so every demo runs against a tagged
product release. What the demos show:

| Demo | What It Shows | Story |
|------|---------------|-------|
| **Mythos Patch Lifecycle** | AI-scale vulnerability discovery → targeted remediation → proven closure | A 13-node AAP workflow: observe the estate, match CVEs to observed inventory, open the change record, back up, drain, patch, assure, undrain, verify, close — then rebuild the risk heat map to prove the exposure is gone. |
| **Golden Image** | Drift detect → auto-rollback → help desk ticket | A SELinux config change is detected in seconds. Enforcement workflow restores golden state and files a ticket — no human intervention. |
| **AAC Comply** | Policy gates in CI/CD | A violating Ansible playbook is blocked at git commit. A Terraform plan missing required tags fails pre-apply. Compliant versions pass both gates. 5 enforcement points vs HashiCorp Sentinel's 2. |
| **NCSC CAF 4.0** | UK critical infrastructure audit | 23 Cyber Outcomes assessed and visualised on the CAF Grafana dashboard. Executive-ready compliance posture in one screen. |
| **NERC-CIP + AMI** | Energy sector compliance | Simultaneous NERC-CIP (CIP-002–015) and smart meter AMI assessment. Nightly audit workflow runs automatically. |
| **Digital Sovereignty** | 7-domain sovereignty | Data residency, cryptographic independence, infrastructure sovereignty — assessed and scored across 70 controls. |
| **Technical Debt** | Compliance cost quantification | OPA scores remediation backlog in £/$. Technical Debt heatmap shows which frameworks carry the most financial exposure. |

This table is the highlights reel — the full catalog (M365, Sentinel enforcement, Windows
golden image, RHEL 10 showcase, external policy libraries, customer-POC runbook, and more)
is in `aac-demos/demos/README.md` (maintainers' demo repository, not published).

### Third-Party Integrations

The [`integrations/`](integrations/OVERVIEW.md) folder documents customer-facing
integrations (Terraform Enterprise, HashiCorp Vault Enterprise, AWS SSM, Kubernetes CAPI,
Metal3/Ironic, BigPanda, xMatters, and more) with sample code and use cases.

In addition, ready-to-use playbooks in `ansible/playbooks/` push compliance data to
external systems:

| Integration | Playbook | What It Does |
|-------------|----------|-------------|
| **Prometheus** | `deploy_prometheus_exporter.yml` | Deploys a rootless podman container that reads `compliance_results` from PostgreSQL and exposes 7 Prometheus metrics on port 9101. Includes `aac_compliance_score`, `aac_compliant`, `aac_controls_total/passed/failed`, `aac_violations_total`, and `aac_assessments_24h`. |
| **Nagios / Icinga** | `notify_nagios_compliance.yml` | Pushes latest compliance results to Nagios as passive check results via NSCA. Supports custom OK/WARNING/CRITICAL thresholds and per-framework filtering. |
| **ServiceNow** | `notify_servicenow_violations.yml` | Creates ServiceNow incidents for non-compliant systems after each assessment. Idempotent — checks for existing open incidents before creating new ones. Supports P2/P3/P4 severity mapping based on compliance score. |

---

## Key Differentiators

### vs. HashiCorp Sentinel

| Capability | HashiCorp Sentinel | AAC |
|------------|-------------------|-----|
| Terraform pre-apply gate | ✅ | ✅ |
| Terraform git check-in gate | ✅ | ✅ |
| Ansible git check-in gate | ❌ | ✅ |
| Ansible runtime pre-flight gate | ❌ | ✅ |
| Ansible continuous audit sweep | ❌ | ✅ |
| AI action governance | ❌ | ✅ |
| Historical compliance trending | ❌ | ✅ |
| Regulatory frameworks (55+) | ❌ | ✅ |
| Executive dashboards | ❌ | ✅ |

**AAC delivers 5 enforcement points** (Ansible + Terraform + AI) vs **Sentinel's 2** (Terraform only).

### vs. Commercial Compliance Platforms

| Capability | Qualys / Rapid7 / Tenable | AAC |
|------------|--------------------------|-----|
| Frameworks covered | 5–15 | 55+ |
| Remediation automation | Alerts only | Automated rollback + enforcement |
| Custom policy authoring | Vendor roadmap | Full Rego v1, open source |
| Works on AAP you already own | ❌ | ✅ |
| OT/SCADA/NERC-CIP | Limited | Full coverage |


---

## Installation

**Start with the [install chooser](install/README.md).** AAC installs four ways depending
on your starting point; tiers and tested status for every method are recorded honestly in
[`install/SUPPORT_MATRIX.md`](install/SUPPORT_MATRIX.md).

| Path | Starting point | Best for |
|------|---------------|----------|
| [**Standard**](install/standard/README.md) — *start here* | Any target; profile-driven (`lab` / `rhpds` / `customer`) | The canonical method: fail-closed environment profiles + preflight/verify gates. Includes the [EC2 provisioning path](install/standard/PROVISION_EC2.md) for fresh instances |
| [Existing AAP](install/existing-aap/README.md) | AAP 2.6+ already running | Adding AAC to an existing AAP deployment |
| [Config as Code](install/config-as-code/README.md) | Git repo + AAP API access | CI/CD pipelines, repeatable environment rebuilds |
| [RHPDS](install/rhpds/README.md) | RHPDS OpenShift cluster | Red Hat demo environments — the provisioning stack lives in aac-demos |

Quick outline of any install (details and gates in the per-path READMEs):

1. Clone with the `policies/` submodule initialised: `git clone --recurse-submodules`
2. Run `scripts/aac-configure.sh` to create `install/aac-install-inventory`,
   `ansible/vars/site_config.yml`, and `ansible/vars/vault_secrets.yml` from their
   `.example` templates (all gitignored by design), then edit all three — inventory
   hosts, endpoints, and secrets
3. Apply the config-as-code YAML (or run the bootstrap playbooks) to seed AAP
4. Run templates **AAC - Initialize PostgreSQL Database** → **AAC - Deploy OPA
   Containers** → **AAC - Load OPA Policies** (find by name in the Templates menu)
5. Run **AAC - Verify Installation** — all green = ready

---

## Technology Stack

| Component | Version | Role |
|-----------|---------|------|
| Ansible Automation Platform | 2.6+ (2.7 reference) | Orchestration, scheduling, EDA, MCP |
| Open Policy Agent | 1.10.0 | Policy-as-Code evaluation (Rego v1) |
| PostgreSQL | 15+ | Historical compliance data (JSONB) |
| Grafana | Latest | Compliance dashboards |
| Python | 3.11+ | Ansible execution environment |
| RHEL | 8.x / 9.x | Primary assessed platform |
| OpenShift | 4.14+ | Reference deployment + RHPDS demo hosting |

### Custom Execution Environment

`aac-compliance-ee` (v1.3.0 reference build) — includes `community.postgresql`,
`community.general`, `ansible.posix`, `ansible.utils`, `amazon.aws`, and Terraform 1.10.5.
Used by AAC job templates; built via the **AAC - Build Compliance EE** job template
(x86_64 build host required) and registered per environment.

---

## MCP Integration (Claude Code)

AAC's MCP server (`services/mcp-server/`) exposes the AAP API — **440+ tools** (counted
live 2026-08-21 via `tools/list`; count it rather than quoting it) — for direct AAP control
from Claude Code and other AI clients: launch jobs, check results, query inventories, and
manage templates without leaving the terminal.

```bash
# MCP server runs at http://<aac-host>:8004
# Bearer token managed by the "AAC - Rotate MCP Token" job template
```

MCP tool calls are governed by OPA policy evaluation (`governance/mcp/mcp_governance.rego`)
— see the AI Governance section below.

---

## Roadmap

### Completed ✅

- [x] **Q1 2026** — CIS RHEL 9 policy set (see [measured coverage](#cis-coverage-and-the-assessment-contract)) + EDA real-time drift detection
- [x] **Q1 2026** — Three-container OPA architecture (security / compliance / OT)
- [x] **Q1 2026** — Digital Sovereignty framework (7 domains, 70 controls)
- [x] **Q1 2026** — MCP integration for Claude Code (since grown to 440+ AAP tools)
- [x] **Q2 2026** — NCSC CAF 4.0 (23 Cyber Outcomes, B2–D1) + Grafana dashboard
- [x] **Q2 2026** — Technical Debt scoring + Grafana heatmap
- [x] **Q2 2026** — 10 new frameworks: DORA, NIS2, NY DFS, SEC Cyber, SWIFT CSP, HITRUST, TISAX, CFR Part 11, CIS GCP, NIST 800-82
- [x] **Q2 2026** — Policy library extracted to dedicated repo (`ynotbhatc/rego_policy_libraries`)
- [x] **Q2 2026** — Config-as-code RHPDS bootstrap (`rhpds_bootstrap.yml` single-command install)
- [x] **Q2 2026** — From-scratch install path (no local AAP required)
- [x] **Q2 2026** — Third-party integrations: Prometheus exporter, Nagios passive checks, ServiceNow incident creation
- [x] **Q2 2026** — RHPDS single-workflow provisioning (`AAC - Full RHPDS Provisioning`, 7-node workflow, ~35 min end-to-end)
- [x] **Q2 2026** — 5 new frameworks: CSA CCM v4.0, ISO 27701, NIST SP 800-171 r3, CCPA/CPRA, EU AI Act — 444 total policies
- [x] **Q2 2026** — RHPDS provisioning workflow chained with AWS credential rotation as Node 1 — single-button 9-node workflow, 5 new AWS survey vars (PR #230)
- [x] **Q2 2026** — Golden Image Enforcement workflow restructured to 5-node serial mitigation chain (Check → NotifyHelpDesk → Rollback → Check → CloseHelpdeskTicket); new `AAC_GoldenImage_CloseHelpdeskTicket` template + playbook (PR #231)
- [x] **Q2 2026** — **Per-environment vault file scheme** — `vault_secrets.{lab,rhpds.<cluster>}.yml` templates isolate lab and per-cluster secrets (the default install flow still creates a single `vault_secrets.yml`; per-env files are opt-in)
- [x] **Q3 2026** — Reference lab migrated to AAP 2.7 on OpenShift (CRC); OPA/PostgreSQL/Grafana run as OpenShift workloads, OPA services distinguished by name rather than host port
- [x] **Q3 2026** — **Install consolidation** — 4 supported install paths with an honest tested-status record ([`install/SUPPORT_MATRIX.md`](install/SUPPORT_MATRIX.md))
- [x] **Q3 2026** — **OSCAL export** — machine-readable compliance evidence (`export_oscal_assessment`), validated end-to-end 2026-09
- [x] **Q3 2026** — **Security exception waivers** — waived-never-hidden: waived findings stay visible in reports and dashboards with waiver metadata
- [x] **Q3 2026** — **Product/demos two-repo split** (restructure Phase 6, 2026-09) — demo content moved to aac-demos, pinned to product release tags; the git tag `v2.9.0-pre-split` marks the last unified tree in this repo

### In Progress / Upcoming

- [ ] **Customer Portal** — self-service web UI for compliance reporting, evidence export, and executive dashboards (in active development in a separate repository); customers browse their compliance posture, download audit packages, and trigger assessments without AAP access
- [x] **CAA signing** — cosign ECDSA-P256-signed `compliance_certifications` rows (PR #288; verify per `docs/security/CAA_VERIFICATION.md`); opt-in per assessment playbook, enabled on five today
- [ ] **Certifiable Audit Artifact (CAA) framework** — promote `compliance_results` rows into discrete, signed, self-contained audit artifacts that auditors verify offline via `aac-verify`. Signing is done (above); still open: clause mappings, `aac-verify` CLI, portal export. Spec at [docs/strategy/AAC_CERTIFIABLE_AUDIT_ARTIFACT_SPEC.md](docs/strategy/AAC_CERTIFIABLE_AUDIT_ARTIFACT_SPEC.md) (PR #232)
- [ ] FedRAMP High / CMMC Level 3 full control mapping
- [ ] **AI Threat Correlation Engine** — see full feature spec below
- [ ] OpenShift-native OPA deployment with HPA auto-scaling
- [ ] ComplyTime integration — AAC as the orchestration and analytics layer above `complyctl` (see [Business Evaluation](docs/reference/complytime_evaluation.md))
- [ ] Real-time compliance streaming with Kafka

---

## AI Governance — OPA as the Universal AI Control Plane *(Q3 2026)*

> **Every AI action goes through OPA before it executes.** No AI agent — including AAC's own
> MCP integration — can perform an operation without first being evaluated against the
> governance policy in the `opa-compliance` OPA service. OPA is the single choke point for all AI
> activity in the environment.

### All AI Actions Are Policy-Evaluated

```
AI Agent (Claude / MCP / any LLM tool)
          │
          │  intended action (tool call, API call, playbook launch)
          ▼
┌─────────────────────────────────────┐
│  OPA Compliance Service              │
│  governance/mcp/mcp_governance.rego │
│                                     │
│  ALLOW  → action proceeds           │
│  DENY   → action blocked, logged    │
│  PENDING_APPROVAL → human gate      │
└─────────────────────────────────────┘
```

The MCP governance policy (`governance/mcp/mcp_governance.rego`) evaluates every tool call
against five risk categories: **read-only**, **state-changing**, **destructive**,
**policy-modifying**, and **credential-accessing**. High-risk actions automatically enter
`PENDING_APPROVAL` — they are queued in PostgreSQL and cannot execute until a human
explicitly approves them in the AAP UI.

This means an AI agent cannot:
- Modify any AAP job template or workflow without human approval
- Delete or alter credentials
- Change OPA policies (see lockdown section below)
- Launch destructive operations (instance termination, DB wipe, firewall changes)

### OPA AI Governance Lockdown

> **Problem:** If an AI agent can call `PUT /v1/policies` on the OPA container, it can
> rewrite the very policies that govern it — defeating the entire governance model. The
> lockdown mechanism makes OPA's AI governance policies immutable after initial load,
> requiring explicit human action to change them.

#### Three-Layer Lockdown Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                   OPA AI Governance Lockdown                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Layer 1 — Cryptographic (Bundle Signing)                            │
│  ─────────────────────────────────────────                           │
│  AI governance policies are loaded as a signed OPA bundle            │
│  (RS256 / ECDSA). OPA verifies the signature on every load.          │
│  An AI agent cannot create a valid signed bundle without             │
│  the private key — which is held only by human operators.            │
│                                                                      │
│  Layer 2 — API (Policy Proxy)                                        │
│  ────────────────────────────                                        │
│  A lightweight nginx sidecar in front of the opa-compliance service │
│  blocks all PUT and DELETE requests to /v1/policies when the         │
│  governance lockfile is present. AI agents see HTTP 423 (Locked).    │
│  The lockfile is only removed by the human unlock workflow below.    │
│                                                                      │
│  Layer 3 — Procedural (AAP Approval Gate)                            │
│  ────────────────────────────────────────                            │
│  Even if layers 1 and 2 are bypassed (e.g. direct host access),      │
│  the AAP "Load OPA Policies" playbook checks a lock record in        │
│  PostgreSQL at the start. If locked, governance policies are         │
│  excluded from the load run. Overriding requires modifying the       │
│  playbook itself — a git commit that triggers CI review.             │
│                                                                      │
│  All three layers must be bypassed simultaneously to modify          │
│  AI governance policies without human involvement.                   │
└─────────────────────────────────────────────────────────────────────┘
```

#### Locking — What Happens After Policy Load

When `AAC - Load OPA Policies` completes for the governance container:

1. SHA256 hash of every loaded governance policy is recorded in PostgreSQL
   (`ai_governance_policy_manifest` table — policy path, hash, loaded timestamp, loaded by)
2. Governance lockfile written to host: `/etc/opa/governance.lock`
3. nginx sidecar reloaded — PUT/DELETE to `/v1/policies` now returns HTTP 423
4. OPA compliance container restarted with `--verification-key` pointing to the
   bundle signing public key (any future load without a valid signature is rejected)
5. Lock event logged: timestamp, operator, policy hashes, AAP job ID

#### Unlocking — Human Steps Required

Changing AI governance policies requires completing a four-step human workflow in AAP. No
step can be skipped or automated.

```
Step 1 — Submit Unlock Request
  Template: AAC - Request OPA Governance Unlock
  Survey fields (all required):
    • change_ticket    — ITSM ticket number authorising the change
    • justification    — Why the policy is being changed
    • scope            — Which policies will be modified
    • requestor        — Name and role of the person making the change
    • duration_minutes — How long the unlock window should be (max 60)
  Effect: Logs request in PostgreSQL, notifies designated approvers
          via Slack + PagerDuty. AAP workflow pauses at approval gate.

Step 2 — Human Approval (AAP UI)
  A designated governance approver (not the requestor) must navigate to
  the AAP workflow in the UI and click Approve. Approval is personal —
  the approver's AAP username is logged with the approval event.
  The requestor cannot approve their own request.

Step 3 — Unlock Window Opens
  Template: AAC - Unlock OPA Governance  (runs automatically after approval)
  Actions:
    • Removes /etc/opa/governance.lock
    • Reloads nginx sidecar — PUT/DELETE to /v1/policies now permitted
    • Restarts OPA compliance without --verification-key (accepts unsigned)
    • Writes time-limited unlock token to PostgreSQL (expires after duration_minutes)
    • Logs unlock event: approver, timestamp, unlock window, change ticket

Step 4 — Make Policy Changes + Re-lock
  Operator makes policy changes and runs:
    Template: AAC - Load OPA Policies  (governance policies only)
    Then:
    Template: AAC - Lock OPA Governance
  Actions:
    • Re-signs the governance bundle with the operator's key
    • Restarts OPA with --verification-key
    • Rewrites governance.lock
    • Reloads nginx sidecar back to blocking mode
    • Records new policy hashes in ai_governance_policy_manifest
    • Logs re-lock event: before/after hashes, operator, duration of unlock window
    • Sends closure notification to approver + audit log
```

#### Continuous Integrity Verification

A scheduled AAP job (`AAC - Verify OPA Governance Integrity`, runs every 15 minutes) hashes
all currently-loaded governance policies and compares against the manifest in PostgreSQL. A
mismatch — whether from tampering, container restart with modified policies, or silent policy
injection — triggers an immediate alert and automatically re-applies the lockdown.

The Grafana Threat dashboard includes a **Governance Integrity** panel showing the last
verified timestamp and a red alert indicator if verification has failed or is overdue.

---

## AI Threat Correlation Engine *(Q3 2026)*

> **Problem:** Modern attacks are not single events. A ransomware deployment involves
> simultaneous changes across storage (mass encryption activity), network (unusual egress,
> C2 beaconing), and systems (privilege escalation, new scheduled tasks, service installs).
> Each signal in isolation may look like noise. Together they are unambiguous.

AAC's existing EDA infrastructure detects **individual** drift events in real time. The Threat
Correlation Engine extends this to **coordinated multi-vector attack detection** — correlating
signals across storage, network, and system layers using AI to identify attack patterns and
trigger automatic containment.

### How It Works

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     AI Threat Correlation Engine                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│   Signal Collectors (EDA rulebooks, always running)                       │
│                                                                           │
│   STORAGE                  NETWORK                  SYSTEMS               │
│   ─────────────────        ────────────────         ───────────────────   │
│   • Encryption rate        • Unusual egress         • Auth failures       │
│     (inotifywait mass        (netstat / ss)         • Privilege escalation│
│     modify events)         • New outbound           • New processes       │
│   • Mass file rename         connections            • Cron/systemd adds   │
│   • Shadow copy delete     • C2 beacon patterns     • SSH key injection   │
│   • Backup deletion        • DNS query spikes       • /etc/passwd changes │
│   • Permission changes     • Port scan signatures   • Package installs    │
│          │                        │                         │             │
│          └────────────────────────┴─────────────────────────┘             │
│                                   │                                        │
│                                   ▼                                        │
│              ┌────────────────────────────────────┐                        │
│              │   PostgreSQL — signal_events table  │                        │
│              │   (timestamp, host, vector, type,   │                        │
│              │    severity, raw_data JSONB)         │                        │
│              └──────────────┬─────────────────────┘                        │
│                             │                                              │
│                             ▼                                              │
│              ┌────────────────────────────────────┐                        │
│              │   AI Correlation Layer (LLM + OPA) │                        │
│              │                                    │                        │
│              │  1. Sliding time window (5 min)    │                        │
│              │  2. Cross-vector pattern matching  │                        │
│              │  3. OPA threat taxonomy scoring    │                        │
│              │  4. AI narrative: "storage + net   │                        │
│              │     + system signals match         │                        │
│              │     ransomware lateral movement"   │                        │
│              └──────────────┬─────────────────────┘                        │
│                             │  threat_score > threshold                    │
│                             ▼                                              │
│              ┌────────────────────────────────────┐                        │
│              │   Automated Containment Workflow    │                        │
│              │   (AAP Enforcement Workflow)        │                        │
│              │                                    │                        │
│              │  STORAGE:  revoke write permissions │                        │
│              │            snapshot volumes         │                        │
│              │            quarantine mount points  │                        │
│              │  NETWORK:  firewall isolation rules │                        │
│              │            block egress by host     │                        │
│              │            null-route suspicious IPs│                        │
│              │  SYSTEMS:  isolate from inventory   │                        │
│              │            disable SSH/WinRM access │                        │
│              │            kill suspicious processes│                        │
│              │                                    │                        │
│              │  + Ticket → ITSM / Slack / PagerDuty│                       │
│              │  + Forensic snapshot → PostgreSQL   │                        │
│              │  + Grafana alert + timeline         │                        │
│              └────────────────────────────────────┘                        │
└──────────────────────────────────────────────────────────────────────────┘
```

### Attack Patterns Detected

| Pattern | Storage Signal | Network Signal | System Signal |
|---------|---------------|----------------|---------------|
| **Ransomware** | Mass file encrypt/rename, shadow copy delete | C2 beaconing, unusual egress spike | New service install, scheduled task, privilege escalation |
| **Data Exfiltration** | Mass read on sensitive paths, backup access | Large sustained egress, unusual DNS | New process with net access, auth from new IP |
| **Lateral Movement** | Credential file access (`/etc/shadow`) | Internal east-west scanning | SSH key injection, new sudo rules, `su` failures |
| **Cryptomining** | High I/O on temp paths | Sustained outbound port 3333/14444 | xmrig/xmr-stak process, high CPU, cron persistence |
| **Insider Threat** | Off-hours bulk copy to removable/cloud | Upload to unapproved destinations | Login outside business hours, bulk data access |
| **Supply Chain** | Package hash mismatch, new binary in PATH | Download from unknown registry | Package install outside change window, binary replace |

### Containment Response Levels

| Threat Score | Level | Action |
|---|---|---|
| 40–60 | **Watch** | Log, alert, increase monitoring frequency — no action |
| 60–80 | **Contain** | Isolate affected host from network, disable outbound rules, alert SOC |
| 80–95 | **Quarantine** | Full network isolation + storage write lock + SOC page |
| 95–100 | **Shutdown** | Emergency host isolation + storage snapshot + forensic capture + executive alert |

### Why AAC Is the Right Platform

AAC already has all the foundational pieces: EDA for real-time event collection, OPA for
policy-based threat scoring, PostgreSQL for time-series correlation data, and AAP workflows
for automated enforcement. The Threat Correlation Engine layers AI pattern recognition on top
of this existing infrastructure — no new runtime components required.

The key advantage over SIEM-only approaches: **AAC does not just alert, it acts.** Containment
is automated and policy-governed. Every action is logged in PostgreSQL with a full audit trail.
Every decision is explainable — OPA produces a structured rationale for every threat score,
and the AI layer generates a human-readable narrative of why the correlation triggered.

---

## Documentation

| Document | Description |
|----------|-------------|
| [install/README.md](install/README.md) | Install chooser — which of the 4 install paths fits your starting point |
| [install/SUPPORT_MATRIX.md](install/SUPPORT_MATRIX.md) | Which install paths exist, their support tier, and what has actually been tested |
| [docs/AAC_HONEST_STATUS_AND_POSITIONING.md](docs/AAC_HONEST_STATUS_AND_POSITIONING.md) | What is and is not supported — the honest status statement |
| [docs/CHANGE_GOVERNANCE.md](docs/CHANGE_GOVERNANCE.md) | How a change gets from idea to `main` — branches, review, protected paths, CI |
| [CHANGELOG.md](CHANGELOG.md) / [RELEASING.md](RELEASING.md) | Release history and versioning policy (`VERSION` is the source of truth) |
| [integrations/OVERVIEW.md](integrations/OVERVIEW.md) | Single-document tour of all customer-facing integrations |
| [CLAUDE.md](CLAUDE.md) | Contributor contract — the non-negotiables, Rego rules, OPA routing, PR rules and CI gates |
| aac-demos | Demo environments, runbooks, and RHPDS provisioning (separate repository, product pinned as submodule) |
| [grafana/dashboards/](grafana/dashboards/) | 8 Grafana dashboard JSON files |

---

## Support & Community

- **Issues:** https://github.com/ansible-automated-compliance/aac/issues
- **Policy Library Issues:** https://github.com/ynotbhatc/rego_policy_libraries/issues

---

**Version 2.8.0** (see `VERSION`) | 2026-09-29 | Tim Coulter · Claude (Anthropic)
