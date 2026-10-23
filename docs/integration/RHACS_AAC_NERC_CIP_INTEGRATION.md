> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: SPLIT-PORTSx3, AAP-2.5/2.6x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Integrating Red Hat Advanced Cluster Security (ACS) with Ansible Automated Compliance (AAC) for NERC-CIP

**Version:** v1.1
**Date:** 2026-07-16
**Audience:** a large investor-owned utility — customer-facing
**Classification:** Confidential — prepared for prospective customer evaluation
**Authors:** Tim Coulter (Red Hat) with Claude (Anthropic)

> **v1.1 correction:** The cluster-side NERC-CIP content is the OpenShift **Compliance
> Operator** `ocp4-nerc-cip` profile (OpenSCAP/XCCDF), which **ACS manages and surfaces**;
> ACS also contributes its own runtime/vuln/supply-chain findings. AAC **collates** these
> `ComplianceCheckResult`s and ACS findings and **maps them to CIP controls** using its own
> versioned OPA/Rego. Earlier phrasing that implied ACS runs on Rego, or that AAC's
> NERC-CIP Rego evaluates ACS facts directly, has been corrected. See the companion
> validation report, `OCP4_NERC_CIP_COMPLIANCE_OPERATOR_VALIDATION.md`.

---

## 1. Executive Summary

a large investor-owned utility operates an increasingly containerized estate on Red Hat
OpenShift, and already uses **Red Hat Advanced Cluster Security for Kubernetes (ACS)**
to manage the security posture of those clusters. ACS is an excellent *sensor*: it
continuously evaluates image vulnerabilities, deployment and cluster configuration,
runtime behavior, and network exposure, and integrates with **OPA/Gatekeeper** for
Kubernetes admission control. Its findings are consumed and evaluated by **Ansible
Automated Compliance (AAC)** through AAC's **OPA/Rego** policy layer — so ACS output
becomes NERC-CIP evidence without a bespoke translation layer.

What ACS does **not** provide is a NERC-CIP *system of record*: a durable historical
compliance database, control-by-control mapping to CIP-002 through CIP-015, and
submission-ready audit reports and audit records that an auditor or the regional
entity will accept as evidence.

This document describes how AAC **collates ACS results, stores them in AAC's
historical compliance database, and generates NERC-CIP reports and audit records
from that data**. The result is a single, continuous, audit-ready NERC-CIP evidence
chain for the utility's containerized and OT-adjacent workloads — with **no rip-and-replace**
of ACS. ACS keeps doing what it does best; AAC turns its output into regulator-grade
compliance evidence.

**In one sentence:** ACS is the sensor, AAC is the OPA/Rego-based system of record and
audit engine — with ACS plugging in cleanly as a Red Hat-native evidence source.

---

## 2. The Opportunity

the utility is actively evaluating a NERC-CIP solution. The specific gap this integration
closes:

| the utility has today (with ACS) | the utility still needs |
|---|---|
| Continuous OCP/K8s security assessment (vuln, config, runtime, network) | The same signals expressed as **NERC-CIP control outcomes** |
| Point-in-time cluster security posture | **Historical tracking** — trend, drift, and "state on date X" for an audit window |
| Security violations and alerts | **Audit records and reports** an auditor/regional entity accepts as evidence |
| `ocp4-nerc-cip` check results scoped to the cluster | Those results **mapped to CIP-002 … CIP-015** and unified with host/OT evidence |
| Operator/SRE-facing dashboards | **Compliance-officer and auditor-facing** artifacts |

NERC-CIP violations carry penalties of **up to \$1,000,000 per violation per day**
(FERC enforcement). The value of a defensible, continuous, automated evidence chain
is measured against that exposure, not against tooling cost.

---

## 3. Solution Overview

### 3.1 The two OpenShift evidence streams

ACS on OpenShift produces NERC-CIP-relevant evidence through **two complementary
streams**, and it is important to be precise about each:

