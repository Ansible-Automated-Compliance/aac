# AAC Terraform Replacement — provider-native infrastructure under AAP

**Version:** v0.1
**Date:** 2026-10-18
**Authors:** Tim Coulter · Claude (Anthropic)
**Status:** plan for the goal after the public cut. Nothing built. Decisions in section 9.
**Builds on:** `docs/integration/AAP_TERRAFORM_PROVIDERS_RESEARCH.md` v0.2 (the feasibility research)

---

## 1. The goal in one paragraph

AAP becomes the only control plane for infrastructure, and AAC becomes its state and evidence
store. Terraform providers stay exactly as they are (MPL 2.0 binaries from the registry); the
Terraform CLI, HCL and `terraform.tfstate` go away. An Ansible module launches the provider,
speaks its gRPC protocol, asks it to plan the change, puts the planned diff through OPA, applies
it, and records the resulting resource state and the decision in the compliance database. Every
infrastructure change is therefore planned by the vendor's own provider, gated by policy, applied
under AAP's credentials and RBAC, and stored as evidence next to the assessment that reads it
back. The same module, in read-only mode, turns any provider resource into facts for assessment.

What this is **not**: an HCL interpreter, a registry-module runtime, or a Terraform Cloud
replacement. Teams invested in HCL modules keep OpenTofu inside an EE via `cloud.terraform`.

## 2. Sequence

| When | What |
|---|---|
| Now to ~2026-10-30 | Finish the reorganisation (R1–R6) and the public cut. Nothing here starts before the cut |
| Immediately after the cut | Phase 0 spike (section 5) in the public repository, on a branch |
| Then | Phases 1 to 4 in order; each has an exit gate proven on the lab |

Total: about 13 to 16 weeks of one engineer plus Claude, with Juan reviewing. Phase 1 alone is a
shippable product increment (provider-backed assessment); phases 2 to 4 are the replacement.

## 3. Architecture

```
AAP job template ──► playbook ──► aac.tfprovider.resource (Ansible module, Python)
                                      │ 1. load prior state        ◄── compliance DB: provider_state
                                      │ 2. PlanResourceChange     ◄──► provider binary (gRPC, tfplugin6/5)
                                      │ 3. OPA: allow/deny diff    ◄──► opa-compliance, package provider_change.main
                                      │ 4. ApplyResourceChange    ◄──► provider binary
                                      │ 5. store state + decision  ──► provider_state, provider_change_log
                                      ▼
                                   changed / failed / denied
```

| Component | Where | What it is |
|---|---|---|
| `aac-provider-ee` | `ansible/execution-environments/aac-provider-ee/` | ubi9 EE: Python gRPC stubs generated from `tfplugin6.proto` and `tfplugin5.proto`, `msgpack`, and the pinned provider binaries a profile selects. Providers are fetched from the registry API at build time, checksum- and signature-verified, never at job time |
| `aac.tfprovider` collection | `collections/ansible_collections/aac/tfprovider/` | Modules `schema`, `data_read`, `resource_read`, `resource` (plan / apply / destroy), `state_import`, `state_export`; one action plugin that keeps a provider process alive for the play and tears it down at the end |
| Provider process manager | inside the collection | Launches the binary with the magic cookie, reads the handshake line, opens the gRPC channel (mTLS when the host passes a cert), caches `GetProviderSchema` per provider version, serialises calls. One process per provider per play |
| `provider_state`, `provider_state_history`, `provider_change_log` | compliance DB, `ansible/files/provider_state_schema.sql` | The state store (section 4) |
| `aac_store_provider_state` role | `ansible/roles/` | The single writer for those tables, like `aac_store_results` is for evidence |
| `provider_change` Rego package | `policies/enforcement/provider/` in the policy library | Input: the planned diff; output: allow or deny with reasons. Routed through `opa_framework_map` key `provider_change` → compliance bucket, next to `sentinel_terraform` |
| Credentials | AAP credential types | The provider reads the environment it already knows (`AWS_*`, `ARM_*`, `GOOGLE_*`, `KUBECONFIG`). No provider-specific credential code |

