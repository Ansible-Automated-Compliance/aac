# Can AAP talk to Terraform providers directly?

**Version:** v0.3
**Date:** 2026-10-18
**Authors:** Tim Coulter · Claude (Anthropic)
**Status:** research; nothing built. Decision requested in section 7.

---

## 1. Verdict

Yes. A Terraform provider is a standalone executable that serves a gRPC API; the Terraform CLI
is only one client of that API. Anything that can launch the binary, complete the go-plugin
handshake and speak the `tfplugin6` (or `tfplugin5`) protocol can call a provider. Two facts
make this credible rather than theoretical: the protocol is published and stable, and
Crossplane's Upjet already runs providers without the Terraform CLI in production, though it
does so **in-process in Go** (section 3), not over an external gRPC connection. HashiCorp's
own providers stay under MPL 2.0, so the licensing is clean. The external-client path proposed
here is therefore protocol-proven but **not** production-proven by anyone we found; Phase 0 of
the plan exists to prove it.

For AAC that means two routes, both of which keep AAP as the only orchestrator:

| Route | What runs inside the EE | What AAC gains | Cost |
|---|---|---|---|
| **A. Engine in the EE** | OpenTofu (MPL 2.0) or Terraform CLI driven by the certified `cloud.terraform` collection | Plan, apply and state with no new code; HCL stays the language | Days. Still "Terraform inside AAP" |
| **B. AAP speaks the provider protocol** | A provider broker plus Ansible modules that launch the provider binary and call it over gRPC; no engine, no HCL, no state file | Read the resources a provider exposes through data sources or importable resource types, as facts for OPA, through the existing facts → OPA → PostgreSQL spine. Not every registry resource: see section 2a | Weeks for a read-only proof; a new protocol client to own |

Recommendation: build the Route B proof for **read-only assessment** first, because that is the
part nobody ships and it fits AAC's assessment-first rule. Then extend it to apply with **AAC as
the state store** (section 6a): the provider computes every diff itself, so AAC only has to keep
the per-resource state, which is a table in the database it already runs. Route A remains the
answer for teams invested in HCL modules.

## 2. How a provider actually works

Verified against the `terraform-plugin-go` server code and the go-plugin internals document.

1. The host launches the provider binary with two environment variables:
   `TF_PLUGIN_MAGIC_COOKIE=d602bf8f470bc67ca7faa0386276bbdd4330efaf76d1a219cb4d6991ca9872b2` and
   `PLUGIN_PROTOCOL_VERSIONS=6` (or `5,6`). Without the cookie the binary refuses to serve.
2. The provider prints one handshake line to stdout:
   `CORE-PROTOCOL-VERSION|APP-PROTOCOL-VERSION|NETWORK-TYPE|NETWORK-ADDR|PROTOCOL[|TLS-CERT]`,
   for example `1|6|unix|/tmp/plugin123|grpc|...`. go-plugin negotiates mutual TLS automatically
   when the host passes a client certificate; otherwise the socket is plain.
3. The host opens a gRPC connection to that socket and calls the `tfplugin6.Provider` service:
   `GetProviderSchema`, `ValidateProviderConfig`, `ConfigureProvider`, then per resource
   `ReadDataSource`, `ImportResourceState`, `ReadResource`, `UpgradeResourceState`,
   `PlanResourceChange`, `ApplyResourceChange`, and `StopProvider`.
4. Values cross the wire as `DynamicValue` objects: MessagePack (or JSON) encoded against the
   schema returned by `GetProviderSchema`. A client must decode them schema-aware.

`TF_REATTACH_PROVIDERS` is the reverse direction (attach the CLI to a provider you started) and
is for debugging only; it is not the mechanism for this.

## 2a. What the protocol does and does not give a reader

The protocol is not a discovery API. Three limits shape Route B's scope:

