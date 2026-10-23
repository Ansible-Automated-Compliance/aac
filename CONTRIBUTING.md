# Contributing to Ansible Automated Compliance (AAC)

## Table of Contents

- [Prerequisites](#prerequisites)
- [Branching and Pull Requests](#branching-and-pull-requests)
- [Adding a Compliance Policy](#adding-a-compliance-policy)
- [Adding an Ansible Playbook](#adding-an-ansible-playbook)
- [Adding an EDA Rulebook](#adding-an-eda-rulebook)
- [Testing](#testing)
- [Code Style](#code-style)

---

## Prerequisites

- Access to an AAP controller — your own, the maintainer lab, or an RHPDS cluster.
  Which one, and its address, comes from your install inventory. No address is
  hardcoded in the runnable surface (`ansible/`, `install/`,
  `scripts/`, `extensions/`, `grafana/`), and CI enforces that. Some docs and
  repo-root files still name the maintainer lab — see
  `docs/CHANGE_GOVERNANCE.md` §8, which lists that as an open gap rather than
  claiming it is closed.
- Config created: `./scripts/aac-configure.sh` (creates the three operator-owned
  files from their templates; they are gitignored and a fresh clone has none)
- The `policies/` git submodule initialized: `git submodule update --init --recursive`
- OPA CLI installed locally for policy linting: `make install` (installs OPA + required tools)

---

## Branching and Pull Requests

**Never push directly to `main`.** Every change goes through a pull request.

A PR touching a **protected path** (`policies/`, `opa/`, `.github/workflows/`,
`aap-integration/`, `ansible/`) additionally needs an `Approved-By:` trailer
from an authorized approver in the commit message — CI enforces this as policy.
See **`docs/CHANGE_GOVERNANCE.md`** for what CI checks, how review works, and
where the governance is still weaker than it looks.

**Two-approver review.** The repository has two maintainers — Tim Coulter
(`@ynotbhatc`) and Juan Medina (`@R0tt3nT0m4t0`) — listed as code owners on every
path (`.github/CODEOWNERS`). Because an author cannot approve their own PR, every
change to `main` requires the **other maintainer's** review, and the required CI
checks must pass. Branch protection enforces both.

```bash
git checkout -b feat/my-feature   # or fix/, chore/, docs/
# make changes
git push origin feat/my-feature
gh pr create
```

After merging, sync the AAP project on the controller so templates pick up the new playbooks:
- AAP → Projects → Compliance Automation → Sync

---

## Adding a Compliance Policy

Policies live in the **`policies/` submodule** (`ynotbhatc/rego_policy_libraries`). Changes to policies require a PR in that repo, not here.

To add a new framework or benchmark:

1. Create the Rego file in `policies/` following the package naming convention:
   ```
   package <framework_key>.<module>
   import rego.v1
   ```
2. Add the framework key to `opa_framework_map` in `ansible/vars/site_config.yml`,
   mapping it to the correct OPA bucket (`security`, `compliance`, or `ot`).
   That file is **not tracked** — create it with `./scripts/aac-configure.sh`
   and add the key to `ansible/vars/site_config.yml.example` as well, which is
   the tracked template every new install starts from.
3. After merging in the submodule repo, update the submodule pointer here:
   ```bash
   cd policies && git pull origin main && cd ..
   git add policies
   git commit -m "chore: update policies submodule"
   ```
4. Load the new policy into OPA via AAP template **27 — AAC - Load OPA Policies**.

### Rego v1 Requirements

All policies must use Rego v1 syntax:

```rego
package my_framework.section

import rego.v1

default compliant := false

violations contains msg if {
    not some_control
    msg := "Control description — what failed and why"
}

compliant if { count(violations) == 0 }
```

**Common pitfalls:**
- `array.concat()` takes exactly 2 arguments — use nested calls for 3+ arrays
- `default rule := false` is required — without it, a rule that never fires returns `undefined`, which propagates as `{}` at the OPA endpoint
- Use `contains` for sets, `if` for conditionals

---

## Adding an Ansible Playbook

1. Place the playbook in the appropriate subdirectory of `ansible/playbooks/`:
   - `assessment/` — compliance scans
   - `deployment/` — infrastructure deployment
   - `reporting/` — report generation
   - `operations/` — maintenance tasks (token rotation, backups)
   - `demo/` — demo scripts

2. Reference vault variables via `vars_files`:
   ```yaml
   vars_files:
     - ../vars/vault_secrets.yml
     - ../vars/site_config.yml
   ```

3. Use the OPA routing pattern — never hardcode OPA URLs:
   ```yaml
   vars:
     framework: "cis_rhel9"
   tasks:
     - include_tasks: ../tasks/resolve_opa_url.yml
     # opa_server_url is now set
   ```

4. Store results via the `aac_store_results` role — always pass `aac_result_framework`:
   ```yaml
   - include_role:
       name: aac_store_results
     vars:
       aac_result_framework: "my_framework"   # required — NOT NULL in DB
       aac_result_policy_name: "My Framework"
       aac_result_violations: "{{ violations }}"
       aac_result_compliance_pct: "{{ compliance_score }}"
   ```

5. Create a corresponding AAP job template before testing. Do **not** run playbooks with `ansible-playbook` directly — always use AAP.

---

## Adding an EDA Rulebook

Rulebooks live in `extensions/eda/rulebooks/`. They are deployed via AAP EDA and should not be run manually.

Port assignments:
| Port | Rulebook | Purpose |
|------|----------|---------|
| 5000 | `compliance_webhook_events.yml` | General compliance webhooks |
| 5001 | `ami_events.yml` | AMI/smart meter events |
| 5002 | `ai_governance_enforcement.yml` | AI governance |
| 5003 | `sentinel_github_webhook.yml` | Sentinel GitHub push events |
| 5004 | `golden_image_enforcement.yml` | Golden image drift enforcement |

After changing a rulebook:
1. Push the branch and merge the PR
2. Sync the EDA project in AAP
3. **Restart the EDA activation** — a sync alone does not reload running rulebook content

---

## Testing

### Rego Policies
```bash
# Lint all policies
make check-syntax

# Run unit tests
make test-unit

# Run with coverage
opa test policies/ tests/ --coverage
```

### Playbooks
```bash
# Syntax check (does not require running AAP)
ansible-playbook --syntax-check ansible/playbooks/<playbook>.yml
```

### Full validation
```bash
make lint    # OPA fmt + syntax
make test    # full test suite
```

---

## Code Style

- **Rego:** Use `opa fmt` (enforced by CI). Control IDs in violation messages: `"CIS 1.1.1: ..."`
- **Ansible:** Snake_case task names, always set `failed_when: false` on fact-collection tasks
- **Commits:** Conventional commits — `feat:`, `fix:`, `chore:`, `docs:`
- **Never** use `docker` — always `podman`
- **Never** run `ansible-playbook` directly — always via AAP job templates
