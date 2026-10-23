> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: SPLIT-PORTSx1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# NERC-CIP Automated Compliance — AAC Check Coverage & Fact-Gathering

**Version:** v1.2
**Date:** 2026-07-31
**Audience:** a large investor-owned utility — currently collecting NERC-CIP evidence with home-grown scripts.
**Scope:** Two layers of NERC-CIP coverage. **Part I** — the OpenShift cluster: what the Compliance Operator produces vs. what AAC generates as system-of-record. **Part II** — the full CIP-002→CIP-015 check index and how AAC/AAP gathers every underlying fact (the direct comparison to home-grown collection).
**Grounding:** cluster attributes and the §6 per-standard coverage counts are measured from a live `ocp4-nerc-cip` scan (125 ComplianceCheckResults, Compliance Operator v1.9.1, 2026-07-31), read from each CCR's own `control.compliance.openshift.io/NERC-CIP` annotation + the AAC `compliance_results` row produced by `collate_ocp_nerc_cip.yml`; the CIP-002→015 index is from the `nerc_cip` Rego library data model — not illustrative.
**Authors:** Tim Coulter; Claude (Anthropic).

---

## Part I — Cluster layer: AAC vs. the OpenShift Compliance Operator

## 1. The short answer

The Compliance Operator produces **per-check, point-in-time** results that live in the cluster's etcd. AAC **collates, maps, scores, persists, and makes them auditor-traceable** — turning raw check output into an audit record with history and an evidence chain. AAC does not replace the operator; it is the record layer on top of it (and, when present, on top of ACS-native findings).

---

## 2. What the Compliance Operator generates — per `ComplianceCheckResult`

Every check the operator runs emits one `ComplianceCheckResult` object with these attributes:

| Group | Attributes (verified from a live FAIL) |
|---|---|
| **Result** | `status` (PASS / FAIL / MANUAL / INFO / ERROR / NOT-APPLICABLE), `severity` (low/medium/high) |
| **Identity** | `id` (XCCDF rule id, e.g. `xccdf_org.ssgproject.content_rule_api_server_encryption_provider_cipher`), `metadata.name`, `metadata.uid`, `metadata.namespace` |
| **Human content** | `description` (~730 chars), `instructions` (~1,100 chars — how to remediate), `rationale`, `warnings` (when present) |
| **Labels** | `check-status`, `check-severity`, `automated-remediation` (is auto-remediation available), `profile-guid`, `scan-name`, `suite` |
| **Control mappings** (annotations) | `control.compliance.openshift.io/`: **NERC-CIP**, NIST-800-53, CIS-OCP, PCI-DSS, PCI-DSS-4-0, STIG, STIGID, SRG, BSI; plus OCM `controls`/`standards`; `rule`; `last-scanned-timestamp` |
| **Lineage** | `ownerReferences` (to the scan), `creationTimestamp`, `resourceVersion`, `generation` |

**What the operator does NOT give you (the audit gaps):**
- **No aggregation** — 125 individual objects, no per-CIP-control roll-up or score.
- **No history** — results are current-state only; a re-scan overwrites, and if the operator/namespace is removed the evidence is gone (etcd, not a durable audit store).
- **No cross-run trend** — no "was CIP-003-8 R4.2 compliant last quarter?"
- **Cluster-config scope only, and narrower than commonly assumed** — counted from the live scan's own annotations, `ocp4-nerc-cip` emits checks for **CIP-007 (96 CCRs), CIP-003 (92), CIP-004 (85), and CIP-005 (1)**. It emits **nothing for CIP-010**, and nothing for CIP-002/006/008/009/011/012/013/014/015. See §6 — the CIP-010 absence matters most, because that is the standard the baseline/drift layer exists to answer.
- **No attestation record** — 22 of 125 checks return **MANUAL** (need human sign-off); the operator can't hold the attestation.
- **No signed/immutable evidence** — nothing an auditor can verify offline.

---

## 3. What AAC generates on top — the `compliance_results` record

AAC's collation reads every CCR, maps it to CIP control(s) via the on-CCR `NERC-CIP` annotation, aggregates at CIP-control level, and stores a durable, timestamped record:

