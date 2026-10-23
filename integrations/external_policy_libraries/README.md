> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# External Policy Libraries — Trivy + Kubescape

## At a glance

- **Integration type:** state-assessment extension via upstream CLI shellout
- **Status:** ✅ production-ready
- **Effort estimate:** 1-2 person-days to wire into a customer environment (EE rebuild + AAP templates + smoke test)
- **Dedicated EE — `aac-policy-tools-ee` v1.0.0:**
  - `trivy` v0.69.3 (Apache-2.0 / MIT checks library) — https://github.com/aquasecurity/trivy
  - `kubescape` v3.0.40 (Apache-2.0) — https://github.com/kubescape/kubescape
  - **Not bundled into the main `aac-compliance-ee`** to keep that image lean. The two AAP templates for this integration use the policy-tools EE.
- **License attribution:** see `THIRD_PARTY_LICENSES.md` at repo root

## Why this integration exists

The Rego policy library that ships with AAC covers 50+ frameworks (CIS,
STIG, NIST, ISO 27001, SOC 2, NERC-CIP, AMI, …). It does **not** cover
two adjacent domains where mature community libraries already exist:

| Domain | Community library | Coverage |
|---|---|---|
| K8s manifest / Dockerfile / Helm / IaC misconfig | Trivy (Aqua) — 592 checks | KSV-* and DS-* IDs |
| K8s NSA-CISA Hardening Guide + MITRE ATT&CK mapping | Kubescape (ARMO) — 357 controls | C-* IDs, multiple frameworks |

Rather than re-implement these in our Rego library — they're well-maintained
upstream and would drift — we orchestrate the upstream CLIs from Ansible
playbooks. State assessment results land in the same PostgreSQL
`compliance_results` table as everything else AAC measures, so Grafana
dashboards work without modification.

## What AAC measures here

**State, not activities.** Both integrations evaluate the **content** of
an artifact — what a Kubernetes Deployment declares, what a Dockerfile
instructs, what a Helm chart renders, what a Terraform plan describes.

We do **not** measure deploy events, audit-log streams, admission
decisions, or runtime telemetry. If the customer's pipeline asks
"what's the state of this artifact?", AAC answers; the pipeline
decides whether to deploy. AAC never observes the deploy itself.

> See `~/.claude/projects/-Users-tcoulter--local-bin/memory/feedback_assessment_not_runtime.md`
> for the full positioning rationale.

## Why upstream CLI shellout (not Rego loaded into our OPA)

We considered loading both libraries' `.rego` files into our OPA
containers via the `/v1/policies` REST API. Both failed:

- **Trivy** uses Go-side builtins (`result.new`, `cidr.is_public`,
  `sh.parse_commands`) registered by Trivy's own binary at
  `pkg/rego/builtin.go`. These are NOT standard OPA features. Loaded
  into vanilla OPA, ~95% of checks fail to compile.

- **Kubescape** declares all 357 rules under a single shared package
  (`armo_builtins`) and has overlapping helper-function names across
  files. OPA's REST API loads modules incrementally and rejects
  duplicate symbols; ~23% of rules silently fail to load when this
  happens. Kubescape's own runtime loads them as a coherent bundle
  with module-merge semantics that OPA REST doesn't apply.

Both libraries are **designed to run in their own runtimes**. We delegate
evaluation to those runtimes (CLI shellout) and store the resulting state
in our own data layer. This is the open-source-clean integration path:
nothing proprietary, no upstream code vendored into our repo.

## Components

| Component | Path | Purpose |
|---|---|---|
| Playbook (Trivy) | `ansible/playbooks/trivy_assess_artifact.yml` | Runs `trivy` CLI against an artifact, parses JSON, stores to `compliance_results` |
| Playbook (Kubescape) | `ansible/playbooks/kubescape_assess.yml` | Runs `kubescape` CLI against manifest path or live cluster |
| Dedicated EE | `ansible/execution-environments/aac-policy-tools-ee/` | Bundles `trivy` + `kubescape` binaries. Separate from `aac-compliance-ee` to keep that image lean. |
| EE build playbook | `ansible/playbooks/build_policy_tools_ee.yml` | Builds + pushes `aac-policy-tools-ee` to quay.io |
| Demo | `demos/external_policy_libraries/run_demo.yml` | 4-act demo: bad K8s, good K8s, bad Dockerfile, NSA-CISA framework view |
| Sample artifacts | `demos/external_policy_libraries/artifacts/` | `bad-deployment.yaml`, `good-deployment.yaml`, `bad.Dockerfile` |

## AAP job templates (created by seed playbook)

| Template | Survey vars |
|---|---|
| AAC - Trivy Assessment | `artifact_path`, `scan_type` (config\|fs\|image), `severity_floor` (LOW\|MEDIUM\|HIGH\|CRITICAL), `target_label` |
| AAC - Kubescape Assessment | `target_path`, `target_cluster` (bool), `framework` (allcontrols\|nsa\|mitre\|cis-v1.10.0\|armobest\|WorkloadScan), `target_label` |

## Using it

### Lint a single artifact from CI

```bash
# CI calls AAP via API
curl -X POST -H "Authorization: Bearer $AAP_TOKEN" \
  -d '{"extra_vars": {"artifact_path": "/path/to/Deployment.yaml", "scan_type": "config"}}' \
  https://<aap-host>/api/controller/v2/job_templates/<trivy-template-id>/launch/
```

