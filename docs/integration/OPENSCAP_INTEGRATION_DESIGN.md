# OpenSCAP Integration — Design & Implementation Plan

**Version:** v1.1
**Date:** 2026-07-03
**Classification:** Internal — Solution Architecture
**Status:** Phases 1-3 implemented — the #536 `openscap_assess.yml` pipeline (scan → `scripts/openscap_xccdf_parse.py` → `aac_store_results`), refactored 2026-09-23 into reusable roles `aac_oscap_scan` + `aac_oscap_ingest` (the playbook composes them; the ingest role also accepts externally produced XCCDF/ARF, e.g. CIS-CAT Pro). Results land under their own `openscap_*` framework key with CCE/CCI idents captured; Phases 4-6 (CCI mapping data, precedence, OVAL-SC snapshots, gated remediation) open
**Authors:** Tim Coulter (architecture) · Claude (Anthropic) — Claude Code (design capture & drafting)

---

## Executive Summary

AAC assesses infrastructure by **gathering facts with Ansible → evaluating them in OPA/Rego →
storing results in PostgreSQL**, which gives it a uniform, historical, cross-framework compliance
store. OpenSCAP is a **host-resident SCAP scanner** (`oscap` + SCAP Security Guide) that produces
authoritative, auditor-recognized OS-hardening evidence via OVAL.

This document specifies how to add OpenSCAP as an **optional, ingested evidence source** — enabled
per customer when they require SCAP/DISA-STIG attestation — **without changing the AAC spine**. The
Ansible→OPA→PostgreSQL model remains the default for the entire estate; OpenSCAP rides on top for a
slice of hosts, and its results are normalized into the **same** `compliance_results` store so they
participate in history, technical-debt scoring, and cross-framework linked evaluations exactly like
native evidence.

**Design principle in one line:** *keep gather-facts as the spine for the whole environment; make
OpenSCAP an opt-in fidelity/attestation upgrade for the OS layer, ingested into the same store —
never a replacement.*

---

## 1. Why this is opt-in, not a replacement

A pure-OpenSCAP compliance program would lose two things AAC depends on:

1. **The uniform fact/result store that powers history and linking.** OpenSCAP emits per-host,
   point-in-time ARF/XCCDF verdicts in its own format and keeps no history of its own. The AAC
   `compliance_results` table holds every framework's evidence in one normalized JSONB shape — that
   uniformity is what makes trend lines, control-to-control linking (CIS → NIST 800-53 → FISMA),
   and technical-debt accrual possible.

2. **Most of the inputs.** OpenSCAP reaches only the Linux-host and container-image layer. The
   `technical_debt_assessment` rolls up **17 frameworks** (`cis_rhel9, nerc_cip, ami,
   digital_sovereignty, nist_800_53, iso27001, ncsc_caf, dora, nis2, nist_800_82, ny_dfs, sec_cyber,
   swift_csp, hitrust, tisax, cfr_part_11, cis_gcp`); OpenSCAP can produce exactly **one**
   (`cis_rhel9`). Going pure-OpenSCAP would collapse a 17-framework rollup to a single benchmark.

Therefore OpenSCAP is added as an **evidence source feeding the existing store**, upgrading OS-layer
fidelity where a customer requires it, while the DB + OPA analytics layer runs unchanged.

---

## 2. Background — OpenSCAP vs the AAC Rego platform

### 2.1 What each is

| | OpenSCAP | AAC (Ansible → OPA/Rego → PostgreSQL) |
|---|---|---|
| Role | Host-level SCAP compliance scanner | Cross-domain policy-as-code platform |
| Engine | `oscap` (OVAL/XCCDF) | OPA (Rego) |
| Content | SCAP Security Guide / ComplianceAsCode (upstream-maintained) | Hand-authored Rego library (505 policies) |
| Collection | Coupled — the scanner probes the live host and evaluates in one pass | Decoupled — Ansible gathers facts; OPA evaluates any JSON |
| Output | ARF / XCCDF results (per-rule pass/fail + collected characteristics) | Normalized JSONB in `compliance_results` |
| History | Point-in-time (Insights/Satellite add some, RHEL-scoped) | PostgreSQL time-series across all frameworks |

### 2.2 Benefits OpenSCAP brings (AAC's current gaps)

