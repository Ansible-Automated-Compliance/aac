# AAC Change Governance

**Version:** v1.0
**Date:** 2026-08-29
**Audience:** Contributors, the BU and engineering teams evaluating transition, and anyone asked "does this project have change control?"
**Authors:** Tim Coulter (Red Hat) with Claude (Anthropic)

---

## 1. Why this document exists

A customer installed AAC, hit problems, and said it looked like *"an ad-hoc
in-home project, not treated as a proper solution, with no change controls or
release management."*

That was a fair reading of what they could see. This document describes what
actually governs a change to this codebase, what is mechanically enforced,
and — in §8 — where the governance is still weaker than it looks. A governance
document that only describes the controls that work is marketing.

Companion documents:

| Document | Covers |
|---|---|
| `RELEASING.md` | How a release is cut, versioned and tagged |
| `CHANGELOG.md` | What each release contained, including its known limitations |
| `CONTRIBUTING.md` | How to add a policy, playbook or rulebook |
| `docs/AAC_HONEST_STATUS_AND_POSITIONING.md` | What is supported and what is not |

---

## 2. The three repositories

A change may touch one, two or all three. They are versioned independently.

| Repository | Contains | Consumed by |
|---|---|---|
| **`compliance`** | Playbooks, rulebooks, installers, demos, docs | The customer, directly |
| **`rego_policy_libraries`** | The Rego policy content | `compliance` and the portal, as a **git submodule** |
| **`AAC_Customer_Portal`** | Customer-facing portal (FastAPI + React) | The customer, directly |

**The submodule pointer is the contract.** A policy change does not reach any
deployment until `compliance` advances `policies/` to a commit that contains it.
Two consequences that have caused real defects:

- A PR that adds a workflow referencing a new policy file **must bump the
  submodule in the same PR**, or `main` briefly points at a workflow whose
  policy does not exist.
- The pinned commit must be **merged on the library's `main`**, not a branch
  tip. `RELEASING.md` has the check.

---

## 3. How a change reaches `main`

```
  branch  ──▶  pull request  ──▶  CI gates  ──▶  review  ──▶  merge  ──▶  release
   │              │                  │             │            │           │
 feat/ fix/    never push to      five           human +      squash     RELEASING.md
 chore/ docs/  main, ever        workflows      Copilot      + delete
```

### Branches

`feat/`, `fix/`, `chore/`, `docs/`, `test/` + a short description.
**Never push directly to `main`.** This is not advisory; it is how every change
in the repository has landed.

### Commits

Conventional Commits: `type(scope): summary`.

The body is where the value is. State **what was wrong and why the fix is the
fix**, not just what changed — a reviewer reading the diff can see what changed.
Where a defect had a non-obvious cause, record the cause, because the next
person to touch that code will otherwise reintroduce it. Several comments in
this codebase exist precisely because that was not done the first time.

### Pull requests

One PR per coherent change. Batch related fixes from one review into one PR
rather than opening five.

The PR body should let a reviewer decide **whether to trust the change** without
reading every line: what was broken, what the fix does, what you verified, and
what you deliberately did not do.

---

## 4. What CI enforces

Five workflows. Each exists because something got through without it.

| Workflow | Enforces | Triggered by |
|---|---|---|
| **Change Approval Check** | Protected paths carry an `Approved-By:` trailer from an authorized approver. Evaluated as Rego (`policies/enforcement/git/approval_policy.rego`), not shell | every PR |
| **OPA Policy Validation** | `opa check` + the full policy test suite | policy changes |
| **Ansible Validation** | YAML parses · `ansible-playbook --syntax-check` · every Jinja expression lexes · repository hygiene policy | `ansible/**` |
| **Install Config Hygiene** | No site addresses or credentials in shipped files · operator config stays untracked | every PR |
| **mac-aap Dashboards** | Every Grafana panel's SQL runs against a disposable schema | dashboard changes |

### Two properties worth understanding

**The gates are policy, not scripts.** The rules live in the shared library
(`policies/enforcement/repo/`, `policies/enforcement/ansible/`, `policies/enforcement/git/`) and carry unit
tests, so the gate itself is tested. The same rule can gate CI and, through AAP
Policy as Code, job launch — one rule, two enforcement points.

**Every gate has a vacuous-pass tripwire.** Each step prints how much it
examined and fails if the count is implausibly low. This is not decoration: a
gate in this repository once reported *"checked 221 files"* in 2.7 seconds while
running nothing at all, because an indentation bug made every file take an early
exit. It passed, and it was worse than having no gate, because it was believed.

**A green badge is not evidence.** Read the counts. `RELEASING.md` makes this a
release condition.

---

## 5. Protected paths and approval

Defined in `policies/enforcement/git/approval_policy.rego`:

```
policies/            .github/workflows/            ansible/
opa/                 aap-integration/
```

A PR touching any of these needs a commit-message trailer:

```
Approved-By: ynotbha@aisle-five.com
```

