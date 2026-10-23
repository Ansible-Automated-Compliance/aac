# Playbook Configuration Standardization Plan

**Version:** v0.1
**Date:** 2026-10-08
**Status:** Proposal — for Tim and Juan to decide the open questions in §7
**Authors:** Tim Coulter; Claude (Anthropic), co-author
**Origin:** Juan's reorg list, items 1 and 2 — "remove hardcoded values from variables in
playbooks (ex: `cis_rhel9_assessment.yml: pg_db: "compliance"`)" and "rename all playbooks
from yaml to yml to standardize".

---

## 1. What the repository actually looks like today

Everything below was measured on `main` at 3a1567c6 (2026-10-08). Counts are quoted from the
scan, not estimated.

### 1.1 File extensions

| Tree | `.yml` | `.yaml` |
|---|---|---|
| `ansible/playbooks/` | 184 | 0 |
| `ansible/roles/` | 125 | 0 |
| `ansible/vars/`, `ansible/inventory/` | 30 | 0 |
| `extensions/eda/rulebooks/` (the rulebooks AAP deploys) | 12 | 0 |
| `ansible/` (whole tree) | 379 | 2 |
| `contrib/` | 15 | 10 |
| `install/` | 4 | 0 |

**Every playbook, role and rulebook (under `extensions/eda/rulebooks/`) is already `.yml`.** The twelve `.yaml` files are Kubernetes
manifests (`ansible/files/aac_config_reader_rbac.yaml`, `ansible/opa-routing/deploy/rbac.yaml`,
`contrib/mac-aap/manifests/*.yaml`, `contrib/lab-aap-crc/manifests/*.yaml`) and Grafana
provisioning files, where `.yaml` is the upstream convention. Twenty-one in-repo references
(`oc apply -f …`, README recipes) point at those names. The same is true of Juan's fork: its
`.yaml` files under `ansible/` and `contrib/` are these same manifests.

### 1.2 Literal configuration in play `vars:`

| Measure | Count |
|---|---|
| Literal connection/endpoint assignments in `ansible/playbooks/*.yml` (two allow-listed files excluded, see below) | 55 |
| Playbooks carrying them | 28 |
| … of which carry a `pg_db` / `pg_user` pair | 22 playbooks (one with `pg_user: "compliance"`) |
| … using alias names instead of `pg_*` | 3 (`db_*` in `store_compliance_to_postgres.yml`, `ai_governance_check.yml`; `postgres_*` in `compliance_trending_report.yml`) |
| … `pg_port: 5432` alone | 4 |
| Playbooks with a literal **host** | 1 (`compliance_trending_report.yml`: `postgres_host: "localhost"`) |

Two further files are allow-listed in the scan because their literals are not configuration drift: `load_opa_routing.yml` names the
Kubernetes namespace and ConfigMap it manages, and `opa-policy-deployment.yml` carries the OPA
download URL template.

### 1.3 How playbooks load configuration — three patterns, no owner

