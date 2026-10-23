# EnforceAuth — Compliance State as Runtime Authorization Context

**Version:** v1.0
**Status:** 🟡 in progress — Compliance-State API + example policies landed and verified; live end-to-end pending a co-deployment with EnforceAuth
**Authors:** Tim Coulter & Claude (Anthropic)
**Related:** `~/Downloads/enforceauth_partnership_analysis.md` (partnership & GTM analysis, 2026-05-08)

## The one-line thesis

> **AAC enforces policy on _state_. EnforceAuth enforces policy at _runtime_.**
> This integration lets EnforceAuth read AAC's state evaluation as authorization
> context — so a runtime decision ("may this identity act on this host?") can be
> gated on compliance evidence ("is this host actually configured to standard?").

Much of the historical Styra/OPA investment pointed at *runtime* authorization.
State evaluation — continuous, framework-by-framework, with an immutable history —
is the half EnforceAuth does not have. AAC produces exactly that, and this bridge
hands it to EnforceAuth's OPA in the two shapes its engine already consumes.

## At a glance

- **Partner system:** EnforceAuth — "OPA-native, MCP-operable authorization control plane for the AI-agent era." Product stages: **Zift** (assess) → **Writ** (control plane; authors Rego, *ships bundles*) → **Herald** (evaluation; MCP server, cloud or **air-gapped**, *"compose Writ data with your own"*) → **Verdict** (agentic firewall, coming).
- **AAC pattern:** pull from AAC (EnforceAuth's OPA reads AAC compliance state — via `http.send` at decision time, or via a periodically-pulled OPA **bundle**).
- **Status in AAC today:** 🟡 in progress. Compliance-State API, deploy role/playbook, and both example policies are landed and verified (`opa test` 14/14, bundle loaded in a real OPA runtime, `pytest` 6/6). Live cross-product demo is the next step.
- **Effort estimate:** ~2 person-days to deploy the bridge and wire one EnforceAuth policy; ~1 more to co-demo end-to-end.
- **Required collections:** none beyond the AAC EE. The service is a rootless-podman container built from `app/Containerfile`.
- **Customer-side prerequisites:** network reachability from EnforceAuth's OPA runtime to the Compliance-State API (port 8090); a `compliance_reader` DB role (already created by `aac_compliance_db`).

## Customer use case

An enterprise runs AAC for continuous compliance assessment and EnforceAuth for
runtime authorization of humans **and non-human identities** (AI agents, service
accounts, automated workflows). They want runtime access to a system to depend on
that system's *current compliance posture*:

- *"AI agents may execute privileged operations on a host only if its CIS RHEL 9
  assessment is ≥ 90% compliant and was evaluated within the last 24 hours."*
- *"Deny any runtime action against a host that AAC has never assessed, or whose
  most recent assessment is stale."*

AAC already stores the assessment results. This integration exposes the **latest
state per host** as authorization context EnforceAuth's OPA can read at decision
time.

## Architecture / data flow

```
   ┌────────────────────────┐         GET /v1/compliance/hosts/{host}   ┌──────────────────────────┐
   │  EnforceAuth            │ ──────── (http.send, decision-time) ────► │ AAC Compliance-State API │
   │  OPA runtime            │                                           │  (read-only, :8090)      │
   │  (Herald / edge:        │ ◄──────── GET /v1/bundle.tar.gz ───────── │                          │
   │   sidecar|gateway|app)  │        (periodic pull -> data.aac...)     └────────────┬─────────────┘
   └───────────┬────────────┘                                                         │ SELECT (compliance_reader)
               │ decision: allow / deny + deny_reasons                                │ read-only
               ▼                                                            ┌─────────▼──────────┐
     runtime enforcement                                                    │ compliance_results │
     (EnforceAuth blocks the action in flight)                             │  (PostgreSQL, JSONB)│
                                                                            └────────────────────┘
                                                                              ▲ written by every
                                                                              │ AAC assessment (OPA→PG)
```

- **Endpoints:** HTTP/JSON on `:8090`. `http.send` for per-decision pull; `/v1/bundle.tar.gz` for the preloaded-data pattern (no per-decision network hop — fits EnforceAuth's sub-50ms budget and air-gapped Herald).
- **AAP credential type:** Ansible Vault (`compliance_reader_password`) + SSH machine credential to `aac_host`.
- **Database:** reads `compliance_results` **only**, through the SELECT-only `compliance_reader` role. The service never writes.
- **AAP job template:** "AAC - Deploy EnforceAuth Compliance-State API" (`ansible/playbooks/deploy_enforceauth_bridge.yml`).

## The API contract

Read-only. Latest row per `(hostname, framework)` — `compliance_results` is
append-only, so the query uses `DISTINCT ON … ORDER BY evaluation_timestamp DESC`.
Hosts are matched on **`hostname` OR `ip_address`** (EnforceAuth's host identity
may be either).

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness + DB reachability (`200` healthy, `503` DB unreachable) |
| `GET /v1/compliance/hosts` | Latest per-framework score for every assessed host |
| `GET /v1/compliance/hosts/{host_key}` | Per-host authorization context (see below) |
| `GET /v1/bundle.tar.gz` | OPA bundle — compliance state at `data.aac.compliance.hosts` |

`GET /v1/compliance/hosts/{host_key}` (see `policy/sample_host_state.json`):

```json
{
  "host_key": "web-01.lab.local",
  "found": true,
  "frameworks": {
    "cis_rhel9": {
      "compliant": true, "compliance_percentage": 94.67,
      "evaluation_timestamp": "2026-07-21T02:00:00Z",
      "age_seconds": 36000, "stale": false, "violation_count": 18
    }
  },
  "summary": { "worst_compliance_percentage": 71.0, "all_compliant": false, "any_stale": true }
}
```

### Fail-closed by design

This feeds a **security** decision, so absence of evidence must read as denial:

- Unknown host → `found: false`, empty `frameworks` → policy denies.
- Missing `evaluation_timestamp` → `age_seconds` = ∞ → `stale: true` → denies.
- `NULL` `compliant` flag → treated as `false`.
- Aggregate `summary` uses **worst-case** score across frameworks (a "best score"
  aggregate would be fail-*open*).
- The example policy **independently** re-checks staleness (`max_age_seconds`) and
  requires `found == true` — it never trusts a single field in isolation.

## Consuming from EnforceAuth's OPA

Two verified policies ship in `policy/`. Both enforce the same decision; pick the
delivery mode that matches the deployment.

| Mode | Policy file | When to use |
|---|---|---|
| Runtime pull (`http.send`) | `enforceauth_authz.rego` | Simplest to demo; state fetched per decision |
| Preloaded **bundle** | `enforceauth_authz_bundle.rego` | Production / air-gapped / sub-50ms; zero decision-time network I/O |

Operator knobs (override via `data` or bundle): `required_frameworks` (default
`{"cis_rhel9"}`), `min_compliance` (default `90.0`), `max_age_seconds` (default
`86400`), and `aac_api_base`.

## Verification (already run in this repo)

```bash
cd integrations/enforceauth

# 1. Policy unit tests — both modes, every failure path denies (14/14).
opa test policy/ -v

# 2. Response-shape contract (fail-closed) — no DB, no server (6/6).
python3 -m pytest tests -q

# 3. Bundle format proven in a REAL OPA runtime, end-to-end decision:
python3 tools/verify.py                       # writes /tmp/aac_compliance_bundle.tar.gz
opa eval -b /tmp/aac_compliance_bundle.tar.gz -d policy/enforceauth_authz_bundle.rego \
  --input <(echo '{"host":"web-01"}') 'data.enforceauth.aac_compliance_bundle.decision'
# -> {"allow": true, ...}   (absent host -> {"allow": false, "deny_reasons":["host_not_in_bundle"]})
```

## Deploy

```
AAP Job Template: "AAC - Deploy EnforceAuth Compliance-State API"
  Playbook : ansible/playbooks/deploy_enforceauth_bridge.yml
  Role     : ansible/roles/aac_enforceauth_bridge
  EE       : AAC Compliance EE   Inventory: localhost
  Creds    : Ansible Vault + aapuser1 SSH machine credential
```

Builds the image from `app/Containerfile`, writes `compliance-state.env` (read-only
`compliance_reader` password, `0600`, `no_log`), runs the container on `:8090`, and
installs a rootless-podman user systemd unit. Verify: `curl http://<aac_host>:8090/health`.

See `examples/curl_examples.sh` for smoke-test calls.

## Gotchas

- **Compliance DB location (post-CRC).** The DB may now live in OpenShift
  (`compliance-db.aac.svc.cluster.local`); the podman `postgresql` container is
  stale. Set `aac_eauth_db_host` to a host/route the container can actually reach.
  `/health` returns `503` (not a crash) when the DB is unreachable — the healthcheck
  surfaces this explicitly.
- **Host identity mismatch is the classic silent break.** The API matches on
  `hostname` *or* `ip_address`; confirm EnforceAuth passes an identifier AAC records.
- **Staleness is enforced twice** — server-computed `stale` *and* the policy's own
  `max_age_seconds`. Keep the two ceilings aligned or set the policy's stricter.
- **Read-only, always.** The connection forces `default_transaction_read_only=on`
  and uses the `compliance_reader` role. This bridge must never gain write access.
- **Port 8090** is free against OPA (8181/8182/8183), MCP (8004), smart-meter
  (8085), Grafana (3000), EDA (5000–5004).

## Open questions for EnforceAuth (from the analysis, updated)

1. ~~Self-hosted / air-gapped deployment?~~ **Resolved by the live site:** Herald
   runs cloud **or air-gapped**, edge-deployed (sidecar/gateway/in-app). This clears
   the path for the joint NERC-CIP / FedRAMP story.
2. Does Herald prefer bundle ingestion or decision-time `http.send` for external
   data like this? (We ship both; their preference sets the default.)
3. Host-identity model — what key does EnforceAuth resolve for a target resource,
   and does it match AAC's `hostname`/`ip_address`?
4. Bundle signing / `.signatures` — does Writ require signed bundles? (Ours is
   unsigned today; easy to add.)

## References

- EnforceAuth — <https://enforceauth.com> (Zift / Writ / Herald / Verdict; Rego + Cedar; OPA-native, MCP-operable)
- OPA bundles — <https://www.openpolicyagent.org/docs/latest/management-bundles/>
- OPA `http.send` — <https://www.openpolicyagent.org/docs/latest/policy-reference/#http>
- Partnership analysis — `~/Downloads/enforceauth_partnership_analysis.md`
- MCP governance (sibling AI-governance seam) — `policies/governance/mcp/mcp_governance.rego`
- Deploy archetype this draws from — `ansible/roles/aac_mcp_server/`
