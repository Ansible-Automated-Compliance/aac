# AAC and NERC-CIP — Capabilities, Architecture, and Gaps

**Version:** v1.2  
**Date:** 2026-10-23  
**Audience:** Red Hat teams engaging a utility on NERC-CIP. **Internal enablement.**  
**Classification:** Internal — not for direct customer distribution. See §1.2.  
**Authors:** Tim Coulter (Red Hat) with Claude (Anthropic)

---

## 1. How to use this document

### 1.1 The one-paragraph version

AAC's NERC-CIP asset today is a **complete, executable specification of what CIP-002
through CIP-015 evidence requires** — all 14 standards modelled as versioned OPA/Rego
policy, **233 named input fields**, each mapped to the source system that must supply it.
**Nine of those 233 fields collect live today.** That is not a gap in the policy layer;
it is the integration backlog, and the map is itself the deliverable.

**What AAC is, in one sentence:** AAP changes state to match intent; AAC measures how
well the estate matches a body of standards — rolled up across varied frameworks and
drillable to a single managed node — and hands the required corrections directly back to
AAP as executable work. That
alignment view is what AAP has always lacked, and §2.4 is the version to use in a
technical conversation.

Two things run end to end and are the proof the architecture works. **CIP-010** on
OpenShift, against certified Compliance Operator content, is the deepest CIP standard.
**AMI 2.0** at the grid edge is the one path with live device telemetry flowing through
policy into persisted evidence with no static file anywhere — the existence proof that
the CIP collection layer is an integration exercise, not an unsolved problem.

### 1.2 Why this is internal

The 9-of-233 number is in here. A utility should eventually hear an honest version of it,
but framed as a scoped integration plan for *their* estate — not as a bare ratio in a
document they can forward. Sending an account team out **unaware** of the collection
status is the larger risk, which is why the number is stated plainly here.

Build the customer-facing artifact from §3 and §4, scoped to what that utility actually
runs. That is a different document.

### 1.3 Language that matters to this audience

Two conventions, and they are not stylistic:

- **We provide evidence of compliance.** Compliance is the state an auditor certifies.
  Never write or say that AAC makes a utility "compliant" — to a regulator that is a
  claim we are not entitled to make. "Evidence", "assessment", "audit record" are correct.
- **AAC measures state; AAP acts on it.** These are two different statements and it
  matters that both are made. AAC's measurement lane is **configuration state**, not
  activity streams — it is not a SIEM, not an admission controller, and it does not sit
  inline in the data path making real-time allow/deny decisions. But AAC is part of
  **Ansible Automation Platform**, and AAP is a remediation, patching and configuration
  management engine. The same platform that detects a deviation can correct it, roll it
  back, patch the underlying system, and record the correction as an authorised change.
  **Do not undersell this — it is the single biggest thing Red Hat brings to a CIP
  conversation**, and §3.6 covers it properly.

### 1.4 A companion document to read carefully

`docs/frameworks/NERC_CIP_COVERAGE.md` (v1.0) is the policy catalogue — what each Rego
package evaluates. It is accurate about the **policy layer** and says nothing about
collection status. Its overview sentence — *"AAC implements all 14 active CIP standards
as OPA Rego policies, continuously assessing BES Cyber Systems"* — is the sentence most
likely to be repeated in a customer meeting and then collapse under a follow-up question.
Read it alongside §4 here, never on its own.

---

## 2. Why — what a utility is actually trying to solve

### 2.1 The problem is evidence production, not knowing the rules

Utilities are not confused about what CIP requires. They have compliance teams who know
the standards better than we do. What consumes them is **producing, organising and
defending the evidence** on an audit cycle, across an estate where the assets are
heterogeneous and the source systems were never designed to answer an auditor's question.

The characteristic state we encounter is home-grown collection: per-system scripts,
logic embedded per-author, no baseline of record, no policy engine, and no historical
series. It works until the author leaves, the estate changes, or an auditor asks
"show me this as it stood in March."

### 2.2 What actually creates exposure

Three things, in the order they hurt:

1. **Unattributable evidence.** A finding that cannot name the asset it attaches to, or
   the rule version that produced it, is difficult to defend regardless of how good the
   underlying control is.
2. **Point-in-time results with no series.** CIP-010 R2 is about detecting deviation from
   a baseline. A scan result with no prior state cannot demonstrate that.
3. **Coverage claimed rather than measured.** "All BES Cyber Systems are assessed" is a
   statement an auditor will test against the asset register.

Penalties are commonly cited at up to $1,000,000 per violation per day under FERC
enforcement. Use that figure carefully: it is a statutory maximum, not a typical
outcome, and utility compliance staff will know the difference.