- **`ReadResource` refreshes, it does not find.** It takes the provider-shaped current state
  (at minimum the resource's `id` and required attributes) and returns the refreshed state. A
  caller that has only an identifier must first go through `ImportResourceState`.
- **Import is optional per resource type.** A provider implements it only for resource types
  whose authors wrote an importer (`ResourceImporter`). Most mainstream AWS, Azure and GCP
  resources have one; many do not, and the import identifier format is resource-specific.
- **Data sources need type-specific configuration and are not uniformly listings.** Some list
  (`aws_instances`), many return one object by filter, and the plural form does not exist for
  every type. Each one AAC uses has to be tested and its required inputs documented.

Route B is therefore scoped to **tested data sources and importable resource types**, with
discovery (which identifiers to import), per-type configuration, import-identifier formats
and an explicit "unsupported resource type" outcome as part of the estimate, not an
afterthought. The honest headline is "any resource a provider can import or list", not "any
resource of any provider".

## 3. Who already does it without the Terraform CLI

- **Crossplane Upjet** lists three execution modes: "Terraform CLI: traditional fork-based
  Terraform CLI and Terraform provider process spawning", "Terraform Plugin SDK v2: direct Go
  library integration (no-CLI invocation)" and "Terraform Plugin Framework: protocol-based
  communication via protov6 (no-CLI invocation)". Upbound moved the GCP provider off the CLI at
  v0.40.0 and removed the Terraform binary from the package. Their stated reasons: the CLI was
  never built for continuous reconciliation, and dropping it avoids the BUSL question.
  **Precision matters here:** both no-CLI modes link the provider's Go code into the Upjet
  binary. The Framework mode builds `providerserver.NewProtocol6(provider)()` and calls the
  returned Go interface in-process; the protov6 messages never cross a socket. Upjet proves
  that providers run fine without the CLI and that the protov6 contract is a usable API. It
  does **not** prove the external-binary-over-gRPC client this document proposes.
- **Pulumi's Terraform bridge** connects the Pulumi engine to a provider's Go code in-process.
  Same idea, Go only.
- **Client code is thin on the ground.** `terraform-plugin-go` is the *server* side: provider
  interfaces and Terraform value types for people writing providers, and its documentation
  scopes it to that. The host side lives inside Terraform core (`internal/plugin6`,
  `internal/providers`, BUSL-licensed since 1.6) and in OpenTofu (MPL 2.0, same packages,
  forked from the last MPL Terraform). `github.com/clean8s/tf-client-sdk` exposes a
  `GRPCProvider` with `PluginClient` ("controls the plugin process") and the `GetProviderSchema`
  / `ReadResource` / `ImportResourceState` methods; it is a small third-party extraction of
  Terraform's client code whose provenance, version and licence have to be checked before it is
  counted as reusable, and it is Go. There is **no Python client.** Generating Python stubs from
  `tfplugin6.proto` gives the gRPC message types and nothing else: process launch, handshake
  parsing, mTLS, schema-aware MessagePack value conversion and unknown/null markers all have to
  be written. OpenTofu's `internal/plugin6` is the reference to port from.

## 4. Licensing

| Component | Licence | Consequence |
|---|---|---|
| HashiCorp providers (`terraform-provider-aws` LICENSE verified 2026-10-18: "Mozilla Public License Version 2.0", copyright IBM Corp. 2014–2026) | MPL 2.0 | Redistributable inside an EE; callable from anything |
| Terraform CLI 1.6+ | BUSL 1.1; "production use" allowed unless offered to third parties "on a hosted or embedded basis" competitive with IBM's products; converts to MPL 2.0 four years after each release | Shipping the CLI inside a product EE is the grey case |
| OpenTofu | MPL 2.0, drop-in for Terraform 1.5-era providers and registry | The safe engine for Route A |

## 5. What Red Hat ships today (AAP 2.6 / 2.7)

- **`hashicorp.terraform`** (certified, recommended by the docs): API integration with **HCP
  Terraform or Terraform Enterprise**. No binary needed, but it requires one of those two
  services. Not applicable to a self-contained AAC install.
- **`cloud.terraform`** (certified, "supported, but we recommend `hashicorp.terraform`"): wraps the
  CLI. Modules `terraform` (with `binary_path`, so OpenTofu works), `terraform_output`,
  `plan_stash`; inventory plugins `terraform_provider` (from a state file) and `terraform_state`
  (from cloud resources); lookup `tf_output`. The operator must put the binary in the EE.
- **`terraform-provider-aap`**: the other direction, Terraform launching AAP jobs. Fully
  supported by Red Hat and HashiCorp. Irrelevant here except as naming precedent.

None of them speaks the provider protocol. That is the gap Route B fills.

## 6. What Route B would take in AAC

| Step | Work | Notes |
|---|---|---|
| B1 | **Execution environment `aac-provider-ee`**: ubi9 base, Python gRPC stubs generated from `tfplugin6.proto` (and `tfplugin5.proto` for older providers), `msgpack`; provider binaries fetched from the registry at build time with checksum and signature verification, pinned by version | Registry downloads are plain HTTPS; no CLI needed. The AWS provider binary is about 600 MB uncompressed, so pin only the providers a profile selects |
| B2 | **Provider broker** (Python, long-lived): launched by the first task on the EE, keyed by the AAP job id, listening on a Unix socket in the job's private directory; it launches provider binaries, completes the handshake, caches `GetProviderSchema` on disk per provider version (the AWS schema is tens of MB), holds the configured provider, serialises calls, and exits when the play ends or on an idle timeout. **Ansible modules `aac.tfprovider.read` / `data_read`** are short-lived clients of the broker: they send a batch of reads and return JSON. A normal module exits after one result, so without the broker every task would pay provider start-up and schema load again | The broker is the piece Phase 0 must get right; a per-invocation batching mode (many resources in one module call, no broker) is the fallback if the broker proves fragile under AAP's job isolation |
| B3 | **Wire into the spine**: the module's JSON becomes `opa_input` for the existing `cis_aws` / `cis_azure` / `cis_gcp` and any provider-shaped framework; stored through `aac_store_results` | Zero new Rego until facts are flowing; then policies can read provider-native field names |
| B4 | **Credentials**: AAP credential types inject the same environment the provider already reads (`AWS_ACCESS_KEY_ID`, `ARM_*`, `GOOGLE_*`) | Nothing provider-specific to build |
| B5 | **Apply with AAC as the state store** — see section 6a | Second phase, after the read-only proof |

Estimate: a one-provider (AWS), read-only proof that produces an OPA-evaluated row on the lab is
two to three weeks once the broker and value conversion are counted honestly. Productising (five
providers, EE pipeline, schema caching, discovery and import-identifier handling per resource
type, error contract, tests) is five to seven weeks. Risks, in order: schema-aware MessagePack
decoding with unknown and null markers; the broker's lifecycle under AAP job isolation; resource
types without importers; providers that only serve protocol 5; provider start-up time and schema
size; registry supply-chain verification.

## 6a. Could AAC provide the stored state? (Tim, 2026-10-18)

Yes, and it is smaller than it sounds. Terraform's state is one JSON document per resource: the
attributes the provider returned after the last apply, an opaque *private* blob the provider
owns, and a schema version. Terraform's own PostgreSQL backend stores exactly that in a table.
AAC already has the database, the row contract and the evidence discipline.

The diff is the provider's job, not Terraform's. `PlanResourceChange` takes prior state plus
desired config and returns the planned new state and whether the resource must be replaced;
`UpgradeResourceState` migrates old state when the provider's schema changes; `ReadResource`
refreshes. Terraform core only orchestrates. The module loop therefore is:

1. load the prior state for this resource from AAC's table;
2. `PlanResourceChange` → the planned diff;
3. send the diff to OPA → allow or deny **before anything changes**;
4. `ApplyResourceChange`; store the new state and private blob; report `changed`.

That is an idempotent Ansible module with a policy gate on the actual planned change, which
Terraform cannot do at that granularity without Sentinel or run tasks.

| Terraform core job | Under AAP |
|---|---|
| HCL evaluation, `count`, `for_each`, modules | Playbook tasks and loops |
| Unknown values resolved across the graph in one plan | Not needed: Ansible runs sequentially, so every value is known when the next task runs |
| Dependency graph and destroy ordering | Task order; the destroy playbook is written in reverse |
| Whole-estate plan preview before any change | Per-task check mode plus the OPA gate per resource |
| State locking | A row lock |
| Registry modules and the HCL ecosystem | Not available; you write playbooks |

**Cost on top of the read-only proof:** two to four weeks. The state table (resource address,
provider and version, schema version, attributes, private blob, sensitive flags), the apply and
destroy path, locking, and an importer that reads an existing `terraform.tfstate` so a customer
can migrate.

**Risks:** sensitive attributes must be flagged and encrypted at rest; the private blob must
round-trip byte-exact; resource identity is whatever key the playbook gives, so renames need a
`moved`-style operation; and the positioning has to be honest: this replaces Terraform for teams
that want AAP as the one control plane, not for teams invested in HCL modules.

## 7. Decision

1. **Go / no-go on the Route B proof** (read-only, AWS, one data source, one OPA policy, one
   stored row), and whether the apply phase with AAC-held state (section 6a) follows it.
2. **Route A engine**: OpenTofu by default in any AAC EE that applies Terraform, for the licence
   reason in section 4.
3. **Where the client lives**: `aac-plugins` (alongside the complytime provider) or a new
   `aac.tfprovider` collection in this repository.

---

Sources: Terraform plugin protocol docs (`docs/plugin-protocol`, `tfplugin6.*.proto`);
`terraform-plugin-go` `tf6server/server.go` (handshake constants); go-plugin `docs/internals.md`
(handshake line); Crossplane Upjet README and Upbound's write-up on dropping the CLI; Pulumi
terraform-bridge README; `terraform-provider-aws` LICENSE; HashiCorp Terraform LICENSE (BUSL 1.1
Additional Use Grant); Red Hat AAP 2.6/2.7 "Integrate with HashiCorp Terraform" and the
`cloud.terraform` module documentation; Red Hat blog on the AAP provider for Terraform.

| Version | Date | Change |
|---|---|---|
| v0.1 | 2026-10-18 | First research pass for Tim's question "can we use AAP to talk to a Terraform provider?" |
| v0.2 | 2026-10-18 | Section 6a: AAC as the state store makes apply viable under AAP; recommendation and B5 updated |
| v0.3 | 2026-10-18 | Copilot review: Upjet is in-process Go, not an external gRPC client; Route B scoped to importable resources and tested data sources (section 2a); terraform-plugin-go is server-side, client code and the Python gap stated honestly; a provider broker replaces the per-play module assumption; estimates raised |
