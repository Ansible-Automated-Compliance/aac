# Phase 7 — Branch Governance & Handover: Decision Document

**Version:** v1.0
**Date:** 2026-09-01
**Authors:** Tim Coulter · Claude (Anthropic) — AI-assisted authorship
**Status:** FOR DISCUSSION — nothing in this document is executed yet
**Audience:** Tim, Juan Medina, the receiving Red Hat engineering team, and (if ownership
moves) the Ansible Business Unit

---

## Why this document exists

Phases 0–6 of the restructure are complete: the `compliance` repository is product-only,
demo content lives in `aac-demos` (product pinned as a submodule), every CI gate is in
place, and the live controller passed a full zero-check. **Phase 7 is the only remaining
phase, and it is deliberately different: it is not a code change — it is a change to how
people work.** Every item below alters someone's daily workflow, so each one is framed as
a decision to discuss *before* anything is executed.

A decision that is premature is worse than one that is late: turning on required reviews
today, with one maintainer, would block every merge in the repository including the
maintainer's own. The guiding rule throughout:

> **Protection follows people.** Each control turns on when the team exists to satisfy
> it, not before.

---

## The decisions

### D1 — Create the `dev` branch (contributor integration)

**DECISION NEEDED: create `dev` now, or at handover day?**

What it is: a long-lived integration branch. Contributor PRs land on `dev`; `main` only
advances by promotion (D2). `main` stays release-quality at all times because the
controllers track it (D9).

| Option | Consequence |
|---|---|
| **A. Create now (recommended)** | Costs nothing, signals the intended flow to Juan's contributors immediately, lets CONTRIBUTING point at something real. Until protection exists it is convention, not enforcement — that is fine. |
| B. Create at handover | Nothing breaks, but contributors who arrive early PR against `main` and learn the wrong habit. |

Note: this is NOT a content branch. The restructure rejected content branches with
evidence (`master` rotted 1,223 commits behind; `sentinel-demo` 731). `dev` carries the
same content as `main`, just earlier in time. The one derived branch that exists —
`eda` in aac-demos — is CI-generated and hand-edit-proof, which is the only kind of
non-main branch this ecosystem tolerates.

---

### D2 — The promotion flow (`dev` → `main`)

**DECISION NEEDED: what promotes, who promotes, and on what cadence?**

Proposed mechanics (aligns with RELEASING.md):

1. Contributor PRs merge to `dev` when CI is green + review passes.
2. A **promotion PR** (`dev` → `main`) is opened when a release is intended.
3. The promotion PR must satisfy the seven release-readiness conditions in RELEASING.md.
4. Merge of the promotion PR == the release: tag is cut, CHANGELOG entry finalized,
   `VERSION` already bumped on `dev` as part of release prep.
5. `aac-demos` advances its `product/` submodule pin to the new tag afterwards — that is
   the moment demos see the new product.

Open discussion points:

- **Cadence** — per-release (recommended; releases when ready, no calendar pressure) vs
  fixed weekly/biweekly trains. Trains create pressure to promote unfinished work.
- **Who merges the promotion PR** — the maintainer role (Tim today; the RH team lead
  after handover). This is the single most powerful action in the repo and should map to
  the fewest people.
- **Hotfix path** — a critical fix that cannot wait for the next promotion: branch from
  `main`, fix, PR straight to `main` (with review), cherry-pick back to `dev`. Needs to
  be written into CONTRIBUTING or it will be invented ad hoc under pressure.

---

### D3 — Branch protection on `main`

**DECISION NEEDED: which controls, and in what order?**

The controls are separable — they do NOT have to turn on together:

| Control | What it does | When it can turn on |
|---|---|---|
| Required status checks | PR cannot merge unless the named CI gates pass | **Any time — even today.** Gates already exist and pass; making them required blocks nobody who is doing the right thing. |
| Required reviews (1+) | PR needs an approval that is not the author's | **Only when ≥2 maintainers exist.** With one maintainer this blocks every merge. |
| `enforce_admins` | Admins (Tim) lose the bypass — rules bind everyone | **Last.** This is the formal end of the admin-merge / "go" pattern (D5). |
| Linear history / no force-push | Protects the audit trail | Any time; effectively true already. |

Recommended required checks (from the existing gate set): Validate Ansible content ·
Install config hygiene · Validate Approvals · Validate Policy Changes · link check.
Discussion: should the boundary gate and EDA template-ref gate (currently inside
`validate_playbooks.sh`) be surfaced as separately-named required checks so a failure is
legible at a glance in the PR UI?

---

### D4 — Protection on `dev`

**DECISION NEEDED: how heavy is `dev` protection?**

Recommendation: **checks required, reviews optional** at first. `dev` is where
contributors iterate; requiring reviews there doubles the review load for the same code
(it gets reviewed again at promotion). Revisit if `dev` quality becomes a promotion
bottleneck. `enforce_admins` on `dev`: not needed — `dev` is not what controllers run.

---

### D5 — The end of admin-merge (the "go" pattern)

**DECISION NEEDED: what replaces the current authorization flow, and when?**

Today: author opens PR → Tim authorizes ("go") → admin-merge. This exists because the
author cannot approve their own PR and there is no second maintainer. It is honest and it
is logged, but it is also exactly what `enforce_admins` exists to end.

The transition:

| Stage | Flow |
|---|---|
| Today (1 maintainer) | admin-merge on Tim's explicit go — unchanged |
| Handover (≥2 maintainers) | required reviews ON; the second maintainer reviews; admin-merge retired for normal work |
| Steady state | `enforce_admins` ON; admin bypass reserved for documented break-glass (outage, security fix), each use explained in the PR |