### 2.3 Where AAC fits

AAC is the **record layer and the correction layer**. It collects facts through Ansible,
evaluates them against versioned policy in OPA, persists the verdict into PostgreSQL as a
historical series — and, because it is part of Ansible Automation Platform, it can then
**act on what it found**: patch, reconfigure, roll back to a known-good state, and record
that correction as an authorised change.

It is a configuration scanner: the collections that manage each technology define its
configurable settings, and AAC reads those settings for their current value and judges them.
It is not a network sensor or an intrusion detector; the utility already owns those, and AAC
takes their output as evidence rather than replacing them.

> **The positioning that holds up:** the utility's existing tools keep sensing; AAC scans
> configuration across the estate and is the system of record that turns their output into an audit record with history, policy
> provenance, and a consistent control mapping across all 14 standards — **and the same
> platform closes the finding and proves it closed.**

That second half is not a footnote. A utility can buy assessment from many vendors. What
is hard to buy anywhere else is detection and correction on one platform, under one change
record, with the evidence of both in one series.

### 2.4 The gap AAC actually fills in AAP

This is the clearest way to explain what AAC *is*, and it should be the first thing said
in a technical conversation.

**Ansible Automation Platform has been best-in-class at managing and changing state for
years.** You express intent — requirements, standards, a desired configuration — and the
estate converges on it. Declarative, idempotent, agentless, at fleet scale. That has never
been the gap.

The gap is that AAP could enforce intent **one playbook at a time**, and could not answer
either of these:

> **"How well does this whole estate align to NERC-CIP? To ISO 27001? To CIS RHEL 9?"**
>
> **"Which specific managed node fails which specific control, right now?"**

Those are the same question at two altitudes, and AAP had neither. A successful playbook
run tells you the playbook succeeded. It does not tell you how aligned the estate is to a
standard the playbook was never written against.

**AAC is that missing layer.** OPA evaluates collected state against versioned policy for
**many standards at once**, so a single fact collection answers all of them — the same
host facts that satisfy a CIS RHEL check also feed NIST, STIG and CIP-007. The result
works in both directions on one axis:

| Direction | The question | Who asks it |
|---|---|---|
| **Roll up** | overall alignment across varied standards, over time | compliance manager, executive, auditor |
| **Drill down** | this node, this control, this verdict, this evidence | the engineer who has to fix it |

Neither view is useful alone. An alignment percentage nobody can decompose is a number
nobody trusts. A per-node finding with no aggregate is a backlog nobody can prioritise.

**And the measurement does not stop at a verdict — it hands the required corrections
directly back to AAP.** This is the step that makes the alignment view operational rather
than informational:

```
standard's requirement  ──▶  measured node state  ──▶  the delta
                                                        │
                                    the specific required corrections
                                                        │
                                        back into AAP as executable work
                                          (generated playbook, gated,
                                           validated, re-assessed)
```

The output of a drill-down is not "node X fails control Y" for someone to go and
interpret. It is **the correction that control Y requires on node X**, expressed as
automation the platform can run — because the measurement already knows the requirement,
the current state, and the node identity AAP manages it under. Nothing is re-derived and
nothing is handed across a boundary.

That is the whole product in one sentence: **AAP changes state to match intent; AAC
measures how well the estate matches a body of standards, at every altitude, and hands the
required corrections directly back to AAP.**

---

## 3. How — the architecture

### 3.1 The pipeline

```
Source systems  (CMDB · GRC · IAM · SIEM · patch · scanners · PACS · INSM · cluster)
      │
      ▼
Ansible Automation Platform          fact collection, per source system
      │   job templates, scheduled or event-driven; no agents on BES assets
      ▼
Open Policy Agent  (opa-ot)          evaluation against versioned Rego
      │   CIP-002 … CIP-015, one package per standard + an aggregator
      ▼
PostgreSQL  compliance_results       the historical evidence series
      │
      ├──▶ Reports · Grafana · portal      auditor-facing output
      │
      └──▶ AAP remediation                 patch · reconfigure · roll back  (§3.6)
                  │
                  └──▶ re-assess ──▶ proven closure, in the same series
```

Four properties are what a utility is buying:

- **Policy is versioned and external to the collection code.** The rule that produced a
  verdict is a reviewable artifact, not logic inside a script.
- **Collection is agentless, and rides on access AAP already has.** State comes from
  Ansible's native `gather_facts` and the standard connection AAP already uses to manage
  the system — no agent, no new port, no new credential model. **The access a utility has
  already granted AAP to *manage* a system is exactly the access needed to *measure* it.**
  This matters disproportionately for OT: adding an agent to a BES Cyber Asset is itself a
  CIP-010 change and a CIP-005 consideration. Assessment that rides on already-approved
  infrastructure avoids both.
