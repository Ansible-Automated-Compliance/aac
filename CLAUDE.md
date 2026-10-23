# CLAUDE.md — contributor contract for the AAC product repository

This file is read by Claude Code (and by people) at the start of every session in this
repository. It states the rules that keep the product consistent. It deliberately contains no
environment detail: no addresses, credentials, controller object ids or site routes. Those live
in each operator's own profile and vault, outside this tree.

## 1. What this repository is

**Ansible Automated Compliance (AAC)** assesses infrastructure against compliance frameworks
with a fixed division of labour:

| Layer | Does | Never does |
|---|---|---|
| Ansible (AAP job templates, EDA rulebooks) | Collects facts, calls OPA, stores results, reports | Decide compliance in playbook logic |
| OPA + the Rego library (`policies/` submodule) | Every compliance decision | Collect facts, talk to databases |
| PostgreSQL (`compliance_results`, `compliance_certifications`, …) | Evidence and history | Hold policy |

Flow: **facts (Ansible) → decision (OPA) → evidence (PostgreSQL) → report**. A new compliance
check is a new Rego policy, not new playbook logic. Assessment is read-only; remediation is a
separate, approved step.

## 2. Repository map

| Path | What |
|---|---|
| `ansible/playbooks/` | Job-template entry points (assess, store, report, seed, deploy) |
| `ansible/roles/` | Shared building blocks — see `ansible/roles/README.md` |
| `ansible/tasks/` | Reusable task files, including `resolve_opa_url.yml` |
| `ansible/vars/profiles/` | Environment profiles (`customer.yml`, `rhpds.yml`, `lab.yml`, …). The operator's live `site_config.yml` and `vault_secrets.yml` are git-ignored |
| `ansible/execution-environments/` | Execution environment definitions (UBI 9 based) |
| `collections/` | The one collections root: `aac.cis_facts`, `aac.m365` |
| `policies/` | Git submodule → the shared Rego library. Change policy there, then bump the pointer here |
| `extensions/eda/` | Event-Driven Ansible rulebooks |
| `services/` | Portal bridge and the AAP MCP server |
| `install/`, `examples/`, `integrations/`, `grafana/` | Install paths, examples, consumer integrations, dashboards |
| `scripts/` | CI gates and tooling (`check_*.py`, `validate_*.py`) |
| `docs/` | Documentation by audience; `docs/CHANGE_GOVERNANCE.md` is how a change reaches `main` |
| `VERSION`, `CHANGELOG.md`, `RELEASING.md` | The version, what changed, how to release |

Demo environments and runbooks live in the separate `aac-demos` repository, which pins this one
as a `product/` submodule. Nothing under `ansible/` may read from `demos/` at runtime
(`scripts/check_core_demo_boundary.py` enforces it).

## 3. Non-negotiables

1. **AAP is the choreographer.** Playbooks run as job templates. Do not run `ansible-playbook`
   against real hosts from a shell; if a playbook has no template, add one to the seeder.
2. **Podman, never Docker.** Container files are `Containerfile`; base images are `ubi9` /
   `ubi9-minimal` from `registry.access.redhat.com` or `quay.io`, never `docker.io/library/`.
3. **RHEL 9 is the host OS** for execution environments, installers and assessments unless a
   customer requires otherwise.
4. **No environment values in the tree.** Addresses, routes, credentials and controller ids
   come from the profile, the inventory or the vault. `Install Config Hygiene` and
   `scripts/check_no_hardcoded_endpoints.py` fail the PR otherwise. Example values in docs are
   placeholders (`<aap-host>`, `192.0.2.x`).
5. **Never a literal OPA URL.** Set `framework` and include `ansible/tasks/resolve_opa_url.yml`;
   it maps the framework key to the right OPA service through `opa_framework_map` and sets
   `opa_server_url`. The three OPA services (security, compliance, OT) are told apart by name,
   not by port.
6. **Store through the roles.** `aac_store_results` and `aac_store_certification` are the only
   writers to the evidence tables. No inline SQL in playbooks.
7. **Fail closed.** A missing fact, an undefined Rego field or an unknown framework key must fail
   the job, not store an empty result that looks green.
8. **Count, don't quote.** Policy counts, control coverage and tool counts drift. Measure them
   at the pinned submodule commit when a document needs them.

## 4. Rego rules (the library enforces these in its own CI)

- `import rego.v1`; rules use `if`, sets use `contains`, iteration uses `some x in xs`.
- `default rule := false` on every boolean rule. An undefined field collapses the whole
  `compliance_report` object to `{}` and the playbook stores nothing useful.
- `array.concat()` takes exactly two arrays; nest it for more.
- Package `<framework_key>.main` must define `compliance_report`, and the key must exist in
  `opa_framework_map`. Verify a new key with empty input before trusting it:

  ```bash
  opa eval -d policies/<dir> -f pretty 'data.<key>.main.compliance_report'   # populated object, not {} or undefined
  ```

- Rule names follow the control id (`control_1_1_1`); violation messages carry the control number
  and description. `opa test` and `opa fmt --diff` are clean before a PR.

## 5. Changing things

- **Never push to `main`.** Branch (`feat/`, `fix/`, `chore/`, `docs/`), open a PR, let CI and
  the other maintainer review. `CONTRIBUTING.md` has the walk-through.
- **Protected paths** (`policies/`, `.github/workflows/`, `enforcement/git/`) need an
  `Approved-By:` trailer from an authorised approver in the commit message, within the first 20
  lines. `policies/enforcement/git/approval_policy.rego` is the rule; `/git-protected-paths-check`
  warns before you commit.
- **One PR per concern.** Fixes for one review round go in one PR, not five.
- **Bumping `VERSION` is a release action**, not part of a feature PR — follow `RELEASING.md`.
- Every change that an operator would notice gets a `CHANGELOG.md` entry under *Unreleased*.
- Reference code as `path/file.ext:line`.

### CI gates (all must pass)

| Workflow | Checks |
|---|---|
| Change Approval Check | `Approved-By:` trailer on protected paths, evaluated as Rego |
| OPA Policy Validation | `opa check` and the policy test suite |
| Ansible Validation | YAML parses, `--syntax-check` on every playbook, every Jinja expression lexes, role include targets exist, EDA template names are seeded, no `demos/` reads, no hard-coded endpoints |
| Install Config Hygiene | No site addresses or credentials in shipped files |
| Framework Catalog Consistency | Framework keys, packages and catalog entries agree |
| Weekly security and CVE scans | gitleaks, dependency and container scans |

Run the Python gates locally before pushing: `python3 scripts/check_<name>.py`.

## 6. Claude Code skills shipped here

| Skill | Use |
|---|---|
| `/code-review` | Pre-merge review of the branch diff against this repository's recurring failure classes |
| `/git-protected-paths-check` | Warns when staged changes touch a protected path |
| `/opa-query` | Query a framework through the routing map against a reachable OPA |

Skills follow `.claude/skills/*/SKILL.md`: resolve paths through `git rev-parse --show-toplevel`,
take arguments as `$1`/`$2`, check HTTP status codes explicitly, and keep the description specific.
Operator-specific skills (environment health checks, controller syncs, provisioning) belong with
the operator, not in the product.

## 7. Documents

Documents generated from this repository carry a `**Version:**` line near the top, bump it on
every revision, and name Claude (Anthropic) as co-author when it contributed.

---

**Maintainers:** Tim Coulter (`@ynotbhatc`), Juan Medina (`@R0tt3nT0m4t0`) — `.github/CODEOWNERS`.
**Version:** read `VERSION`; never quote it from this file.