## 4. The state store

One row per resource, keyed by the address the playbook gives it.

| Column | Meaning |
|---|---|
| `address` (PK with `environment`) | `aws_s3_bucket.evidence`, chosen by the playbook; renames go through `state_move` |
| `environment` | profile name (`customer`, `rhpds`, `lab`) |
| `provider`, `provider_version`, `protocol_version` | `registry.terraform.io/hashicorp/aws`, `5.70.0`, `6` |
| `resource_type`, `schema_version` | `aws_s3_bucket`, the provider's schema version at write time; `UpgradeResourceState` runs on read when it differs |
| `attributes` (JSONB) | The provider's new state after apply, decoded by schema |
| `private` (BYTEA) | The provider's opaque blob, stored byte-exact |
| `sensitive_paths` (JSONB) | Attribute paths the schema marks sensitive; those values are encrypted at rest with the evidence key and redacted in job output |
| `last_job_id`, `last_change_id`, `updated_at` | Provenance |

`provider_state_history` keeps every prior row (append-only, same discipline as
`evidence_append_only.sql`). `provider_change_log` records one row per `resource` module run:
address, planned action (`create` / `update` / `replace` / `delete` / `no-op`), the diff, the OPA
decision and reasons, operator, job id, outcome. Locking is `SELECT … FOR UPDATE` on the state row
for the duration of plan + apply.

## 5. Phases

### Phase 0 — spike (1 to 2 weeks)

Prove the protocol end to end with one provider, read-only.

- Generate Python stubs from the proto files; write the process manager (handshake, channel,
  schema cache); decode `DynamicValue` by schema.
- `aac-provider-ee` with `hashicorp/aws` pinned; build through `build_domain_ee.yml`.
- `data_read` on `aws_instances` and `resource_read` on one `aws_s3_bucket` against the AWS lab
  account; feed the JSON to the existing `cis_aws` policy; store through `aac_store_results`.
- CI: unit tests against `hashicorp/null` and `hashicorp/random`, two tiny MPL providers that
  need no credentials; the EE build verifies checksums and signatures.

**Exit gate:** a `compliance_results` row on the lab whose facts came from a provider over gRPC,
and a CI job that drives the `null` provider.

### Phase 1 — provider-backed assessment, shippable (3 to 4 weeks)

- Five providers pinned: `aws`, `azurerm`, `google`, `kubernetes`, `vsphere` (matches the CIS
  cloud and Kubernetes frameworks AAC already carries).
- Protocol 5 support for providers that still serve it; schema cache on disk in the EE.
- A generic playbook `provider_assessment.yml` (survey: provider, resource type or data source,
  framework key) using the routing pattern; seeder adds the template.
- Documentation: install (profile keys for provider pins and credentials), operate, extend
  (adding a provider); support matrix row.

**Exit gate:** the six Definition-of-Done items from the extraction plan (§8) applied to this
collection; `cis_aws`, `cis_azure`, `cis_gcp` and `cis_kubernetes` each evaluated from
provider facts on the lab.

### Phase 2 — state and apply, the replacement proper (3 to 4 weeks)

- Schema SQL, the store role, `resource` module with `state: present | absent`, check mode
  (plan only, no apply), `--diff` output from the planned change.
- The OPA gate: `provider_change.main` with a first policy set (deny public S3, deny 0.0.0.0/0
  ingress, deny replace of resources tagged `protected`, require tags). A denied change is
  recorded, reported, and not applied.
- Sensitive handling, row locking, `UpgradeResourceState` on schema drift, `state_move`.
- Destroy is an explicit playbook with `state: absent` tasks in reverse order; no implicit
  dependency graph.

**Exit gate:** on the AWS lab, one playbook creates a VPC, security group and S3 bucket; a second
run is idempotent (`changed=0`); a modification is applied; a non-compliant modification is
denied by OPA with the reason in the job output and the change log; `state: absent` tears it down;
every step has a `provider_change_log` row.

### Phase 3 — migration from Terraform (2 weeks)

