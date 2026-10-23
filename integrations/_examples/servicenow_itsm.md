# ServiceNow ITSM

> Gold-standard reference. This is what a finished `integrations/<slug>/README.md`
> looks like. Use the template at `_template/INTEGRATION_TEMPLATE.md` to start
> a new one and aim for this depth.

## At a glance

- **Customer system:** ServiceNow (Now Platform — ITSM module)
- **AAC pattern:** push from AAC + event-driven (bidirectional)
- **Status in AAC today:** ✓ proven — fully working playbook + EDA handler
- **Effort estimate:** 1–2 person-days for a fresh customer install (most time is collecting customer-side scope: assignment group, custom fields, sandbox creds)
- **Required collections:**
  - `servicenow.itsm` v2.14.0 (Galaxy + Automation Hub certified) — preferred for new work
  - The existing playbook uses raw `uri` calls (no collection dep) — also fine for customers without AH entitlement
- **Customer-side prerequisites:**
  - ServiceNow instance URL (e.g. `acme.service-now.com`)
  - Service account with `itil` + `web_service_admin` roles
  - Sandbox / dev instance for testing
  - Custom incident fields (optional): `u_compliance_framework`, `u_compliance_score`, `u_aac_assessment_timestamp`

## Customer use case

AAC pushes compliance violations into ServiceNow as incidents so the
customer's existing ITSM process (assignment, on-call rotation, SLA
clock, closure workflow) drives remediation. Compliance-only tooling
without ITSM hand-off is a non-starter at every enterprise customer —
audit teams require the ticket trail.

The bidirectional half: when a ServiceNow change request closes
("change implemented"), an EDA-driven handler can fire a re-assessment
to validate the change actually moved compliance forward.

## Architecture / data flow

```
   ┌─────────────────┐                                    ┌──────────────────────┐
   │ Compliance      │  (1) SELECT non-compliant          │ AAC + AAP 2.6        │
   │ assessment      │      results                       │                      │
   │ runs            │  ────────────────────────────────► │ AAP job:             │
   └─────────────────┘                                    │ "AAC - Notify SNOW   │
                                                          │  Violations"         │
                                                          │                      │
                                                          │ Playbook:            │
                                                          │ notify_servicenow_   │
                                                          │ violations.yml       │
                                                          └──────────┬───────────┘
                                                                     │
                                                                     │ (2) GET /api/now/table/incident
                                                                     │     ?active=true&u_hostname=<host>
                                                                     │     &u_compliance_framework=<fw>
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ ServiceNow           │
                                                          │ /api/now/table/      │
                                                          │ incident             │
                                                          │                      │
                                                          │ (3) POST new         │
                                                          │     incident if      │
                                                          │     none open        │
                                                          └──────────┬───────────┘
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ ITSM assignment +    │
                                                          │ remediation flow    │
                                                          └──────────────────────┘

   (Event-driven half — when change request closes)
   ┌──────────────────────┐  webhook   ┌──────────────────────┐  trigger    ┌──────────────────────┐
   │ ServiceNow Business  │ ────────► │ EDA rulebook         │ ──────────► │ AAP workflow:        │
   │ Rule on CHG closure  │ /endpoint  │ lab10_itsm_ticket_   │             │ re-assess affected   │
   │                      │            │ handler.yml          │             │ host                 │
   └──────────────────────┘            └──────────────────────┘             └──────────────────────┘
```

## Required collections

| Collection | Vendor | Availability | In our EE? | Version | Used for |
|---|---|---|---|---|---|
| `servicenow.itsm` | Red Hat (partner) | Galaxy + Automation Hub | no (could be added) | 2.14.0 | declarative incident / change / problem record mgmt (preferred for new code) |
| `community.postgresql` | Community | Galaxy + Automation Hub | yes (3.0+) | 4.2.0 | reading non-compliant results from AAC's compliance DB |
| `ansible.builtin.uri` | Red Hat | n/a (core) | yes | bundled | raw REST calls — used by the existing playbook |

The existing playbook (`ansible/playbooks/notify_servicenow_violations.yml`)
doesn't use `servicenow.itsm`; it uses `uri` directly. Both work. For a
greenfield customer install we recommend `servicenow.itsm` because of the
better idempotency primitives — but the `uri` path is fine if the customer
doesn't have Automation Hub entitlement.

## Integration steps

### Step 1 — Create the ServiceNow service account

1. **What:** A dedicated account for AAC, separate from human users
2. **How:**
   - ServiceNow UI → **User Administration → Users → New**
   - Username: `aac_compliance_svc`
   - Type: **Web service access only**
   - Roles: `itil`, `web_service_admin`
   - (Optional but recommended) Roles: `change_manager` if AAC will also create change requests
