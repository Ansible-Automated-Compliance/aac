# Ansible Automated Compliance (AAC) — Solution Architecture & Capabilities

**Version:** v1.0
**Date:** 2026-07-09
**Audience:** Sales engineering, solution architects, field enablement, CISO/compliance stakeholders
**Companion to:** *The Compliance Revenue Multiplier* briefing deck; *AAC Hybrid Certified-Tools Architecture* (v1.1)

---

## 1. Executive summary

AAC is **not a standalone product that replaces anything** — it is the **content and capability layer that turns the Ansible Automation Platform (AAP) a customer already owns into a continuous compliance-evidence engine.** Same operators, same controller, a different — and far larger — budget.

Compliance demands **complete infrastructure coverage** — an auditor does not accept that the Linux team is CIS-compliant if the database and network teams are not — so AAC brings the whole estate under one assessment, with a 13-month immutable audit record behind every verdict.

This document details the architecture, the eight capabilities, the hybrid model that leverages already-certified tools like OpenSCAP, the end-to-end traceability, the collaboration with the AAC Customer Portal, and deep dives into the highest-stakes compliance areas (NERC-CIP and Digital Sovereignty).

---

## 3. Architecture — the three-layer engine

AAC layers three components onto AAP. It is additive and non-invasive: it adds compliance job templates, workflows, policies, storage, and dashboards to a running AAP without changing the customer's existing controllers or playbooks.

```
   Layer 3 — DECISION            Open Policy Agent (OPA)
   (the policy engine)           3 purpose-split containers, 505 Rego policies, ms latency
        ▲                          ├─ opa-security    :8181  CIS, STIG, hardening, IaC enforcement
        │ verdict                  ├─ opa-compliance  :8182  GRC, sovereignty, SaaS, management frameworks
        │                          └─ opa-ot          :8183  NERC-CIP, AMI/NIST IR 7628, IEC 62443
   Layer 2 — STORAGE             PostgreSQL
   (the audit record)           13-month immutable JSONB compliance facts — a queryable
        ▲                        database, not a screenshot
        │ state / evidence
        │
   Layer 1 — ORCHESTRATION      Ansible Automation Platform 2.6 / 2.7
   (what the customer owns)     Controller + Event-Driven Ansible (EDA) + MCP;
                                deep, agentless state collection via gather_facts
```

**Layer 1 — Orchestration (AAP).** The customer's existing platform. `gather_facts` performs **deep, agentless state collection** over SSH/WinRM/HTTPS using existing credentials — hardware, OS identity, packages, services, users, network, storage, auth, audit, certificates, containers, cloud agents, and custom application state. This is far richer than any scanner output and is the substrate for drift detection, patching, cost heat-mapping, and dashboards. Event-Driven Ansible provides the real-time trigger surface; the MCP server (port 8004, 46 AAP tools) is the AI-governed control interface.

**Layer 2 — Storage (PostgreSQL).** Every assessment writes a timestamped JSONB record (~180 KB/host). Retention is 13 months minimum (SOC 2 Type II floor; extended for NERC-CIP and FedRAMP ConMon). Auditors receive a **queryable database**, not a point-in-time screenshot — the difference between "continuous monitoring evidence" (what regulators require) and "a snapshot."

**Layer 3 — Decision (OPA).** Three purpose-split OPA containers evaluate **505 Rego v1 policies (50+ frameworks, 22 platforms; tests excluded) in milliseconds**. Framework-to-container routing is declarative (`opa_framework_map` in `site_config.yml`): security frameworks → :8181, GRC/management/sovereignty → :8182, OT/critical-infrastructure → :8183. Policies are version-controlled in a git submodule and loaded at deploy time.

### 3.1 The AAC closed loop

What customers actually pay for is the **loop that no certified scanner closes**:

```
   Find ──▶ Assess (OPA) ──▶ Auto-Remediate (AAP) ──▶ Verify (PostgreSQL) ──▶ Close ticket
     ▲                                                                            │
     └──────────────────────── continuous / event-driven ◀────────────────────────┘
```

A scanner *finds* a problem and stops — it opens a ServiceNow ticket and waits for a human, while drift accumulates (the "scanner dead-end"). AAC + AAP **finds, assesses, auto-remediates, re-verifies, and closes the loop in seconds**, writing every step to the immutable record.

---

## 4. The Compliance Capability Matrix — 8 capabilities, 4 domains

This is the canonical AAC capability model (deck slide 7). Each capability states the problem and the AAC solution.

### Domain 1 — Code & Posture

