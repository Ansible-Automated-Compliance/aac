# Example reports

**Authors:** Tim Coulter & Claude
**Version:** v1.0
**Date:** 2026-11-24

Sample outputs of the AAC reports. How to run the reports on your own
installation, and what data they need, is in
[`docs/operations/COMPLIANCE_REPORTING.md`](../../docs/operations/COMPLIANCE_REPORTING.md).

**All data here is synthetic.** The tenant `tenant.example`, the hosts
`rhel-web-01.example.com` and `rhel-db-01.example.com`, the people named as
owners and approvers, the ticket numbers and every finding are invented. Control
numbers and finding texts are illustrative and are not quoted from a benchmark.
The control catalog in the inputs is an 11-row excerpt made for the example, so
the banner "against real CIS M365 v7.0.0 control text" printed by the M365
report does not apply to these files.

**No output was written by hand.** Every file outside `inputs/` was produced by
the repository's own report scripts with the commands below, run from the
repository root with `python3` and no extra packages. The scripts are the ones
the report playbooks call. The playbooks add only the database query and the
file handling.

## Inputs

The inputs stand in for what the playbooks read from the database.

| File | Stands in for | Derived from |
|---|---|---|
| `inputs/findings_workbook_cis_m365_v7.json` | The payload `compliance_findings_workbook.yml` builds: `compliance_results` rows for three runs of one tenant, a catalog excerpt, coverage buckets, a decisions file, and the shipped `ansible/vars/risk/cis_m365_v7.yml` and `ansible/vars/mitigation/cis_m365_v7.yml` | The fixtures in `tests/test_findings_workbook.py`, with the tenant renamed and e-mail addresses replaced by names |
| `inputs/m365_findings_report.json` | The latest row per section for the tenant, as `m365_cis_findings_report.yml` queries it | The newest run from the file above |
| `inputs/compliance_results_cis_rhel9.json` | The latest `compliance_results` row for each of two hosts, as the findings sync reads them | Written for this example |
| `inputs/open_findings_cis_rhel9.json` | Open rows of `compliance_findings` joined with `findings_blast_radius`, plus the shipped `_default.yml` risk and mitigation files | Written for this example, consistent with the file above |
| `inputs/all_findings_cis_rhel9.json` | Rows of `compliance_findings` in every status, as the closure report queries them | Written for this example |

The `now` value in two inputs pins the report date so the outputs are
reproducible. The `_note` key is ignored by the scripts.

## Findings workbook

Job template "AAC - Compliance Findings Workbook". Columns:
[`docs/operations/FINDINGS_WORKBOOK_CONTRACT.md`](../../docs/operations/FINDINGS_WORKBOOK_CONTRACT.md).

```bash
python3 scripts/findings_workbook.py \
  --out-dir examples/reports/findings-workbook \
  --basename findings_workbook-cis_m365_v7 \
  < examples/reports/inputs/findings_workbook_cis_m365_v7.json
```

| File | Content |
|---|---|
| [`findings-workbook/findings_workbook-cis_m365_v7.md`](findings-workbook/findings_workbook-cis_m365_v7.md) | The whole report in Markdown. Start here |
| `findings-workbook/findings_workbook-cis_m365_v7.html` | The same as one HTML page |
| `findings-workbook/findings_workbook-cis_m365_v7.xlsx` | Six sheets: Summary, Findings, Unassessable, Decisions, Delta, Passed |
| `findings-workbook/findings_workbook-cis_m365_v7-<sheet>.csv` | One CSV per sheet, same columns as the workbook |
| `findings-workbook/findings_workbook-cis_m365_v7.json` | The full structured report |

What the example shows: a finding that regressed (1.1.3), one that is new
(5.1.2.2), one accepted with a justification (6.5.1), one waived at evidence
time (6.1.2), one fixed since the previous run (5.2.3.6, on the Delta sheet),
five unassessable controls split by reason, a decision whose approver is a team
alias and is flagged, and a decision that matches no open finding.

## M365 findings report

Job template "AAC - M365 CIS Findings Report". `--sample` adds the sample
banner. The playbook does not pass it.

