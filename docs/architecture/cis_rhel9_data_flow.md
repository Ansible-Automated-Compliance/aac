# CIS RHEL 9 Benchmark — Data Flow Overview

**Version:** v1.0
**Date:** 2026-07-30
**Status:** Reference (grounded in `ansible/playbooks/cis_rhel9_assessment.yml`)
**Authors:** Tim Coulter; Claude (Anthropic) — co-author

---

## 1. Overview

A CIS RHEL 9 assessment moves data through four stages: **collect facts** from the
target host, **evaluate** those facts against the CIS policy in OPA, **store** the
result in PostgreSQL (plus a signed audit artifact), and **visualize** the result
in Grafana. One playbook —
`ansible/playbooks/cis_rhel9_assessment.yml` (`hosts: all`, `gather_facts: yes`,
`become: yes`) — orchestrates the whole pipeline, driven by the AAP job template
**"AAC - CIS RHEL 9 Assessment."**

```
┌──────────────┐   facts JSON    ┌───────────────┐   POST /input   ┌──────────────┐
│  1. COLLECT  │ ──────────────► │  2. EVALUATE  │ ──────────────► │  OPA-security │
│ target host  │  opa_input      │  (Ansible →   │   :8181         │  cis_rhel9    │
│ (setup, cmd, │                 │   OPA REST)   │ ◄────────────── │  Rego policy  │
│  slurp)      │                 └───────┬───────┘  violations[],  └──────────────┘
└──────────────┘                         │          compliant, %
                                         │ result
                                         ▼
                         ┌───────────────────────────────┐
                         │  3. STORE  (role                │
                         │  aac_store_results)            │
                         │   • compliance_results  (row)  │
                         │   • compliance_certifications  │  ← cosign-signed CAA
                         │     (signed evidence)          │
                         └───────────────┬────────────────┘
                                         │ SELECT
                                         ▼
                         ┌───────────────────────────────┐
                         │  4. VISUALIZE                   │
                         │  Grafana "AAC Infrastructure    │
                         │  Compliance" (uid aac-          │
                         │  compliance-001)               │
                         └────────────────────────────────┘
```

> **Ordering note.** Facts are evaluated by OPA **before** anything lands in the
> database — it is the *result* of the evaluation that is stored, not the raw
> facts. In this playbook the raw facts are written to a local JSON report
> (`reports/<host>_facts_<ts>.json`), **not** to a database table.

---

## 2. Stage 1 — Collect facts (on the target host)

Facts are gathered **inline** on the managed host (`become: yes`, no dedicated
role in this path):

| Source | What it captures |
|---|---|
| `ansible.builtin.setup` (`gather_subset: all, hardware, network, virtual`) | OS/distribution/kernel/arch, mounts, interfaces, SELinux state, service manager |
| `findmnt -J` | partition/mount layout |
| `lsmod` + `/etc/modprobe.d/*` checks | disabled filesystems (cramfs/squashfs/udf) |
| `sestatus`, `firewall-cmd --state` | SELinux + firewalld posture |
| `slurp` of `/etc/ssh/sshd_config`, `/etc/audit/auditd.conf` | SSH + auditd config |

These are assembled into the OPA input document **`opa_input.ansible_facts`** (the
`setup`-derived keys: `ansible_hostname`, `ansible_distribution*`, `ansible_kernel`,
`ansible_mounts`, `ansible_selinux`, `ansible_service_mgr`, …). A copy of the facts
is saved to `reports/<host>_facts_<timestamp>.json` on the controller.

*(A richer collector, `enhanced_cis_fact_collection.yml`, and role-based
`gather_*` collectors exist, but the standard `cis_rhel9_assessment.yml` path
uses the inline tasks above.)*

## 3. Stage 2 — Evaluate in OPA

The controller POSTs the facts to the **OPA security** container and reads back
the decision (`delegate_to: localhost`):

- **Endpoint:** `http://opa-security.aac.svc.cluster.local:8181` (`opa_security_url` in `site_config.yml`).
- **Three data queries** (each `body: {input: opa_input}`):
  1. `POST /v1/data/cis_rhel9/all_violations` → `violations[]`
  2. `POST /v1/data/cis_rhel9/compliant` → boolean
  3. `POST /v1/data/cis_rhel9/compliance_percentage` → number
- **Policy of record:** `policies/benchmarks/cis/os/linux/rhel_9/cis_rhel9_complete.rego`
  (`package cis_rhel9`) — the master orchestrator that imports ~20 section modules
  (`filesystem`, `ssh`, `auditd`, `pam`, `selinux`, …) and aggregates `compliant`,
  `all_violations`, and `compliance_percentage`.
