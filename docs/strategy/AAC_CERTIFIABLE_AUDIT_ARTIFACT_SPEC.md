> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: OLD-CLUSTER-IDx2.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# AAC Certifiable Audit Artifact (CAA) — Specification

**Version:** v1.0 (draft)
**Status:** Draft for team review
**Date:** 2026-06-17
**Audience:** AAC engineering, Red Hat SAs / PMs touching regulated industries
**Owner:** Tim Coulter

---

## 1. Executive summary

AAC has the data behind every compliance evaluation it runs — hostname, framework, violations, timestamp, policy outputs — but those rows in `compliance_results` are query results, not deliverables. Regulators are converging on a sharper bar: **certifiable audit artifacts** — discrete, self-contained, signed objects that an auditor can verify offline without re-running the AAC stack.

This spec defines:

- What a Certifiable Audit Artifact (CAA) is, precisely
- The schema for storing and serving CAAs
- The signing approach (recommend: Sigstore / cosign)
- The clause-mapping layer that ties internal control IDs (e.g., `CIS 1.1.1`) to specific regulatory clauses (e.g., `HIPAA §164.312(c)(1)`)
- The offline verifier that re-runs OPA against the artifact and confirms the result
- A 6-step roadmap to ship this without breaking existing AAC functionality

The motivating context (the eight cybersecurity regimes putting fleet-wide compliance pressure on regulated customers) is in the Red Hat-internal Regulatory Tailwinds talk-track guide (2026-06-10, v1.0).

---

## 2. The proof-bar regulators are setting

Every regime AAC speaks to — HIPAA Security Rule NPRM, NERC CIP-015, CMMC 2.0, SEC Cybersecurity Disclosure, EU DORA, EO 14028 / OMB M-22-09, NIS2, TSA Pipeline — converges on the same evidentiary demand:

> Provable, on-time remediation of known vulnerabilities, evidenced per host, across the entire fleet, with documented compensating controls where patches can't land — per-host, per-CVE, with timestamps and errata IDs.

That sentence is the design target. AAC's job is to produce artifacts that satisfy it without the customer having to assemble a parallel reporting pipeline.

### The seven properties of a CAA

A Certifiable Audit Artifact has all seven:

| # | Property | What it means |
|---|---|---|
| 1 | **Discrete deliverable** | A single object — not a query result. Handable to an auditor. |
| 2 | **Self-contained** | Includes the input facts and policy SHA needed to re-derive the verdict. |
| 3 | **Cryptographically signed** | Tamper-evident; provenance fixed at generation time. |
| 4 | **Provenance-rich** | Who ran it (AAP user / job), when, against which `rego_policy_libraries` SHA, which OPA bundle revision. |
| 5 | **Regulatorily mapped** | Tagged to specific clauses in the regime(s) it speaks to. |
| 6 | **Reproducible** | A third party can recompute the OPA decision from the artifact and confirm the same result. |
| 7 | **Scoped** | Knows whether it is a host attestation, a fleet attestation, a control attestation, or a compensating-control attestation. |

A row in `compliance_results` today satisfies properties 4 and 5 partially. A CAA satisfies all seven.

---

## 3. Data model

### 3.1 `compliance_certifications` (new table)

```sql
CREATE TABLE compliance_certifications (
    certification_id        UUID PRIMARY KEY,        -- artifact identifier; signed
    framework               VARCHAR(100) NOT NULL,   -- e.g. nerc_cip, hipaa, cmmc_l2
    framework_version       VARCHAR(50),             -- e.g. "v2.0.0", "Rev2"
    scope                   VARCHAR(20) NOT NULL,    -- host | fleet | control | compensating_control
    scope_value             TEXT NOT NULL,           -- hostname | fleet_id | control_id | exception_id
    period_start            TIMESTAMPTZ NOT NULL,    -- attestation period
    period_end              TIMESTAMPTZ NOT NULL,
    evaluator_aap_job_id    INTEGER NOT NULL,        -- AAP job that produced it
    evaluator_aap_host      VARCHAR(255),            -- local AAP vs RHPDS vs customer
    policy_library_sha      VARCHAR(40) NOT NULL,    -- rego_policy_libraries git SHA
    opa_bundle_revision     VARCHAR(255),            -- OPA bundle x-opa-bundle-revision
    input_hash              CHAR(64) NOT NULL,       -- sha256 of canonicalized OPA input
    result                  JSONB NOT NULL,          -- canonical OPA decision document
    regulatory_clauses      TEXT[] NOT NULL,         -- ["HIPAA §164.308(a)(1)(ii)(D)", ...]
    compliance_status       VARCHAR(20) NOT NULL,    -- compliant | non_compliant | partial
    severity_summary        JSONB,                   -- {critical: 0, high: 3, medium: 12, low: 1}
    signature               BYTEA NOT NULL,          -- detached signature over a canonical projection
    signature_algorithm     VARCHAR(50) NOT NULL,    -- sigstore-cosign | gpg-sha256 | hmac-sha256
    signed_by               VARCHAR(255) NOT NULL,   -- key fingerprint / cosign identity
    signed_at               TIMESTAMPTZ NOT NULL,
    artifact_uri            TEXT,                    -- S3 / object store key for the bundle
    superseded_by           UUID REFERENCES compliance_certifications(certification_id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_caa_framework_scope     ON compliance_certifications(framework, scope, scope_value);
CREATE INDEX idx_caa_period              ON compliance_certifications(period_start, period_end);
CREATE INDEX idx_caa_evaluator_job       ON compliance_certifications(evaluator_aap_job_id);
CREATE INDEX idx_caa_regulatory_clauses  ON compliance_certifications USING gin(regulatory_clauses);
```

