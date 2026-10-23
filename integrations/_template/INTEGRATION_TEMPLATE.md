# {Integration Name}

> Copy this template to `integrations/<slug>/README.md` when starting a
> new integration write-up. Fill in every section. Delete this quote
> block when you're done.

## At a glance

- **Customer system:** {vendor name + product name}
- **AAC pattern:** event-driven | push from AAC | pull from AAC | hybrid
- **Status in AAC today:** ✓ proven | 🟡 in progress | ⚠ partial | ✗ greenfield
- **Effort estimate:** {N} person-days for a competent AAP engineer who hasn't done this integration before
- **Required collections:** {list with Galaxy / Automation Hub source noted}
- **Customer-side prerequisites:** {API endpoint, service account, license entitlement, network reachability}

## Customer use case

One or two paragraphs describing what the customer wants AAC to do with
this system. Be specific:

- AAC fires `{action}` in `{vendor system}` when `{event}` happens
- AAC consumes `{feed / webhook / API endpoint}` from `{vendor system}` to enrich `{compliance results / inventory / debt scoring}`
- `{Vendor system}` consumes `{compliance results / OPA decisions / events}` from AAC to drive `{their automation / their alerting / their dashboards}`

## Architecture / data flow

ASCII diagram showing AAC ↔ external system. Identify:
- HTTP / gRPC endpoints
- AAP credential type
- EDA rulebook(s) involved (if any)
- AAP job / workflow templates kicked off
- Database tables read/written

```
   ┌─────────────────┐                       ┌──────────────────┐
   │ {Vendor system} │ ◄──── (action) ────── │  AAC + AAP 2.6   │
   │                 │ ───── (event) ─────► │                  │
   └─────────────────┘                       └──────────────────┘
                                                     │
                                                     ▼
                                            ┌──────────────────┐
                                            │ compliance DB    │
                                            │ + OPA + EDA      │
                                            └──────────────────┘
```

## Required collections

| Collection | Vendor | Availability | In our EE? | Version | Used for |
|---|---|---|---|---|---|
| `<namespace>.<collection>` | Red Hat / Partner / Community | Galaxy / Automation Hub / both | yes / no | x.y.z | what this collection does in this integration |

## Integration steps

Numbered, 6-12 steps. Each step has three parts:

### Step 1 — {short title}

1. **What:** the goal of this step in one sentence
2. **How:** the exact command / playbook / UI click sequence
3. **Verify:** how you know it worked (curl response, log line, DB row, UI checkmark)

### Step 2 — ...

(repeat)

## Playbooks

### Existing in the repo (reuse)

- `ansible/playbooks/{file}.yml` — one-line description of what it does for this integration

### New (to write)

- `integrations/{slug}/playbooks/{file}.yml` — proposed name + one-line description
- `integrations/{slug}/tasks/{file}.yml` — for OS- or vendor-specific task includes

## Credentials required

For each credential the integration needs:

- **AAP credential type:** Source Control / Machine / Custom / Container Registry / Vault
- **What it grants:** read API / write API / service account password
- **How to acquire:** UI link + steps the customer takes to mint one
- **Rotation cadence:** how often the customer needs to rotate this

## EDA rulebook bits

(Skip if this integration doesn't use EDA.)

- **Webhook port:** 5xxx (claim a port — see `extensions/eda/rulebooks/` for current bindings)
- **Source plugin:** which event source plugin to use (`ansible.eda.webhook`, `lab.eda.aac_portal_feed`, custom)
- **Routing rules:** which payload fields → which workflow

## Gotchas

Bullet list. Be specific:

- Auth quirks (basic vs OAuth vs mTLS; token vs service account; SAML quirks)
- Version pins (collection version that doesn't support feature X; vendor API version)
- Ordering (must create X before Y; must wait for sync)
- Idempotency traps (POST that always creates instead of upserting)
- Rate limits + back-off behavior
- Network requirements (must be reachable from EDA pod, not just AAP host)
- Common error messages + meaning

## Customer-engagement checklist

Before kickoff:
- [ ] Customer has provided {credential / endpoint / scope}
- [ ] Network path validated (firewall + DNS)
- [ ] Vendor-side service account has the right scopes

During implementation:
- [ ] Smoke test against customer's sandbox / dev environment
- [ ] {integration-specific validation}

Pre-cutover:
- [ ] Rollback plan documented
- [ ] On-call coverage during cutover
- [ ] Customer's runbook updated

## References

- {Vendor API documentation URL}
- {Certified collection documentation URL}
- Related entries: `../{other-slug}/` — cross-references where integrations interact
- Existing playbook patterns this draws from: `{repo path}`
