# Compliance Reporting Guide

**Authors:** Tim Coulter & Claude
**Version:** v2.0
**Date:** 2026-11-24

This guide is for people who have AAC installed on their own Ansible Automation
Platform and want reports out of it. It covers what data must be in place first,
which report answers which question, how to run each one, and what to do when a
report fails.

Every report in this guide reads stored results. None of them evaluates policy,
and none of them connects to a managed host. If the data was not gathered, no
report can supply it.

Sample outputs, produced by the repository's own report code from synthetic
data, are in [`examples/reports/`](../../examples/reports/README.md).

## 1. Get the right data gathered

### 1.1 The data path

| Step | What runs | What it writes |
|---|---|---|
| 1. Assess | An assessment job for the framework, for example `ansible/playbooks/cis_rhel9_assessment.yml`, `ansible/playbooks/cis_windows_server_2022_assessment.yml` or `collections/ansible_collections/aac/m365/playbooks/cis_m365_v7_assessment.yml` | One or more rows in `compliance_results` per subject and run |
| 2. Sync findings | `ansible/playbooks/sync_compliance_findings.yml` (job template "AAC - Sync Compliance Findings") | `compliance_findings` and the views `findings_blast_radius`, `findings_system_targets`, `findings_ref_radius` |
| 3. Report | A report job from section 2 | Files in the execution environment, optionally copied to a host you name |

A subject is whatever was assessed: a hostname for an operating system
benchmark, a tenant for Microsoft 365. It is stored in the `hostname` column.

The assessment job template names depend on how you installed. The extended
installer for an existing AAP
(`install/existing-aap/extended/playbooks/automation_execution/templates/`)
creates `AAC_CIS_RHEL9_Assessment`, `AAC_CIS_Windows_Server_2022_Assessment`
and `AAC_CIS_M365v7_Assessment`.

Step 2 is needed only for the three reports that read `compliance_findings`
(risk scoring, mitigation guidance, closure). The findings workbook, the M365
reports and the summary report read `compliance_results` directly.

### 1.2 Where results are stored

All tables are in the PostgreSQL database that `pg_host` points at (database
name `compliance` by default).

**`compliance_results`** is the evidence store. It is created by the
`aac_compliance_db` role (`ansible/roles/aac_compliance_db/tasks/schema.yml`)
and written by the `aac_store_results` role and the M365 assessment role.
Assessments only add rows.

| Column | What a report uses it for |
|---|---|
| `id` | The evidence row a finding points back to |
| `hostname` | The subject. Rows with an empty `hostname` are skipped by the workbook and by the findings sync |
| `framework` | The framework key, for example `cis_rhel9`, `cis_m365_v7`. This is the value you type into a report survey |
| `policy_name` | Section or policy within the framework. M365 stores one row per section (`cis_m365_v7.<section>`) |
| `policy_version` | Benchmark version shown in report headers |
| `total_controls`, `passed_controls`, `failed_controls`, `compliance_percentage`, `compliant` | Counts and percentages in the summary and M365 reports |
| `violations` | JSON list of failures. Each entry is a message such as `CIS 5.1.2.2: ...` or a structured object. Every finding in every report comes from here |
| `metadata` | JSON. Reports read `waivers_applied`, `controls_evaluated`, `evaluated_control_ids`, `evidence_strength`, `risk_level`, `waived_count` and `platform` when present |
| `evaluation_timestamp` | The run time. Every report window is measured against it |

**`compliance_findings`** is derived from `compliance_results` by the findings
sync (`ansible/roles/aac_findings_sync/files/schema.sql`). One row per
(`framework`, `control_id`, `subject`, `finding_type`).

| Column | Meaning |
|---|---|
| `framework`, `control_id`, `subject` | The identity of the finding |
| `finding_type` | `violation` or `evidence_gap` |
| `severity`, `title`, `refs` | From the stored violation. `severity` is empty for message-based frameworks |
| `status` | `open`, `waived` or `resolved` |
| `first_seen`, `last_seen`, `resolved_at`, `times_seen` | History across runs |
| `last_result_id` | The newest `compliance_results.id` that reported it |

A finding is marked `resolved` only when a newer assessment of the same subject
and framework no longer reports it. A subject that stops being assessed keeps
its open findings.

### 1.3 How fresh the data must be

Each report reads a window that ends now. Rows older than the window are not
read. If the newest assessment is older than the window, the report fails
instead of printing an empty page.

