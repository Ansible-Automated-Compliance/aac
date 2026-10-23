# BigPanda

## At a glance

- **Customer system:** BigPanda — alert correlation / aggregation platform
- **AAC pattern:** **bidirectional** — EDA event source (BigPanda → AAP) **and** push from AAP (AAP → BigPanda)
- **Status in AAC today:** ✗ greenfield — no code yet
- **Effort estimate:** ~3 person-days for the push half (state sync / alert enrichment / resolution); +3 days for the EDA inbound half (BigPanda webhook → AAP workflow)
- **Required collection:** **`bigpanda.incident`** (certified, on Automation Hub) — ships **both** the outbound modules **and** an EDA event-source plugin for BigPanda webhooks
- **Customer-side prerequisites:** BigPanda integration source key for the AAC integration; downstream (PagerDuty / ServiceNow / Slack) already wired into BigPanda is the typical setup

## Customer use case (1-sentence summary)

AAC and BigPanda close the loop in both directions: AAC pushes
compliance violations + drift events into BigPanda for correlation
with the customer's existing monitoring stack (Splunk / Datadog /
Nagios / etc.), and AAP's EDA listens to BigPanda webhooks so that a
correlated incident in BigPanda can trigger remediation workflows in
AAP without a human in the loop. The same certified collection
(`bigpanda.incident`) carries both directions.

## How it works end-to-end (Pete's note, 2026-06-02)

> "BigPanda integration with AAP leverages EDA via webhooks for
> inbound automation, and the same collection's push capabilities let
> AAP update BigPanda on state, alert enrichment, and resolution."
>
> Pete Cruz, 2026-06-02 — see also <https://docs.bigpanda.io/en/ansible-automation-platform>

The architecture is symmetric:

```
                         ┌──────────────────────────┐
                         │ BigPanda                  │
   correlated incident ──┼──────────────────────┐    │
   webhook (inbound)     │                      │    │
                         └──────────────────────│────┘
                                                │
                                  ┌─────────────▼─────────────┐
                                  │ AAP — EDA rulebook         │
                                  │  source: bigpanda.incident │
                                  │          .alert_handler    │
                                  │  rules: launch playbook on │
                                  │         specific events    │
                                  └──────────────┬─────────────┘
                                                 │ trigger workflow
                                  ┌──────────────▼─────────────┐
                                  │ AAP — remediation playbook │
                                  │ (uses bigpanda.incident    │
                                  │  module to enrich /        │
                                  │  resolve / update state)   │
                                  └──────────────┬─────────────┘
                                                 │ push update
                         ┌──────────────────────│────┐
                         │ BigPanda              │    │
                         │  incident closed /   ◄┘    │
                         │  enriched / annotated      │
                         └──────────────────────────┘
```

The customer gets a self-healing loop: BigPanda detects a correlated
problem → AAP fixes it → AAP tells BigPanda the incident is resolved
+ attaches the remediation evidence to the incident record.

## Required collection

**`bigpanda.incident`** — Red Hat–certified partner collection,
published in Automation Hub:
<https://console.redhat.com/ansible/automation-hub/collections/published/bigpanda/incident/details>

Add to the engagement Execution Environment's `requirements.yml`:

```yaml
collections:
  - name: bigpanda.incident
    source: https://console.redhat.com/api/automation-hub/content/published/
```

The EE must be built with the Automation Hub token attached so
`ansible-builder` can pull the collection.

> **Why use the certified collection instead of raw `uri`?**
> The collection ships documented modules with parameter validation,
> idempotency, and structured error handling. `uri`-based integrations
> work for a one-shot demo but accumulate hand-written retry, payload-
> shape, and error-mapping code over time. The certified collection
> is the maintained path.

## Customer-engagement steps

1. **Confirm Automation Hub access.** The customer needs an active AAP
   subscription with Automation Hub entitlement so the certified
   collection can be pulled into their EE. If they're on Galaxy-only,
   negotiate adding AH access or fall back to the `uri`-based
   integration documented under "Fallback" below.
2. **Provision BigPanda integration source.** In BigPanda, create
   an "AAC Compliance" integration source. Capture the source key
   and the API access token. Store both as Ansible vault variables
   in `vars/vault_secrets.yml`: `vault_bigpanda_app_key` and
   `vault_bigpanda_api_token`.
