# AAC — What It Is, What It Isn't, and What to Say

**Version:** v2.1  
**Date:** 2026-08-28  
**Audience:** Red Hat field teams representing AAC at a customer  
**Purpose:** Answer the questions a customer asks after a rough install, without overclaiming — or underclaiming  
**Authors:** Tim Coulter (Red Hat) with Claude (Anthropic)

---

## 1. Why this document exists

A customer installed AAC, hit problems, and asked four fair questions:

> *Is this thing going to be like that all the time?*
> *Do I have to keep fixing problems manually?*
> *Is this going to be supported by Red Hat?*
> *Is this ready for my production environments?*

Those questions have honest answers, and the honest answers are **better than an evasive
version of them.** This document gives them plus the language to use, so nobody in the field
improvises a position they cannot defend later.

**The person in the room wears a Red Hat badge.** If they say "supported" where it isn't
true, their credibility spends first, then Red Hat's. If they say "not supported" where it
*is* true, they give away the strongest part of the story. Both errors are avoidable, and
this document exists to avoid both.

---

## 2. The honest one-liner

> **The architecture is a supported Red Hat product. The policy content and the delivery
> tooling are not.**

AAP ships **Policy as Code** — OPA as the decision engine, Rego as the policy language, AAP
as the invoker, the OPA v1 data API as the interface, configured through first-class
controller settings. That is Red Hat's own productized design, and AAC is built on exactly
it.

What Red Hat does **not** ship is a policy library. It ships the enforcement mechanism and
a handful of example policies. **AAC is the library.** That is the same relationship as
Ansible and your playbooks: Red Hat supports the engine, you own the content.

---

## 3. What is supported, and what is not

Be precise about this table. The middle row is the one people get wrong in both directions.

| Layer | Status | Who supports it |
|---|---|---|
| **AAP Policy as Code** — OPA integration, Rego evaluation, controller settings, the decision contract | **Supported product feature** since AAP 2.5.5 | **Red Hat**, with SLAs and errata |
| Ansible Automation Platform, OpenShift, RHACS, Compliance Operator, Private Automation Hub | **Supported products** | **Red Hat** |
| **AAC Rego policy library** — CIS, NERC-CIP, ISO, NIST content | Open source, actively maintained, well tested — **content on a supported engine** | Customer / community, not a Red Hat entitlement |
| **AAC playbooks, installers, portal** | Reference implementation | Customer, not a Red Hat entitlement |

**The distinction that matters:** *"AAP calls OPA to evaluate Rego"* is not an
idiosyncratic pairing somebody invented. It is Red Hat's own product architecture. Before
AAP 2.5.5 a reviewer could reasonably have asked whether that combination was unusual.
Since 2.5.5, the architectural question is settled by Red Hat's product decision.

So the honest answer to *"who supports this?"* is **not** "nobody." It is: **the engine and
the platform are supported; the content and the packaging are yours** — which is the normal
arrangement for every Ansible customer on earth.

---

## 4. An honest split — the halves are not equal

Presenting AAC as uniformly mature is what creates the credibility problem. Being precise is
more persuasive than smoothing it over.

### 4.1 The policy layer — product-grade content on a supported engine

| Measure | Reality |
|---|---|
| Automated tests | **540+**, run on every change (545 at pin `75bb5f1`, 2026-08-28 — count with `opa test . --ignore .github`) |
| CI guards | Control IDs verified against each benchmark's own enumeration; coverage buckets must partition the standard or CI fails |
| Design posture | Fail-closed throughout — an absent fact reports "could not be evaluated", never a pass |
| Self-assessment | The project measured defects in its **own** evidence corpus and published them |
| Runs on | AAP's supported Policy as Code surface |

This half stands up to scrutiny. It is more rigorously tested than plenty of shipping
software, and the willingness to publish defects in its own data is unusual.

### 4.2 The delivery layer — a demo harness

| Measure | Reality |
|---|---|
| Playbooks | **221** |
| Tests covering them | **9** |
| Playbooks carrying demo-environment hostnames | **37** |
| Playbooks with lab IPs in non-lab paths | **8+** |
| CI that tests a playbook | **none** |
| Release gate on the install path | **none** |

**This is the half a customer installs.** It was built to demonstrate an approach and it
shows. The known-issue-documented-in-a-runbook-for-months pattern is the tell: with no
release gate, a known break gets written down instead of fixed.

**A customer's install experience comes from the weaker half.** That is why the install went
badly, and it says nothing about the policy engine's quality.

---

## 5. The four questions — answers you can use

### *"Is this thing going to be like that all the time?"*

> "The install tooling has no automated testing behind it today, so regressions can reach
> you. That's being fixed — the policy layer already has 540+ tests and CI gates, and the same
> discipline is being extended to the install path. Until it is, expect friction on install
> and expect us to work through it with you."

Do not say "no, that was a one-off." It probably wasn't.

