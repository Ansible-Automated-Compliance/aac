# AAC Patch Remediation Lifecycle — CVE to Verified Closure

**Version:** v1.5
**Date:** 2026-08-07
**Audience:** Internal engineering and product; customers and partners under NDA.
**Status:** Target-state design. Every stage carries an honest implementation
status — ✅ shipped, ⚠️ partial, ❌ gap — so this doubles as the build roadmap.

## Revision history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-08-07 | Initial twelve-stage lifecycle; asset-class generic; one worked example + three contrast vignettes |
| v1.5 | 2026-09-02 | Added **Stage 4b — Remediation-path determination** (backport vs upgrade as an agentic, debt-costed, policy-governed decision — "a backport is a loan"), §5.10 **Surface lag — the backport ledger** (lag metrics feeding `technology_lifecycle`, extending §5.9's support-status view with distance-behind-upstream), the **VEX attestation** addition to Stage 12 (evidence-backed closure when scanners stay red on backported builds), and the intent-vs-as-built (POM/SBOM) framing with pointers to the portal's SBOM-catalog design. Informed by the Mythos demo composition. |
| v1.1 | 2026-08-07 | Added §5 **Aggregation — Technical Debt & Coverage Heat Map**: patch exposure as a debt *and risk* source, the exposure-valley concept, and the drill-down contract that makes the map the single view of gaps and risks across the estate |
| v1.4 | 2026-08-07 | Added §11 **Roles and responsibilities**: role definitions, per-stage RACI, how accountability shifts by risk tier, the AI's fixed Consulted-only position, separation-of-duties rules and anti-patterns |
| v1.3 | 2026-08-07 | Added §8 **Compliance control mapping** (NIST 800-53/CSF, NERC CIP-007-6, ISO 27001:2022, PCI DSS v4.0, SOC 2, CIS v8, 800-171/CMMC, IEC 62443-2-3), §9 **Programme metrics** (SLA compliance rate, burndown, estimate-vs-actual feedback loop) and §10 **Adapter contracts** |
| v1.2 | 2026-08-07 | Added §5.9 **Technology age**: support status (automatically tracked from vendor lifecycle sources) and capital position (from asset management), the support × depreciation quadrant, vendor-viability signals, and the finding that unsupported technology converts remediation debt into replacement debt |

---

## 1. Purpose and scope

This document describes the complete lifecycle of a security patch in the
Ansible Automated Compliance (AAC) platform: from a CVE arriving in a public
feed, through identifying exactly which of a customer's assets are affected,
authorising the work, applying it safely, proving it worked, and closing the
loop so the platform's own record of the estate is current again.

**It is not limited to servers.** The same twelve stages apply to:

| Asset class | Examples |
|---|---|
| **Compute** | RHEL / Windows servers, VMs, container images |
| **Network** | Routers, switches, firewalls (VyOS, pfSense, vendor appliances) |
| **Application** | Web tiers, middleware, language-runtime dependencies |
| **Storage** | Array controller firmware, HBA/driver stacks, storage services |
| **OT / IoT** | AMI smart meters, RTUs, protection relays, field devices |

The *stages* are constant. The *mechanics of each stage* differ by class — and
those differences are where most real-world patching programmes fail. Section 6
walks one class end to end; Section 7 shows where the others diverge. Section 5
describes how it all aggregates into a single view of gaps and risks.

### Two boundaries that never move

1. **AAC assesses; the customer executes.** The Portal never reaches into a
   customer environment. The customer's own automation pulls work over
   authenticated, scope-gated endpoints and runs it under their own change
   control. The Portal records evidence.
2. **Hostnames stay with the customer, and no binaries are hosted.** The
   inventory the Portal receives is aggregated — it knows *how many* hosts run a
   vulnerable package, never *which*. Host-level resolution happens inside the
   customer estate. Patch content is never mirrored; the Portal distributes the
   *address* of a fix, not the fix.

---

## 2. Design principles

- **Policy decides depth, not procedure.** How much backup, how much testing,
  how much approval — these are risk decisions, evaluated in OPA like every
  other decision in AAC. A tier-0 dev host and a BES Cyber System do not get the
  same ceremony, and that difference should be a policy input, not a fork in a
  playbook.
- **Adapters, not integrations.** Ticketing, traffic management and asset
  management all vary per customer. The lifecycle defines a *contract*; providers
  plug in behind it. ServiceNow is the primary provider for two of the three, but
  nothing in the design depends on it.
- **Observe, don't assume.** Where a customer system of record and our own fact
  collection disagree about the estate, fact collection is the ground truth for
  *what exists*, and the disagreement itself is a finding.
- **Every mutating step is reversible, or it does not run.** The recovery path
  is chosen and verified *before* the patch step executes.
- **Closure requires proof, not assertion.** A ticket closes when the platform
  can re-measure the estate and demonstrate the exposure is gone.
- **Fail closed and loudly.** An ambiguous match, a missing fix, or an
  unverifiable rollback stops the flow and surfaces; it never silently proceeds.

---

## 3. Architecture at a glance

```
   PUBLIC FEEDS                 PORTAL (operator-hosted)          CUSTOMER ESTATE
  ┌──────────────┐            ┌──────────────────────┐         ┌──────────────────┐
  │ NVD          │──ingest──► │ cve_events           │         │ host_facts       │
  │ CISA KEV     │            │ classification       │         │      │           │
  │ Vendor advis.│            │ cve_vendor_remediat. │         │      ▼           │
  └──────────────┘            │                      │         │ installed_       │
                              │ tenant_inventory_    │◄─pull───│  inventory       │
                              │  catalog (aggregate) │  bridge │      │           │
                              │      │               │         │      ▼           │
                              │      ▼               │         │ inventory_catalog│
                              │ tenant_cve_matches   │         │  (host_count)    │
                              │      │               │         │                  │
                              │      ▼               │         │                  │
                              │ patch manifest ──────┼──pull──►│ patch_worklist   │
                              │ (coords + advisory)  │         │  (PER HOST)      │
                              │                      │         │      │           │
                              │ remediation_items ◄──┼─────────┤      ▼           │
                              │ remediation_playbooks│         │ change record    │
                              │      │               │         │      │           │
                              │      ▼               │         │      ▼           │
                              │ customer_remediation_│◄─post───│ execute (AAP)    │
                              │  runs (evidence)     │ outcomes│                  │
                              └──────────────────────┘         └──────────────────┘
```

The asymmetry is deliberate: **detail flows outward as coordinates, evidence
flows back as outcomes.** Identity stays home.

---

## 4. The twelve stages

### Stage 1 — Baseline the estate ✅ shipped

Fact collection populates `host_facts`. `refresh_inventory_catalog.yml`
normalises that into `installed_inventory` (one row per host × package, with
`os_family`, version, architecture) and refreshes the `inventory_catalog`
materialised view, which aggregates to `{vendor, product, version}` plus a
**host_count**. Operator-declared products that package managers cannot see —
appliance firmware, network OS versions, storage microcode — are added through
`manual_product_declarations`, which carries its own `affected_hosts[]`.

The bridge serves the catalog; the Portal pulls it per tenant into
`tenant_inventory_catalog`.

> **Asset-class note.** Compute populates automatically. Network, storage and OT
> assets frequently require the manual-declaration path or a class-specific
> collector, because there is no package manager to interrogate. Catalog
> completeness — not CVE coverage — is the usual limiting factor on patch
> programmes.

### Stage 2 — CVE intake and classification ⚠️ partial

NVD and CISA KEV adapters ingest into `cve_events`. Classification tags each CVE
into operator-curated vendor and bucket taxonomies. Vendor advisories populate
`cve_vendor_remediations` — **the fix data**, without which no downstream stage
can produce anything actionable.

**Status:** feed ingestion and classification are shipped. Vendor-remediation
enrichment is the current gap; KEV establishes *exploitation*, not *remedy*.

### Stage 3 — Match to the estate ⚠️ partial

The matcher joins CVEs to `tenant_inventory_catalog`, producing
`tenant_cve_matches` with `inventory_hits`, severity and KEV membership. Tenant
preferences apply here: severity floor, KEV pass-through, tag-only mode, and
per-match suppression with an audit trail.

**This is the notification event.** A match with `inventory_hits > 0` means "you
own something affected by this." Everything before it is intelligence;
everything after it is work.

### Stage 4 — Target to individual assets ✅ shipped

The Portal exposes the inventory-keyed manifest:

```
GET /api/portal/v1/tenants/{tenant_id}/patches      scope: remediation
```

Per CVE it returns severity, KEV membership, the affected
`{vendor, product, installed_version}` tuples with a **host count**, and one or
more fixes carrying package coordinates, install command, package manager,
source classification and advisory link.

The customer's AAC pulls this and **resolves the count back to real hostnames**
locally, against `installed_inventory`, into `patch_worklist`. Two joins happen,
and both record their provenance on every row:

| Column | Values | Meaning |
|---|---|---|
| `host_resolution` | `auto` / `manual` | matched per-host inventory, or an operator-declared product's `affected_hosts[]` |
| `fix_match` | `os_family` / `registry` / `sole` / `ambiguous` / `none` | how confidently the right vendor's fix was selected for this host |

A CVE with **no** known fix is retained (`fix_match='none'`) rather than
dropped — hiding it would hide exposure. An unresolvable vendor choice is
flagged `ambiguous` rather than silently trusted.

### Stage 4b — Remediation-path determination: patch vs upgrade ❌ gap (design)

Every patch pipeline takes a fork here without pricing it. When a fix
exists as both a backport (a vendor backport build or a
z-stream) and a version upgrade, the choice is made by default, not by decision.

**A backport is a loan.** It clears the CVE but extends time-on-old-version;
the backport suffix counter is literally a running tally of accumulated
principal. Each one widens the delta to upstream, raises the cost of the
eventual upgrade, and increases the likelihood the next CVE needs yet another
backport. An upgrade pays principal now at the price of regression risk and
effort now. Neither is always right — it is a **costed decision per component
per estate**, and AAC holds every input:

| Input | Source |
|---|---|
| Running vs latest-in-branch vs upstream vs EOL | Stage 1 catalog + §5.9 lifecycle stages |
| Will a fix ever exist on this branch | Stage 3 / support status |
| Stacked-backport count on this component | catalog version history |
| Expected future-CVE rate for this component | CVE feed history per version-year of lag |
| Effort + $-rates for both paths | §5.4 effort model × `remediation_rates` |
| App criticality / risk tier / change windows | Stage 6 tiers + maintenance-window policy |

**The determination is agentic — and governed.** An agent assembles
`cost(backport path) = patch effort + expected future backports + upgrade-cost
growth` against `cost(upgrade) = upgrade effort + regression risk given
criticality`, and emits one of three recommendations with the arithmetic
attached: *backport now*, *upgrade now*, or the honest middle answer no current
tooling gives — *backport now AND schedule the upgrade by date X; waiting costs
$Y per quarter*. The agent operates inside OPA policy (the same MCP-governance
posture as everywhere else in AAC), the recommendation lands in the Stage 5
change record, four-eyes approves the **action**, and the decision itself
becomes audit evidence. Consistent with §11: the AI is Consulted, never
Accountable.

### Stage 5 — Raise the change record ⚠️ partial

Work becomes a **change record** — the authorisation artefact. AAC treats this
as an adapter contract, not a specific product:

| Provider | Role |
|---|---|
| **ServiceNow** | Primary. Change Request with CI linkage, risk, window |
| Jira / Remedy / others | Same contract, different backend |
| **AAP workflow approval** | Native path when no external ITSM exists |
| `remediation_items` | Always the internal state of record, whatever fronts it |

**Contract the adapter must satisfy:**

```
create(work)        -> external_ref          # returns the CR/issue id
state(external_ref) -> pending|approved|rejected|closed
attach(evidence)                             # playbook, backup ref, test results
close(external_ref, outcome, evidence)
```

`remediation_items` already implements genuine **four-eyes**: statuses
`open → in_progress → pending_approval → approved`, with a database CHECK
constraint enforcing that the approver is a different person from the submitter.

**Gap:** there are no terminal states. `completed`, `failed`, `rolled_back` and
`closed` must be added before a ticket can actually close — see Stage 12 for what
closure requires, and §9 for where this sits in the build sequence.

### Stage 6 — Select risk tier and recovery plan ❌ gap (design below)

Before anything mutates, policy evaluates the asset and selects depth. Proposed
inputs: asset criticality and regulatory scope (BES Cyber System, PCI/CDE, SOX,
PHI), blast radius (single node vs. cluster member vs. singleton), reversibility,
and change-window constraints.

| Tier | Typical asset | Backup depth | Approval | Rollout |
|---|---|---|---|---|
| **0** | Dev / ephemeral | Package manifest | Auto | Parallel |
| **1** | Standard prod, redundant | Manifest + config | Single | Serial, canary first |
| **2** | Business-critical, singleton | Full snapshot / golden image | Four-eyes | Serial, soak between |
| **3** | Regulated / OT / safety | Snapshot + offline evidence | Four-eyes + window + CAB | Staged campaign |

Tier selection belongs in **OPA**, consistent with every other AAC decision —
adding a tiering rule should be a policy change, not a code change.

### Stage 7 — Prepare: backup and remove from service ❌ gap

Two actions, both class-dependent, both required before the patch step.

**7a. Backup — "to the depth required to safely recover."**

| Class | Meaningful backup |
|---|---|
| Compute | VM/storage snapshot or LVM snapshot; package manifest alone is *not* recovery |
| Network | Running-config export **plus** the alternate boot image slot |
| Application | Config + data backup, or a blue/green standby |
| Storage | Controller config + replication state; never snapshot the array with itself |
| OT | Device config + firmware image, plus a documented field-recovery path |

Today the generated playbook captures a **package-level manifest** only. That is
sufficient to *describe* the prior state and to drive a package downgrade; it is
not sufficient to recover a host whose patch corrupted it. Closing this is the
single highest-value item in Section 12.

**7b. Remove from service — the traffic-drain adapter.**

"Take it out of the load balancer" generalises to *stop sending it work and wait
for in-flight work to finish*. One contract, many providers:

```
drain(asset, timeout)   -> drained          # stop new work, await quiesce
verify_quiesced(asset)  -> bool             # zero active sessions/paths
undrain(asset)          -> in_service
verify_in_service(asset)-> bool             # receiving and healthy
```

| Class | What drain actually means |
|---|---|
| Compute behind LB | Disable pool member (F5, HAProxy, ALB/ELB, OpenShift route/endpoint) |
| Network device | Routing failover — raise OSPF cost, HSRP/VRRP standby, drain BGP with AS-prepend |
| Application | Connection draining, consumer-group rebalance, queue quiesce |
| Storage | Path failover — multipath, controller failover to partner |
| **OT / AMI** | **Frequently impossible.** A meter has no standby. Mitigation is scheduling, staged campaigns and rollback readiness, not drain |

**No traffic-drain integration exists today.** The adapter contract above is the
proposed design.

### Stage 8 — Acquire the patch ✅ shipped

The manifest resolves each fix to a **download path**, classified by how the
customer legitimately obtains it:

| `source` | Meaning | Retrieval |
|---|---|---|
| `vendor_entitled` | RHEL, SUSE — subscription-gated | Customer's own Satellite / RHUI / SCC. **Never mirrored by the Portal** |
| `os_repo` | Public distro archive | Distro mirror |
| `registry` | Language ecosystem (npm, PyPI) | Public registry |
| `advisory_reference` | Advisory known, package coordinates not | Manual, vendor-directed |

`artifact_url` is deliberately null. The Portal is a **directory service for
fixes, not a repository of them** — which keeps it clear of redistribution
licensing entirely and removes it as a supply-chain target.

### Stage 9 — Apply ✅ shipped (generation) / ⚠️ pull execution

The generator emits a **Backup → Patch → Validate** playbook. Structural
guarantees: `become: true`, `serial: 1` by default (one host at a time), Backup
and Validate read-only on the target, Patch the only mutating block, a `rescue`
on Patch, and a provenance header with a SHA-256 of the generated content.

Execution happens in the **customer's own AAP**, under their change control. The
customer pulls approved work:

```
GET  /api/portal/v1/tenants/{id}/remediations/pending      scope: remediation
POST /api/portal/v1/tenants/{id}/remediations/{item}/outcomes
```

> **Asset-class note.** `dnf update` has no analogue outside compute. Network
> devices write an image to the alternate slot and reboot into it. Storage
> arrays update controller-by-controller to preserve availability. Applications
> may deploy a new artefact rather than patch in place. OT devices run a staged
> campaign over a management protocol. Stage 9 is where the class-specific
> module belongs; Stages 1–8 and 10–12 remain common.

### Stage 10 — Validate: the assurance ladder ⚠️ narrow

"Test it" means climbing until you have the assurance the tier demands:

| Level | Question answered | Status |
|---|---|---|
| **A0 — Version** | Is the fixed version actually installed? | ✅ Real comparison (installed ≥ fixed, RPM EVR-aware) — not a presence check |
| **A1 — Service** | Is the service running and listening? | ❌ |
| **A2 — Functional** | Does it do its job? (health endpoint, query, synthetic transaction) | ❌ |
| **A3 — Integration** | Does it work *in the estate* — through the LB, with dependants? | ❌ |
| **A4 — Compliance** | Does re-assessment show the exposure gone? | ❌ (mechanism exists; not wired as a gate) |

A0 alone is a version assertion, not assurance of working software. Tier 1 should
require A1–A2; tier 2+ should require A3; regulated changes should require A4 as
the evidentiary record.

### Stage 11 — Branch: succeed or recover ❌ gap

**On success:** capture evidence, undrain, verify in service, close the record.

**On failure: the recovery ladder.** Depth matches what went wrong:

| Level | Action | Notes |
|---|---|---|
| **R0** | No-op | Patch failed cleanly; nothing changed |
| **R1** | Package downgrade from manifest | Needs per-package downgrade logic |
| **R2** | Config restore | Network/app/storage config from Stage 7a |
| **R3** | Snapshot restore | VM/LVM/storage rollback |
| **R4** | **Golden-image reimage** | Rebuild to a known-good signed image |
| **R5** | Failover / rebuild | Promote standby; rebuild from scratch |

**Today rollback is not automatic.** The Patch block's `rescue` fails loudly and
prints the snapshot location for a human. That is honest, but it is a runbook,
not automation.

**Golden image and AI-assisted recovery.** AAC already ships Golden Image
enforcement — drift detection, rollback to a known-good image, and notification,
orchestrated as an AAP workflow. Recovery-by-reimage (R4) is that same machinery
pointed at a failed patch rather than at configuration drift.

AI's role is **diagnosis and recommendation, under human authority**:

- classify the failure — did the patch fail, or did the *service* fail after a
  successful patch? Those need different recovery levels
- correlate against prior runs in `customer_remediation_runs` — has this fix
  failed on this platform before?
- recommend the lowest sufficient recovery level, with its evidence
- draft the change-record update and the customer-facing explanation

The AI recommends; policy and a human authorise. Reimaging a production asset is
never an autonomous decision.

### Stage 12 — Close and reconcile ⚠️ partial

Closure is not "the playbook succeeded." It is **the platform re-measuring the
estate and proving the exposure is gone**:

1. Post the outcome → `customer_remediation_runs` ✅
2. Undrain, verify in service ❌
3. Re-run fact collection and `refresh_inventory_catalog` on the changed hosts ⚠️ *(exists, not wired as a closing step)*
4. Re-pull the catalog into the Portal; re-run matching ⚠️ *(same)*
5. **Confirm the CVE no longer matches** — the actual proof ✅ *(`verify_patch_closure.yml`)*
6. Attach evidence and close the change record ❌ *(needs Stage 5 terminal states)*
7. Recalculate technical-debt and coverage heat map ❌ *(see §5 — this is the proof surface)*
8. Emit the compliance/audit artefact for the evidence trail ⚠️

Steps 3–5 are the difference between a patching *process* and a patching
*programme*. Without them the platform's belief about the estate silently drifts
from reality, and the next CVE match is computed against stale inventory.

---

#### Stage 12 addition — VEX attestation on closure ❌ gap (design)

Backported builds keep scanners red *correctly*: the advisory's affected range
contains the backport's version string, and nothing in the advisory says the
patch was applied. The answer is not suppression — it is the same posture as
the waiver system: **closed, never hidden, with evidence.** On verified
closure, generate a VEX statement (`NOT_AFFECTED` /
`vulnerable_code_not_present`, naming the specific remediated build) **from
observed post-patch inventory** — a stronger justification than attesting from
the update event, because it is grounded in what the estate actually runs. The
attestation joins the change record and the audit-evidence stream, and feeds
customer scanners that consume VEX.


## 5. Aggregation — the Technical Debt & Coverage Heat Map

Stages 1–12 describe a *single* patch. A patching programme needs the view above
it: **where is the estate exposed, how much does it cost to close, and what is
the risk of not closing it.** That is the Technical Debt & Coverage Heat Map, and
it is the aggregation surface for everything in this document.

### 5.1 What the heat map is today

The map scores **compliance-control violations** into six debt categories, with
effort hours and cost at per-domain rates, presented as:

| View | Grid | Serves |
|---|---|---|
| Primary | `hostname × debt_category` → hours, item count, debt score, est. cost | "Which hosts are costing me?" |
| Framework | `framework × domain` (OT / IT / Sovereignty) | "Which programme is costing me?" |
| Valleys | Coverage and currency gaps | "What am I not even looking at?" |

Rates are per-tenant and time-versioned, so cost always reflects the rate in
effect at evaluation time. OT, IT and Sovereignty budgets roll up separately —
NERC-CIP debt does not consume the IT security budget, because a different team
funds and staffs it.

**Patch and CVE exposure is absent from this model.** The map answers "where am I
non-compliant," not "where am I vulnerable." Closing that is what this section
specifies.

### 5.2 What patching contributes: debt *and* risk

The existing map is a **cost** surface — hours × rate. Vulnerability exposure
adds something cost alone cannot express. A KEV-listed CVE means *actively
exploited in the wild*: the question is not what it costs to fix, but what it
costs **not** to. So a heat-map cell gains two contributions from this lifecycle:

| Contribution | Answers | Unit |
|---|---|---|
| **Remediation debt** | What will it cost to patch everything outstanding? | hours, currency |
| **Exposure risk** | How badly am I exposed while it stays unpatched? | unitless risk score |

Both aggregate to the same host × category cells, so a single view carries the
budget question and the risk question together.

### 5.3 Category mapping — no new category

Patch findings fold into the **existing** debt categories rather than adding a
seventh. A host's number stays a single number, and no rate table, rollup or
chart has to learn a new concept:

| Finding | Category | Rationale |
|---|---|---|
| Unpatched CVE with an available fix | `security` | It is a security defect with a known remedy |
| EOL / unsupported version, no fix available | `technology_lifecycle` | It is a lifecycle problem; patching cannot solve it |
| OT/ICS device exposure | `critical_infrastructure` | Follows the existing domain separation |

The consequence is deliberate: on the primary grid, a host's `security` cell
becomes the sum of its **compliance** security findings and its **unpatched CVE**
findings. That is the aggregation — one cell, one owner, one budget line.

### 5.4 Effort model

Patch effort is per *host × fix*, scaled by asset class and whether service
interruption is required. Indicative defaults, tunable per tenant:

| Work | Default hours |
|---|---|
| Package update, no reboot, redundant host | 0.25 |
| Package update requiring reboot + drain/undrain cycle | 0.5 |
| Application/middleware update with functional validation | 1.0 |
| Network device image swap (slot + reboot + failover verify) | 2.0 |
| Storage controller firmware (controller-by-controller) | 4.0 |
| OT firmware campaign | Per cohort, not per device — field economics dominate |

These are estimates for **planning**, not billing. Their value is comparative:
they let a CISO see that one storage array's firmware backlog outweighs two
hundred package updates.

### 5.5 Risk score

```
risk = severity_weight × kev_multiplier × age_factor × breadth
```

| Term | Values |
|---|---|
| `severity_weight` | CRITICAL 10 · HIGH 6 · MEDIUM 3 · LOW 1 |
| `kev_multiplier` | 3.0 if KEV-listed, else 1.0 |
| `age_factor` | `1 + (days_since_fix_available / 30)`, capped at 4.0 |
| `breadth` | Scaled by affected host count — a fleet-wide exposure outranks a single host |

`age_factor` is the term that matters most operationally: it makes an
un-actioned finding **grow louder over time**, so a stale backlog cannot sit
quietly at the same colour for months. Exposure is dated from when the fix became
available, not from CVE publication — the clock starts when action became
possible.

### 5.6 The third valley: exposure

The map surfaces two valley types today. Patching adds a third, and it is the
most actionable of them:

| Valley | Meaning | Why it matters |
|---|---|---|
| **Coverage** | Controls or hosts never assessed | You do not know |
| **Currency** | Assessment or policy has gone stale | You knew, once |
| **Exposure** ← new | Known-vulnerable, **fix available**, unremediated past SLA | You know, the remedy exists, and it has not been applied |
| **Support** ← new (§5.9) | Concentration of unsupported or obsolete technology | No remedy exists. Patching cannot help; only replacement can |

Coverage and currency valleys are questions. An exposure valley is an *answer
you have not acted on* — which is also how it will read in an audit finding.

Suggested SLA thresholds, tenant-configurable:

| Class | Threshold |
|---|---|
| KEV-listed | 14 days |
| CRITICAL | 15 days |
| HIGH | 30 days |
| MEDIUM | 90 days |
| LOW | Next maintenance window |

### 5.7 Drill-down contract

Aggregation is only useful if it reverses. Every cell resolves to the underlying
work:

```
heat-map cell (host × security)
   └─► patch_worklist rows for that host
         └─► CVE, severity, KEV, current → fixed version,
             install command, source, advisory link,
             host_resolution + fix_match provenance
               └─► remediation_items / change record (if raised)
                     └─► customer_remediation_runs (outcome, if executed)
```

A CISO starts at "which host is worst," and lands on the exact command that fixes
it and the ticket tracking it. The provenance columns from Stage 4 travel the
whole way, so an ambiguous vendor match is visible at the point of decision
rather than buried.

### 5.8 Where it plugs into the lifecycle

| Stage | Effect on the map |
|---|---|
| **3** — Match | A match with `inventory_hits > 0` **creates** exposure debt and risk |
| **4** — Target | Resolves it to specific hosts, so cells become host-accurate |
| **5** — Change record | Item is *accepted*, not yet closed — risk continues to accrue |
| **9–11** — Apply/validate/recover | No change until proven; a rollback returns the exposure |
| **12** — Reconcile | Re-measurement removes the finding. **The map is the proof surface** |

This closes the loop the lifecycle depends on: Stage 12 is not "the playbook
succeeded," it is "the heat map no longer shows this exposure." The map is where
closure becomes visible, and where failure to close becomes progressively louder.

### 5.9 Technology age — the lifecycle contribution

The `technology_lifecycle` debt category already exists, and its own definition
names "EOL software, deprecated protocols, obsolete OT firmware." **Nothing
currently feeds it.** The slot was cut and left empty. This section supplies it.

Technology age has two aspects with genuinely different natures, and conflating
them is why most tooling handles neither well:

| Aspect | Question | Nature |
|---|---|---|
| **Support status** | What will the vendor still do for you? | Highly automatable |
| **Capital position** | What is it worth on the books? | Requires an asset register |

#### 5.9.1 Support status — automatically tracked

Product and version are already in the catalog from Stage 1, and authoritative
lifecycle data is queryable. A scheduled job resolves every catalog entry to a
**lifecycle stage**:

| Stage | Definition | Consequence for this lifecycle |
|---|---|---|
| **Current** | In full support | Patches flow normally |
| **Mature** | Supported but superseded | Patches flow; plan the refresh |
| **Sunset** | Under 12 months to end of support | Patches flow, but replacement must be funded *now* |
| **Unsupported** | Past end of support | **No patches will ever come** |
| **Obsolete** | No longer sold, no successor product | Replacement requires re-platforming, not upgrading |
| **Orphaned** | Vendor gone or project abandoned | No recourse at all |

Sources, all queryable without customer input: `endoflife.date` for broad product
coverage, vendor lifecycle APIs (Red Hat, Microsoft and similar), and for open
source the repository itself — archive flag, last release date, commit recency.

**The structural consequence, and the most important point in this section:**

> **Unsupported technology converts remediation debt into replacement debt.**

You cannot patch what has no patches. Today a `fix_match='none'` row in the
worklist reads as a *data gap* — we didn't find a fix. For a product past end of
support it is not a gap, it is a **permanent fact**, and the only remedy is
replacement. Two things follow:

1. Its exposure risk (§5.5) **never decays**, because no patch cycle can retire
   it. Any model that assumes exposure is eventually remediable understates this
   case badly.
2. Its effort estimate is not a patch estimate. It is a migration estimate, and
   it belongs in `technology_lifecycle`, not `security`.

#### 5.9.2 Capital position — an asset-management adapter, correlated with our own catalog

Like ticketing (§Stage 5) and traffic drain (§Stage 7b), asset management is an
**adapter contract, not a product integration**. ServiceNow is the primary
provider because most enterprises already run it, but the contract is what
matters:

```
lookup(asset_identity) -> { acquisition_date, acquired_cost,
                            class_life, depreciation_method,
                            owner, cost_centre, location }
```

| Provider | Notes |
|---|---|
| **ServiceNow** | Primary — CMDB + asset management, already the Stage 5 ticketing provider |
| BMC Helix / Ivanti / Device42 / Lansweeper | Same contract, different backend |
| Flat import | CSV/API asset register for customers with no ITSM |
| **Class defaults** | Always-available fallback: per-class depreciation schedule set by the operator |

**And we already have the observational half.** The product catalog built by fact
collection in Stage 1 — `installed_inventory` and the `inventory_catalog`
matview — is a first-class source here, not just an input to CVE matching. It
gives us, per product and version:

- **what is actually running**, observed rather than declared
- **`first_seen_at` / `last_seen_at`** — when the estate first and last presented
  this version, which is a genuine age signal even with no asset record at all
- **host counts and spread** — how deeply a given version is embedded

That makes the model a **three-way correlation**, and each pair produces
something the others cannot:

| Correlation | Produces |
|---|---|
| **Catalog × vendor lifecycle** | Support status for what is *actually running* — fully automatic, no customer input, no asset register required |
| **Catalog × asset register** | Capital position for observed assets — and, in the other direction, **register drift** |
| **Asset register × vendor lifecycle** | Refresh planning for assets whose software has not been observed yet |

The middle row is worth dwelling on. Comparing what fact collection **observes**
against what the asset register **claims** surfaces two findings that neither
source produces alone:

- **Observed but not registered** — unrecorded or shadow assets, running
  and vulnerable, invisible to procurement and to the CMDB
- **Registered but not observed** — assets believed live that no longer report;
  either decommissioned without retirement, or an inventory-coverage gap

CMDBs drift. Fact collection does not — it reports what answered. Using our own
catalog as the ground truth for *existence* and the asset register as the source
for *value* plays each to its strength, and the disagreement between them is
itself a finding worth surfacing on the map.

> Derived values must be **labelled as estimates**. A depreciation figure inferred
> from a class default and a first-seen date is a planning input, not an
> accounting fact, and must never be presented as one in a customer-facing view.
> Values sourced from a real asset register are marked as such; the two must be
> visually distinguishable.

#### 5.9.3 The quadrant — where the CISO and the CFO meet

Support status and capital position interact, and the interaction is more useful
than either alone:

| | **In support** | **Out of support** |
|---|---|---|
| **Not yet depreciated** | Healthy — no action | **Worst case.** Must replace, and you take a write-off to do it |
| **Fully depreciated** | Refresh candidate — plan it | **Best replacement opportunity.** No book value left to lose |

The bottom-right cell is the one that funds a security programme. "This must be
replaced *and* it costs nothing in book value to replace" is an argument a CFO
accepts; "this is out of support" on its own generally is not. Surfacing that
pairing is the practical reason to put capital data on a risk map at all.

#### 5.9.4 Vendor viability — observable signals only

Viability feeds the score through **facts that can be observed**, not judgements
about a company:

| Signal | Source |
|---|---|
| Repository archived or read-only | Source host metadata |
| No release in N months; no commits in N months | Repository history |
| Sole maintainer / bus factor of one | Contributor graph |
| Product discontinuation notice published | Vendor lifecycle source |
| End of support announced with no successor product | Vendor lifecycle source |
| Security-advisory response latency trending up | CVE feed timestamps |

> **Scope boundary.** AAC reports observable facts about a *product's* maintenance
> posture. It renders no opinion on any company's financial health or going-concern
> status, and no such assessment should be inferred from these signals. Where a
> customer holds that view, they can flag a vendor at-risk manually and the flag
> feeds the same score.

#### 5.9.5 How age scores

| Contribution | Where it lands |
|---|---|
| Replacement/migration effort for unsupported and obsolete technology | `technology_lifecycle` debt, at that category's rate |
| Refresh effort for mature and sunset technology | `technology_lifecycle`, weighted by months remaining |
| Support-status multiplier on exposure risk (§5.5) | Applied to `security` risk — unsupported products carry permanent, non-decaying exposure |
| Vendor-viability signals | Risk factor, not effort — it changes urgency, not cost |

This is why folding patch findings into the *existing* categories (§5.3) was the
right call: a host's `security` cell carries what can be fixed, its
`technology_lifecycle` cell carries what must be replaced, and the two together
are the whole picture for that host.

### 5.10 Status

| Capability | Status |
|---|---|
| Compliance-driven debt scoring, rates, domain budgets | ✅ Shipped (AAC) |
| Heat map API + tenant UI, per-host drill-down, coverage/currency valleys | ✅ Shipped (Portal) |
| Product catalog from fact collection (the observational spine) | ✅ Shipped (AAC) |
| `technology_lifecycle` debt category | ⚠️ Declared, nothing feeds it |
| Patch exposure as a debt contribution | ❌ Gap |
| Risk score alongside cost | ❌ Gap |
| Exposure valleys + SLA thresholds | ❌ Gap |
| Cell → worklist drill-down | ❌ Gap |
| Stage 12 recalculation trigger | ❌ Gap |
| Support-status resolution (catalog × vendor lifecycle) | ✅ Shipped |
| Asset-management adapter (capital position) | ❌ Gap |
| Register-drift detection (observed vs registered) | ❌ Gap |
| Vendor-viability signals | ❌ Gap |

The surface exists and is shipped; **what is missing is feeding patch exposure
into it.** That makes this a well-bounded addition to an existing capability
rather than new analytics — the same conclusion the heat map's own
implementation notes reached about bringing AAC debt data into the Portal.

---

### 5.10 Surface lag — the backport ledger

§5.9 answers *what will the vendor still do for you*. This section answers the
question backporting actively hides: **how far behind the surface actually is.**
A fleet can be CVE-green — every scanner satisfied, every VEX filed — while the
distance between what runs and current upstream compounds silently. Every
Stage 4b "backport now" decision writes to this ledger.

Per catalog entry, four lag metrics, all computable from data Stage 1 and §5.9
already collect:

| Metric | Meaning |
|---|---|
| Versions behind | releases between running and current upstream |
| Days behind | age of the running release vs newest |
| Stacked backports | how many loans are outstanding on this component |
| EOL horizon | days until §5.9 stage becomes Sunset/Unsupported |

Each converts to `technology_lifecycle` debt items through the §5.4 effort
model — **no new category, no new machinery**: the shipped heat map, OT/IT/
Sovereignty budget separation, and the portal heat-map UI all light up with lag
debt as soon as the items flow. Projected forward at the observed backport
rate, the ledger becomes a budget-cycle artifact: *"upgrade debt in these two
applications crosses $X by Q3; cheapest sequencing is…"* — the CFO conversation
no scanner can enter, and the honest completion of the VEX story: attest the
CVE closed **and** show the debt the closure method accrued.

**Intent vs as-built.** The application-layer twin of this section's
observe-don't-assume stance is the POM/SBOM distinction: the manifest is
*intent*, the SBOM is *as-built*, and the delta (a dependency present that
nobody declared; a declared component absent) is itself a finding. The portal's
catalog carries the as-built side; SBOM ingestion (CycloneDX + PURL/OSV
matching — NVD's CPE matching silently produces **zero** findings against
application-package SBOMs) extends it below the OS layer. Design:
`AAC_Customer_Portal/docs/design_sbom_catalog_and_patch_decision.md`.


## 6. Worked example — CRITICAL/KEV openssl CVE on RHEL 9 app servers

*Illustrative. Identifiers are representative, not from any customer estate.*

**Setting.** Twelve RHEL 9 application servers behind a load balancer, running
`openssl 3.0.7`. Tier 1: production, redundant, no regulatory overlay.

**Stage 1.** Nightly fact collection refreshes the catalog. `installed_inventory`
holds twelve rows for `openssl 3.0.7`; `inventory_catalog` aggregates them to one
row, `host_count = 12`. The Portal pulls that aggregate — twelve is all it learns.

**Stage 2–3.** CVE-2026-XXXX arrives via NVD, is added to CISA KEV the same day,
and the vendor advisory populates `cve_vendor_remediations` with a Red Hat fix to
`3.0.8` and an RHSA reference. Matching produces a `tenant_cve_matches` row:
`severity=CRITICAL`, `kev_member=true`, `inventory_hits=12`. **This is the
notification.**

**Stage 4.** The customer's AAC runs *AAC - Pull Patch Worklist (Portal)*. The
manifest returns the CVE with its criticality and one fix — package `openssl`,
fixed version `3.0.8`, manager `dnf`, source `vendor_entitled`, install command
`dnf update -y openssl-3.0.8`, plus the RHSA link. Locally, the twelve-host count
resolves to twelve named hosts. Because all twelve are `os_family=RedHat` and the
fix vendor is `redhat`, every row records `fix_match='os_family'` and
`host_resolution='auto'` — no ambiguity to adjudicate.

**Stage 5.** A ServiceNow Change Request is raised through the adapter, linked to
the twelve CIs, carrying the CVE, its KEV status, the fix, and the generated
playbook as an attachment. `remediation_items` mirrors it: submitted by the
platform engineer, approved by the service owner — a different person, enforced
by the database.

**Stage 6.** Policy evaluates tier 1: manifest + config backup, single approval,
serial rollout with one canary.

**Stage 7.** For each host in turn: snapshot taken; the LB adapter disables the
pool member; drain waits for active connections to reach zero.

**Stage 8.** The host pulls `openssl-3.0.8` from the customer's **own Satellite**.
The Portal never touched the bits — it supplied coordinates and an advisory link.

**Stage 9.** The generated playbook runs with `serial: 1`. Backup captures the
package manifest; Patch updates to the pinned version; the canary goes first.

**Stage 10.** A0 confirms `openssl-3.0.8` installed via real version comparison.
A1 confirms the dependent service is active and listening. A2 hits the health
endpoint and gets a 200 with a valid TLS handshake on the new library.

**Stage 11 (success path).** Assurance met. The LB adapter re-enables the pool
member; the host is confirmed receiving traffic and healthy. Repeat for the
remaining eleven, one at a time.

**Stage 11 (failure path).** Suppose host 4's service fails to start after
patching. AI triage classifies it as *service failure after successful patch* —
so R1 (package downgrade) is the appropriate level, not R4 (reimage); it
correlates a prior identical failure on this platform in
`customer_remediation_runs`, and recommends the downgrade with that evidence.
A human authorises. The host is downgraded, service restored, host stays drained,
and the CR is updated with the failure and its evidence. The remaining hosts halt
pending review — `serial: 1` means the blast radius was exactly one host.

**Stage 12.** Fact collection re-runs on the twelve hosts; the catalog rebuilds
showing `openssl 3.0.8`; the Portal re-pulls; matching re-runs and the CVE **no
longer matches** — proof, not assertion. Evidence attaches to the CR, which
closes. Technical debt drops by the closed finding; the coverage heat map
refreshes.

---

## 7. Contrast vignettes — where other classes diverge

### Network device — VyOS router firmware

- **Stage 1:** no package manager. Version arrives via a class-specific collector
  or `manual_product_declarations`.
- **Stage 7a:** backup is running-config export **plus** the alternate image slot
  — the slot *is* the rollback mechanism.
- **Stage 7b:** drain is routing failover — raise OSPF cost or force HSRP/VRRP
  standby, then confirm zero transit traffic.
- **Stage 9:** install to the alternate slot, set next-boot, reboot. Patching is
  a *reboot into a different image*, not a package transaction.
- **Stage 11:** R2 recovery is exceptionally clean — boot the previous slot. Often
  faster and safer than any compute rollback.
- **Watch-out:** the device is frequently the path to itself. Losing management
  connectivity mid-change is the dominant failure mode; console/out-of-band access
  is a precondition, not a nicety.

### Storage — array controller firmware

- **Stage 6:** almost always tier 2+. Blast radius is every host with a LUN.
- **Stage 7b:** drain is path failover — move active paths to the partner
  controller and verify multipath health from the *hosts*, not just the array.
- **Stage 9:** strictly controller-by-controller with a full health check and
  path-restoration wait between. Never both at once.
- **Stage 10:** A3 is mandatory — verify from the consuming hosts that every path
  is restored and I/O is served. Array-side "healthy" is insufficient evidence.
- **Watch-out:** rollback frequently is not possible mid-way. The go/no-go
  decision happens before controller 1, and forward-fix may be the only path —
  which raises the assurance bar in Stage 10 rather than the recovery bar in 11.

### OT — AMI smart-meter population

- **Stage 1:** inventory comes from the head-end system and device management
  (e.g. LwM2M), not package facts.
- **Stage 6:** tier 3. Regulatory scope (NERC-CIP where applicable), safety
  implications, and a population measured in millions.
- **Stage 7b:** **there is no drain.** A meter has no standby and cannot be taken
  out of rotation. Mitigation is staged campaigns, ring-fenced cohorts and
  scheduling — never traffic management.
- **Stage 9:** a firmware campaign over days or weeks, in cohorts, with per-cohort
  soak. Constrained by RF bandwidth, battery budget and field-service capacity.
- **Stage 11:** R4/R5 mean a **truck roll**. Recovery cost is measured in field
  visits, so the assurance bar before the first cohort is far higher than
  anything in IT.
- **Stage 12:** closure is a regulatory evidence artefact, not just a ticket.
- **Watch-out:** the economics invert. In IT, rollback is cheap and testing is
  expensive; in AMI, testing is cheap and rollback is ruinous. Depth allocation
  must reflect that.

---

## 8. Compliance control mapping

### 8.1 How to read this mapping

Three things to hold in mind, because control crosswalks are routinely
over-claimed:

1. **A crosswalk is interpretive, not authoritative.** Frameworks are written in
   prose and do not map cleanly onto each other. The mapping below is a
   reasonable professional reading; **your auditor or assessor decides what
   satisfies a control**, not a vendor document.
2. **This platform *supports and evidences* controls. It does not make anyone
   compliant.** Compliance is a property of an organisation's whole control
   environment — policy, people, process and evidence. AAC automates the
   measurement and the evidence trail for one slice of that.
3. **Control identifiers are version-specific.** ISO renumbered substantially in
   the 2022 revision; NIST CSF renumbered in 2.0; NERC CIP standards carry a
   version suffix. Every reference below states its revision. Check yours
   matches before citing it.

Rows are marked **explicit** where the standard names patch or vulnerability
management directly, and **inferred** where patching is one reasonable way to
satisfy a broader requirement. The distinction matters in an audit conversation.

### 8.2 Canonical patterns this lifecycle follows

This design deliberately follows established public patterns rather than
inventing a proprietary process:

| Pattern | Source | Where it shows up here |
|---|---|---|
| **Enterprise patch management planning** | NIST SP 800-40 Rev 4 | The overall stage model: inventory → identify → prioritise → deploy → verify. Rev 4's framing of patching as *preventive maintenance* is why Stage 6 tiers by risk rather than treating all patches alike |
| **Vulnerability handling process** | ISO/IEC 30111 | Stages 2–5 — intake, triage, remediation decision |
| **Change enablement** | ITIL 4 | Stage 5–6. The three ITIL change types map directly onto the risk tiers (below) |
| **Severity scoring** | CVSS v3.1 / v4.0 | `severity_weight` in the §5.5 risk score |
| **Exploitation probability** | EPSS | A natural future input to §5.5 — probability complements severity |
| **Observed exploitation** | CISA KEV | `kev_multiplier` in §5.5; drives the tightest SLA in §5.6 |
| **Decision-tree prioritisation** | SSVC (CISA / CMU SEI) | The tiering model in Stage 6 is an SSVC-style decision, not a severity threshold |

**ITIL change types map onto the risk tiers** cleanly, which is useful when
talking to a change-management function that already thinks in these terms:

| ITIL 4 change type | AAC tier (Stage 6) | Behaviour |
|---|---|---|
| Standard (pre-authorised, low risk) | Tier 0 | Auto-approved, parallel rollout |
| Normal (assessed and authorised) | Tier 1–2 | Single or four-eyes approval, serial rollout |
| Emergency (expedited authority) | Any tier, KEV-driven | Compressed approval, tightest SLA |

### 8.3 Regulatory clocks — where the SLA thresholds come from

The SLA thresholds proposed in §5.6 are not arbitrary. They are the tightest
common denominator of the clocks these frameworks impose:

| Source | Required timeframe | Revision |
|---|---|---|
| **CISA BOD 22-01** (US federal, KEV catalogue) | KEV entries with CVE ID 2021 or later: **2 weeks**; earlier CVEs: 6 months | 2021, ongoing |
| **NERC CIP-007-6 R2.2** | Evaluate applicable security patches at least once every **35 calendar days** | CIP-007-6 |
| **NERC CIP-007-6 R2.3** | Within **35 calendar days** of evaluation: apply, **or** create a dated mitigation plan | CIP-007-6 |
| **PCI DSS v4.0 §6.3.3** | Critical/high-severity patches within **one month**; others within an appropriate timeframe | v4.0 |
| **FedRAMP** | High **30 days**, Moderate **90 days**, Low **180 days** from discovery | Continuous monitoring requirements |

Two observations worth carrying into a customer conversation:

- **The §5.6 KEV threshold of 14 days is BOD 22-01's clock**, not an invention.
  Even outside federal scope it is the most defensible number available, because
  it reflects *observed* exploitation rather than theoretical severity.
- **NERC CIP-007-6 R2 is a two-stage clock, and the second stage has an escape
  hatch that matters enormously for §5.9.** R2.3 permits a *dated mitigation
  plan* instead of applying the patch. For unsupported technology — where no
  patch will ever exist — the mitigation plan is not a delay tactic, it is the
  only lawful path, and it must be documented and tracked. AAC already encodes
  the R2.2 35-day evaluation clock in its CIP-007 policy.

### 8.4 Stage-to-control mapping

#### NIST SP 800-53 Rev 5

The backbone from which FedRAMP, CMMC and much of NIST 800-171 derive.

| Control | Title | Stage / § | Type |
|---|---|---|---|
| CM-8 | System Component Inventory | Stage 1 | Explicit |
| RA-5 | Vulnerability Monitoring and Scanning | Stages 2–3 | Explicit |
| SI-2 | Flaw Remediation | Stages 4, 8–12 | Explicit |
| SI-2(2) | Automated Flaw Remediation Status | §5 heat map | Explicit |
| SI-2(3) | Time to Remediate / Benchmarks | §5.5 `age_factor`, §5.6 SLA | Explicit |
| CM-3 | Configuration Change Control | Stage 5 | Explicit |
| CM-4 | Impact Analysis | Stage 6 | Explicit |
| CP-9 | System Backup | Stage 7a | Explicit |
| CP-10 | System Recovery and Reconstitution | Stage 11 recovery ladder | Explicit |
| **SA-22** | **Unsupported System Components** | **§5.9** | **Explicit** |
| CA-7 | Continuous Monitoring | Stage 12 | Explicit |

#### NERC CIP-007-6 R2 — Security Patch Management

| Requirement | Substance | Stage / § |
|---|---|---|
| R2.1 | Identify a source or sources for security patches | Stage 2 |
| R2.2 | Evaluate applicability at least every 35 days | Stages 3–4 |
| R2.3 | Within 35 days: apply, or produce a dated mitigation plan | Stages 5–9 |
| R2.4 | Implement the mitigation plan; revisions need CIP Senior Manager approval | Stage 11; §5.9 for unsupported assets |

#### ISO/IEC 27001:2022 (Annex A)

Note the 2022 renumbering — technical vulnerability management moved from
A.12.6.1 (2013) to **A.8.8**.

| Control | Title | Stage / § | Type |
|---|---|---|---|
| A.5.9 | Inventory of information and other associated assets | Stage 1 | Explicit |
| A.8.8 | Management of technical vulnerabilities | Stages 2–4, 8–10 | Explicit |
| A.8.9 | Configuration management | Stage 7a | Explicit |
| A.8.32 | Change management | Stage 5 | Explicit |
| A.8.13 | Information backup | Stage 7a | Explicit |
| A.5.30 | ICT readiness for business continuity | Stage 11 | Inferred |

#### PCI DSS v4.0

| Requirement | Substance | Stage / § | Type |
|---|---|---|---|
| 6.3.1 | Identify security vulnerabilities from recognised sources | Stage 2 | Explicit |
| 6.3.3 | Install applicable security patches within defined timeframes | Stages 8–9 | Explicit |
| 11.3.1 | Internal vulnerability scanning | Stage 12 re-measurement | Explicit |
| 6.5.1 | Change control for system components | Stage 5 | Explicit |
| 12.5.1 | Inventory of system components in scope | Stage 1 | Explicit |

#### SOC 2 — Trust Services Criteria (2017)

| Criterion | Substance | Stage / § | Type |
|---|---|---|---|
| CC7.1 | Detect and monitor for configuration changes and vulnerabilities | Stages 2–3 | Explicit |
| CC7.2 | Monitor for anomalies indicating malicious acts | Stage 12 | Inferred |
| CC8.1 | Authorise, design, develop, test and approve changes | Stages 5–10 | Explicit |
| CC6.8 | Prevent/detect unauthorised software | §5.9 register drift | Inferred |

#### CIS Controls v8

| Safeguard | Substance | Stage / § | Type |
|---|---|---|---|
| 1.1–1.2 | Enterprise asset inventory | Stage 1 | Explicit |
| **2.2** | **Ensure authorised software is currently supported** | **§5.9** | **Explicit** |
| 7.1 | Establish a vulnerability management process | Whole document | Explicit |
| 7.3 | Automated operating-system patch management | Stage 9 | Explicit |
| 7.4 | Automated application patch management | Stage 9 | Explicit |
| 7.5–7.7 | Vulnerability scanning and remediation | Stages 3, 12 | Explicit |

#### NIST Cybersecurity Framework 2.0

Renumbered from 1.1; cited at Function/Category level with subcategories where
they map cleanly.

| Reference | Substance | Stage / § |
|---|---|---|
| ID.AM | Asset management — hardware and software inventory | Stage 1 |
| ID.RA | Risk assessment — vulnerabilities identified and recorded | Stages 2–3 |
| PR.PS | Platform security — software maintained, replaced, removed commensurate with risk | Stage 9, §5.9 |
| RS.MI | Incident mitigation | Stage 11 |
| GV.RM | Risk management strategy — risk tolerance established | Stage 6 tiering |

#### NIST SP 800-171 Rev 2 / CMMC Level 2

| Requirement | Substance | Stage / § |
|---|---|---|
| 3.14.1 | Identify, report and correct system flaws in a timely manner | Stages 2–4, 8–9 |
| 3.11.2 | Scan for vulnerabilities periodically and when new ones are identified | Stage 3 |
| 3.11.3 | Remediate vulnerabilities in accordance with risk assessments | Stages 6, 8–9 |
| 3.4.3 | Track, review, approve and log changes | Stage 5 |

#### IEC 62443 — industrial automation and control systems

**IEC 62443-2-3, *Patch management in the IACS environment*, is the directly
applicable document** and is worth reading alongside this one for OT estates. It
addresses precisely the constraints in the AMI vignette (§7): patching assets
that cannot be taken out of service, campaign scheduling, and asset-owner /
product-supplier responsibility split.

#### Frameworks where patching is inferred, not explicit

Stated plainly rather than over-claimed:

| Framework | Position |
|---|---|
| **HIPAA Security Rule** | Contains no explicit patch-management standard. Patching evidences §164.308(a)(1)(ii)(A) risk analysis, §164.308(a)(1)(ii)(B) risk management, and §164.308(a)(5)(ii)(B) protection from malicious software. **Inferred throughout** |
| **DORA** (EU 2022/2554) | Principles-based. Patching supports the ICT risk-management framework — asset identification, and protection and prevention measures — rather than satisfying a numbered patch control. **Inferred** |
| **SOX** | No IT control requirements in the statute. Patching is evidenced through whichever ITGC framework the auditor uses (commonly COBIT or COSO-aligned change management). **Inferred, and framework-dependent** |

### 8.5 Evidence artifacts by stage

What an assessor typically asks for, and what produces it:

| Evidence request | Produced by | Stage |
|---|---|---|
| "Show me your asset/software inventory" | `installed_inventory`, `inventory_catalog` | 1 |
| "How do you learn about vulnerabilities?" | Feed run history, source configuration | 2 |
| "Show applicability assessment for this CVE" | `tenant_cve_matches` with `inventory_hits` | 3 |
| "Which systems were affected?" | `patch_worklist`, with `host_resolution` provenance | 4 |
| "Show the change authorisation" | Change record + `remediation_items` four-eyes trail | 5 |
| "What was your rollback plan?" | Recovery tier selected, backup reference | 6–7 |
| "Prove the patch was applied" | `customer_remediation_runs` outcome | 9 |
| "Prove it worked" | Validation results at the assurance level required | 10 |
| "Prove the exposure is closed" | Post-remediation re-match showing no result | 12 |
| "Show your unsupported technology and its mitigation plans" | §5.9 support status + mitigation records | §5.9 |
| "Show remediation timeliness against your SLA" | §5.5 `age_factor`, §5.6 exposure valleys | §5 |

The last three are the ones organisations most often cannot produce on demand,
and they are exactly what the heat map makes routine.

### 8.6 The two controls that make §5.9 non-optional

**NIST 800-53 SA-22 (Unsupported System Components)** and **CIS Controls v8
Safeguard 2.2 (Ensure Authorized Software is Currently Supported)** both require
an organisation to know what it runs that is no longer supported, and either
replace it or document compensating controls.

These are commonly failed silently — not because organisations disagree with
them, but because nobody has a reliable list. §5.9 produces that list
automatically from the product catalog, with no asset register required. For an
assessor, "we have no unsupported software" is an assertion; a dated,
system-generated inventory of it with mitigation status is evidence.

### 8.7 What this mapping does not claim

- It does **not** claim implementing this lifecycle makes an organisation
  compliant with any framework.
- It does **not** substitute for an assessor's judgement, a gap assessment, or a
  formal readiness review.
- It does **not** cover the policy, training, governance and organisational
  controls that every framework above also requires.
- Timeframes cited are those published at the revision stated. **Verify against
  the current revision applicable to you before relying on them.**

What it does claim: for the control requirements listed as *explicit*, this
lifecycle produces the measurement and the evidence an assessor will ask for,
automatically and with provenance.

---

## 9. Programme metrics

### 9.1 Every stage emits measurement

Metrics are not a reporting layer bolted on at the end — **each stage emits the
measurement that makes the next one accountable.** If a stage produces no
measurement, it cannot be managed and it will drift.

| Stage | Emits | Feeds |
|---|---|---|
| 1 Baseline | Inventory freshness, host coverage, class completeness | Coverage valleys; confidence in everything downstream |
| 2 Intake | Feed latency, enrichment completeness | Are we learning about CVEs promptly? |
| 3 Match | Findings created, by severity/KEV | Arrival rate (§9.3) |
| 4 Target | Hosts resolved, `fix_match` distribution | Targeting quality — `ambiguous`/`none` rates |
| 5 Authorise | Time-to-approval, rejection rate | Governance friction |
| 6 Tier | Tier distribution | Is tiering discriminating, or is everything tier 2? |
| 7 Prepare | Backup success, drain duration | Change-window sizing |
| 8–9 Acquire/Apply | Execution duration, success rate | **Actuals for §9.4** |
| 10 Validate | Assurance level attained vs required | Assurance debt |
| 11 Branch | Rollback rate, recovery level used | First-pass success (§9.5) |
| 12 Reconcile | Time-to-proven-closed, re-match result | **SLA compliance (§9.2)** |

### 9.2 SLA compliance rate — the primary metric

Given this platform's compliance orientation and the regulatory clocks in §8.3,
**SLA compliance rate is the headline number**: the proportion of findings
remediated within the timeframe their class requires.

```
SLA compliance rate = findings closed within SLA / findings due in period
```

Measured **from fix availability**, consistent with `age_factor` in §5.5 — the
clock starts when action became possible, which is also how CIP-007-6 R2 and
BOD 22-01 count.

Report it in three states rather than as a single percentage, because "87%"
hides whether the remaining 13% is about to breach or already has:

| State | Meaning |
|---|---|
| **Attained** | Closed within SLA |
| **At risk** | Open, inside SLA, but past a warning threshold |
| **Breached** | Open past SLA, or closed late |

Break down by severity class, domain (OT/IT/Sovereignty), asset class and
business unit. The breakdown is what makes it actionable: a 95% aggregate rate
concealing 40% on OT assets is a finding, not a success.

**This is directly reportable against §8.3 obligations** — an assessor asking
"do you remediate critical vulnerabilities within one month" is asking for this
number, sliced to their scope.

### 9.3 Backlog burndown

A rate metric, not a level metric. The level alone tells you nothing about
whether you are winning:

| Measure | Question |
|---|---|
| **Arrival rate** | New findings per period (Stage 3) |
| **Closure rate** | Findings proven closed per period (Stage 12) |
| **Net position** | Closure − arrival. Negative means the backlog is growing |
| **Projected clear date** | At current net rate, when does the backlog reach zero? |
| **Exposure-days** | Sum of open-finding-days over the period — the integral, not the snapshot |

**Exposure-days is the risk measure**, and it is the one to put in front of a
board. A backlog of 100 findings closed within a week is a different risk
posture from 100 findings open for a year, and a level metric cannot tell them
apart.

> **Interpretation guard.** A flat backlog with high throughput is *not* a
> failing process — it means arrival rate equals closure rate. That is a
> **capacity** signal, not a process signal, and the remedy is staffing or
> automation, not more governance. Reporting the two rates separately is what
> makes that distinguishable.

### 9.4 Estimate-versus-actual — the feedback loop

The effort figures in §5.4 are **defaults**. `customer_remediation_runs` captures
what work actually took. Comparing them closes the loop and makes the heat map's
cost projections progressively accurate rather than permanently notional:

```
for each (work_type × asset_class × tenant):
    actual  = median(observed duration from customer_remediation_runs)
    default = §5.4 shipped estimate
    if sample_count >= N:  tenant effort model := actual
    else:                  tenant effort model := default
```

**Design guards, because a naive loop degrades quickly:**

- **Median, not mean.** One pathological run must not move the model.
- **Minimum sample count before overriding.** Below `N`, keep the shipped
  default; a two-sample "calibration" is noise wearing a data costume.
- **Shipped defaults remain the fallback** for work types never yet observed, and
  for new tenants with no history.
- **Version the effort model.** A projection made last quarter must remain
  explicable, which it is not if the model silently changed underneath it.
- **Report variance, not just the point estimate.** High variance is itself the
  finding: work whose duration is unpredictable is *risky* work, and planning
  should widen the range rather than trust a tighter-looking median.

**Two second-order uses**, which are where this earns its keep:

1. **Tier feedback.** Work that consistently overruns its estimate may be
   mis-tiered in Stage 6 — the estimate is a hypothesis about complexity, and
   persistent overrun falsifies it.
2. **Credibility.** A cost projection a customer has seen validated against their
   own history is an argument. One derived from vendor defaults is a brochure.

### 9.5 Supporting metrics

| Metric | Definition | Watch for |
|---|---|---|
| **MTTR by severity** | Mean time from finding to proven closure | Use with SLA rate, never alone |
| **First-pass success rate** | Remediations completing without rollback | Falling rate suggests inadequate pre-change validation |
| **Rollback rate + level used** | How often, and how deep (R1–R5) | Rising recovery *depth* is more serious than rising rate |
| **Assurance attainment** | % reaching the assurance level their tier required | Systematic shortfall means the tier is aspirational |
| **Targeting quality** | `fix_match` distribution | Rising `ambiguous` means vendor data is degrading |
| **Inventory freshness** | Age of newest fact collection per host | Everything upstream depends on it |
| **Register drift** | Observed-not-registered, registered-not-observed (§5.9.2) | Trend matters more than count |

### 9.6 What not to optimise

Metrics become targets and then stop measuring. Three specific traps here:

- **Raw patch count.** Rewards clearing trivial low-severity work while criticals
  age. SLA compliance by severity resists this; a count does not.
- **MTTR alone.** The fastest path to a low MTTR is skipping assurance and
  closing on assertion rather than proof. Always pair it with first-pass success
  and assurance attainment.
- **100% SLA compliance at any cost.** Achievable by rushing changes and eating
  rollbacks. If SLA compliance rises while first-pass success falls, the
  programme is trading stability for a number.

---

## 10. Adapter contracts

### 10.1 Why contracts rather than integrations

Three capabilities in this lifecycle depend on systems AAC does not own:
ticketing, traffic management and asset management. Every customer has different
ones. Specifying **contracts** means providers are swappable, testable with a
stub, and absent-provider behaviour is defined rather than accidental.

**Common requirements for all three adapters:**

| Requirement | Rule |
|---|---|
| **Idempotent** | Re-invoking with the same inputs must not duplicate work. Every create returns a stable external reference |
| **Timeout-bounded** | Every call has an explicit timeout; expiry is a defined outcome, not a hang |
| **Explicit failure semantics** | Distinguish *provider unreachable* from *provider refused*. The first is retryable; the second is a decision |
| **Fail closed** | An adapter that cannot confirm its action stops the lifecycle. Never assume success |
| **Audited** | Every invocation and response is recorded with correlation to the finding and change record |
| **Least privilege** | Scoped credentials, stored per tenant, never in playbook source |
| **Degradable** | Defined behaviour when no provider is configured — usually "require manual confirmation and record it" |

### 10.2 Change-record adapter (Stage 5)

```
create(work)                  -> external_ref
    work: { finding_ids[], assets[], severity, cve_ids[],
            proposed_window, risk_tier, playbook_ref }

state(external_ref)           -> pending | approved | rejected | closed | cancelled

attach(external_ref, artifact)
    artifact: { kind: playbook|backup_ref|test_result|evidence, uri|blob }

close(external_ref, outcome, evidence)
    outcome: completed | failed | rolled_back | cancelled
```

**Semantics:** the lifecycle never proceeds past Stage 5 without `approved`.
`rejected` returns the finding to the backlog with its exposure clock **still
running** — rejection defers work, it does not retire risk. `cancelled` requires
a recorded reason.

| Provider | Notes |
|---|---|
| ServiceNow | Change Request, CI linkage, CAB workflow |
| Jira / Remedy / Ivanti | Same contract |
| **AAP workflow approval** | Native fallback where no ITSM exists — satisfies four-eyes without an external system |
| Manual | Operator confirms and the confirmation is recorded as the artefact |

### 10.3 Traffic-drain adapter (Stage 7b)

```
drain(asset, timeout)          -> drained | timeout | unsupported
verify_quiesced(asset)         -> bool          # zero active work
undrain(asset)                 -> in_service
verify_in_service(asset)       -> bool          # receiving AND healthy
```

**Semantics:** `verify_quiesced` must be checked, never assumed from a successful
`drain` — the distinction between "asked it to stop" and "it has stopped" is
where outages come from. `unsupported` is a **first-class, legitimate return**
(see the AMI case in §7): the lifecycle then requires the tier's compensating
control — scheduling, cohorting — rather than failing.

Undrain and `verify_in_service` are mandatory on **every** exit path, including
failure and rollback. A drained asset left drained is a self-inflicted outage,
and it is the most common operational mistake in automated patching.

| Provider | Drain mechanism |
|---|---|
| F5 / HAProxy / NGINX | Disable pool member, await connection drain |
| AWS ALB/ELB, Azure LB, GCP LB | Deregister target, await deregistration delay |
| OpenShift / Kubernetes | Remove from Service endpoints; readiness probe |
| Router (VyOS, vendor) | OSPF cost increase, HSRP/VRRP standby, BGP AS-prepend |
| Storage | Multipath path failover to partner controller |
| Application | Connection draining, consumer-group rebalance, queue quiesce |
| **None / OT** | Returns `unsupported` — compensating controls apply |

### 10.4 Asset-management adapter (§5.9.2)

```
lookup(asset_identity)  -> { acquisition_date, acquired_cost,
                             class_life, depreciation_method,
                             owner, cost_centre, location }
                         | not_found

reconcile(observed[])   -> { matched[], observed_not_registered[],
                             registered_not_observed[] }
```

**Semantics:** `not_found` is normal, not an error — it triggers the class-default
fallback, and the resulting values must be **labelled as estimates** (§5.9.2).
`reconcile` is the drift-detection call; both of its non-matching lists are
findings in their own right.

| Provider | Notes |
|---|---|
| ServiceNow | CMDB + asset management; primary |
| BMC Helix / Ivanti / Device42 / Lansweeper | Same contract |
| Flat import | CSV/API register for customers with no ITSM |
| **Class defaults** | Always available; no provider required |

### 10.5 Testing adapters

Each adapter ships with a **stub provider** that satisfies the contract with
deterministic responses. Two consequences: the lifecycle is testable end to end
with no customer systems attached, and a customer can dry-run the whole flow
before connecting anything real — which is also the safest way to demonstrate it.

---

## 11. Roles and responsibilities

### 11.1 Why this section exists

The schema already enforces **four-eyes** — `remediation_items` carries
`created_by`, `assigned_to`, `requested_approval_by` and `approved_by`, with a
database CHECK constraint requiring the approver to differ from the submitter.
What the platform *cannot* enforce is whether those two people are the **right**
two. A change submitted and approved by two members of the same team technically
satisfies the constraint and defeats its purpose entirely.

This section names the roles so the constraint carries the meaning it was built
for.

### 11.2 Roles

Generic role names, because titles vary. Map them to your own organisation once
and the rest follows.

| Role | Owns | Notes |
|---|---|---|
| **Asset Owner** | The asset's availability, and the decision to accept residual risk | Accountable for anything that changes the asset's state |
| **Security / Vulnerability Manager** | The finding, its severity classification and its SLA | Accountable for *whether and when* work happens — not for executing it |
| **Platform / Operations Engineer** | Execution | Responsible for the mechanics at nearly every stage |
| **Service / Application Owner** | Whether the service actually works afterwards | The only role that can credibly sign off assurance level A2+ |
| **Change Authority** | Authorisation | A manager, a CAB, or a pre-authorisation policy, depending on tier |
| **Compliance / Audit** | Evidence sufficiency | **Consumes** evidence. Never executes, never approves operational work |
| **AAC Operator** (SaaS side) | Feeds, taxonomy, Portal availability | **Never executes inside a customer environment** — see §1's boundaries |
| **AI Assistant** | Diagnosis and recommendation | **Consulted only.** Never Responsible, never Accountable — see §11.5 |

### 11.3 RACI by stage

**R**esponsible does the work · **A**ccountable owns the outcome (exactly one) ·
**C**onsulted before · **I**nformed after.

| Stage | Asset Owner | Security Mgr | Platform Eng | Service Owner | Change Authority | Compliance |
|---|---|---|---|---|---|---|
| 1 Baseline | C | **A** | R | I | — | I |
| 2 CVE intake | I | **A** | R | — | — | I |
| 3 Match | I | **A** | R | I | — | I |
| 4 Target | C | **A** | R | I | — | — |
| 5 Authorise | C | R | I | C | **A** | I |
| 6 Risk tier | C | R | I | C | **A** | I |
| 7 Prepare | **A** | I | R | C | I | — |
| 8 Acquire | I | C | R | — | — | — |
| 9 Apply | **A** | I | R | I | I | — |
| 10 Validate | C | C | R | **A** | I | I |
| 11 Recover | **A** | C | R | C | I | I |
| 12 Close | I | **A** | R | C | I | C |

**Three placements that are deliberate and often get argued about:**

- **Stage 5–6 accountability sits with the Change Authority, not the Security
  Manager.** Security owns *whether the risk is worth carrying*; the Change
  Authority owns *whether this change may proceed now*. Collapsing them removes
  the second pair of eyes the schema is trying to guarantee.
- **Stage 10 accountability sits with the Service Owner.** The engineer who
  applied the patch is Responsible for running the validation, but should not be
  the sole authority on whether their own change worked. Above tier 1 this
  separation should be real, not nominal.
- **Stage 11 accountability sits with the Asset Owner.** Recovery is a
  risk-acceptance decision — restore, reimage, or run degraded — and that belongs
  to whoever carries the consequence, not to whoever is holding the keyboard at
  02:00.

### 11.4 How RACI shifts by risk tier

Tiering (Stage 6) changes *who* must be involved, not the shape of the flow:

| Tier | Change Authority | Approval | Service Owner | Notes |
|---|---|---|---|---|
| **0** | Pre-authorisation policy | Automatic | Informed | Standard change; no human in the path |
| **1** | Line manager or delegated approver | Single | Consulted | Normal change |
| **2** | CAB or delegated board | **Four-eyes required** | **Accountable at Stage 10** | Normal change, elevated |
| **3** | CAB **plus** regulatory sign-off | Four-eyes + documented window | Accountable | See below |

**Tier 3 and regulated estates.** Where NERC CIP applies, CIP-007-6 R2.4 requires
**CIP Senior Manager or delegate** approval for revisions to a mitigation plan.
That is a named regulatory role, not a generic Change Authority — the adapter's
change record must capture *who* approved in a form that survives audit, and the
role cannot be delegated informally.

### 11.5 The AI's place

AI appears in this lifecycle at Stage 11 (recovery triage, §Stage 11) and
potentially at Stage 6 (tier recommendation). Its RACI position is fixed:

| | AI |
|---|---|
| Responsible | **Never** |
| Accountable | **Never** |
| Consulted | Yes — this is its role |
| Informed | Yes |

An AI recommendation is an **input to a human decision**, recorded alongside the
decision so an assessor can see what was advised and what was chosen. Where the
two differ, that divergence is itself worth keeping — it is the record of human
judgement being applied, which is exactly what a regulator wants to see.

Concretely: AI may recommend "restore from package manifest (R1) rather than
reimage (R4), because this is a service failure after a successful patch and this
platform has failed this way before." A human authorises. The reasoning and the
authorisation are both retained.

### 11.6 Separation of duties — the rules that matter

1. **Submitter ≠ approver.** Enforced in schema. Do not build a service account
   that can do both.
2. **Executor should not be the sole validator** above tier 1. If your
   organisation cannot staff that, record it as an accepted deviation rather than
   letting the RACI quietly say otherwise.
3. **Compliance never approves operational work.** They assess whether the
   evidence is sufficient. An audit function that authorises changes cannot then
   independently assess them.
4. **The AAC Operator never executes in a customer environment.** This is an
   architectural boundary (§1), not a policy preference — the Portal has no path
   to do so.
5. **One Accountable per stage.** Two accountable parties means none.

### 11.7 Anti-patterns

| Anti-pattern | Why it fails |
|---|---|
| Security Manager accountable for execution | They do not own the asset or its availability; accountability without authority |
| Asset Owner absent from the recovery decision | The person carrying the consequence is not in the decision |
| Compliance marked Responsible anywhere | Converts an assurance function into a delivery function; independence is lost |
| Same team supplies both "eyes" | Satisfies the constraint, defeats the control |
| AI recommendation recorded as the decision | Removes the human judgement the record is supposed to evidence |
| No named Service Owner | Nobody can credibly attest the service works, so validation stops at A0 |

---

## 12. Implementation status summary

| Stage | Capability | Status |
|---|---|---|
| 1 | Inventory baseline + catalog + bridge | ✅ Shipped |
| 2 | CVE feed ingest + classification | ✅ Shipped |
| 2 | Vendor remediation (fix) enrichment | ⚠️ Gap — blocks everything downstream |
| 3 | Inventory matching + prioritisation | ✅ Shipped |
| 4 | Patch manifest + per-host worklist resolution | ✅ Shipped |
| 5 | Four-eyes approval state machine | ✅ Shipped |
| 5 | Terminal states (`completed`/`failed`/`rolled_back`/`closed`) | ❌ Gap |
| 5 | Change-record adapter (ServiceNow / Jira / AAP approval) | ❌ Gap |
| 6 | Risk tiering policy (OPA) | ❌ Gap |
| 7a | Backup beyond package manifest | ❌ Gap |
| 7b | Traffic-drain adapter | ❌ Gap |
| 8 | Download path / source classification | ✅ Shipped |
| 9 | Backup→Patch→Validate generation | ✅ Shipped |
| 9 | Pull-based execution + outcome capture | ✅ Shipped |
| 9 | Class-specific apply modules (network/storage/OT) | ❌ Gap |
| 10 | A0 version validation | ✅ Shipped |
| 10 | A1–A4 assurance ladder | ❌ Gap |
| 11 | Automatic rollback (R1–R3) | ❌ Gap |
| 11 | Golden-image recovery (R4) | ⚠️ Machinery exists, not wired to patching |
| 11 | AI-assisted triage | ❌ Gap |
| 12 | Outcome evidence capture | ✅ Shipped |
| 12 | Re-measure and prove closure | ✅ Shipped |
| 12 | Debt / heat-map recalculation | ❌ Gap |
| §5 | Product catalog as observational spine | ✅ Shipped |
| §5 | Patch exposure → debt + risk on the heat map | ❌ Gap |
| §5.9 | Support-status resolution (no customer input required) | ✅ Shipped |
| §5.9 | Asset-management adapter + register-drift detection | ❌ Gap |
| §8 | Control mapping + evidence artifacts per stage | ⚠️ Mapped here; evidence export not built |
| §9 | SLA compliance rate, burndown, exposure-days | ❌ Gap |
| §9.4 | Estimate-vs-actual effort feedback loop | ❌ Gap |
| §10 | Adapter contracts + stub providers | ❌ Gap |
| §11 | Role model + RACI (process, not code) | ✅ Defined here — adopt per customer |

**Honest reading:** discovery, targeting and the download path — Stages 1–4 and
8–9 — are real and verified. Change safety (5–7), assurance depth (10),
recovery (11) and proof-of-closure (12) are largely design. Anyone evaluating
AAC for patch automation today should read this as *strong intelligence and
targeting, with the execution-safety envelope still being built*.

---

## 13. Recommended build sequence

1. **Vendor remediation enrichment** (Stage 2) — nothing downstream produces
   output without it. Highest leverage by a wide margin.
2. ~~**Support-status resolution** (§5.9.1)~~ — **DONE** (`refresh_support_status.yml`). Catalog × vendor lifecycle. Deserved
   to be this high because it is the cheapest meaningful win available: it needs
   **no customer integration and no asset register**, runs entirely against the
   product catalog we already collect, and immediately fills the
   `technology_lifecycle` debt category that has been declared and empty since it
   was defined. It also tells us which `fix_match='none'` rows are permanent
   rather than missing data — which changes what the patch worklist means.
3. **Terminal states + change-record adapter** (Stage 5) — without these no work
   can close, and the ticket is the customer's unit of accounting.
4. ~~**Prove-closure loop** (Stage 12, steps 3–5)~~ — **DONE**
   (`verify_patch_closure.yml`). Converts the platform from asserting to
   demonstrating, and prevents inventory drift.
5. **Assurance ladder A1–A2** (Stage 10) — turns "installed" into "working."
6. **Backup depth + traffic drain** (Stage 7) — the safety envelope for tier 1+.
7. **Automatic rollback R1–R3, then golden-image R4** (Stage 11).
8. **Risk tiering in OPA** (Stage 6) — formalises what by then will be implicit.
9. **Class-specific apply modules** (Stage 9) — network, storage, OT.

---

## 14. Open questions

- **Change-record granularity:** one record per CVE, per host, or per campaign?
  Affects ServiceNow CI linkage and how partial failure is represented.
- **Drain provider discovery:** does the customer declare each asset's traffic
  provider, or is it inferred from inventory?
- **Assurance authorship:** who writes the A2 functional probe — AAC ships
  defaults per service type, or the customer supplies it per application?
- **AI authority boundary:** confirmed as recommend-only for recovery. Should it
  extend to *proposing* a risk tier in Stage 6, still under policy veto?
- **OT closure evidence:** which regulatory artefact formats must Stage 12 emit
  per jurisdiction?

---

## Authorship

Drafted by **Tim Coulter** with **Claude (Anthropic, Claude Opus 5)** as
co-author. Claude produced the initial lifecycle model by inspecting the AAC
platform and Customer Portal implementations against their design documents, and
marked implementation status from the code as it stands on `main` at the date
above. Tim edits and authorises all shipped-state claims.