Notes:

- `compliance_certifications` is **additive** — `compliance_results` stays as-is. New writers populate both. A `compliance_result` row may be linked to one CAA via `(hostname, framework, evaluation_timestamp)` lookup, or via an explicit FK in a later migration.
- `superseded_by` lets us re-issue (e.g., after policy library bump that changes the result) without losing the chain.
- `regulatory_clauses` is an array because one assessment maps to multiple regimes (e.g., a baseline CIS RHEL 9 result speaks to HIPAA, CMMC, and SEC simultaneously).

### 3.2 The CAA bundle (on-disk / object-store format)

```
caa-<certification_id>.tgz
├── manifest.json          # canonical metadata (signed)
├── input.json             # OPA input — the facts evaluated
├── policy/                # the Rego policies used, pinned to policy_library_sha
│   └── ... .rego
├── result.json            # OPA decision document
├── clauses.yml            # clauses mapping in effect at evaluation time
├── attestation.intoto     # in-toto attestation envelope (when sigstore)
└── signatures/
    └── manifest.sig       # detached signature over manifest.json
```

The bundle is the durable artifact. The DB row points at it via `artifact_uri` and stores enough metadata to query without unpacking.

### 3.3 `manifest.json` schema

```json
{
  "schema_version": "1.0",
  "certification_id": "<uuid>",
  "framework": "nerc_cip",
  "framework_version": "v6",
  "scope": "host",
  "scope_value": "bes-asset-001",
  "period": {"start": "...", "end": "..."},
  "evaluator": {
    "aap_job_id": 42,
    "aap_host": "aap-aap.apps.cluster-mvt2r-1.dynamic2.redhatworkshops.io",
    "user": "admin"
  },
  "policy": {
    "library_sha": "ab12cd34...",
    "library_url": "https://github.com/ynotbhatc/rego_policy_libraries",
    "opa_bundle_revision": "..."
  },
  "input_hash": "sha256:...",
  "result_hash": "sha256:...",
  "compliance_status": "non_compliant",
  "severity_summary": {"critical": 0, "high": 3, "medium": 12, "low": 1},
  "regulatory_clauses": [
    "NERC CIP-007-6 R1",
    "NERC CIP-010-3 R1"
  ],
  "generated_at": "2026-06-17T18:00:00Z"
}
```

---

## 4. Signing approach

### 4.1 Recommendation: Sigstore (cosign)

Sigstore is the recommended path. Rationale:

- **Transparency log**: every signature is logged to Rekor. Auditors can verify both "did Red Hat AAC sign this" and "was the signature issued at a time consistent with the period_start/period_end."
- **Aligns with broader regulatory trajectory**: EO 14028 / OMB M-22-09 / EO 14144 increasingly require SLSA / in-toto-style attestations for software supply chain. Same infrastructure serves both.
- **Keyless option**: cosign keyless mode binds signatures to OIDC identities (the AAP user / job), removing customer-side key management overhead.
- **In-toto attestation envelope**: standardized predicate format that an auditor can verify with stock tooling.

### 4.2 Fallback: PGP / age

For customers where Sigstore is not yet acceptable (air-gapped environments, customer-controlled root of trust):

- PGP detached signatures with customer-rotated keys
- `signed_by` records the key fingerprint
- The verifier supports both Sigstore and PGP paths

### 4.3 What gets signed

The **canonical projection** of `manifest.json` (sorted keys, no whitespace, UTF-8 NFC). The `result.json` is referenced by its `result_hash` from the manifest, so signing the manifest signs the verdict transitively. This avoids re-signing large result blobs and lets verifiers detect any tampering of either the manifest or the result.