- **Every assessment is a row, not a report.** History is the default, not a feature.
- **The platform that finds it can fix it.** Detection and correction share one control
  plane and one audit record — see §3.6.

### 3.2 AAC does not collect from BES assets directly

This is the point most often misunderstood. The great majority of CIP evidence does not
live on the BES Cyber Asset — it lives in the **systems of record around it**: the CMDB
that categorises it, the GRC platform holding the approved documentation, the HR and
learning systems proving personnel training, the PACS logging physical access.

**Where AAC does read the asset directly, it reads it the way AAP already does.**
`gather_facts` returns the OS and version, installed packages, running and enabled
services, network configuration, mounts, and local accounts — which is most of what
CIP-007 and CIP-010 need at the host level, available with no additional tooling on the
target. The technology components of the environment describe their own current state
through the mechanism the platform already uses to automate them.

That is worth stating plainly in a CIP conversation, because the first objection to any
assessment tool is "what are you installing on my BES assets?" The answer is nothing.

AAC's job is then to query the surrounding systems and assemble a single evidence object
per assessment.
`policies/frameworks/critical_infrastructure/nerc_cip/DATA_SOURCES.md` maps every one of
the 233 input fields to the source system that must supply it, the collection method, and
its current status. **That map is the most immediately useful thing we have for a utility
conversation** — it is a 233-line requirements specification for CIP evidence that nobody
hands them.

### 3.3 The worked example — CIP-010 on OpenShift

One standard is implemented end-to-end and is the proof that the architecture works.

CIP-010 (Configuration Change Management and Vulnerability Assessments) asks for
R1 an established baseline, R1.2 authorised changes, and R2 monitoring for and acting on
deviations. On an OpenShift estate that maps cleanly onto tooling a utility may already run:

```
OpenShift Compliance Operator  (ocp4-nerc-cip profile, certified content)
   + Red Hat Advanced Cluster Security  (sensor; also its own runtime/vuln findings)
        │  cluster configuration → ComplianceCheckResults
        ▼
AAC     capture baseline → detect drift → mitigate → re-baseline
        ▼
PostgreSQL   authorized baseline + every deviation, tagged and evidence-chained
```

Measured, not illustrative: a live `ocp4-nerc-cip` scan produced **125
ComplianceCheckResults** (Compliance Operator v1.9.1, 2026-07-31), collated by AAC and
mapped to CIP controls from each result's own
`control.compliance.openshift.io/NERC-CIP` annotation.

The division of labour is the thing to communicate:

| Layer | Role | Owner |
|---|---|---|
| Compliance Operator | certified check content, point-in-time results in etcd | Red Hat product |
| ACS | manages and surfaces the profile; adds runtime, vulnerability, supply-chain findings | Red Hat product |
| **AAC** | **collates, maps to CIP controls, scores, persists, makes auditor-traceable** | **this platform** |

**AAC does not replace the Compliance Operator.** It is the record layer on top of it.
Say this early — a customer running the operator will otherwise hear a rip-and-replace
pitch, and the honest story is stronger than the one they fear.

Correction worth carrying: ACS does not run Rego, and AAC's NERC-CIP Rego does not
evaluate ACS facts directly. AAC collates `ComplianceCheckResult` objects and ACS
findings and maps them to CIP controls using its own versioned policy.

### 3.4 The second worked example — AMI 2.0, and why it matters most

If §3.3 proves the architecture on cluster configuration, **AMI 2.0 proves it on device
telemetry** — and for a utility audience that is the more interesting half, because it is
the only place in the platform where facts are pulled from grid devices, evaluated, and
persisted end to end without a static file anywhere in the path.

**The loop, per utility:**

```
Smart meter / head-end endpoint
      │  GET /api/ami-assessment          ← live device + head-end facts
      ▼
AAP  ami_compliance_per_utility.yml
      │  POST ×3 to OPA (opa-ot)
      ├─▶ /v1/data/ami/nist_ir7628/complete    NIST IR 7628 Rev 1
      ├─▶ /v1/data/ami/device/compliance       device posture
      └─▶ /v1/data/ami/headend/security        head-end / MDMS security
      ▼
PostgreSQL   three evidence rows per utility, per run  →  Grafana
```

**What is assessed.** Three complementary frameworks giving coverage from the meter,
through the communications network, to the MDMS head-end:

