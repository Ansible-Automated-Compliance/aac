# Ansible Policy as Code (PAC) and Ansible Automated Compliance (AAC)

## Support validation — AAC is PAC in its bones

**Version:** v2.4
**Date:** 2026-08-28
**Purpose:** to establish that **AAC rests on supported Red Hat product surface**, by showing that
its architecture is the architecture Red Hat productized as Policy as Code — and that AAC is a
**functional superset** of it, adding history, a standards policy library, and governance.
**Audience:** architects, platform owners, and anyone asked *"who supports this?"*
**Grounding:** PAC details are from Red Hat's public product documentation, the
`ansible/example-opa-policy-for-aap` repository (input/output contracts and example Rego), and the
**live AAP controller settings API** on the reference environment. AAC details are from this
repository and a live reference deployment. Nothing here is illustrative.
**Authors:** Tim Coulter; Claude (Anthropic).

> **For business-unit and engineering review.** This document is circulated to be argued
> with, not agreed to. §1 makes a support argument that the author believes holds; §6.1 and
> §6.2 record the places it does *not* reach. If a reviewer finds those sections too
> generous, that is the more useful finding — say so.
>
> **Companion:** `docs/AAC_HONEST_STATUS_AND_POSITIONING.md` answers the field-facing
> question *"is what we handed the customer supportable?"*. This document answers *"is the
> technology supportable?"*. Read together; either alone misleads.

---

## 1. The support argument

The question this document exists to answer is: *"AAC is a compliance platform someone built —
what's the support story?"*

**The answer: AAC is PAC in its bones.** Every architectural decision AAC made — OPA as the policy
decision engine, Rego as the policy language, AAP as the invoker, the OPA v1 data API as the
interface — is the same decision Red Hat made when it built Policy as Code into Ansible Automation
Platform. AAC did not invent an unusual combination. It chose the combination Red Hat has since
shipped and supports.

**Before AAP 2.5.5**, "AAP calls OPA to evaluate Rego" was a pattern AAC had selected on its own
judgement, and a reasonable reviewer could ask whether that pairing was idiosyncratic.
**Since AAP 2.5.5**, that pairing is Red Hat's own productized design, documented in the AAP
product documentation and configured through first-class controller settings. The architectural
question is settled by Red Hat's own product decision.

What that means concretely:

| Layer AAC depends on | Support status |
|---|---|
| RHEL | Supported Red Hat product |
| AAP — controller, execution environments, job templates, workflows, credentials | Supported Red Hat product |
| **OPA as a policy decision engine invoked from AAP** | **Supported Red Hat product capability** (Policy as Code, GA in AAP 2.5.5) |
| **Rego as the policy language** | **The language Red Hat selected** for AAP policy |
| **OPA v1 data API** | **The API version AAP supports** — AAC uses the same one |
| PostgreSQL | Supported Red Hat product (and a standard AAP dependency) |
| AAC's Rego policy library and playbooks | **Customer content** |

That last row is the whole of the custom surface, and it is the *normal* posture for any Ansible
deployment: Red Hat supports the platform that executes content; the content itself belongs to the
customer. A customer's own playbooks, roles, and Rego are supported the same way — Red Hat stands
behind the engine, the customer owns the logic. AAC is **supported platform plus customer content**,
not an unsupported architecture.

> **Say it this way:** *"AAC isn't a bespoke stack bolted onto Ansible. It is Policy as Code — same
> engine, same language, same API, the architecture Red Hat productized — with more functional
> attributes on top: history, written policies for the common security and compliance standards, and
> governance of the estate. The platform underneath is fully supported. What we add is policy
> content, which is customer content in any Ansible deployment."*

> **A note on the policy counts in this document.** They are stated as ranges
> ("over 550", "two dozen families") rather than exact figures, on purpose. The
> library is a git submodule that advances independently, so any exact number is
> stale the next time it moves, and stale counts have already propagated through
> several documents here. Count it at the commit the repository actually pins,
> which is the only number that means anything:
>
> ```bash
> PINNED=$(git ls-tree HEAD policies | awk '{print $3}')
> cd policies
> git ls-tree -r "$PINNED" --name-only | grep '\.rego$' \
>   | grep -vcE '(^|/)(test_|.*_test\.rego$)'      # policy files
> git ls-tree -r "$PINNED" --name-only | grep -c '\.rego$'   # including tests
> ```
>
> At pin `75bb5f1` (2026-08-28) that is **558 policy files, 644 including tests,
> 86 test files**. Quote the policy-file number; say "including tests" if you use
> the larger one.

### 1.1 One distinction to state honestly

**AAC uses the same substrate as PAC; it does not call the PAC enforcement feature.** PAC's
enforcement gate intercepts job launches. AAC evaluates collected facts about managed systems.
Same components, different flow — see §4.

State this plainly rather than blurring it. The support argument does not depend on AAC using the
enforcement feature; it depends on AAC using the same supported components, which it demonstrably
does. Anyone who checks will find that distinction, and the argument is stronger for having named it
first.

---

## 2. AAC is a functional superset of PAC

The relationship is not "two tools for two jobs." **AAC does what PAC does, and then adds three
things PAC has no answer for.**

> **AAC = PAC + history + a policy library + governance.**

Start from PAC's own capability — policy enforcement on automation, in Rego, on OPA, invoked from
AAP. AAC has that, at **three** enforcement points rather than one (git check-in, runtime pre-flight,
post-hoc audit sweep) and across **more artifact types** than AAP jobs alone (Ansible playbooks,
Terraform plans, Dockerfiles, Kubernetes admission, CI/CD, supply chain, AI-driven decisions). See
§5.3 and §5.4.

