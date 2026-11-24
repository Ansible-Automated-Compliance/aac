# Waivers: Warranting a Gap

**Version:** v1.0
**Authors:** Tim Coulter, Claude (Anthropic)

A waiver records that a finding is accepted for a stated reason, for a limited time, with a mitigation in place. It never hides the finding: the finding is stored with the result as waived, and it returns to the violations on the day the waiver expires.

## What an entry holds

Entries live in `ansible/vars/waivers.yml` (samples in `examples/waivers_example.yml`).

| Field | Required | Meaning |
|---|---|---|
| `host` | yes | Host name as stored in results, or `*` |
| `framework` | yes | Framework key, for example `cis_rhel9`, or `*` |
| `control_id` | yes | Control number or CVE id that identifies the finding |
| `reason` | yes | Why the gap is accepted |
| `approver` | yes | The person who signed off |
| `expires` | yes | `YYYY-MM-DD`. An entry without a date never applies |
| `mitigation` | site rule | What reduces the risk while the gap is open |
| `evidence_ref` | no | Where the approval and mitigation evidence live |

## Site rules

`waiver_settings` in the same file makes the policy enforce the site's own rules.

| Setting | Effect |
|---|---|
| `required_fields` | Each named field must be filled on every entry, for example `[reason, approver, mitigation]` |
| `max_ttl_days` | Longest time to live. A waiver may not expire further ahead than this |
| `expiring_within_days` | Waivers this close to expiry are listed with the result (default 14) |

With no settings, no rule is applied. A setting that is present but malformed refuses every waiver.

## What happens to a finding

| Case | Finding | Stored with the result (`metadata`) |
|---|---|---|
| Waiver applies | Leaves the violations, counted as waived | `waivers_applied`, `waived_count` |
| Waiver breaks a site rule | Stays a violation | `waivers_refused` with the reasons, `waivers_refused_count` |
| Waiver expires soon | Still waived | `waivers_expiring_soon` with the days left |
| Waiver has expired | Back in the violations | `waiver_expired_matches` |

If the policy engine cannot be reached, nothing is waived.

## Applying a change

1. Edit `ansible/vars/waivers.yml`.
2. Run "AAC - Load OPA Policies". It loads the entries and the settings.
3. Run the assessment. The next stored result reflects the change.

The site rules need a policy library that includes them (rego library after 2026-11-19). An older library ignores the settings and applies waivers as before.
