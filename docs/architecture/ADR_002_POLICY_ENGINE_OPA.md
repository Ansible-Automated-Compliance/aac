> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: SPLIT-PORTSx2, HOST:8181x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# ADR-002: Policy Engine — AAC Standardizes on Open Policy Agent (OPA)

**Status:** Accepted
**Version:** v1.1
**Date:** 2026-07-29
**Deciders:** Tim Coulter (architect / maintainer)
**Authors:** Tim Coulter; Claude (Anthropic) — co-author
**Supersedes / relates to:** ADR-001 (Core Facts & Sidecar Architecture)

---

## 1. Context

Ansible Automated Compliance (AAC) uses **Open Policy Agent (OPA)** as its policy
**decision engine for compliance assessment**. The pattern throughout the platform is:

```
Managed systems → Ansible (fact collection) → OPA (policy evaluation) → PostgreSQL (history) → Reports
```

Concretely, AAC posts a JSON document of collected facts to an OPA data endpoint and
receives a **structured compliance report** back:

- `POST http://<host>:8181/v1/data/cis_rhel9/compliance_assessment` → per-control results, score, violations
- Three purpose-specific OPA containers: **:8181 security** (CIS, NIST, STIG), **:8182 compliance**
  (ISO, SOC2, PCI, SOX, FISMA, sovereignty, …), **:8183 OT** (NERC-CIP, AMI, IEC 62443)
- A **shared Rego policy library of 510 policy files** (587 including tests) spanning 50+ frameworks, versioned as a git submodule

**Origin (2022).** AAC's policy-as-code opportunity began with a proof-of-concept comparison at a
large enterprise (PepsiCo): **HashiCorp Sentinel satisfied 3 of 5 proof points; AAP + OPA satisfied
all 5** — OPA additionally validated *any* IaC (Ansible, ARM, Terraform), whereas Sentinel was
Terraform-only, required Terraform Cloud/Enterprise, and used a proprietary language. The customer
raised exactly two objections to OPA, both of which this ADR shows are now resolved (see §6):
*(1) "how viable is the vendor / is it supported?"* and *(2) "are there libraries so we don't have
to write every rule?"*

This ADR records the decision to **remain on OPA**, prompted by two 2025–2026 developments that
reasonably raise the question "should AAC reconsider its policy engine?":

1. **August 2025 — Apple acqui-hired the OPA/Styra core team** (the three OPA creators), triggering
   community concern about the project's trajectory.
2. A maturing field of **policy-as-code alternatives** (kyverno-json, CEL, AWS Cedar, Kubewarden, …).

## 2. Decision drivers

- **Fit for purpose:** AAC needs *batch evaluation of arbitrary fact JSON into scored, per-control
  reports* — not Kubernetes admission control and not application authorization.
- **Sunk investment / moat:** 510 Rego policies across 50+ frameworks are a strategic asset. A
  wholesale engine change means rewriting all of them.
- **Project health & governance:** longevity of the open-source engine AAC depends on.
- **Enterprise supportability:** regulated customers (NERC-CIP, FedRAMP) ask "who supports your
  policy engine?"
- **Performance / scale:** evaluation latency across large fleets.

## 3. Options considered

| Engine | What it is | Fit for AAC's assessment model | Verdict |
|---|---|---|---|
| **OPA (open source, CNCF)** | General-purpose Rego decision engine; REST eval API | Native — already the whole platform; JSON in → structured report out | **Keep (incumbent)** |
| **Enterprise OPA (EOPA)** | Styra's faster OPA runtime + data integrations; moving to open source | Drop-in — **same Rego**, keeps all 510 policies | **Upgrade path for scale** |
| **kyverno-json** | CNCF; YAML policies that validate **any JSON** (not just K8s) | Closest general-purpose alternative; no Rego, but YAML is weaker for scored multi-control reports | **Complementary** (no-Rego subset) |
| **CEL** (Common Expression Language) | Embeddable expression language; native in Kubernetes | Great for single boolean checks; not a framework for 338-control benchmarks | **Complementary** (embedded checks) |
| **AWS Cedar** + Verified Permissions | Rust, formally verified, ~42–60× faster than Rego | Built for **authorization** (principal/action/resource), not compliance reports | Wrong problem shape |
| **Gatekeeper / Kubewarden / jsPolicy** | Kubernetes admission engines (Gatekeeper *is* OPA) | Admission control for manifests, not host-fact assessment | Wrong layer |
| **Apache Casbin** | Access-control library (RBAC/ABAC) | Authorization only | Not applicable |
| **HashiCorp Sentinel** | Proprietary PaC language (HashiCorp, now IBM) | Terraform/HashiCorp-scoped, proprietary; lost the original 5-vs-3 PoC to OPA | Non-viable (proprietary, IaC-scoped) |
| **Chef InSpec** | Compliance-as-code DSL (Progress Chef) | Host/config compliance, but its own DSL + agent model; not a JSON decision engine | Adjacent, not a fit |
| **Azure Policy** | Azure-native governance | Cloud-provider-locked to Azure | Non-viable (single cloud) |
| **Fugue (→ Snyk) / Regula** | IaC compliance built **on OPA/Rego** | Same engine as AAC; Regula's Rego library is *reusable*, not a replacement | Complementary (reusable Rego) |
| **CUE / JSONLogic** | Config validation / lightweight rules | CUE handles structural checks; too limited for scored framework logic | Niche |

