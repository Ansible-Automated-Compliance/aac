# Per-Control Results: Passes as Well as Fails

**Version:** v1.0
**Authors:** Tim Coulter, Claude (Anthropic)

An assessment stores one summary row in `compliance_results`. An auditor also asks for the result of every control: which passed, which failed, and since when. This page describes where that is kept and how to read it.

## What is stored

| Object | Holds |
|---|---|
| `control_state` | One row per host, framework and control: the control's current status and when it last changed |
| `control_state_history` | One row each time a control's status changes for a host, including the first time it is seen. Append-only |
| `control_state_current` | View: the state rows with the version and time of the result they came from |
| `control_state_summary` | View: counts per status for each host and framework |

The state table is updated in place. It does not grow with every run: a host with 350 controls has 350 rows however often it is assessed. The history table grows only when something changes.

## Columns of `control_state`

| Column | Meaning |
|---|---|
| `hostname` | The assessed subject, as in `compliance_results` (for Microsoft 365, the tenant) |
| `framework` | Framework key, for example `cis_rhel9` |
| `control_id` | The recommendation number |
| `status` | See the statuses below |
| `basis` | How the status was reached: `evidence` (collected facts) or `attestation` (a manual review) |
| `profile` | The benchmark profiles the control belongs to |
| `in_scope` | Whether the control applies to the selected profile |
| `since` | When the status last changed |
| `last_seen` | When a run last reported the control |
| `last_result_id` | The `compliance_results` row that last reported it |

`control_state_history` holds `hostname`, `framework`, `control_id`, `from_status`, `to_status`, `changed_at` and `result_id` (the result that showed the change).

## Statuses

| Status | Meaning |
|---|---|
| `pass` | The collected facts, or an attestation, satisfy the control |
| `fail` | The collected facts do not satisfy the control |
| `evidence_missing` | The facts the control needs were not collected. Counted as failed |
| `not_attested` | A manual review that nobody has attested. Counted as failed |
| `not_applicable` | Outside the selected profile, or not relevant to this system |
| `not_reported` | The control was in an earlier run for this host and framework and is absent from the latest one |
| `invalid` | The report carried a status that is not a plain word |

A control that disappears from a report (a new benchmark version, a different profile, a changed policy module) is marked `not_reported` and the change is written to the history. It does not keep its last status. `last_seen` and `last_result_id` keep the time and result of its last report.

The statuses are the policy's own. A waiver does not change them: a waived finding is still `fail` here and is listed as waived in the summary row's `metadata.waivers_applied`.

## Which assessments record it

A policy module must return `control_results` in its report. At the pinned library these do:

| Assessment | Framework key stored |
|---|---|
| CIS RHEL 9 (`cis_rhel9_assessment.yml`) | `cis_rhel9` |
| CIS RHEL 8 (`cis_rhel8_assessment.yml`) | `cis_rhel8` |
| CIS Windows Server 2022 (`cis_windows_server_2022_assessment.yml`) | `cis_windows_2022` |
| CIS Microsoft 365 v7 (`aac.m365` role) | the role's framework name |
| Evaluate Stored Facts (`evaluate_stored_facts.yml`) | the policy key, for each policy whose report carries the list |

For any other assessment nothing is written and nothing fails.

## How it is written

`aac_store_results` takes the list as `aac_result_control_results` and, after the summary row is stored, calls the database function `control_state_record(result_id, hostname, framework, controls)` once. The function is the only write path. It runs with its owner's rights, so the least-privilege evidence writer needs only permission to execute it and holds no update right on any table.

The function refuses a result id that is not a stored result of that framework, ignores a run older than the state it would overwrite, and writes nothing for an empty list.

## Installing

New install: the database role (`aac_compliance_db`) creates the tables. Existing install: re-run that role, or apply `ansible/files/control_state_schema.sql`. Every statement is safe to repeat. Until the tables exist, assessments store the summary row as before and say that the per-control results were not recorded.

## Example queries

Every control for one host, passes included:

```sql
SELECT control_id, status, basis, since, last_seen
FROM control_state_current
WHERE hostname = 'web01.example.com' AND framework = 'cis_rhel9' AND in_scope
ORDER BY string_to_array(control_id, '.')::int[];
```

Counts per status for every host of a framework:

```sql
SELECT hostname, controls, pass, fail, evidence_missing, not_attested, not_reported
FROM control_state_summary
WHERE framework = 'cis_rhel9'
ORDER BY hostname;
```

What changed in the last 30 days, for example controls that went from pass to fail:

```sql
SELECT changed_at, hostname, control_id, from_status, to_status, result_id
FROM control_state_history
WHERE framework = 'cis_rhel9' AND changed_at > now() - interval '30 days'
  AND from_status = 'pass' AND to_status <> 'pass'
ORDER BY changed_at DESC;
```

## Limits

- History rows are never removed by the product. Removing old ones needs a stated reason in the session (`SET aac.evidence_maintenance_note = '...'`), as for the other evidence tables.
- The signed audit artifact covers the summary result. It does not yet sign the per-control list.
- Reports and dashboards do not read these tables yet.