Related: **does the `Approved-By:` trailer survive?** It predates GitHub-native review
and is enforced by the rego `git_approval` policy on protected paths
(`policies/`, `.github/workflows/`, `enforcement/git/`). Options:

- Keep both (trailer + GitHub review) — belt and suspenders, slight friction.
- **Retire the trailer once required reviews are on; keep the rego policy for protected-
  path *detection* only (recommended)** — GitHub review becomes the approval record; the
  policy still names which paths are sensitive.
- Keep trailer only for the rego library (it is public and has outside consumers).

---

### D6 — VERSION → 3.0.0

**DECISION NEEDED: cut 3.0.0 now, or with the first post-handover release?**

The case for now: the split is a completed breaking change (demos/ gone, RHPDS tooling
moved, install methods consolidated) — exactly what a major version is for. The
`v2.9.0-pre-split` tag already marks the before-state; `v3.0.0` marks the after. The
aac-demos submodule pin then advances to `v3.0.0` and the demos officially consume a
release, closing the loop the split was designed for.

The case for waiting: 3.0.0 lands as the handover team's "first release," giving them a
clean starting line and ownership of the number.

Recommendation: **cut v3.0.0 now.** The split is Tim's work and the version should record
reality; the handover team's first release will be 3.1.0. Mechanics per RELEASING.md
(release action, own PR, CHANGELOG "Unreleased" → "3.0.0", tag, then the submodule-pin
advance in aac-demos).

Housekeeping folded in: the dead `0.x` GitHub-release numbering scheme should be
explicitly closed out in the release notes so nobody resurrects it.

---

### D7 — CODEOWNERS and reviewer population

**DECISION NEEDED: who are the named owners after handover?**

CODEOWNERS currently names Tim. Required reviews route through it, so it must be real
before D3's review requirement turns on. Needs from the receiving team: 2+ named GitHub
handles per area (ansible/, policies/ submodule pointer, .github/workflows/, install/).
Until names exist, this blocks D3-reviews and D5 — which is precisely why Phase 7 waits
for the handover conversation.

---

### D8 — Ownership transfer (Ansible BU contingency)

**DECISION NEEDED: none yet — but the constraint list should be agreed now.**

If the Ansible BU takes the repos into their org, the following must move or re-key.
Everything on this list is already parameterized or single-point — keep it that way:

| Item | State |
|---|---|
| Controller project URLs (7, 247, EDA 1, EDA 3) | Single-point config on the controller; update at transfer |
| aac-demos `product/` submodule URL | One line in `.gitmodules` |
| RHPDS bootstrap repo URLs | Vars (`compliance_repo`, `aac_demos_repo`) — already parameterized |
| GHCR OPA-bundle publish (rego repo) | Package + GHCR_PAT re-key under new org |
| EDA GitHub credential (cred 2), controller PAT (cred 4), aac-demos deploy key | Re-mint under new org |
| Traffic tracker (3-repo snapshots) | Repo slugs in one workflow |
| Visibility gate | Tim's policy: private until 5–6 successful POCs; transfer does not change the gate |

Standing rule to agree: **no new hardcoded org/repo URLs anywhere** — every new
integration takes the URL as a variable.

---

### D9 — Controllers and the default branch

**DECISION NEEDED: confirm as policy (this one is really a confirmation, not a choice).**

Controllers resolve projects BY NAME and track `main`. That stays true in the promotion
model — `main` is always release-quality, so controllers tracking it is safe *because of*
D2. Two rules to write down:

- No AAP/EDA project may ever point at `dev`. `dev` is CI-territory only. (The by-name
  create-if-absent resolution makes a second same-name project a silent ambiguity — the
  failure class Phase 0 killed.)
- Scheduled workflows (nightlies, traffic tracker, hygiene) run from `main` only —
  GitHub runs scheduled workflows from the default branch, so this is enforced by the
  platform; noting it so nobody expects a nightly to exercise `dev`.

---

### D10 — Handover-day sequence (when all decisions are made)

The order of operations, each step reversible before the next:

1. Confirm CODEOWNERS names with the receiving team (D7)
2. Create `dev` from `main` (D1) — if not already done
3. CONTRIBUTING update: contributor flow → `dev`, hotfix path, promotion rules (D2)
4. Required status checks ON for `main` and `dev` (D3/D4 — safe, blocks nobody)
5. Required reviews ON for `main` (D3) — the go-cadence retires here (D5)
6. `enforce_admins` ON (D3) — break-glass documented
7. Trailer decision executed (D5)
8. VERSION → 3.0.0 release if not already cut (D6); aac-demos pin advances
9. Update the memory/CLAUDE.md contracts so every future session works the new flow

---

## Pre-work that needs no discussion

Safe to execute any time on Tim's word, independent of the decisions above:

- Create `dev` (D1-A) and update CONTRIBUTING with the intended flow marked "effective at
  handover"
- Cut v3.0.0 (if D6 lands on "now")
- Surface boundary + EDA gates as named CI checks (D3 prep)

## Open items this document deliberately excludes

- iso27001/pci_dss/soc2 dead role-family deletion (parked, awaiting Tim)
- Fork reconciliation (rhpds ×7, mac-aap ×9 historical forks)
- RHPDS bootstrap first live validation (at next cluster provisioning)
- aac-demos/aac-demo-datacenter visibility (gated on 5–6 successful POCs — Tim's call)
