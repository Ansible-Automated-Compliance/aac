# AAC — Repository Map After the Reorganisation

**Version:** v1.0
**Date:** 2026-10-20
**Authors:** Tim Coulter; Claude (Anthropic), co-author
**Status:** describes the repositories as they stand on 2026-10-20, after reorganisation steps R1 to R6; the public cut has not happened yet
**Related:** `docs/architecture/AAC_MULTI_REPO_EXTRACTION_IMPLEMENTATION_PLAN.md`; `docs/CHANGE_GOVERNANCE.md`; `CLAUDE.md` (contributor contract); `CHANGELOG.md`

---

## 1. Why there are several repositories

AAC is one product delivered from several repositories, each with one audience and one
reason to change. The reorganisation of October 2026 finished a split that began on
2026-09-01 (demos out of the product) and prepared the product tree for a public release:
everything that was lab-specific, business-specific or dead left the product repository,
and what remained was sorted by the reader who needs it.

The rule that decides where a file lives:

| If the file is… | It lives in |
|---|---|
| Product code: playbooks, roles, EDA rulebooks, EEs, installers, CI gates, product docs | **compliance** |
| A compliance decision (Rego) | **rego_policy_libraries** |
| A demo, runbook, lab or RHPDS environment, blog figure | **aac-demos** |
| Customer self-service UI or API | **AAC_Customer_Portal** |
| A third-party provider plugin (complytime, OpenSCAP) | **aac-plugins** |
| Business material, lab topology, operator runbooks and skills | **aac-internal** (private, owner only) |

## 2. The family at a glance

| Repository | Role | Visibility today | Consumes | Merge rule |
|---|---|---|---|---|
| `compliance` | The product. AAP playbooks, roles, EDA, execution environments, install paths, CI gates, product docs | private (public cut pending) | `policies/` submodule → rego library | Tim's go + code-owner approval (Juan); `Approved-By:` trailer on protected paths |
| `rego_policy_libraries` | The shared Rego policy library: every compliance decision | public | — | squash once "Check and Test Rego Policies" is green |
| `aac-demos` | Demo environments, runbooks, blogs, the lab environment, RHPDS provisioning | private | `product/` submodule → compliance at a tag | content merges freely; code PRs reviewed by norm |
| `AAC_Customer_Portal` | Customer-facing self-service portal (FastAPI + React) | private | reads `compliance_results` (contract, not code) | merge once the three required checks pass |
| `aac-plugins` | Provider plugins in Go (`complytime-provider-aap`, Alpha) | private | — | normal review |
| `aac-internal` | Business documents, lab topology, lab `CLAUDE.lab.md` and operator skills, retired docs | private, owner only, no collaborators | mirrors the git-ignored `internal/` of compliance and aac-demos | owner only |
| `aac-demo-datacenter` | The partner demo datacenter playbooks, split out of compliance 2026-09-01 | private | — | — |

## 3. What the reorganisation changed, per repository

### 3.1 compliance (the product)

Six steps, all merged except the three noted as open. No playbook changed path; that is
deliberate, because 200 controller job templates point at 177 playbook paths.

| Step | What moved or changed | PR |
|---|---|---|
| R1 | Removed what nothing called: 15 roles (11 legacy `gather_*` twins and 4 framework roles), the second `ansible_collections/` root with the GEISA collection, three stray playbooks, `data/` | #832, merged 2026-10-19 |
| R2 | Finished Phase 0 of the extraction plan: `aac.cis_facts` became `aac.host_facts` 2.0.0, one copy of the gatherers, two legacy fixes ported | #836, merged 2026-10-19 |
| R3a | Lab material left the tree: `contrib/mac-aap/`, `contrib/lab-aap-crc/`, the CRC install guide, the lab recovery runbook, the lab vault example. Lab routes and addresses replaced by required variables or `<route>` / `192.0.2.x` placeholders in 15 shipped files | #834, merged 2026-10-19 |
| R3b | The install-config hygiene gate now scans `CLAUDE.md` and no longer allowlists the lab vault example | #835, **open** |
| R4 | `CLAUDE.md` rewritten as a 131-line public contributor contract (the 987-line operator runbook and six controller-bound skills moved to aac-internal) | #833, merged 2026-10-19 |
| R5a | Nineteen loose `docs/` root files sorted into the audience folders; `docs/README.md` gives one reading path each for install, operate, extend, audit | #852, **open** |
| R5b | Three stale docs rewritten as v2.0; five retired to aac-internal | #853, **open** |
| R6 | Licence to Apache-2.0; `Dockerfile` → `Containerfile` for the MCP server and the Prometheus exporter | #823, #837, merged |
| — | Business documents left the tracked tree into git-ignored `internal/` (E6, docs by audience) | merged 2026-10-16 |
| — | README states the support boundary in its first lines | #840, merged 2026-10-19 |

Two consequences for operators:

- The post-boot recovery hook and the Windows event-log decision-environment build now
  **require** their URLs (`AAP_URL`, `OPA_COMPLIANCE_URL`, `REGISTRY`) from configuration.
  They no longer default to any environment.
- Three Golden Image helpers that only existed as lab variants (`NotifyHelpDesk`,
  `StoreEvidence`, `CurrentState_Query`) are now topology-neutral product playbooks under
  `ansible/playbooks/`. Controller templates that pointed at the deleted lab copies must be
  re-pointed at those.