1. **Compliance Operator `ocp4-nerc-cip` profile (the cluster NERC-CIP "policies").**
   The OpenShift **Compliance Operator** runs the built-in `ocp4-nerc-cip` (Platform)
   and `ocp4-nerc-cip-node` (Node) profiles. These are **OpenSCAP/XCCDF** security
   content from the ComplianceAsCode community — *not* Rego. Each rule carries NERC-CIP
   control annotations (CIP-003-8, CIP-004-6, CIP-007-3, …) and produces one
   **`ComplianceCheckResult`** object per rule. **ACS manages and surfaces** these scans:
   it can create/schedule Compliance Operator scans and reports their results in its
   Compliance Dashboard. This stream natively covers the CIP families that map to
   OpenShift cluster configuration — **CIP-002, 003, 004, 005, 007, 009** (see §6).

2. **ACS-native findings.** ACS's own engine produces image vulnerability, runtime
   threat/network, and supply-chain (image provenance/signing) findings. This stream
   supplies evidence for controls the Compliance Operator profile does *not* cover —
   notably **CIP-007** (vuln/patch currency), **CIP-010** (config/vuln), **CIP-013**
   (supply chain), and **CIP-015** (runtime network monitoring). ACS's core detection
   engine is proprietary; it integrates with **OPA/Gatekeeper** for admission control.

### 3.2 Roles

- **ACS + Compliance Operator (sensor / assessor):** Assess the OpenShift estate —
  `ocp4-nerc-cip` XCCDF scans plus ACS-native image/runtime/supply-chain findings.

- **AAC (system of record / audit engine):** **Collates** both streams —
  `ComplianceCheckResult` objects and ACS-native findings — normalizes them to AAC's
  fact schema, **maps them onto NERC-CIP controls** (AAC's mapping/evaluation logic runs
  as OPA/Rego in the `opa-ot` container, :8183), persists every result to the
  **PostgreSQL historical compliance database**, and generates NERC-CIP reports and
  audit records.

### 3.3 Why this division is the right one

1. **Evidence is preserved with provenance, not re-derived.** Each collated record keeps
   its originating `ComplianceCheckResult` id or ACS object id as an auditor
   back-reference, rather than being reverse-engineered from an opaque report.
2. **AAC owns the CIP mapping in versioned Rego.** The control-mapping and roll-up logic
   are versioned Rego in git — reviewed, testable, and promoted through one pipeline —
   consuming check results and findings as input data.
3. **No rip-and-replace.** The Compliance Operator and ACS keep running unchanged; AAC
   adds the historical record, the CIP control mapping, and the audit artifacts they do
   not themselves provide.

---

## 4. Reference Architecture

```
        the utility OpenShift / Kubernetes estate
        ┌───────────────────────────────────────────────┐
        │  Compliance Operator      Red Hat ACS           │
        │  ocp4-nerc-cip (XCCDF)    image vuln · runtime  │
        │  → ComplianceCheckResults supply-chain · netpol │
        │        ▲  ACS manages/surfaces CO scans         │
        └───────────────┬─────────────────────────────────┘
                        │  (A) ACS/K8s API  (ComplianceCheckResults + ACS findings)
                        │  (B) ACS notifier → webhook (near-real-time)
                        │  (C) roxctl / oc export (batch, air-gapped)
                        ▼
        ┌───────────────────────────────────────────────┐
        │  AAC Collation Layer  (AAP 2.6 job / EDA)       │
        │  • pull/receive check results + ACS findings    │
        │  • normalize → AAC fact schema (keep prov. id)  │
        └───────────────┬─────────────────────────────────┘
                        │  normalized evidence (JSON)
                        ▼
        ┌───────────────────────────────────────────────┐
        │  AAC CIP mapping (OPA/Rego, opa-ot :8183)       │
        │  check-result/finding → CIP-002…015 control     │
        │  outcomes  (AAC's own mapping logic)            │
        └───────────────┬─────────────────────────────────┘
                        │  per-control results (JSON)
                        ▼
        ┌───────────────────────────────────────────────┐
        │  PostgreSQL  compliance_results  (JSONB)        │
        │  historical, timestamped, per-control evidence  │
        └───────────────┬─────────────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────────────────────┐
        │  Reports & Audit Records                        │
        │  • NERC-CIP audit report (DOCX / PDF)           │
        │  • per-control audit records                    │
        │  • Grafana historical dashboards                │
        └───────────────────────────────────────────────┘
```

*(Infrastructure endpoints are shown as roles, not addresses. Concrete hostnames are
supplied per environment at deployment time — `<ACS_CENTRAL_URL>`,
`<AAP_CONTROLLER_HOST>`, `<COMPLIANCE_DB_HOST>`.)*

