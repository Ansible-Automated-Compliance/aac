# aac_store_results

Single authoritative INSERT for the `compliance_results` table.

## Why

Over 15 playbooks each contained a hand-written `community.postgresql.postgresql_query` INSERT.
When the live schema diverged from the one used during development (e.g., `facts_id` FK vs the
old `hostname`/`framework` columns), every playbook broke individually. This role is the single
source of truth — change the SQL here and all callers benefit automatically.

## Usage

```yaml
- name: Store CIS RHEL 9 results
  include_role:
    name: aac_store_results
  vars:
    aac_result_policy_name:    "CIS RHEL 9"
    aac_result_policy_version: "CIS Red Hat Enterprise Linux 9 Benchmark v2.0.0"
    aac_result_total_controls: 338
    aac_result_violations:     "{{ violations }}"          # list of dicts/strings
    aac_result_metadata:
      hostname:    "{{ inventory_hostname }}"
      kernel:      "{{ ansible_kernel }}"
      is_compliant: "{{ is_compliant }}"
    aac_result_opa_server: "{{ opa_server_url }}"
```

After the role runs, `aac_result_id` is set to the new row's primary key.

## Variables

### Required

| Variable | Description |
|----------|-------------|
| `aac_result_policy_name` | Human-readable policy name, e.g. `"CIS RHEL 9"` |
| `aac_result_policy_version` | Benchmark version string |
| `aac_result_total_controls` | Total number of controls evaluated |

### Optional / Defaults

| Variable | Default | Description |
|----------|---------|-------------|
| `aac_result_violations` | `[]` | List of violation dicts or strings |
| `aac_result_failed_controls` | `{{ aac_result_violations \| length }}` | Auto-derived from violations |
| `aac_result_passed_controls` | `total - failed` | Auto-derived |
| `aac_result_compliance_pct` | `(passed/total)*100` | Auto-derived |
| `aac_result_facts_id` | `null` | FK to `compliance_facts.id`; omit for standalone assessments |
| `aac_result_metadata` | `{}` | Free-form JSONB (hostname, timestamps, etc.) |
| `aac_result_opa_server` | `""` | OPA URL used for this assessment |
| `aac_result_risk_level` | `null` | `"critical"` / `"high"` / `"medium"` / `"low"` |
| `aac_result_duration_ms` | `null` | Assessment duration in milliseconds |

### DB Connection

| Variable | Default |
|----------|---------|
| `aac_result_pg_host` | `{{ pg_host }}` |
| `aac_result_pg_port` | `{{ pg_port \| default(5433) }}` |
| `aac_result_pg_user` | `{{ pg_user \| default('postgres') }}` |
| `aac_result_pg_password` | `{{ pg_password \| default(compliance_db_password) }}` |
| `aac_result_pg_db` | `{{ pg_db \| default('compliance') }}` |
| `aac_result_delegate_to` | `localhost` |

## Output

| Fact | Description |
|------|-------------|
| `aac_result_id` | Primary key of the inserted `compliance_results` row |

## Schema

Inserts into `compliance_results` (from `openshift/compliance-schema.sql`):

```sql
INSERT INTO compliance_results
  (facts_id, policy_name, policy_version,
   total_controls, passed_controls, failed_controls,
   compliance_percentage, risk_level, violations,
   metadata, opa_server, assessment_duration_ms)
VALUES (...)
RETURNING id
```

`facts_id` is omitted (NULL) when `aac_result_facts_id` is not set.

## AAP Templates That Use This Role

| ID | Template Name |
|----|---------------|
| 10 | CIS RHEL 9 Assessment |
| 26 | AAC - NERC CIP Compliance Report |
| 29 | AMI - Full Compliance Audit and Store |
| 35 | Sentinel - Audit: Scan All Playbooks |