3. **Verify:** Log in to ServiceNow with the account at `/api/now/table/incident?sysparm_limit=1` — should return one record, not 401

### Step 2 — Optional: Add custom incident fields

1. **What:** Track which framework / score triggered each incident
2. **How:**
   - **System Definition → Tables → incident**
   - Add string field `u_compliance_framework` (length 40)
   - Add integer field `u_compliance_score`
   - Add date/time field `u_aac_assessment_timestamp`
   - Add to the incident form layout if you want them user-visible
3. **Verify:** GET `/api/now/table/incident?sysparm_fields=u_compliance_framework` returns 200 (not 400 "invalid field")

### Step 3 — Store ServiceNow creds in the AAC vault

1. **What:** Vault the SNOW credentials so playbooks can use them
2. **How:** Add to the customer's `ansible/vars/vault_secrets.yml`:
   ```yaml
   vault_snow_instance: acme.service-now.com
   vault_snow_username: aac_compliance_svc
   # vault_snow_password — paste the value from ServiceNow on the line below
   vault_snow_password: REPLACE_WITH_SNOW_SERVICE_ACCOUNT_VALUE
   ```
   For production: use HashiCorp Vault or CyberArk instead of plaintext (see `integrations/hashicorp_vault_enterprise/`).
3. **Verify:** Run `grep snow ansible/vars/vault_secrets.yml` — three lines come back.

### Step 4 — Run the existing playbook against sandbox

1. **What:** Smoke-test before pointing at production ServiceNow
2. **How:**
   ```bash
   ansible-playbook ansible/playbooks/notify_servicenow_violations.yml \
       -e "snow_instance=${vault_snow_instance}" \
       -e "snow_username=${vault_snow_username}" \
       -e "snow_password=${vault_snow_password}" \
       -e "framework=cis_rhel9" \
       -e "critical_pct=75"
   ```
3. **Verify:** ServiceNow incident list shows N new incidents in `New` state with `u_compliance_framework=cis_rhel9`

### Step 5 — Wire into AAP as a job template

1. **What:** Make this runnable from the AAP UI on a schedule
2. **How:**
   - AAP UI → **Templates → Add → Job Template**
   - Name: `AAC - Notify ServiceNow Violations`
   - Job Type: `Run`
   - Inventory: `Compliance Infrastructure`
   - Project: `AAC Compliance`
   - Playbook: `ansible/playbooks/notify_servicenow_violations.yml`
   - Credentials: `Ansible Vault`
   - Survey vars: `framework`, `critical_pct`, `warning_pct`, `assignment_group`, `category` (see playbook header)
3. **Verify:** Launch from UI with `framework=cis_rhel9` — completes successful in <60s; SNOW incident appears

### Step 6 — Chain off compliance assessments

1. **What:** Auto-fire after every compliance assessment so a fresh fail = a fresh ticket
2. **How:** Add this template to existing workflows (e.g. `AAC_NERC_FullAudit`, the CIS workflows) as a follow-up node on **on-failure** AND **on-success** (so closed-and-re-broken still fires)
3. **Verify:** Force a CIS RHEL 9 host into non-compliance (turn off auditd), run the CIS workflow — incident appears within 2 minutes

### Step 7 — (Optional) Wire the ServiceNow → AAC reverse direction

1. **What:** When the customer closes a change request, re-validate compliance
2. **How:**
   - ServiceNow side: Business Rule on `change_request` table `state == Closed` → POST to AAC's EDA webhook (`http://<aap-host>:5005/endpoint`)
   - AAC side: enable `extensions/eda/rulebooks/lab10_itsm_ticket_handler.yml` (already exists)
   - Update the rulebook to route `change_request` payloads to a re-assessment template
3. **Verify:** Close a change in SNOW, watch EDA activation log show the inbound webhook, then watch the re-assessment job kick off

## Playbooks

### Existing in the repo (reuse)

- `ansible/playbooks/notify_servicenow_violations.yml` — the working ServiceNow incident creator. 200+ lines. Reads non-compliant rows from compliance DB, checks SNOW for open incidents per (hostname, framework) tuple, creates new incident with severity mapped from compliance score.
- `extensions/eda/rulebooks/lab10_itsm_ticket_handler.yml` — generic ITSM webhook receiver on port 5005. Already covers ServiceNow's change-request closure payload shape.
- `demos/windows_golden_image/playbooks/windows_golden_notify_helpdesk.yml` — companion pattern that writes to a Postgres `helpdesk_tickets` table when SNOW isn't available (used in the Windows Golden Image demo).