---

## 5. Data Collation Pipeline

AAC collates ACS results in four stages. Each stage is idempotent and fully
automated through Ansible Automation Platform.

### 5.1 Acquire

Three supported acquisition modes (choose per the utility operational preference; they can
coexist):

| Mode | Mechanism | Best for |
|---|---|---|
| **(A) Pull** | Poll the ACS Central REST API and/or the Kubernetes API for **`ComplianceCheckResult`** objects (from the `ocp4-nerc-cip` scan) and ACS-native findings on a schedule | Steady-state periodic collection into the audit window |
| **(B) Push** | Configure an ACS **notifier** (generic webhook) to post violations to an **EDA** webhook listener | Near-real-time drift capture; event-driven re-assessment |
| **(C) Batch** | `roxctl` / `oc get compliancecheckresult -o json` export run as an AAP job | Point-in-time snapshots, backfills, disconnected/air-gapped collection |

### 5.2 Normalize

Both evidence streams are mapped to AAC's canonical **fact** shape so they can be
processed uniformly with facts from every other AAC source. A normalized record carries:

- `source: "compliance_operator"` (with the `ComplianceCheckResult` name/rule id) or
  `source: "acs"` (with the ACS alert/CVE id) — preserving a **verifiable
  back-reference** for auditors.
- `cluster`, `namespace`, `deployment`, `image` context.
- The rule/standard, its `severity`, and its status (`PASS`/`FAIL`/`MANUAL`/… for check
  results; severity/state for ACS findings).

### 5.3 Map to controls

Normalized evidence is evaluated by **AAC's own OPA/Rego mapping logic** (`opa-ot`,
:8183), which associates each check result / finding with the NERC-CIP control(s) it
supports and emits **per-control compliance outcomes** — the same output shape AAC
produces for host-level facts, so downstream reporting is unchanged. Note the direction:
AAC does not re-scan the cluster; it **maps existing check results and findings** onto
CIP controls. `MANUAL` check results are carried through as attestation-required, not
silently scored.

### 5.4 Persist

Every evaluation is written to `compliance_results` with a timestamp, giving the utility the
historical record ACS alone does not retain. See §7.

---

## 6. OpenShift → NERC-CIP Control Mapping

This is the core of the integration: which OpenShift evidence stream supports which CIP
requirement. The **Compliance Operator `ocp4-nerc-cip` profile** natively evidences the
cluster-configuration CIP families; **ACS-native findings** extend coverage to
vuln/supply-chain/runtime controls. AAC maintains the mapping as versioned Rego so it can
be tuned to the utility's environment and updated as CIP standards evolve.

| NERC-CIP Standard | Requirement focus | Evidence stream |
|---|---|---|
| **CIP-002 / CIP-003** Asset categorization, security management | Governance, crypto (FIPS), service-account/access | **Compliance Operator** `ocp4-nerc-cip` (native CIP-002/003 annotations) + cluster inventory |
| **CIP-004** Personnel & training | RBAC / access-management portion | **Compliance Operator** (RBAC rules); training/PRA are organizational, out of cluster scope |
| **CIP-005** Electronic Security Perimeters | Network segmentation, controlled connectivity | **Compliance Operator** (API access) + **ACS** network graph / NetworkPolicy analysis |
| **CIP-007** Systems Security Management | Ports/services, patching, malicious code | **Compliance Operator** (etcd encryption, RBAC, SCC) + **ACS** image-vuln patch currency & runtime detection |
| **CIP-009** Recovery plans | Recovery-relevant config | **Compliance Operator** `ocp4-nerc-cip` (CIP-009-6 rules, e.g. etcd backup) |
| **CIP-010** Config change mgmt & vuln | Baseline, drift, vuln assessment | **ACS** vulnerability assessment + **File Integrity Operator** node drift *(not in the native `ocp4-nerc-cip` profile)* |
| **CIP-013** Supply Chain Risk Management | Software/image integrity | **ACS** image provenance, signature verification, untrusted-registry/unsigned-image policies *(ACS-native, not CO)* |
| **CIP-015** Internal Network Security Monitoring | Network baseline + anomaly inside the ESP | **ACS** runtime network baselining & anomaly detection — maps closely to INSM R2 *(ACS-native, not CO)* |

