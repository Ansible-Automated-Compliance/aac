# AAC Integrations

This folder is the home for customer-facing integration documentation
and per-integration code (playbooks, tasks, EDA rulebooks that don't
belong elsewhere in the repo).

### 📖 Start here

Want a single-document tour of all 7 integrations with sample code +
use cases? Read **[`OVERVIEW.md`](OVERVIEW.md)** — it covers every
integration in this folder in one place. Use it for customer scoping
calls, internal briefings, or as the on-ramp before diving into
per-integration folders.

---

Each integration gets its own folder under `integrations/<slug>/` with a
consistent structure so a partner SE or AAC engineer can pick one up
and scope the work for a specific customer.

---

## How to use this folder

### I'm scoping a new customer engagement

1. Read [`_common/discovery_checklist.md`](_common/discovery_checklist.md) to figure out which integrations the customer needs.
2. For each one, read `integrations/<slug>/README.md` for steps, gotchas, effort, and the certified collection to reach for.
3. Copy the per-integration write-up into your customer-engagement doc and customize.

### I'm adding a new integration write-up

1. Copy the template:
   ```bash
   cp integrations/_template/INTEGRATION_TEMPLATE.md integrations/<slug>/README.md
   ```
2. Find the closest existing pattern in the repo (see the table in `_common/patterns.md`) and use it as a starting point.
3. Fill in: status, customer use case, architecture diagram, integration steps, playbooks, gotchas, effort estimate.
4. Cross-check the Galaxy + Automation Hub status of any new collection in `_common/certified_collections.md`.
5. Open a PR.

### I'm a customer running an engagement

The `notes/` subfolder in each integration is **gitignored** — drop your customer-specific config there. The committed `README.md` is the archetype; your `notes/` are the per-customer customizations.

---

## Integration index

Status badges:
- ✓ proven — fully working in the AAC repo today
- 🟡 in progress — write-up exists, code partially landed
- ⚠ partial — stub code in repo, full write-up not yet
- ✗ greenfield — no code yet, write-up is the scoping reference
- 📝 pending write-up — listed but not documented yet

### Currently documented

| Integration | Status | Pattern | Folder |
|---|---|---|---|
| ServiceNow ITSM | ✓ proven | push + event-driven | [`_examples/servicenow_itsm.md`](_examples/servicenow_itsm.md) |
| EnforceAuth | 🟡 in progress | pull from AAC (compliance state → runtime authz) | [`enforceauth/`](enforceauth/) |

### Planned (customer engagement queue)

| Integration | Vendor | Use case | Folder |
|---|---|---|---|
| BigPanda | BigPanda | Alert aggregation / correlation | [`bigpanda/`](bigpanda/) |
| xMatters | xMatters | Alert-driven automation, on-call routing | [`xmatters/`](xmatters/) |
| Terraform Enterprise | HashiCorp | IaC for cloud deployments | [`terraform_enterprise/`](terraform_enterprise/) |
| HashiCorp Vault Enterprise | HashiCorp | Centralized secrets (already used by AWX) | [`hashicorp_vault_enterprise/`](hashicorp_vault_enterprise/) |
| Kubernetes CAPI | CNCF | Declarative cluster provisioning | [`kubernetes_capi/`](kubernetes_capi/) |
| Metal3 / Ironic | Metal3 (CNCF) | Bare-metal provisioning | [`metal3_ironic/`](metal3_ironic/) |
| AWS SSM | AWS | EC2 management without SSH | [`aws_ssm/`](aws_ssm/) |

---

## The three AAC integration patterns

(See [`_common/patterns.md`](_common/patterns.md) for the full description with ASCII diagrams.)

1. **Event-driven** — EDA rulebook listens for an event → triggers AAP workflow
2. **Push from AAC** — AAP job calls an external API (e.g. create ServiceNow incident)
3. **Pull from AAC** — external system queries AAC's compliance DB or OPA endpoints

Most enterprise integrations are a hybrid of patterns 1 and 2.

---

## Folder layout

```
integrations/
├── README.md                      ← you are here
├── _template/                     ← copy this when starting a new integration
│   └── INTEGRATION_TEMPLATE.md
├── _common/                       ← shared reference material
│   ├── patterns.md
│   ├── discovery_checklist.md
│   └── certified_collections.md
├── _examples/                     ← gold-standard reference write-ups
│   └── servicenow_itsm.md
└── <integration-slug>/
    ├── README.md                  ← THE write-up
    ├── playbooks/                 ← integration-specific playbooks (optional)
    ├── tasks/                     ← integration-specific task includes (optional)
    └── notes/                     ← per-customer notes (gitignored)
```
