# aac_opa_containers

Ansible role that deploys and manages the three purpose-specific OPA containers
used by Ansible Automated Compliance (AAC), with optional horizontal scaling
via HAProxy load balancers.

## What this role does

1. Creates `/etc/opa/{security,compliance,ot}` policy directories on `aac_host` with SELinux contexts
2. Expands `replicas` counts into a concrete container list
3. Cleans up stale containers from previous deployments (including old replicas)
4. Pulls the OPA image and starts all containers
5. When any type has `replicas > 1`: deploys an HAProxy container on the canonical port to load-balance across backends — callers need no reconfiguration
6. Polls each canonical port's `/health` endpoint until healthy
7. Optionally generates podman systemd units for all containers (OPA + HAProxy)

Policies are **not** loaded by this role. After deployment, run:
- **AAP Template 27** — "AAC - Load OPA Policies" loads Rego files into all three containers.

## Default topology (replicas: 1)

| Container | Port | Purpose |
|-----------|------|---------|
| `opa-security` | 8181 | CIS Benchmarks, NIST, STIGs |
| `opa-compliance` | 8182 | ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, Sentinel, Governance |
| `opa-ot` | 8183 | NERC-CIP, AI Governance, AMI, Threat Detection |

## Scaled topology (replicas: N)

When `replicas > 1` for a container type, the role deploys N backend instances
plus one HAProxy container on the canonical port. The canonical port URL
never changes — existing playbooks and `site_config.yml` require no edits.

Example: `opa-security` with `replicas: 3`:

```
http://aac_host:8181       ← callers hit this (unchanged)
       │
  haproxy-opa-security     ← round-robin load balancer
       │         │         │
opa-security-1  -2  -3     ← backends on 8191, 8192, 8193
```

## Port allocation

Backend ports are pre-allocated with room for up to 10 replicas per type:

| Type | Canonical port | Backend range |
|------|---------------|---------------|
| security | 8181 | 8191–8200 |
| compliance | 8182 | 8201–8210 |
| ot | 8183 | 8211–8220 |

## Defaults

| Variable | Default | Description |
|----------|---------|-------------|
| `aac_opa_image` | `docker.io/openpolicyagent/opa:latest` | OPA container image |
| `aac_opa_policy_base_dir` | `/etc/opa` | Host base directory for policy volumes |
| `aac_opa_generate_systemd` | `true` | Generate and enable systemd units |
| `aac_opa_haproxy_image` | `docker.io/haproxy:lts-alpine` | HAProxy image (used when replicas > 1) |
| `aac_opa_haproxy_config_dir` | `/etc/opa/haproxy` | HAProxy config file directory on host |
| `aac_opa_containers[*].replicas` | `1` | Number of replicas for this container type |
| `aac_opa_containers[*].backend_base_port` | see table above | First backend port when replicas > 1 |

## Required variables

From `ansible/vars/site_config.yml`:

| Variable | Example | Description |
|----------|---------|-------------|
| `aac_host` | `<aac-host>` | Host where containers run |

## Usage

### Standard (single instance per type, no HAProxy)

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

### Scale security tier to 3 replicas

```yaml
roles:
  - role: aac_opa_containers
    vars:
      aac_opa_containers:
        - name: opa-security
          port: 8181
          policy_subdir: security
          description: "CIS Benchmarks, NIST, STIGs"
          replicas: 3
          backend_base_port: 8191
        - name: opa-compliance
          port: 8182
          policy_subdir: compliance
          description: "ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, Sentinel, Governance"
          replicas: 1
          backend_base_port: 8201
        - name: opa-ot
          port: 8183
          policy_subdir: ot
          description: "NERC-CIP, AI Governance, AMI, Threat Detection"
          replicas: 1
          backend_base_port: 8211
```

This deploys:
- `opa-security-1` on 8191, `opa-security-2` on 8192, `opa-security-3` on 8193
- `haproxy-opa-security` on 8181 (round-robin across the three)
- `opa-compliance` on 8182 (unchanged)
- `opa-ot` on 8183 (unchanged)

### Sizing guidance

| Environment size | Typical replica count |
|-----------------|----------------------|
| Lab / demo (< 50 hosts) | 1 (default) |
| Mid-size (50–500 hosts) | 2 for security tier |
| Enterprise (500–2000 hosts) | 3 for security, 2 for compliance |
| Large enterprise (2000+ hosts) | 3–5 for security, 2–3 for compliance |

OPA evaluations are CPU-bound and stateless — each replica handles a full
evaluation independently. Scale the tier that handles your highest-volume
framework (typically `opa-security` for CIS assessments).

## Scale-down

Re-run the role with reduced `replicas`. The cleanup step always removes
all containers matching `{name}-{N}`, and the haproxy step always removes
HAProxy containers before conditionally restarting them. Reducing from 3 to 1
removes `opa-security-{1,2,3}` and `haproxy-opa-security`, then starts a
single `opa-security` on port 8181 directly.

## Handlers

| Handler | Use case |
|---------|---------|
| `restart_opa_security` | Policy files updated in `security/` (replicas=1) |
| `restart_opa_compliance` | Policy files updated in `compliance/` (replicas=1) |
| `restart_opa_ot` | Policy files updated in `ot/` (replicas=1) |
| `restart_opa_security_replicas` | Policy files updated (replicas>1) — restarts all `opa-security-N` |
| `restart_opa_compliance_replicas` | Same for compliance replicas |
| `restart_opa_ot_replicas` | Same for ot replicas |
| `restart_haproxy_security` | HAProxy config changed for security |
| `restart_haproxy_compliance` | HAProxy config changed for compliance |
| `restart_haproxy_ot` | HAProxy config changed for ot |

## AAP templates that use this role

| Template ID | Name | Notes |
|-------------|------|-------|
| 28 | AAC - Deploy OPA Containers | Full redeploy; set replicas via survey or vars |
| 80 | AAC - Deploy Infrastructure | OPA + DB + MCP in one click |

## Bootstrap fallback

`scripts/install_opa.sh` deploys the default single-instance topology.
The role is authoritative for AAP-managed environments and is the only path
that supports scaling.
