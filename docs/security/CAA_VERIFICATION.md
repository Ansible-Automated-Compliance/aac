# Verifying a Certifiable Audit Artifact (CAA)

**Version:** v1.1
**Applies to:** CAAs signed by AAC with `signature_algorithm = 'cosign-ecdsa-p256'` and `signed_by = 'cosign-key-v1'`
**Audience:** External auditors, compliance reviewers, anyone who needs to independently confirm a CAA row hasn't been tampered with

---

## Prerequisites

- **cosign** v2.x installed locally — `brew install cosign`, `go install github.com/sigstore/cosign/v2/cmd/cosign@latest`, or download from https://github.com/sigstore/cosign/releases (any v2.x tag works; the AAC EE uses v2.6.3)
- **The CAA row** you want to verify — either as a direct query result from `compliance_certifications` or as an exported bundle
- **The AAC public key** — [`caa-signing-key-v1.pub`](./caa-signing-key-v1.pub) in this same directory

## What you're verifying

A CAA signature covers a **canonical projection** of these fields:

| Field | Meaning |
|---|---|
| `certification_id` | UUID that uniquely names the CAA |
| `framework` | e.g., `cis_rhel9`, `nerc_cip` |
| `framework_version` | e.g., `v2.0.0`, `CIP-002 through CIP-015` |
| `scope` | `host`, `fleet`, `control`, or `compensating_control` |
| `scope_value` | Hostname (for host scope), organization (for fleet), etc. |
| `period_start` / `period_end` | Assessment window |
| `evaluator_aap_job_id` | AAP job that ran the assessment |
| `policy_library_sha` | The `rego_policy_libraries` commit — or `project:<sha>`, see below |
| `input_hash` | sha256 of the canonical OPA input |
| `result` | The full OPA decision document |
| `compliance_status` | `compliant`, `non_compliant`, or `partial` |

If ANY of these change after signing, `cosign verify-blob` fails.

**Note on cert_id and reproducibility.** The projection embeds a random `certification_id` (UUIDv4) generated at row-write time. This means the same host, same policies, same OPA input, run twice — produces two **different** signatures. That's by design (each CAA is a discrete artifact). What verification proves is: *this specific row was signed by AAC and hasn't been tampered with since*. It does NOT prove "this input has ever produced a compliant CAA before" — for that, query the DB by `input_hash` (which IS deterministic on the same input).

### Dereferencing a `project:<sha>` policy_library_sha

When AAP's execution environment strips the submodule's git metadata, the field
records the **parent repository's** commit instead, prefixed `project:`. It is
still a complete provenance pointer — resolve it in two steps:

```bash
# policy_library_sha = project:c3d4ffec41edece36e48dbeb91281629e5c81dc4
git clone https://github.com/ansible-automated-compliance/aac && cd compliance
git ls-tree c3d4ffec41edece36e48dbeb91281629e5c81dc4 policies
# 160000 commit 7980372494ba09208f5dacffe36fd284edeb4423  policies
#                ^ the rego_policy_libraries commit that evaluated this system
```

Look that second SHA up in `ynotbhatc/rego_policy_libraries` to read the exact
policies. **Do not look a `project:` SHA up in the policy library directly** —
it belongs to the parent repository and will not resolve there.

---

## Verify from a Postgres query

The row stores the exact signed bytes in `signed_projection` so verification is a pure lookup — no reconstruction required.

> ### ⚠️ The trailing-newline trap — read this before you run anything
> `psql` appends a newline to its output. The signature covers the projection
> **exactly as signed**, with no trailing newline, so piping `psql` straight to a
> file produces one byte too many and `cosign` reports **`invalid signature`
> on a perfectly valid record**.
>
> The commands below strip it with `printf '%s'`. If you adapt them, keep that.
> A quick sanity check — these two numbers must match:
>
> ```bash
> wc -c < /tmp/caa_projection.json                    # bytes you extracted
> psql -U postgres -d compliance -tAc \
>   "SELECT octet_length(signed_projection) FROM compliance_certifications
>    WHERE certification_id = '$CERT_ID';"            # bytes that were signed
> ```

