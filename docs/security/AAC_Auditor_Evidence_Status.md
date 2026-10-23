# AAC Auditor Evidence — Current State & Roadmap

**Version:** v1.2
**Date:** 2026-10-08
**Status:** Snapshot of shipped evidence + roadmap for pieces still under construction
**Audience:** External auditors, compliance reviewers, engagement teams evaluating AAC's audit readiness
**Owner:** Tim Coulter

> **v1.2 (2026-10-08):** CAA coverage scoped to the frameworks that opt in (CAA writing is per-playbook, not universal); verification described as it is — `psql` extraction plus one `cosign verify-blob`.

---

## 1. Executive summary

AAC (Ansible Automated Compliance) produces a **compliance result** row for every assessment it runs — a summary of how a system scored against a framework — and, for the assessments that opt in to CAA writing (`aac_caa_enabled: true`; the frameworks in §2.2), a **Certifiable Audit Artifact (CAA)** — a cryptographically signed record an auditor can verify offline without any trust in AAC's operational security.

As of 2026-07-02, the frameworks listed in §2.2 write both artifacts; the remaining assessment playbooks write `compliance_results` only until they opt in. Signatures are ECDSA-P256 via Sigstore cosign, keyed against a public key committed to the repo. Verification is `psql` extraction of the stored bytes followed by one standard `cosign verify-blob` against the committed public key.

Three pieces of the CAA specification remain under construction: regulatory clause mapping (linking each finding to a specific regulation), a dedicated auditor verifier CLI (currently auditors use `cosign` directly), and a customer-facing portal endpoint for downloading bundles. None block auditor verification today; they streamline it.

---

## 2. What's shipped

### 2.1 The evidence chain

```
  ┌────────────────┐    ┌──────────┐    ┌───────────────────────┐    ┌───────────────────────┐
  │ AAP job runs   │───▶│ OPA      │───▶│ compliance_results    │───▶│ CAA row (cosign-signed)│
  │ an assessment  │    │ evaluates│    │ (summary of the run)  │    │ + signed_projection   │
  └────────────────┘    └──────────┘    └───────────────────────┘    └───────────────────────┘
                                                                                │
                                                                                ▼
                                                                      ┌──────────────────────┐
                                                                      │  Auditor verifies    │
                                                                      │  offline with cosign │
                                                                      └──────────────────────┘
```

Every step is inspectable, timestamped, and traceable back to a specific AAP job number.

### 2.2 Framework coverage

| Framework | Scope | compliance_results | CAA row | cosign verify |
|---|---|---|---|---|
| CIS RHEL 9 | host (per-system) | ✅ | ✅ | ✅ end-to-end verified |
| CIS RHEL 8 | host | ✅ | ✅ | Awaiting RHEL 8 target |
| CIS Ubuntu 22.04 | host | ✅ | ✅ | Pattern proven via siblings |
| NERC-CIP main (CIP-002…015) | fleet (per-organization) | ✅ | ✅ | ✅ end-to-end verified |
| NERC-CIP CIP-015-1 INSM | fleet | ✅ | ✅ | ✅ end-to-end verified |
| Digital Sovereignty (ENISA/GAIA-X/BSI-C5/IRAP/DORA/CRA) | fleet | ✅ | ✅ | ✅ end-to-end verified |

### 2.3 Storage

Both `compliance_results` and `compliance_certifications` live in PostgreSQL (`compliance-db` in the AAC namespace). Data is retained indefinitely by default — AAC never auto-deletes rows. Multi-year retention is a schema-level guarantee; regulatory retention windows (typically 6–7 years for compliance evidence) are satisfied by not touching what's there.

### 2.4 CAA row — what each field proves

