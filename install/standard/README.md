# AAC Standard Install (profile-driven)

**Version:** v0.1 (foundational slice — profile system + preflight/verify gates)

One templated, generic way to install AAC into any environment — lab, mac-aap
(local OCP), RHPDS, or a customer site — with the **same** playbooks and
consistent, validated results. Nothing is hard-coded to a host: every
environment-specific value comes from a profile you select.

## The model

Every site-specific value lives in **one file you create**, patterned on the
AAP containerized installer's `inventory`. If you have installed AAP, this is
the same shape: fill in one file, pass it with `-i`, edit nothing else.

```
install/aac-install-inventory     ← you create this from the .example
   │  [all:vars]
   │    env_profile=customer      ← REQUIRED, no default
   │    aac_host=...              ← everything else derives from this
   │  wins over ↓
ansible/vars/site_config.yml      ← optional per-machine overrides
   │  wins over ↓
ansible/vars/profiles/<env>.yml   ← topology defaults for that kind of site
```

Precedence (later wins): `profiles/<env>.yml` → `site_config.yml` →
**inventory `[all:vars]` / `-e`**. Loaded by
`ansible/tasks/load_install_profile.yml`.

Two things about this changed, and both were bugs:

- **The inventory now wins.** `include_vars` outranks inventory variables in
  Ansible's precedence table, so a profile default used to silently override
  the value an operator had set in their own file.
- **`env_profile` has no default.** It used to fall back to `lab`, so a run
  without `-e env_profile=` quietly pointed the install at the maintainer's
  lab. It now refuses to guess.

**Secrets never live in any of these files.** They come from an AAP credential
(recommended) or an ansible-vault encrypted file for CLI runs — set by
`secret_source` in the inventory.

**None of the three files are in git**, only their `.example` templates. A
filled-in config in git is how one site's addresses reach another site's
install; this repository shipped a tracked `site_config.yml` pointing at the
maintainer lab for months. CI enforces this — see
`.github/workflows/install-config-hygiene.yml`.

## Quick start

```bash
# 0. Create your config from the templates (safe to re-run; never overwrites):
./scripts/aac-configure.sh
$EDITOR install/aac-install-inventory    # set env_profile + aac_host

# 1. Preconditions gate (AAP reachable, DB ≥15, secrets present, config filled in):
ansible-playbook -i install/aac-install-inventory ansible/playbooks/install_preflight.yml

# 2. Install (or run your environment's existing infra/bootstrap):
ansible-playbook -i install/aac-install-inventory ansible/playbooks/install.yml

# 3. Post-install verify gate (OPA/PG-as-compliance-role/Grafana/MCP/AAP objects):
ansible-playbook -i install/aac-install-inventory ansible/playbooks/verify_install.yml
```

Each also runs as an AAP job template. **OpenShift profiles (lab/macaap/rhpds)
use in-cluster service DNS**, so run them from the AAP Execution Environment
(job template), not an external laptop.

## Gates

| Playbook | Stage | Checks | Result |
|---|---|---|---|
| `install_preflight.yml` | pre-install | config filled in, AAP reachable + auth, PostgreSQL reachable + ≥15, required secrets present, EE image set, topology is a known value (`containers`\|`openshift` — fails closed on a typo), podman ≥ 5.8.2-6 on container hosts (/dev/null layer-extraction fix) + /dev/null integrity (char device, 666, link count 1 — catches leftover hard links from pre-fix extractions) | 🟢 GO / 🔴 NO-GO, fails on hard failure |
| `verify_install.yml` | post-install | OPA ×3 + policy counts, PostgreSQL **as the `compliance` role** (catches GRANT gaps) + canonical tables + data, Grafana, MCP, AAP object presence | 🟢 GO / 🔴 NO-GO, fails on hard failure |
| `grafana_dashboard_coverage.yml` | post-install | every dashboard panel returns data (deep coverage) | 🟢/🔴 |

## Profiles

| Profile | Environment | Topology | DB |
|---|---|---|---|
| `lab` | maintainer lab CRC (addresses in the lab profile) | openshift (in-cluster svc DNS) | in-cluster `compliance-db` |
| `macaap` | local CRC MicroShift | openshift | in-cluster `compliance-db` |
| `rhpds` | ephemeral RHPDS OCP (`rhpds_cluster` var) | openshift | in-cluster `compliance-db` |
| `customer` | customer AAP + external DB | containers (host:port) | **external** (`aac_db_skip_container_deploy`) |

## Status & roadmap

This is the **foundational slice**. The `infra`, `config-as-code`, and `seed`
stages of `install.yml` still delegate to the existing assets (shared roles +
`ansible/config_as_code/`). The convergence work — folding the imperative
seeders / bash installers into this single profile-driven path and retiring the
duplicate OPA/PostgreSQL/AAP-wiring paths — is tracked in the standardize-install
plan.
