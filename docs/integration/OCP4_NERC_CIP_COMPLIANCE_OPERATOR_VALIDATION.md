# Validation: OpenShift `ocp4-nerc-cip` Compliance Operator Profile → AAC

**Version:** v1.0
**Date:** 2026-07-16
**Authors:** Tim Coulter (Red Hat) with Claude (Anthropic)
**Status:** Design/coverage validation from documentation — see scope note

---

## 0. Scope of this validation (read first)

This report validates the **canonical** `ocp4-nerc-cip` profile as documented by
ComplianceAsCode / OpenSCAP and the OpenShift Compliance Operator, **not** a specific
running instance. At the time of writing there is no network route from the working
environment to the cluster running these policies (the full OpenShift cluster was
unreachable; the locally-connected MicroShift cluster has neither the Compliance
Operator nor ACS installed).

Two distinct meanings of "validate," handled separately:

- **(A) Operational validation** — *do the profiles parse, is the scan binding Active,
  are scans completing `DONE` (not `ERROR`), are results being produced?* This can only
  be answered against the live cluster. §6 is an `oc` checklist you run there; it also
  captures the **version**, which matters (see §5).
- **(B) Coverage/design validation** — *does the profile actually evidence NERC-CIP, and
  which controls can it and can it not cover?* This is done here from documentation and
  is the substance of the report (§3–§4).

---

## 1. What these policies actually are (reconciliation)

Your two framings — "NERC-CIP policies for **ACS**" and "running in the **Compliance
Operator**" — describe the **same content seen from two layers**:

- **Engine:** The **OpenShift Compliance Operator** runs the scans. It uses
  **OpenSCAP / XCCDF** security content from the ComplianceAsCode community — **not Rego,
  and not ACS SecurityPolicies.** The NERC-CIP content ships as the built-in profiles
  **`ocp4-nerc-cip`** (Platform / Kubernetes-API checks) and **`ocp4-nerc-cip-node`**
  (Node / OS-level checks).
- **Management surface:** **Red Hat Advanced Cluster Security (RHACS/ACS)** integrates
  with the Compliance Operator — it can create and manage scan schedules and surfaces the
  resulting `ComplianceCheckResult` data in its Compliance Dashboard. So "ACS NERC-CIP
  policies" are the Compliance Operator's `ocp4-nerc-cip` profile, driven/surfaced by ACS.