```bash
CERT_ID='<the-uuid-you-are-verifying>'

# 1. Pull the signed projection bytes to a file — printf '%s' strips psql's
#    trailing newline, which is NOT part of the signed bytes.
printf '%s' "$(psql -U postgres -d compliance -tAc \
  "SELECT signed_projection FROM compliance_certifications
   WHERE certification_id = '$CERT_ID';")" \
  > /tmp/caa_projection.json

# 2. Pull the base64-encoded signature to a file
psql -U postgres -d compliance -tAc \
  "SELECT encode(signature, 'base64') FROM compliance_certifications
   WHERE certification_id = '$CERT_ID';" \
  | tr -d '\n' > /tmp/caa.sig

# 3. Confirm the algorithm and key id (should be cosign-ecdsa-p256 / cosign-key-v1)
psql -U postgres -d compliance -c \
  "SELECT signature_algorithm, signed_by FROM compliance_certifications
   WHERE certification_id = '$CERT_ID';"

# 4. Verify
cosign verify-blob \
  --key docs/security/caa-signing-key-v1.pub \
  --signature /tmp/caa.sig \
  --insecure-ignore-tlog \
  /tmp/caa_projection.json

# Expected output: "Verified OK"
# Any tampering → "Error: invalid signature ..."
```

**Verified end-to-end on 2026-07-31** against a live CAA (`cosign-ecdsa-p256` /
`cosign-key-v1`, 819-byte projection, 70-byte DER signature): the genuine
artifact returns `Verified OK`, and each of these returns `invalid signature` —

| Tamper | Result |
|---|---|
| `compliance_status` altered, same byte length | `invalid signature` |
| `evaluator_aap_job_id` altered | `invalid signature` |
| A single trailing space appended | `invalid signature` |

The last row is the point of the warning above: **one stray byte is
indistinguishable from tampering.** That is correct cryptographic behaviour —
which is exactly why the extraction must be byte-exact.

`--insecure-ignore-tlog` is correct here — AAC's CAAs are **not** logged to Rekor. This is key-based signing, not keyless-with-transparency-log.

**Historical rows without `signed_projection`.** CAAs written before this column was added (see PR that introduced the column) have `signed_projection = NULL`. To verify those, reconstruct the canonical projection from the other columns — but note that PG's JSONB round-trip does not guarantee byte-identical output, so verification may require manual reformatting. The clean fix is to re-sign old rows; the practical fix is to treat pre-column rows as provenance-only.

## Verify from an exported bundle

TBD once the CAA portal export (spec item 6) ships. The bundle format will include:
- The `projection` JSON (byte-exact)
- The `signature` (base64)
- A copy of the public key
- Optionally, the raw OPA input if included in the export

Auditor runs:
```bash
cosign verify-blob --key key.pub --signature caa.sig --insecure-ignore-tlog projection.json
```

## Key rotation

- Current signing key: **v1** (2026-07-02 — see git history for exact commit)
- Public key: [`caa-signing-key-v1.pub`](./caa-signing-key-v1.pub)
- CAAs signed with v1 will have `signed_by = 'cosign-key-v1'`

When the signing key rotates, this repo will publish `caa-signing-key-v2.pub` alongside v1 (v1 remains available so historical CAAs stay verifiable). CAAs signed with v2 will carry `signed_by = 'cosign-key-v2'`.

Rotation procedure:
1. Generate new keypair: `COSIGN_PASSWORD="" cosign generate-key-pair`
2. Update `aac_caa_signing_key_id` to `cosign-key-vN` in `aac_store_certification/defaults/main.yml`
3. Commit `caa-signing-key-vN.pub` to `docs/security/`
4. Update the vault: replace `caa_signing_private_key` with the new PEM content
5. Rebuild the EE (or restart affected AAP jobs)

## References

- [Cosign documentation](https://docs.sigstore.dev/cosign/)
- [`ansible/roles/aac_store_certification/tasks/main.yml`](../../ansible/roles/aac_store_certification/tasks/main.yml) — the signing task
- [`docs/strategy/AAC_CERTIFIABLE_AUDIT_ARTIFACT_SPEC.md`](../strategy/AAC_CERTIFIABLE_AUDIT_ARTIFACT_SPEC.md) — the CAA data model spec
- [`docs/strategy/AAC_CERTIFIABLE_AUDIT_RESULTS_STATUS.md`](../strategy/AAC_CERTIFIABLE_AUDIT_RESULTS_STATUS.md) — roadmap status

---

*Researched, drafted, and co-authored with Claude (Anthropic) as engineering documentation aid. Human-reviewed by the AAC team.*
