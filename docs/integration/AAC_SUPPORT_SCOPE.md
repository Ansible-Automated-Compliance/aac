# AAC / Policy-as-Code — Support Scope

**Version:** v1.0 · **Date:** 2026-09-17 · **Audience:** Red Hat Support & BU, and (customer-facing sections) the customer
**Authors:** Tim Coulter (Red Hat) with Claude (Anthropic) · *AI-assisted authorship*
**Status:** Draft for Support-team review

> **Purpose.** Set clear, honest expectations about what Red Hat supports and what
> the customer owns in an Ansible Automated Compliance (AAC) / Policy-as-Code
> deployment — so the customer knows their responsibilities up front, and so
> Support can recognize the configuration in the field and route an issue to the
> right owner. A large portion of an AAC deployment is **customer-managed and
> customer-responsible by design**; this document draws that line precisely.

---

## 1. The boundary in one line

> **Red Hat supports the engine and the platform** — Ansible Automation Platform
> and its Policy-as-Code integration with Open Policy Agent (OPA). **The customer
> owns the content and the delivery layer** — the Rego policy library, the
> playbooks and installers, the compliance database schema and its data, the
> portal, and the dashboards.

This is the normal Ansible arrangement: Red Hat supports the platform; a customer's
own playbooks and content are the customer's. AAC does not change that contract — it
is content and tooling *on top of* supported products.

**Authoritative Red Hat support definitions — link the official `access.redhat.com` pages; do not paraphrase them:**
- Red Hat Ansible Automation Platform — *Scope of Coverage* — **[official URL — TODO: paste the exact `access.redhat.com` link before this goes external]**
- Red Hat Ansible Automation Platform — *Database Scope of Coverage* (reproduced in §4) — **[official URL — TODO: paste the exact `access.redhat.com` link]**

For anything Red Hat officially covers, this document points **to** those pages.
It speaks in its own voice only for the AAC-specific solution layer, which is
explicitly customer-managed.

---

## 2. Component-by-component coverage

Legend: 🔴 **Red Hat supported product surface** · 🔵 **AAC content (Galaxy/community model — see §6)** · ⚪ **customer infrastructure / customer-managed solution glue**

| Component | Coverage | Basis |
|---|---|---|
| 🔴 RHEL | **Supported** | Standard product support |
| 🔴 AAP — controller, execution environments, job templates, credentials | **Supported** | Standard product support |
| 🔴 **Policy-as-Code enforcement feature** (AAP → OPA decision contract) | **Supported product feature** | GA in **AAP 2.5.5** — Red Hat's own product architecture |
| 🔴 OpenShift, RHACS, Compliance Operator, Private Automation Hub (where used) | **Supported** | Standard product support |
| 🟡 **OPA — invoked from AAP** (the productized PaC *pattern*) | **Supported capability** | The pattern Red Hat productized; see the two-part note in §5 |
| ⚪ **OPA server instances** (the OPA binary/servers themselves, ×3 buckets) | **Customer-provided** | Red Hat does not ship or run the OPA server (§5) |
| 🔴/⚪ **PostgreSQL engine** | **Per the official AAP Database Scope of Coverage** (§4) | The AAC compliance DB is a *customer-provided database* in that scheme |
| ⚪ AAC **compliance/evidence database** — schema, `compliance_results` data, retention | **Customer-managed** | The AAC solution layer, not an AAP platform DB (§4) |
| 🔵 **AAC Rego policy library** (CIS, NERC-CIP, ISO, NIST, … — count at the pinned submodule SHA) | **Community content** | Open source, actively maintained, well tested — content on a supported engine, not an entitlement (§6) |
| ⚪ **AAC playbooks / installers** (the delivery layer) | **Customer-managed** | Reference implementation; platform-team owned, like any customer's own playbooks |
| ⚪ **AAC portal** | **Customer-managed** | Reference implementation (see the reconciliation note below) |
| ⚪ **MCP server** (`aap-mcp`, live tools for the AI agent) | **Customer-managed** | Solution glue; not a Red Hat entitlement |
| ⚪ **EDA rulebooks / webhook enforcement** (e.g. golden-image drift) | **Customer-managed** | Delivery layer; EDA the *product* is supported, the AAC *rulebooks* are content |
| ⚪ Grafana | **Customer-managed / optional** | Presentation only, never a dependency of correctness — replaceable by any SQL dashboard tool |
| ⚪ OT / smart-meter simulators | **Customer-managed** | Demo/lab tooling |