Then add the three attributes that are AAC's reason for existing:

| Added attribute | What it means | PAC equivalent |
|---|---|---|
| **1. History** | Every evaluation is a durable, timestamped, scored row in PostgreSQL. Trends, quarter-over-quarter posture, and an evidence chain back to the source object. Signed with cosign so an auditor can verify offline | **None.** A PAC decision gates the launch and is gone — nothing is written down |
| **2. Written policies for the common security and compliance standards** | **over 550 curated Rego policy files across two dozen framework families** — CIS, STIG, NIST, FISMA, ISO 27001, SOC 2, PCI-DSS, SOX, HIPAA, GDPR, NERC-CIP, IEC 62443, DORA, NIS2, sovereignty | **None.** Red Hat ships example policies and a blank page. Policy content is customer-supplied |
| **3. Governance** | Assessment of the managed estate against those standards; config baselining and unauthorized-change detection; attestation for manual controls; AI/MCP decision governance; auditor-facing reporting | **None.** PAC's subject is the job, never the estate |

### 2.1 The job-metadata gap is now closed

Earlier revisions of this document recorded an exception: PAC gated on job metadata —
`extra_vars`, credentials, inventory-to-organization, job-template naming, launch time — that AAC
had no policy for. **That gap is closed.**

`enforcement/aap/` in the Rego library ships **eleven decisions** written against AAP's own Policy
as Code contract (`{"allowed": bool, "violations": [string]}`), covering **all twelve** of Red Hat's
published example policies:

| AAC decision | Replaces Red Hat example |
|---|---|
| `maintenance_window` | `maintenance_window` |
| `owner_scope` | `restrict_inv_use_to_org` |
| `superuser_restriction` | `superuser_allowed_false` |
| `credential_scope` | `global_credential_allowed_false`, `mismatch_prefix_allowed_false` |
| `extra_vars_control` | `extra_vars_allowlist`, `extra_vars_validation` |
| `team_extra_vars` | `team_based_extra_vars_restriction` |
| `naming_standard` | `jt_naming_validation` |
| `source_control` | `github_repo_validation`, `project_scm_branch` |
| `deny_all` | `allowed_false` |
| `maintenance_mode` | *no equivalent* |
| `required_labels` | *no equivalent* |

47 tests. Because they honour PAC's contract, they can be loaded into **either** enforcement path:
associated with an organization/inventory/job template through PAC itself, or evaluated by AAC.

### 2.2 What genuinely remains

One thing, and it is structural rather than a capability gap:

**PAC's enforcement is unbypassable; AAC's runtime pre-flight is not.** PAC is enforced by the
controller and applies to every job launched from an associated template. AAC's pre-flight lives in
the playbook and can be removed by editing the content — which is why the git check-in gate and the
audit sweep exist as backstops (§5.4).

That is an argument for running both — PAC as the perimeter, AAC for depth, history, and the
standards library — not for treating them as equivalent. And note what it is *not*: it is no longer
a claim that AAC lacks the policies. It has them.

### 2.3 Side by side

| | **PAC** | **AAC** |
|---|---|---|
| Policy engine | OPA | OPA |
| Policy language | Rego | Rego |
| OPA API version | v1 | v1 |
| Invoked from | AAP | AAP |
| Enforce policy on automation | ✅ 1 point (job launch) | ✅ 3 points (check-in, runtime, audit) |
| Artifact types covered | AAP jobs | AAP jobs, Ansible content, Terraform, Dockerfile, K8s, CI/CD, AI |
| Gate on job metadata | ✅ native | ✅ `enforcement/aap/`, 11 decisions (§2.1) |
| Unbypassable enforcement | ✅ platform-enforced | ⚠️ content-enforced (git gate + audit sweep as backstops) |
| **History** | ❌ nothing persisted | ✅ PostgreSQL, scored, signed |
| **Standards policy library** | ❌ examples only | ✅ 550+ files, ~two dozen framework families |
| **Governance of the estate** | ❌ | ✅ assessment, baseline/drift, attestation, reporting |

**Rows 1–4 are the bones (§1). Rows 5–8 are the same job done more broadly. The last three are why
AAC exists.**

---

## 3. Components

### 3.1 PAC components

| Component | Role |
|---|---|
| **AAP controller** | Enforcement caller. Evaluates policy before launching a job. |
| **External OPA server** | Policy decision point. Must be reachable from the AAP deployment. Red Hat does not ship it as part of the enforcement feature — you provide it. |
| **Rego policies** | Written by the customer. The public examples use package `aap_policy_examples`. |
| **Association points** | A policy is attached to an **organization**, an **inventory**, or a **job template**. |

**Controller settings** — these are the actual setting names, read from a live AAP controller
(`/api/controller/v2/settings/all/`), with this deployment's defaults:

| Setting | Default here | Purpose |
|---|---|---|
| `OPA_HOST` | `''` | OPA server hostname |
| `OPA_PORT` | `8181` | OPA server port |
| `OPA_SSL` | `False` | Use TLS to reach OPA |
| `OPA_AUTH_TYPE` | `'None'` | Authentication mode |
| `OPA_AUTH_TOKEN` | `''` | Bearer token |
| `OPA_AUTH_CA_CERT` | `''` | CA bundle for OPA's certificate |
| `OPA_AUTH_CLIENT_CERT` | `''` | Client certificate (mTLS) |
| `OPA_AUTH_CLIENT_KEY` | `''` | Client key (mTLS) |
| `OPA_AUTH_CUSTOM_HEADERS` | `{}` | Extra request headers |
| `OPA_REQUEST_TIMEOUT` | `1.5` | **Seconds** to wait for a decision |
| `OPA_REQUEST_RETRIES` | `2` | Retry attempts |