### New (to write — per customer)

Typically none, but customer-specific add-ons land at:
- `integrations/servicenow_itsm/playbooks/snow_change_request.yml` — if the customer wants AAC to file change requests (not just incidents) for sanctioned remediations
- `integrations/servicenow_itsm/playbooks/snow_cmdb_sync.yml` — pull host metadata from SNOW CMDB before assessment (bidirectional CMDB sync — known gap today)

## Credentials required

| Credential | AAP type | How to acquire | Rotation |
|---|---|---|---|
| ServiceNow service account password | **Machine** (or **Custom** with `snow_username` + `snow_password` fields) | Customer's SNOW admin creates the user (Step 1 above) | Every 90 days per the customer's policy; rotate in vault + AAP credential |
| AAC Postgres password (already exists) | **Vault** (credential 8) | Provisioned during AAC install | Rotated via `ansible/playbooks/rotation_postgres.yml` |

## EDA rulebook bits

- **Webhook port:** 5005 (`lab10_itsm_ticket_handler.yml`)
- **Source plugin:** `ansible.eda.webhook`
- **Payload contract:** ServiceNow Business Rule sends `{table, sys_id, state, u_compliance_framework, u_hostname}` — handler routes to the right re-assessment workflow

## Gotchas

- **`u_compliance_framework` length** — ServiceNow defaults string fields to 40 chars. If a framework key like `sentinel_kubernetes_admission_controller` exceeds it, the POST returns 400 with an opaque message. Bump the field length to 100 during Step 2.
- **`SOAP Authentication failed`** — almost always a typo'd password or missing `web_service_admin` role. Test with `curl -u user:pass https://<inst>/api/now/table/incident?sysparm_limit=1`.
- **Idempotency by hostname + framework only** — the existing playbook treats "same host, same framework, any open incident" as already-handled. If the customer wants per-policy granularity (e.g. one incident per CIS section), add `u_policy_name` to the existing-incident lookup.
- **`Severity` ≠ `Priority`** — ServiceNow has both. AAC maps compliance score → severity (1-4). Priority is derived by SNOW workflow from severity + impact, which is customer-side. Don't try to set both.
- **Sandbox URL changes** — many customers reset their dev/test instances weekly. Add a "is the URL still valid?" preflight before customer demos.
- **API rate limit** — ServiceNow defaults to 10,000 transactions/hour per service account. AAC's batch (~100 hosts × ~20 frameworks = 2000 lookups + 2000 creates worst-case) fits well under this. If the customer has heavier compliance volume, batch or throttle.
- **No upsert in SNOW Table API** — the existing playbook does the right thing: GET-then-POST. Don't blindly POST; you'll spam incidents on every run.

## Customer-engagement checklist

Before kickoff:
- [ ] Customer's SNOW admin has created the `aac_compliance_svc` service account
- [ ] Sandbox / dev SNOW URL provided + reachable from the AAP host (test with `curl`)
- [ ] Custom `u_compliance_*` fields added (if customer wants them)
- [ ] Assignment group named (default `IT Security` may not exist in customer's instance)

During implementation:
- [ ] Sandbox smoke test: run notify playbook against sandbox SNOW with `framework=cis_rhel9` (or whatever's relevant to customer's first compliance scope)
- [ ] Confirm incidents land in the right assignment group
- [ ] Confirm custom fields are populated
- [ ] Confirm the second-run idempotency check works (same conditions → no duplicate incidents)

Pre-cutover:
- [ ] Customer's on-call team is briefed (incidents will start landing automatically)
- [ ] Initial volume estimate communicated (customer's IT Service Desk leadership wants to know if 500 incidents are about to arrive)
- [ ] Rollback: disable the workflow node, or set `framework=__none__` to no-op the playbook

## References

- ServiceNow Table API: https://docs.servicenow.com/bundle/utah-application-development/page/integrate/inbound-rest/concept/c_TableAPI.html
- `servicenow.itsm` collection: https://galaxy.ansible.com/ui/repo/published/servicenow/itsm/
- Existing playbook: `ansible/playbooks/notify_servicenow_violations.yml`
- Companion (Postgres-table fallback): `demos/windows_golden_image/playbooks/windows_golden_notify_helpdesk.yml`
- EDA receiver: `extensions/eda/rulebooks/lab10_itsm_ticket_handler.yml`
- Pattern reference: `integrations/_common/patterns.md` § 2 (Push from AAC) + § 1 (Event-driven)