- **Content currency.** SSG is upstream-maintained and version-tracked. This directly retires AAC's
  biggest maintenance risk — the Rego OS benchmarks drift (audit found all STIGs behind, CIS M365
  v3.1→v7.0, Azure/Windows-Server behind, NIST 800-171 mixing withdrawn Rev 2).
- **Check fidelity.** OVAL inspects real system state (rpm DB, file contents, permissions, kernel
  args, SELinux booleans) on the host. AAC checks are only as good as the Ansible facts gathered.
- **Auditor/attestation recognition.** NIST SCAP-validated; ARF/XCCDF results are recognized by DISA
  (STIG), FedRAMP, and assessors. Custom JSON is not.
- **Remediation generation.** `oscap xccdf generate fix --fix-type ansible` and bootc image hardening
  (`oscap-im`) from the same content.
- **Ecosystem fit.** Ships in RHEL; integrates with AAP, Insights compliance, Satellite.

### 2.3 Gaps OpenSCAP has (AAC's advantages)

- **Breadth.** SSG is host-OS profiles only. AAC covers cloud (AWS/Azure/GCP), containers, network
  devices, SaaS (M365), and — critically — management/regulatory frameworks (SOC 2, ISO 27001,
  NERC-CIP, DORA, NIS2, HIPAA, SEC Cyber, SWIFT CSP, TISAX) OpenSCAP cannot do.
- **One engine, many surfaces.** Rego also does K8s admission, Terraform-plan gating, CI/CD
  enforcement, AI/MCP governance. OpenSCAP is scan-only.
- **Framework roll-up, history, analytics, fact-source flexibility** — all AAC strengths.

---

## 3. Coverage analysis — how much OpenSCAP can actually own

Counted from the Rego library (510 policy files, tests excluded):

| Layer | Policies | OpenSCAP reality |
|---|---|---|
| Linux OS (CIS RHEL/Ubuntu/Rocky/Debian/Amazon) | 152 | ✅ clean `oscap` core |
| STIG Linux (RHEL/Ubuntu) | 26 | ✅ clean `oscap` core |
| Windows OS (CIS) | 24 | ⚠️ SCAP-*ecosystem* (DISA SCC), not `oscap` itself |
| Containers / OpenShift | 7 | ✅ images (`oscap-podman`/bootc), OpenShift (Compliance Operator); ❌ generic K8s |
| **Subtotal "SCAP could own"** | **~209 (41%)** | clean `oscap` core ≈ **178** |
| Regulatory/management frameworks | 220 | ❌ none |
| Cloud (AWS/Azure/GCP) | 9 | ❌ none |
| SaaS (M365) | 7 | ❌ none |
| Network devices (Cisco/Juniper/Arista/PAN/Forti/VyOS) | 7 | ❌ none — cannot install the scanner on an appliance |
| Databases (PostgreSQL/MySQL/Oracle) | 5 | ⚠️ thin/manual; effectively AAC's |
| Governance / Enforcement / Web / Threat | 30 | ❌ none |
| **Subtotal "only Rego"** | **~296 (59%)** | |

**Bounded offload:** ~178 policies (the Linux-OS core — also the *most drift-prone* content) are
cleanly OpenSCAP-ownable. The other ~300 stay uniquely Rego, and **220 of them (44% of the library)
are regulatory frameworks OpenSCAP cannot touch.**

**Root cause of the boundary:** `oscap` (and `oscap-ssh`, which copies content to the target and
runs `oscap` there) must execute **on the machine being assessed**. Anything you cannot install the
scanner on — network appliances, cloud control planes, SaaS — is out of scope by design.

---

## 4. The collection-model difference (the crux)

- **OPA/Rego is data-agnostic** — a pure function, `facts in → decision out`. It evaluates whatever
  it is handed: live facts *or* facts already stored in PostgreSQL. This is why re-evaluating stored
  facts against updated policy works today (`evaluate_stored_facts.yml`).
- **OpenSCAP is collection-coupled** — its OVAL engine *is* the collector; it probes a live host (or
  a mounted image) and evaluates in the same pass. Its input is a system, not a database row.

Consequence — three integration models:

| Model | Description | Verdict |
|---|---|---|
| **1. Grab + store verdicts** | Run `oscap` on hosts → ARF/XCCDF → **ingest normalized results into `compliance_results`** → OPA rolls up | ✅ **Primary** |
| **2. Decoupled re-evaluation** | Store OVAL **System Characteristics** snapshots; re-evaluate offline against a newer benchmark without re-scanning | ➕ Optional (historical re-scoring) |
| **3. `oscap` over existing Ansible-fact JSON** | Point `oscap` at facts already in Postgres | ❌ Not viable — format mismatch; this is OPA's job |

The two patterns map onto the two engines' strengths: *"evaluate data already in the database"* is
an **OPA** strength (re-judge stored facts anytime policy/benchmark changes, offline); *"grab
authoritative current state"* is an **OpenSCAP** strength. Combine them via Model 1.

---

## 5. Target architecture

```
                    ┌──────────────────────────────────────────────┐
                    │            AAP 2.6 (orchestration)            │
                    └──────────────────────────────────────────────┘
        gather-facts (default, whole estate)     OpenSCAP option (per-host, opt-in)
        ┌───────────────────────────────┐        ┌───────────────────────────────┐
        │ Ansible fact collection        │        │ aac_oscap_scan role            │
        │ (OS, cloud, SaaS, network, …) │        │  oscap xccdf eval --profile … │
        └───────────────┬───────────────┘        │  → ARF + XCCDF results + HTML  │
                        │ facts (JSON)            └───────────────┬───────────────┘
                        ▼                                         │ ARF
                ┌───────────────┐                         ┌───────▼────────────────┐
                │ OPA / Rego     │ evaluate               │ aac_oscap_ingest        │
                │ (facts→verdict)│                         │  parse ARF → normalize  │
                └───────┬───────┘                         └───────┬────────────────┘
                        │ normalized results                      │ normalized results
                        ▼                                         ▼
                ┌────────────────────────────────────────────────────────────────┐
                │  PostgreSQL  compliance_results  (single normalized store)       │
                │  hostname · framework · violations(jsonb) · metadata(jsonb) …    │
                └───────────────────────────────┬────────────────────────────────┘
                                                │
                        ┌───────────────────────┴───────────────────────┐
                        ▼                                                ▼
            OPA framework roll-up / linking              technical_debt · trends · reports
            (CCI/CCE → NIST 800-53 → framework)          (17-framework, source-agnostic)
```

**Key point:** OpenSCAP output enters the **same store** and is thereafter indistinguishable to the
analytics layer except by a `metadata.evidence_source` tag. History, technical debt, and linked
evaluations keep working because they read `compliance_results`, not the scanner.

---

## 6. Components to build

### 6.1 `aac_oscap_scan` (Ansible role + AAP job template)
Runs the scan against target host(s).
- **Inputs (survey vars):** `oscap_target`, `oscap_profile` (e.g. `xccdf_org.ssgproject.content_profile_stig`),
  `oscap_datastream` (SSG datastream for the OS, e.g. `ssg-rhel9-ds.xml`), `oscap_mode` (`assess`
  default | `assess+remediate`, gated).
- **Execution options:**
  - *On-target* (preferred, RHEL-native): `oscap` + `scap-security-guide` present on the host; AAP
    runs the scan via SSH/`delegate_to`.
  - *`oscap-ssh`* orchestration from the controller/EE when the target lacks the package but can
    accept a copied datastream + temporary scanner.
- **Outputs:** ARF (`--results-arf`), XCCDF results XML (`--results`), HTML report (`--report`).
  Copy artifacts back to the controller via SCP (see EE `/tmp` caveat in repo docs).
- **AAP template name:** `AAC - OpenSCAP Host Scan`.

### 6.2 `aac_oscap_ingest` (Ansible role/playbook + parser)
Parses ARF/XCCDF and writes normalized rows.
- Parse with `oscap xccdf generate report`/`--results` or a Python parser (lxml) in the EE.
- Map to the `compliance_results` schema (§7).
- Insert via `community.postgresql.postgresql_query` from the EE (no podman in EE).
- **AAP template name:** `AAC - Ingest OpenSCAP Results`. Chain Scan → Ingest as a workflow
  (`AAC - OpenSCAP Assess & Store`).

### 6.3 OPA roll-up / control mapping (extend existing)
So OpenSCAP hosts feed technical-debt and linked evaluations:
- Persist each failed rule's **reference IDs** (CCE, DISA CCI, XCCDF rule id, severity) in the
  `violations` JSONB.