Only **OPA API v1** is supported.

### 3.2 AAC components

| Component | Role |
|---|---|
| **AAP** | Fact collection and orchestration. Every assessment is a job template or workflow. |
| **OPA ×3, domain-split** | `opa-security` (CIS, NIST, STIG) · `opa-compliance` (ISO, SOC 2, PCI, SOX, FISMA, sovereignty) · `opa-ot` (NERC-CIP, AMI, IEC 62443) |
| **Rego policy library** | 550+ policy files (see the count note in §1) across two dozen framework families, versioned as a git submodule |
| **PostgreSQL** | `compliance_results` (scored history, JSONB violations) and `compliance_certifications` (signed records) |
| **Grafana** | Posture dashboards, trends, drift panels |
| **CAA signing** | cosign ECDSA-P256 signatures so auditors can verify records offline |

AAC's engine choice is recorded in [ADR-002](../architecture/ADR_002_POLICY_ENGINE_OPA.md), which
also addresses the "is OPA viable and supported?" question directly.

### 3.3 What AAC adds to the PAC baseline — the complete delta

This is the heart of the support conversation. Start from a PAC deployment and list everything AAC
adds. **The list is short, and nothing on it introduces a new class of technology.**

| What AAC adds | Relative to PAC | Why it's low-risk to support |
|---|---|---|
| **A database** — PostgreSQL for `compliance_results` + `compliance_certifications` | PAC persists nothing | **PostgreSQL is already an AAP dependency.** AAC adds a *database* (or an instance), not a new technology. Same engine, same backup and support story the platform team already runs |
| **Two extra OPA containers** — three total, split by domain: `opa-security` / `opa-compliance` / `opa-ot` | PAC requires **one** customer-provided OPA server | **Same component, more instances.** The split is for blast radius and performance, not function — AAC would work on a single OPA. Each container is the same image PAC would use |
| **The policy content** — 550+ Rego policy files across two dozen framework families, versioned as a git submodule | PAC requires customer-written Rego and ships only examples | **Same category of artifact PAC already requires you to supply.** AAC supplies a curated library instead of a blank page. Red Hat ships no compliance policy library either way |
| **Grafana** — posture dashboards, trends, drift panels | PAC has no reporting surface | **Optional and replaceable.** It reads the compliance database over SQL like any BI tool. Swap in Superset, Power BI, Tableau, or an existing corporate dashboard with no change to assessment, storage, or policy |
| **Fact-collection playbooks** | PAC needs none — its input is the job context AAP already has | Ordinary Ansible content, executed by a supported EE |

Read that table as a support statement:

- **Nothing is a new technology class.** PostgreSQL is already there. OPA is already there — PAC
  requires one, AAC runs three of the same thing. Rego is already there. The playbooks are Ansible.
- **Two items are strictly additive instances**, not new dependencies: the database and the extra
  OPA containers.
- **One item is customer content** that PAC also requires — AAC just brings a library rather than a
  blank page.
- **One item is entirely optional.** If Grafana is unwelcome in an environment, remove it: the
  compliance record still lands in PostgreSQL, the API is SQL, and any graphing product can consume
  it. **Grafana is presentation, never a dependency of correctness.**

> **Say it this way:** *"Take a supported Policy as Code deployment. Add a PostgreSQL database — which
> AAP already depends on — so decisions become durable history instead of evaporating. Add two more
> instances of the OPA container PAC already needs, split by domain. Add a curated Rego library
> instead of writing policy from scratch. Optionally point a dashboard at the database. That's AAC.
> There is no fifth thing, and nothing on that list is exotic."*

---

## 4. Data flow

### 4.1 PAC — synchronous gate, nothing persisted

```
User launches job
        │
        ▼
AAP controller  ──► builds job-context JSON
        │
        ▼
   OPA server        POST /v1/data/<policy path>     [timeout 1.5s, 2 retries]
        │
        ▼
{ "allowed": false, "violations": ["No job execution is allowed"] }
        │
        ├── allowed:true  ──► job runs
        └── allowed:false ──► job blocked, violations shown to the user
```

**Input** — AAP sends the job execution context. Documented fields include `id`, `name`, `created`,
`created_by` (with `username`, `is_superuser`), `credentials[]` (with `kind`, `cloud`, `kubernetes`,
`organization`), `execution_environment` (`image`, `pull`), `extra_vars`, `forks`, `hosts_count`,
`instance_group`, `inventory`, `job_template`, `job_type`, `labels[]`, `launch_type`, and `limit`.

**Output contract** — exactly two fields matter:

```json
{ "allowed": false, "violations": ["reason 1", "reason 2"] }
```

**Nothing is written down.** The decision gates the launch and is gone. There is no policy-decision
history, no score, no trend, no evidence artifact.

### 4.2 AAC — asynchronous assessment, everything persisted

```
Managed systems (RHEL / Windows / cloud / OT / OpenShift)
        │  Ansible fact collection (AAP job)
        ▼
   Facts JSON  (~180 KB per system)
        │  POST /v1/data/<framework>/compliance_report
        ▼
   OPA (opa-security | opa-compliance | opa-ot)
        │  structured report: per-control results, score, violations
        ▼
PostgreSQL  compliance_results  ──► Grafana dashboards
        │                        ──► PDF / DOCX auditor reports
        ▼
compliance_certifications (cosign-signed, offline-verifiable)
```

### 4.3 Why the timeout proves the split