---

## 5. Clause-mapping layer

### 5.1 Structure

```
policies/mappings/
├── hipaa_security_rule_2025_nprm/
│   ├── README.md
│   └── clauses.yml
├── nerc_cip/
│   ├── clauses.yml
├── cmmc_l2/
│   ├── clauses.yml
├── sec_cybersecurity_disclosure/
├── dora/
├── eo_14028_omb_m_22_09/
├── nis2/
└── tsa_pipeline_2021_02f/
```

### 5.2 `clauses.yml` format

```yaml
# policies/mappings/hipaa_security_rule_2025_nprm/clauses.yml
framework_id:        hipaa_security_rule_2025_nprm
framework_version:   "90 FR 898 (2025-01-06)"
last_reviewed:       2026-06-17

# Maps internal control IDs (from AAC's Rego packages) to specific regulatory clauses.
# An internal control ID may map to multiple clauses; a clause may be cited by
# multiple controls.

mappings:
  CIS_RHEL9_5_2_1:
    clauses:
      - id: "§164.312(c)(1)"
        title: "Integrity controls"
        rationale: "SSH hardening prevents unauthorized modification of ePHI in transit."
      - id: "§164.308(a)(1)(ii)(D)"
        title: "Information system activity review"

  CIS_RHEL9_4_1_1:
    clauses:
      - id: "§164.312(b)"
        title: "Audit controls"

# Clauses NOT yet mapped (gap analysis for future work)
unmapped_clauses:
  - id: "§164.308(a)(7)(ii)(D)"
    title: "Testing and revision procedures"
    note: "Penetration testing cadence — needs new control"
```

### 5.3 Maintenance discipline

- The mapping is **declarative and reviewable** — changes go through PR like any other policy change.
- `last_reviewed` is checked at each AAC release to flag mappings that have drifted from the regulatory text.
- A CI check fails if a Rego control ID is removed from the library while still referenced in `clauses.yml`.

---

## 6. Offline verifier

`aac-verify` — a single static binary (Go preferred for portability; Python with `pyoxidizer` acceptable).

### 6.1 Behavior

```
$ aac-verify path/to/caa-<id>.tgz

✓ Bundle integrity:        manifest.json sha256 matches signed projection
✓ Signature (sigstore):    signed by aap-job-42@cluster-mvt2r-1, 2026-06-17T18:00:01Z
✓ Rekor entry:             https://rekor.sigstore.dev/api/v1/log/entries/...
✓ Policy library SHA:      ab12cd34... (matches bundled policies)
✓ OPA re-evaluation:       result_hash matches re-derived result
✓ Clause mapping:          all 7 referenced clauses present in clauses.yml

Compliance status:         non_compliant
  critical: 0  high: 3  medium: 12  low: 1

Regulatory clauses (NERC CIP-015 R1, R2, R3 + 4 others).
Bundle is verifiable, reproducible, and signed.
```

### 6.2 Failure modes the verifier distinguishes

- **Signature invalid** — tampering or key mismatch
- **Result drift** — re-running OPA against the bundled input + policy produces a different result (most likely cause: OPA version mismatch)
- **Bundle incomplete** — missing input, missing policies, missing manifest
- **Clause mismatch** — `regulatory_clauses` array references clauses not in `clauses.yml` for that framework_version
- **Stale provenance** — `policy_library_sha` no longer exists in `rego_policy_libraries` (likely force-pushed history; bundle still verifiable if the bundled policies are sufficient)

---

## 7. Lifecycle

```
                ┌────────────────┐
                │   AAP job      │
                │   (assessment) │
                └──────┬─────────┘
                       ▼
        ┌──────────────────────────────┐
        │  OPA evaluation              │
        │  (input + policy → result)   │
        └──────┬───────────────────────┘
               ▼
        ┌──────────────────────────────┐
        │  Build manifest.json         │
        │  Pin policy_library_sha      │
        │  Pin opa_bundle_revision     │
        │  Hash input and result       │
        │  Map control IDs to clauses  │
        └──────┬───────────────────────┘
               ▼
        ┌──────────────────────────────┐
        │  Sign manifest               │
        │  (cosign keyless / PGP)      │
        └──────┬───────────────────────┘
               ▼
        ┌──────────────────────────────┐
        │  Write CAA bundle to S3      │
        │  Insert into                 │
        │  compliance_certifications   │
        └──────┬───────────────────────┘
               ▼
        ┌──────────────────────────────┐
        │  Portal / API serves         │
        │  Download bundle             │
        └──────┬───────────────────────┘
               ▼
        ┌──────────────────────────────┐
        │  Auditor runs aac-verify     │
        │  Independent confirmation    │
        └──────────────────────────────┘
```