| Report | Window variable | Default | What it reads inside the window |
|---|---|---|---|
| Findings workbook | `report_lookback` | 90 days | Every row for the framework. The delta compares the two newest runs per subject. Rows on one subject less than 30 minutes apart count as one run (`report_run_gap_minutes`) |
| Sync findings | `findings_lookback_days` | 90 days | The latest row per subject and framework |
| Risk scoring, mitigation guidance | none | n/a | Every `open` row in `compliance_findings` for the framework, whatever its age |
| Closure report | `closure_lookback` | 180 days | Findings of every status with `last_seen` inside the window |
| M365 findings, M365 violations | `report_lookback` | 30 days | The latest row per section for one tenant |
| Summary report | `lookback_days` | 30 days | The latest row per subject and framework |

Consequences worth knowing before you read a report:

- A delta needs two runs of the same subject inside the window. With one run,
  the Delta column reads `first run`.
- Risk scoring and mitigation guidance have no window. They are as current as
  the last findings sync. Run the sync after each assessment, or on a schedule.
- The M365 reports cover one tenant. If no tenant is given, the tenant with the
  newest row is used. Tenants are never mixed in one report.
- The summary report shows the latest result per subject and framework. A
  Grafana panel that counts every row in the same window shows a larger number.
  That number is assessments run, not systems assessed.

### 1.4 What "unassessable" and "evidence gap" mean

A control that the run could not confirm as a pass or a fail is reported
separately. It is never counted as a failure and never counted as a pass.

| Where you see it | What it is |
|---|---|
| Workbook, Unassessable sheet | One row per control that could not be confirmed, with a `Reason` and a `Who acts` column. The reasons are defined in the [column contract](FINDINGS_WORKBOOK_CONTRACT.md) |
| `compliance_findings.finding_type = 'evidence_gap'` | A stored message that starts with `FAIL-CLOSED`: an area where no facts were supplied to the policy |
| Risk scoring | Band `Unable to assess`, no score, listed after the scored findings |
| Mitigation guidance | The action is to fix fact collection, not to change a control |
| M365 findings report | Section "Evidence gaps". Messages that contain `(this is not a pass)` land here |

If a report shows many evidence gaps, the collection step is where to look.
A waived finding is different: the control failed, a recorded waiver applies,
and the finding stays visible with status `waived`.

The Passed sheet of the workbook lists controls only when the stored row
records which controls were evaluated (`metadata.evaluated_control_ids`). In
this repository the M365 assessment records it. For other frameworks the
passed count is in `passed_controls` and the Passed sheet is empty.

### 1.5 Check the data before you run a report

Run this against the compliance database. It shows, per framework, how many
subjects have rows in the last 90 days, how new the newest row is, and how many
rows have no subject.

```sql
SELECT framework,
       COUNT(DISTINCT hostname)                               AS subjects,
       COUNT(*)                                               AS result_rows,
       MAX(evaluation_timestamp)                              AS newest,
       COUNT(*) FILTER (WHERE hostname IS NULL OR hostname = '') AS rows_without_subject
FROM compliance_results
WHERE evaluation_timestamp >= NOW() - INTERVAL '90 days'
GROUP BY framework
ORDER BY framework;
```

Read the result like this:

| You see | It means |
|---|---|
| No row for your framework | No assessment stored a result under that key in 90 days. Check the key and run the assessment |
| `newest` older than the report window | The report will fail on an empty window. Run the assessment, or widen the window |
| `rows_without_subject` above zero | Those rows are invisible to the workbook and to the findings sync |
| `subjects` lower than the number of systems you expect | Some systems were not assessed |

For the three reports that read the findings layer, also check that the sync
has run:

```sql
SELECT framework, status, finding_type, COUNT(*) AS findings, MAX(last_seen) AS newest
FROM compliance_findings
GROUP BY framework, status, finding_type
ORDER BY framework, status;
```

If the table does not exist, the sync has never run.

With the single-host container install
(`install/existing-aap/extended/quadlets/aac-postgresql.container`) the
database runs in a container named `aac-postgresql`, with user and database
`compliance`:

```bash
podman exec -it aac-postgresql psql -U compliance -d compliance
```

To make staleness fail a job instead of relying on someone looking,
`ansible/playbooks/aac_assert_fresh_results.yml` checks each framework you
declare against a maximum age and fails when one is stale or has no rows.