> **Correction carried forward:** the earlier integration doc (PR #311) and the PAC
> competitive summary describe ACS findings flowing into AAC's "NERC-CIP Rego." The
> accurate mechanism is: **AAC collates `ComplianceCheckResult` objects (XCCDF check
> outcomes) from the `ocp4-nerc-cip` profile and maps them to CIP controls.** Those two
> artifacts should be reconciled to this framing — see §7. This report uses the accurate
> framing throughout.

---

## 2. The Compliance Operator object model (validation targets)

Grounded in the Compliance Operator CRD reference. A valid NERC-CIP deployment is a
chain of these objects:

| CRD | Role in a NERC-CIP scan | What "valid" looks like |
|---|---|---|
| `ProfileBundle` | Packages the XCCDF datastream (`ssg-ocp4-ds.xml`) as a content image | `status.dataStreamStatus: VALID` |
| `Profile` | Parsed `ocp4-nerc-cip` / `ocp4-nerc-cip-node` (auto-generated, never hand-edited) | Exists, lists rules |
| `Rule` | One XCCDF check; carries CIP control annotations, `severity`, `checkType` (Platform/Node) | Annotated to CIP controls |
| `TailoredProfile` | *(optional)* customization — enable/disable rules, `setValues`, with rationale | `status.state: READY`, emits a tailoring ConfigMap |
| `ScanSetting` | Schedule, storage, roles (operator ships `default` / `default-auto-apply`) | Referenced by the binding |
| `ScanSettingBinding` | Binds profile(s) + `ScanSetting` → generates the suite | Bound, owns a `ComplianceSuite` |
| `ComplianceSuite` | Orchestrates the scans | `status.phase: DONE`, `status.result: COMPLIANT / NON-COMPLIANT` |
| `ComplianceScan` | Executes one profile | `phase: DONE`, `result` set, no `ERROR` |
| `ComplianceCheckResult` | **One per rule — the atom AAC collates** | Status ∈ {PASS, FAIL, INFO, MANUAL, INCONSISTENT, ERROR, NOTAPPLICABLE} |
| `ComplianceRemediation` | Optional fix (usually a MachineConfig) for auto-remediable fails | `apply` flag; review before applying |

`ComplianceCheckResult` status semantics (validation-relevant):
- **PASS / FAIL** — automated verdict.
- **MANUAL** — no automated check; requires human attestation (many CIP controls land here).
- **NOTAPPLICABLE** — rule not selected / not applicable to this cluster.
- **INCONSISTENT** — nodes disagree (Node scans); triggers retry — worth flagging in a report.
- **ERROR** — check could not execute; **any `ERROR` is an operational validation failure**, not a compliance failure.

---

## 3. Coverage validation — which CIP controls the profile evidences

**This is the core finding.** Per the canonical `ocp4-nerc-cip` profile guide
(**147 rules across 20 groups**), the profile's rules are annotated to these NERC-CIP
standards:

> **CIP-002-5, CIP-003-8, CIP-004-6, CIP-005-6, CIP-007-3, CIP-007-6, CIP-009-6**

Mapped against the full CIP-002…CIP-015 family, and judged by *what an OpenShift cluster
configuration can actually evidence*:

| CIP standard | Covered by `ocp4-nerc-cip`? | Rationale |
|---|---|---|
| **CIP-002** Asset categorization | ⚠️ Partial | Cluster/workload inventory contributes; formal BES categorization is organizational |
| **CIP-003** Security management controls | ✅ Yes | FIPS crypto (CIP-003-8 R4.2), service-account/access controls (R6) |
| **CIP-004** Personnel & training | ⚠️ Partial | RBAC / access-management side only; training & PRA are process, not cluster-checkable |
| **CIP-005** Electronic Security Perimeter | ✅ Yes | API access controls, network-facing configuration |
| **CIP-006** Physical security | ❌ No | Not evidenceable from cluster config — expected exclusion |
| **CIP-007** Systems security management | ✅ Yes | etcd encryption-in-transit (R5.1), RBAC (R6.1), SCC admission, ports/services |
| **CIP-008** Incident reporting & response | ❌ No | Process/plan control |
| **CIP-009** Recovery plans | ✅ Yes (partial) | etcd backup / recovery-relevant config (CIP-009-6) |
| **CIP-010** Config change mgmt & vuln | ❌ Not in native profile | Node drift partly via **File Integrity Operator**; vuln assessment is an **ACS** strength, not CO |
| **CIP-011** Information protection | ❌ No | Minimal cluster-config surface |
| **CIP-012** Comms between control centers | ❌ No | Out of cluster scope |
| **CIP-013** Supply chain risk mgmt | ❌ No (CO) | Image provenance/signing is an **ACS** capability, not the CO profile |
| **CIP-014** Physical security (transmission) | ❌ No | Physical control |
| **CIP-015** Internal Network Security Monitoring | ❌ No (CO) | Runtime network baseline/anomaly is an **ACS** capability, not the CO profile |

**Validation verdict (coverage):** the `ocp4-nerc-cip` profile is a **correct but
deliberately partial** artifact. It evidences the ~6 CIP families that map to OpenShift
**cluster configuration** (CIP-002/003/004/005/007/009) and is intentionally silent on
physical, personnel-process, incident-response, information-protection, comms, supply-
chain, and INSM controls. That is proper scoping for a cluster-config scanner, **not a
defect** — but it means the profile **must not be represented to an auditor as full
NERC-CIP coverage.** It is the *OpenShift cluster slice* of NERC-CIP.

---

## 4. Where AAC completes the picture

The coverage gaps in §3 are exactly AAC's role — this is the validated integration thesis:

1. **Collate the cluster slice.** AAC ingests the `ocp4-nerc-cip`
   `ComplianceCheckResult` objects into the historical PostgreSQL `compliance_results`
   table, mapped to their CIP controls, with each row retaining the originating check
   `id` as an auditor back-reference. This gives the CO results the **historical,
   timestamped audit trail** the Compliance Operator does not itself retain.
2. **Cover the non-cluster controls.** AAC's host/OT fact collection + its own CIP-002…
   CIP-015 Rego supply the controls the CO profile cannot see (physical via attestation,
   CIP-010 host baselines, CIP-011/012, etc.).
3. **Fold in ACS-specific signals.** For CIP-010 (vuln), CIP-013 (image provenance/
   signing) and CIP-015 (runtime network baseline) — which the *CO profile* does not
   cover — **ACS's own capabilities** are the evidence source, collated the same way.

Net: **Compliance Operator = cluster-config evidence; ACS = container/runtime/supply-
chain evidence; AAC = the system of record that unifies both with host/OT evidence and
generates the NERC-CIP reports and audit records.**

---

## 5. Version dependence (do not skip)

The "147 rules / 6 CIP families" figures are **canonical as of the referenced OpenSCAP
guide**, and rule sets and control coverage **shift across OCP releases and content-image
versions**. Findings here are therefore **version-dependent**. The §6 checklist captures
the operator version, content-image, and profile rule count on the actual cluster so the
coverage table can be confirmed against the deployed version rather than assumed.

---

## 6. Operational validation checklist (run on the live cluster)

Read-only. Run against the cluster where the profile is deployed; substitute the
Compliance Operator namespace (commonly `openshift-compliance`).

```bash
# 0. Version pin — capture what is actually deployed
oc get csv -n openshift-compliance | grep -i compliance   # operator version
oc get profilebundle -n openshift-compliance \
   -o jsonpath='{range .items[*]}{.metadata.name}{"  img="}{.spec.contentImage}{"\n"}{end}'

# 1. ProfileBundle parsed cleanly (content is valid)
oc get profilebundle -n openshift-compliance \
   -o custom-columns=NAME:.metadata.name,STATUS:.status.dataStreamStatus

# 2. The NERC-CIP profiles exist and are populated
oc get profile.compliance -n openshift-compliance | grep -i nerc
oc get profile.compliance ocp4-nerc-cip -n openshift-compliance \
   -o jsonpath='{"rules="}{.rules[*]}' | tr ' ' '\n' | wc -l   # rule count vs §3

# 3. If a TailoredProfile is used — it must be READY (not ERROR)
oc get tailoredprofile -A \
   -o custom-columns=NAME:.metadata.name,STATE:.status.state,ERR:.status.errorMessage

# 4. Scan wiring: binding → suite → scans
oc get scansettingbinding -A
oc get compliancesuite -A \
   -o custom-columns=NAME:.metadata.name,PHASE:.status.phase,RESULT:.status.result
oc get compliancescan -A \
   -o custom-columns=NAME:.metadata.name,PHASE:.status.phase,RESULT:.status.result,WARN:.status.warnings

# 5. Any scan in ERROR = operational failure to fix before trusting results
oc get compliancescan -A -o json \
  | jq -r '.items[] | select(.status.result=="ERROR") | .metadata.name'

# 6. Result distribution for the NERC-CIP scan (the numbers AAC will collate)
oc get compliancecheckresult -A -l compliance.openshift.io/scan-name=ocp4-nerc-cip \
   -o custom-columns=NAME:.metadata.name,STATUS:.status,SEVERITY:.metadata.labels.compliance\.openshift\.io/check-severity \
   | awk '{print $2}' | sort | uniq -c        # counts of PASS/FAIL/MANUAL/ERROR/...

# 7. FAILs at high severity — the real compliance signal
oc get compliancecheckresult -A \
   -l 'compliance.openshift.io/scan-name=ocp4-nerc-cip,compliance.openshift.io/check-status=FAIL' \
   -o custom-columns=RULE:.metadata.name,SEV:.metadata.labels.compliance\.openshift\.io/check-severity
```

**Interpreting the output:**
- `dataStreamStatus: VALID`, `TailoredProfile READY`, suite `phase: DONE` → the policies
  are **operationally valid**.
- A nonzero **`ERROR`** count (steps 5–6) is an *operational* problem (RBAC, content,
  storage) — fix it before trusting the compliance verdict.
- **`MANUAL`** results are expected for CIP controls with no automated check — they need
  attestation, and AAC should record them as such (not silently as pass/fail).
- Rule count materially different from §3 → you are on a different content version;
  re-confirm §3's coverage table against it.

---

## 7. Action items

1. **Reconcile the two customer-bound artifacts** to the accurate XCCDF /
   `ComplianceCheckResult` framing (not "ACS → AAC Rego"):
   - PR #311 `docs/integration/RHACS_AAC_NERC_CIP_INTEGRATION.md`
   - `~/Downloads/PAC_AAC_NERC_AMI_Business_Competitive_Summary` (v1.1)
   The corrected story is *stronger* (concrete Red Hat-native mechanism), so this is a
   tightening, not a walk-back.
2. **Run §6 on the live cluster** to convert this from design validation to instance
   validation, and to pin the version.
3. **Build the collation path** — `AAC - Collate ComplianceCheckResults` (map CO check
   results → CIP controls → `compliance_results`), per the integration design.

---

*Grounded in OpenShift Compliance Operator and ComplianceAsCode documentation. Rule
counts and control coverage are version-dependent (§5). This report validates the
canonical profile; §6 validates a specific cluster instance.*