`OPA_REQUEST_TIMEOUT = 1.5` seconds with `OPA_REQUEST_RETRIES = 2` is the most informative number in
the PAC configuration. PAC sits **inline on the job-launch path**, so it must return a decision in
under two seconds against a small job-context document. A slow policy is a broken launch.

AAC posts roughly **180 KB of collected facts per system** and evaluates hundreds of controls; a
framework assessment takes seconds to minutes and runs *after* collection, off the critical path.

Neither design can absorb the other's workload. PAC could not evaluate a 338-control CIS benchmark
inside 1.5 s; AAC's assessment has no meaning at job-launch time because the facts have not been
collected yet. **This is an architectural boundary, not a feature gap.**

---

## 5. Functionality

### 5.1 What PAC does

Red Hat's stated use cases:

1. Control **where** policies apply (scope)
2. Manage **which users** can automate specific inventory
3. Regulate **when** automation executes (e.g. maintenance windows)
4. Control **which variables** pass into automation (`extra_vars`)
5. Prevent **credential / inventory mismatches**
6. Enforce **naming conventions**

The public example policies map directly onto these: `allowed_false`, `extra_vars_allowlist`,
`extra_vars_validation`, `github_repo_validation`, `global_credential_allowed_false`,
`jt_naming_validation`, `maintenance_window`, `mismatch_prefix_allowed_false`, `project_scm_branch`,
`restrict_inv_use_to_org`, `superuser_allowed_false`, `team_based_extra_vars_restriction`.

Every one of them is a statement about **the automation**, not about the managed estate.

### 5.2 What AAC does

| Capability | Detail |
|---|---|
| Multi-framework assessment | 50+ frameworks — CIS, STIG, NIST, FISMA, ISO 27001, SOC 2, PCI-DSS, SOX, HIPAA, GDPR, NERC-CIP, IEC 62443, AMI/NIST IR 7628, DORA, NIS2, sovereignty, and more |
| Control-level scoring | Per-control pass/fail rolled to a framework score |
| Historical tracking | Every run is a durable timestamped row; trends across months |
| Evidence chain | Each violation retains a back-reference to its source object |
| Signed records | cosign ECDSA-P256, verifiable offline against a published public key |
| Baseline & drift | Config baselining with change-authorization tagging (e.g. NERC-CIP CIP-010) |
| Reporting | Grafana dashboards plus auditor-facing PDF/DOCX |
| Remediation | Assessment-first; remediation is explicit and recorded |

### 5.3 Capability matrix

**AAC enforces automation policy too — this is not a PAC-only lane.** AAC's `enforcement/` policy
set and the *comply* demo block Ansible playbooks at git check-in and again at runtime, deny
Terraform plans, and gate CI/CD, Dockerfiles, Kubernetes admission, and AI-driven automation. The
difference is *mechanism*, not *whether* — see §5.4.

| Capability | PAC | AAC |
|---|---|---|
| **Block a non-compliant automation job** | ✅ platform-enforced, pre-launch | ✅ content-enforced, pre-task (§5.4) |
| Enforce maintenance windows | ✅ | ✅ `maintenance_window`, `maintenance_mode` |
| Restrict `extra_vars` / credentials / inventory-to-org | ✅ native | ✅ `extra_vars_control`, `team_extra_vars`, `credential_scope`, `owner_scope` |
| Enforce job-template naming | ✅ | ✅ `naming_standard` (and play/task naming via `SENTINEL-ANS-001`) |
| **Inspect the contents of a playbook** (hardcoded secrets, bare `all`, missing tags) | ❌ **structurally cannot** — sees job metadata only | ✅ `SENTINEL-ANS-001…004` |
| **Block a bad commit at git check-in** | ❌ | ✅ EDA webhook → OPA |
| **Deny a Terraform plan** | ❌ | ✅ `SENTINEL-TF-001…003` |
| Gate CI/CD, Dockerfiles, supply chain (SLSA) | ❌ | ✅ `enforcement/cicd`, `dockerfile`, `supply_chain` |
| Kubernetes admission control | ❌ | ✅ `kubernetes_admission.rego` (Gatekeeper-compatible) |
| Govern AI-driven automation decisions | ❌ | ✅ `governance/mcp`, AI controls demo |
| Assess a managed host against CIS/STIG/NIST | ❌ | ✅ |
| Score an estate against a regulatory framework | ❌ | ✅ |
| Retain compliance history / trend | ❌ | ✅ |
| Produce auditor evidence | ❌ | ✅ |
| Cryptographically sign a compliance record | ❌ | ✅ |
| Config baseline + unauthorized-change detection | ❌ | ✅ |
| Written in Rego, evaluated by OPA | ✅ | ✅ |

Read the enforcement rows carefully. **AAC covers more of the enforcement lane than PAC does** —
more enforcement points, more artifact types, and since `enforcement/aap/` the job-metadata checks
as well. The residual complement runs one way only, and it is structural: **PAC's gate cannot be
removed by editing content.**

### 5.4 Two enforcement mechanisms — the distinction that matters

Both block automation. They do it at different points, with different guarantees.

| | **PAC** | **AAC (Sentinel / comply)** |
|---|---|---|
| Where the check lives | **The platform.** The controller calls OPA before launching | **The content.** The playbook's first `pre_task` calls OPA; plus a git-check-in gate and CI |
| What it inspects | **Job metadata** — template, credentials, `extra_vars`, inventory, user, EE, time | **The artifact itself** — playbook YAML, Terraform plan, Dockerfile, K8s manifest |
| Does the job start? | **No.** Blocked pre-launch | Yes, then fails at task 1 — before any deployment task runs |
| Bypassable? | **No.** Associated at org / inventory / template; applies to every job from that template | **Yes.** Remove the `pre_task` include and the runtime gate is gone (which is why the git gate and the audit sweep exist as backstops) |
| Enforcement points | 1 — job launch | 3 — git check-in, runtime pre-flight, post-hoc audit sweep |
| Coverage beyond AAP | None | Terraform, Dockerfiles, Kubernetes admission, CI/CD, supply chain, AI decisions |

