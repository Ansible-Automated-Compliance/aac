# AAC Installation Guide

**Ansible Automated Compliance (AAC)** installs four ways depending on your starting point.
Tiers and tested status for every method: [`SUPPORT_MATRIX.md`](SUPPORT_MATRIX.md).

## Which path is right for you?

| Path | Starting point | Best for |
|------|---------------|----------|
| [**Standard**](standard/README.md) — *start here* | Any target; profile-driven (`lab` / `rhpds` / `customer`) | The canonical method: fail-closed environment profiles + preflight/verify gates. Includes the [EC2 provisioning path](standard/PROVISION_EC2.md) for fresh instances |
| [Existing AAP](existing-aap/README.md) | AAP 2.6+ already running | Adding AAC to an existing AAP deployment. The [extended variant](existing-aap/extended/README.adoc) adds quadlets + EE build |
| [Config as Code](config-as-code/README.md) | Git repo + AAP API access | CI/CD pipelines, repeatable environment rebuilds |
| [RHPDS](rhpds/README.md) | RHPDS OpenShift cluster provisioned | Red Hat demo environments, field sales (demo/field tier) |
| [OpenShift Local (CRC)](openshift-local/README.md) | One RHEL 9 host with hardware virtualisation | Evaluation of AAP 2.7 and Automation Orchestrator on one machine, with shipped manifests; AAC itself then follows the extended guide (evaluation tier) |

Former methods: `from-scratch/` is absorbed into Standard; `mac-aap/` and `lab-aap-crc/` moved
to the aac-demos repository (`demos/lab-crc/`) as a documented, unsupported example environment — not install methods.

## What gets installed

All paths result in the same AAC stack — AAP (2.6+; 2.7 is the reference), three
domain-specific OPA services, PostgreSQL (compliance evidence store), Grafana dashboards, and
the Rego policy library loaded into OPA. **Topology varies by profile**: on OpenShift, each
OPA is its own Service (all on 8181, distinguished by name); on a single-host container
deployment, the three OPAs bind host ports 8181/8182/8183. Playbooks resolve endpoints from
the environment profile — never hardcode either form.

## Prerequisites (all paths)

- **AAP license or Red Hat subscription** — manifest (disconnected) or service account
  (connected): [`../docs/install/AAP_SUBSCRIPTION_MANIFEST.md`](../docs/install/AAP_SUBSCRIPTION_MANIFEST.md)
- **RHEL 9** target hosts
- **GitHub PAT** with read access to this repository
- **AWS credentials** for EC2-based paths
- Run `scripts/aac-configure.sh` after cloning — it generates the gitignored local config
  (`site_config.yml`, `vault_secrets.yml`, `install_config.yml`) from the examples

## After installation

Run the consolidated verifier — from AAP (template **"AAC - Verify Install"**, seeded by the
standard path) or CLI:

```bash
ansible-playbook ansible/playbooks/verify_install.yml -e env_profile=<your-profile>
```

It gates on: OPA ×3 policy minimums, PostgreSQL schema + read access as the app role, Grafana
health, and required templates — GO/NO-GO with per-check detail. (The older
`verify_installation.yml` is the legacy verifier and is being retired.)

## Key files referenced by all paths

| File | Purpose |
|------|---------|
| `ansible/vars/vault_secrets.yml` | Site credentials — gitignored; generated from example by `aac-configure.sh` |
| `ansible/vars/profiles/` | Environment profiles (lab / macaap / rhpds / customer) |
| `install_config.example.yml` | Optional per-install overrides (fail-closed: no default profile) |
| `ansible/inventory/hosts.yml` | Production inventory |
| `policies/` | Rego policy library (git submodule — count policies at the pinned commit) |
| `extensions/eda/rulebooks/` | EDA rulebooks for event-driven compliance |