- Add/extend a mapping layer (`CCI → NIST 800-53 → framework`) so an OpenSCAP STIG finding rolls up
  into NIST 800-53 / FISMA / FedRAMP posture the same way a Rego finding does. DISA publishes the
  CCI-to-800-53 mapping; ship it as reference data.

### 6.4 Optional — `aac_oscap_snapshot` (Model 2)
Store OVAL **System Characteristics** (the raw collected state) alongside results so a host can be
**re-scored against a newer benchmark offline** without re-scanning — preserving the
"re-evaluate raw state when the standard moves" capability for the OS layer.

### 6.5 Optional — remediation (gated)
`oscap xccdf generate fix --fix-type ansible` produces an idempotent remediation playbook.
**Read-only by default** per AAC principle #3 (assess before remediate); gate behind explicit
approval / change ticket, mirroring the CIP-010 baseline pattern.

---

## 7. Data model — mapping ARF/XCCDF → `compliance_results`

Reuse the existing 7-column result contract; no schema change required.

| Column | Source from OpenSCAP |
|---|---|
| `hostname` | scan target |
| `framework` | benchmark key, e.g. `stig_rhel9` (**same key** as the Rego equivalent so roll-ups merge) |
| `policy_name` | XCCDF profile title (e.g. "DISA STIG for Red Hat Enterprise Linux 9") |
| `policy_version` | benchmark version from the datastream (e.g. `V2R8`) |
| `total_controls` | count of rules evaluated |
| `passed_controls` / `failed_controls` | XCCDF result counts (`pass` / `fail`+`error`) |
| `compliance_percentage` | `passed / total * 100` |
| `compliant` | `failed == 0` (or a profile threshold) |
| `violations` (jsonb) | array of failed rules: `{rule_id, xccdf_id, cce, cci, nist_800_53_refs, severity, title}` |
| `metadata` (jsonb) | `{evidence_source: "openscap", profile_id, datastream, benchmark_version, arf_uri, scan_time, oscap_version, ssg_version}` |

**Source disambiguation & precedence.** A host's OS layer could in principle be evaluated by both
Rego and OpenSCAP. Rules:
- Tag every row with `metadata.evidence_source` (`ansible_facts` | `openscap`).
- Define precedence: when OpenSCAP evidence exists for a `(hostname, framework)`, prefer it for
  reporting/attestation and mark the Rego row superseded (do **not** double-count).
- `technical_debt` and trends aggregate by `framework`, source-agnostic — so an OpenSCAP-scanned
  RHEL host still appears in the 17-framework rollup, just with higher-fidelity OS evidence.

---

## 8. Implementation plan (phased)

| Phase | Deliverable | Notes |
|---|---|---|
| **0. Decide & scope** | Confirm the customer + which benchmarks require SCAP attestation | See §9 scoping criteria. Environment must be RHEL (oscap-native). |
| **1. Scan** | `aac_oscap_scan` role + `AAC - OpenSCAP Host Scan` template; ARF/XCCDF/HTML artifacts captured | On-target preferred; `oscap-ssh` fallback. |
| **2. Parse & normalize** | ARF/XCCDF parser → `compliance_results` shape | Python (lxml) in the EE, or `oscap` result generation. |
| **3. Ingest** | `aac_oscap_ingest` writes rows via `community.postgresql`; Scan→Ingest workflow | Include `framework` (NOT NULL) + `evidence_source` metadata. |
| **4. Link** | CCI/CCE → NIST 800-53 → framework mapping so OpenSCAP feeds technical-debt + linked evals | Ship DISA CCI mapping as reference data. |
| **5. Precedence** | Source-preference + dedup so OS findings aren't double-counted | OpenSCAP wins for the OS layer when present. |
| **6. Optional** | (a) retire/deprecate the ~178 drift-prone OS Rego (or keep as fallback); (b) OVAL-SC snapshots for re-scoring; (c) gated remediation | Decide per customer. |

**EE / runtime:** `oscap` + `scap-security-guide` on RHEL targets (ubi9-native); the AAC EE handles
orchestration + ARF parsing + Postgres writes. Use `podman`/`oscap-podman` for container-image
scanning. No lab identifiers in any customer artifact — use `<target-host>` / RFC 5737 `192.0.2.x`.

---

## 9. Scoping — when a customer "requires it"

