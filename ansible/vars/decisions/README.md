# Decisions files

One file per framework: `ansible/vars/decisions/<framework>.yml` (for example
`cis_m365_v7.yml`, `cis_rhel9.yml`). The findings workbook
(`ansible/playbooks/compliance_findings_workbook.yml`) joins it to the live
findings on every run, so an owner, an approval or a business justification
recorded here survives the next assessment and appears in the next workbook
without anyone re-typing it.

This is the only place decisions are written. Evidence
(`compliance_results`) is never edited, and the workbook is never edited by
hand — it is regenerated from evidence plus this file.

Start from `examples/decisions_example.yml`. Fields:

| Field | Required | Meaning |
|---|---|---|
| `default_owners` | no | owner by section or control prefix (longest match wins); `_default` catches the rest |
| `review_cycle_days` | no | how long an accepted deviation stands before renewal (default 90) |
| `decisions[].control_id` | yes | control number, with or without the `CIS` prefix |
| `decisions[].subject` | no | hostname / tenant, or `*` (default) for every subject |
| `decisions[].owner` | no | business owner for this finding; overrides the default owner |
| `decisions[].decision` | yes | `remediate`, `accept` (keep, with justification) or `review` |
| `decisions[].justification` | for accept | why the deviation is kept, or the remediation plan |
| `decisions[].approver` | yes | a **named person**, not a team alias — the workbook flags aliases |
| `decisions[].approved` | no | date approved (YYYY-MM-DD) |
| `decisions[].expires` | for accept | renewal date; when missing it is defaulted to `approved + review_cycle_days` and flagged |
| `decisions[].risk_override` | no | Critical / High / Medium / Low — your call stands next to the derived band |
| `decisions[].ticket` | no | change or tracking reference |

Accepted decisions can be exported as OPA waiver entries so the evidence
itself records the deviation as waived (visible, never hidden):

```bash
python3 scripts/findings_workbook.py --emit-waivers <<< '{"framework":"cis_m365_v7","decisions":'"$(python3 -c 'import yaml,json;print(json.dumps(yaml.safe_load(open("ansible/vars/decisions/cis_m365_v7.yml"))))')"'}'
```

Paste the resulting `waiver_entries` into `ansible/vars/waivers.yml` (or pass
them as `waiver_entries` extra_vars) and re-run "AAC - Load OPA Policies".

Column contract for the workbook: `docs/operations/FINDINGS_WORKBOOK_CONTRACT.md`.
