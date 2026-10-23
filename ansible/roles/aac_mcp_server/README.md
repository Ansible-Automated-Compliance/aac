# aac_mcp_server

Ansible role that deploys and manages the AAP MCP server container used by
Claude Code to control Ansible Automation Platform.

## What this role does

1. Creates `/opt/aap-mcp-server/` on `aac_host`, owned by `aac_mcp_run_user`
2. Writes `mcp.env` with `AAP_TOKEN` (placeholder if no token supplied; never overwrites an existing token)
3. Stops any existing `aap-mcp` container and starts a fresh one — token read from `mcp.env` at runtime, not embedded in the command line
4. Health-checks port 8004 (HTTP 200 or 404 both indicate the server is up)
5. Optionally writes a user-level systemd unit under `aac_mcp_run_user` and enables linger so it starts on boot without an active login

Token rotation is handled separately by **Template 40 — AAC - Rotate MCP Token**
(`ansible/playbooks/rotate_mcp_token.yml`). That playbook creates a new AAP
gateway token and restarts the container — no role re-run needed.

## Defaults

| Variable | Default | Description |
|----------|---------|-------------|
| `aac_mcp_image` | `{{ mcp_image }}` | Container image (from site_config.yml) |
| `aac_mcp_container_name` | `aap-mcp` | Container name |
| `aac_mcp_port` | `8004` | Host port |
| `aac_mcp_app_dir` | `/opt/aap-mcp-server` | Source volume mount on aac_host |
| `aac_mcp_token` | `""` | AAP token — blank writes placeholder; set via vault or rotate job |
| `aac_mcp_run_user` | `{{ aap_ssh_user }}` | OS user that owns the container (from site_config.yml) |
| `aac_mcp_gateway_url` | `{{ external_aap_url }}` from the environment profile (required) | AAP gateway URL inside container |
| `aac_mcp_controller_url` | `{{ external_aap_url }}/api/controller/v2` | Controller API URL inside container |
| `aac_mcp_network` | `host` | **Required post-CRC** — see below |
| `aac_mcp_volume_opts` | `Z` | SELinux relabel for the `/app` bind mount |
| `aac_mcp_opa_url` | `{{ external_opa_compliance_url }}` from the environment profile | OPA endpoint for governance decisions |
| `aac_mcp_opa_governance_enabled` | `true` | DEPRECATED — governance is unconditional; `false` makes the server refuse to start |
| `aac_mcp_entrypoint` | `/app/server_opa.py` | OPA-governed server (streamable-http) — the only entrypoint; the ungoverned `server.py` bypass was removed 2026-09-21 |
| `aac_mcp_agent_id` | `""` | Agent identity sent to OPA (`input.agent`) and written to the decision log — set one per deployed agent |
| `aac_mcp_decision_log_dsn` | `""` | PostgreSQL DSN for the append-only `ai_action_log` decision log; empty disables persistence |
| `aac_mcp_decision_log_required` | `false` | `true` → a failed log write refuses the call (no evidence, no action) |

## Post-CRC notes (2026-08-01)

**Host networking is required.** With the default rootless network, the container
resolves the cluster's ingress routes to its *own* loopback rather than the host's, so every
call to the AAP gateway fails with `httpx.ConnectError: All connection attempts
failed` — which surfaces as HTTP 500 on an authenticated request. `--network host`
makes the container resolve and connect exactly as the host does. There is
consequently no `-p` mapping; the app binds the host port directly.

**The bind mount needs `:Z`.** Without it the container hits
`PermissionError: [Errno 13] Permission denied: '/app'` even though the directory is
world-readable — the host directory carries the private SELinux MCS categories of
whichever container last claimed it. Note `podman inspect` reports the *resulting*
mount as plain `rbind`, so copying options from inspect silently loses the relabel.

**The endpoint is `/mcp`, not `/sse`.** `server_opa.py` runs
`transport='streamable-http'`. `/sse` returns 404. Health check:

```bash
curl -s -4 -X POST http://127.0.0.1:8004/mcp \
  -H "Authorization: Bearer $AAP_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"1.0"}}}'
```

Use `-4`: the listener is IPv4-only, and `localhost` resolves to `::1` first, which
returns a misleading `000`.

**OPA governance is UNCONDITIONAL** — there is no disable path. The old
`OPA_GOVERNANCE_ENABLED=false` bypass was removed after review flagged it as
fail-open: the server now refuses to start if the flag is set false (for
development, point `OPA_URL` at a permissive local OPA instead). Every
tool call is evaluated by the `ai_governance/mcp` policy before execution:
default-deny, fail-closed on OPA timeout/unreachability. Each verdict — allow and
deny — is written append-only to `ai_action_log` in the compliance DB when
`aac_mcp_decision_log_dsn` is set (schema: `ansible/files/ai_action_log_schema.sql`),
keyed by a per-call trace id and the deployment's agent identity
(`aac_mcp_agent_id` → OPA `input.agent`). Note the "22 blocked operations" in the
startup log are a *separate*, static blocklist (`OperationIdBlackRule`) applied
before the catalog is ever visible, and are unaffected by this flag.
| `aac_mcp_openapi_spec_url` | `file:///app/aap-controller-api.json` | OpenAPI spec path inside container |
| `aac_mcp_generate_systemd` | `true` | Write and enable user-level systemd unit |

## Required variables

From `ansible/vars/site_config.yml`:

| Variable | Example | Description |
|----------|---------|-------------|
| `aac_host` | `<aac-host>` | Host where the container runs |
| `mcp_image` | `<aac-host>/aap-mcp-server:v1.0` | Pre-built MCP container image |
| `aap_ssh_user` | `aapuser1` | OS user for the rootless container |

## Usage

### Standard deploy (called by Template 39 or fresh install)

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

### With token pre-populated (e.g., during fresh install when token is known)

```yaml
roles:
  - role: aac_mcp_server
    vars:
      aac_mcp_token: "{{ vault_aap_local_mcp_token }}"
```

### Skip systemd (e.g., OpenShift deployment)

```yaml
roles:
  - role: aac_mcp_server
    vars:
      aac_mcp_generate_systemd: false
```

## Token management

The role writes `mcp.env` only once (`force: false`). After initial deploy:

- **Rotate token:** Run **Template 40 — AAC - Rotate MCP Token** — creates a new AAP gateway token, updates `mcp.env`, restarts the container
- **Check current token ID:** `curl -sk -H "Authorization: Bearer TOKEN" https://<aac-host>/api/gateway/v1/tokens/ | jq '[.results[] | {id, description}]'`

## MCP SDK version

The container image **must use `mcp==1.25.0`** — v1.26.0 broke SSE session
initialization. The pre-built image pins this in `requirements.txt`. If the
container is rebuilt and starts returning `-32602` errors, run:

```bash
podman exec aap-mcp pip install mcp==1.25.0 -q
podman restart aap-mcp
```

Then restart Claude Code to get a fresh SSE session.

## AAP templates that use this role

| Template ID | Name | Notes |
|-------------|------|-------|
| 39 | AAC - Demo Stability Setup | Deploys MCP + all other demo containers |
| 40 | AAC - Rotate MCP Token | Token rotation only — does not use role |

## Health check

```bash
# Verify container is running
podman ps --filter name=aap-mcp --format '{{.Status}}'

# Verify SSE endpoint responds (requires auth header)
curl -s --max-time 5 -H "Authorization: Bearer TOKEN" \
  http://<aac-host>:8004/sse | head -c 200
# Expected: event: endpoint\ndata: /messages/?session_id=...
```