Customer's CI parses the resulting `compliance_results` row to decide
whether to deploy. The decision belongs to the pipeline; AAC just
reports state.

### Sweep a directory of manifests

```bash
ansible-playbook ansible/playbooks/kubescape_assess.yml \
  -e target_path=/opt/customer-repo/manifests \
  -e framework=nsa
```

### Run the demo

```bash
ansible-playbook demos/external_policy_libraries/run_demo.yml \
  -i ansible/inventory/rhel9_test.yml \
  -e record_to_db=false   # set true for full PostgreSQL E2E
```

## Customer-side prerequisites

- AAC Compliance EE v1.2.2 or later (includes trivy + kubescape binaries)
- Network egress allowed to `github.com` on first run (trivy downloads its
  vulnerability + misconfig database the first time it runs; cached after)
- For Kubescape `target_cluster=true`: a valid kubeconfig with read access
  to the target cluster (the EE pod / runner needs the kubeconfig mounted
  or available via `KUBECONFIG` env var)

## Bumping versions

Each tool ships frequent releases. Bump deliberately via PR:

1. Edit `ansible/execution-environments/aac-policy-tools-ee/execution-environment.yml`
   — update the trivy + kubescape versions in the single `RUN` block (the
   block is arch-aware, so update the version once and both architectures
   pick up the matching upstream asset). Bump `ee_version` in
   `ansible/playbooks/build_policy_tools_ee.yml`.

2. Build natively on **both** architectures (no cross-build / qemu — see
   "Why multi-arch" below):

   ```bash
   # On an amd64 host (e.g. lab-aap at AAP_HOST):
   ansible-playbook ansible/playbooks/build_policy_tools_ee.yml \
     -e ee_version=vX.Y.Z

   # On an arm64 host (e.g. local Mac):
   ansible-playbook ansible/playbooks/build_policy_tools_ee.yml \
     -e ee_version=vX.Y.Z
   ```

   Each run pushes `<image>:vX.Y.Z-<arch>` to quay.io.

3. Combine into a multi-arch manifest from any host with podman:

   ```bash
   ansible-playbook ansible/playbooks/build_policy_tools_ee_manifest.yml \
     -e ee_version=vX.Y.Z
   ```

   This creates `<image>:vX.Y.Z` and `<image>:latest` as manifest lists.
   Consumers (mac-aap arm64 pods, lab-aap amd64 hosts, RHPDS EC2 amd64)
   automatically pull the correct arch.

4. Smoke-test by running the demo against the new EE.

5. PR with diff + smoke-test evidence; admin-merge once green.

### Why multi-arch (and why native, not buildx)

mac-aap CRC runs **aarch64** pods (matches the Mac host). lab-aap is
**amd64**. RHPDS demos are **amd64**. A single-arch image would force
one camp through qemu emulation, and **kubescape's Go runtime panics
under amd64-on-arm64 emulation** (`lfstack.push invalid packing`).
Building natively on each arch avoids that bug and is faster.

This is independent of the `aac-compliance-ee` cadence — bumping
trivy/kubescape does NOT force a rebuild of the EE that runs all your
core demos.

## Data model

Each assessment writes one row to `compliance_results`:

| Column | Trivy | Kubescape |
|---|---|---|
| `hostname` | `target_label` (artifact name) | `target_label` (artifact name or `cluster:<ctx>`) |
| `framework` | `"trivy"` | `"kubescape_<framework>"` (e.g. `kubescape_nsa`) |
| `policy_name` | `"trivy-checks"` | `"kubescape regolibrary"` |
| `policy_version` | trivy version | kubescape version |
| `compliant` | `true` iff failed_count == 0 | `true` iff failed_controls == 0 |
| `total_controls` | misconfigurations evaluated | controls evaluated |
| `passed_controls` | PASS count | passed count |
| `failed_controls` | FAIL count | failed count |
| `compliance_percentage` | computed from PASS/total | kubescape's own complianceScore |
| `violations` (jsonb) | list of `{id, title, severity, status, ...}` | list of `{control_id, name, score_factor, ...}` |
| `metadata` (jsonb) | tool version, artifact path, scan params | tool version, framework, target path |

## Known limitations

- **Trivy first-run download.** The first invocation of `trivy config`
  downloads ~50 MB of vulnerability + misconfig databases. Bake this
  into the EE build (or pre-warm on the runner) for faster customer
  demos.
- **Kubescape `target_cluster=true`** needs kubeconfig wiring. In CRC
  the pod needs the right token + CA. In customer environments, the
  customer provides kubeconfig as an AAP credential file.
- **Trivy file detection by name.** `trivy config` recognizes
  Dockerfile by filename (`Dockerfile`, `*.Dockerfile`) — a Dockerfile
  named `Containerfile` or `Dockerfile-prod` won't be detected as a
  Dockerfile. Customers should rename or use `scan_type=fs` for
  arbitrary-content scans.
- **Kubescape skipped-control noise.** Some controls require live
  cluster connectivity (kubelet config, etcd certs); they show as
  SKIPPED when scanning files. Counted separately in summary; not
  treated as PASS or FAIL.

## See also

- `THIRD_PARTY_LICENSES.md` — license attribution for trivy + kubescape
- `~/.claude/projects/.../memory/feedback_assessment_not_runtime.md` —
  positioning rationale (state, not activities)
- `policies/CLAUDE.md` — why our own Rego library uses different
  conventions than trivy / kubescape
