# Ansible Automated Compliance — Role Installation Guide

**Version:** 1.0 | **Updated:** March 2026

This guide covers the five AAC Ansible roles used to install and operate the
AAC platform. These roles are the authoritative deployment path — all AAP job
templates call them internally. You can also call them directly from a playbook
for custom deployments.

---

## Role Overview

| Role | AAP Template | Purpose |
|------|-------------|---------|
| [`aac_opa_containers`](#aac_opa_containers) | 28 — Deploy OPA Containers | Deploy all three OPA policy-evaluation containers |
| [`aac_compliance_db`](#aac_compliance_db) | 114 — Initialize PostgreSQL Database | Deploy PostgreSQL and create compliance schema |
| [`aac_mcp_server`](#aac_mcp_server) | 39 — Demo Stability Setup | Deploy the AAP MCP server for Claude Code integration |
| [`aac_store_results`](#aac_store_results) | *(called by assessment playbooks)* | Write compliance results to PostgreSQL |
| [`aac_facts_collector`](#aac_facts_collector) | 15/16 — Fact Collection | Gather system facts for OPA evaluation |

For a **full stack install** (all components at once), see [Full Stack Deployment](#full-stack-deployment) below.

---

## Prerequisites

### 1. Ansible Vault secrets file

All roles require passwords from Ansible Vault. Ensure `ansible/vars/vault_secrets.yml`
contains the following variables:

```
compliance_db_password       # PostgreSQL superuser password
compliance_reader_password   # Read-only role (Grafana / reports)
```

Decrypt and verify:
```bash
ansible-vault view ansible/vars/vault_secrets.yml --vault-password-file ~/.vault_pass
```

### 2. Site configuration file

Roles read host/URL settings from `ansible/vars/site_config.yml`. Verify these
are correct for your environment:

```yaml
aac_host: <aac-host>          # AAP server IP or hostname
pg_host: <aac-host>
pg_port: 5432
pg_user: postgres
pg_db: compliance
aap_ssh_user: aapuser1
mcp_image: <aac-host>/aap-mcp-server:v1.0
```

### 3. Podman

All containers are run with **podman** (not docker). Verify podman is installed:

```bash
podman --version
```

### 4. Collections

The `community.postgresql` collection is required for database roles. It is
bundled in the AAC Compliance Execution Environment (EE v1.1.0, ID 6).
If running outside AAP, install it manually:

```bash
ansible-galaxy collection install community.postgresql
```

---

## aac_opa_containers

Deploys the three purpose-specific OPA containers that evaluate all compliance policies.

| Container | Port | Frameworks |
|-----------|------|-----------|
| `opa-security` | 8181 | CIS Benchmarks, NIST, STIGs |
| `opa-compliance` | 8182 | ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, Sentinel |
| `opa-ot` | 8183 | NERC-CIP, AI Governance, AMI/IEC 62443 |

**Note:** This role deploys containers only. Policies are loaded separately by
running **AAP Template 27 — AAC: Load OPA Policies** after deployment.

### Standard deployment (1 instance per container)

```yaml
- name: Deploy OPA Containers
  hosts: localhost
  connection: local
  gather_facts: false
  vars_files:
    - ../vars/site_config.yml
    - ../vars/vault_secrets.yml
  roles:
    - role: aac_opa_containers
```

### Scaled deployment (multiple replicas with HAProxy)

When `replicas > 1`, the role automatically deploys an HAProxy load balancer
on the canonical port. Callers continue using the same port — no reconfiguration
needed.

```yaml
roles:
  - role: aac_opa_containers
    vars:
      aac_opa_containers:
        - name: opa-security
          port: 8181
          policy_subdir: security
          replicas: 3                  # deploys opa-security-1/2/3 + HAProxy on 8181
          backend_base_port: 8191
        - name: opa-compliance
          port: 8182
          policy_subdir: compliance
          replicas: 1                  # single instance, no HAProxy
        - name: opa-ot
          port: 8183
          policy_subdir: ot
          replicas: 1
```

### Key variables

| Variable | Default | Description |
|----------|---------|-------------|
| `aac_opa_image` | `docker.io/openpolicyagent/opa:latest` | OPA container image |
| `aac_opa_policy_base_dir` | `/etc/opa` | Host directory for policy volume mounts |
| `aac_opa_generate_systemd` | `true` | Create systemd units for on-boot startup |
| `aac_opa_haproxy_image` | `docker.io/haproxy:lts-alpine` | HAProxy image (replicas > 1 only) |

### Verify deployment

```bash
curl http://<aac_host>:8181/health   # opa-security
curl http://<aac_host>:8182/health   # opa-compliance
curl http://<aac_host>:8183/health   # opa-ot
```

All three should return `{}` (HTTP 200).

---

## aac_compliance_db

Deploys the PostgreSQL container and initializes the complete AAC compliance schema.
All DDL is idempotent — safe to re-run for schema migrations or when adding tables.

### Schema created

| Object | Type | Purpose |
|--------|------|---------|
| `compliance_results` | Table | OPA evaluation results (all frameworks) |
| `compliance_facts` | Table | Raw Ansible facts (pre-OPA) |
| `host_facts` | Table | Nightly gather_facts snapshots |
| `host_facts_latest` | View | Most recent snapshot per host |
| `sidecar_datasets` | Table | Org context: Digital Sovereignty, NERC-CIP assets |
| `sidecar_datasets_latest` | View | Most recent sidecar per type+entity |

### Full deployment (container + schema)

```yaml
- name: Initialize Compliance Database
  hosts: localhost
  connection: local
  gather_facts: false
  vars_files:
    - ../vars/site_config.yml
    - ../vars/vault_secrets.yml
  roles:
    - role: aac_compliance_db
```

### Schema-only (container already running)

Use this when you need to add new tables to an existing database without
recreating the container:

```yaml
roles:
  - role: aac_compliance_db
    vars:
      aac_db_skip_container_deploy: true
```

### Key variables

| Variable | Default | Description |
|----------|---------|-------------|
| `aac_db_image` | `registry.access.redhat.com/ubi9/postgresql-15` | PostgreSQL image |
| `aac_db_container_name` | `postgresql` | Container name |
| `aac_db_volume` | `compliance_pgdata` | Named volume for data persistence |
| `aac_db_port` | `5432` | Host port |
| `aac_db_name` | `compliance` | Database name |
| `aac_db_user` | `postgres` | Superuser account |
| `aac_db_password` | `{{ compliance_db_password }}` | **From Ansible Vault** |
| `aac_db_reader_user` | `compliance_reader` | Read-only role (Grafana / reports) |
| `aac_db_reader_password` | `{{ compliance_reader_password }}` | **From Ansible Vault** |
| `aac_db_generate_systemd` | `true` | Create systemd unit for on-boot startup |
| `aac_db_skip_container_deploy` | `false` | Schema-only mode |

### Verify deployment

```bash
podman exec postgresql psql -U postgres -d compliance -c "\dt"
```

Expected output: six objects (`compliance_results`, `compliance_facts`,
`host_facts`, `host_facts_latest`, `sidecar_datasets`, `sidecar_datasets_latest`).

---

## aac_mcp_server

Deploys the AAP MCP server that allows Claude Code to control AAP through
46 dedicated tools. Required only for AI-assisted compliance workflows.

**Token management:** This role writes a token placeholder on first deploy.
Use **AAP Template 40 — AAC: Rotate MCP Token** to set or rotate the live
token without redeploying.

### Standard deployment

```yaml
- name: Deploy AAP MCP Server
  hosts: localhost
  connection: local
  gather_facts: false
  vars_files:
    - ../vars/site_config.yml
    - ../vars/vault_secrets.yml
  roles:
    - role: aac_mcp_server
```

### With token pre-populated (fresh install when token is known)

```yaml
roles:
  - role: aac_mcp_server
    vars:
      aac_mcp_token: "{{ vault_aap_local_mcp_token }}"
```

### Key variables

| Variable | Default | Description |
|----------|---------|-------------|
| `aac_mcp_image` | `{{ mcp_image }}` | Pre-built MCP image (from site_config.yml) |
| `aac_mcp_container_name` | `aap-mcp` | Container name |
| `aac_mcp_port` | `8004` | Host port (SSE endpoint) |
| `aac_mcp_app_dir` | `/opt/aap-mcp-server` | Source volume on the host |
| `aac_mcp_token` | `""` | AAP Bearer token — blank writes placeholder |
| `aac_mcp_run_user` | `{{ aap_ssh_user }}` | OS user owning the rootless container |
| `aac_mcp_gateway_url` | `https://host.containers.internal` | AAP URL inside container |
| `aac_mcp_generate_systemd` | `true` | Create user-level systemd unit with linger |

### Verify deployment

```bash
curl -s --max-time 5 \
  -H "Authorization: Bearer <token>" \
  http://<aac_host>:8004/sse | head -c 200
```

Expected: `event: endpoint` followed by a session ID.

---

## aac_store_results

The single authoritative INSERT into the `compliance_results` table.
Every assessment playbook calls this role instead of writing its own SQL,
ensuring schema consistency across all 15+ frameworks.

This role is **not** called directly during installation. It is called at the
end of every compliance assessment playbook.

### Usage in an assessment playbook

```yaml
- name: Store compliance results
  ansible.builtin.include_role:
    name: aac_store_results
  vars:
    aac_result_policy_name:    "CIS RHEL 9"
    aac_result_policy_version: "CIS Red Hat Enterprise Linux 9 Benchmark v2.0.0"
    aac_result_total_controls: 338
    aac_result_violations:     "{{ opa_result.json.result.violations | default([]) }}"
    aac_result_metadata:
      hostname:     "{{ inventory_hostname }}"
      is_compliant: "{{ opa_result.json.result.compliant }}"
      trigger:      "{{ compliance_trigger | default('manual') }}"
```

After the role runs, `aac_result_id` is set to the new row's primary key
(useful for linking follow-on queries).

### Required variables

| Variable | Description |
|----------|-------------|
| `aac_result_policy_name` | Human-readable name, e.g. `"NERC-CIP"` |
| `aac_result_policy_version` | Benchmark/version string |
| `aac_result_total_controls` | Total controls evaluated (integer) |

### Auto-derived variables (override if needed)

| Variable | Derived from | Description |
|----------|-------------|-------------|
| `aac_result_violations` | *(caller sets)* | List of violation strings/dicts — defaults to `[]` |
| `aac_result_failed_controls` | `violations \| length` | Count of failed controls |
| `aac_result_passed_controls` | `total - failed` | Count of passed controls |
| `aac_result_compliance_pct` | `(passed / total) * 100` | Compliance percentage |

### Optional variables

| Variable | Default | Description |
|----------|---------|-------------|
| `aac_result_facts_id` | `null` | FK to `compliance_facts.id` |
| `aac_result_metadata` | `{}` | Free-form JSONB (hostname, timestamps, etc.) |
| `aac_result_opa_server` | `""` | OPA URL used for this assessment |
| `aac_result_risk_level` | `null` | `critical` / `high` / `medium` / `low` |
| `aac_result_duration_ms` | `null` | Assessment duration in milliseconds |

---

## aac_facts_collector

Collects system facts from managed hosts and stores them in the `compliance_facts`
table for OPA evaluation. Used by the nightly fact collection workflow and
on-demand assessments.

### Usage

```yaml
- name: Collect and store system facts
  hosts: rhel_servers
  gather_facts: true
  vars_files:
    - ../vars/site_config.yml
    - ../vars/vault_secrets.yml
  roles:
    - role: aac_facts_collector
```

Facts are stored as JSONB in `compliance_facts` (~180 KB per host per run).
The `host_facts_latest` view always points to the most recent snapshot per host.

---

## Full Stack Deployment

To deploy all AAC infrastructure components in the correct order, use
`ansible/playbooks/deploy_infrastructure.yml` which calls all roles in sequence:

```bash
# Via AAP (recommended) — runs all three in order:
#   Template 114: Initialize PostgreSQL  →
#   Template 28:  Deploy OPA Containers  →
#   Template 27:  Load OPA Policies
```

Or call directly with Ansible (for greenfield / offline installs):

```yaml
# deploy_all.yml — example full-stack play
- name: Deploy AAC Infrastructure
  hosts: localhost
  connection: local
  gather_facts: false
  vars_files:
    - ansible/vars/site_config.yml
    - ansible/vars/vault_secrets.yml
  roles:
    - role: ansible/roles/aac_compliance_db      # 1. PostgreSQL first
    - role: ansible/roles/aac_opa_containers     # 2. OPA containers
    - role: ansible/roles/aac_mcp_server         # 3. MCP server (optional)
```

Then load OPA policies:

```bash
# Load all Rego policies into all three OPA containers
for container_port in 8181 8182 8183; do
  find policies -name "*.rego" | while read policy; do
    policy_id=$(echo "$policy" | sed 's|/|_|g; s|\.rego||')
    curl -s -X PUT --data-binary @"$policy" \
      "http://<aac_host>:${container_port}/v1/policies/${policy_id}"
  done
done
```

Or run **AAP Template 27 — AAC: Load OPA Policies** which handles routing
each policy file to the correct container automatically.

---

## Installation Order Summary

```
1. aac_compliance_db      Deploy PostgreSQL + initialize schema
        ↓
2. aac_opa_containers     Deploy opa-security, opa-compliance, opa-ot
        ↓
3. AAP Template 27        Load all Rego policies into OPA containers
        ↓
4. aac_mcp_server         Deploy MCP server (Claude Code integration — optional)
        ↓
5. aac_facts_collector    Begin collecting facts (nightly workflow)
        ↓
6. aac_store_results      Called automatically by each assessment playbook
```

---

## Troubleshooting

### OPA container not starting

```bash
podman logs opa-security
podman logs opa-compliance
podman logs opa-ot
```

### PostgreSQL schema missing tables

Re-run the role in schema-only mode:
```bash
# Via AAP: Template 114 with aac_db_skip_container_deploy=true
# Or directly:
ansible-playbook ansible/playbooks/aac_init_facts_schema.yml \
  --vault-password-file ~/.vault_pass
```

### MCP server not responding

```bash
# Check container is running
podman ps --filter name=aap-mcp

# Check logs
podman logs aap-mcp

# Rotate token if getting 401
# Run AAP Template 40: AAC - Rotate MCP Token
```

### Policy not loading into OPA

Verify Rego syntax before loading:
```bash
opa check policies/path/to/policy.rego
```

Then re-run **AAP Template 27 — AAC: Load OPA Policies**.