Layout after the reorganisation (from `CLAUDE.md` §2): `ansible/{playbooks,roles,tasks,vars/profiles,execution-environments}`, `collections/` (the one collections root: `aac.host_facts`, `aac.m365`), `policies/` (submodule), `extensions/eda/`, `services/`, `install/`, `examples/`, `integrations/`, `grafana/`, `scripts/` (CI gates), `docs/` (by audience), `VERSION`, `CHANGELOG.md`, `RELEASING.md`.

### 3.2 rego_policy_libraries (the policy library)

Not restructured by the reorganisation; it was already its own repository with its own CI,
converters, crosswalk and standards registry. It is consumed only through the `policies/`
submodule pointer in compliance, and the pointer is a protected path (trailer required).

Counted by the library's own `make count` on 2026-10-20 at main `23694a1`: 804 policy
files, 1,985 including tests, 20,387 control-level checks. Count it, never quote it.

One side effect of the reorganisation window is recorded here because it crosses the two
repositories: compliance #818 advanced the pointer by 14 library commits, which retired two
rules that five compliance suite tests called and made CI run the library's full test set
on a two-core runner. #854 (open) fixes the tests and restricts CI to the compliance suites.

### 3.3 aac-demos (demos, runbooks, lab)

The receiving side of the reorganisation. It gained:

| Content | From | PR |
|---|---|---|
| `demos/lab-crc/` — the maintainers' lab environment as a documented example (51 files plus the dashboard validation workflow) | compliance `contrib/` | #49, merged 2026-10-18 |
| `demos/geisa/` — GEISA device provisioning, kept as a paused demo with its two security-review findings recorded | compliance `ansible_collections/` | #47, #48 |
| `internal/` (git-ignored) for its own business material | — | #46 |

Everything else was already here from the 2026-09-01 split: `demos/` (golden_image,
mythos_patch, nerc_cip_ami, m365, sentinel, digital_sovereignty, rhpds, customer-poc and the
rest), `config_as_code/`, `customer_profiles/`, `extensions/`, `docs/`, `scripts/`. The product
is reached only through the `product/` submodule, pinned at a tag; nothing in the product may
read from `demos/` at runtime, and compliance enforces that with
`scripts/check_core_demo_boundary.py`.

### 3.4 AAC_Customer_Portal

Unchanged by the reorganisation. `api/` (FastAPI), `frontend/` (React, PatternFly), `deploy/`,
`docs/`, `scripts/`. Its only coupling to the product is the `compliance_results` table
contract. `api/migrations/` is a protected path.

### 3.5 aac-plugins

Unchanged and quiet (last push 2026-04-30). Go provider plugins under `plugins/`; the
complytime provider for AAP is Alpha. It follows the family into the public organisation at
cut time.

### 3.6 aac-internal

Created 2026-10-17 as the private home for everything the reorganisation took out of the
public trees: `compliance/` and `aac-demos/` folders that mirror each repository's git-ignored
`internal/` (business documents, statements of work, plans, retired docs), the lab operator
`CLAUDE.lab.md`, and the six controller-bound skills. Owner only; never add collaborators.
When `internal/` changes in either working tree, push the change here.

## 4. The seams that hold it together

- **Submodule pins.** compliance pins the policy library (`policies/`); aac-demos pins the
  product (`product/`) at a release tag. A policy change is: merge in the library, bump the
  pointer in compliance with the trailer, then bump the product pin in aac-demos.
- **Protected paths and the trailer.** `policies/`, `.github/workflows/` and `enforcement/git/`
  in compliance; `api/migrations/` in the portal; `enforcement/git/` in the library. A change
  there carries `Approved-By: ynotbha@aisle-five.com` in the commit message, and
  `approval_policy.rego` checks it in CI.
- **Hygiene gates.** `Install config hygiene` and `check_no_hardcoded_endpoints.py` fail any
  compliance PR that carries an address, route, credential or controller id; after R3b the
  gate also reads `CLAUDE.md`. Example values are placeholders.
- **Core/demo boundary.** Zero tolerance: no product path reads from `demos/`.
- **Lab pin during demo week.** The lab controller's projects track the tag
  `lab-pin-2026-10-16` on both repositories, so merges to `main` cannot change a demo
  mid-week. Unpin after the live week and re-point the five lab templates named in R3a.

## 5. What comes after the cut

Decided 2026-10-16 and recorded in the reorganisation plan:

1. The public repository is **`ansible-automated-compliance/aac`**, cut fresh from the
   cleaned private tree as a single first commit. It becomes the working repository; the
   private one is archived read-only. The rest of the family follows under the same
   organisation (`rego-policy-library`, `aac-pack`, `aac-plugins`; `aac-demos` only if it is
   released).
2. Still to merge before the cut: #835 (R3b), #852 and #853 (R5), #854 (tests against the
   pinned library). Then a final scan of the exact tree for secrets, addresses and business
   terms, and the submodules re-pointed.
3. **After** the cut: group the playbooks by job (assess, store, report, seed, deploy, lab),
   which changes 177 template paths and so needs a path map and a scripted controller update;
   then the collection extractions E1 to E5 (`aac.m365`, `aac.host_facts` once wired in,
   `aac.platform`); then the variable-naming rule and the shared site-config loader.

---

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-10-20 | First version: state of the seven repositories after R1 to R6 |