> **Portal status — one answer.** The portal is a **reference implementation
> (customer-managed)** for support purposes. Some portal features are described
> elsewhere as "shipped" because they have run in customer demos; that describes
> *maturity of the demo*, not a Red Hat support entitlement. Treat the portal as
> customer-owned.

---

## 3. The middle row people get wrong in both directions

The one row that is misread — in both directions — is the **PaC feature itself**.

- It is **not** an idiosyncratic pairing somebody invented. *"AAP calls OPA to
  evaluate Rego"* is Red Hat's own product architecture, GA since **AAP 2.5.5**.
- It is **not** "everything about OPA is supported." Red Hat supports the
  *integration and the decision contract*; it does not ship or run the *OPA server*
  (§5).

So the honest answer to "who supports this?" is neither "nobody" nor "all of it."
It is: **the engine and the platform are supported; the content and the packaging
are the customer's.**

---

## 4. PostgreSQL — per the official AAP Database Scope of Coverage

AAC stores compliance evidence in PostgreSQL. **The database engine's support is
governed by Red Hat's official *Ansible Automation Platform Database Scope of
Coverage*** — quoted below verbatim; link the official page rather than relying on
this copy. AAC's compliance/evidence database is an **external, customer-provided
database** in that document's terms (it is a separate instance from the AAP
platform database), so the **"Customer-provided or configured database"** column is
the one that applies.

> **Database, installed with Ansible Automation Platform** (embedded — on the
> controller/hub/separate node, using Red Hat PostgreSQL packages, as part of the
> AAP install):
>
> | Covered by Red Hat | Not Covered by Red Hat |
> |---|---|
> | Installation | Replication configuration for HA or DR |
> | Upgrades as part of a full platform upgrade | HA/DR operation |
> | Backup and restore | Upgrades independent of platform upgrades |
> | Performance diagnosis and potential tuning | |
>
> *Upgrading or customizing the AAP-installed database manually, outside a full
> platform upgrade, renders it "customer provided" and limits supportability as
> such.*
>
> **Customer-provided or configured database** (external — on bare metal, VM,
> container, or a cloud-hosted service; customer creates the DBs, users,
> permissions before installing AAP):
>
> | Covered by Red Hat | Not Covered by Red Hat |
> |---|---|
> | Platform configuration and platform operation connected to the database | Replication configuration for HA or DR |
> | Backup and restore (for Postgres versions matching the Platform) | HA/DR operation |
> | Commercially reasonable performance diagnosis and potential tuning | Software and version upgrades |
> | | Customized configurations and hardening |
>
> *It must be a PostgreSQL-compatible database of the appropriate version for the
> installed AAP version, in the same data center/geography as AAP.*

**What this means for AAC, in our own words (the customer-managed part):**
- The **PostgreSQL engine** carries the coverage above.
- The **AAC compliance schema, the `compliance_results` evidence data, retention,
  the fact-collection playbooks that populate it, and any AAC-specific DB tuning or
  hardening are customer-managed.** They are the solution layer, not a supported
  Red Hat deliverable.
- Because AAC's DB is a *customer-provided database*, **HA/DR and DB
  software/version upgrades are the customer's responsibility.**

---

## 5. OPA — the two-part distinction (state both, plainly)

- The **PaC pattern — OPA invoked from AAP** — is a **supported capability** (the
  productized AAP 2.5.5 feature).
