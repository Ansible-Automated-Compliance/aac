# Evidence of Compliance — What Automated Tooling Actually Produces

### A naming and positioning note for teams building compliance dashboards

**Version:** v1.0
**Date:** 2026-08-14
**Audience:** Red Hat engineering, product and field teams building compliance-facing tooling
**Status:** discussion paper — proposes a naming convention, not a product decision

---

## 1. The argument in one paragraph

A tool that continuously evaluates systems against a standard produces **evidence of compliance**.
It does not produce **compliance**. Compliance is the state that exists once an accountable
human — an auditor, an authorizing official, or a certifying body — has reviewed that evidence,
accepted the residual risk, and put their name to it. Every major framework encodes this
separation explicitly, and **NIST has already standardized the distinction in machine-readable
form**. When we call a product a *Compliance Dashboard*, we claim the second thing while
delivering the first. Calling it an **Evidence of Compliance Dashboard** costs one word and is
accurate.

This is not a smaller claim. It is a more defensible one, and — as §7 argues — a more valuable one.

---

## 2. What "compliance" formally requires

Technical compliance is achieved when a system, process or product satisfies every mandatory
requirement of a governing standard. It is not an event but a continuously maintained state. Four
things are required, and **automation delivers one and a half of them**.

### 2.1 Verification of requirements

Proving the infrastructure matches the standard's criteria, through:

| Method | What it means |
|---|---|
| **Testing** | Automated or manual tests confirming the system behaves as required |
| **Inspection** | Examining code, hardware configuration or architecture directly |
| **Analysis** | Modelling or calculation proving a performance or safety property |
| **Demonstration** | Operating the system to show a required function works |

> **Automation is genuinely strong here.** Continuous evaluation across an entire estate is
> something manual audit cannot match on coverage or frequency.

### 2.2 Formal documentation — the paper trail

Compliance cannot exist without records:

- **Traceability matrices** — mapping each requirement to a specific test case or system feature
- **Test reports** — certified results showing mandatory evaluations were passed
- **Standard operating procedures** — written evidence that the team follows compliant processes

> **Automation produces the raw material but not the artefact.** A results database is not a
> traceability matrix, and a dashboard is not a test report. Both must be *derived, reviewed and
> retained* — and the retention period is set by the framework, not by the tool.

### 2.3 Third-party audit or self-certification

Recognition happens in exactly one of two ways, and **neither is a software output**:

- **Independent audit** — an accredited third party reviews the evidence and issues a formal
  certification
- **Self-declaration** — an accountable team signs a formal declaration that the product meets
  the applicable rules

> **This is the step no tool performs.** It is a human accepting professional, and often legal,
> liability.

### 2.4 Continuous monitoring

Because systems drift, compliance is only *maintained* through configuration management and
automated checking.

> **Automation is the strongest option available here** — arguably the only viable one at scale.

---

## 3. Scoring ourselves honestly

| Requirement | What automated tooling delivers | Gap |
|---|---|---|
| Verification | ✅ Testing and inspection, continuously, at full estate coverage | Analysis and demonstration usually remain manual |
| Documentation | ⚠️ Produces the underlying records | Traceability matrices, reports and SOPs must still be derived and retained |
| Audit / certification | ❌ **Nothing** | Entirely a human act |
| Continuous monitoring | ✅ The core strength | Requires the estate to actually be in scope and current |

**Two of four, plus a partial.** That is a strong product. It is not compliance.

---

## 4. NIST already made this distinction — and named it

This is the decisive point, because it means the naming argument is not a matter of taste.

### 4.1 The Risk Management Framework separates Assess from Authorize

**NIST SP 800-37** defines these as *different steps performed by different people*:

- **Assess** — test and validate that controls are effective, properly configured and documented.
  Produces **evidence and findings**.
- **Authorize** — an **Authorizing Official** reviews the authorization package and formally
  **accepts the residual risk**, deciding whether the system may operate.

Assessment produces evidence. Authorization is a person accepting consequences. A dashboard can
do the first and can never do the second.

### 4.2 OSCAL names the model "Assessment Results"

**OSCAL** — NIST's Open Security Controls Assessment Language — is the standard for exchanging
this information in machine-readable form. Its **Assessment Layer** contains three models:

| OSCAL model | Purpose |
|---|---|
| **Assessment Plan** | What will be assessed and how |
| **Assessment Results** | **The findings of a periodic or continuous assessment, with supporting evidence** |
| **Plan of Action & Milestones (POA&M)** | Known risks, deviations, remediation plan and disposition |

The model describing exactly what a compliance dashboard emits is called **Assessment Results**.
NIST did not call it "compliance", and the choice was deliberate: authorization lives outside the
assessment layer entirely.

> **Practical note:** AAC already exports to **OSCAL 1.1.2 Assessment Results**
> (`scripts/oscal_mapper.py`). Our own interchange format uses NIST's term. It would be odd for
> the user interface to claim something stronger than the export format does.

---

## 5. Who actually signs off — and what they sign

The signatory differs by framework, and in no case is it a tool. This table is worth keeping
close when writing UI copy.

| Framework | Who signs | What is issued |
|---|---|---|
| **ISO/IEC 27001** | An accredited certification body (accredited under **ISO/IEC 17021-1**) | A **certificate**, after a two-stage audit; valid 3 years with annual surveillance audits |
| **SOC 2** | A **licensed CPA firm** under AICPA standards | An **attestation report containing the auditor's opinion** — there is no SOC 2 certificate, and no accreditation body for SOC 2 auditors |
| **FedRAMP** | A **3PAO** assesses; the **agency Authorizing Official** decides | An **ATO** — an Authority to Operate |
| **PCI DSS** | A **QSA** (or ISA for some merchants) | **Report on Compliance** and **Attestation of Compliance** |
| **NERC CIP** | The **Regional Entity** audits under NERC/FERC authority | Audit finding; non-compliance carries **financial penalty** |
| **CMMC** | A **C3PAO** for the certified levels | A certification decision |
| **Self-declaration regimes** | The engineering or manufacturing organisation itself | A signed **declaration of conformity** |

Note the SOC 2 row especially. The deliverable is a **professional opinion**. No amount of
telemetry produces an opinion.

---

## 6. The naming recommendation

**Rename the class of thing, not the capability.**

| Instead of | Use |
|---|---|
| Compliance Dashboard | **Evidence of Compliance Dashboard** |
| Compliance Score | **Control Assessment Score** *or* **Evidence Coverage** |
| "You are compliant with CIS RHEL 9" | **"Evidence for CIS RHEL 9 — 312 of 338 controls passing"** |
| Compliance Status: PASS | **Assessment Result: PASS** |
| Compliance Report | **Assessment Report** *or* **Evidence Pack** |

### Keep the word "compliance" — it is doing necessary work

This is **not** an argument for scrubbing the term. "Compliance" sets the frame: it invokes
auditors, frameworks, controls, penalties and the budget line that funds the work. Remove it and
the conversation shrinks to "a scanning tool".

The distinction is grammatical and easy to apply under pressure:

- ✅ **"compliance" as the domain noun** — *compliance evidence*, *compliance automation*,
  *compliance posture*, *the compliance team*. Use freely.
- ❌ **"compliant" as a predicate about the customer** — *"you are compliant"*, *"makes you
  compliant"*, *"guarantees compliance"*. Never.

The noun names the space we work in. The adjective asserts a verdict only an auditor can render.

### "Evidence of" or "evidence for"?

Both are defensible and the difference is worth knowing:

- **Evidence *of* compliance** — asserts the underlying state exists and this demonstrates it.
  Slightly stronger.
- **Evidence *for* compliance** — evidence submitted *toward* an assessment, with the outcome
  still open. Slightly more cautious, and more accurate before an audit concludes.

**Recommendation: "evidence of compliance" for product naming** (it reads naturally and is
widely used in audit practice), **"evidence for the audit"** when describing a specific
submission.

---

## 7. Why this is a stronger position, not a weaker one

The instinctive objection is that this concedes ground. It does the opposite.

**1. It is the only claim we can defend.** When a customer fails an audit, a vendor who claimed
"compliance" owns the failure. A vendor who supplied evidence has a defensible position — and the
evidence is examinable.

**2. It raises our own bar.** If evidence is the product, then evidence *quality* is product
quality. That makes concrete engineering properties load-bearing rather than optional:

- **Attribution** — every result names the system it is about and the framework it evaluates
- **Provenance** — every result identifies the policy version that produced it, so
  *"show me the rule you applied"* is answerable
