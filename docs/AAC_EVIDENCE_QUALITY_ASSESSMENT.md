# AAC Evidence Quality Assessment

**Version:** v1.1
**Date:** 2026-08-13
**Scope:** the lab evidence corpus — `compliance_results`, 2,744 rows, 2026-01-25 → 2026-08-13
**Extends:** `docs/patch_remediation_lifecycle.md` §5 (valley model)

---

## Why this assessment exists

> *"What we do is provide evidence of compliance. Compliance is the state when an auditor signs
> off on the evidence. We provide the evidence."*

If evidence is the product, then evidence quality **is** product quality. This assessment applies
that standard to AAC's own corpus and asks one question of every row: **would an auditor accept
it?**

Every figure below was measured against the live lab database, not estimated.

---

## 1. Summary — five findings, ranked by what discredits a corpus

| # | Finding | Scale | Severity |
|---|---|---|---|
| 1 | **Evidence cannot name its subject** — 1,338 `localhost` + 906 with no hostname at all | **2,244 rows / 81.8%** | **Critical** |
| 2 | **No policy provenance** — cannot answer "which rule produced this verdict" | **100% of corpus** | **Critical** |
| 3 | **Unattributed evidence** — `framework IS NULL`, and the column is nullable | **906 rows / 33%** | High |
| 4 | **Silent empty results** stored as if meaningful | `iec_62443` 3/3 | High |
| 5 | **Coverage and currency** — managed assets never assessed | **11 of 13** | High |

The first two would cause an auditor to reject the corpus outright. The rest degrade it.

### Remediation status (as of v1.1)

| Finding | Status |
|---|---|
| 3 — unattributed evidence | ✅ **Fixed 2026-08-13.** 906 rows attributed; `framework` is now `NOT NULL` |
| 4 — silent empty results | ✅ **Fixed 2026-08-13.** Fail-closed gate live and verified rejecting `total_controls = 0` |
| 1, 2, 5 | Open — see §8 |

Applied by `ansible/playbooks/fix_evidence_integrity.yml` (AAP template
*"AAC - Fix Evidence Integrity"*, dry-run by default). Row count unchanged at 2,744 — no verdict
was deleted or rewritten, and every corrected row records the correction itself in
`metadata._integrity_fix`. Remaining defects are visible in the `evidence_integrity_exceptions`
view rather than being quietly cleaned away.

---

## 2. Finding 1 — evidence that cannot name its subject

| Subject | Rows | Share |
|---|---|---|
| `localhost` — the execution context, not an asset | 1,338 | 48.8% |
| **no hostname at all** (the column is nullable) | 906 | 33.0% |
| **a named asset** | **500** | **18.2%** |

**Only 18% of the evidence corpus names the system it is about.**

`localhost` is not an asset — it is the controller that happened to run the playbook, and it
denotes a *different* machine depending on where it ran. The other 906 rows carry no subject at
all: like `framework`, `hostname` is nullable, so a producer that omits it fails silently.

The first question in any audit is *"which system is this evidence about?"* For four rows in five
there is no answer.

> **Corrected in v1.1.** The first draft reported this as 49%, counting only the `localhost` rows.
> Verifying the fix surfaced the 906 rows with no hostname at all — the same rows that had no
> framework. The honest figure is 81.8%.

### It gets worse on reconciliation

| Measure | Count |
|---|---|
| Assets with evidence | 18 |
| Managed assets observed in inventory | 13 |
| **Assets appearing in both** | **2** |

Evidence exists for 16 names that the inventory has never observed
(`aac-controller`, `assessment-host`, `compliance-lab-rhel9`, `ncsc-caf-degraded`, …), while 11
observed managed assets have no evidence at all. **The two halves of the platform disagree about
what exists.**

This is precisely the *register drift* concept from §5.9 — observed-but-not-registered and
registered-but-not-observed — turned inward on our own data.

**Fix:** resolve the real target hostname at storage time rather than recording the execution
context; where a playbook genuinely assesses the controller, record the controller's actual
hostname, never `localhost`. Then make `hostname` NOT NULL, as was done for `framework`.

---

## 3. Finding 2 — no policy provenance

`policy_version` is free text, and it is being used for at least four different things:

| Value | Rows | What it actually is |
|---|---|---|
| `1.0` | 1,600 | a placeholder |
| `CIP-002 through CIP-015` | 196 | a control range |
| `CIS Red Hat Enterprise Linux 9 Benchmark v2.0.0` | 176 | a benchmark title |
| `mac-aap-demo-v1` | 81 | a demo tag |
| `4.0-phase1-phase2` | 61 | a project phase |

**None of them identifies the policy that produced the verdict.** No row in the corpus carries the
Rego commit SHA, and a `metadata` scan for `sha|commit|revision|git` returns no genuine
provenance.

This matters more here than in most systems because **the policy library changes constantly** —
515 policy files behind a submodule pointer that moves most weeks. A verdict rendered in March and
a verdict rendered in August may have been produced by materially different rules, and nothing in
the corpus distinguishes them.

An auditor asking *"show me the rule you applied"* cannot be answered for any of the 2,744 rows.
An auditor asking *"re-run that assessment and show me the same result"* cannot be satisfied
either, because the inputs are not pinned.

**Fix:** capture the pinned submodule SHA at evaluation time — `git ls-tree HEAD policies` — and
store it in a dedicated column. Keep `policy_version` for the human-readable benchmark title,
which is what most rows are already using it for. Cheap to implement; touches every storing
playbook.

---

## 4. Finding 3 — unattributed evidence, and a safeguard that does not exist

**906 rows (33%) have `framework IS NULL`.** They come from identifiable producers:

| Producer | Rows |
|---|---|
| AMI NIST IR 7628 Rev 1 | 164 |
| AMI Device Compliance | 162 |
| AMI Head-End Security | 162 |
| CIS Fedora 39 | 74 |
| Digital Sovereignty | 58 |
| NERC CIP | 57 |

CLAUDE.md documents this column as **`framework varchar(100) NOT NULL`** and warns:
*"Always include `framework` in INSERT — it is NOT NULL; omitting it causes a constraint
violation."*

**The column is nullable.** `information_schema` reports `is_nullable: YES`.

So the guidance is right in spirit and wrong on mechanism — and the wrong mechanism is the whole
problem. The failure that was supposed to be loud and immediate has instead been **silent for
seven months**, quietly appending unattributable rows.

**Fix, in order:** backfill `framework` from `policy_name` (populated on all 906 rows), then
`ALTER TABLE ... SET NOT NULL`. That converts a third of the corpus from dead to usable and stops
new unattributed rows the same day.

---

## 5. Finding 4 — silent empty results

| Framework | Rows | Zero-control rows | No violation detail |
|---|---|---|---|
| `iec_62443` | 3 | **3 (100%)** | 3 |
| `ncsc_caf_4` | 78 | 1 | **70** |
| *(null framework)* | 906 | 1 | 275 |
| `cis_rhel9` | 116 | 4 | 12 |

`iec_62443` is the clearest case: **every stored row claims zero controls.** The cause is already
documented — the package is `iec_62443_main`, not `iec_62443.main`, so the generic framework path
resolves to `{}`. It has been known since June and has continued writing meaningless evidence
since, because **nothing rejects an empty result at the storage boundary.**

The job goes green. The row lands. The dashboard counts it.

**Fix:** a fail-closed gate on insert — reject rows with `total_controls = 0` or an empty
violations payload, and fail the job loudly. This is the same shape as the fail-closed gates the
CIS audit added at the policy layer; it belongs at the storage layer too. *An assessment that
found nothing and an assessment that never ran produce identical rows today.*

---

## 6. Finding 5 — coverage and currency

Measured against **managed assets only** — 85 of the 98 observed hostnames are ephemeral container
IDs and are deliberately excluded, because counting them would inflate the gap and an auditor
would say so.

| Managed asset | Days since evidence |
|---|---|
| `LAB_UTIL_HOST` | 22 |
| `compliance-lab-rhel10` | 51 |
| 11 others (9 EC2, `ocptesttc`, `EC2AMAZ-P47FJVH`) | **NEVER** |

**11 of 13 managed assets have never been assessed. Not one has evidence under 22 days old.**

Framework currency is comparably weak — `iec_62443` 45 days, `cis_ubuntu_2204` and
`cis_amazon_linux_2023` 71 days, `NIST IR 7628` and the AMI frameworks 82 days.

AAC's own stated principle is that *complete coverage is mandatory — compliance requires 100% of
infrastructure*. The platform does not currently meet that standard on its own lab.

**Fix:** this is a programme, not a patch — scheduled collection reaching the full inventory, plus
an explicit scope decision about which assets are in scope. Scope is a decision, not a count.

---

## 7. The valley model, turned inward

§5 defines four valley types for compliance gaps. Our own corpus sits in three of them:

| Valley | Our corpus |
|---|---|
| **coverage** — never assessed | 11 of 13 managed assets |
| **currency** — assessed but stale | frameworks at 22–82 days |
| **exposure** — known gap past its window | `iec_62443` broken since June |
| support — no fix will exist | n/a |

**Findings 1–3 do not fit any of them.** Subject identity, policy provenance and attribution are
not gaps in *coverage* — they are defects in the evidence itself. A perfectly fresh, 100%-coverage
corpus with these defects would still be rejected.

**Recommendation: add a fifth dimension — `attribution` — to §5.** It answers *"can this row say
what it is about, what produced it, and against which rule?"* That is a genuine extension to the
lifecycle model rather than a parallel construct.

---

## 8. Recommended sequence

Ranked by what an auditor rejects a corpus over, not by ease.

| # | Action | Effort | Effect |
|---|---|---|---|
| ~~1~~ | ~~**Fail-closed gate on insert**~~ | Small | ✅ **DONE** — verified rejecting empty results |
| ~~2~~ | ~~**Backfill `framework`, then `SET NOT NULL`**~~ | Small | ✅ **DONE** — 906 rows recovered, 0 unattributed |
| 3 | **Store the pinned Rego SHA per result** | Medium | Makes "which rule produced this" answerable — the single biggest credibility gain |
| 4 | **Resolve real hostname instead of `localhost`, then `hostname NOT NULL`** | Medium | Makes 82% of the corpus attributable to a subject |
| 5 | **Reconcile evidence against observed inventory** | Medium | Surfaces register drift as a first-class signal |
| 6 | **Coverage programme** — scheduled collection across the full inventory | Large | Closes the coverage valley |

Items 1 and 2 are same-day structural fixes that stop the bleeding. Items 3 and 4 are what convert
the corpus from *internally useful* to *externally defensible*. Item 6 is the largest number but
the slowest lever — it should not displace 1–4.

---

## 9. What this assessment does not claim

- It measures the **lab** corpus. A customer install may differ, though the schema and playbooks
  are shared, so findings 1–4 are structural and will travel.
- It does not evaluate whether individual Rego rules are *correct* — only whether the evidence
  they produce is attributable, provenanced and complete.
- "Never assessed" means no row in `compliance_results`. An asset may have been assessed by
  something outside AAC.

---

## Authorship

Prepared by **Tim Coulter** with **Claude (Anthropic, Claude Opus 5)** as co-author.