| Framework | Scope | Packages |
|---|---|---|
| **NIST IR 7628 Rev 1** | smart-grid cybersecurity — **31 controls across 6 families**: SG.AC access control, SG.AU audit, SG.CM configuration management, SG.IA identification & authentication, SG.IR incident response, SG.SC system & communications | `ami.nist_ir7628.*` |
| **AMI device compliance** | per-device posture across the meter population | `ami.device.compliance` |
| **AMI head-end security** | MDMS / head-end system security | `ami.headend.security` |

Each of three utility types — **electric, gas, water** — is assessed independently across
all three frameworks, so the model is genuinely multi-utility rather than a single
hard-coded path.

**It is wired to NERC-CIP, not parallel to it.** A nightly AAP workflow chains the two:

```
Node 1  NERC CIP Compliance Report   →   Node 2  AMI Full Compliance Audit
                                     →   Node 3  Remediation Report
```

That is the shape of the eventual production story: the OT estate and the grid-edge
estate assessed on one schedule, into one evidence series, with one remediation view.

**Why it matters for a NERC-CIP conversation.** AMI infrastructure is not itself the
Bulk Electric System, and NIST IR 7628 is not a CIP standard — do not conflate them. Its
relevance is threefold:

1. It demonstrates **live fact collection into the same policy engine and the same
   evidence table** that CIP-002→015 use. The pattern the 221 stubbed fields need is not
   theoretical; it is running next door.
2. Grid-edge security is where many utilities' immediate operational attention sits, and
   an AMI conversation frequently opens the CIP conversation.
3. The device-facts-over-REST collection shape is exactly what a CIP-015 INSM platform
   integration will look like.

**The caveat, and state it before you are asked.** The meter endpoints in our environment
are **simulators** — they emulate DLMS/COSEM meters with AMI 2.0 security attributes, and
they are not production metering infrastructure. The collection *method* against a real
head-end is the same shape (REST against the MDMS), but it has not been proven against a
production AMI system. What is proven is the full path from a live endpoint through
policy to persisted evidence — which is precisely what the NERC-CIP collection layer does
not yet have.

### 3.5 Automation surface that exists today

Driven from AAP job templates — launch by name, never by ID, as IDs shift:

| Template | What it does | Standard |
|---|---|---|
| *AAC - NERC CIP Compliance Report* | fleet assessment across CIP-002→015, writes to PostgreSQL | all 14 |
| *AAC - CIP-010 Baseline Capture* | captures OS, ports, packages as the baseline of record | CIP-010 |
| *AAC - CIP-008 Incident Response* | BES forensic evidence capture and reporting record | CIP-008 |
| *AAC - Capture OCP NERC-CIP Baseline* | cluster baseline from Compliance Operator results | CIP-010 |
| *AAC - Check OCP NERC-CIP Drift* | detects deviation from the captured cluster baseline | CIP-010 |
| *AAC - CIP-010 Demo Loop* | single job: baseline → drift → report | CIP-010 |
| *AMI - NIST IR 7628 Assessment* | live meter/head-end facts → 31 controls, 6 families | AMI 2.0 |
| *AMI - Full Compliance Audit and Store* | all three AMI frameworks, all utilities, → PostgreSQL | AMI 2.0 |
| *NERC/AMI Nightly Audit* (workflow) | chains NERC-CIP → AMI → remediation report | both |

### 3.6 Closing the loop — remediation, patching and management

**This is a large part of AAC's value and it is routinely undersold.** Assessment tells a
utility what is wrong. AAP is the platform that *fixes it* — and because both halves run
on the same platform, the fix arrives with an audit record attached.

The pattern is already built and demonstrated:

```
detect  ──▶  evaluate  ──▶  correct  ──▶  re-assess  ──▶  prove closed
  │            │              │              │               │
Ansible       OPA            AAP          Ansible        PostgreSQL
facts       policy       remediation      facts          evidence
                          playbook                        series
```

Working examples in the platform today:

| Capability | What it does |
|---|---|
| **Golden Image enforcement** | Detects drift from an approved image, **rolls the system back** to known-good, notifies the service desk, and re-checks. The full loop, demonstrated end to end. |
| **CIP-010 mitigate step** | The cluster loop is baseline → detect drift → **mitigate** → re-baseline. Correction is a stage in the standard's own workflow, not an afterthought. |
| **Remediation generator** | Turns a finding or CVE into a **Backup → Patch → Validate** playbook, with the validate step doing a real version comparison rather than a presence check. |
| **Patch remediation lifecycle** | A staged model from exposure ranking through deployment to verified closure. |

Why this matters specifically for NERC-CIP:

- **CIP-010 R2 asks what you did about a detected deviation.** A platform that detects and
  corrects answers that requirement with one record. A platform that only detects hands
  the utility a finding and a separate manual process to evidence.
- **CIP-007 patch management** is a remediation obligation, not only an assessment one.
  The standard is about applying security patches within a defined window.
- **The correction is itself an authorised change** — which is exactly the artifact
  CIP-010 R1.2 wants.

**Remediation carries the validation and checkpoints an auditor expects.** This is the
part that distinguishes governed remediation from "someone ran a script", and it is worth
walking through explicitly — a utility's change-management function will ask about every
one of these:

| Checkpoint | What happens | What it satisfies |
|---|---|---|
| **Authorisation** | The remediation is raised as a change and approved before it runs. A four-eyes flow — assign → submit → approve/reject — is implemented, and approval is recorded against the item. | CIP-010 R1.2 authorised change; the utility's own change process |
| **Pre-change backup** | The generated playbook's first block captures a restore point before touching anything. | Rollback capability; change-management prerequisite |
| **Check mode** | The change is executed as a dry run and the intended difference shown, before anything is applied. | Change review; "show me what it will do" |
| **Scoped execution** | The change runs against a named, bounded target set — not the estate. | Blast-radius control |
| **Failure handling** | The patch block carries a `rescue` path, so a failed change is handled rather than left half-applied. | Operational safety |
| **Post-change validation** | The playbook's third block **verifies the fix actually took**. For a patch this is a real version comparison — installed version ≥ fix version, using proper RPM EVR semantics — not a "did the package manager exit zero" check, and not a presence check. | Evidence that the remediation worked |
| **Provenance** | Every generated playbook carries a provenance header and a content hash, so the artifact that ran is identifiable later. | "Which change was this?" |
| **Re-assessment** | The control is assessed again after the change, and the result written to the same evidence series. | Proof of closure, not assertion of closure |
| **Evidence capture** | Finding, approval, change, validation and re-assessment all land in one series with timestamps and attribution. | The audit trail an auditor actually asks for |

The distinction that matters: **the loop does not close on "the playbook succeeded."** It
closes on a re-assessment that no longer reports the finding. Those are different claims,
and only the second one is evidence.

**Where the depth currently stops — say this if asked.** The validation tier that is built
is *did the change apply and does the state now satisfy the control*. Deeper assurance
tiers — functional testing of the application after patching, integration testing across
dependent systems — are **not built** in the patch path. For a utility that will matter on
BES-adjacent systems, and the honest answer is that those checkpoints belong to their
existing test process today, with an integration point rather than a replacement.

**The guardrails, which are what make it acceptable to an OT audience:**

- Remediation runs as an **authorised, gated change** through the utility's own process —
  never autonomously, never invisibly.
- **Check mode first.** The change is shown before it is made.
- Every correction is recorded, attributed and timestamped, and appears in the same
  evidence series as the finding that triggered it.

Say this early in a CIP conversation. A compliance team hears "assessment tool" and
mentally files it next to the scanner they already own. Detection *and* correction on one
platform — with the approval, backup, dry run, validation and re-assessment an auditor
expects, all in one record — is a materially different proposition.

### 3.7 Technical debt and exposure heat map

Two related capabilities that turn a finding list into something a budget holder can act
on — and they are the bridge from a compliance conversation to a funded programme.

**Technical debt scoring** converts open findings into **remediation cost**, using
per-domain hourly rates rather than a single blended figure. This matters for a utility
more than for most sectors: an OT/ICS/SCADA specialist is not costed like a sysadmin.

| Debt category | Rate | Why it differs |
|---|---|---|
| `critical_infrastructure` | $285/hr | OT / ICS / SCADA specialist |
| `sovereignty` | $225/hr | Privacy / legal engineer |
| `compliance` | $195/hr | GRC specialist |
| `security` | $175/hr | Security engineer |
| `technology_lifecycle` | $150/hr | IT asset management |
| `operational` | $125/hr | SysAdmin / DevOps |

Rates are held in a `remediation_rates` table with effective-dating, not hardcoded, and
the model **separates OT from IT budget** — which reflects how a utility actually funds
this work. Grafana panels present the result as trend and breakdown.

The output is a sentence a compliance manager can take to a budget conversation:
*"closing the CIP-007 gap on this asset class is N hours at the OT rate."*

**The exposure heat map** ranks patch exposure across the estate — KEV membership over
raw CVSS, aged against SLA, attributed to real assets — so remediation effort targets what
is actually being exploited on systems the utility actually runs.