- **Score:** the stored `compliance_percentage` is derived in Ansible as
  `((338 − total_violations) / 338) × 100` against the fixed **338-control** CIS
  RHEL 9 v2.0.0 baseline.

## 4. Stage 3 — Store in PostgreSQL (+ signed evidence)

The playbook calls `include_role: aac_store_results`, which writes to the
`compliance` database (`compliance-db.aac.svc.cluster.local:5432`).

**`compliance_results`** — one row per assessment:

| Column | Value |
|---|---|
| `hostname` | target host |
| `framework` | `cis_rhel9` |
| `policy_name` / `policy_version` | `CIS RHEL 9` / `CIS Red Hat Enterprise Linux 9 Benchmark v2.0.0` |
| `total_controls` | `338` |
| `passed_controls` / `failed_controls` | 338 − violations / violations |
| `compliance_percentage`, `compliant` | score, boolean |
| `violations` (jsonb), `metadata` (jsonb) | the violation list + summary |

> Raw facts are **not** written to `compliance_facts` in this path (`facts_id` is
> NULL); they persist only in the local `reports/*.json` file.

**`compliance_certifications`** — because `aac_caa_enabled: true`, the wrapper
chains `aac_store_certification`, which resolves the policy-library SHA, builds a
deterministic projection (`build_caa.py`), **cosign-signs** it, and inserts a
**Certifiable Audit Artifact (CAA)** row: `certification_id`, `framework`,
`policy_library_sha`, `input_hash`, `result` (jsonb), `signature`,
`signed_projection`, `signed_by`, `signed_at`, scope `host`. This is the
tamper-evident, auditor-verifiable record of the assessment.

## 5. Stage 4 — Visualize in Grafana

- **Dashboard:** "AAC Infrastructure Compliance," `uid aac-compliance-001`
  (`grafana/dashboards/aac_compliance_dashboard.json`), provisioned by
  `deploy_grafana_dashboard.yml`.
- **Datasource:** PostgreSQL `aac-compliance-db`, connecting as the read-only
  `compliance` role.
- **Panels** read `compliance_results` filtered by **`policy_name LIKE 'CIS%'`**
  over `$__timeFilter(evaluation_timestamp)`:
  - overall compliance gauge — `AVG(compliance_percentage)`
  - high-severity findings, systems assessed (`COUNT(DISTINCT hostname)`)
  - per-host bar/table, compliance trend over time, and a detail table of the
    latest assessments.
- The playbook prints the dashboard link `{{ grafana_url }}/d/aac-compliance-001`.

---

## 6. End-to-end summary

| # | Stage | Component | File / endpoint | Data |
|---|---|---|---|---|
| 1 | Collect | inline tasks on host | `ansible/playbooks/cis_rhel9_assessment.yml` | `opa_input.ansible_facts{…}` (+ `reports/*.json`) |
| 2 | Evaluate | `uri` → OPA | `…:8181/v1/data/cis_rhel9/{all_violations,compliant,compliance_percentage}` | in: `{input}`, out: violations[], bool, % |
| 2 | Policy | Rego master | `policies/benchmarks/cis/os/linux/rhel_9/cis_rhel9_complete.rego` | aggregates 338 controls / ~20 sections |
| 3 | Store | role `aac_store_results` | `compliance_results` table | row: framework `cis_rhel9`, score, violations |
| 3 | Sign | role `aac_store_certification` | `compliance_certifications` table | cosign-signed CAA row |
| 4 | Visualize | Grafana | dashboard `aac-compliance-001` | `SELECT … WHERE policy_name LIKE 'CIS%'` |

**Data-flow one-liner:** *Managed host → Ansible facts → OPA (`cis_rhel9` Rego) →
`compliance_results` + signed `compliance_certifications` → Grafana.*

## 7. References

- Playbook: `ansible/playbooks/cis_rhel9_assessment.yml`
- Roles: `ansible/roles/aac_store_results/`, `ansible/roles/aac_store_certification/`
- Policy: `policies/benchmarks/cis/os/linux/rhel_9/cis_rhel9_complete.rego` (+ section modules)
- Dashboard: `grafana/dashboards/aac_compliance_dashboard.json` (uid `aac-compliance-001`)
- Config: `ansible/vars/site_config.yml` (`opa_security_url`, `pg_host`, `grafana_url`)
- AAP job template: **AAC - CIS RHEL 9 Assessment**
