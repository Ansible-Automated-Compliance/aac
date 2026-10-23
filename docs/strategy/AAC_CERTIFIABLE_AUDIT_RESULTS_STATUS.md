> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# AAC Certifiable Audit Results — Initiative Status & Roadmap

**Version:** v1.4
**Status:** Active development
**Date:** 2026-10-08

> **v1.4 (2026-10-08) — signing status reconciled against the code.** Item 4 (cosign key-based
> ECDSA-P256 signing) merged in PR #288 on 2026-07-02 and is hard-required by
> `ansible/roles/aac_store_certification` (the role refuses to write an unsigned row). The
> `sha256-unsigned` placeholder described in v1.3 is no longer written (rows that predate PR #288 still carry it). Offline verification is
> documented in [`docs/security/CAA_VERIFICATION.md`](../security/CAA_VERIFICATION.md). Items 3, 5
> and 6 remain open as stated. Every "item 4 pending" statement in §§1–3 and 5–7 was reconciled in the same pass; the STALE banner above stands for lab-topology specifics only.
**Audience:** AAC engineering, Red Hat field SAs/PMs touching regulated industries, partner auditors
**Owner:** Tim Coulter

---

## 1. Executive summary

AAC has the data behind every compliance evaluation it runs — hostname, framework, violations, timestamp, policy outputs — stored as `compliance_results` rows in PostgreSQL. **Those rows are query results, not deliverables.** Regulators are converging on a sharper bar: they want discrete, self-contained, signed objects that an auditor can verify offline without standing up the AAC stack.

This document describes the work in flight to bridge that gap — turning AAC's compliance data into **Certifiable Audit Artifacts (CAAs)** — and lists what still needs to be built, decided, or fixed.

### Where we are

| Item | Status | Delivered by |
|---|---|---|
| Spec — what a CAA is, the schema, the verifier flow | ✅ **Merged** | PR #232 (2026-06-23) |
| Item 2 — `compliance_certifications` table + writer role | ✅ **Merged** | PR #235 (2026-06-26) |
| Item 2a — real CIS RHEL 9 assessment writes a CAA row | ✅ **Merged** | PRs #269 / #270 / #271 (2026-07-01) |
| §5.9 follow-ups — `policy_library_sha` and `severity_summary` hardening | ✅ **Merged** | PRs #275 / #276 / #277 / #278 / #279 / #280 (2026-07-01 – 2026-07-02) |
| Item 4 — cosign key-based signing | ✅ **Merged** | PR #288 (2026-07-02) — ECDSA-P256, key id `cosign-key-v1`, public key in `docs/security/`; role hard-requires the key |
| Items 3, 5, 6 — clause mappings, verifier CLI, portal endpoint | ⬜ **Not started** | — |

### What this means in practice today

A consumer of AAC's data can already see `compliance_results` rows and join them to the host/framework/timestamp. CAA writing is opt-in per assessment playbook (`aac_caa_enabled: true`, which also passes the OPA result and input through to the writer); five playbooks opt in today (CIS RHEL 8, CIS RHEL 9, CIS Ubuntu 22.04, NERC CIP, Digital Sovereignty), the rest write `compliance_results` only. Each opted-in evaluation also writes a `compliance_certifications` row that captures **provenance** (policy library SHA, AAP job ID), **reproducibility** (canonical input hash + full result JSONB), and a **cosign ECDSA-P256 signature** over a canonical projection of those fields (the exact signed bytes are stored in `signed_projection`). The schema is the spec from §3.1, applied verbatim.

What it does **not** do yet:

- ~~The "signature" is sha256 over a canonical projection.~~ **Superseded (v1.4):** every CAA row written since PR #288 (2026-07-02) is cosign-signed (ECDSA-P256); see §5.1. Rows written before `signed_projection` existed keep the sha256 placeholder and are not cosign-verifiable (`CAA_VERIFICATION.md` covers them).
- `regulatory_clauses` is stored as an empty array — clause-mapping YAMLs are item 3.
- No dedicated verifier CLI exists yet (item 5). Auditors verify today by extracting the stored projection and signature with `psql` and running one `cosign verify-blob` against the committed public key, per [`CAA_VERIFICATION.md`](../security/CAA_VERIFICATION.md); re-deriving the verdict from bundled policies is still item 5.
- No portal surface — customers can query the row but cannot download a bundled artifact.

A CAA today proves **provenance, integrity and signature authenticity**. The rest of the property set (regulatory mapping, offline reproducibility, customer-facing delivery) lands across items 3, 5 and 6.

---

## 2. What a Certifiable Audit Artifact is

From the spec (`docs/strategy/AAC_CERTIFIABLE_AUDIT_ARTIFACT_SPEC.md` §2), a CAA has seven properties. The table below scores AAC's current state against each:

| # | Property | What it means | Today (post-#288) | Gap |
|---|---|---|---|---|
| 1 | Discrete deliverable | A single object handable to an auditor | Row exists; bundle does not | Item 6 (portal download) |
| 2 | Self-contained | Includes input facts + policy SHA to re-derive verdict | Result + input_hash stored; policies not bundled | Item 5 (verifier needs bundled policies) |
| 3 | Cryptographically signed | Tamper-evident, provenance fixed | ✅ cosign ECDSA-P256, `signed_by = cosign-key-v1`, exact signed bytes stored in `signed_projection` | — (done, PR #288) |
| 4 | Provenance-rich | Who/when/which policy SHA/which bundle | ✅ All captured | — |
| 5 | Regulatorily mapped | Tagged to specific clauses | Empty array | **Item 3 (clause YAMLs)** |
| 6 | Reproducible | A third party can recompute and confirm | Signature check possible (`cosign verify-blob`); no tool re-derives the verdict yet | Item 5 |
| 7 | Scoped | Knows whether it's host/fleet/control/compensating-control | Schema supports all 4; only `host` exercised | Items 3–6 |

**Net:** properties 3 and 4 are real today, and 7 partially. The other four each have a named roadmap item to close them.

---

## 3. The six-step roadmap

| # | Item | Status | Risk | Effort | Notes |
|---|---|---|---|---|---|
| 1 | CAA spec lands in `docs/` | ✅ Done | Low | 0 | Merged as `a404412` (PR #232) |
| 2 | `compliance_certifications` table + writer role | ✅ Done | Low | 0 | PR #235 merged 2026-06-26 |
| 3 | Clause-mapping YAMLs for 8 regimes + CI lint | ⬜ Not started | **Medium** | **3–5 weeks** | Long pole; needs domain SME input per regime |
| 4 | Cosign signing in writer role | ✅ Done | — | 0 | PR #288 — key-based ECDSA-P256 (`env://COSIGN_PRIVATE_KEY` from vault). Keyless/Rekor remains a possible later enhancement, not a gap |
| 5 | `aac-verify` CLI binary | ⬜ Not started | Medium | 1 week (Go) / 2–3 days (Python MVP) | Re-runs OPA against bundle; confirms sig + hash |
| 6 | Portal endpoint + UI | ⬜ Not started | Low | 3–4 days | `GET /api/portal/v1/certifications/<id>/bundle` + UI to list/preview |

**Dependencies & sequencing:**

- Items 1, 2 and 4 are done (#232, #235, #288).
- Item 3 is the calendar bottleneck — splits into 8 PRs (one per regulatory regime); each PR needs a careful read of the regulatory text.
- ~~Item 4 depends on item 2 (needs the schema).~~ Both merged; the signature format (`signed_projection` + `cosign-ecdsa-p256`) is fixed.
- Item 5 depends on items 2 + 4 — both done, so the verifier is unblocked; it defines the bundle format.
- Item 6 is last by design — portal surfaces the artifact, so it benefits from the rest stabilizing first.

---

## 4. What's been built so far

### 4.1 The spec (PR #232 — merged 2026-06-23)

`docs/strategy/AAC_CERTIFIABLE_AUDIT_ARTIFACT_SPEC.md` — 380-line draft that fixes the contract:

- The seven properties of a CAA
- The `compliance_certifications` table schema
- The clause-mapping directory layout (`policies/mappings/<regime>/clauses.yml`)
- The `aac-verify` CLI behavior
- The 6-step roadmap
- A glossary covering 11 regulatory terms

The spec is intentionally a draft — it sets the contract that downstream items implement, and surfaces seven open questions (§5).

### 4.2 Schema + writer (PR #235, merged 2026-06-26; cosign signing added in PR #288)

**Schema** — added to `ansible/roles/aac_compliance_db/tasks/schema.yml`:

- `CREATE TABLE compliance_certifications` with all 24 columns from spec §3.1
- 4 indexes (framework+scope+scope_value, period, evaluator job, GIN on regulatory_clauses)
- Idempotent (`IF NOT EXISTS`); safe to re-run

**Writer** — new role `ansible/roles/aac_store_certification/`:

- Validates inputs (framework, scope, status, scope value, result mapping)
- Resolves `policy_library_sha` from the `rego_policy_libraries` submodule pointer (falls back to `"unknown"` outside a git context)
- Calls a Python helper (`files/build_caa.py`) to compute:
  - `certification_id` (UUID v4)
  - `input_hash` (sha256 of canonicalized OPA input JSON)
  - the canonical `projection` bytes that the role then signs with `cosign sign-blob` (PR #288; the helper no longer computes signature bytes)
  - `severity_summary` (counts by severity from violations)
  - `signed_at` (RFC 3339 UTC)
- INSERTs one row, returns `aac_certification_id`

**Opt-in chain** — `aac_store_results` now accepts `aac_caa_enabled: true`. When set, it calls the new role after its own INSERT — so any existing assessment using `aac_store_results` gets CAA writes "for free" by flipping one var.

**Smoke test** — `ansible/playbooks/caa_smoke_test.yml` exercises the role end-to-end with a synthetic OPA decision and asserts the row landed with all expected columns populated. Verified against the live `compliance` DB on `AAP_HOST`:

```
TASK [Assert the row exists and has all required fields] *********
ok: [localhost] => "✅ CAA row written and verified"
PLAY RECAP *******************************************************
localhost  : ok=11  changed=1  unreachable=0  failed=0
```

---

## 5. What needs to be improved or fixed

Listed roughly in priority order. Items in **bold** block production credibility; the rest are improvements.

### 5.1 Cryptographic signing — DONE (Item 4, PR #288, 2026-07-02)

- **Today (rows written since PR #288):** `signature_algorithm = "cosign-ecdsa-p256"`, `signed_by = "cosign-key-v1"`. The role signs the canonical projection with `cosign sign-blob` using a private key sourced from the AAP vault via `env://COSIGN_PRIVATE_KEY`; the key never touches disk. The role **asserts the key is configured and refuses to write a row without it**.
- **Verification:** extract `signed_projection` and `signature` with `psql`, then one `cosign verify-blob` with the public key committed at `docs/security/caa-signing-key-v1.pub` — walkthrough in [`docs/security/CAA_VERIFICATION.md`](../security/CAA_VERIFICATION.md), including the trailing-newline pitfall.
- **Open design choice, not a gap:** key-based signing was chosen over keyless Sigstore/Rekor. Keyless would add a transparency-log entry per CAA; revisit only if an auditor asks for it.

### 5.2 No regulatory clause mappings yet (Item 3)

- **Today:** `regulatory_clauses` stored as empty array `'{}'`.
- **Why it matters:** the central value proposition — "this result speaks to HIPAA §164.312(c)(1)" — requires the mapping table. Without it, CAAs prove integrity + provenance but say nothing about which regulation they satisfy.
- **Fix:** Item 3 — `policies/mappings/<regime>/clauses.yml` for each of the 8 priority regimes (HIPAA NPRM, NERC CIP, CMMC L2, SEC Cybersecurity Disclosure, EU DORA, EO 14028 / OMB M-22-09, NIS2, TSA Pipeline). Needs domain SME or auditor review per regime — **this is the calendar bottleneck.**

### 5.3 No offline verifier exists (Item 5)

- **Today:** an auditor can read the DB row but cannot independently re-derive the OPA decision.
- **Why it matters:** "reproducible" is property #6 of a CAA. Without `aac-verify`, AAC is asking auditors to trust the row rather than verify it.
- **Fix:** Item 5 — `aac-verify` CLI. Go binary preferred for portability; Python MVP acceptable for a first cut.

### 5.4 No customer-facing surface (Item 6)

- **Today:** rows live in PostgreSQL behind the AAC perimeter. A customer cannot download a CAA bundle.
- **Why it matters:** an auditor in the field needs the bundle on their laptop. Today AAC's compliance posture is invisible outside the AAC environment.
- **Fix:** Item 6 — `GET /api/portal/v1/certifications/<id>/bundle` in `AAC_Customer_Portal` + a list/preview UI. Depends on the bundle format item 5 defines (the signature format is already fixed by item 4).

### 5.5 Bundle storage and `artifact_uri` are unspecified

- **Today:** `artifact_uri` is NULL. No bundle is built or stored.
- **Why it matters:** even once item 5 lands, the bundle itself needs a home — local filesystem, S3, MinIO. Currently undecided (open question #2 in the spec).
- **Fix:** pick a default. Recommendation: ship a MinIO container with AAC for self-hosted; document a customer-provided S3 hook for cloud deploys.

### 5.6 No bundle revision pinning

- **Today:** `opa_bundle_revision` is NULL. Only `policy_library_sha` (git SHA of the submodule pointer) is captured.
- **Why it matters:** when OPA serves bundles via the bundle API, the `x-opa-bundle-revision` header is the canonical pin. Capturing it would allow the verifier to confirm the *exact same bytes* OPA saw, not just the git tree.
- **Fix:** read the bundle revision from OPA's `/v1/status/bundles` endpoint during evaluation and store it. Small enhancement; could ride on item 5.

### 5.7 Only host-scoped CAAs are exercised

- **Today:** spec supports four scopes (`host`, `fleet`, `control`, `compensating_control`). Only `host` has been tested.
- **Why it matters:** `compensating_control` is the regulator-friendly mechanism for "I can't patch this, here's what I'm doing instead" — particularly valuable for OT/ICS. Open question #3 in the spec calls this out as needing a separate writer + portal form.
- **Fix:** scope this as a follow-up after items 3–6 stabilize. Likely a new playbook + a portal form for customer-declared compensating controls.

### 5.8 Per-CVE granularity is undefined

- **Today:** one CAA per assessment run. Each row covers all controls evaluated.
- **Why it matters:** several regimes (especially HIPAA NPRM, CISA EO 14028) emphasize "per-CVE, with timestamps and errata IDs." Aggregate CAAs may not meet that bar. Open question #5 in the spec.
- **Fix:** decide whether each CVE generates its own CAA (`scope=control`, `scope_value=CVE-ID`) or rolls up into a host CAA. Likely both, with the relationship modeled in a follow-up migration.

### 5.9 No AAP template wires this in yet — *closed 2026-07-01*

- **Was:** writer role existed but no assessment template launched with `aac_caa_enabled: true`. Only the synthetic smoke test wrote CAA rows.
- **Now:** CIS RHEL 9 assessment template (ID 18 on lab-aap) writes one `compliance_certifications` row per assessed host. Verified 2026-07-01 via lab-aap job 411 against `aap-controller-ssh` — new row `91e56235-0300-4b52-8efb-f7008973545e` landed in `compliance-db.aac.svc.cluster.local` with `evaluator_aap_job_id=411`, real `input_hash`, real `signature_hex`.
- **Landed via three PRs on 2026-07-01:**
    - PR #269 — flip `aac_caa_enabled: true` on the CIS RHEL 9 playbook, pass `aac_result_caa_result` and `aac_result_caa_input` through to the writer
    - PR #270 — rename wrapper pass-through vars to break a Jinja recursion (`aac_caa_result: "{{ aac_caa_result | default({}) }}"` hit max recursion depth in the first CIS run)
    - PR #271 — `become: no` on the three `delegate_to: localhost` tasks in `aac_store_certification` (same class as #266 / #267 — EE has no sudo)
- **Two follow-ups landed via six PRs on 2026-07-01 – 2026-07-02:**
    1. **`policy_library_sha` resolution** (PRs #276 / #277 / #278 / #279 / #280) — multi-strategy resolver: try `git rev-parse HEAD` inside the submodule, then `git ls-tree HEAD policies` in the parent, then read `policies/.git/HEAD` directly, then fall back to `awx_project_revision` prefixed with `project:`. Widened the DB column from `VARCHAR(40)` to `TEXT` to accommodate prefixed markers. Verified on lab-aap job 444 — CAA row `fa6137c8-...` has `policy_library_sha = 'project:9c02c41074ff74a0bf624e8605a4e41e0719e8af'` instead of `"unknown"`. Auditor dereference: parent-repo SHA → `.gitmodules` at that commit → exact `rego_policy_libraries` SHA.
    2. **`severity_summary` counting** (PR #275) — `build_caa.py` now handles string violations too (word-boundary regex `\b(critical|high|medium|low)\b`) and adds an `unclassified` bucket for anything without a resolvable severity. CIS RHEL 9 violations are plain strings without embedded severity keywords, so they all land in `unclassified` — honest signal rather than silently-zeroed summary. Verified on lab-aap job 444 — `severity_summary = {critical:0, high:0, medium:0, low:0, unclassified:63}` correctly counts all 63 real violations.

### 5.10 CAA retention policy is undecided

- **Today:** rows are immutable + `superseded_by` chain supports re-issue. No retention policy.
- **Why it matters:** regulators typically want 6–7 year retention. AAC needs a documented retention default and a way for customers to override. Open question #4 in the spec.
- **Fix:** add a retention policy doc + a daily job that flags rows older than the policy for archival (not deletion — auditors hate deletion).

### 5.11 Verifier distribution is undecided

- **Today:** no verifier exists, so the question is moot.
- **Why it matters:** when item 5 lands, auditors will need to install `aac-verify`. Options: GitHub Releases (single static binary), inside the AAC EE, `dnf install aac-verify` package, container image. Open question #6 in the spec.
- **Fix:** decide before item 5 starts. Recommendation: static binary on GitHub Releases (lowest friction for auditors who don't have AAC).

### 5.12 Portal as generator vs consumer

- **Today:** AAP generates results; the portal would only consume them.
- **Why it matters:** open question #7 — does the portal also become a CAA generator (e.g., for compensating-control attestations a customer self-declares), or stay purely a consumer? Affects item 6 scope.
- **Fix:** decide during item 6 planning. Recommendation: portal stays a consumer initially; compensating-control attestations are item 7 (post-roadmap).

---

## 6. Effort estimate to "complete the spec"

Two realistic shapes for the remaining 3 items (3, 5, 6):

### 6.1 MVP slice (~1 week of focused work)

- ~~Item 4 (signing)~~ — done (PR #288)
- Item 5 Python MVP (verifier)
- Item 3 for **one** framework (e.g. CIS RHEL 9 → HIPAA) as a proof of concept
- No portal yet

End state: assessment → signed bundle → auditor runs `aac-verify` and it passes. Provable, demonstrable, shippable to one customer.

### 6.2 Full roadmap as spec'd (~6–10 weeks)

- All 3 remaining items
- All 8 regimes properly mapped with auditor review
- Go verifier (not Python)
- Portal integration

End state: production-grade CAA pipeline; AAC is an auditor-ready system.

**The calendar bottleneck is item 3 — clause mapping is bulk regulatory work, not engineering work.** Pulling in a compliance SME or paying for an auditor review pass should be in the plan; without it the mappings are credible to engineers but vulnerable to auditor pushback.

---

## 7. Recommended next moves

1. ~~Land PR #235~~ — ✅ merged 2026-06-26.
2. ~~Wire `aac_caa_enabled: true` into the CIS RHEL 9 assessment template~~ — ✅ merged 2026-07-01 via PRs #269 / #270 / #271. Real CAA row verified in `compliance-db.aac.svc.cluster.local`.
3. ~~Fix the two small follow-ups from §5.9~~ — ✅ landed 2026-07-01 – 2026-07-02 via PRs #275–#280. Every real CAA row now carries a classified severity summary and a resolvable `policy_library_sha`.
4. ~~Start item 4 (cosign signing)~~ — **done** (PR #288, 2026-07-02). The remaining auditor-credibility gap is item 5 (verifier CLI that re-derives the verdict from bundled policies).
5. **Wire CAA into more assessments** — CIS Ubuntu 22.04 (template 23), CIS RHEL 8 (template 22), NERC-CIP (template 26), Digital Sovereignty (template 47). Each is a small copy-paste of the CIS RHEL 9 pattern in PR #269. High-volume auditor coverage; low per-assessment risk.
6. **Scope item 3 by regime** — pick the first regime (suggested: HIPAA NPRM) and produce a complete clause mapping as the template for the other 7. This is the calendar bottleneck — pull in a compliance SME early.
7. ~~Defer items 5–6 until item 4 is solid~~ — item 4 is done and the signature format is fixed. Item 5 can start now; item 6 follows it, because the portal consumes the bundle format item 5 defines.

---

## 8. References

- `docs/strategy/AAC_CERTIFIABLE_AUDIT_ARTIFACT_SPEC.md` — the spec this work descends from (PR #232, merged 2026-06-23)
- PR #235 — item 2 implementation (merged 2026-06-26)
- PR #288 — item 4, cosign key-based ECDSA-P256 signing in the writer role (merged 2026-07-02); verification walkthrough `docs/security/CAA_VERIFICATION.md`
- PR #269 / #270 / #271 — CIS RHEL 9 CAA opt-in + two follow-up fixes (Jinja recursion, become: no) (merged 2026-07-01)
- PR #275 — `severity_summary` handles string violations + adds `unclassified` bucket (merged 2026-07-01)
- PR #276 / #277 / #278 / #279 / #280 — `policy_library_sha` multi-strategy resolver, `awx_project_revision` fallback, environment-var passing, schema widening to TEXT, whitespace trimming (merged 2026-07-01 – 2026-07-02)
- Sigstore documentation — https://docs.sigstore.dev/
- in-toto attestation spec — https://github.com/in-toto/attestation
- Red Hat internal **Regulatory Tailwinds for Standardization** talk-track guide (2026-06-10, v1.0) — the strategic frame the spec descends from

---

*Researched, drafted, and co-authored with Claude (Anthropic) as engineering review aid. Human-reviewed by the AAC team.*