> **Gap, and do not work around it.** The heat map **report cannot currently be
> regenerated**. The generator expects a `heatmap.json` that no script produces; the last
> published version was assembled by hand and has since drifted from the live data. Two
> of its sections exist as database views (`patch_heatmap_latest`,
> `patch_unpatched_systems`); the totals, top-CVE and no-fix sections have no producer.
>
> **Never show the live database and hand out the published heat map PDF in the same
> meeting** — they disagree. Until an extractor is built, treat the heat map as a live
> dashboard capability, not as a deliverable artifact.

---

## 4. Coverage — what is modelled versus what collects

### 4.1 The policy layer is complete

All 14 active standards are implemented as Rego, one package per standard plus an
aggregator (`nerc_cip_main`), evaluated in the `opa-ot` bucket.

| Standard | Title | Package |
|---|---|---|
| CIP-002 | BES Cyber System Categorization | `nerc_cip.cip_002` |
| CIP-003 | Security Management Controls | `nerc_cip.cip_003` |
| CIP-004 | Personnel & Training | `nerc_cip.cip_004` |
| CIP-005 | Electronic Security Perimeters | `nerc_cip.cip_005` |
| CIP-006 | Physical Security of BES Cyber Systems | `nerc_cip.cip_006` |
| CIP-007 | Systems Security Management | `nerc_cip.cip_007` |
| CIP-008 | Incident Reporting and Response | `nerc_cip.cip_008` |
| CIP-009 | Recovery Plans | `nerc_cip.cip_009` |
| CIP-010 | Configuration Change Management & Vulnerability | `nerc_cip.cip_010` |
| CIP-011 | Information Protection | `nerc_cip.cip_011` |
| CIP-012 | Communications Between Control Centers | `nerc_cip.cip_012` |
| CIP-013 | Supply Chain Risk Management | `nerc_cip.cip_013` |
| CIP-014 | Physical Security of Transmission Stations | `nerc_cip.cip_014` |
| CIP-015 | Internal Network Security Monitoring (INSM) | `nerc_cip_cip015` |

### 4.2 The collection layer is 9 fields

Measured from `DATA_SOURCES.md`, 2026-08-25:

| Status | Fields | Share |
|---|---|---|
| **Live** — collects today | **9** | 3.9% |
| **Partial** — collectable from Ansible facts, not fully wired | 3 | 1.3% |
| **Stubbed** — modelled, mapped to a source system, not yet collected | **221** | 94.8% |
| **Total input fields** | **233** | |

The nine live fields:

| Fields | Standard | Collected by |
|---|---|---|
| baseline established · captured date · components | CIP-010 | *CIP-010 Baseline Capture* |
| open ports · ports reviewed · unauthorized ports | CIP-010 | CIP-010 playbook |
| incident id · reported to NERC · reported within 1 hour | CIP-008 | CIP-008 playbook |

Everything else runs from a static assessment file
(`examples/nerc_cip_assessment_data.yml`). **A demo of the full 14-standard report is
therefore a demo of the policy engine, not of live collection.** Be explicit about that
when demonstrating it; a utility that discovers it later will discount everything else.

**The contrast to draw deliberately:** the AMI 2.0 path (§3.4) runs the same engine and
writes to the same evidence table with **no static file anywhere in the path**. It is the
existence proof that the collection layer is an integration exercise rather than an
unsolved problem — and it is the better thing to demonstrate live.

### 4.3 How to talk about this honestly and still be compelling

The stubbed 221 are not vapour — each is a named field with an identified source system
and a collection method. The sequence that makes the fastest audit difference:

1. **CMDB** — the BES asset inventory drives every other standard. Nothing works without it.
2. **GRC platform** — the bulk of the documentation and attestation fields; one integration
   touches CIP-002 through CIP-015.
3. **Patch + vulnerability scanner** — CIP-007 and CIP-010; low effort, high audit value.
4. **IAM / Active Directory** — CIP-004 personnel and access; well-supported Ansible modules.
5. **SIEM** — CIP-007 alerting, CIP-008 detection.
6. **INSM platform** — CIP-015 is newest and enforcement is ramping; highest regulatory exposure.
7. **EMS / SCADA** — CIP-014; complex OT integration, start with attestation and automate later.

The proposition to a utility is not "we have 14 standards automated." It is: *we have
modelled what every one of these standards needs, mapped it to the systems you already
run, and we can stand up the integrations in this order — with the CIP-010 loop working
on day one if you run OpenShift.*

---

## 5. The partner and integration picture

Four related efforts exist. Their maturity differs sharply and conflating them is the
easiest way to lose credibility.