## 4. The Apple / Styra governance change — assessed

- Apple's move was an **acqui-hire, not an acquisition of Styra**; the OPA/Styra founders and core
  team joined Apple.
- **OPA itself is unaffected as a project:** it remains a **CNCF-governed, open-source** project, with
  the maintainer list and community oversight intact.
- Styra's previously-commercial add-ons (**Enterprise OPA, Regal, SDKs**) are being **moved into open
  source** rather than discontinued.

**Conclusion:** the engine AAC depends on — open-source OPA under CNCF — is **not at project-health
risk**. The change affected the commercial vendor layer, not the open-source core.

## 5. Enterprise support path — EnforceAuth

The one residual concern was **enterprise supportability** of OPA after the vendor-layer change.
That gap is addressed by **EnforceAuth** — an OPA-native runtime-authorization platform founded by
the **former Styra CEO**, which is **assuming enterprise support for the OPA/Styra enterprise
customer base**.

For AAC this is doubly significant because **EnforceAuth is already an AAC integration partner**
(Compliance-State API; AAC enforces on *state*, EnforceAuth enforces at *runtime*). The result is a
single, coherent **OPA-native backbone**:

- **AAC** — compliance **state / assessment** on OPA (510 Rego policies, three domain containers)
- **EnforceAuth** — **runtime authorization** *and* **enterprise OPA support** on the same engine

> Note: the EnforceAuth enterprise-support arrangement is current partner intelligence and was not
> independently confirmable via public sources at the time of writing; a citable reference should be
> obtained from EnforceAuth for customer/auditor use.

## 6. How the original (2022) objections have aged

The two objections the original PoC customer raised against OPA are now both retired — and they map
directly onto what AAC (and the AAC ↔ EnforceAuth partnership) delivers today:

| 2022 objection | Status in 2026 |
|---|---|
| "How viable is the vendor / how do we ensure a supported solution?" | **Resolved.** OPA is a CNCF-graduated, community-governed project (100M+ downloads); enterprise support is now available through **EnforceAuth** (ex-Styra leadership) — see §4–§5. |
| "Are there libraries so we don't have to write every rule?" | **Resolved.** AAC ships a **510-policy Rego library across 50+ frameworks** (CIS, NIST, STIG, ISO, SOC 2, PCI, NERC-CIP, AMI, sovereignty, …). Reusable OPA/Rego libraries such as **Regula** further extend it. |

The risks that were open questions three years ago are precisely the value the platform now provides.

## 7. Decision

**AAC standardizes on Open Policy Agent (open-source, CNCF) as its policy decision engine.**

Alternatives are adopted as **complementary tools for specific needs**, never as a wholesale
replacement:

- **Scale / performance pressure** → adopt **Enterprise OPA** (same Rego; no policy rewrite).
- **A customer mandates no-Rego / YAML policies for a subset** → add **kyverno-json** as a *second*,
  complementary engine for those frameworks only.
- **Lightweight embedded checks** (pre-flight, in-playbook) → **CEL**.

## 8. Consequences

**Positive**
- Preserves the 510-policy Rego library — AAC's principal technical moat.
- Engine remains open-source and CNCF-governed; no license or lock-in exposure.
- Enterprise support is available through an existing partner (EnforceAuth), giving a concrete
  answer to regulated-buyer due-diligence.
- Reinforces the AAC ↔ EnforceAuth "one OPA-native backbone" co-sell (state + runtime + support).

**Negative / watch-items**
- Continued dependence on Rego expertise for policy authoring.
- Cedar's formal-verification story is genuinely ahead of Rego and worth monitoring for
  authorization-adjacent use cases (not compliance assessment).
- The EnforceAuth support arrangement should be documented with a citable source before it is used
  in customer commitments.

**Neutral**
- No change to the running platform: this ADR ratifies the status quo with fresh justification.

## 9. Supportability statement (for customer / auditor conversations)

> AAC's policy engine is **Open Policy Agent**, an open-source, CNCF-graduated project. The
> open-source engine is community-governed and unaffected by the 2025 changes to its original
> commercial vendor. Enterprise support is available through **EnforceAuth**, led by the former
> Styra leadership, which also provides AAC's runtime-authorization integration — a single
> OPA-native backbone for both compliance assessment and runtime enforcement.

## 10. References

- Apple hires OPA/Styra team; OPA remains open source (CNCF) — Cloud Native Now, Oso, Open Source For You, heise (Aug 2025)
- Kyverno — "Evaluating policy engines" and JSON (ValidatingPolicy) documentation
- Oso — "OPA vs Cedar vs Zanzibar" (2025 policy-engine guide)
- AWS — "Migrating from Open Policy Agent to Amazon Verified Permissions"
- Spacelift — "Top Policy-as-Code tools" (2026)
- AAC memory: `enforceauth_integration`, `demo_tour_2026_07_28`