- **Fail-closed storage** — an assessment that found nothing must not be storable as an
  assessment that passed
- **Retention and immutability** — the framework sets the period, not the tool
- **Honest gaps** — coverage and staleness stated, not hidden behind an aggregate score

**3. It is where the real value is.** Auditors sample a handful of systems at a point in time,
and customers spend weeks assembling screenshots. Continuous, timestamped, machine-collected
evidence across the whole estate **shortens the audit and widens its coverage**. Both claims are
true, defensible, and neither borrows the auditor's judgement.

**4. It aligns with how buyers already think.** Audit and GRC professionals are precise about
this vocabulary. Using it correctly signals fluency; using it loosely signals the opposite to
exactly the audience whose budget we want.

---

## 8. Practical guidance for dashboard builders

If you are building one of these, five things follow directly:

1. **Name the artefact for what it is** — see §6.
2. **Make every result attributable.** A result that cannot name its subject, its framework and
   the policy version that produced it is not usable as evidence, however good the UI is.
3. **Never let a score read as a verdict.** 94% is a measurement. Pair it with coverage and
   recency, or it will be read as a pass.
4. **Show what you did not assess.** Coverage gaps and stale results are audit findings waiting
   to happen. Surfacing them is more valuable than a green number.
5. **Export to OSCAL Assessment Results.** It is the standard interchange format, it is what
   FedRAMP automation consumes, and it keeps the naming honest by construction.

---

## 9. Resources

**Primary standards and frameworks**

- NIST SP 800-37 Rev. 2 — *Risk Management Framework*, Assess and Authorize steps —
  <https://csrc.nist.gov/pubs/sp/800/37/r2/final>
- NIST SP 800-53A — *Assessing Security and Privacy Controls* —
  <https://csrc.nist.gov/pubs/sp/800/53/a/r5/final>
- NIST OSCAL — layers and models — <https://pages.nist.gov/OSCAL/documentation/schema/>
- NIST OSCAL Assessment Layer concepts —
  <https://pages.nist.gov/OSCAL/learn/concepts/layer/assessment/>
- ISO/IEC 27001:2022 — <https://www.iso.org/standard/27001>
- ISO/IEC 17021-1 — requirements for bodies providing audit and certification —
  <https://www.iso.org/standard/61651.html>
- ISO 19011 — guidelines for auditing management systems —
  <https://www.iso.org/standard/70017.html>
- AICPA SOC 2 / Trust Services Criteria —
  <https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2>
- FedRAMP — <https://www.fedramp.gov/>
- PCI DSS v4.0 — <https://www.pcisecuritystandards.org/>
- NERC CIP standards — <https://www.nerc.com/pa/Stand/Pages/CIPStandards.aspx>
- CMMC — <https://dodcio.defense.gov/CMMC/>

**Red Hat context**

- Red Hat Compliance Operator (OpenShift) —
  <https://docs.redhat.com/en/documentation/openshift_container_platform/latest/html/security_and_compliance/compliance-operator>
- OpenSCAP / SCAP Security Guide — <https://www.open-scap.org/>
- Ansible Automation Platform documentation —
  <https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform>

**Related internal material**

- `docs/AAC_EVIDENCE_QUALITY_ASSESSMENT.md` — applies this standard to a live evidence corpus and
  measures where it falls short. Useful as a worked example of what "evidence quality is product
  quality" means in practice.
- `scripts/oscal_mapper.py` — maps assessment results to OSCAL 1.1.2 Assessment Results.

---

## 10. Summary

| | |
|---|---|
| **What we build** | Continuous, attributable, machine-collected **evidence of compliance** |
| **What we do not build** | The auditor's sign-off, the certification, or the authorisation decision |
| **What to call it** | *Evidence of Compliance* — keep "compliance", drop "compliant" |
| **Why it matters** | It is the only claim that survives contact with an auditor, and it sets a higher engineering bar for us |

> A dashboard cannot make anyone compliant. It can make the evidence so complete, so current and
> so well attributed that the sign-off becomes straightforward. **That is the product.**

---

## Authorship

Prepared by **Tim Coulter** with **Claude (Anthropic, Claude Opus 5)** as co-author.

*This is a discussion paper offering a naming convention for internal consideration. It is not a
statement of Red Hat product policy, and it is not legal or audit advice. Framework requirements
change; verify against the current published standard before relying on any specific detail here.*