**The structural point:** PAC's input schema is job metadata. It never receives the playbook's
contents, so **no PAC policy can detect a hardcoded secret inside a play** — the data simply is not
there. Conversely, AAC's pre-flight only fires in playbooks that include it, so **AAC cannot stop a
job that never opted in.**

That is a genuine argument for running both: PAC provides the unbypassable perimeter around *which
jobs may run*; AAC provides depth on *what the automation actually contains*, plus the earlier git
gate and the audit sweep that catches anything which slipped past.

---

## 6. Support and lifecycle

This is the asymmetry worth stating plainly.

| | **PAC** | **AAC** |
|---|---|---|
| Status | Supported Red Hat product feature | Custom platform built on AAP |
| Availability | GA from **AAP 2.5.5**; documented in AAP 2.5 and 2.6 | Versioned in this repository |
| Support path | Red Hat support, standard AAP lifecycle | Maintained by the platform team |
| Policy content | Customer-written; Red Hat publishes examples only | 550+ curated Rego policy files across two dozen framework families, versioned as a submodule |
| OPA server | **Customer-provided**, not shipped as part of the feature | Deployed and managed by AAC (three containers) |
| Upgrade risk | Follows AAP releases | Tracks OPA and Rego v1 directly |

Note the symmetry hidden in that table: **both require you to bring your own OPA and your own
policy content.** Red Hat supports the *enforcement mechanism*; it does not supply a compliance
policy library. That gap is precisely where AAC's 550+-policy library sits.

For the durability of OPA itself as a dependency — including the August 2025 Apple acqui-hire of the
Styra/OPA core team — see [ADR-002 §6](../architecture/ADR_002_POLICY_ENGINE_OPA.md).

---

### 6.1 The other half — and the reason this document is not sufficient on its own

Everything above concerns the **runtime architecture**, and the argument holds. It is not
the whole picture, and a reader who stops here will be blindsided by the thing that
actually goes wrong at a customer.

AAC has two halves and they are not equally mature:

| | Policy layer | Delivery layer |
|---|---|---|
| Content | 550+ Rego policies, 85+ test files | 221 playbooks, 2 collections |
| Automated tests | **540+**, gated in CI | **9** |
| CI that tests it | Yes — id verification, coverage partition, syntax | **None** |
| Release management | Versioned as a submodule | 2 non-semver tags |
| State | Product-grade | **Demo harness** |

**The customer installs the second half.** The support argument in §1 is sound and it says
nothing about installer quality. Recent field experience bore this out: hardcoded lab
addresses and demo hostnames in playbooks a customer runs, a recurring platform failure
documented in a runbook rather than fixed, and at least one playbook that did not parse at
all — none of which CI would catch, because no CI tests playbooks.

State this before a customer discovers it. It does not weaken §1; it prevents §1 being
quoted as a claim it never made.

### 6.2 What "fully supported" would require

§1 establishes that the architecture qualifies. It does not establish that the artifact
does. The gap, honestly:

| Requirement | Today | Gap |
|---|---|---|
| Bounded scope — exact artifacts, exact versions | Undefined | Define what is in and out |
| Semantic versioning, signed immutable releases | **Zero tags** on the policy library | Release process |
| Lifecycle policy — supported versions, for how long | None | Policy decision |
| **Named owning team with a defect SLA** | 3 contributors, effectively one | **The hardest item — organisational, not technical** |
| CI on everything a customer runs | Policy layer yes; delivery layer no | Test coverage |
| Support matrix — AAP / OCP / RHEL versions claimed and tested | Informal | Define and test |
| Diagnostics bundle for triage | §7.2 exists informally | Package it |
| Security response — CVE handling, errata | None | Process |
| Licensing consistency | Policy library and orchestrator repo both Apache-2.0 (reconciled 2026-10-16) | Done |

The realistic path is not "support AAC". It is **certified or validated content** for the
policy library, with the delivery layer explicitly out of scope and customer- or
consulting-owned.

### 6.3 The precedent already exists — this is the Ansible collections model

The support question for policy content is not a new problem, and Red Hat does not need a
new answer for it. **It is the Ansible collections model**, applied to Rego instead of
Python and YAML.

Red Hat ships Ansible; it does not ship every collection. Content sits at a declared tier,
and every Ansible customer already understands what each tier means:

| Tier | Where it lives | Who supports it | Rego equivalent |
|---|---|---|---|
| **Community collection** | Ansible Galaxy | Community — no entitlement | The policy library today: public, Apache-2.0 |
| **Validated content** | Automation Hub | Red Hat tested against a matrix | A curated subset, verified against benchmark enumerations |
| **Certified collection** | Automation Hub | **Red Hat supported**, with SLAs | A certified policy library |

The parallel is exact, including the part that matters:

> **Red Hat ships the engine and supports it. Content is a separate artifact with its own
> support tier. A customer running a community collection has no entitlement to it and is
> not surprised by that** — because the tier was declared up front.

Policy as Code is the engine. Rego is the content. **Red Hat ships the engine and publishes
example policies — exactly as it ships Ansible and publishes example playbooks.** The
library fills the same gap that certified collections fill for automation content.

**Why this matters for the support conversation:** it converts an open question into a
choice between three well-understood options, none of which requires inventing a support
model:

1. **Community tier** — where the library sits today. No entitlement, clearly stated. Costs
   nothing to declare and is honest immediately.
2. **Validated** — Red Hat tests it against a support matrix without owning defects.
3. **Certified** — Red Hat supported, with the obligations that implies.

The right question for the business unit is therefore not *"can AAC be supported?"* but
**"which tier does this content belong in, and what is the bar for the next one up?"** That
is a question the collections process already knows how to answer.

**One caveat worth naming:** the analogy is strong on the support model and weaker on the
maintenance burden. Compliance content carries a currency treadmill that a typical
collection does not — CIS reissues benchmarks, NERC adds standards, and CIS Microsoft 365
moved from v3 to v7 inside a year. Whoever owns a tier above community owns that treadmill.
The tiering model is right; the ongoing cost should be sized honestly against it.

---

## 7. How to support AAC — a guide for the support team

This section exists so an engineer who has never seen AAC can triage it. The governing idea from §1
applies directly: **AAC is supported platform plus customer content**, so the first job of triage is
deciding which of those two a symptom belongs to.

### 7.1 Triage — platform issue or content issue?

Work down this ladder. The first layer that fails is the layer that owns the problem.

| # | Question | How to check | If it fails |
|---|---|---|---|
| 1 | Is AAP healthy? | `/api/controller/v2/ping/` returns 200 | **Platform** — standard AAP support |
| 2 | Did the job reach an execution environment? | Job stdout shows tasks running | **Platform** — EE, instance group, capacity |
| 3 | Is the OPA server reachable? | `curl <opa>/health` → 200 | **Platform/infra** — networking, container, TLS |
| 4 | Are the policies loaded? | `curl <opa>/v1/policies` → non-empty | **Content/ops** — reload job; see 7.3 |
| 5 | Does the framework path resolve? | `curl <opa>/v1/data/<framework>` → not `{}` | **Content** — Rego package or load gap |
| 6 | Did PostgreSQL accept the row? | Job stdout shows the insert; row present | **Platform/content** — schema, credential, constraint |
| 7 | Is the answer *wrong* rather than absent? | Result returns but values look incorrect | **Content** — Rego logic, customer-owned |

Layers 1–3 are ordinary Red Hat product support. Layers 4–7 are AAC content, owned by the platform
team — exactly as a customer's own playbooks would be.

### 7.2 The single most useful diagnostic

Almost every AAC symptom is one of three things: **OPA didn't answer**, **OPA answered `{}`**, or
**PostgreSQL rejected the row.** Establishing which one takes about a minute:

```bash
# 1. Is OPA up?
curl -s -o /dev/null -w '%{http_code}\n' http://<opa-host>:<port>/health

# 2. How many policies are loaded? (an unexpectedly low number is the tell)
curl -s http://<opa-host>:<port>/v1/policies | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["result"]))'

# 3. Does this framework resolve, or return empty?
curl -s http://<opa-host>:<port>/v1/data/<framework> | head -c 200
```

Service map: **`opa-security`** (CIS, NIST, STIG) · **`opa-compliance`** (ISO, SOC 2, PCI, SOX,
FISMA, sovereignty) · **`opa-ot`** (NERC-CIP, AMI, IEC 62443). A framework queried against the
wrong instance returns `{}` and looks exactly like a missing policy — check which instance you
hit before escalating.

They are told apart by **service name, not port**. On OpenShift each is its own Service listening
on 8181; the `:8181`/`:8182`/`:8183` scheme was the pre-CRC layout where all three shared one
host. Playbooks resolve the right one from the framework name and never hardcode either form.

### 7.3 Known failure modes

These are observed on real deployments. Most "AAC is broken" reports are one of these.

| Symptom | Cause | Resolution | Owner |
|---|---|---|---|
| A framework returns `{}` after a policy reload; others fine | **Bulk policy load overwhelms OPA.** Each `PUT` triggers a full recompile; under load OPA returns transient 5xx and that policy is silently dropped | Re-run the reload; use retry-on-5xx. Verify with the policy count in 7.2 | Content/ops |
| Job fails at `aac_store_certification: Assert a CAA signing private key is configured` | No `caa_signing_private_key` for that template. The assessment itself succeeded — only signing failed | Supply the CAA key (vault or template `extra_vars`). Note the assessment data *did* store | Content/ops |
| Assessment returns data but the job is marked **failed** | A later step (commonly CAA signing) failed after a successful assessment | Read the `PLAY RECAP`: `failed=1` with a high `ok=` count means late-stage failure, not a bad assessment | Content/ops |
| `null value in column "framework" violates not-null constraint` | `framework` is `NOT NULL` in `compliance_results` and was omitted from the insert | Pass `framework` in the storage call | Content |
| Kubernetes/OpenShift reads return 403 | The AAP credential's ServiceAccount lacks RBAC | `oc auth can-i <verb> <resource> --as=system:serviceaccount:<ns>:<sa>`; grant or use the right credential | Platform/content |
| A change pushed to git never appears in jobs | The AAP **project is tracking a different branch**, or was not re-synced | Check `projects/<id>/ scm_branch`; sync; restart EDA activations (a sync alone does not refresh running rulebook content) | Platform/ops |
| Grafana panel is empty | Datasource, or panel SQL referencing a column/`policy_name` that no longer matches | Run the panel's `rawSql` directly against the compliance DB | Content |
| Rego rule returns `undefined`, whole report becomes `{}` | A rule with no `default` never fires; `undefined` inside an object literal makes the whole object undefined | Add `default <rule> := false` | Content |
| `array.concat` error | `array.concat()` takes **exactly two** arrays | Nest the calls pairwise; convert sets to arrays first | Content |
| PDF/report file missing on the host after a job | `connection: local` runs inside the EE; `/tmp` there is ephemeral | Generate in the EE, then copy to the host | Content |