> **Scoping note for the utility (validated):** The Compliance Operator `ocp4-nerc-cip` profile
> natively covers only **CIP-002, 003, 004, 005, 007, 009** — the controls evidenceable
> from OpenShift cluster configuration. It is **silent on** CIP-006/008/010/011/012/013/
> 014/015 by design. ACS-native findings extend the cluster story to CIP-007/010/013/015;
> the remaining organizational and physical controls (CIP-006/008/011/012/014, personnel
> process) are evidenced by AAC's host/OT fact sources and the utility process attestations, not
> by the cluster. The integration is **additive** and must not be represented to an
> auditor as full NERC-CIP coverage on its own. See the companion validation report,
> `docs/integration/OCP4_NERC_CIP_COMPLIANCE_OPERATOR_VALIDATION.md`.

---

## 7. Historical Database Integration

ACS findings land in the same `compliance_results` table AAC uses for every
framework, so ACS-sourced evidence is a first-class citizen in reports, trends, and
dashboards.

**Relevant columns (`compliance_results`):**

| Column | ACS-sourced value |
|---|---|
| `hostname` | Cluster / node identity (e.g. `ocp-prod-cluster-01`) |
| `framework` | `nerc_cip` (NOT NULL — always set) |
| `policy_name` | `NERC CIP` or `NERC CIP-015 INSM` |
| `policy_version` | CIP standard version string |
| `total_controls` / `passed_controls` / `failed_controls` | Derived from the mapped check results / findings |
| `compliance_percentage` | Per-run score |
| `compliant` | Boolean roll-up |
| `violations` (JSONB) | Failing controls, each carrying its back-reference — the `ComplianceCheckResult` rule id or the ACS alert/CVE id |
| `metadata` (JSONB) | Assessment context: `organization`, `assessment_date`, Compliance Operator / ACS version, cluster inventory, `source` ∈ {`compliance_operator`, `acs`} |
| `evaluation_timestamp` | When AAC collated and mapped the evidence |

Because each `violations` entry retains the originating `ComplianceCheckResult` rule id
or ACS object id, an auditor can trace any NERC-CIP finding in AAC **back to the exact
check result or ACS alert** that produced it — a complete, defensible evidence chain.

Storage is via the existing `aac_store_results` role, which is the single writer to
`compliance_results` and already enforces the NOT-NULL `framework` contract. No schema
change is required to onboard the Compliance Operator or ACS as a source.

---

## 8. Report & Audit Record Generation

AAC generates NERC-CIP artifacts **from the stored data**, so ACS-sourced evidence
flows into the existing report pipeline with no new report code:

- **NERC-CIP Audit Report (DOCX + PDF):** The existing generators
  (`scripts/generate_nerc_cip_docx.py`, `scripts/generate_nerc_cip_pdf.py`) query the
  latest stored results and render a submission-ready report — cover page, executive
  summary, scope, per-control results (now populated by ACS evidence for the cluster
  scope), findings, remediation, and an auditor-certification block.
- **Per-control audit records:** Each `compliance_results` row is itself a timestamped
  audit record; the ACS back-references make it self-evidencing.
- **Historical dashboards:** The NERC-CIP Grafana dashboard visualizes trend and drift
  over the audit window from the same table.

Report generation is driven by AAP job templates (never ad-hoc CLI), consistent with
AAC's "packaged solution" operating model.

---

## 9. Integration Mechanics

### 9.1 New AAP job templates (proposed)

| Template | Playbook | Function |
|---|---|---|
| **AAC - Collate OpenShift Compliance** | `acs_collate_results.yml` (new) | Acquire `ocp4-nerc-cip` `ComplianceCheckResult`s + ACS findings (mode A/B/C), normalize, map to CIP controls via AAC's OPA/Rego, store to PostgreSQL |
| **AAC - NERC CIP Compliance Report** | *(existing)* | Roll up stored results into the CIP assessment |
| **NERC/AMI - Generate Audit PDF** | *(existing)* | Render the submission-ready audit report |

### 9.2 Execution Environment

The collation playbook runs in the **AAC Compliance EE**, which already carries
`community.postgresql` for the database writes. ACS acquisition uses the ACS Central
API token (stored as an AAP credential) or `roxctl`.

