# AAC Futures / Backlog

**Version:** v1.0
**Date:** 2026-07-03
**Purpose:** Running list of planned-but-not-yet-implemented work so designs don't get lost between
sessions. Each item links to its design/context doc. Add new items at the top of the relevant
section; move to "Done / superseded" when shipped.

---

## Planned work

| # | Item | Repo | Status | Trigger / priority | Design ref |
|---|------|------|--------|--------------------|-----------|
| F1 | **OpenSCAP integration** (optional ingested evidence source) | compliance | Designed — ready to implement | Customer requires SCAP / DISA-STIG attestation | `docs/integration/OPENSCAP_INTEGRATION_DESIGN.md` (PR #298) |
| F2 | Benchmark **version-content refresh** (STIGs/CIS behind) | rego_policy_libraries | Diagnosed, not started | Ongoing; needs source benchmarks | `~/Downloads/rego-policy-currency-audit.md` |
| F3 | `package cis` **namespace split** (7 colliding frameworks) | rego_policy_libraries | Diagnosed, deferred | Before combined `data.cis.*` queries | Phase 1 findings (`docs/testing/phase1-findings.md`) |
| F4 | **RHEL 9 tree consolidation** (3 overlapping trees) | rego_policy_libraries | Diagnosed, deferred | Consumer-sensitive; do deliberately | contract-drift finding (`~/Downloads/rego-consumer-contract-drift.md`) |
| F5 | Additional **certified-tool integrations** (SCC for Windows, Tenable, CIS-CAT) | compliance | Architected, not designed in detail | Per-customer tool licensing | the hybrid certified-tools design (internal) |

---

## F1 — OpenSCAP integration (primary entry)

**One-liner:** Add OpenSCAP as an *optional, ingested* evidence source for the Linux-OS layer,
without changing the AAC spine (Ansible gather-facts → OPA → PostgreSQL stays the default for the
whole estate). This is the detailed implementation of the **OpenSCAP row** in
the hybrid certified-tools design (internal) (certified upstream tools own audit-weight verdicts;
AAC owns orchestration, history, and cross-framework roll-up).

**Full design:** `docs/integration/OPENSCAP_INTEGRATION_DESIGN.md` (v1.0, PR #298) — do not lose;
this entry is only the index.

**Why (do-not-forget rationale):**
- OpenSCAP brings content currency, OVAL check fidelity, and auditor-recognized ARF/XCCDF
  attestation — exactly the drift-prone weakness the currency audit found in the Rego OS benchmarks.
- It is **opt-in, never a replacement**: pure OpenSCAP would lose the uniform historical store and
  collapse `technical_debt` from a 17-framework rollup to one benchmark.
- Coverage boundary: ~178 of 505 Rego policies (Linux-OS core) are cleanly OpenSCAP-ownable; the
  other ~296 — including 220 regulatory-framework policies — stay uniquely Rego. OpenSCAP can't
  reach network devices, cloud, SaaS, or frameworks (the scanner must run on the target).

**Integration model (chosen):** Model 1 — run `oscap` on hosts → parse ARF → **normalize into the
same `compliance_results` store** → OPA rolls up. Standalone ARF/HTML that never hits the DB is a
silo and defeats the purpose. Optional Model 2 (store OVAL System-Characteristics snapshots) if
raw-state re-scoring on the OS layer is wanted.

**Phased plan (from the design doc):**
0. Decide & scope (which customer, which benchmarks require SCAP attestation; RHEL-native).
1. `aac_oscap_scan` role + `AAC - OpenSCAP Host Scan` template → ARF/XCCDF/HTML.
2. ARF/XCCDF parser → `compliance_results` shape.
3. `aac_oscap_ingest` → PostgreSQL (framework key + `evidence_source` metadata).
4. CCI/CCE → NIST 800-53 → framework mapping so OpenSCAP feeds technical-debt + linked evals.
5. Source precedence / dedup (OpenSCAP wins for the OS layer when present).
6. Optional: retire the ~178 drift-prone OS Rego / OVAL-SC snapshots / gated remediation.

**Built 2026-09-23:** `aac_oscap_scan` + `aac_oscap_ingest` roles (extracted from the proven
`openscap_assess.yml` #536 pipeline, which now composes them; single tested parser
`scripts/openscap_xccdf_parse.py`). External XCCDF/ARF ingest (CIS-CAT Pro etc.) supported via
`oscap_results_file` + `oscap_tool`. AAP template: "AAC - OpenSCAP Assessment".

**Still open:** CCI→800-53 crosswalk reference data, dual-source precedence, OVAL-SC snapshots,
gated remediation (design doc Phases 4-6).

---

## Done / superseded

*(none yet)*
