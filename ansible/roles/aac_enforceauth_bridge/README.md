> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: CONTAINERS-INTERNALx1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# aac_enforceauth_bridge

Deploys the **AAC Compliance-State API** — a read-only service that exposes the
latest compliance assessment per host as runtime authorization context for
EnforceAuth. AAC enforces policy on *state*; EnforceAuth enforces at *runtime*;
this bridge lets EnforceAuth's OPA read AAC state when deciding whether an identity
(human or AI agent) may act on a host.

Full integration write-up: [`integrations/enforceauth/`](../../../integrations/enforceauth/).

## What it does

1. Syncs the API source (`integrations/enforceauth/app/`) to `aac_host`.
2. Builds the image from `Containerfile` via rootless `podman build`.
3. Writes `compliance-state.env` with the read-only `compliance_reader` password (`0600`, `no_log`).
4. Runs the container on port 8090 with `--restart=always`.
5. Polls `/health` (200 healthy, 503 = DB unreachable).
6. Installs a user-level systemd unit (linger) so it survives reboots.

## Requirements

- `aac_host`, `aap_ssh_user` (from `site_config.yml`)
- `compliance_reader_password` (from `vault_secrets.yml`)
- podman on `aac_host`; the `compliance_reader` role (created by `aac_compliance_db`)

## Key variables

| Variable | Default | Purpose |
|---|---|---|
| `aac_eauth_port` | `8090` | Host port |
| `aac_eauth_image` | `aac-compliance-state:v1.0` | Built image tag |
| `aac_eauth_app_dir` | `/opt/aac-compliance-state` | Source + build dir on host |
| `aac_eauth_db_host` | `host.containers.internal` | DB host as seen from the container (see post-CRC note) |
| `aac_eauth_db_user` | `compliance_reader` | Read-only DB role |
| `aac_eauth_max_age_seconds` | `86400` | Assessments older than this are marked stale |
| `aac_eauth_generate_systemd` | `true` | Install the user systemd unit |

## Usage

```yaml
- hosts: localhost
  connection: local
  vars_files:
    - ../vars/site_config.yml
    - ../vars/vault_secrets.yml
  roles:
    - role: aac_enforceauth_bridge
```

Or run the packaged playbook: `ansible/playbooks/deploy_enforceauth_bridge.yml`.

> **Post-CRC:** if the compliance DB lives in OpenShift
> (`compliance-db.aac.svc.cluster.local`), set `aac_eauth_db_host` to a route the
> container can reach — the podman `postgresql` container is stale.