---

## 8. Roadmap (priority order)

| # | Item | Scope | Risk | Notes |
|---|---|---|---|---|
| 1 | **This spec** lands in `docs/` and is reviewed | Doc only | Low | Sets the contract; everything else descends from it |
| 2 | `compliance_certifications` table + writer playbook | Migration + 1 playbook | Low | Additive to `compliance_results`; no breaking change |
| 3 | Clause-mapping YAMLs for the 8 regimes + CI lint | New directory in `policies/` | Medium | Bulk of the work is the regulatory mapping itself; reviewer matters |
| 4 | Sigstore signing integration in the writer playbook | EE-level + AAP cred change | Medium | Cosign in the EE, keyless OIDC binding via AAP user |
| 5 | `aac-verify` CLI binary | New repo or `tools/aac-verify/` | Medium | Go binary; can ride on existing OPA library |
| 6 | Portal: `GET /api/portal/v1/certifications/<id>/bundle` | Portal API + UI | Low | The customer-facing surface — closes the loop |

### Sequencing

- Items 1-2 are independent; do in parallel.
- Item 3 is the long pole — needs subject-matter review for each of the 8 regimes' clause text. Could be split into 8 PRs (one per regime).
- Item 4 depends on item 2.
- Item 5 depends on items 2 and 4 (verifier needs to know the bundle format and signature format).
- Item 6 is last; it's the customer-facing surface and benefits from the rest stabilizing first.

### Backwards compatibility

`compliance_results` stays unchanged. Existing dashboards, demos, and customer integrations keep working. The CAA is a new product surface alongside, not a replacement.

---

## 9. Open questions

Items that need a decision before this becomes v1.1:

1. **Cosign keyless vs key-based by default.** Keyless requires customer comfort with the Sigstore public log. Air-gapped customers will need key-based.
2. **Bundle storage.** S3 / S3-compatible object store is the obvious answer. Should AAC ship an MinIO container by default for self-hosted, or assume the customer has S3?
3. **Compensating-control attestations.** Property 7 mentions `scope = compensating_control`. The schema supports it but the writer/lifecycle for those isn't designed yet — likely needs a separate sibling playbook driven by a customer-facing form in the portal.
4. **CAA retention.** Regulators want 6-7 years typically. Are bundles immutable, or can they be re-issued (with `superseded_by` linkage) when policies change?
5. **Per-CVE / errata ID granularity.** The talk-track emphasizes "per-CVE, with timestamps and errata IDs." Need an explicit decision: does each CVE remediation generate its own CAA (`scope = control`, `scope_value = CVE-ID`), or does CVE remediation roll up into a host attestation? Probably both, but the relationship needs a model.
6. **Verifier distribution.** Static binary on GitHub Releases? Inside the AAC EE? Part of a `dnf install aac-verify` package? Container image?
7. **Where does the Customer Portal fit?** The portal already has the surface for customer download. Does the portal also become the *generator*, or stay a *consumer* of CAAs produced by AAP?

---

## 10. Glossary

| Term | Meaning |
|---|---|
| **AAC** | Ansible Automated Compliance — the broader platform AAC compliance repo is part of |
| **CAA** | Certifiable Audit Artifact — the deliverable defined by this spec |
| **C3PAO** | CMMC Third-Party Assessment Organization |
| **CIRCIA** | Cyber Incident Reporting for Critical Infrastructure Act |
| **CTPP** | Critical ICT Third-Party Provider (under DORA) |
| **ESP** | Electronic Security Perimeter (NERC CIP) |
| **FCEB** | Federal Civilian Executive Branch |
| **FCI / CUI** | Federal Contract Information / Controlled Unclassified Information (CMMC) |
| **INSM** | Internal Network Security Monitoring (CIP-015) |
| **NPRM** | Notice of Proposed Rulemaking |
| **ZTMM** | Zero Trust Maturity Model (CISA v2.0) |

---

## 11. References

- Red Hat internal **Regulatory Tailwinds for Standardization** talk-track guide (compiled 2026-06-10, v1.0) — the strategic frame this spec descends from
- `rego_policy_libraries` — the policy substrate ([ynotbhatc/rego_policy_libraries](https://github.com/ynotbhatc/rego_policy_libraries))
- Sigstore project documentation — https://docs.sigstore.dev/
- in-toto attestation specification — https://github.com/in-toto/attestation
- AAC `compliance_results` schema (current state) — see `ansible/playbooks/seed_*` for DDL

---

*Researched, drafted, and co-authored with Claude (Anthropic) as engineering review aid. Human-reviewed by the AAC team.*