| Variable | Default | Meaning |
|---|---|---|
| `aac_freshness_frameworks` | none, required | List of framework keys, or mappings with `framework`, optional `max_age_hours` and optional `hosts` |
| `aac_freshness_max_age_hours` | `26` | Age limit when an entry does not set its own |
| `aac_freshness_fact_hosts` | none | Hostnames that must have a fresh row in `host_facts` |

No seed playbook registers a job template for it. Create one that points at the
playbook, or run it from the command line (section 3.4).

## 2. Which report answers which question

These seven job templates are registered by
`ansible/playbooks/seed_report_templates.yml`.

| Report | Question it answers | Input | Outputs | Job template | Playbook |
|---|---|---|---|---|---|
| Findings workbook | What is open, who owns it, how risky is it, where is it fixed, what changed since the last run, what could not be assessed? | `compliance_results`, plus the decisions, risk and mitigation files for the framework | `.xlsx` with six sheets, one CSV per sheet, HTML, Markdown, JSON | AAC - Compliance Findings Workbook | `ansible/playbooks/compliance_findings_workbook.yml` |
| Sync findings | Not a report. Builds the findings layer the next three read | `compliance_results` | Rows in `compliance_findings` | AAC - Sync Compliance Findings | `ansible/playbooks/sync_compliance_findings.yml` |
| Risk scoring | Which open findings come first, and why? | `compliance_findings`, `findings_blast_radius` | JSON, CSV | AAC - Compliance Risk Scoring | `ansible/playbooks/compliance_risk_scoring.yml` |
| Mitigation guidance | For each open finding: where is it fixed, what is the action, is it manual or automated? | `compliance_findings` | JSON, CSV | AAC - Compliance Mitigation Guidance | `ansible/playbooks/compliance_mitigation_guidance.yml` |
| Closure report | What was found, and is each item resolved by a rescan, waived, or still open? | `compliance_findings` | JSON, CSV | AAC - Compliance Closure Report | `ansible/playbooks/compliance_closure_report.yml` |
| M365 findings report | For one tenant: findings ranked by risk, each with a remediation, plus a one-page summary for leadership | `compliance_results` (`cis_m365_v7`), the CIS M365 index from the policy library | Markdown, HTML, executive summary HTML, CSV | AAC - M365 CIS Findings Report | `ansible/playbooks/m365_cis_findings_report.yml` |
| M365 violations report | For one tenant: every violation message per section as the policy emitted it, with evidence gaps and applied waivers | `compliance_results` (`cis_m365_v7`) | HTML, Markdown | AAC - M365 CIS Violations Report | `ansible/playbooks/m365_cis_violations_report.yml` |

The workbook composes risk, mitigation, decisions and delta into one artifact.
If you run one report, run the workbook. Its sheets and columns are a published
contract: [FINDINGS_WORKBOOK_CONTRACT.md](FINDINGS_WORKBOOK_CONTRACT.md).

Other report playbooks in the tree that an outside installer can use:

| Playbook | What it produces | Needs |
|---|---|---|
| `ansible/playbooks/generate_compliance_report_from_db.yml` | Estate summary: one line per subject and framework with status, percentage, counts, waived count and risk level, then the findings per subject. HTML, CSV, Markdown | `compliance_results`. The extended installer registers it as `AAC_Compliance_Report` |
| `ansible/playbooks/remediation_report.yml` | Console report: remediation status per host and policy with owner, due date, overdue flag, top violations | The tables created by `ansible/playbooks/migrate_schema_v2.yml`, filled by `ansible/playbooks/evaluate_stored_facts.yml`. Job template "AAC - Remediation Report" is registered by `ansible/playbooks/seed_phase2_templates.yml` |
| `ansible/playbooks/opa_policy_report.yml` | Console summary and JSON file listing the policies loaded in the OPA instance at `opa_security_url`, grouped by framework prefix | A reachable OPA. No database |
| `ansible/playbooks/inventory_report.yml` | Console report of the inventory groups: what is assessed, what is AAC product, which API endpoints exist, which hosts are unclassified | An inventory. No database, no host access |

Report playbooks in the tree that this guide does not cover, and why:

| Playbook | Reason |
|---|---|
| `scripts/compliance_reporter.py` and the `make report*` targets | See section 6 |
| `ansible/playbooks/cis_benchmark_report.yml` | Renders built-in sample systems only. It refuses to run without `use_demo_data=true` and its figures never come from the evidence store |
| `ansible/playbooks/compliance_trending_report.yml` | See section 6 |
| `ansible/playbooks/drift_report.yml` | See section 6 |
| `ansible/playbooks/nerc_cip_compliance_report.yml` | An assessment, not a report: it evaluates a data file against OPA. The default data file is the sample in `examples/` |
| `ansible/playbooks/nerc_cip_pdf_report.yml`, `ansible/playbooks/nerc_ami_remediation_report.yml`, `ansible/playbooks/ds_pdf_report.yml` | Specific to the NERC CIP, AMI and Digital Sovereignty assessments. They read `compliance_results` rows that only those assessments write. Read the header of each playbook before use |

## 3. How to run each report

### 3.1 Register the job templates

`ansible/playbooks/seed_report_templates.yml` creates or updates the seven
templates by name and attaches a survey and the vault credential to each. It is
safe to re-run.

It needs these values:

| Variable | Source |
|---|---|
| `aap_url`, `aap_project_name`, `aap_inventory_name`, `aap_ee_name`, `aap_vault_credential_name` | `ansible/vars/site_config.yml` (copy from `ansible/vars/site_config.yml.example`) |
| `aap_token` | A controller API token. Keep it in a vault-encrypted variables file or an AAP credential. Do not pass it in clear text |

The project, inventory, execution environment and vault credential named in
`site_config.yml` must each exist on the controller exactly once.

```bash
ansible-playbook ansible/playbooks/seed_report_templates.yml \
  -e @path/to/vault-encrypted-vars.yml --ask-vault-pass
```

The extended installer for an existing AAP registers three report templates
under different names and without surveys: `AAC_CIS_M365v7_Findings_Report`,
`AAC_CIS_M365v7_Violations_Report` and `AAC_Compliance_Report`. They run the
same playbooks with the playbook defaults. To change a variable on those,
set it in the template's extra variables.

### 3.2 What every report job needs

| Need | Detail |
|---|---|
| Database host | `pg_host`. Required. No default |
| Database password | `compliance_db_password`, from `ansible/vars/vault_secrets.yml` or an AAP credential that injects it. The extended installer's `AAC Postgresql` credential injects both `pg_host` and `compliance_db_password` |
| Optional database settings | `pg_port` (default `5432`), `pg_user` (default `postgres`), `pg_database` (default `compliance`), `pg_ssl_mode` (default `prefer`) |
| Execution environment | One with the `community.postgresql` collection and `python3` |
| Inventory | Any. The plays run on `localhost` |

The seeded templates attach only the vault credential. If your database
settings come from a separate credential, attach it to each report template.

**Getting the files out.** Reports are written inside the execution
environment (`/tmp` by default). That filesystem is removed when the job ends.
Set `report_publish_host` to have the job copy the files with `scp`.

| Variable | Default | Meaning |
|---|---|---|
| `report_publish_host` | empty | Destination host. Empty means the files stay in the execution environment and the job prints a warning |
| `report_publish_user` | `aapuser1` | SSH user on that host |
| `report_publish_dir` | `/var/tmp` | Destination directory |

The copy uses `BatchMode`, so the job needs a machine credential whose key is
accepted by `report_publish_user` on that host. Only `report_publish_host` is
in the surveys. Set the user and directory in the template's extra variables.

### 3.3 Survey variables per job template

**AAC - Sync Compliance Findings**

| Variable | Default | Meaning |
|---|---|---|
| `findings_framework` | empty | One framework key. Empty means all frameworks |
| `findings_lookback_days` | `90` | Window of assessments to sync from |

**AAC - Compliance Findings Workbook**

| Variable | Default | Meaning |
|---|---|---|
| `report_framework` | `cis_m365_v7` | Framework key. Required |
| `report_subject` | empty | One hostname or tenant. Empty means every subject with rows in the window |
| `report_lookback` | `90` | Days of history |
| `report_publish_host` | empty | See 3.2 |

Not in the survey, settable as extra variables: `report_output_dir` (`/tmp`),
`report_basename` (`findings_workbook-<framework>-<date>`), `report_decisions`
(`ansible/vars/decisions/<framework>.yml`), `report_catalog`,
`report_coverage` (`ansible/vars/comparison/<framework>_coverage.yml`),
`report_benchmark_name`, `report_benchmark_version`, `report_run_gap_minutes`
(`30`), `report_expiring_days` (`30`).

The workbook joins three per-framework files when they exist:

| File | Purpose | When absent |
|---|---|---|
| `ansible/vars/decisions/<framework>.yml` | Owner, decision, justification, approver, expiry. Field reference: `ansible/vars/decisions/README.md`. Start from `examples/decisions_example.yml` | The Owner and Decision columns are blank |
| `ansible/vars/risk/<framework>.yml` | Control criticality and keyword elevators for the risk band | `ansible/vars/risk/_default.yml` is used |
| `ansible/vars/mitigation/<framework>.yml` | Where to fix, action, method | `ansible/vars/mitigation/_default.yml` is used, which gives generic text |

The tree ships framework-specific risk and mitigation files for `cis_m365_v7`
only. For other frameworks, the workbook runs with the defaults until you add
a file.

**AAC - Compliance Risk Scoring**

| Variable | Default | Meaning |
|---|---|---|
| `risk_framework` | `cis_m365_v7` | Framework key. Required |
| `report_publish_host` | empty | See 3.2 |

Output: `risk_scored_findings-<framework>-<date>.json` and `.csv` in
`risk_output_dir` (`/tmp`).

**AAC - Compliance Mitigation Guidance**

| Variable | Default | Meaning |
|---|---|---|
| `mit_framework` | `cis_m365_v7` | Framework key. Required |
| `report_publish_host` | empty | See 3.2 |

Output: `mitigation_guidance-<framework>-<date>.json` and `.csv` in
`mit_output_dir` (`/tmp`).

**AAC - Compliance Closure Report**

| Variable | Default | Meaning |
|---|---|---|
| `closure_framework` | `cis_m365_v7` | Framework key. Required |
| `closure_lookback` | `180` | Days of history. Bounds how far back resolved and waived findings are reported |
| `report_publish_host` | empty | See 3.2 |

Output: `closure_report-<framework>-<date>.json` and `.csv` in
`closure_output_dir` (`/tmp`).

**AAC - M365 CIS Findings Report** and **AAC - M365 CIS Violations Report**

| Variable | Default | Meaning |
|---|---|---|
| `report_tenant` | empty | Tenant as stored in `hostname`. Empty means the tenant with the newest row |
| `report_lookback` | `30` | Days of history |
| `report_publish_host` | empty | See 3.2 |

Findings report output, in `report_output_dir` (`/tmp`):
`m365_findings_report-cis_m365_v7-<date>.md` and `.html`,
`m365_executive_summary-cis_m365_v7-<date>.html`,
`m365_results_export-cis_m365_v7-<date>.csv`. It reads the CIS M365 index from
the policy library at
`policies/benchmarks/cis/saas/m365_v7/data/cis_m365_v7_index.json`, so the
project checkout must include the `policies` submodule.

Violations report output: `m365_cis_violations_report-<date>.html` and `.md`.

**Summary report** (`generate_compliance_report_from_db.yml`)

| Variable | Default | Meaning |
|---|---|---|
| `lookback_days` | `30` | Days of history |
| `report_framework` | empty | One framework key. Empty means all |
| `report_formats` | `html,csv,md` | Any subset |
| `output_dir` | `/tmp/compliance_reports` | Directory inside the execution environment |
| `report_persist_host` | `aac_host` when defined | Host to copy the files to, into `~/reports/` |
| `report_persist_user` | `aap_ssh_user`, else `aapuser1` | SSH user on that host |

CSV columns: `hostname`, `framework`, `status`, `compliance_percentage`,
`passed_controls`, `total_controls`, `failed_controls`, `waived_count`,
`risk_level`, `evaluation_timestamp`, `findings_count`, `findings`.

This playbook uses different publish variables from the seeded reports
(`report_persist_*`, not `report_publish_*`).

### 3.4 From the command line

The report playbooks run with `ansible-playbook` from the repository root on a
RHEL 9 host that can reach the database. You need `ansible-core`, the
`community.postgresql` collection, `psycopg2` (pinned in
`scripts/requirements.txt`), and the two local files
`ansible/vars/site_config.yml` and `ansible/vars/vault_secrets.yml`. Both are
loaded when present. `vault_secrets.yml` holds `compliance_db_password` and
should be encrypted with `ansible-vault`.

