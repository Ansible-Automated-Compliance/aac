# Findings Workbook — Column Contract

**Version:** v1.0
**Date:** 2026-10-13
**Authors:** Tim Coulter (Red Hat); Claude (Anthropic) via Claude Code

This is the published contract for the AAC findings workbook produced by
`scripts/findings_workbook.py` (job template **"AAC - Compliance Findings
Workbook"**). The workbook is the same for every framework: CIS Microsoft 365,
CIS RHEL 9, Windows Server, STIG, NERC CIP and the rest all produce these
sheets with these columns. Anything you build on top of it (spreadsheet
formulas, GRC imports, macros) can rely on the column names and order below.
A change to a column is a change to the contract version.

## How to read it

Three things are kept separate on purpose, and the workbook is the join of
the first two:

| Thing | Where it lives | Edited by |
|---|---|---|
| **Evidence** | `compliance_results` (append-only, hash-chained) | nobody — assessments only add rows |
| **Decisions** | `ansible/vars/decisions/<framework>.yml` — owner, decision, justification, approver, expiry | the customer, under review |
| **Report** | this workbook, regenerated from the two above after every run | nobody — it is never hand-edited |

So an owner or an approval recorded in the decisions file survives the next
run and shows up in the next workbook automatically. If a report is edited by
hand, the edits are lost on the next run — that is by design.

**Finding identity.** Every finding has a stable key, `Finding ID`, derived
from (framework, control, subject). It is the same across runs, so a VLOOKUP
on it joins last month's sheet to this month's, and a decision in the
decisions file can name it.

**What "unassessable" means.** A control the run could not confirm as a pass
or a fail. It is never counted as a failure, and the `Reason` column says
whose work it is:

| Reason | Meaning | Who acts |
|---|---|---|
| `benchmark_manual` | the benchmark itself classifies the control as Manual | customer — manual review |
| `attestation_required` | the control needs a human attestation and none is recorded | customer — record the attestation |
| `collector_not_built` | AAC has no collector path for it yet | vendor — backlog, count trends down |
| `facts_not_collected` | the collector ran but the platform did not return the fact | vendor — investigate the run |
| `not_evaluated` | no policy evaluates the control yet, or no stored run touched it | vendor |

**Delta.** `new` appeared this run and was not in the previous run;
`regressed` appeared this run after having been fixed earlier in the window;
`fixed` was open in the previous run and is gone now (verified by the rescan,
never by absence of data); `still open` was in both. A subject's first run in
the window has no delta.

**Decisions and renewal.** `accept` keeps a deviation with a business
justification and must carry an expiry; when the expiry is missing it is
defaulted to the approval date plus the review cycle (90 days unless the file
says otherwise) and flagged in `Issues`. Decisions expiring within 30 days
show `expiring`; past expiry they show `expired` and the finding is treated
as open again. The approver must be a named person, not a team alias.
Accepted decisions can be exported as OPA waiver entries
(`--emit-waivers`) so they are honoured at evidence time as well.

**Sampled.** `yes` when the policy recorded that the evidence came from a
sample of the population rather than the whole of it. A sampled pass is
indicative, not proof for every object, and an auditor will ask.

## Sheets and columns

Contract version 1.0

## Summary

| Column | Meaning |
|---|---|
| Item | Summary item name |
| Value | Its value for this run |

## Findings

| Column | Key | Meaning |
|---|---|---|
| Finding ID | `finding_id` | Stable short key for the (framework, control, subject) identity. Survives re-runs; join on it. |
| Identity | `identity` | framework|control|subject — the identity the findings layer uses. |
| Framework | `framework` | Framework key as stored in the evidence. |
| Control | `control_id` | Control number with any framework prefix removed (e.g. 6.5.1). |
| Control (as emitted) | `control_raw` | Control id exactly as the policy emitted it. |
| Title | `title` | Catalog title when the catalog has one; otherwise the leading clause of the finding. |
| Section | `section` | Section/category number from the catalog or the stored row. |
| Category | `category` | Section/category name (e.g. Exchange admin center). |
| Profile level | `level` | Benchmark profile level (L1/L2) from the catalog, when known. |
| Benchmark assessment | `assessment` | Automated or Manual, as the benchmark classifies the control. |
| Subject | `subject` | The system or tenant the finding is on. |
| Status | `status` | open or waived (a waived finding is still listed). |
| Risk | `risk_band` | Derived risk band: Critical / High / Medium / Low. |
| Risk score | `risk_score` | Numeric score behind the band. |
| Risk basis | `risk_basis` | The factors that produced the score — the score is explainable. |
| Risk override | `risk_override` | Customer override from the decisions file, when set. |
| Effective risk | `effective_risk` | Override when present, otherwise the derived band. Sort on this. |
| Blast radius | `blast_radius` | Number of subjects failing this control in the latest runs. |
| Sampled | `sampled` | yes when the evidence was taken from a sample, not the full population. |
| Evidence strength | `evidence_strength` | The policy's own note on how strong the evidence is. |
| Where to fix | `where` | Admin surface where the control is set. |
| Action | `action` | What to change. |
| Method | `method` | manual / automated / governed. |
| Owner | `owner` | From the decisions file: per-finding decision, else default owner by section. |
| Decision | `decision` | remediate / accept / review, from the decisions file; blank = undecided. |
| Justification | `justification` | Business justification recorded with an accept decision. |
| Approver | `approver` | Named person who approved the decision. |
| Expires | `expires` | Expiry of an accepted deviation (renewal date). |
| Decision status | `decision_status` | active / expiring / expired / undecided. |
| Ticket | `ticket` | Change or tracking reference from the decisions file. |
| Delta | `delta` | new / still open / regressed / first run, relative to the previous run. |
| First seen | `first_seen` | First run in the window that reported this finding. |
| Last seen | `last_seen` | Latest run that reported it. |
| Times seen | `times_seen` | Runs in the window that reported it. |
| Age (days) | `age_days` | Days since first seen. |
| Detail | `detail` | The finding text exactly as the policy emitted it. |
| Evidence row | `evidence_id` | compliance_results.id of the row this finding came from. |
| Evidence timestamp | `evidence_at` | evaluation_timestamp of that row. |
| Policy SHA | `policy_sha` | Policy library commit that produced the row, when recorded. |

## Unassessable

| Column | Key | Meaning |
|---|---|---|
| Control | `control_id` | Control number. |
| Title | `title` | Catalog title, when known. |
| Section | `section` | Section number. |
| Category | `category` | Section name. |
| Profile level | `level` | L1/L2 when known. |
| Benchmark assessment | `assessment` | Automated or Manual per the benchmark. |
| Subject | `subject` | System or tenant, or * when the gap is benchmark-wide. |
| Reason | `reason` | benchmark_manual / attestation_required / collector_not_built / facts_not_collected / not_evaluated. |
| Who acts | `who_acts` | customer (manual review / attestation) or vendor (collector backlog). |
| Owner | `owner` | Default owner by section from the decisions file. |
| Detail | `detail` | The gap text as emitted, or the coverage note. |
| Evidence row | `evidence_id` | compliance_results.id when the gap came from a stored row. |

## Decisions

| Column | Key | Meaning |
|---|---|---|
| Control | `control_id` | Control the decision applies to. |
| Subject | `subject` | Subject the decision applies to, or *. |
| Decision | `decision` | remediate / accept / review. |
| Owner | `owner` | Business owner. |
| Justification | `justification` | Why the deviation is kept (accept) or the plan (remediate). |
| Approver | `approver` | Named person. |
| Approved | `approved` | Date approved. |
| Expires | `expires` | Renewal date for an accepted deviation. |
| Status | `status` | active / expiring / expired / unmatched (no open finding). |
| Days to expiry | `days_to_expiry` | Negative when expired. |
| Matched findings | `matched_findings` | Open findings this decision applies to. |
| Issues | `issues` | Validation notes: missing expiry (defaulted), approver not a person, unknown band. |
| Ticket | `ticket` | Change reference. |

## Delta

| Column | Key | Meaning |
|---|---|---|
| Change | `change` | new / fixed / regressed / still open. |
| Finding ID | `finding_id` | Stable key. |
| Control | `control_id` | Control number. |
| Title | `title` | Catalog title when known. |
| Subject | `subject` | System or tenant. |
| Effective risk | `effective_risk` | Band for open items; blank for fixed. |
| First seen | `first_seen` | First run in the window. |
| Previous run | `previous_run` | Timestamp of the run compared against. |
| Latest run | `latest_run` | Timestamp of the latest run. |

## Passed

| Column | Key | Meaning |
|---|---|---|
| Control | `control_id` | Control number. |
| Title | `title` | Catalog title when known. |
| Section | `section` | Section number. |
| Category | `category` | Section name. |
| Subject | `subject` | System or tenant. |
| Sampled | `sampled` | yes when the pass rests on a sample. |
| Evidence strength | `evidence_strength` | The policy's note on the evidence, when any. |
| Evidence row | `evidence_id` | compliance_results.id. |

## Files produced

| File | Content |
|---|---|
| `<name>.xlsx` | all six sheets, header row frozen, filters on |
| `<name>-<sheet>.csv` | one CSV per sheet, same columns, for tools that cannot read xlsx |
| `<name>.html` | one-page readable report with the same sections |
| `<name>.md` | the same in Markdown |
| `<name>.json` | the full structured report (summary + every sheet) |

The CSV and xlsx carry identical columns; the HTML and Markdown show a
reduced set of Findings columns for readability and the full set is always
in the xlsx/CSV/JSON.

## Revision history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-10-13 | Initial contract: six sheets, decisions join, delta, unassessable by cause |