| Column / field | What AAC adds |
|---|---|
| `framework` = `nerc_cip_ocp` | Distinct source lane (kept separate from host-based `nerc_cip`) |
| `total_controls` / `passed_controls` / `failed_controls` | **CIP-control-level aggregation** (51 / 15 / 36) — a control fails if any mapped check fails |
| `compliance_percentage`, `compliant` | **Scored posture** (29.41%, false) — not in the raw CO output |
| `evaluation_timestamp` | **Historical row** — every run is a durable, queryable point in time |
| `hostname` / `ip_address` | Subject (cluster `crc`) |
| `policy_name` / `policy_version` | `OpenShift Compliance Operator — ocp4-nerc-cip` / scan name |
| `violations` (JSONB) | Per-failure record: `control`, `cip_controls[]`, `check`, **`ccr_uid`** (evidence back-reference to the CO/ACS object), `severity`, `message` |
| `metadata` (JSONB) | `source`, `integration` (ACS→AAC), `scan`, `namespace`, `ccr_total`, `status_spread {FAIL/PASS/MANUAL}`, `checks_without_cip_mapping`, `controls_failed[]` |

**Net delta AAC adds today:** CIP-control roll-up · a compliance score · durable timestamped history in PostgreSQL · a per-violation evidence chain back to the source object · status-spread + unmapped accounting · framework separation · queryable trend across runs.

---

## 4. Side-by-side attribute matrix

| Audit need | Compliance Operator alone | AAC (system-of-record) |
|---|---|---|
| Per-check pass/fail | ✅ `status`/`severity` | ✅ preserved in `violations[]` |
| Remediation instructions | ✅ `instructions` (per check) | ⤴ referenced by `check`/`ccr_uid` |
| CIP control mapping | ✅ per-check annotation | ✅ **aggregated to CIP-control level** |
| Compliance score / % | ❌ | ✅ `compliance_percentage`, `compliant` |
| Roll-up by CIP control | ❌ | ✅ `total/passed/failed_controls`, `controls_failed[]` |
| Historical / trend | ❌ (current-state, etcd) | ✅ durable timestamped rows |
| Evidence chain to source | ⚠ uid lives in cluster only | ✅ `ccr_uid` stored beside the finding |
| MANUAL-check accounting | ⚠ status only | ✅ `status_spread.MANUAL` (+ attestation, §5) |
| Multi-framework in one record | ⚠ annotations only | ✅ collatable (§5) |
| Auditor-verifiable / signed | ❌ | ⤴ CAA signing (§5) |
| Survives operator/cluster teardown | ❌ | ✅ external PostgreSQL |

---

## 5. What AAC can further augment this with

Beyond what it stores today, AAC is positioned to add:

1. **Cryptographic audit signing (CAA).** Sign each stored record (cosign) so an auditor can verify it offline against a published public key — an immutable, tamper-evident evidence trail. (Infrastructure exists; needs the signing key wired.)
2. **Cross-framework roll-up in one record.** Each CO check also carries NIST-800-53, PCI-DSS, STIG, CIS, BSI mappings — AAC can store *all* mappings per finding, so one scan answers multiple audits (NERC-CIP + NIST + PCI) from the same evidence.
3. **Coverage for the CIP controls the operator is silent on.** Fold AAC host/OT facts + attestation for **CIP-006/008/010/011/012/013/014/015** (physical security, incident response, config-change mgmt, supply chain, INSM) — the cluster profile can't check these; AAC completes the picture so no control is left "unassessed."
4. **Attestation records for MANUAL checks.** Capture reviewer, date, and justification for the 22 MANUAL checks — turning "needs human review" into signed evidence.
5. **ACS-native findings** (when RHACS is installed): runtime, image-vulnerability, and network-segmentation findings mapped onto CIP-005/007/010/013/015 — the sensor half of the ACS↔AAC story.
6. **Remediation lifecycle tracking.** Use the `automated-remediation` availability → applied → re-verified, with before/after CIP posture as the audit artifact.
7. **Provenance enrichment.** Store operator version, profile GUID, content-image digest, and scan timestamp on each record for full chain-of-custody.
8. **Presentation & trend.** Grafana panels keyed on `nerc_cip_ocp`, quarter-over-quarter trend queries, and generated PDF audit reports for the assessor.