- The **OPA server itself** (the binary and the running server instances AAC
  stands up, one per bucket) is **customer-provided** — Red Hat does not ship or
  run the OPA server. This is true under the productized PaC pattern too.

Said together so it doesn't read as a contradiction: **Red Hat supports the *call*
from AAP into OPA and the decision contract; the customer runs the *OPA server*.**

---

## 6. The Rego policy library — the Galaxy / collections model

The AAC Rego library (`rego_policy_libraries`, public, Apache-2.0) is **community
content on a supported engine**, exactly analogous to Ansible collections:

| Tier | Analogy | Support | Where AAC's library sits |
|---|---|---|---|
| **Community** | Ansible Galaxy | Community — no entitlement | **The policy library today** — public, open source |
| **Validated** | Automation Hub | Red Hat tested against a matrix | A curated subset could move here |
| **Certified** | Automation Hub | **Red Hat supported, with SLAs** | A future certified policy library |

The right question for the BU is not *"can AAC be supported?"* but **"which tier
does this content belong in, and what is the bar for the next tier up?"** One
honesty caveat to size: compliance content carries a **currency treadmill** (CIS,
NERC-CIP, and other frameworks reissue) that ordinary collections do not — a
certified tier would need a refresh cadence.

*(Adoption/vision context to confirm before printing externally: the public
library sees meaningful community pull-through, and the long-term vision is for the
Business Unit to own the repository — the Galaxy→Certified path above.)*

---

## 7. Support triage ladder — who owns the problem

When something is wrong, walk the layers; **the first failing layer owns the
problem.** Layers 1-3 are standard Red Hat support; 4-7 are customer / content.

1. Is **AAP** healthy? → **Red Hat**
2. Did the job reach an **execution environment**? → **Red Hat**
3. Is **OPA reachable** and healthy? → **Customer platform** (customer-run OPA server)
4. Are the **correct policies loaded**? → **Customer compliance engineering** (content)
5. Did **PostgreSQL accept** the write? → **Customer DBA** (per §4)
6. Is the **assessment result correct** against the benchmark? → **Policy / content team** (content)
7. Is a **portal / dashboard / MCP / EDA** behavior wrong? → **Customer** (solution layer)

---

## 8. What "fully supported" (a certified tier) would require

To set expectations honestly about the path from here: moving the AAC content into
a **supported/certified tier** would require bounded scope, semver + signed
releases, a published lifecycle policy, **a named owning team with a defect SLA
(the hardest item)**, CI gates, a support matrix, a diagnostics bundle, a CVE
process, and license reconciliation. That is a BU productization decision, not the
state today.

---

## 9. Setting customer expectations

- Say up front, in writing, **which components are Red Hat-supported and which are
  customer-managed** for their specific engagement (the per-customer POC template
  captures this per account).
- The customer is **responsible** for the OPA servers, the compliance database
  (HA/DR, upgrades, hardening), the policy content they run, and the delivery
  playbooks/portal/dashboards.
- Red Hat's goal remains **customer success** — Support can help contextualize,
  guide, and raise issues to the BU even where a component is customer-managed.
  This document exists so those conversations start from a shared, accurate line.

---

## Sources (link the official ones; do not reword)

- Red Hat Ansible Automation Platform — *Scope of Coverage* (official) — **[access.redhat.com URL — TODO]**
- Red Hat Ansible Automation Platform — *Database Scope of Coverage* (official; §4) — **[access.redhat.com URL — TODO]**
- `docs/AAC_HONEST_STATUS_AND_POSITIONING.md` — the canonical supported/unsupported spine
- `docs/integration/AAC_PAC_SUPPORT_BRIEFING.md` — the Support-meeting deck (coverage table, triage ladder, color legend)
- `docs/AAC_EXECUTIVE_ARCHITECTURE.adoc` — support matrix + triage ladder
- `docs/frameworks/REGO_POLICY_LIBRARY.md` — the library-as-consumable / Galaxy model