| Field | Meaning for the auditor |
|---|---|
| `certification_id` | Globally unique identifier (UUIDv4) for the artifact |
| `framework` | Which policy family (`cis_rhel9`, `nerc_cip`, `digital_sovereignty`, etc.) |
| `framework_version` | Version of the framework evaluated (e.g., `CIS RHEL 9 Benchmark v2.0.0`) |
| `scope` | `host` (per-system) or `fleet` (per-organization) |
| `scope_value` | Hostname (for host scope), organization name (for fleet scope) |
| `period_start` / `period_end` | Assessment window |
| `evaluator_aap_job_id` | AAP job number that produced this artifact — traceable back through AAP's own audit log |
| `policy_library_sha` | Git commit SHA of the Rego policy library that evaluated this system. May instead be `project:<sha>` — the parent-repo commit, when AAP's execution environment strips the submodule's git metadata. Both are complete provenance pointers; see [CAA_VERIFICATION.md](CAA_VERIFICATION.md) for how to dereference the `project:` form. **A `project:` SHA will not resolve in the policy library — it belongs to the parent repo.** |
| `input_hash` | SHA-256 of the canonical facts fed into OPA — proves the same input reproduces the same result |
| `result` | Full OPA decision document (framework-specific fields: `compliance_percentage`, `violations`, etc.) |
| `compliance_status` | `compliant`, `non_compliant`, or `partial` |
| `severity_summary` | Breakdown by severity (`critical`, `high`, `medium`, `low`, `unclassified`) |
| `signature` | Cryptographic signature (BYTEA) — ECDSA-P256 |
| `signature_algorithm` | `cosign-ecdsa-p256` |
| `signed_by` | Key identifier (currently `cosign-key-v1`) |
| `signed_at` | Timestamp of signing |
| `signed_projection` | The **exact bytes** cosign signed — enables byte-for-byte offline verification |

### 2.5 Signing model

- **Cosign v2.6.3 key-based signing** — ECDSA-P256 private key, held in the AAP vault, never touches disk during signing (passed via `env://COSIGN_PRIVATE_KEY`).
- **Public key** committed to the repository at [`docs/security/caa-signing-key-v1.pub`](caa-signing-key-v1.pub). This is the reference an auditor uses to verify signatures.
- **No Rekor transparency log** — signing is fully offline-capable and works in air-gapped customer deployments.
- **Key rotation path** in place: bumping to `cosign-key-v2` involves publishing `caa-signing-key-v2.pub` alongside v1, updating `aac_caa_signing_key_id`, replacing the vault key. Old rows remain verifiable against `caa-signing-key-v1.pub` forever.

---

## 3. How auditors verify a CAA (offline)

> **Extract the projection byte-exactly.** `psql` appends a trailing newline that is
> not part of the signed bytes; piping it straight to a file makes `cosign` report
> `invalid signature` **on a valid record**. Use `printf '%s' "$(psql ...)"`. Verified
> live 2026-07-31 — full procedure and tamper matrix in
> [CAA_VERIFICATION.md](CAA_VERIFICATION.md).

Two `psql` extractions, then one `cosign verify-blob`. Needs read access to the database (or, once item 6 ships, an exported bundle) and `cosign` — nothing else from AAC.

```bash
# 1. Pull the exact signed bytes and the signature
CERT_ID='<the-uuid-you-are-verifying>'

psql -U postgres -d compliance -tAc \
  "SELECT signed_projection FROM compliance_certifications
   WHERE certification_id = '$CERT_ID';" \
  > /tmp/caa_projection.json

psql -U postgres -d compliance -tAc \
  "SELECT encode(signature, 'base64') FROM compliance_certifications
   WHERE certification_id = '$CERT_ID';" \
  | tr -d '\n' > /tmp/caa.sig

# 2. Verify with cosign against the committed public key
cosign verify-blob \
  --key docs/security/caa-signing-key-v1.pub \
  --signature /tmp/caa.sig \
  --insecure-ignore-tlog \
  /tmp/caa_projection.json

# Expected output: "Verified OK"
```

`--insecure-ignore-tlog` is correct here — AAC's signing is key-based, not keyless-with-Rekor.

Any tampering with `signed_projection` or `signature` after they were written produces a signature failure — this is exactly the tamper-evidence property regulators expect.

Full verification walkthrough: [`CAA_VERIFICATION.md`](CAA_VERIFICATION.md)

---

## 4. What's under construction

The remaining CAA specification items either streamline verification or add regulatory linkage. None block the core "auditor can verify a CAA" workflow.