| Pattern | Playbooks | Behaviour when `site_config.yml` is absent |
|---|---|---|
| `vars_files: - ../vars/site_config.yml` (hard) | 128 | **Play fails to load.** `site_config.yml` is gitignored by design (the loader comment in `ansible/tasks/load_install_profile.yml` explains why: the tracked copy is how lab addresses kept leaking). An AAP project checkout never has it. |
| `include_vars` + `with_first_found` + `skip: true` (optional) | 1 (`generate_compliance_report_from_db.yml`) | Falls through to extra_vars / defaults. This is the pattern Copilot keeps asking for (today: #779 and #780). |
| `include_tasks: ../tasks/load_install_profile.yml` (layered: `profiles/<env>.yml` < `site_config.yml` < inventory / `-e`; fail-closed on `env_profile`) | 2 | Works from the tracked profile. |
| Neither | 31 (12 of them talk to PostgreSQL or OPA) | Relies entirely on the play literals or extra_vars. |

`ansible/vars/profiles/{lab,customer,rhpds,macaap}.yml` are tracked and already carry the
topology defaults (`pg_host`, `pg_port`, `pg_db`, `pg_user`, the three `opa_*_url`,
`grafana_url`). `site_config.yml.example` carries the same keys. So the values Juan wants out
of the playbooks already have a home; the playbooks just do not use it consistently.

### 1.4 Why the literals are mostly dead, and why that is worse

Ansible precedence puts `vars_files` above play `vars`. In 27 of the 28 playbooks the literal
sits next to a `vars_files` load of `site_config.yml`, so it is overridden whenever the
file is present and used only when it is not — which is exactly the AAP case. The literal is
therefore a silent second configuration path that only activates on the platform where
configuration matters most. Removing it is not cosmetic.

## 2. Target state

1. **One loader, one precedence.** Every playbook that needs topology values loads them through
   a single shared task file: tracked profile defaults, then optional per-machine
   `site_config.yml`, then operator inventory / extra_vars (the precedence
   `load_install_profile.yml` already documents). No playbook names `site_config.yml` in
   `vars_files`.
2. **Zero literal connection configuration in play `vars:`.** `pg_*`, `opa_*_url`,
   `grafana_url`, `mcp_url`, `aac_host` live in `ansible/vars/profiles/*.yml` (tracked
   defaults) and the operator's inventory. One name per concept: `pg_*`, never `db_*` or
   `postgres_*`.
3. **Fail closed, with a message.** A play that reaches a database task without `pg_host`
   stops with an assert naming the variable and where to set it — never a default to
   `localhost` or an in-cluster hostname (the "No hardcoded in-cluster endpoints" gate already
   forbids the latter).
4. **Gated so it cannot regress.** Two CI checks in `Validate Ansible content`: no literal
   assignment of the connection keys in `ansible/playbooks` or `ansible/roles/*/defaults`
   (allow-list scoped to the three legitimate file/key pairs), scanning `ansible/playbooks/`
   recursively, and no `.yaml` under `ansible/{playbooks,roles,vars,inventory}` or
   `extensions/eda/rulebooks/`.
5. **Extensions: no rename.** Playbooks are already uniform. Kubernetes and Grafana manifests
   keep `.yaml`; the gate above locks the playbook convention in.

## 3. Options for the loader (decision needed)

| | Option | What changes | Verdict |
|---|---|---|---|
| **A** | **One shared `ansible/tasks/load_site_config.yml`** — profile defaults, optional `site_config.yml`, optional `vault_secrets.yml`, inventory wins; no `env_profile` requirement for assessment/report playbooks (they fail closed on the specific key instead) | 128 `vars_files` lines become one `include_tasks` line; 31 playbooks gain it; 55 literals deleted | **Recommended.** One place to reason about precedence; the pattern Copilot already demands; `load_install_profile.yml` stays the strict variant for installs. |
| B | Make every playbook require `env_profile` through `load_install_profile.yml` | Same edits plus every AAP job template and every CLI invocation must pass `env_profile` | Safest, but it breaks every existing template until each is updated. Right end state for installs; too much coupling for 180 assessment playbooks in one move. |
| C | Only delete the 55 literals, leave loading alone | 28 files | Incomplete: the 12 playbooks that load nothing and talk to PostgreSQL would lose their only configuration; the 128 hard `vars_files` keep failing in AAP checkouts. |

## 4. Phases

Each phase is one or more PRs on upstream branches (not fork branches — fork PRs need a
maintainer to approve every CI run), each passing `Validate Ansible content` and one lab job
run per playbook family before merge.

| Phase | Scope | Deliverable | Size |
|---|---|---|---|
| **P0 — gates in warn mode** | `scripts/check_literal_config.py` (connection-key literals, `.yaml` under playbook trees), wired into `ansible-validation.yml` as non-blocking; this document | Inventory is reproducible by CI, not by a one-off scan | 1 PR (the workflow file is a protected path: **Tim commits with the trailer**) |
| **P1 — the 28 playbooks** | Delete the 55 literals; rename `db_*`/`postgres_*` to `pg_*` in the 3 playbooks that use aliases; fix `compliance_trending_report.yml`'s `localhost`; each file gets the shared loader (Option A) | The example Juan gave is gone; all 28 load identically | 1–2 PRs |
| **P2 — loader unification** | Replace the 128 hard `vars_files` and add the loader to the 12 config-dependent playbooks that load nothing, batched by family: `cis_*` (10), `patch_*`/`mythos` (12), `seed_*` (14), `nerc_cip_*`/`cip_*`, `aws_*`, remainder | No playbook names `site_config.yml` directly | 5–6 PRs, one lab job run each |
| **P3 — flip the gates to blocking** | Same workflow step, `continue-on-error` removed; `CONTRIBUTING.md` and `CLAUDE.md` state the rule | Regression impossible without a red check | 1 PR (protected path, Tim) |
| **P4 — installs (optional, later)** | Move install/verify playbooks fully onto `load_install_profile.yml` with mandatory `env_profile` | Option B, for the playbooks where it belongs | Separate decision |

Already in flight and consistent with this plan: PR #780's fix converts
`identify_affected_components.yml`, `simulate_patch_lifecycle.yml` and
`golden_image_set_rollback_pause.yml` to the optional loader because the sales.demos pack
cannot ship `site_config.yml`. Those three count toward P2.

## 5. Risks and how the plan handles them

- **Job templates that rely on the literals.** Any AAP template whose playbook loads nothing
  today and sets no `pg_*` extra_vars will stop with the new assert instead of connecting to a
  guessed host. That is the intended behaviour; P2 batches are sized so each lab run surfaces
  the templates that need `pg_*` extra_vars or an `env_profile`. The lab's job-template
  inventory (memory `aap_job_templates.md`) is the checklist.
- **Merge conflicts with #777.** Juan's `yes/no → true/false` sweep touches many of the same
  playbooks. Sequence: #777 merges first, then P1.
- **Protected paths.** `CONTRIBUTING.md`, `docs/CHANGE_GOVERNANCE.md` and
  `docs/operations/GIT_APPROVAL_WORKFLOW.md` classify `ansible/` as protected and require the
  `Approved-By:` trailer; `approval_policy.rego` enforces only `policies/`, `.github/workflows/`
  and `enforcement/git/`. Until that drift is resolved the documented rule stands: P1/P2 commits
  carry the trailer, which means Tim adds it (or the sweep lands through his commits). P0 and P3
  edit `.github/workflows/` and are Tim's commits either way.
- **Behaviour change hidden in a mechanical sweep.** P1 and P2 are scripted and the script
  output is reviewed as a diff before commit — the same discipline as the 2026-09 branch
  cleanup. No hand edits inside the sweep.
- **Precedence surprise.** The shared loader re-applies profile values with `set_fact` only
  where the inventory has none, exactly as `load_install_profile.yml` does, so an operator's
  inventory keeps winning.

## 6. What is not in scope

- Renaming Kubernetes or Grafana `.yaml` manifests (12 files, 21 references, no benefit).
- `contrib/mac-aap/` playbooks (maintainer tooling outside the hygiene gates; two of them
  hardcode the lab DB hostname — noted in #779, separate clean-up).
- Role defaults: no role sets `pg_*` literals today; the gate covers them so that stays true.

## 7. Open questions

1. **Option A or B** for the loader (§3)? Recommendation: A now, B for installs in P4.
2. **Which lab job templates may break** when P2 lands for each family — who runs the lab
   checks, Juan or Tim?
3. **Did Juan's list have more items** beyond these two? This document covers only what was
   forwarded.
4. **Is the `.yaml` answer acceptable to Juan** — keep manifests as `.yaml`, lock playbooks to
   `.yml` by gate — or does he want the twelve renamed anyway?

---

*Measured on `main` at 3a1567c6. Re-run the scan with `python3 scripts/check_literal_config.py --warn`
(added with this document); the `.yaml`/`.yml` counts are plain `find`.*