```bash
python3 scripts/m365_findings_report.py --sample --render md \
  < examples/reports/inputs/m365_findings_report.json \
  > examples/reports/m365-findings/m365_findings_report.md
python3 scripts/m365_findings_report.py --sample --render html \
  < examples/reports/inputs/m365_findings_report.json \
  > examples/reports/m365-findings/m365_findings_report.html
python3 scripts/m365_findings_report.py --sample --render exec-html \
  < examples/reports/inputs/m365_findings_report.json \
  > examples/reports/m365-findings/m365_executive_summary.html
python3 scripts/m365_findings_report.py --sample --render csv \
  < examples/reports/inputs/m365_findings_report.json \
  > examples/reports/m365-findings/m365_results_export.csv
```

| File | Content |
|---|---|
| [`m365-findings/m365_findings_report.md`](m365-findings/m365_findings_report.md) | Findings ordered by risk, each with the risk factors and a remediation. Evidence gaps listed apart |
| `m365-findings/m365_findings_report.html` | The same as HTML |
| `m365-findings/m365_executive_summary.html` | One page for leadership |
| `m365-findings/m365_results_export.csv` | Summary by category, then a detail section per control |

## Findings layer, risk, mitigation, closure

Job templates "AAC - Sync Compliance Findings", "AAC - Compliance Risk
Scoring", "AAC - Compliance Mitigation Guidance" and "AAC - Compliance Closure
Report".

```bash
python3 scripts/findings_extract.py \
  < examples/reports/inputs/compliance_results_cis_rhel9.json \
  > examples/reports/findings-layer/findings_extract-cis_rhel9.json

python3 scripts/risk_score.py --format json \
  < examples/reports/inputs/open_findings_cis_rhel9.json \
  > examples/reports/findings-layer/risk_scored_findings-cis_rhel9.json
python3 scripts/risk_score.py --format csv \
  < examples/reports/inputs/open_findings_cis_rhel9.json \
  > examples/reports/findings-layer/risk_scored_findings-cis_rhel9.csv

python3 scripts/mitigation.py --format json \
  < examples/reports/inputs/open_findings_cis_rhel9.json \
  > examples/reports/findings-layer/mitigation_guidance-cis_rhel9.json
python3 scripts/mitigation.py --format csv \
  < examples/reports/inputs/open_findings_cis_rhel9.json \
  > examples/reports/findings-layer/mitigation_guidance-cis_rhel9.csv

python3 scripts/closure.py --format json \
  < examples/reports/inputs/all_findings_cis_rhel9.json \
  > examples/reports/findings-layer/closure_report-cis_rhel9.json
python3 scripts/closure.py --format csv \
  < examples/reports/inputs/all_findings_cis_rhel9.json \
  > examples/reports/findings-layer/closure_report-cis_rhel9.csv
```

| File | Content |
|---|---|
| [`findings-layer/findings_extract-cis_rhel9.json`](findings-layer/findings_extract-cis_rhel9.json) | What the sync derives from two stored rows: open findings, one waived finding, one evidence gap, and the scanned subjects. The sync then writes these to `compliance_findings` with SQL, which is not run here |
| [`findings-layer/risk_scored_findings-cis_rhel9.csv`](findings-layer/risk_scored_findings-cis_rhel9.csv), `.json` | Open findings ranked by band, with the basis for each score. The control that fails on two hosts scores higher. The evidence gap is listed as "Unable to assess" |
| [`findings-layer/mitigation_guidance-cis_rhel9.csv`](findings-layer/mitigation_guidance-cis_rhel9.csv), `.json` | Where, action and method per open finding. The text is generic because the tree ships no mitigation catalog for `cis_rhel9` |
| [`findings-layer/closure_report-cis_rhel9.csv`](findings-layer/closure_report-cis_rhel9.csv), `.json` | Every finding with its state: open with age, resolved with the rescan date, or waived |

## Reports without an example

The M365 violations report and the summary report
(`generate_compliance_report_from_db.yml`) are rendered by templates inside
their playbooks from a live database query. They cannot be run offline, so no
output is shown here. Their content and columns are described in section 4 of
the reporting guide.

## Regenerating

Run the commands above from the repository root. The outputs are deterministic,
except that the `.xlsx` is a zip archive and carries the time it was written, so
it differs byte for byte on every run while its sheets stay the same.
If a script changes its output, regenerate and commit the result with the
change. Set `PYTHONDONTWRITEBYTECODE=1` to avoid leaving `__pycache__` behind.
