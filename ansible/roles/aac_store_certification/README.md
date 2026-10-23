# aac_store_certification

Single authoritative INSERT for the `compliance_certifications` table — produces
a Certifiable Audit Artifact (CAA) row.

See [`docs/strategy/AAC_CERTIFIABLE_AUDIT_ARTIFACT_SPEC.md`](../../../docs/strategy/AAC_CERTIFIABLE_AUDIT_ARTIFACT_SPEC.md)
for the data model and design rationale.

## What it does

For every assessment that runs through `aac_store_results`, optionally also
write a `compliance_certifications` row capturing:

- **Provenance** — `policy_library_sha` (pinned from the `rego_policy_libraries`
  submodule pointer), `evaluator_aap_job_id`, `signed_by`, `signed_at`.
- **Reproducibility** — `input_hash` (sha256 of the canonicalized OPA input)
  and the full `result` JSONB, so a verifier can re-run OPA and confirm.
- **Integrity** — a `signature` over a canonical projection of the
  certification fields.

### Signature (since PR #288, 2026-07-02)

`signature_algorithm = "cosign-ecdsa-p256"`, `signed_by = "cosign-key-v1"` — the
canonical projection is signed with `cosign sign-blob` using an ECDSA-P256 private key
sourced from the vault via `env://COSIGN_PRIVATE_KEY`. The role asserts the key is
configured and refuses to write an unsigned row. The exact signed bytes are stored in
`signed_projection`; verify offline per `docs/security/CAA_VERIFICATION.md`. Rows written
before PR #288 carry the earlier `sha256-unsigned` placeholder and are not cosign-verifiable.

### Clause mapping in v1.0 (this role)

`regulatory_clauses` is written as an empty array. Clause-mapping YAMLs are
item 3 of the CAA roadmap; until then, CAAs prove provenance + integrity but
do not yet claim specific regulatory clauses.

## Usage

Direct call:

```yaml
- name: Store CIS RHEL 9 certification
  include_role:
    name: aac_store_certification
  vars:
    aac_caa_framework:         "cis_rhel9"
    aac_caa_framework_version: "v2.0.0"
    aac_caa_scope:             "host"
    aac_caa_scope_value:       "{{ inventory_hostname }}"
    aac_caa_result:            "{{ opa_decision }}"
    aac_caa_input:             "{{ opa_input }}"
    aac_caa_violations:        "{{ violations }}"
    aac_caa_compliance_status: "{{ 'compliant' if is_compliant else 'non_compliant' }}"
```

Via `aac_store_results` (set `aac_caa_enabled: true`, the chain calls this role
automatically):

```yaml
- include_role:
    name: aac_store_results
  vars:
    aac_result_policy_name: "CIS RHEL 9"
    # ... other aac_result_* vars ...
    aac_caa_enabled:           true
    aac_caa_framework:         "cis_rhel9"
    aac_caa_result:            "{{ opa_decision }}"
    aac_caa_input:             "{{ opa_input }}"
    aac_caa_compliance_status: "{{ 'compliant' if is_compliant else 'non_compliant' }}"
```

## Required vars

| Variable | Description |
|----------|-------------|
| `aac_caa_framework` | Framework key, e.g. `cis_rhel9`, `nerc_cip`, `hipaa` |
| `aac_caa_scope_value` | Hostname (host scope), fleet id, etc. |
| `aac_caa_result` | OPA decision document (mapping) |
| `aac_caa_input` | OPA input that produced the result (used for `input_hash`) |
| `aac_caa_compliance_status` | One of `compliant`, `non_compliant`, `partial` |

## Output

| Fact | Description |
|------|-------------|
| `aac_certification_id` | UUID of the inserted CAA row |
