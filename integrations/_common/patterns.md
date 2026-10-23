# AAC Integration Patterns

Every integration in AAC fits one of three architectural shapes. When
you're scoping a new integration, identify which pattern (or
combination) applies first — it determines the EDA / playbook / DB
moving parts.

---

## 1. Event-driven (EDA → AAP workflow)

The vendor system emits an event (webhook / file change / log line / API
poll). EDA listens, applies routing rules, fires an AAP workflow that
runs playbooks.

```
  ┌───────────────┐  webhook /     ┌────────────────┐  trigger    ┌────────────────┐
  │ {Vendor sys}  │ ─ file watch ─►│ EDA rulebook   │ ────────────► AAP workflow   │
  │ (event source)│  / log line    │ (extensions/   │  via API    │ (controller_v2)│
  └───────────────┘                │  eda/rulebooks)│             └────────┬───────┘
                                   └────────────────┘                      │
                                                                            ▼
                                                                  ┌────────────────┐
                                                                  │ Ansible job(s) │
                                                                  └────────────────┘
```

**When to use:**
- Customer wants AAC to react to an external event in near real-time
- The vendor system pushes (webhook or message queue)

**Existing examples in the repo:**
- `extensions/eda/rulebooks/compliance_webhook_events.yml` (port 5000)
- `extensions/eda/rulebooks/sentinel_github_webhook.yml` (port 5003)
- `extensions/eda/rulebooks/golden_image_enforcement.yml` (port 5004)
- `extensions/eda/rulebooks/compliance_scheduled_drift.yml` (polling / tick-based source, not webhook)
- `extensions/eda/rulebooks/ami_events.yml` (smart meter events)
- `extensions/eda/rulebooks/nerc_cip_events.yml` (NERC-CIP triggers)

**Port map:** Each rulebook claims a unique port (5000-5099 by convention). Track allocations in `extensions/eda/rulebooks/` headers — duplicate-port mistakes cause EDA activations to crash-loop.

**Complexity:** Medium. Decision Environments need the right collection + Python deps. EDA tokens need `cve_feed` or equivalent scopes. Webhook payloads vary per vendor — the rulebook DSL is YAML, not full Jinja, so payload shape matters.

---

## 2. Push from AAC (AAP job → external API)

An AAP job template runs a playbook that calls the vendor's API
(creates a ticket, sends a Slack message, applies a Terraform plan, etc.).

```
  ┌──────────────────┐                ┌──────────────────┐
  │ AAP job template │ ─── POST ────► │ {Vendor system}  │
  │ (run playbook    │   /api/...     │ (creates ticket, │
  │  on schedule or  │                │  sends alert,    │
  │  triggered)      │                │  applies plan)   │
  └────────┬─────────┘                └──────────────────┘
           │
           ▼
   ┌──────────────────┐
   │ compliance DB    │ ← log the API call result
   └──────────────────┘
```

**When to use:**
- AAC needs to inform the vendor system of a compliance event
- The vendor system exposes a REST API and accepts a service account

**Existing examples in the repo:**
- `ansible/playbooks/notify_servicenow_violations.yml` — ServiceNow incident creation
- `demos/windows_golden_image/playbooks/windows_golden_notify_helpdesk.yml` — Postgres-table-based "ticket"
- `ansible/playbooks/push_db_backup_to_github.yml` — GitHub repo push
- `ansible/playbooks/aac_cve_auto_apply.yml` — applies remediation, logs to DB

**Idempotency rule:** Always query before POST. Most vendor APIs don't have native upsert. The ServiceNow playbook does the right thing — it queries for an existing incident matching the framework + hostname before creating.

**Complexity:** Low to medium. Mostly `uri` module calls. Hardest parts are credential management (AAP credential type + how to source it) and rate-limit / back-off handling.

---

## 3. Pull from AAC (external system queries AAC state)

An external system (a customer dashboard, a SIEM, a portal) reads from
AAC's compliance PostgreSQL via the read-only `compliance_reader` role.

> **OPA HTTP endpoints (8181/8182/8183) are unauthenticated and intended
> to be internal-only.** Don't expose them directly to external systems.
> If a customer needs OPA evaluation from outside the AAC network, put
> an authenticated proxy / bridge in front (an AAP job that wraps the
> call, or a small FastAPI service that adds bearer auth) — or expose
> the result via the compliance DB instead.

```
  ┌──────────────────┐                ┌──────────────────────┐
  │ {External sys}   │ ─── SELECT ──► │ compliance DB        │
  │ (BI dashboard,   │   compliance_  │ (compliance_results, │
  │  SIEM, portal)   │   reader role  │  cve_*, etc.)        │
  └──────────────────┘                └──────────────────────┘

                       OR

  ┌──────────────────┐                ┌──────────────────────┐
  │ {External sys}   │ ── POST /v1/   │ OPA :8181 / 8182 /   │
  │ (any client)     │  data/<policy> │  8183                │
  │                  │ ◄ compliant or │ (security/compliance/│
  │                  │   violation    │  ot)                 │
  └──────────────────┘                └──────────────────────┘
```

**When to use:**
- Vendor system can't accept pushes — it has to poll
- Customer has a BI / Grafana / Splunk that wants direct DB access
- Customer wants to call OPA from their own code

**Existing examples in the repo:**
- `ansible/roles/aac_portal_bridge/` — deploys the FastAPI bridge that wraps the compliance reader with tenant auth for outside callers
- Grafana dashboards under `grafana/dashboards/` — direct compliance DB datasource (internal)
- The `compliance_reader` PostgreSQL role itself

**Read-only safety:** The `compliance_reader` role has `GRANT SELECT`
only; no writes are possible. That makes the DB the right surface for
external pulls. OPA HTTP endpoints, by contrast, are unauthenticated —
fine for internal callers on the AAC network, but **never expose
8181/8182/8183 directly to a customer or third-party**. Wrap them in
the portal bridge (or an equivalent auth proxy) if external evaluation
is needed.

**Complexity:** Low — just give the customer credentials + a network path. The catch is **schema stability**: if you rename a column, every pull-customer's dashboards break.

---

## Most integrations combine 1 + 2

Real-world enterprise integrations are usually **hybrid event-driven +
push**. Example: ServiceNow integration in this repo
- Webhook from ServiceNow → EDA rulebook → AAP workflow (event-driven, pattern 1)
- AAP job runs → POSTs incident creation to ServiceNow Table API (push, pattern 2)

The two halves are independent — many integrations land one direction
before the other.

---

## Adding a 4th pattern (advisory: don't)

If an integration doesn't fit 1, 2, or 3, **stop and check the
architecture**. The three patterns above cover ~95% of enterprise
integrations. The 5% that don't fit are usually:

- **Streaming** (Kafka, RabbitMQ): in practice modeled as pattern 1 with a custom EDA source plugin
- **Bidirectional sync** (CMDB): model as pattern 2 push + pattern 3 pull running on a schedule
- **Embedded auth** (federate AAP into customer SSO): not an integration in the AAC sense — that's an AAP topology change

If you genuinely need a 4th pattern, write up the case and bring it to
the AAC core team before building.