---

## 6. NERC-CIP coverage reconciliation

**Measured, not canonical.** The table below is counted from a live `ocp4-nerc-cip` scan
(125 `ComplianceCheckResult`s, Compliance Operator v1.9.1, verified 2026-07-31) by reading each
CCR's own `control.compliance.openshift.io/NERC-CIP` annotation. Earlier revisions of this
document listed the profile's coverage from Red Hat's published content description; those
numbers did not match what the profile actually emits.

**97 of 125 CCRs carry a NERC-CIP annotation. 28 carry none** — the profile is a superset that
also serves CIS/NIST/PCI/STIG mappings. A single CCR frequently maps to several CIP families,
so the per-family CCR counts below sum to more than 97.

| CIP standard | `ocp4-nerc-cip` (cluster) | distinct CCRs | FAIL | distinct control IDs | AAC augmentation |
|---|---|---|---|---|---|
| **CIP-007** Systems Security Mgmt | ✅ native cluster checks | 96 | 10 | 28 | ✅ collated + scored + historical |
| **CIP-003** Security Mgmt Controls | ✅ native cluster checks | 92 | 8 | 10 | ✅ collated + scored + historical |
| **CIP-004** Personnel & Training | ✅ native cluster checks | 85 | 7 | 9 | ✅ collated + scored + historical |
| **CIP-005** Electronic Security Perimeters | ✅ native, but thin | 1 | 0 | 3 | ✅ + firewall/IAM facts for real ESP coverage |
| **CIP-010** Configuration Management | ❌ **no annotated checks** | 0 | — | 0 | ✅ **AAC supplies this entirely** — baseline + drift |
| CIP-002 (BES categorization) | ❌ not emitted by this profile | 0 | — | 0 | CMDB/GRC facts + attestation |
| CIP-006 (physical) | ❌ not cluster-checkable | 0 | — | 0 | host/OT facts + attestation |
| CIP-008 (incident response) | ❌ | 0 | — | 0 | AAC incident-response evidence (CIP-008 pipeline) |
| CIP-009 (recovery) | ❌ not emitted by this profile | 0 | — | 0 | backup-system facts + attestation |
| CIP-011/012/013/014 | ❌ | 0 | — | 0 | AAC facts + attestation + supply-chain (image signing) |
| CIP-015 (INSM) | ❌ | 0 | — | 0 | ACS runtime network anomaly + AAC INSM records |

Annotation formats observed: `CIP-003-8 R4.2`, `CIP-004-6 R2.2.2`, `CIP-005-6 R1.1`,
`CIP-007-3 R2.1`. AAC maps from these annotations directly and does not re-derive Red Hat's
mapping.

> **Two things to say carefully.**
>
> **1. The operator's cluster coverage is real but narrow — three families do the work.**
> CIP-007, CIP-003, and CIP-004 account for essentially all of it. CIP-005 has a single
> annotated check, so the profile should not be presented as covering Electronic Security
> Perimeters in any meaningful sense.
>
> **2. The profile emits nothing for CIP-010.** This is the important one, and it is not a
> gap to apologize for — **CIP-010 is exactly what AAC contributes.** The operator answers
> *"is this setting correct right now?"*; CIP-010 asks *"what is the authorized baseline, what
> changed against it, and who approved the change?"* No point-in-time checker can answer that,
> which is why AAC's baseline + drift layer is the thing that makes cluster evidence
> CIP-010-admissible.
>
> The `ocp4-nerc-cip` profile must never be presented as full NERC-CIP coverage. AAC's role is
> precisely to extend cluster checks with host/OT facts, attestation, ACS findings, and the
> CIP-010 baseline-of-record into a complete, auditable CIP posture.

---

*AAC does not replace the Compliance Operator or ACS — it is the durable, mapped, signable audit system-of-record that turns their point-in-time output into NERC-CIP audit evidence.*

---

# Part II — Full NERC-CIP Check Index & Fact-Gathering (CIP-002 → CIP-015)