**1. Code Lifecycle Governance (shift-left pipeline enforcement).**
*Problem:* playbooks and Terraform plans introduce misconfigurations before deployment.
*AAC:* **five policy enforcement points — commit, pre-run, runtime, drift, and AI.** OPA evaluates Ansible AST and Terraform plan JSON at git check-in and job launch, blocking non-compliant IaC from ever reaching production. (This is the "everything Sentinel does, natively, plus Ansible and AI" story — Sentinel only guards Terraform.)

**2. Environment Validation (benchmarks).**
*Problem:* manual audits produce spreadsheets six months late.
*AAC:* **338/338 CIS RHEL 9 controls (100% coverage)** plus CIS Windows/Ubuntu/cloud/container, DISA STIGs, and NIST overlays. **Zero device credentials required at evaluation time** (facts are collected by AAP, evaluated by OPA), and the output is **exact gaps, not just a percentage score.**

### Domain 2 — History & Translation

**3. Regulatory Framework Mapping (multi-standard translation).**
*Problem:* customers buy separate tools for SOC 2, PCI, and HIPAA.
*AAC:* a **translation engine** — one fact-collection run populates multiple compliance reports, translating a single technical state into the distinct language of **50+ regulatory frameworks** simultaneously (see §6, Traceability).

**4. Historical Audit Evidence (the moat).**
*Problem:* auditors require *continuous monitoring* evidence, not snapshots.
*AAC:* every assessment writes a timestamped JSONB record; after 12 months the **13-month immutable record** is a massive switching barrier — auditors depend on it, so ripping out AAC means failing the audit.

### Domain 3 — Action & Economics

**5. Configuration Drift Detection & Automated Remediation.**
*Problem:* weeks or months between violation detection and remediation.
*AAC:* continuous assessment + EDA. `inotify`/`auditd` detect file drift (e.g. an SSH-config change), OPA evaluates, AAP restores the golden baseline, and ServiceNow is updated — **total time under 60 seconds** to known-good.

**6. Technical Debt Quantification (dollars, not just scores).**
*Problem:* "you have 847 violations" is meaningless to a CFO; "$2.3M in remediation debt" is not.
*AAC:* converts compliance failures into **remediation cost** using per-domain engineering rates (e.g. $185/hr baseline; OT specialists higher), separated by OT/IT/Sovereignty budget — the board-level economics no scanner provides.

### Domain 4 — Future & Consolidation

**7. AI Controls & Governance (MCP tool enforcement).**
*Problem:* AI-driven automation is entering compliance workflows ungoverned.
*AAC:* every MCP tool call passes through OPA (`governance/mcp/mcp_governance.rego`) — tool authorization, scope, time bounds, per-tenant overlays, audit requirements — the governance EU AI Act, NIST AI RMF, and ISO 42001 reference. No certified upstream tool provides AI-action governance for AAP/AAC.

**8. Critical Infrastructure & Sovereignty (NERC-CIP, EU).**
*Problem:* the highest-stakes, lowest-coverage frameworks are where fines and sovereignty risk live.
*AAC:* direct Rego assessment of NERC-CIP (CIP-002…CIP-015), AMI/NIST IR 7628, and Digital Sovereignty (7 pillars) — areas where no certified scanner offers coverage (deep dives in §8 and §9).

---

## 5. The hybrid model — leveraging already-certified tools (OpenSCAP and beyond)

A regulated customer runs **two different products that are often conflated:**

| Product | Produces | Consumed by | Certification regime |
|---|---|---|---|
| **Audit-weight verdict** | "this control passes/fails" with audit-grade chain of custody | Auditors, regulators, 3PAOs | Full FedRAMP / DISA APL / SCAP / FIPS |
| **Operational compliance platform** | drift detection, remediation, patching workflow, dashboards, cost heat-maps, AI-governed orchestration, traceability | Operators, engineers, executives | SOC 2 + ISO 27001 (standard enterprise SaaS) |

**AAC's hybrid architecture (Path B) separates them:** certified upstream tools own the *verdict*; AAC owns the *platform*.

### 5.1 OpenSCAP as the certified verdict source

**OpenSCAP** (the `oscap` CLI + ComplianceAsCode content) is the **primary audit-weight verdict source for CIS, STIG, and NIST overlays on Linux.** It is NIST SCAP 1.3 validated, ships with RHEL (inheriting Common Criteria EAL4+ and FIPS 140-3), is in Iron Bank, and is DISA-accepted for STIG. **AAC orchestrates OpenSCAP via Ansible in the same playbook run as `gather_facts`** — so a single job produces both the certified scan verdict *and* the deep state, side by side, written to the same PostgreSQL evidence schema.