Enable the OpenSCAP option when one or more hold:
- **Recognized attestation required** — DISA STIG / SCAP-validated results are contractually
  mandated (DoD, FedRAMP, federal).
- **Deep host checks** — FIPS mode, cryptographic policy, or low-level OS state that Ansible facts
  cannot reliably capture.
- **High-assurance hardening proof** — auditor demands ARF/XCCDF artifacts, not custom JSON.

Everything else — the entire agentless estate and every framework roll-up — stays on gather-facts,
uniform and re-evaluatable. OpenSCAP rides as a fidelity/attestation upgrade on a slice of the ~178
OS policies while the 505-policy, 17-framework analytics engine keeps running on the fact store.

---

## 10. Trade-offs & risks

| Trade-off / risk | Mitigation |
|---|---|
| Storing OpenSCAP **verdicts** loses "re-evaluate raw OS facts against new policy in OPA" | Adopt Model 2 (store OVAL System Characteristics) where re-scoring matters |
| Windows: `oscap` support is weak | Use DISA SCC for Windows attestation, or keep Windows on Rego |
| Content currency becomes OpenSCAP's responsibility | Track SSG/datastream + benchmark versions; pin and bump deliberately |
| **Silo risk** — `oscap` HTML/ARF that never reaches the DB is invisible to technical-debt/linking | **Non-negotiable: ingest to `compliance_results` (Model 1)**; standalone reports are a supplement, not the integration |
| Dual-source double-counting of OS findings | `evidence_source` tag + precedence rule (§7) |
| Scan cost heavier than fact-gather | Schedule OpenSCAP scans on their own cadence; don't couple to the fast fact-gather loop |
| Hardened/minimal targets may lack the scanner | `oscap-ssh` (copy datastream + temporary scanner) or bake into the golden image |

---

## 11. What is preserved (the whole point)

- **Uniform historical store** — one JSONB schema, all frameworks, all sources.
- **Technical debt** — still a 17-framework rollup; OpenSCAP simply upgrades the `cis_rhel9`/STIG
  inputs.
- **Linked evaluations** — CIS/STIG → NIST 800-53 → FISMA/FedRAMP mapping keeps working because
  OpenSCAP findings carry CCE/CCI references into the same store.
- **Re-evaluation & trends** — unchanged for the estate; optionally extended to the OS layer via
  OVAL-SC snapshots.

---

## Appendix A — Reference commands

```bash
# Assess a RHEL 9 host against the DISA STIG profile, emit machine + human artifacts
oscap xccdf eval \
  --profile xccdf_org.ssgproject.content_profile_stig \
  --results-arf   /var/tmp/arf-<host>.xml \
  --results       /var/tmp/xccdf-results-<host>.xml \
  --report        /var/tmp/report-<host>.html \
  /usr/share/xml/scap/ssg/content/ssg-rhel9-ds.xml

# Remote orchestration when the target lacks a local scanner
oscap-ssh <user>@<target-host> 22 xccdf eval --profile <profile> <datastream>

# Generate an idempotent remediation playbook (gated; do not auto-apply)
oscap xccdf generate fix --fix-type ansible \
  --profile <profile> --result-id "" /var/tmp/xccdf-results-<host>.xml \
  > remediate-<host>.yml

# Scan a container image
oscap-podman <image> xccdf eval --profile <profile> <datastream>
```

## Appendix B — References
- OpenSCAP User Manual — https://static.open-scap.org/openscap-1.3/oscap_user_manual.html
- SCAP Security Guide — https://www.open-scap.org/security-policies/scap-security-guide/
- ComplianceAsCode/content — https://github.com/ComplianceAsCode/content
- Red Hat — Compliance Operator vs OPA (complementary) — https://www.redhat.com/en/blog/how-does-compliance-operator-work-for-openshift-part-1
- DISA CCI ↔ NIST 800-53 mapping — https://public.cyber.mil/stigs/cci/

## Appendix C — Related AAC docs
- `docs/architecture/AAC_ARCHITECTURE_ASSESSMENT.md`
- `docs/integration/AAP_OPA_INTEGRATION_GUIDE.md`
- Rego policy currency audit & contract-drift findings (motivating content-drift context)

---

*Document co-authored by Claude (Anthropic) via Claude Code, per AAC AI-authorship transparency
convention. Bump the version on every revision.*
