# aac_findings_sync

Derives **first-class findings** from stored `compliance_results` evidence.
A stored violation is a message inside an assessment row — re-emitted every
run, no identity, no state. A finding has identity —
**(framework, control_id, subject)** — which is what makes every action
question answerable with **targets instead of percentages**:

```sql
-- Blast radius: which systems fail this control / carry this hole?
SELECT * FROM findings_blast_radius WHERE control_id = 'CIS 1.1.1';
SELECT * FROM findings_ref_radius   WHERE ref_value = 'CCE-90638-3';

-- Target list: what does this system need fixed, oldest first?
SELECT * FROM findings_system_targets WHERE subject = 'host01';
```

## What it does

1. Reads the **latest** assessment row per (subject, framework) inside the
   lookback window.
2. Normalizes violations through the tested extractor
   (`scripts/findings_extract.py` — control-id parsing for every message
   family the library emits; `FAIL-CLOSED` sentinels become
   `finding_type = evidence_gap`, a different actionable than a control
   failure; structured OpenSCAP-shape dicts keep their CCE/CCI/800-53 refs).
3. Upserts into `compliance_findings`: new issues open, recurring issues
   accumulate `times_seen`, previously-resolved issues that reappear
   **reopen** (regression), waivers from `metadata.waivers_applied` show as
   `waived` — visible, never hidden.
4. Resolves open findings **only** when a newer scan of the same
   (subject, framework) no longer reports them — **verified by rescan**;
   absence of data never closes anything.

Rows are never deleted; state transitions only. Evidence rows are never
modified. The schema (`files/schema.sql`) is applied idempotently each run.

## Variables

| Variable | Criticality | Default | How to supply |
|---|---|---|---|
| `findings_lookback_days` | MEDIUM | `90` | extra_vars — window of assessments considered |
| `findings_framework` | MEDIUM | `""` (all) | extra_vars — restrict to one framework key |
| `findings_python` | LOW | `python3` | extra_vars |
| `pg_host` etc. | **CRITICAL** | from `site_config.yml` | site config or extra_vars; `pg_host` is mandatory, no fallback |

## Finding lifecycle

`open` → (`waived` while a documented waiver applies) → `resolved`
(newer scan shows the control passing) → back to `open` if it regresses.
`evidence_gap` findings follow the same lifecycle — closing one means the
facts are now being collected, not that the control passes.

## Run context

`hosts: localhost, connection: local` in the EE — PostgreSQL only.
AAP JT: **"AAC - Sync Compliance Findings"**. Run after assessments or on a
schedule.