### 7.4 What to collect for a support case

Ask for these up front; they resolve most cases without a second round trip.

1. **AAP job ID and full stdout** — including the `PLAY RECAP` line
2. **Which OPA port** the framework should be on, and `GET /health` + `/v1/policies` count from it
3. **The framework key** and the result of `GET /v1/data/<framework>`
4. **AAP version, EE image tag, OPA version**
5. **Whether a policy reload ran recently** (the most common precipitating event)
6. For storage failures: the target row and whether `framework` was supplied

### 7.5 Escalation boundary

| Escalate to Red Hat when | Handle in-house when |
|---|---|
| AAP itself is unhealthy — API, controller, EE, instance groups, capacity | A Rego policy returns the wrong answer |
| Job execution, credential, or inventory subsystem misbehaves | A framework is missing from OPA |
| PostgreSQL as an AAP dependency fails | A dashboard panel query is wrong |
| The **PAC enforcement feature** misbehaves (see §1.1 — AAC does not use it, but a customer may) | A compliance score is disputed |
| RHEL, container runtime, or platform networking faults | An assessment playbook needs changing |

**The line to hold:** Red Hat supports the platform that runs the content. AAC's Rego and playbooks
are content. That is not a weaker position than any other Ansible deployment — it is the same
position, and §1 is the argument for why.

---

## 8. Running both — verified coexistence

Because PAC and AAC both talk to OPA, a reasonable question is whether they can share a server.

**They can.** OPA namespaces by package, and different data paths coexist by design. Verified on the
reference environment: the `opa-security` container currently serves **310 loaded policies across 46
distinct top-level packages**, and both paths resolve independently:

```
GET /v1/data/aap_policy_examples  -> 200
GET /v1/data/cis_rhel9            -> 200
```

So `OPA_PORT = 8181` pointing at the same OPA that AAC uses is **not** a namespace conflict.

**The real risk is latency, not collision.** A bulk policy reload makes OPA recompile, and under
load it can return transient 5xx. AAC reload jobs push hundreds of policies at once. With PAC
configured against that same server, a reload window could exceed `OPA_REQUEST_TIMEOUT` (1.5 s) and
exhaust `OPA_REQUEST_RETRIES` (2) — **failing job launches for reasons unrelated to policy.**

**Recommendation:** give PAC its own OPA instance, or at minimum an instance AAC does not bulk-reload
into. The isolation is about availability, not correctness.

---

## 9. Choosing between them

| If you need to… | Use | Why |
|---|---|---|
| **Stop automation that violates policy from running** | **PAC / AAC** | Both do this. PAC blocks pre-launch and cannot be bypassed; AAC blocks at git check-in and again as a pre-task. Best together (§5.4) |
| **Stop a playbook containing a hardcoded secret** | **AAC** | PAC never receives the playbook's contents — only job metadata |
| **Stop a bad change before it is even merged** | **AAC** | Git check-in gate via EDA → OPA. PAC has no pre-merge enforcement point |
| **Deny a Terraform plan** | **AAC** | `SENTINEL-TF-001…003`. Outside PAC's scope entirely |
| **Gate Kubernetes admission, CI/CD, Dockerfiles, supply chain** | **AAC** | `enforcement/` policy set |
| **Govern AI-driven automation decisions** | **AAC** | `governance/mcp` + AI controls |
| Stop a job during a change freeze | **PAC / AAC** | Both. `maintenance_window` (time, day, dated freezes) and `maintenance_mode` (named freeze, per-inventory) |
| Prevent a user passing an unapproved `extra_var` | **PAC / AAC** | Both. `extra_vars_control` adds secret-shaped-key detection and value patterns; `team_extra_vars` scopes by team |
| Keep an inventory usable only by its owning organization | **PAC / AAC** | Both. `owner_scope` also binds users and teams to inventory patterns |
| Enforce job-template naming | **PAC / AAC** | Both. `naming_standard` covers pattern, length, and forbidden terms |
| Prove to an auditor that 500 hosts met CIS RHEL 9 last quarter | **AAC** | |
| Score the estate against NERC-CIP, ISO 27001, or PCI-DSS | **AAC** | |
| Detect an unauthorized configuration change against a baseline | **AAC** | |
| Produce signed, offline-verifiable compliance evidence | **AAC** | |

