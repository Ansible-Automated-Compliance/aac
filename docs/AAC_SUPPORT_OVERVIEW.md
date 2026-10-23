# AAC / Policy-as-Code — Solution Overview for Support

**Version:** v1.0 · **Date:** 2026-09-17 · **Audience:** Red Hat Support engineers
**Authors:** Tim Coulter (Red Hat) with Claude (Anthropic) · *AI-assisted authorship*
**Status:** Draft for review

> **Why you're reading this.** ~5 customers are running Ansible Automated
> Compliance (AAC) / Policy-as-Code in POC. You will see it in the field. This is
> the two-page version: what it is, what you'll see, and **who owns a problem when
> it breaks**. The precise support boundary is in the companion
> `docs/integration/AAC_SUPPORT_SCOPE.md`; the deep architecture is in
> `docs/AAC_EXECUTIVE_ARCHITECTURE.adoc`.

---

## What AAC is, in one paragraph

AAC turns **AAP a customer already owns** into a continuous **compliance-evidence
engine**. It does not lock down or change systems — it **reads** them, evaluates
the facts against policy, and **keeps the verdict as durable audit evidence**. It
is content and tooling *on top of* supported Red Hat products (AAP + its
Policy-as-Code OPA integration), not a standalone product that replaces anything.

The distinctive value: **facts are gathered once and reused across many frameworks**
(CIS, SOC 2, NIST, NERC-CIP, …) to produce distinct scores without re-querying
systems, and every result is **immutable evidence** for auditors — which also lets
it govern actions attempted by AI agents.

---

## The three layers (what you'll see running)

1. **AAP** — the hub. Runs the fact-collection jobs and the Policy-as-Code call. 🔴 *Red Hat product.*
2. **OPA ×3** — the decision engine. Three OPA servers (security / compliance / OT buckets), each evaluating Rego policies. ⚪ *Customer runs the OPA servers; 🔴 the AAP→OPA call is the supported PaC feature.*
3. **PostgreSQL** — the evidence store. Assessment results, history, violations. ⚪ *Customer-provided database (see the Support Scope doc / official AAP DB Scope of Coverage).*

Around those: the **Rego policy library** (🔵 community content), the **playbooks**
(⚪ delivery layer), and optionally a **portal / Grafana / MCP / EDA** (⚪ all
customer-managed solution glue).

---

## How an assessment works — five steps (the narration)

1. **Collect** — AAP runs a **read-only** job that reads configuration from the systems (a structured inventory of security settings — nothing is changed).
2. **Send** — the job posts those facts as JSON to an OPA server (one of three, by framework).
3. **Decide** — OPA runs the Rego policies and returns a scored report: which controls passed, which failed, and why.
4. **Store** — results land in PostgreSQL as a permanent record (host, framework, score, violations, timestamp).
5. **Report** — Grafana dashboards / exported PDF-DOCX read from that database for auditors and executives.

*Timing:* a single-framework assessment takes seconds to minutes by estate size —
this is **not** the sub-2-second AAP Policy-as-Code pre-launch gate.

---

## How the policy library stays current (a question you will get)

Fresh policies are load-bearing — an assessment against a stale benchmark is
worse than no assessment. Two scheduled AAP jobs keep the library current, and
you can point at their run history as the receipt:

1. **Standards Update Sweep** (weekly) — automated change-detection for
   watchable frameworks and benchmarks listed in
   `STANDARDS_UPDATE_REGISTRY.md`: each non-manual upstream page is fetched,
   content-hashed (noise-resistant), and compared against the last run's
   hash in the evidence database. A change opens a deduped GitHub issue in
   the policy-library repo titled `sweep: <framework> watch page changed` —
   the signal that a human reviews the upstream and updates the modules.
   This is change *detection*, not auto-update: policy content only changes
   through a reviewed PR.
2. **OPA policy refresh** (weekly) — reloads the three OPA servers from the
   library so the decision engines never drift from the repo. The loader
   fails loud on compile errors and prunes removed policies every run.

A weekly status report (updates found, blockers, suggestions) goes to the
maintainers. The watch list lives in `ansible/vars/standards_watch.yml` —
when the registry gains a framework, the watch list gains an entry in the
same PR.

---

## The one thing to remember — the support triage ladder

**When something fails, the first broken layer owns the problem.** Layers 1-2 are
standard Red Hat support; 3-6 are customer / content:

1. Is **AAP** healthy (controller API, execution capacity)? → **Red Hat**
2. Did the job reach an **execution environment**? → **Red Hat**
3. Is **OPA reachable** and healthy? → **Customer platform** (customer-run OPA server)
4. Are the **correct policies loaded**? → **Customer compliance engineering** (content)
5. Did **PostgreSQL accept** the write? → **Customer DBA**
6. Is the **assessment result correct** against the benchmark? → **Policy / content team** (content)

(Portal / dashboard / MCP / EDA behavior → customer solution layer.)

---

## Use cases you may hear about (the demo catalog)

These are the scenarios customers evaluate — each is a narrated walkthrough in the
`aac-demos` repo:

- **Golden-image drift** — config/SELinux drift detected → policy verdict → auto-rollback or hold, with a ticket.
- **Mythos patch** — AI-scale vulnerability discovery → policy-governed remediation → **proven closure**.
- **NERC-CIP + AMI** — utility compliance (CIP-002…CIP-015 + smart-meter/AMI).
- **Digital Sovereignty**, **NCSC CAF**, **CIS Microsoft 365**, **Comply** (policy-as-code across the code lifecycle vs Sentinel).

---

## Where to send people / find more

- **Support boundary (who owns what):** `docs/integration/AAC_SUPPORT_SCOPE.md`
- **Deep architecture + FAQ:** `docs/AAC_EXECUTIVE_ARCHITECTURE.adoc`
- **Honest status (field teams):** `docs/AAC_HONEST_STATUS_AND_POSITIONING.md`
- **Demo catalog + run order:** `aac-demos/demos/README.md`