3. **Build / update the engagement EE.** Add `bigpanda.incident` to
   `requirements.yml`; rebuild and push (e.g. via AAP template "AAC -
   Build Compliance EE" or `ansible-builder build` locally).
4. **Wire the AAP credential.** Create a custom AAP credential type
   for BigPanda holding the API token; attach to the relevant job
   templates.
5. **Author the notification playbook.** New playbook at
   `ansible/playbooks/notify_bigpanda_violations.yml` modeled on
   `notify_servicenow_violations.yml` — query the latest
   `compliance_results` for failed controls, post to BigPanda using
   `bigpanda.incident.incident`.
6. **Wire as an AAP workflow failure node** (and / or as a recurring
   "open incidents for current violations" schedule). The choice
   depends on whether the customer wants alert-on-failure or
   continuous-state-sync semantics.
7. **(Optional) Closed-loop ack.** Wire an EDA rulebook to
   BigPanda's webhook so an operator's *ack* in BigPanda flips the
   matching `tenant_cve_matches` row to `acknowledged_at` (only
   relevant if running the CVE Intelligence portal alongside AAC).
8. **Smoke test.** Apply a deliberate violation (e.g. introduce SSH
   drift via Golden Image template `IntroduceDrift`), confirm the
   BigPanda incident lands and routes through correlation rules
   to the downstream pager.

### EDA inbound — BigPanda → AAP (the second half of the loop)

The `bigpanda.incident` collection includes an **EDA event-source
plugin** that listens for BigPanda webhook payloads. With this
direction wired up, a BigPanda incident can launch an AAP workflow.

9. **Configure BigPanda outbound webhook integration.** In BigPanda,
   set up an outbound integration that POSTs incident lifecycle events
   to a URL on the customer's EDA controller. Common triggers: incident
   created, severity changed, manually-tagged "auto-remediate".
10. **Create an EDA decision environment with the collection.** The
    collection ships an event-source plugin (typically
    `bigpanda.incident.alert_handler` or similar — verify against the
    upstream docs at <https://docs.bigpanda.io/en/ansible-automation-platform>).
11. **Author the EDA rulebook.** Listens on the webhook port, parses
    the BigPanda payload, and launches an AAP workflow conditional on
    the incident's source, severity, or operator-supplied tag.
    Example skeleton:

    ```yaml
    - name: BigPanda incident → AAP remediation
      sources:
        - bigpanda.incident.alert_handler:
            host: 0.0.0.0
            port: 5005
            token: "{{ EDA_WEBHOOK_TOKEN }}"
      rules:
        - name: Auto-remediate compliance drift
          condition: >-
            event.source == "AAC Compliance" and
            event.tags | select("auto_remediate") | length > 0
          action:
            run_workflow_template:
              name: "AAC - Compliance Drift Remediation"
              organization: Default
              job_args:
                hostname: "{{ event.host }}"
                framework: "{{ event.check }}"
    ```

12. **Wire the remediation workflow to acknowledge / resolve in
    BigPanda on completion.** On workflow success, run
    `bigpanda.incident.incident` with `state: absent` (or the
    upstream collection's `resolve` action — confirm the exact module
    name at integration time) and attach the remediation evidence.
13. **End-to-end test.** Trigger a fault that BigPanda will correlate
    into an incident; confirm the EDA rulebook fires, the workflow
    runs, and the incident is updated with evidence + closed in
    BigPanda within the customer's expected SLA.

## Sample task (using the certified collection)

```yaml
- name: Open BigPanda incident for a failed control
  bigpanda.incident.incident:
    api_token: "{{ vault_bigpanda_api_token }}"
    component: "{{ item.hostname }}"
    description: >-
      AAC {{ item.framework }} compliance failed —
      {{ item.failed_controls }} control(s) failing.
      Latest run {{ item.evaluation_timestamp }}.
    severity: "{{ 'high' if item.compliance_percentage < 80 else 'warning' }}"
    state: present
    primary_property: component
  loop: "{{ failed_results }}"
  loop_control:
    label: "{{ item.hostname }} / {{ item.framework }}"
```

`failed_results` would be the output of a `community.postgresql.postgresql_query`
selecting recent failing rows from `compliance_results`.

## Fallback — `uri`-based push (only if Automation Hub access unavailable)

A reusable task an Ansible job can call to send an alert via raw
HTTP. Often wired in as the **workflow's failure node**.

```yaml
- name: Notify BigPanda of failed AAP job (uri fallback)
  ansible.builtin.uri:
    url: "https://api.bigpanda.io/data/v2/alerts"
    method: POST
    headers:
      Authorization: "Bearer {{ vault_bigpanda_api_token }}"
      Content-Type: "application/json"
    body_format: json
    body:
      app_key: >-
        {{ vault_bigpanda_integration_source_key }}
      status: critical
      host: "{{ awx_host | default('aac-controller') }}"
      check: "AAP job: {{ awx_job_template_name }}"
      incident_identifier: "aap-{{ awx_job_id }}"
      description: >-
        AAP job failed on {{ ansible_date_time.iso8601 }}
```

Prefer the certified collection above; this fallback exists only for
customers without Automation Hub.

## Gotchas

- **Severity mapping:** BigPanda uses `critical / high / warning / info`;
  AAC uses `critical / high / medium / low`. Decide on the mapping
  with the customer's SecOps team before go-live.
- **Component naming:** BigPanda dedupes on the `component` field. If
  AAC fires one alert per `(hostname, framework)` pair and BigPanda
  groups on just `hostname`, multi-framework alerts collapse into a
  single incident. Recommended: use `"{{ hostname }} :: {{ framework }}"`
  to separate.
- **Auto-resolve:** BigPanda will not auto-resolve incidents based on
  AAC re-runs unless AAC explicitly POSTs `state: absent` (or `status:
  ok` in the raw API). The notification playbook should query the
  previous run's failures and resolve any not present in the current
  run.
- **Webhook payload (closed-loop):** BigPanda's outgoing webhooks have
  a fixed shape that does not include arbitrary metadata. The EDA
  rulebook needs to look up `tenant_cve_matches` / `compliance_results`
  on `component` to find the matching internal record.
- **Rate limits:** BigPanda alerts API allows ~100 req/sec per source.
  For large initial syncs, batch into groups of 50 per request.

## Closest existing pattern in the repo

`ansible/playbooks/notify_servicenow_violations.yml` — query DB →
POST to vendor API. Same shape; substitute the BigPanda module.

## See also

- [`../_examples/servicenow_itsm.md`](../_examples/servicenow_itsm.md) — closest fully-worked example (push-from-AAC to a vendor REST API)
- [`../_common/patterns.md`](../_common/patterns.md) — §2 "Push from AAC"
- [`../_common/certified_collections.md`](../_common/certified_collections.md) — `bigpanda.incident` listed under "Vendor partner collections on Automation Hub (certified)"