> **For a large investor-owned utility.** They currently collect NERC-CIP evidence with home-grown
> scripts. This part indexes **every detail AAC checks** across all 14 CIP standards, the
> **source system** each fact comes from, and the **AAC/AAP fact-gathering method** — so it can be
> compared, control-by-control, to the home-grown collection in place today.

## 7. How AAC checks NERC-CIP — the model

```
Source systems (CMDB, GRC, HR/LMS, IAM, SIEM, patch/vuln, PACS, INSM, backup, CLM, OCP cluster)
        │   AAP fact collection  (versioned Ansible playbooks — one method per source)
        ▼
Single JSON fact object  ──POST──▶  OPA / Rego  (nerc_cip_main, opa-ot :8183)
        │   ~332 discrete checks across CIP-002…CIP-015
        ▼
PostgreSQL  compliance_results   (historical, scored, signable system-of-record)
```

Two things a home-grown script pipeline typically does **not** provide, and AAC does:
- **Policy-as-Code** — the pass/fail logic is Rego: versioned in git, unit-tested, auditor-readable, and identical across every asset. A script embeds the logic inline, per-team, unversioned.
- **A single evidence store** — every result lands in one queryable, historical DB with an evidence back-reference, instead of scattered script output.

## 8. NERC-CIP check index — what is evaluated, per standard

Each standard is a Rego module (`policies/frameworks/critical_infrastructure/nerc_cip/cip_0XX_*.rego`)
evaluating the listed **fact fields** (the "details checked"), sourced and gathered as shown.

| CIP standard | Fields checked | What is evaluated (representative) | Primary source system(s) | AAP gather method |
|---|---:|---|---|---|
| **CIP-002** BES Cyber System Categorization | 23 | Asset inventory, high/medium impact criteria (Attachment 1), external routable connectivity, ESP, categorization docs + CIP-senior-manager approval | CMDB, GRC | `community.general.uri` → CMDB/GRC REST; or `postgresql_query` |
| **CIP-003** Security Management Controls | 46 | Cybersecurity policies documented + approved, CIP senior manager designated, low-impact asset controls, delegations | GRC | GRC REST / survey attestation |
| **CIP-004** Personnel & Training | 13 | Personnel risk assessments, training completion + content coverage, security-awareness reinforcement, access role changes | HR, LMS, IAM/AD | `uri` → Workday/Cornerstone; `community.windows.win_domain_group_membership` / LDAP |
| **CIP-005** Electronic Security Perimeters | 15 | ESP defined, Electronic Access Points, interactive + vendor remote access controls, malicious-comm detection | Firewall, CMDB, IAM | firewall API / config query |
| **CIP-006** Physical Security (BES) | 25 | Physical access controls, visitor control program (documented/escort/logging), PACS + EACS, monitoring & review | PACS, CMDB | `uri` → Genetec/Lenel/Software House |
| **CIP-007** Systems Security Management | 32 | Ports & services, patch management, malicious-code prevention (AV/EDR), security-event logging/monitoring, password policy | Patch mgmt, Vuln scanner, SIEM, IAM | `ansible.builtin.package_facts`; `uri` → Tenable/Qualys/CrowdStrike/Splunk |
| **CIP-008** Incident Response | 31 | IR plan, testing, roles, E-ISAC reporting, detection, lessons-learned | GRC, SIEM, Change mgmt | `uri`; `servicenow.itsm.*`; SIEM rule query |
| **CIP-009** Recovery Plans | 20 | Recovery plans, backup verification, restoration testing, data preservation | Backup, GRC | `uri` → Veeam/NetBackup |
| **CIP-010** Configuration Management | 18 | Baseline config, change management + rollback/test, config monitoring, software integrity, vuln assessments, transient assets | CMDB, Change mgmt, Vuln scanner | **`cip_010_baseline_capture.yml` (LIVE — Template 116)**; `servicenow.itsm` |
| **CIP-011** Information Protection | 32 | BES cyber-system info protection, access controls, media sanitization/reuse | GRC, IAM, SIEM | `uri`; LDAP/AD |
| **CIP-012** Communications Protection | 18 | Control-center comm confidentiality + integrity, encryption in transit | Firewall, SIEM | firewall/network device query |
| **CIP-013** Supply Chain Risk Management | 34 | Supply-chain risk plan, vendor security assessment, software integrity/authenticity, vendor remote access | Contract/CLM, GRC, Change mgmt | `uri` → Ironclad/Icertis/SAP Ariba |
| **CIP-014** Physical Security (Transmission) | 20 | Risk assessment, physical security plan, independent third-party review | EMS/SCADA, PACS, GRC | EMS query / manual attestation initially |
| **CIP-015** Internal Network Security Monitoring | 5 | INSM deployed, east-west anomaly detection, data collection + retention | INSM platform | `uri` → Claroty/Dragos/Nozomi/Darktrace |