| Effort | What it is | Status |
|---|---|---|
| **OpenShift Compliance Operator** | certified `ocp4-nerc-cip` check content; AAC collates and maps to CIP | **Running.** Measured against a live scan, 125 results |
| **Red Hat ACS** | manages/surfaces the profile; contributes runtime, vulnerability and supply-chain findings | **Running** in the cluster story |
| **IBM Guardium** | CIP-011 (BES Cyber System Information) — data-store security around BCSI | **Design proposal only.** No bridge is built |

Notes worth carrying into a conversation:

- **Guardium's NERC-CIP fit is narrow but very sharp.** It concentrates almost entirely in
  CIP-011. Guardium is a data-store security platform and NERC-CIP is OT-centric, so the
  overlap is small — but where it lands, it lands well. The integration architecture is
  written and is explicitly a **design proposal describing new behaviour**, not current
  behaviour. Do not demo it.

---

## 6. Gaps — stated plainly

Ordered by what would discredit us fastest, not by how hard they are to fix.

### 6.1 Collection: 221 of 233 fields are stubbed

The dominant gap, covered in §4.2. Nothing in the policy layer is blocked on it — the
policies are written and tested — but a full-fleet CIP assessment today reflects a static
file, not the estate.

**Consequence for an engagement:** never present the 14-standard report as live coverage.
Present it as the target-state artifact and the CIP-010 loop as the working proof.

### 6.2 Evidence quality in our own corpus

Measured against the live lab evidence database (2,744 rows), and the reason this section
exists at all: we applied our own evidence standard to ourselves and did not fully pass.

| Finding | State |
|---|---|
| 81.8% of rows could not name their subject (`hostname` `localhost` or null) | **Being fixed** — 906 unattributed rows resolved; real hostname resolution wired into the storage role |
| No row carried the policy version that produced it | **Addressed** — `policy_sha` / `project_sha` columns and a shared resolver, proven live |
| `framework` nullable despite being documented `NOT NULL` | **Fixed** — backfilled and constrained; fail-closed gate live |
| A framework storing zero-control rows — "found nothing" indistinguishable from "never ran" | **Fixed** — insert now rejects `total_controls = 0` |
| Managed assets with no assessment evidence | **Open** |

One limitation to state rather than oversell: the policy digest is reproducible only via
the same canonicalisation. It is a strong **change-detection** fingerprint — same digest
implies same rules — but is **not yet independently verifiable by a third party.** Do not
offer it to an auditor as a verification mechanism until a canonical JSON form is pinned.

This section is an asset in a utility conversation, not a liability. A vendor that has
measured defects in its own evidence and shows the fix sequence is more credible than one
claiming none.

### 6.3 The aggregate score is misleading

`nerc_cip_main` computes `standards_passing * 100 / 14`. A standard counts as passing only
if every requirement within it passes, so the score collapses hard: a recorded run showed
an overall score of 0% while nine of twelve standards displayed individually green on the
same screen.

**Do not put that number on a slide.** Show per-standard status and the violation detail.
The score is not the artifact; the evidence chain is.

### 6.4 Scope boundaries to state before you are asked

- **CIP-014** (physical security of transmission stations) requires EMS/SCADA integration
  and power-flow analysis. Realistically this begins as attestation.
- **CIP-015** (INSM) needs an OT monitoring platform. The Rego is written; the
  integration is not, and these platforms are the hardest to reach from an automation
  host.
- **CIP-006** depends on PACS access records — a source system that is frequently on an
  isolated network.
- Requirement-level depth varies by standard. The policies model the requirements; they
  do not claim to encode every sub-requirement's evidentiary nuance.

### 6.5 Not a gap — a boundary, and a narrower one than it first appears

The boundary is **state versus activity**, and **orchestrated change versus inline
interception**. Stated precisely:

**AAC does not** analyse activity streams — it is not a SIEM and does not evaluate audit
logs, authentication events or network flows. It does not sit inline in the data path as
an admission controller or IPS making real-time allow/deny decisions. It measures the
*state* of configuration, not the *activity* around it.

**AAP does** patch, reconfigure, harden, roll back and manage. Correction is a first-class
capability, not a bolt-on — see §3.6.

The distinction that matters to an OT audience: AAC never acts *autonomously and
invisibly* on a BES Cyber Asset. Every correction is an authorised, orchestrated,
recorded change that the utility gates through its own change process. That is
reassuring, and it is a different statement from "it cannot act", which would be wrong.

---

## 7. Taking this to a utility

**Open with §2.4** if the room is technical — the missing-alignment-layer framing lands
faster than anything else, because an AAP-literate audience already knows what AAP does
and will immediately recognise what it never did.