The same pattern extends to the rest of the certified ecosystem, chosen per what the customer already runs:

| Layer | Certified verdict source | AAC role |
|---|---|---|
| OS / config (Linux) | **OpenSCAP** / SCC / CIS-CAT | orchestrate + rollup + evidence |
| Vulnerability | Tenable / Qualys / Rapid7 | ingest + remediate + per-product debt |
| Cloud (CSPM) | Defender for Cloud / AWS Security Hub / GCP SCC | ingest + rollup |
| Containers / K8s | RHACS / Aqua / Trivy | ingest + rollup |
| OT / ICS | Dragos / Nozomi / Claroty | ingest + CIP rollup + supply-chain (see §8) |
| SIEM / logs | Splunk / Sentinel / Elastic | correlate |
| GRC workflow | ServiceNow GRC / Archer | bidirectional ticket sync |

### 5.2 What AAC owns that no scanner replicates

Six capabilities survive intact regardless of which certified tool supplies the verdict:

1. **Deep agentless state collection** (`gather_facts`) — the substrate for drift, patching, cost, and dashboards.
2. **AAP as action coordinator** — the closed remediation loop.
3. **Cross-framework rollup + 13-month longitudinal storage** — one piece of evidence, every applicable framework.
4. **Sidecar organizational context** — owners, business functions, change tickets, scope tags joined to every technical artifact.
5. **Portal-driven product dashboards** — per-product compliance and cost visibility (see §7).
6. **MCP-mediated AI governance + end-to-end traceability** (see §6).

### 5.3 Where AAC assesses directly (no certified scanner exists)

For frameworks no certified tool covers, AAC's Rego library **is** the assessment: **NIS2, EU AI Act, DORA, NCSC CAF, Digital Sovereignty, and NERC-CIP CIP-013 supply chain.** Here AAC is not orchestrating a scanner — it is the primary engine.

### 5.4 Why the hybrid model wins

- It **matches Red Hat's house pattern**: AAP orchestrates over heterogeneous infrastructure it doesn't replace; AAC orchestrates over the certified security ecosystem it doesn't replace.
- It **cuts AAC's own certification burden by ~80% cost / 60% time / 70% risk** versus self-certifying as the system of record, while preserving every operational capability.
- It **lets customers keep their existing scanner investments** — AAC adds the platform layer on top, lowering adoption friction.

---

## 6. Traceability — from fact to auditor

Traceability is the through-line that makes AAC's evidence *defensible*, not just *pretty*.

### 6.1 The evidence chain

```
gather_facts (state)  ─▶  OPA / certified scanner (verdict)  ─▶  AAP (action)  ─▶  gather_facts (re-verify)
        │                          │                                 │                    │
        ▼                          ▼                                 ▼                    ▼
   compliance_facts          compliance_results               AAP activity           post-state
   (JSONB, ~180KB/host)      (verdict + policy name/version)   stream                 (proof of change)
        └──────────────────────────── all in PostgreSQL, 13-month immutable ────────────────────────────┘
                                                    │
                                                    ▼
                        Cross-framework rollup (Rego)  ─▶  per-framework report / OSCAL export
```

Every event is recorded: fact collection, scanner-artifact ingestion, OPA verdict (with policy name + version), AAP job launch, MCP tool call, portal user action, sidecar update, and rollup execution. The audit log is **hash-chained** for chain-of-custody.

### 6.2 The translation engine (one fact → many frameworks)

A single collected state (or a single scanner finding) is **translated into the control language of every applicable framework at once**: one SSH-hardening fact simultaneously satisfies CIS 5.2, STIG RHEL-09-255xxx, NIST 800-53 AC/IA controls, ISO 27001, SOC 2, PCI, and HIPAA mappings. Customers stop buying separate tools per framework, and auditors get consistent, cross-referenced evidence.

### 6.3 The auditor's view

Given any AAC report, an auditor can drill **fact → verdict → action → outcome** with cryptographic continuity. In the hybrid model the chain of trust *starts* at the certified scanner's signed artifact, passes through AAC's **deterministic, replayable transforms**, and arrives at the report — so AAC does not itself need to be independently certified to make the chain defensible; it needs to be deterministic and auditable, which it is.

---

## 7. Collaboration with the AAC Customer Portal