**Total: ~332 discrete NERC-CIP checks** — every one versioned in git and unit-tested, not embedded in a script.

## 9. Fact-gathering: AAC/AAP vs home-grown scripts

AAC gathers each fact with a **named, supported Ansible module** against the system of record — the
same job the utility's scripts do today, but structured, idempotent, and centrally orchestrated by AAP.

| Source system | CIP standards it feeds | AAC/AAP collection module |
|---|---|---|
| GRC (ServiceNow GRC, Archer, Diligent) | All 14 | `community.general.uri` (REST) |
| CMDB (ServiceNow, Device42) | 002, 005, 006, 007, 010, 013, 014, 015 | `uri` / `postgresql_query` |
| HR (Workday, PeopleSoft, SAP HCM) | 004 | `uri` |
| LMS (Cornerstone, Workday Learning, KnowBe4) | 004 | `uri` |
| IAM / Active Directory | 004, 005, 007, 011 | `community.microsoft.ad` / LDAP |
| Firewall / network (Cisco, Palo Alto) | 005, 007, 012 | device API / config query |
| PACS (Genetec, Lenel, Software House) | 006 | `uri` |
| Patch mgmt (Satellite 6, WSUS, RHSM) | 007, 010 | `ansible.builtin.package_facts` + API |
| Vulnerability scanner (Tenable, Qualys) | 007, 010 | `uri` |
| SIEM (Splunk, QRadar, Elastic) | 007, 008, 011, 012 | `uri` |
| INSM (Claroty, Dragos, Nozomi, Darktrace) | 015 | `uri` |
| Backup (Veeam, NetBackup, AWS Backup) | 009 | `uri` |
| Change mgmt (ServiceNow ITSM) | 008, 010, 013 | `servicenow.itsm` |
| EMS / SCADA (OSIsoft PI, GE EMS) | 014 | ICCP/OPC-UA / manual attestation |
| Contract/CLM (Ironclad, Icertis, Ariba) | 013 | `uri` |
| **OpenShift cluster** | 005, 007, 010, 013, 015 (cluster config) | **`kubernetes.core.k8s_info` → Compliance Operator `ocp4-nerc-cip`** (Part I) |

**Existing AAC fact-collection playbooks:** `aac_gather_facts.yml`, `collect_all_facts.yml`,
`aac_gather_network_facts.yml`, `cip_010_baseline_capture.yml` (live), `nerc_cip_compliance_report.yml`.

### Where AAC differs from home-grown scripts

| Dimension | Home-grown scripts | AAC / AAP |
|---|---|---|
| Collection | Per-team, per-system, ad-hoc | One orchestrated AAP job set; named modules per source |
| Pass/fail logic | Embedded in the script, per-author | **Rego policy-as-code** — versioned, unit-tested, one definition |
| Coverage | Whatever a script happens to check | **~332 explicit checks** across all 14 CIP standards, indexed above |
| Evidence | Scattered script output / spreadsheets | Single **PostgreSQL system-of-record**, historical, scored |
| Auditor trust | "trust the script" | Signable records + per-finding evidence chain (Part I) |
| Cluster (OCP) | Custom `oc` scripting | **Red Hat-certified Compliance Operator** content, collated |
| Change over time | Hard to diff | Git history on both policy and fact model |

The OpenShift cluster layer (Part I) and this host/OT/organizational layer share **one fact object,
one Rego engine, and one system-of-record** — so a single NERC-CIP posture spans the cluster and the
rest of the estate.
