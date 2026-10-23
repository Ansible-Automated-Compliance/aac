# AAC Multi-Repository Extraction — Implementation Plan

**Version:** v0.1
**Date:** 2026-10-08
**Status:** Proposal — answers Juan Medina's *AAC Multi-Repository Extraction Plan* v1.0 (2026-09-23)
with a verified inventory, the adjustments the evidence requires, and a concrete Phase 0 work
breakdown. Nothing here is executed yet.
**Authors:** Tim Coulter; Claude (Anthropic), co-author
**Related:** Juan's plan v1.0 (PDF, not yet in the tree); tracking issue #695; `install/SUPPORT_MATRIX.md`;
`docs/PHASE7_GOVERNANCE_DECISIONS.md`; `docs/operations/PLAYBOOK_CONFIG_STANDARDIZATION_PLAN.md` (PR #781)

---

## 1. Verdict on the plan

Juan's direction is right and this document does not reopen it: extract Galaxy collections with a
clear API, keep the facts → OPA → PostgreSQL spine (`aac_store_results`, routing, playbooks,
schema, `VERSION`) in core, pin through EE image tags plus the `policies/` submodule SHA, never
one repo per role, never Rego inside a collection repo. His anti-pattern list (§10) stands as
written.

Three things the current tree changes, and one naming decision from Tim:

1. **Phase 0 is not done.** Issue #695 is closed as *completed* (2026-09-29), but on `main` today
   the 11 legacy `ansible/roles/gather_*` roles still exist, every one still differs from its
   collection twin, the two task-logic fixes the issue said to port first are still unported
   (`gather_filesystem_config` 20 differing lines, `gather_logging_config` 17), and there are
   0 FQCN references to `aac.cis_facts.*` anywhere. Six docs still name the legacy roles.
   Recommendation: reopen #695 or supersede it with this plan's P0 issue.
2. **The facts collection has no runtime consumer.** Neither copy of the `gather_*` roles is
   called by any playbook. `cis_rhel9_assessment.yml` builds `opa_input.ansible_facts` from
   `gather_facts` plus its own tasks; `aac_facts_collector` has its own `linux_*` task files and
   does not include the roles either. Extracting `aac.cis_facts` to its own repo (Juan's Phase 2)
   therefore ships a collection nothing uses. The order should be: dedupe → rename → **wire it in
   as the gatherer** (behind `aac_facts_collector`) → prove facts → OPA → row on the lab → then
   extract. The extraction DoD already requires that end-to-end run; it is impossible for a
   collection with no caller.
3. **EE pins are floating today.** Every `execution-environments/*/requirements.yml` pins third-party
   collections with `>=`. The plan's DoD (§8.4: "pins the version, not `*` / floating") needs the
   `aac.*` entries added as exact versions when Phases 1–2 land, and the existing `>=` entries
   reviewed at the same time.
4. **Naming (Tim's critique).** `aac.cis_facts` is too specific: the gatherers collect host
   configuration that CIS, STIG and NERC CIP all consume, and the fact keys are `cis_ssh_facts`,
   `cis_pam_facts`, …. Recommendation: rename to **`aac.host_facts`** with fact keys
   **`host_*_facts`** *now*, in-tree, in Phase 0 — the only moment it is free. No Rego file reads the
   `cis_*_facts` keys (0 matches under `policies/`), no playbook consumes them, so the rename is a
   directory move to `collections/ansible_collections/aac/host_facts/`, plus updates to `galaxy.yml`,
   all role fact-key definitions and reads, and READMEs (E0.2), with no coordinated policy bump. After the
   collection has a Galaxy/PAH artifact and an EE pin, the same rename is a major version and a
   cross-repo event.

## 2. Inventory, re-verified 2026-10-08 (`main` 3a1567c6)

| Juan's row (2026-09-23) | Today | Change |
|---|---|---|
| `collections/…/aac/m365/` full collection + `aac-m365-ee` | present, `galaxy.yml` 1.1.1, 2 roles, 16 modules, 4 playbooks, tests; `docs/m365/` present; EE present | unchanged — still the best first extraction |
| `collections/…/aac/cis_facts/` shell with 11 `gather_*` roles | present, 1.0.0, 11 roles | unchanged |
| `ansible/roles/gather_*` (11) near-identical twins | 11 present; all 11 differ from the collection (metadata everywhere; task logic in 2) | **not deduped** |
| `collections/…/lab/eda/` | present, 1.0.0 | unchanged |
| `ansible_collections/geisa/device_management/` | present | unchanged |
| Platform roles `aac_opa_containers`, `aac_compliance_db`, `aac_mcp_server`, `aac_post_boot`, `aac_enforceauth_bridge`, `aac_bundle_consumer` | all present; 1–3 playbook/install consumers each | unchanged |
| `aac_store_results` ~26 refs | 19 playbook/install refs | fewer, still the shared contract |
| Roles under `ansible/roles/` ~25 | 28 | +3 |
| EEs | 8 (`compliance`, `m365`, `ami`, `policy-tools`, `satellite`, `sovereignty`, `windows`, `zift`) | more than the plan assumed; each pins with `>=` |
| Project-level `collections/requirements.yml` | absent; `collections/README.md` forbids it | matches the plan's rule |
| `ansible.cfg` `collections_path = collections` | set | plan §6.1 item 4 done |
| Docs tree | already categorized (`architecture/ frameworks/ install/ integration/ operations/ reference/ strategy/ marketing/ sow/ m365/ runbooks/ reports/ security/`) | Phase 6 is a move of three directories, not a re-sort |
| Publication target | lab Private Automation Hub (galaxy_ng in AAP 2.7) mirrors certified content; AAP pulls from PAH | exists — the publish path for Phases 1–3 |

## 3. Adjusted phase order

Juan's phase numbers collide with the handover plan's (#695 redline). This document uses **E0–E6**.

| Phase | Juan's | What changes here | Gate to exit |
|---|---|---|---|
| **E0 — in-tree hygiene** | Phase 0 | Port the two legacy fixes; declare the collection the source of truth; **rename to `aac.host_facts` / `host_*_facts`**; delete the 11 legacy roles; flip the 6 doc references to FQCNs; **wire the collection in as `aac_facts_collector`'s gatherer** (or a new `aac_gather_host_facts.yml`) so it has a caller; fold in #672 (versioned OPA image in `aac_bundle_consumer`); land the config-loading standardization P1 (PR #781) in the same window | one lab job runs the collection roles end-to-end and the two repaired facts appear in a stored row (the receipt #695 describes) |
| **E1 — extract `aac.m365`** | Phase 1 | as Juan wrote it; EE pins the collection **tag**, not `>=`; CI in the new repo matrix-tests collection × `cis_m365_v7` at the policies SHA | DoD §8 all six items |
| **E2 — extract `aac.host_facts`** | Phase 2 | only after E0's wiring gate; freeze the fact-key schema as a versioned document validated before persist (#695 redline, Nick's gap) | DoD §8 |
| **E3 — `aac.platform`** | Phase 3 | as written; `aac_bundle_consumer` last within the phase (still absorbing review rounds) | DoD §8 |
| **E4 — stays in core** | Phase 4 | unchanged list | — |
| **E5 — niche / install repos** | Phase 5 | unchanged; not before E3 | — |
| **E6 — docs by audience** | Phase 6 | `docs/marketing/`, `docs/sow/`, `docs/strategy/` leave the engineering tree; destination to be named (aac-demos? a docs repo?) | — |

Every lab-verification step assumes #779 (the `demo/ao-setstats` merge) is on `main` **and** that
lab project 7 has been repointed from `demo/ao-setstats` to `main` and re-synced — merging #779
does not move the branch the project checks out. Each receipt job must show an SCM revision that
contains the phase's commits (job → *SCM revision* in AAP) before its result counts; otherwise the
receipt exercises stale code.

## 4. E0 work breakdown

All E0 work is in-tree, on upstream branches (fork PRs cannot run CI without a maintainer
approving each run), no new repositories. `ansible/` is not a Rego-enforced protected path; the
one workflow edit is Tim's commit.

| # | PR | Scope | Owner | Size |
|---|---|---|---|---|
| E0.1 | Port legacy fixes | 3-way diff of all 11 twins (all files); port every legacy-only task fix into the collection (`gather_filesystem_config`, `gather_logging_config` confirmed; sweep the rest) | Juan or Claude | 1 PR, ~40 lines |
| E0.2 | Rename | move the directory to `collections/ansible_collections/aac/host_facts/` (`ansible.cfg` resolves FQCNs by path, not by `galaxy.yml`); `galaxy.yml` → `aac.host_facts` 2.0.0; every fact-key reference inside the roles — the `set_fact` definitions **and** the roles' own reads of them (e.g. `gather_logging_config/tasks/main.yml` reads `cis_logging_facts` back) — `cis_*_facts` → `host_*_facts`; completeness check `grep -rn 'cis_' collections/ansible_collections/aac/host_facts/` returns only CHANGELOG/README history; collection README documents the key schema (the frozen contract E2 needs) | Claude | 1 PR |
| E0.3 | Wire in | `aac_facts_collector` (or `aac_gather_host_facts.yml`) calls `aac.host_facts.*` roles and merges their facts into the payload that reaches OPA; job template on lab | Claude, Juan runs the lab job | 1 PR + 1 lab run |
| E0.4 | Delete + flip docs | remove `ansible/roles/gather_*` (11); point `ansible/roles/README.md`, `docs/operations/VALIDATION_STRATEGY.md`, `docs/reference/FAQ.md`, `docs/architecture/ENTERPRISE_ARCHITECTURE.md`, `docs/frameworks/COVERAGE_COMPARISON.md`, `docs/frameworks/CIS_TECHNICAL_COMPONENTS.md` at the FQCNs | Claude | 1 PR |
| E0.5 | Gate | CI check scoped to executable content: no `ansible/roles/gather_*` directory; no `aac.cis_facts.` FQCN and no `collections/ansible_collections/aac/cis_facts/` path in `ansible/`, `collections/`, `extensions/` or `execution-environments/*/requirements.yml`; `aac.host_facts` resolves (`ansible-galaxy collection list` in the EE build). Documentation history and `.gitignore`'s unrelated fact-output rule are out of scope | Tim (workflow file) | 1 PR |
| E0.6 | #672 | versioned, registry-compliant OPA image default in `aac_bundle_consumer` | Claude | 1 PR |
| — | #781 P1 | 55 literal connection values out of 28 playbooks; shared optional loader | Claude, after #777 merges | 1–2 PRs |

Exit: the lab receipt from E0.3, `ansible/roles/gather_*` gone, `aac.host_facts` 2.0.0 tagged in-tree.

## 5. Decisions needed

1. **Name**: `aac.host_facts` (recommended), `aac.os_facts`, or `aac.system_facts`? And rename the
   fact keys in the same move (recommended — it is free now) or keep `cis_*` keys for a later
   major?
2. **#695**: reopen, or close for real by superseding it with an E0 tracking issue that links this
   document?
3. **Wiring target** (E0.3): make `aac_facts_collector` call the collection, or add a new
   `aac_gather_host_facts.yml` playbook and leave the collector's own `linux_*` tasks alone until
   E2? Recommendation: new playbook first (no change to the collector's existing payload), fold
   into the collector in E2 when the schema is frozen.
4. **Repository names** for E1–E3 (`ynotbhatc/aac.m365` vs `ynotbhatc/ansible-collection-aac-m365`)
   and the **publish target** (lab PAH only, or also public Galaxy).
5. **Juan's v1.0 → v1.1 in the tree**: his plan is a PDF outside the repo. Land it as
   `docs/architecture/AAC_MULTI_REPO_EXTRACTION_PLAN.md` v1.1 with the #695 redlines, under his
   authorship, so the two documents sit together.

## 6. Risks specific to the adjusted order

- **Renaming after publish is a major version**; hence E0.2 before any artifact exists.
- **Wiring the collection in changes the OPA input shape** only if its facts are merged into the
  existing payload keys; E0.3 adds new keys (`host_*_facts`) and leaves `ansible_facts` as is, so
  current Rego is unaffected until a policy chooses to read the new keys.
- **Issue #695 says "completed"**; anyone reading it will assume E0 is done. Decision 2 fixes that.
- **Fork workflow friction**: Juan's PRs come from his fork, which never runs Actions until Tim
  approves the run. E0 PRs should be upstream branches so CI is the review gate.

---

*Verified with `find`, `diff -r` and `grep` over `main` 3a1567c6 on 2026-10-08; commands are
reproducible from the counts in §2. Juan's plan v1.0 is quoted by section number throughout.*
