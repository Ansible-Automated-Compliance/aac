# AAC / Policy-as-Code — Solution Video Script (for Support enablement)

**Version:** v1.0 · **Date:** 2026-09-17 · **Audience:** presenter (Tim); output for Red Hat Support
**Authors:** Tim Coulter (Red Hat) with Claude (Anthropic) · *AI-assisted authorship*
**Status:** Draft for review — **script/storyboard only** (Tim records)

> **Format.** ~12-15 min screen-recorded walkthrough for global Support (async, so
> no live meeting needed). Each beat = **[on screen]** + **[say]**. Live demo
> segment uses the **Mythos Patch** cycle (validated end-to-end on the lab);
> **golden-image drift** is the drop-in alternate (noted at Beat 4). Pre-flight
> `/aac-verify` (GO) and, for Mythos, run the **"AAC - Refresh Inventory Catalog
> (patch intelligence)"** job template — launch by NAME, never a template ID
> (IDs shift) — before recording so verify passes.

---

## Beat 1 — What this is (≈90s)
**[on screen]** Title slide → the one-line boundary from `AAC_SUPPORT_SCOPE.md`.
**[say]** "This is Ansible Automated Compliance — Policy-as-Code. It turns AAP a
customer already owns into a continuous compliance-evidence engine. It does not
lock systems down — it **reads** them, evaluates against policy, and keeps the
verdict as durable audit evidence. Red Hat supports the engine and the platform;
the customer owns the content and the delivery tooling. Keep that split in mind —
it's the whole point of this video."

## Beat 2 — The architecture (≈2 min)
**[on screen]** The 3-layer diagram (`docs/integration/aac_architecture.svg`),
color-coded: 🔴 AAP + PaC feature · ⚪ OPA servers + PostgreSQL · 🔵 Rego library.
**[say]** Walk the five steps: "**Collect** — AAP reads config, read-only.
**Send** — facts go as JSON to OPA. **Decide** — OPA runs Rego, returns a scored
report. **Store** — results land in PostgreSQL as permanent evidence. **Report** —
dashboards and PDF/DOCX read from that database." Note: facts gathered once, reused
across many frameworks.

## Beat 3 — Where it lives (≈1 min)
**[on screen]** AAP controller UI: the job templates and the OPA services;
Grafana tile.
**[say]** "In the field you'll see AAP job templates, three OPA servers, a
PostgreSQL evidence store, and optionally a portal or Grafana. The customer runs
the OPA servers and the database; Red Hat supports AAP and the Policy-as-Code call
into OPA."

## Beat 4 — Live use case: Mythos governed patch (≈5-6 min)
**[on screen]** Automation Orchestrator → workflow **"AAC - Mythos Patch (governed
+ OPA, lab AAP)"**. Launch with `target_hostname=LAB_UTIL_HOST`,
`cve_ids=CVE-2026-90008`, `dry_run=yes`.
> **Which workflow — read this before recording.** The beats below describe the
> **Automation Orchestrator** governed variant, which has the OPA gate **and** an
> approval node. It is *not* the AAP-native **"AAC - Mythos Patch Lifecycle"**
> (seeded by `ansible/playbooks/seed_mythos_patch_workflow.yml`), which runs
> change-record → backup → drain → install → assurance → undrain → verify → close
> with **no approval node**. Record whichever your audience actually runs; the
> "govern-the-AI, human-approves" story here is specifically the AO variant.
**[say / narrate the nodes as they run]:**
1. **Identify** — "It first identifies exactly which components are affected — a catalog match against live inventory, not a guess."
2. **AI triage** — "An AI agent triages the patch — severity, blast radius, recommendation. The agent **proposes**; it does not decide."
3. **OPA gate** — "Policy decides. OPA takes the facts *and* the agent's recommendation and returns a governed verdict. This is the enforcement point — the AI can't act outside what policy allows."
4. **Route → approval** — workflow pauses. **[on screen]** approve "Approve production patch." **[say]** "High-impact → a human approves. The human decides, not the machine."
5. **Patch → verify closure** — completes. **[say]** "Install, then **verify closure** — and notice the verify step refuses stale inventory; it protects against false 'all clear'. Every step is evidence: what was affected, what policy decided, who approved, proof of closure."
> *Alternate (drop-in):* golden-image drift demo — drift → OPA verdict → auto-rollback/hold → ticket. Same "AI/automation proposes, policy disposes, evidence throughout" arc.

## Beat 5 — The support boundary (≈2 min)
**[on screen]** The **support triage ladder** (from `AAC_SUPPORT_OVERVIEW.md`).
**[say]** "When something breaks, walk the layers — the first broken layer owns it.
AAP and the execution environment are Red Hat. OPA reachability, the loaded
policies, the database write, and whether the result is *correct against the
benchmark* are customer and content. Same for the portal, dashboards, MCP, and EDA
rulebooks — customer-managed solution layer." Point to `AAC_SUPPORT_SCOPE.md` for
the component-by-component table and the official AAP Database Scope of Coverage.

## Beat 6 — Close (≈45s)
**[say]** "Bottom line: machine-speed where it's safe, human-governed where it
matters, audit evidence throughout — running on supported Red Hat products, with a
clear line between what Red Hat supports and what the customer owns. The Support
Scope doc and this overview are your references; raise anything to the BU through
the usual channel."

---

## Pre-record checklist
- `/aac-verify` → GO (or the parent's health-check equivalent).
- **Mythos:** run the **"AAC - Refresh Inventory Catalog (patch intelligence)"** job template first — by name, not an ID (IDs shift) — since verify enforces a 24h inventory-freshness guard.
- Use `dry_run=yes` (safe — no real patch).
- Confirm no lab-only IPs or secrets are on screen; use service-DNS hostnames, not raw IPs.