**Why a trailer and not a GitHub review.** The project has effectively one
maintainer, and GitHub will not let an author approve their own PR. The trailer
records that the change was authorized by the person accountable for it, and it
lives in the commit — so `git log` carries the approval record, not just the PR
UI. That matters for a compliance product: the audit trail should survive the
forge.

**What this does not do.** It records authorization; it does not constitute
independent review. See §8.

---

## 6. Review

Every substantive change gets three passes:

1. **Author + Claude** — implementation and self-verification.
2. **GitHub Copilot** — an independent second read on the PR diff.
3. **A required human maintainer** — the *other* of the two code owners
   (Tim Coulter `@ynotbhatc` / Juan Medina `@R0tt3nT0m4t0`) must approve before
   merge. Because an author cannot approve their own PR, this guarantees a second
   human with product context signs off on every change. Enforced by branch
   protection (`require_code_owner_reviews`) plus `.github/CODEOWNERS`; the
   required CI checks must also be green. An admin break-glass merge remains
   available for emergencies and is the exception, not the norm.

Copilot's review is pinned to the diff at review time and does not re-fetch
`main`. If it says something is "still not fixed" after a follow-up PR merged,
it is looking at an old snapshot — check `main` before acting.

This pairing has repeatedly caught real defects, including several this process
would otherwise have shipped. It is a genuine second opinion, and it is not a
substitute for a human reviewer with context on the product.

---

## 7. What a change leaves behind

For a compliance product, the audit trail of the product's own changes should be
at least as good as the evidence it collects. A merged change leaves:

| Artifact | Answers |
|---|---|
| Commit message + `Approved-By` | What changed, why, who authorized it |
| PR + CI run | What was verified, and with what output |
| `CHANGELOG.md` entry | Which release it reached |
| Git tag | Exactly which bytes a deployment is running |
| Submodule pin | Which policy content shipped with it |

Until 2.8.0 the last three did not exist. That is the gap the customer noticed.

---

## 8. Where this is still weak

Stated plainly, because the alternative is that someone else finds it.

**Approval is a formality, not a control.** The author writes the trailer and
admin-merges their own PR. With one maintainer there is no alternative that is
not theatre, but it should not be described as independent review. *If AAC moves
to a team, this is the first control to make real* — require a GitHub review
from a second person on protected paths and drop the trailer to a record rather
than the gate.

**`ansible/` is a protected path, which is nearly the whole repository.** Almost
every change needs the trailer, so adding it becomes reflex rather than a
decision. A control that fires on everything signals nothing. Worth narrowing to
the paths where authorization genuinely matters.

**The hygiene gate does not cover the whole tree.** It scans `ansible/`,
`install/`, `scripts/`, `extensions/` and `grafana/`. It does **not**
scan the repository root, `docs/`, or `.claude/`. As of 2026-08-29 there are
tracked files outside its scope carrying lab addresses — including `README.md`,
`CONTRIBUTING.md`, `CLAUDE.md`, several skill definitions, and
`install_config.example.yml`, which is an operator-facing template. Widening the
scope means deciding which of those legitimately describe the lab.

**Maintainer lab tooling is not in this repository.** `install/mac-aap/` became the
unsupported `contrib/` tier on 2026-08-31 (outside the hygiene gate by design) and left
the product tree for the aac-demos repository (`demos/lab-crc/`) on 2026-10-17. The gate
therefore has no unsupported tier to exempt; the only allowlisted lab file is
`ansible/vars/profiles/lab.yml`, which is the lab's addresses by definition. See
`install/SUPPORT_MATRIX.md`.

**There is no `CODEOWNERS`.** Nothing routes a change to whoever knows that area.

**The delivery layer is thinly tested.** 221 playbooks, 9 tests. The CI gates
check structure — that files parse, templates render, no credential ships. They
do not check that a playbook does the right thing. Three roles currently cannot
run at all because they include task files that do not exist.

**Documentation drifts and CI does not catch it.** Counts of policies, tests and
frameworks have gone stale in several documents at once. `CLAUDE.md` and
`RELEASING.md` now say to read `VERSION` and to count the policy library at the
pinned commit rather than quoting from memory, but nothing enforces it.

---

## 9. If you are evaluating this for transition

The honest summary for a BU or engineering team:

- **The policy layer has real engineering discipline** — hundreds of tests, CI
  gates, fail-closed design, and a project willing to publish defects in its own
  evidence.
- **The delivery layer has the discipline of a demo harness that is being
  retrofitted.** The gates described here were added in August 2026, after a
  customer install went badly. They are new, and they are real, and they do not
  yet cover behaviour.
- **The governance is single-maintainer governance.** It is honest about that.
  Every control in §5 and §6 was designed around one person being accountable,
  and several would need to change on the day a second maintainer arrives — §8
  says which.

What would need to be true for this to be owned by a team is a separate
question, addressed in `docs/integration/ANSIBLE_POLICY_AS_CODE_vs_AAC.md` §6.

---

## Revision history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-08-29 | First change-governance document. Written after a customer described AAC as having no change controls, and alongside the first tagged release in the `2.x` lineage. |