### *"Do I have to keep fixing problems manually?"*

> "Some, for now — and where that's true it should be us doing it with you, not you alone.
> The recurring ones are known and being closed at the root rather than documented as
> workarounds. I won't tell you they're all gone when they aren't."

### *"Is this going to be supported by Red Hat?"*

**Answer it in two parts, because it has two answers.**

> "The architecture is. Ansible Automation Platform ships Policy as Code — OPA evaluating
> Rego, invoked by AAP, configured through supported controller settings. That's a Red Hat
> product feature with the SLAs and errata you'd expect, and it's exactly what this runs on.
>
> What Red Hat doesn't ship is a policy library — it ships the engine and some examples.
> This is the library, and the installers around it. Those aren't a Red Hat product today,
> so there's no support entitlement for that layer. It's the same relationship you already
> have with Ansible: Red Hat supports the platform, you own your content."

That is both honest and considerably stronger than "no." Do not overstate it into a support
entitlement that does not exist, and do not understate it into "unsupported project."

### *"Is this ready for my production environments?"*

> "The engine underneath is production software you may already be running. The policy
> content is well tested. The packaging around it isn't production-ready — it's ready to
> prove the approach in your environment and define what a production deployment needs. If
> you want this in production, let's talk about what your team owns."

---

## 6. What is being fixed, and what that does not fix

**Underway now:**

- Removing hardcoded lab IPs and demo-environment hostnames from playbooks and installers.
  **37 playbooks** carry demo host names and **8+** carry lab IPs on paths a customer runs.
  Several were also *stale* — pointing at endpoints that moved when the lab migrated, so they
  would fail even at home. Every one reads to a customer as *"this was never meant for me."*
- Closing recurring operational failures at the root rather than documenting the workaround.

**What that does not fix:** none of it changes the support entitlement for the AAC layer.
Cleaning up the install removes the *evidence* that prompts the support question. The answer
in §5 stays the same.

---

## 7. The decision that has to be made

Three honest positions. Pick one deliberately rather than drifting.

| Option | What it means | Cost |
|---|---|---|
| **Content on a supported engine** *(recommended)* | AAP Policy as Code is the supported product; AAC is the policy library and reference implementation the customer's team owns | One clear conversation. Survives contact |
| **Productization** | Owner, funding, release management, test coverage on the delivery layer, a support model | A programme, not a sprint |
| **Narrow the offer** | Lead with Policy as Code, Compliance Operator, ACS and AAP — all supported — and treat AAC purely as content | Smallest claim, strongest footing |

**Recommendation: take the first position now** and decide on productization deliberately.
It is accurate, it is defensible under scrutiny, and it does not require anyone to overstate
the packaging.

---

## 8. What not to do

- **Do not** claim a support entitlement for the AAC policy library or installers.
- **Do not** answer "is it supported?" with a flat no — that gives away the Policy as Code
  architecture, which genuinely is supported.
- **Do not** present the 540+-test policy layer as evidence the installer is equally mature.
  Different halves.
- **Do not** promise a fix timeline that depends on one person's evenings.
- **Do not** demo against the lab and imply a customer install behaves the same way. It
  demonstrably does not.

---

## 9. What is genuinely worth selling

Being honest about the gaps does not mean there is little here. There is:

- **The architecture is Red Hat's own.** AAC chose OPA + Rego + AAP before Red Hat shipped
  Policy as Code, and Red Hat then shipped that same combination. That is validation, and
  it is worth saying plainly.
- **A complete, executable model of what compliance evidence requires** across many
  frameworks — for NERC-CIP alone, 14 standards and 233 named input fields, each mapped to
  the source system that must supply it. Nobody hands a utility that.
- **Detection and correction on one platform**, under one change record, with the evidence
  of both in one series — hard to buy anywhere else.
- **An evidence discipline that survives an auditor**: attribution, policy provenance,
  fail-closed, and a project willing to publish the defects in its own data.

Sell that. It is real, it is differentiated, and none of it requires overstating the
packaging.

---

## Revision history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-08-28 | Written after a customer install surfaced four direct questions about supportability and production-readiness. |
| **v2.1** | 2026-08-28 | Corrected the test count, which was stated as 492 and is 545 at the pinned commit, and tied it to a command so it can be rechecked rather than trusted. A document whose whole argument is "be precise about what is and isn't true" cannot carry a stale number. |
| **v2.0** | 2026-08-28 | **Corrected the support position, which v1.0 understated.** AAP ships **Policy as Code** — OPA evaluating Rego, invoked by AAP, configured through supported controller settings — as a product feature since 2.5.5. The architecture AAC runs on *is* supported Red Hat product surface; what is not supported is the policy *content* and the installers. v1.0's flat "the AAC layer is not supported" gave away the strongest part of the story. §2, §3, §5 and §9 rewritten; the delivery-layer assessment in §4.2 is unchanged and still stands. |