**Where the line actually falls.** It is no longer a capability line. AAC now has policies for the
job-metadata checks too (§2.1), so those rows read PAC **/** AAC — pick by enforcement property, not
by what is possible. Everything about the *substance* of the automation — its contents, its
Terraform plans, its container images, its cluster manifests — is AAC's, because PAC structurally
cannot see it. And the compliance posture of the managed estate is AAC's alone.

**The one durable reason to run PAC as well:** its gate is enforced by the platform and cannot be
removed by editing a playbook.

Most enterprises with a compliance mandate need **both**: PAC as the unbypassable perimeter on which
jobs may run, AAC for depth on what the automation contains, earlier enforcement at check-in, and
proof that the estate the automation manages is compliant.

---

## 10. Current state on the reference environment

`OPA_HOST` is empty on this AAP controller, so **PAC is not currently configured** — the platform's
own policy gate is unused while AAC runs three OPA servers beside it. That is an observation, not a
defect: nothing in AAC depends on PAC. Enabling it would be a small, separable piece of work
(populate `OPA_HOST`/`OPA_PORT`, load a Rego policy, associate it with a job template), and per §6 it
should point at an OPA instance outside AAC's bulk-reload path.

---

## 11. Summary

**What AAC is, in one line:**

> **AAC is PAC with more functional attributes — history, written policies for the common security
> and compliance standards, and governance.**

It does what PAC does (policy enforcement on automation, in Rego, on OPA, from AAP) at three
enforcement points instead of one and across more artifact types, then adds the three attributes PAC
has no answer for. The job-metadata gap that earlier revisions recorded is **closed** — `enforcement/aap/` ships eleven
decisions covering all twelve of Red Hat's published examples (§2.1). What remains is structural,
not a capability: **PAC's gate is enforced by the platform and cannot be removed by editing
content** (§2.2, §5.4).

**What this document does not claim** (§6.1, §6.2): that the delivery layer is ready, or
that a support entitlement exists today. The policy layer is product-grade — 550+ policies,
540+ tests, gated in CI. The 221-playbook delivery layer has **9 tests and no CI**, and that
is the half a customer installs. Stated here first because a reviewer will find it anyway.

**The support argument (the point of this document):**

- AAC's architecture — **OPA as the engine, Rego as the language, AAP as the invoker, OPA API v1 as
  the interface** — is the architecture Red Hat productized as Policy as Code in AAP 2.5.5. AAC is
  PAC in its bones.
- Every layer AAC runs on is **supported Red Hat product surface**. The only custom surface is Rego
  policy content and playbooks, which is **customer content** — the normal posture for any Ansible
  deployment.
- AAC uses the same *substrate* as PAC; it does not call the PAC *enforcement feature* (§1.1). Say
  this plainly; the argument does not need it and is stronger for naming it.
- Red Hat supports the enforcement mechanism and ships **no compliance policy library**. That gap is
  where AAC's 550+ policy files sit.

**The delta from PAC to AAC is four things (§3.3), none of them exotic:**

1. **A database** — PostgreSQL, already an AAP dependency, so decisions become durable history
   instead of evaporating.
2. **Two extra OPA containers** — three total, split by domain. Same component PAC already requires,
   just more instances; AAC would run on one.
3. **The policy content** — a curated 550+-policy Rego library instead of the blank page PAC hands you.
   Same category of artifact PAC already requires.
4. **Grafana** — *optional and replaceable.* It reads the compliance DB over SQL; any graphing
   product substitutes without touching assessment, storage, or policy. Presentation, never a
   dependency of correctness.

There is no fifth thing.

**Supporting it (§7):**

- Triage down the ladder — AAP → EE → OPA reachable → policies loaded → framework resolves →
  PostgreSQL accepted → answer correct. The first layer that fails owns the problem.
- Layers 1–3 are Red Hat product support; layers 4–7 are AAC content.
- Nearly every symptom is **OPA didn't answer**, **OPA answered `{}`**, or **PostgreSQL rejected the
  row** — three curl commands separate them.
- A framework queried on the wrong OPA port returns `{}` and is indistinguishable from a missing
  policy. Check the port first.

**How they differ:**

- PAC is a **synchronous gate on automation**, bounded by a 1.5-second timeout, persisting nothing.
- AAC is an **asynchronous assessment and system-of-record for the estate**, persisting scored,
  signed, historical evidence.
- They **coexist safely** on one OPA server by namespace, but should be separated so an AAC policy
  reload cannot stall a PAC job launch.
- The one-liner: **PAC keeps your automation in policy. AAC does that too — and keeps the history,
  the standards library, and the governance that prove your infrastructure is.**

---

## Sources

- Red Hat — [Automated Policy as Code with Ansible Automation Platform](https://www.redhat.com/en/technologies/management/ansible/automated-policy-as-code)
- Red Hat Docs — [Implementing policy enforcement, AAP 2.6](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html/configuring_automation_execution/controller-pac)
- Red Hat Blog — [Using AAP to Enable a Policy as Code Solution](https://www.redhat.com/en/blog/using-red-hat-ansible-automation-platform-to-enable-a-policy-as-code-solution)
- GitHub — [`ansible/example-opa-policy-for-aap`](https://github.com/ansible/example-opa-policy-for-aap) (`POLICY_INPUT_DATA.md`, `POLICY_OUTPUT_DATA.md`, `aap_policy_examples/`)
- Live AAP controller `/api/controller/v2/settings/all/` (setting names and defaults)
- This repository — [ADR-002](../architecture/ADR_002_POLICY_ENGINE_OPA.md), `CLAUDE.md`, live reference deployment

---

## Revision history

| Version | Date | Change |
|---|---|---|
| **v2.4** | 2026-08-28 | **Removed every hardcoded policy/test count** and replaced them with ranges plus a reproducible count note (§1). The figures had already drifted — the document said 556 policies and 492 tests where the pinned commit has 558 and 545 — and stale counts have propagated through several documents here. Also **stopped identifying the three OPA instances by port**: `:8181`/`:8182`/`:8183` was the pre-CRC single-host layout. On OpenShift each is its own Service on 8181, told apart by name (`opa-security` / `opa-compliance` / `opa-ot`). Both issues raised in review. |
| v2.3 | 2026-08-28 | Counts stated as ranges with a reproducible count note rather than hardcoded figures. Added **§6.1** the delivery layer, which the runtime support argument does not cover and which is what fails at a customer; **§6.2** what "fully supported" would require, as a gap table for the support conversation;  and **§6.3** framing policy content on the **Ansible collections model** — community, validated, certified — so the support question becomes "which tier", not "can it be supported". Framed for BU critique rather than agreement. |
| v2.2 | 2026-07-31 | Prior revision — support argument, functional superset, support-team triage guide. |