### 9.3 Event-driven mode (EDA)

For push mode, an EDA rulebook listens on a dedicated webhook port; an ACS notifier
posts violations, and the rulebook triggers **AAC - Collate ACS Results** so the
historical record updates within seconds of a new ACS finding — the same event-driven
pattern AAC already uses for drift detection.

### 9.4 Security & credentials

- ACS Central API token and `<COMPLIANCE_DB_HOST>` credentials are held as AAP
  credentials, never in playbooks.
- All collation is **read-only** against ACS and **append-only** against the historical
  database — the integration never mutates the utility's clusters or ACS configuration.

---

## 10. Competitive Positioning — ACS + AAC vs. NeuVector

the utility is weighing **NeuVector** (SUSE) for container security. NeuVector is a capable
full-lifecycle container-security product (vulnerability scanning, admission control,
runtime protection, zero-trust network segmentation). This section is deliberately
fair about that — and clear about why the **ACS + AAC** combination is the stronger
answer *for a NERC-CIP outcome on OpenShift*.

The decision is not sensor-vs-sensor. It is: **do you also get a NERC-CIP system of
record and audit engine, and does your security tooling fit your platform?**

| Dimension | NeuVector (SUSE) — standalone | ACS + AAC (Red Hat) |
|---|---|---|
| **NERC-CIP system of record** | Not provided — general compliance/benchmark reporting only; still requires a separate compliance layer | **AAC provides it** — historical PostgreSQL evidence, per-control audit records, submission-ready reports |
| **Compliance evaluation substrate** | Would need a separate NERC-CIP compliance/audit layer bolted on | **AAC maps evidence to CIP controls in versioned OPA/Rego** and is Red Hat-native — it collates the Compliance Operator `ocp4-nerc-cip` check results and ACS findings directly |
| **Platform fit** | SUSE product introduced into a Red Hat OpenShift estate — a cross-vendor seam | **OpenShift-native** — ACS is part of the Red Hat platform the utility already runs |
| **Support model** | Multi-vendor (SUSE + Red Hat OpenShift + whatever compliance tool) | **Single-vendor Red Hat** across ACS + AAP + AAC |
| **Orchestration** | Bespoke integration to drive collection and reporting | **AAP-native** collection, evaluation, and reporting (the utility likely already runs AAP) |
| **Auditor evidence chain** | Findings not natively mapped to CIP controls | Every CIP finding **back-references the exact ACS object** that produced it |
| **CIP-015 INSM fit** | Runtime/network monitoring present, but not expressed as CIP-015 evidence | ACS network baseline/anomaly → **CIP-015 R2 evidence** in the historical record |

**The core message for the utility:** choosing NeuVector solves container security but leaves
the NERC-CIP compliance and audit problem unsolved — you would still need AAC (or an
equivalent) on top, wired in through custom integration to a non-OPA policy model.
Choosing **ACS + AAC** solves both with one Red Hat-native, OpenShift-aligned stack —
ACS as the sensor, AAC's OPA/Rego engine as the compliance system of record — using
the OpenShift platform and automation the utility already operates.

> **Positioning discipline:** Lead with the *compliance system-of-record gap* and the
> *OpenShift-native platform fit*. Do not disparage NeuVector's security capabilities —
> the win is integration completeness and platform alignment, not a sensor bake-off.

---

## 11. Phased Implementation Roadmap

| Phase | Scope | Outcome |
|---|---|---|
| **0 — Discovery** | Confirm the utility ACS topology, cluster inventory in NERC-CIP scope, audit window, and reporting cadence | Agreed control-mapping scope |
| **1 — Collation MVP** | Pull-mode (A) acquisition + normalize + store for CIP-010 and CIP-007 (highest-fit controls) | ACS evidence visible in the historical DB |
| **2 — Full mapping** | Extend mapping to CIP-005, CIP-011, CIP-013, CIP-015 | Complete cluster-scope CIP coverage |
| **3 — Reporting** | Generate first the utility NERC-CIP audit report + dashboards from stored ACS data | Submission-ready artifacts |
| **4 — Event-driven** | Add ACS notifier → EDA push mode | Near-real-time drift capture |
| **5 — Operationalize** | Scheduling, retention policy, runbooks, handover | Continuous, hands-off evidence chain |

---

