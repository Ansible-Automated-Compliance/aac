# Pre-engagement verification gate

**Version:** v1.0
**Last Updated:** 2026-08-24
**Owner:** must be someone who did **not** author the thing being checked
**Run:** within 3 working days of any customer engagement — demo, POC, or workshop
**Authors:** Tim Coulter · Claude (Anthropic)

---

## Why this exists

Every defect found in the recent NERC-CIP, patch and Windows demo work was found by
**running** something. None was found by writing it, reading it, or reviewing it.

A single week produced:

| Defect | How it presented |
|---|---|
| Three playbooks targeting the execution environment instead of the host | Backup, install and assurance all silently ran against the EE. Only surfaced because the EE has no `sudo` — with sudo present all three would have "succeeded" and been wrong |
| Patch workflow dead at node 02 | Duplicate `host_id` after an identity cutover; the collector fix was already merged and did not repair existing rows |
| Demo estate inflated 24× | "98 hosts" where 4 were real; the rest were container ids and ephemeral AWS names |
| CIP-015 described as enforceable | Our doc said April 2026; it is October 2028 |
| "NERC-CIP certified" | No such certification regime exists |
| Windows decision environment | Existed in no registry; the demo could not have run as documented |
| Enforcement firing every ~35s | Only visible with a live host and a running activation |
| A committed registry password | Added in the same change that carefully avoided committing a different password |
| A demo running months-old code | A second project pinned to a squash-merged branch; its sync succeeded every time while guaranteeing stale playbooks |

Every one was cheap to fix. Every one looked fine until executed. **A compliance
function is precisely the audience that finds this class of error**, and a POC at a
registered entity is the worst place to find it.

## The rule

> **Nothing is "ready" because it was written, merged, or previously worked.
> It is ready because someone ran it this week and watched it finish.**

And the second rule, which is why the owner matters:

> **The author cannot be the verifier.** Every defect above passed its author's own
> review. Authors verify what they intended to build; a second person runs what
> actually exists.

---

## The gate

Mark each line PASS with evidence, or FAIL with an issue number. **A line with no
evidence is a FAIL** — "should work" and "worked last time" are both failures.

### 0. The automation being demonstrated is the automation you fixed

This is first because it silently invalidates every other check.

- [ ] For each job template in scope, record **which project** it uses — not all
      templates in one workflow necessarily share one
- [ ] For each of those projects, record **`scm_branch` and `scm_revision`**
- [ ] Confirm every one is on the branch you expect and at the revision you expect

**Found 2026-08-24:** the patch-lifecycle demo ran from a second project pinned to a
feature branch that had been squash-merged months earlier. Its sync node succeeded
on every run — syncing the *stale branch* — so four merged fixes never reached the
demo, and a defect appeared "unfixed" after its fix was verified on main. Nodes in a
single workflow were observably running two different revisions.

**A green sync proves the project fetched. It does not prove the project points
anywhere useful.** Check the revision against `git rev-parse origin/main`.

### 1. Workflows actually complete

- [ ] Every workflow in scope runs **start to finish**, node count recorded
- [ ] The count is the **expected** count — a workflow that reports `successful`
      while skipping nodes is a FAIL (a failed node on an `always` edge can leave
      the overall status green)
- [ ] Job ids recorded for each

Evidence format: `workflow <id>: N/M nodes, status`

### 2. Every number that will be spoken is re-derived from live data

- [ ] Host counts, finding counts, coverage percentages, scores
- [ ] Re-derived **today**, from the database, not read from a runbook
- [ ] Identity sanity: does the host count contain container ids, `ip-*` names, or
      `localhost`? Quote **real** hosts

Evidence format: the query and its output.

### 3. Every externally-quoted regulatory or vendor claim is re-checked at source

- [ ] Effective dates against the standards register — **not** against our own docs
- [ ] Certification claims: does that certification regime exist at all
- [ ] Vendor capability claims against current vendor documentation, with the date

### 4. Every "built" claim is exercised once

- [ ] For each capability that will be *stated* as built, run it and keep the output
- [ ] Anything not exercised is described as **roadmap** in the engagement, not as
      built. Not "mostly working". Roadmap.

### 5. Environment prerequisites, not just code

- [ ] Images that demos depend on exist **in the registry they are pulled from**
- [ ] Credentials work from the path that will actually use them — an AAP credential
      working does not mean a vault file or an EDA activation works
- [ ] Addresses that change on restart (public IPs) are current in every place they
      are baked in
- [ ] Event-driven pieces are watched **idle** for 10 minutes: a watcher that fires
      when nothing is wrong is a FAIL

### 6. The demo is walked as a presenter, not as an engineer

- [ ] The scripted flow, in order, at demo pace
- [ ] Timing claims measured with a clock
- [ ] Every screen the customer will see is opened — including dashboards
- [ ] The reset-and-repeat cycle works, because the second call needs it

### 7. Clean-up is verified

- [ ] Billable infrastructure stopped, and **confirmed** stopped
- [ ] No stranded state: no open tickets, no drained hosts, no half-applied changes

---

## Recording a run

Append to `docs/operations/verification-runs/` as `YYYY-MM-DD-<engagement>.md`:

```
Date:        2026-08-24
Engagement:  <what this was for>
Verifier:    <name — NOT the author>
Scope:       <what was checked>

Section 1  PASS  workflow 3090: 14/14, successful
Section 2  FAIL  #NNN — host count includes container ids
...

Defects raised: #NNN, #NNN
Verdict: GO / NO-GO
```

**A NO-GO is a success of this process, not a failure of it.** Finding it here costs
an afternoon; finding it in front of a registered entity costs the account.

---

## What this is not

Not a substitute for CI, code review, or the pre-commit hooks — those catch different
things, and they work. Two of the week's defects *were* caught automatically, by the
sensitive-data hook and by an automated security review.

This gate exists for the category **nothing automated can reach**: environments that
rot between demos, images that were never built, addresses that changed, watchers
that are too noisy, and claims that were true when written.