- `state_import`: read `terraform.tfstate` (format version 4) and populate `provider_state`,
  preserving `private` and schema versions.
- `playbook_from_state`: emit a playbook skeleton (one `resource` task per resource, current
  attributes as desired config) so a customer's estate becomes AAP-managed in one step.
- Document "Moving from Terraform": what carries over (providers, state, credentials), what does
  not (HCL modules, workspaces, remote backends, Sentinel policies — the Rego library replaces the
  last).

**Exit gate:** a Terraform-managed lab estate imported, assessed and modified under AAP with no
Terraform binary present.

### Phase 4 — hardening and release (2 to 3 weeks)

- Parallel reads across resources; provider process reuse across plays where AAP allows.
- Failure contract: provider crash, schema mismatch, registry unavailable, lock contention — each
  fails closed with a named reason.
- Demo in aac-demos (the Comply demo's Terraform act becomes provider-native), blog, and the
  support-matrix tier (**Supported**, profile-driven, 2.6+).
- Release as AAC minor version with the collection at 1.0.0.

## 6. Design decisions taken in this plan

| Decision | Choice | Why |
|---|---|---|
| Language | Python inside the collection | Same runtime as every other AAC module; stubs generated from the proto; no second toolchain to ship. A Go sidecar is the fallback if MessagePack decoding or gRPC performance disappoints in Phase 0 |
| Where the client lives | `aac.tfprovider` in the product repository, extracted later like `aac.m365` (extraction plan E1–E3) | Shares the EE build, CI gates and release train from day one |
| Provider acquisition | Build-time, pinned per profile, verified | Job-time downloads are a supply-chain hole and fail without egress |
| Resource identity | Playbook-given address, plus `state_move` | Mirrors Terraform addresses; survives renames |
| Dependency ordering | Task order; no graph | Ansible is sequential, so every value is known when the next task runs. Destroy playbooks are written in reverse |
| Policy gate | OPA on the planned diff, in the module, before apply | The one thing Terraform cannot do at this granularity; it is AAC's reason to exist |
| Evidence | State plus change log in the compliance DB, append-only history | Same discipline as assessment evidence; one audit trail |
| Not supported | HCL, registry modules, workspaces, remote backends | Say it in the README's first lines |

## 7. Risks

| Risk | Mitigation |
|---|---|
| Schema-aware MessagePack decoding of `DynamicValue` (nested, unknown and null markers) | Phase 0 proves it on the AWS schema, the largest in common use; fall back to JSON encoding where the provider offers it |
| Providers that only serve protocol 5 | Generate both stub sets; the process manager picks from the handshake line |
| `GetProviderSchema` size and provider start-up time | Cache the schema per provider version; one process per play |
| Sensitive attributes in state and job output | Schema marks them; encrypt at rest, redact in output, test both |
| Provider private blob must round-trip exactly | `BYTEA`, never decoded; a test asserts byte equality across a plan/apply cycle |
| Terraform compatibility expectations from customers | README and the migration doc state the boundary; `state_import` covers the estate, not the modules |
| Registry supply chain | Checksums and GPG signatures verified at EE build; providers pinned by exact version |

## 8. What it gives AAC that Terraform does not

- A policy decision on every planned change, with the reason stored, before anything changes.
- Infrastructure state and compliance evidence in one database, one audit trail, one RBAC.
- Assessment that reads the same provider the change went through, so drift is measured against
  the vendor's own view of the resource.
- No BUSL binary in the product.

## 9. Decisions

1. Go on this plan as the goal after the cut, Phase 0 first.
2. Phase 1 ships as its own increment (provider-backed assessment) before Phase 2 starts.
3. Name of the collection: `aac.tfprovider` (proposed), or `aac.provider`.
4. The first provider set in Phase 1 (proposed: aws, azurerm, google, kubernetes, vsphere).

---

| Version | Date | Change |
|---|---|---|
| v0.1 | 2026-10-18 | First plan, from the v0.2 research and Tim's direction "the next goal after the migration" |