```bash
# Findings workbook for one framework, files kept in ./out
ansible-playbook ansible/playbooks/compliance_findings_workbook.yml \
  -e report_framework=cis_rhel9 -e report_output_dir="$PWD/out" --ask-vault-pass

# Findings layer, then the three reports that read it
ansible-playbook ansible/playbooks/sync_compliance_findings.yml \
  -e findings_framework=cis_rhel9 --ask-vault-pass
ansible-playbook ansible/playbooks/compliance_risk_scoring.yml \
  -e risk_framework=cis_rhel9 -e risk_output_dir="$PWD/out" --ask-vault-pass
ansible-playbook ansible/playbooks/compliance_mitigation_guidance.yml \
  -e mit_framework=cis_rhel9 -e mit_output_dir="$PWD/out" --ask-vault-pass
ansible-playbook ansible/playbooks/compliance_closure_report.yml \
  -e closure_framework=cis_rhel9 -e closure_output_dir="$PWD/out" --ask-vault-pass

# Summary across frameworks
ansible-playbook ansible/playbooks/generate_compliance_report_from_db.yml \
  -e lookback_days=30 -e output_dir="$PWD/out" --ask-vault-pass

# Fail when a framework is stale
ansible-playbook ansible/playbooks/aac_assert_fresh_results.yml \
  -e '{"aac_freshness_frameworks": ["cis_rhel9"]}' --ask-vault-pass
```

The output directory must be an absolute path made of letters, digits, `/`, `_`, `.` and `-`, without `..`. Create it first.
On the command line the files stay where you put them, so
`report_publish_host` is not needed.

The report logic itself is plain Python with no database access and no
third-party packages. Each script reads one JSON object on standard input:

| Script | Used by |
|---|---|
| `scripts/findings_workbook.py` | Findings workbook |
| `scripts/findings_extract.py` | Findings sync |
| `scripts/risk_score.py` | Risk scoring |
| `scripts/mitigation.py` | Mitigation guidance |
| `scripts/closure.py` | Closure report |
| `scripts/m365_findings_report.py` | M365 findings report |

That is how the examples in the next section were produced. The exact
commands are in [`examples/reports/README.md`](../../examples/reports/README.md).

## 4. Examples

All example outputs are in [`examples/reports/`](../../examples/reports/README.md).
They were generated by running the scripts above on synthetic input. No output
was written by hand. The inputs are in `examples/reports/inputs/`.

| Report | Example | Format |
|---|---|---|
| Findings workbook | [`findings-workbook/findings_workbook-cis_m365_v7.md`](../../examples/reports/findings-workbook/findings_workbook-cis_m365_v7.md) | Markdown. The same directory holds the `.xlsx`, the six CSVs, the HTML and the JSON |
| M365 findings report | [`m365-findings/m365_findings_report.md`](../../examples/reports/m365-findings/m365_findings_report.md) | Markdown. The same directory holds the HTML, the executive summary and the CSV export |
| Findings layer | [`findings-layer/findings_extract-cis_rhel9.json`](../../examples/reports/findings-layer/findings_extract-cis_rhel9.json) | JSON. What the sync derives from two stored rows |
| Risk scoring | [`findings-layer/risk_scored_findings-cis_rhel9.csv`](../../examples/reports/findings-layer/risk_scored_findings-cis_rhel9.csv) | CSV and JSON |
| Mitigation guidance | [`findings-layer/mitigation_guidance-cis_rhel9.csv`](../../examples/reports/findings-layer/mitigation_guidance-cis_rhel9.csv) | CSV and JSON |
| Closure report | [`findings-layer/closure_report-cis_rhel9.csv`](../../examples/reports/findings-layer/closure_report-cis_rhel9.csv) | CSV and JSON |

Two reports have no example because they are rendered by templates inside the
playbook from a live database query, and cannot be run offline:

| Report | What it contains |
|---|---|
| M365 violations report | A header with tenant, window and totals. Then one block per stored section (`policy_name`) with passed, failed and evaluated counts, the violation messages as emitted, evidence gaps listed apart from failures, and applied waivers |
| Summary report | The CSV columns listed in section 3.3. The HTML and Markdown carry the same rows as a table, followed by the findings per subject |

## 5. Troubleshooting