| Item | What it adds | Estimated effort | Priority |
|---|---|---|---|
| **Regulatory clause mapping** | Every finding tagged with a specific regulatory clause (HIPAA §164.312(c)(1), NERC CIP-007-6 R2.1, etc.) | 3–5 weeks (SME-dependent) | High — this is the value narrative auditors care about most |
| **`aac-verify` CLI** | Single binary auditors install once and run against any CAA. Wraps the extract-then-verify procedure into `aac-verify <cert-id>`. | 2–3 days (Python MVP) or 1 week (Go binary) | Medium — reduces auditor effort but not strictly required |
| **Portal CAA endpoint + UI** | Customer-facing web download of a self-contained bundle (projection + signature + public key + verification instructions) | 3–4 days | Medium — makes AAC visible outside the AAC perimeter |
| **Bundle storage in S3/MinIO** | `artifact_uri` gets populated with a downloadable location | Small | Low — depends on the portal endpoint |
| **OPA bundle revision pinning** | `opa_bundle_revision` captures the exact bytes OPA served, in addition to the git SHA | Small | Low — nice-to-have for OPA-bundle-hosted deployments |
| **Per-CVE granularity** | Where regulations demand per-CVE evidence (HIPAA NPRM, CISA EO 14028), one CAA per CVE rather than aggregated per assessment | Medium — needs design decision | Medium — regulation-dependent |
| **Compensating control scope** | Customer-declared "I can't patch this, here's what I'm doing instead" — self-attested CAAs signed by the customer | Small once portal ships | Low until a customer asks |

### Detail on the largest item — clause mapping

For each of the 8 priority regulatory regimes (HIPAA NPRM, NERC CIP, CMMC L2, SEC Cyber Disclosure, EU DORA, EO 14028 / OMB M-22-09, NIS2, TSA Pipeline), AAC will publish a YAML mapping file at `policies/mappings/<regime>/clauses.yml` that pairs each policy control ID with the regulatory clause(s) it satisfies. The CAA row's `regulatory_clauses` column (currently empty array) will then populate automatically.

This is the calendar bottleneck — each regime needs domain SME review, and mapping is bulk regulatory work, not engineering. Pulling in a compliance SME or paying for an auditor review pass shortens the timeline.

---

## 5. Retention and lifecycle

- **PostgreSQL retention:** indefinite. AAC never auto-deletes rows.
- **Immutability:** CAA rows are append-only. Corrections use a `superseded_by` chain rather than in-place edits — the historical row stays verifiable.
- **Backups:** delegated to the deployment's PostgreSQL backup policy (customer-managed or via the AAC install helm chart's PVC backup).
- **Documented retention policy:** *under construction.* A minimum-6-year policy doc is on the roadmap.

## 6. Key rotation

Current signing key: **v1** (public key at [`caa-signing-key-v1.pub`](caa-signing-key-v1.pub)).

When a rotation happens:
1. Generate the new keypair.
2. Publish `caa-signing-key-vN.pub` alongside v1 (v1 stays available so historical CAAs stay verifiable).
3. Update AAC's signing key configuration.
4. New CAAs carry `signed_by = 'cosign-key-vN'`.

Full procedure: [`CAA_VERIFICATION.md`](CAA_VERIFICATION.md) §"Key rotation".

---

## 7. References

- `docs/strategy/AAC_CERTIFIABLE_AUDIT_ARTIFACT_SPEC.md` — the CAA data model specification
- `docs/strategy/AAC_CERTIFIABLE_AUDIT_RESULTS_STATUS.md` — engineering roadmap tracker (internal)
- `docs/security/CAA_VERIFICATION.md` — auditor verification procedure (step-by-step)
- `docs/security/caa-signing-key-v1.pub` — current CAA signing public key
- [Sigstore cosign documentation](https://docs.sigstore.dev/cosign/)
- [Open Policy Agent (OPA) documentation](https://www.openpolicyagent.org/docs/)

---

*Researched, drafted, and co-authored with Claude (Anthropic) as engineering documentation aid. Human-reviewed by the AAC team.*
