# AAC CIS Benchmark Results — Reading and Comparison Guide

**Version:** v1.0
**Date:** 2026-09-28
**Applies to:** any CIS benchmark assessed by AAC (worked examples use CIS Microsoft 365 Foundations v7.0.0)
**Audience:** the team operating an AAC POC environment and the team comparing AAC's results against a manual assessment
**Authored with Claude (Anthropic)** — AI-authorship transparency

---

## 1. What this guide covers

After an AAC assessment run, three questions come up in order:

1. **What specifically failed?** — the per-control violation detail behind the summary numbers (§3).
2. **What exactly did AAC assess?** — a flat per-control verdict export your team can line up against its own worksheet (§4).
3. **Where do AAC and our manual assessment agree and differ?** — the concordance report (§5).

All three run entirely inside your environment. AAC reads its own
`compliance_results` evidence store; nothing leaves your tenant or your
database.

One prerequisite matters before trusting summary numbers, covered in §2.

## 2. Before you start: verify the failed-count fix is in your checkout

Assessments run before 2026-09-24 stored their violation detail correctly
but derived **failed-control counts of zero** (a defect in the persistence
step, fixed in compliance PR #692). The quick tell:

- **Fix present:** the summary shows non-zero failed counts consistent with
  the violation list.
- **Fix absent:** the report says 0 failed / 100% while listing violations.

If your checkout predates the fix, update the AAP project from the
repository and re-sync before the next assessment. Historical rows can be
repaired in place — see §6.

## 3. Drilling into specific failures: the violations report

Run the job template **"AAC - M365 CIS Violations Report"** (playbook
`ansible/playbooks/m365_cis_violations_report.yml`). It renders, from the
latest stored result per section for one tenant:

- every violation message exactly as the policy engine stored it — control
  ID, what the control requires, and the specific detail observed
- **evidence gaps** — lines beginning `FAIL-CLOSED` mean no facts were
  collected for that area. That is a gap, not an assessed control failure,
  and the report renders it distinctly.
- **waivers** — waived findings are listed separately, never hidden.

Key variables: `report_tenant` (defaults to the tenant with the newest
row), `report_lookback` (days, default 30), and the `report_publish_*`
variables to copy outputs somewhere persistent (execution-environment
`/tmp` vanishes when the job ends).

## 4. Exporting AAC's per-control verdicts

Run the job template **"AAC - CIS Benchmark Comparison"** (playbook
`ansible/playbooks/cis_benchmark_comparison.yml`) **with no manual input**.
It writes `aac_control_verdicts-<framework>-<date>.csv`: one row per
benchmark control with AAC's verdict and the reason. This is the artifact
to hand a team doing a side-by-side review in a spreadsheet.

### Verdict glossary

| Verdict | Meaning |
|---|---|
| `pass` | Evaluated; no stored violation names this control |
| `fail` | An assessed failure is stored in the evidence store |
| `attested` | No automated read path exists; an admissible operator attestation is on record. A human assertion, deliberately kept distinct from a measured `pass` |
| `not_assessed` | The stored result itself says this is not a pass/fail — an evidence gap, a missing attestation, or no stored row for the control's section in the window. Never silently counted as pass **or** fail |
| `not_covered` | AAC currently has no automated or attestation path for this control — a declared scope boundary |

The coverage boundary is declared up front in every report. For CIS M365
v7.0.0 it is: **144** of 160 controls evaluated automatically, **6** taken
by recorded operator attestation, **10** currently without a path. A
control your manual assessment answered that AAC did not is a scope
statement, not an AAC miss — and the report classes it that way rather
than hiding it.

## 5. Comparing against a manual assessment

### 5.1 What the comparison needs from the manual artifact

A CSV with one row per control:

- a **control ID column** using the benchmark's numbering (`5.1.2.1`)
- a **result column** (pass/fail wording is configurable)
- optionally a **notes column**, carried into the concordance output

Column headers are matched case-insensitively and are configurable —
supply your artifact's actual headers via variables rather than reshaping
the artifact:

| Variable | Default | Purpose |
|---|---|---|
| `comparison_manual_col_control` | `control_id` | control-ID column header |
| `comparison_manual_col_result` | `result` | result column header |
| `comparison_manual_col_notes` | `notes` | notes column header (optional) |
| `comparison_pass_values` / `comparison_fail_values` | common wordings (pass/compliant/met/…, fail/non-compliant/open/…) | which result strings count as pass / fail; anything else is reported as `other`, not guessed |

**Version alignment:** confirm which benchmark version the manual
assessment used *before* comparing. If its numbering predates the assessed
version, supply a crosswalk CSV (columns `their_id,benchmark_id`) via
`comparison_crosswalk_csv` — otherwise controls that moved will appear as
spurious mismatches. IDs that match nothing in the benchmark catalog are
flagged `not_in_benchmark` so a numbering mismatch is visible, not silent.

### 5.2 Running it

Launch **"AAC - CIS Benchmark Comparison"** and supply the manual artifact
either as a file path readable by the job (`comparison_manual_csv`) or by
pasting the CSV content into the survey
(`comparison_manual_csv_content` — takes precedence). Outputs:

- `benchmark_comparison-<framework>-<date>.md` / `.html` — the concordance
  report
- `benchmark_concordance-<framework>-<date>.csv` — the full per-control
  join, one row per control
- `aac_control_verdicts-<framework>-<date>.csv` — AAC's side alone (§4)

### 5.3 Reading the concordance

Every control lands in exactly one agreement class:

| Class | Meaning |
|---|---|
| `agree_pass` / `agree_fail` | Both assessed it; same answer |
| `aac_fail_manual_pass` | AAC found a stored failure the manual review passed — review the stored violation detail together; one of the two is wrong, and the violation message says precisely what AAC observed |
| `aac_pass_manual_fail` | The manual review failed it; AAC saw no violation — check whether the manual finding is about an aspect AAC's check does not read, or whether the configuration changed between the two assessments |
| `manual_only` | The manual assessment answered it; AAC did not assess it (scope boundary or evidence gap — the `aac_detail` column says which) |
| `aac_only` | AAC assessed it; the manual artifact does not mention it |
| `neither` | Nobody assessed it |

The headline number is **agreement over the controls both assessed** — the
report states it with the denominator. Where the two differ, the
concordance CSV carries AAC's stored detail and the manual notes side by
side, which is the working document for the joint review session.

## 6. Repairing historical summary counts (pre-fix rows)

`scripts/sql/backfill_m365_derived_counts.sql` recomputes the derived
counts for rows stored before the #692 fix, from the correctly-stored
violations, using the same regex and arithmetic as the fixed code. It
touches only rows with the bug signature (failed = 0 while violations are
present), is idempotent, and is structured as **preview → transactional
update → verify**: run the preview SELECT first, compare its row count
with the UPDATE's, and only then commit. Violation detail is never
modified — only the derived counts and the `failed_control_ids` metadata.

## 7. Repeating the process for the next benchmark

The comparison pipeline is benchmark-agnostic. Onboarding the next CIS
benchmark to this same process requires:

1. **A coverage file**, generated from the policy library — declares
   evaluated / attestation / no-path per control:
   `python3 scripts/generate_benchmark_coverage.py <framework_key>`
   (committed as `ansible/vars/comparison/<framework_key>_coverage.yml`;
   re-run with `--check` in review to catch drift when the policy library
   advances)
2. **The same job template**, launched with
   `comparison_framework=<framework_key>`
3. **The manual artifact + column mapping** from the assessing team, as in
   §5.1

Nothing else changes: same verdict glossary, same agreement classes, same
outputs.

## Appendix A — job template setup

**"AAC - CIS Benchmark Comparison"**

| Setting | Value |
|---|---|
| Project | the AAC compliance project |
| Playbook | `ansible/playbooks/cis_benchmark_comparison.yml` |
| Execution environment | AAC Compliance EE |
| Inventory / hosts | localhost (reads PostgreSQL only) |
| Credentials | Ansible Vault credential (DB password) |
| Survey (suggested) | `comparison_framework` (default `cis_m365_v7`), `comparison_tenant` (blank = newest), `comparison_manual_csv_content` (textarea, optional), `comparison_manual_col_control` / `_result` / `_notes` |

---

*Generated by AAC. Co-authored by Claude (Anthropic) via Claude Code.*
