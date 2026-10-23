# AAP-Native NERC-CIP Cluster Assessment — Replicating the `ocp4-nerc-cip` Compliance Operator Profile with the Certified Kubernetes Collection

**Version:** v1.0
**Date:** 2026-07-16
**Authors:** Tim Coulter (Red Hat) with Claude (Anthropic)
**Status:** Feasibility assessment — grounded in live cluster queries + OpenSCAP/collection documentation

---

## 0. Question

Can we obtain the **same NERC-CIP information the OpenShift Compliance Operator produces**
(`ocp4-nerc-cip` profile) using **AAP + the certified Kubernetes/OpenShift Ansible
collection** — feeding the facts into AAC's OPA → PostgreSQL pipeline — instead of
depending on the Compliance Operator (and/or ACS) to run the scans?

**Short answer:** **Yes for the Platform (Kubernetes-API) checks — proven live.** The
Node/OS-level checks are also achievable without the operator, via three documented
techniques (§5). The real cost is not feasibility; it is that you take ownership of the
*check content* the operator otherwise maintains (§6).

> **Relationship to the collate design (PR #311):** The merged integration doc
> (`RHACS_AAC_NERC_CIP_INTEGRATION.md`) describes AAC **collating**
> `ComplianceCheckResult` objects *from* the Compliance Operator. This document explores
> the opposite vector — **replacing** the operator with AAP-native fact collection. They
> are alternative architectures; §7 recommends the **hybrid** and neither doc invalidates
> the other.

---

## 1. Which collection — "can we use the OCP certified collection?"

Two certified collections exist on Automation Hub; they play different roles:

| Collection | Certified | Provides | Role here |
|---|---|---|---|
| **`kubernetes.core`** | ✅ (Automation Hub) | `k8s`, **`k8s_info`**, **`k8s_exec`**, `helm`, `k8s_json_patch`, inventory plugin | **Primary** — `k8s_info` gathers compliance facts; `k8s_exec` reaches pods/nodes |
| **`redhat.openshift`** | ✅ (Automation Hub) | `k8s`, `openshift_auth`, `openshift_route`, `openshift_process`, `openshift_build`, `openshift_import_image`, `openshift_registry_info`, `openshift_adm_*` | **Optional** — OCP-specific *management*; does **not** include `k8s_info`/`k8s_exec` |

**Key point:** `redhat.openshift` is the certified *OpenShift-specific* collection, but the
read/query modules this use case needs — **`k8s_info`** (GET any API object) and
**`k8s_exec`** (run in a pod/debug pod) — live in **`kubernetes.core`**, which is also
certified. So: **use `kubernetes.core` as the primary; add `redhat.openshift` only if you
also want the certified OCP management modules.** Both are pullable from Automation Hub,
so the EE can source certified builds rather than Galaxy.

> Reminder from the EE audit: `aac-compliance-ee`'s `requirements.yml` does **not** yet
> declare `kubernetes.core`, even though the running image contains it. Any AAP-native
> approach here must add `kubernetes.core` (certified) to that requirements file so a
> rebuild reproduces it.

---

## 2. What the Compliance Operator gets (`ocp4-nerc-cip` inventory)

The profile is **147 rules / 20 groups**, split into Platform (Kubernetes-API) and Node
(OS-level) checks, annotated to CIP-002/003/004/005/007/009. Categorized:

| # | Category | Items checked | CIP mapping | Type |
|---|---|---|---|---|
| 1 | **API server & encryption** | etcd encryption cipher (aescbc); etcd CA/cert/key; client-cert CA; kubelet HTTPS; no insecure port/bind | 003-8 R4.2, 007-3 R5.1 | Platform |
| 2 | **RBAC & authorization** | Node+RBAC modes enabled; no AlwaysAllow; API priority & fairness (FlowSchema); anonymous-auth disabled | 003-8 R6, 004-6 R3, 007-3 R6.1 | Platform |
| 3 | **Admission / SCC** | no AlwaysAdmit/AlwaysPullImages; enable NamespaceLifecycle/NodeRestriction/SCC/ServiceAccount; no SecurityContextDeny | 003-8 R6, 007-3 R6.1 | Platform |
| 4 | **Service accounts & tokens** | restrict SA token automounting; unique SAs (avoid default) | 003-8 R6, 004-6 R3 | Platform |
| 5 | **Logging & audit** | audit log path; max size; backup retention | 003-8 R6 | Platform |
| 6 | **Authentication** | no basic-auth-file; cert-based kubelet auth | 003-8 R6, 004-6 R3 | Platform |
| 7 | **System & software integrity** | **FIPS on all nodes**; Cluster Version Operator verification; **File Integrity Operator (AIDE)** | 003-8 R4.2, 007-3 R4.2/R5.1 | **Node** |

Categories 1–6 are Kubernetes-API reads. Category 7 is on-node OS state.

---

## 3. Platform checks (1–6): fully AAP-replicable — proven live

Every Platform check is a read of an OpenShift API object, which is exactly what
`kubernetes.core.k8s_info` returns. Verified live against a running cluster:

| Compliance Operator rule | Live API read | Result observed |
|---|---|---|
| `api_server_encryption_provider_cipher` | `apiserver/cluster .spec.encryption.type` | empty → **FAIL reproduced** (same finding the operator reports) |
| SCC admission plugins present | `oc get scc` | 11 SCCs enumerated |
| RBAC bindings enumerable | `oc get clusterrolebinding` | 84 CRBs |
| SA token automount | `serviceaccount .automountServiceAccountToken` | null (default-true → finding) |
| Identity providers (CIP-005) | `oauth/cluster .spec.identityProviders` | retrievable |

**Conclusion:** an AAP playbook using `kubernetes.core.k8s_info` can gather the identical
fact set the operator's Platform rules evaluate — including reproducing the etcd-encryption
FAIL — then POST those facts to OPA for the CIP verdict and store to `compliance_results`.
This is AAC's native fact → OPA → PostgreSQL pattern with the OCP API as the source.

---

## 4. Two honest caveats on "replicable"

1. **RBAC / service-account scope.** The live reads above were run as `system:admin`. An
   AAP EE runs as a service account (e.g. `aac-demo-runner`). Reading apiserver config,
   *all* SCCs, *all* clusterrolebindings, and oauth requires binding that SA to the
   built-in **`cluster-reader`** ClusterRole. This is a prerequisite, not a footnote.
2. **New Rego content required.** AAC's existing 18 NERC-CIP Rego modules are host/OT-fact
   shaped — none consume OpenShift API objects. Mapping cluster facts to CIP controls is
   **new Rego** regardless of approach; there is no existing cluster-shaped NERC-CIP Rego
   to reuse.

---

## 5. Node checks (slice 7) — **yes, achievable without the Compliance Operator**

The operator's node scan is OpenSCAP (oscap) + AIDE running on RHCOS via privileged pods.
None of that is exclusive to the operator; it can be reproduced three ways, in increasing
reuse of Red Hat content:

### Option A — Ansible-native OS checks via `oc debug node` / privileged exec
Use `kubernetes.core.k8s_exec` into an `oc debug node/<name>` pod (or a privileged
DaemonSet mounting hostPath `/`), then run targeted commands with `chroot /host`:
- **FIPS:** `cat /proc/sys/crypto/fips_enabled`
- **Kernel params:** `sysctl <key>`
- **File permissions:** `stat -c '%a' <path>`
- **File integrity:** `sha256sum <path>` compared to a golden baseline
No operator, no OpenSCAP. **You author and maintain each node check** (lightest infra,
highest content ownership).

### Option B — Run the OpenSCAP content yourself (recommended for the node slice)
Launch a Job/pod from an **openscap-scanner** image with the same ComplianceAsCode
datastream the operator uses (`ssg-rhcos4-ds.xml` / `ssg-ocp4-ds.xml`) and invoke
`oscap xccdf eval --profile nerc-cip …` against the node's mounted filesystem. This
**reproduces the operator's node scan without the operator** — AAP orchestrates oscap
directly. You keep Red Hat's certified *check content* while dropping the operator
machinery; parse the ARF/XCCDF results into `compliance_results`.

### Option C — Golden-image baseline + checksum (already in production here)
For file-integrity controls specifically, the **golden-image demo pattern is exactly this
check without any operator**: a pristine baseline stored in PostgreSQL, compared to the
live node/pod file, drift → remediate → ticket. AIDE-class file integrity, AAP-native,
already working.

> **FIPS nuance:** on full OpenShift, FIPS intent is partially discoverable via the API
> (MachineConfig kernel arguments), but the authoritative check is on-node
> `/proc/sys/crypto/fips_enabled` — i.e. it needs Option A/B. (Note: MicroShift has no
> MachineConfig API, so FIPS there is node-only.)

**Trade-off for slice 7 without the operator:** you take on privileged node access,
orchestration, and — for Option A — authoring the node check logic. Option B keeps the
certified content and only replaces the operator's scheduling/CRD layer.

---

## 6. The decisive distinction — certified plumbing ≠ certified content

`kubernetes.core` / `redhat.openshift` are certified **collectors**: they read the cluster
supportably. The `ocp4-nerc-cip` profile is certified **content**: 147 Red Hat-maintained
checks with the compliance logic and CIP mappings already written and version-tracked.

**AAP + the certified collection gets you the facts, not the verdicts.** Replicating the
profile means re-authoring and maintaining the rule logic (in Rego for Platform, in
Ansible/oscap for Node) as OpenShift fields change across releases. For a NERC-CIP audit
customer, "who certifies and keeps the check logic current" is a real procurement
question — do not let "certified collection" imply "certified compliance."

---

## 7. Recommendation — the hybrid

| Slice | Best source | Why |
|---|---|---|
| **Platform (cat. 1–6)** | **AAP + `kubernetes.core`** | Simple API reads; AAC owns them; no operator dependency; historical DB + reports built in. Proven live. |
| **Node (cat. 7)** | **Compliance Operator** *(collate)* — or **Option B** oscap Job if operator-free is required | Node oscap/AIDE is the operator's strength; re-implementing is high-maintenance. Collate its results (per PR #311) unless a no-operator mandate applies. |

This hybrid maximizes AAC's differentiators (system of record, historical tracking,
reports, unified CIP mapping) while not re-inventing the node-OS scanning Red Hat already
certifies. If the customer mandates **no Compliance Operator at all**, Node moves to
**Option B** (self-run oscap) so certified check content is retained.

---

## 8. Proposed POC (one slice, end-to-end)

Prove the Platform path for real without over-building:

1. `kubernetes.core.k8s_info` gathers the category-1 & 2 facts (etcd encryption type, SCCs,
   RBAC mode, SA automount) — the exact objects pulled live in §3.
2. Normalize to AAC fact shape; POST to OPA; a small new Rego module maps them to
   **CIP-007 / CIP-003** control outcomes.
3. Write **one `compliance_results` row** carrying the etcd-encryption finding, with the
   API object reference as the auditor back-reference.

Deliverable: the AAP-native pipeline producing the same finding the operator reports —
validating the architecture on the cluster that is already running.

---

*Grounded in live `oc`/API queries (Platform facts reproduced, incl. the etcd-encryption
FAIL) and OpenSCAP/collection documentation. Node-level techniques (§5) are documented
approaches; on this MicroShift test cluster `oc debug node` was constrained, but the
techniques apply unchanged on full OpenShift. Rule counts/coverage are version-dependent.*