AAC (the engine, in the customer's environment) and the **AAC Customer Portal** (operator-hosted SaaS) are **two products that work together.** The engine produces evidence where the data lives; the Portal is the CISO/Compliance-Officer's consumption and self-service surface (deck slide 14: the economic buyer "lives in the Customer Portal / exported reports").

### 7.1 How the collaboration works

```
   Customer environment                              Operator-hosted SaaS
   ┌───────────────────────────┐                    ┌──────────────────────────────┐
   │  AAC engine (AAP+OPA+PG)   │                    │   AAC Customer Portal         │
   │                           │  ── posture/results ──▶  per-product dashboards,    │
   │  compliance_results,      │     (read model)      │   cost heat-maps, drift trend │
   │  technical_debt, facts    │                    │   audit-evidence export        │
   │                           │  ◀── signed bundles ──│   framework bundles (CIS…),   │
   │  AAC bridge (pull)        │     CVE feeds,        │   CVE intelligence, policy    │
   │                           │     enrollment-gated  │   updates, enrollment control │
   └───────────────────────────┘                    └──────────────────────────────┘
             data stays in the customer's environment for assessment
```

- **Distribution (Portal → engine).** The on-site AAC **bridge pulls** operator-published, **ed25519-signed framework bundles** (CIS RHEL 9, CIS Windows, etc.), **classified CVE feeds**, and policy updates over authenticated, scope-gated, **enrollment-gated** endpoints. A revoked or paused enrollment stops future bytes — the Portal never reaches *into* the customer environment.
- **Visibility (engine → Portal).** The Portal renders **per-product** (not just per-host) compliance posture, **cost heat-maps** (from `remediation_rates` / `remediation_budgets`), and **drift trending** over the 13-month window — the CISO's board-level view — plus **exported, auditor-ready reports.**
- **Multi-tenant Compliance-as-a-Service.** Per-tenant token issuance with scoped API access (bcrypt-hashed secrets) lets MSPs serve many customers from one Portal; every tenant query is tenant-scoped.
- **AI narrative.** MCP-driven executive/board summaries are embedded in Portal reports.

### 7.2 Why the split matters

Assessment happens **next to the estate** — regulated data never has to leave the customer's environment. The Portal is the visibility, distribution, and self-service layer on top. This is exactly the separation the hybrid model formalizes (§5): the engine is the operational platform; the Portal productizes its output for the economic buyer.

---

## 8. Deep dive — NERC-CIP & critical infrastructure

### 8.1 The stakes

NERC-CIP governs the cyber defense of the North American Bulk Electric System (BES). **Fines run up to $1M per violation per day** — which is precisely why compliance here is a board-level, non-discretionary budget line, and a wedge into the largest compliance spend.

### 8.2 Coverage — CIP-002 through CIP-015

AAC evaluates the full standard family against the OT OPA engine (`:8183`, `POST /v1/data/nerc_cip_main`):

| Standard | Focus | AAC treatment |
|---|---|---|
| **CIP-002** | BES cyber-system categorization | asset identification from `gather_facts` + scope tags |
| **CIP-003** | Security management controls | policy evaluation |
| **CIP-004** | Personnel & training | sidecar personnel context |
| **CIP-005** | Electronic Security Perimeters (ESP) | config assessment + drift enforcement |
| **CIP-006** | Physical security | evidence rollup |
| **CIP-007** | System security management (ports, patch, malware, logging) | assessment + auto-remediation |
| **CIP-008** | Incident reporting & response | **`CIP-008 Incident Response` template → BES forensic evidence to PostgreSQL** |
| **CIP-009** | Recovery plans | evidence rollup |
| **CIP-010** | Configuration change mgmt & vuln assessment | **`CIP-010 Baseline Capture` (capture/check modes) with authorized-change-ticket** |
| **CIP-011** | Information protection | policy evaluation |
| **CIP-012** | Control-center communications | assessment |
| **CIP-013** | Supply-chain risk management | **direct Rego — no certified scanner covers this** |
| **CIP-014** | Physical security (transmission) | evidence rollup |
| **CIP-015** | Internal Network Security Monitoring (INSM) | **`POST /v1/data/nerc_cip_cip015/cip_015_compliance_report`** |

### 8.3 AMI / smart-grid (NIST IR 7628)

Alongside NERC-CIP, AAC assesses **Advanced Metering Infrastructure** to NIST IR 7628 across three framework families — **device compliance, head-end security, and data protection** — driven by a Python smart-meter simulator for realistic telemetry, with dedicated Grafana dashboards. Endpoints: `/v1/data/ami/device/compliance`, `/v1/data/ami/headend/security`, `/v1/data/ami/nist_ir7628/complete`.

### 8.4 Hybrid + continuous OT monitoring

In the hybrid model, **Dragos / Nozomi / Claroty** (IEC 62443-4-1 certified) supply OT anomaly *verdicts*; AAC ingests them, does **CIP-013 supply chain directly**, rolls every finding up across CIP + IEC 62443, and produces the audit evidence. Event-Driven Ansible runs a **30-minute continuous NERC-CIP check** on the `critical_infrastructure` inventory group — detection-to-evidence without a human in the loop.

---

## 9. Deep dive — Digital Sovereignty

### 9.1 What it answers

Regulators increasingly ask not just *where* data is stored, but *who controls* the keys, the supply chain, the AI pipelines, and the network routes. AAC's Digital Sovereignty framework evaluates **70 controls across seven pillars**, mapped to **ENISA, GAIA-X, BSI C5, and GDPR Chapter V**, and rolls up to an organizational posture of **NON_SOVEREIGN → MODERATE_ASSURANCE → SOVEREIGN.** No certified scanner covers this — it is direct Rego assessment (OPA `:8182`).

### 9.2 The seven pillars

| Pillar | Controls | Focus |
|---|---|---|
| **Data Residency** (DR-001…010) | 10 | Regulated data stays in approved EU jurisdictions |
| **Cryptographic** (CS-001…011) | 11 | BYOK / HYOK / HSM — your keys, your control |
| **Infrastructure** (IS-001…010) | 10 | Cloud-concentration limits, CLOUD Act mitigation |
| **Software Supply Chain** (SS-001…010) | 10 | SBOM, no unverified updates |
| **Operational** (OS-001…010) | 10 | Personnel vetting, vendor access control |
| **Network** (NS-001…011) | 11 | DNS / DNSSEC / RPKI, no foreign egress |
| **AI / ML** (AL-001…008) | 8 | No EU data to foreign AI SaaS; inference within jurisdiction |

*Seven pillars, one continuous assessment* — the same fact→OPA→PostgreSQL→dashboard loop as every other framework, so sovereignty posture is tracked continuously and trended over the 13-month window rather than attested once a year.

### 9.3 Why it matters commercially

Sovereignty is a fast-emerging, high-assurance requirement across EU public sector and regulated industry (aligned to the EU AI Act mandatory dates and NIS2/DORA). Because AAC assesses it **directly** — no scanner dependency — it is a differentiated wedge into sovereign markets where competitors have no coverage.

---

## 10. Competitive positioning — scanners vs. enforcement

**The objection:** *"We already have Tenable / Qualys / Rapid7."*

| Commercial scanners | AAC + AAP |
|---|---|
| Find vulnerable packages | Find non-compliant **configurations, regulatory gaps, and AI-governance violations** |
| **Stop at the assessment line** | **Remediate automatically** |
| Provide a dashboard | Provide the **verifiable audit artifact the auditor demands** |
| Remediation → ticket queue for weeks | Closed loop in **seconds** |

> Your scanner finds the problem. **AAC fixes it, records it, and proves it to the auditor — using the automation you already own.** AAC does not compete with the scanner; it consumes the scanner's verdict and closes the loop the scanner can't.

---

## 11. Deployment & framework coverage

- **Deployment paths:** add to an **existing AAP** (primary, non-invasive), **greenfield** install, cloud/OpenShift (RHPDS) demo environments, or a full AWS demo datacenter.
- **505 Rego policies across 50+ frameworks and 22 platforms (tests excluded)**, split across security (:8181), compliance/management/sovereignty (:8182), and OT (:8183).
- **Integrations:** ServiceNow (bidirectional), Nagios, Prometheus, and MCP/Claude Code.

---

## 12. The closing narrative

> *"You already own the engine. AAC is the content layer that turns the AAP you bought for automation into the compliance-evidence platform your audit team desperately needs. Same operators, same controller, different budget."*

**Three takeaways:** **Follow the budget** (the 10–20× larger compliance spend) · **Ensure stickiness** (the 13-month immutable record is an unbreakable audit-lock) · **Force scale** (100% compliance coverage drives maximum AAP node expansion).

---

*Co-authored by Claude (Anthropic) with Tim Coulter. Figures, framework counts, and template/endpoint IDs track the current platform and the* Compliance Revenue Multiplier *deck as of 2026-07-09; verify against the live instance and the current strategy deck before external delivery. Certification and five-year economics are detailed in the companion* AAC Hybrid Certified-Tools Architecture *(v1.1).*