| What the job says | Cause | What to do |
|---|---|---|
| `No <framework> rows in compliance_results within the last N days` | Empty window. No assessment stored rows under that framework key in the window, or the key is misspelled | Run the query in section 1.5. Use the key exactly as it appears in the `framework` column. Run the assessment, or raise the lookback |
| `No <framework> rows ... for <subject>` (workbook) or `No <framework> rows for tenant <tenant> in the window` | The subject or tenant filter matches nothing | Compare the value with the `hostname` column. Leave the field blank to take every subject |
| `No open findings for framework <framework> in compliance_findings. Run the assessment and findings sync first` | The sync has not run for that framework, the key is wrong, or there are no open findings | Run "AAC - Sync Compliance Findings", then the second query in section 1.5. If the framework has only `resolved` and `waived` rows, there is nothing to score |
| `No <framework> findings in compliance_findings within the last N days` (closure) | No finding was seen inside `closure_lookback` | Run the sync. Raise `closure_lookback` |
| `relation "compliance_findings" does not exist` | The sync has never run. It creates the table | Run "AAC - Sync Compliance Findings" once |
| The sync job ends early with no error and no findings | No row in `compliance_results` inside `findings_lookback_days` | Run the assessment, or raise the window |
| A mandatory-variable error that names `pg_host` | No database host reached the job | Set `pg_host` in `site_config.yml`, or attach the credential that injects it |
| An undefined-variable error that names `compliance_db_password` | No database password reached the job | Attach the vault credential and make sure `vault_secrets.yml` is in the project, or attach a credential that injects `compliance_db_password` |
| Connection refused or timeout on the query task | The execution environment cannot reach PostgreSQL at `pg_host`:`pg_port` | Check the port. These reports default to `5432` |
| `report_framework is required and must be a safe key` | The framework field is empty or has characters outside letters, digits, `_` and `-` | Enter the framework key |
| `report_output_dir must be an absolute path without '..'` | Relative output path | Use an absolute path |
| File lookup error for `cis_m365_v7_index.json` (M365 findings report) | The `policies` submodule is not in the project checkout | Enable submodule tracking on the AAP project, or run `git submodule update --init` |
| `WARNING: outputs written only to the execution environment` | `report_publish_host` is empty | Set it. See section 3.2 |
| The `scp` step fails with `Permission denied` | The job has no SSH key that `report_publish_user` accepts | Attach a machine credential. Set `report_publish_user` |
| Seed playbook: `must each resolve to exactly one object on the controller` | A name in `site_config.yml` does not match the controller, or matches more than one object | Correct `aap_project_name`, `aap_inventory_name`, `aap_ee_name` or `aap_vault_credential_name` |
| The workbook has no Owner or Decision values | No decisions file for the framework | Create `ansible/vars/decisions/<framework>.yml` |
| Every row has the same generic "Where to fix" and "Action" text | No mitigation catalog for the framework | Add `ansible/vars/mitigation/<framework>.yml` |
| The Delta column reads `first run` everywhere | One run per subject inside the window | Wait for the second run, or raise `report_lookback` |
| The reports read the wrong database | The seeded reports take the database name from `pg_database`. The store role takes it from `pg_db` | If your database is not named `compliance`, set both variables to the same name |

## 6. Known limits

These were found while checking this page against the tree on 2026-11-24.

| Item | State |
|---|---|
| `scripts/compliance_reporter.py`, `make report`, `make report-json`, `make report-csv`, `make report-cis`, `make report-nist`, `make report-iso27001`, `make report-with-data` | The targets exist and the script runs. In a test on 2026-11-24 with `--sample-data` it reported 0.0% for every framework it evaluated, with and without the policy library checked out. It evaluates built-in sample data against policy paths with `opa eval`, does not read the evidence store, and does not reconcile with any other report. Earlier versions of this guide were built around it. Do not use it for reporting |
| `ansible/playbooks/compliance_trending_report.yml` | Does not run as shipped. It passes no database password, uses `ansible_date_time` with fact gathering off, and queries a `policy_violations` table that no schema in the tree creates |
| `ansible/playbooks/drift_report.yml` | Not verified. It reads `compliance_facts.collection_timestamp`. The schema created by `aac_compliance_db` names that column `collected_at` |
| Passed controls per control | Recorded only where the assessment writes `metadata.evaluated_control_ids`. See section 1.4 |
| Policy SHA in the workbook | The workbook can show the policy library commit per evidence row. The playbook query does not select one, so the field reads `(not recorded)` |
| Freshness check | `aac_assert_fresh_results.yml` has no seeded job template |

## Revision history

| Version | Date | Change |
|---|---|---|
| v2.0 | 2026-11-24 | Rewritten around the seeded report job templates. Data prerequisites first. Examples generated by the report code. Removed the `compliance_reporter.py` quick start |
| v1.0 | 2025-10-15 | Initial guide |