**Lead with:** the evidence problem (§2.1), the record-and-correction position (§2.3),
and the two working proofs — the CIP-010 cluster loop (§3.3) and the AMI 2.0
live-collection loop (§3.4). If they run OpenShift, lead with CIP-010. If the conversation
starts at the grid edge, lead with AMI.

**Do not stop at assessment.** §3.6 — detection *and* correction on one platform, under
one change record — is a large part of the value and the thing a scanner vendor cannot
answer. A compliance team who hears only "assessment" files us next to a tool they already
own. Follow it with §3.7: technical debt scoring turns the finding list into a costed
programme at OT rates, which is what turns a compliance conversation into a funded one.

**Then:** the 233-field source map (§3.2) as the artifact that shows we have actually done
the work of understanding what CIP evidence requires — scoped to the systems that utility
runs.

**Be straight about:** collection status, in the framing of §4.3. A scoped integration
sequence for their estate is a better conversation than a coverage claim, and it survives
the follow-up question.

**Do not:** demo the full 14-standard report as live coverage, show the aggregate score,
demo the Guardium bridge, present AMI simulators as production metering, conflate NIST
IR 7628 with a CIP standard, hand out the published heat-map PDF alongside live data
(§3.7), or say "compliant."

**Before the meeting, read:** `DATA_SOURCES.md` for the source-system map; the
Compliance Operator comparison if they run OpenShift.

---

## 8. Verification status of this document

| Claim | How established |
|---|---|
| 14 standards implemented as Rego | Package declarations in `nerc_cip/`, counted |
| 233 input fields; 9 live, 3 partial, 221 stubbed | Parsed from the status column of every field row in `DATA_SOURCES.md`, 2026-08-25 |
| 125 ComplianceCheckResults, Compliance Operator v1.9.1 | Measured from a live `ocp4-nerc-cip` scan, 2026-07-31, recorded in the comparison doc |
| Aggregate score formula and its 0% behaviour | Read from `nerc_cip_main.rego`; the 0%-with-green-standards run is a recorded demo result |
| Evidence-quality findings and their fix state | Measured against the lab evidence database, 2,744 rows |
| AMI 2.0: 31 controls, 6 SG families, 3 frameworks, 3 utilities | Counted from `ami_2_0_assessment_scope.md` and the `ami.*` package declarations |
| AMI collection is live end-to-end | Read from `ami_compliance_per_utility.yml`: REST GET to the meter endpoint, three OPA POSTs, three PostgreSQL writes — no static input |
| AMI endpoints are simulators, not production meters | `demos/ami_nerc/meter_simulator.py` — emulates DLMS/COSEM with AMI 2.0 security attributes |
| Multi-framework evaluation from one fact collection | The same collected host facts are evaluated by CIS, STIG, NIST and CIP packages in the shared policy library |
| Remediation is a built capability, not a roadmap item | Golden Image enforcement (detect → roll back → notify → re-check), the CIP-010 mitigate stage, and the Backup→Patch→Validate remediation generator all exist and have been demonstrated |
| Per-domain remediation rates | `remediation_rates` table, effective-dated, OT/IT budget separated |
| The heat map report cannot be regenerated | The generator requires a `heatmap.json` that no script produces; the last published version was hand-assembled and has drifted from live data |
| Guardium integration is design-only | Stated as design proposal in its own architecture document |
| Template names | AAP job templates; **names not IDs** — IDs shift and a stale ID silently runs a different template |

Nothing above rests on recall. Where a claim is a design proposal rather than running
behaviour, it is labelled as one.

---

## Revision history

| Version | Date | Change |
|---|---|---|
| v1.1 | 2026-08-25 | Added §2.4 — the gap AAC fills in AAP: AAP changes state to match intent, but could never report overall alignment to varied standards with drill-down to a specific managed node. That is the product thesis and it now leads the document. **Corrected a material understatement.** v1.0 said "AAC assesses; it does not enforce" and "the enforcement systems are the utility's existing controls", which gave away one of the platform's biggest strengths. AAC is part of AAP, and AAP patches, reconfigures, rolls back and manages. The real boundary is state versus activity streams, and orchestrated change versus inline interception — §1.3, §2.3 and §6.5 restated, and §3.6 added on the detect→correct→re-assess loop. Added §3.7 on technical debt scoring at per-domain OT rates and the exposure heat map, including the heat-map regeneration gap. |
| v1.0 | 2026-08-25 | Initial version. Written for a Red Hat team engaging a utility. States the collection gap (9 of 233 fields live) explicitly, positions the CIP-010 cluster loop as the working proof, and separates running integrations from design proposals. |