## 12. Assumptions & Open Questions

**Assumptions**
- the utility runs the OpenShift **Compliance Operator** with the `ocp4-nerc-cip` /
  `ocp4-nerc-cip-node` profiles bound to a scan, and **ACS** with API access reachable
  from the AAP control plane (or an `oc`/`roxctl` export path for disconnected segments).
- The NERC-CIP-in-scope workloads are identifiable by cluster/namespace labeling.
- Compliance Operator content version is captured at onboarding — the `ocp4-nerc-cip`
  rule set and control coverage are version-dependent (see the validation report).

**Open questions for the utility discovery**
1. Which clusters/namespaces are in NERC-CIP scope (High/Medium impact BES Cyber
   Systems on OpenShift)?
2. Required audit window and retention period for historical evidence?
3. Preferred acquisition mode(s) — pull, push, batch, or a mix?
4. Existing GRC/system-of-record that AAC audit records must feed or reconcile with?
5. Regional entity / auditor formatting requirements for submitted reports?

---

## Appendix A — Sample normalized evidence records (illustrative)

A Compliance Operator `ocp4-nerc-cip` check result:

```json
{
  "source": "compliance_operator",
  "check_result": { "name": "ocp4-nerc-cip-api-server-encryption-provider-cipher",
                    "rule_id": "xccdf_org.ssgproject.content_rule_api_server_encryption_provider_cipher",
                    "scan": "ocp4-nerc-cip", "cip_controls": ["CIP-007-3"] },
  "cluster": "ocp-prod-cluster-01",
  "severity": "high",
  "status": "FAIL",
  "detail": "etcd encryption provider cipher not set to aescbc (encryption in transit, CIP-007-3 R5.1)"
}
```

An ACS-native finding (for a control the CO profile does not cover):

```json
{
  "source": "acs",
  "acs_object": { "type": "image_vulnerability", "id": "b8e1...c4", "cve": "CVE-2026-1234" },
  "cluster": "ocp-prod-cluster-01",
  "namespace": "ot-workloads",
  "deployment": "historian-api",
  "image": "registry.example/ot/historian@sha256:...",
  "severity": "HIGH",
  "state": "FAIL",
  "control_hint": "CIP-007",
  "detail": "Fixable critical CVE past 35-day patch window (patch currency, CIP-007 R2)"
}
```

## Appendix B — Sample control-mapping entries (illustrative)

```yaml
# openshift_to_nerc_cip_map.yml  (versioned config consumed by the collation playbook)
# Compliance Operator ocp4-nerc-cip rules already carry CIP annotations — map by rule id:
- check_rule: "xccdf_org.ssgproject.content_rule_api_server_encryption_provider_cipher"
  nerc_cip: ["CIP-007"]
  rationale: "etcd encryption in transit (CIP-007-3 R5.1) — from ocp4-nerc-cip"
# ACS-native signals extend coverage beyond the CO profile:
- acs_signal: "image_vulnerability_overdue_patch"
  nerc_cip: ["CIP-007"]
  rationale: "Patch currency within 35-day requirement (CIP-007 R2)"
- acs_signal: "runtime_network_anomaly"
  nerc_cip: ["CIP-015"]
  rationale: "Internal network anomaly detection inside the ESP (CIP-015 R2) — ACS-native"
```

## Appendix C — Sample stored audit record (illustrative `compliance_results` row)

```json
{
  "hostname": "ocp-prod-cluster-01",
  "framework": "nerc_cip",
  "policy_name": "NERC CIP",
  "policy_version": "CIP-002 through CIP-015",
  "compliance_percentage": 83.3,
  "compliant": false,
  "violations": [
    {
      "control": "CIP-010",
      "severity": "HIGH",
      "description": "Configuration drift from approved baseline on historian-api",
      "evidence_source": "acs",
      "acs_object_id": "b8e1...c4"
    }
  ],
  "metadata": { "organization": "a large investor-owned utility", "source": "acs",
                "assessment_date": "2026-07-16", "cluster_count": 1 },
  "evaluation_timestamp": "2026-07-16T00:00:00Z"
}
```

---

*This document describes a proposed integration design. All infrastructure endpoints
are shown as roles or placeholders and are supplied per environment at deployment
time. Sample data is illustrative and does not represent an actual the utility compliance
assessment.*
