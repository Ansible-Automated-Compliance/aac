# xMatters

## At a glance

- **Customer system:** xMatters — on-call / alert routing platform with rudimentary workflow automation
- **AAC pattern:** push from AAC (event flow) + event-driven (xMatters → AAC inbound webhooks for acknowledgement-driven actions)
- **Status in AAC today:** ✗ greenfield — no code yet
- **Effort estimate:** TBD — pending write-up
- **Required collections:** none (custom REST integration; no published collection)
- **Customer-side prerequisites:** xMatters Inbound Integration URL + auth (token or basic); on-call group(s) mapped to the AAC compliance domains the customer cares about

## Customer use case (1-sentence summary)

AAC fires critical compliance violations (P1/P2 only) into xMatters so
the customer's on-call rotation gets paged via their existing channels
(phone, SMS, push). For some integrations, xMatters can also call back
into AAC to trigger a remediation workflow when an on-call engineer
acknowledges the page.

## Status

📝 **Pending full write-up.**

## Quick notes (for the eventual write-up)

- **Primary API:** xMatters Inbound Integration trigger URLs (per-integration).
  POST a JSON payload (the customer designs the shape; xMatters maps fields
  to recipients and rendering).
- **Closest existing pattern in the repo:** `ansible/playbooks/notify_servicenow_violations.yml`
  — query DB → POST to vendor endpoint. Same shape; xMatters payload is freeform JSON.
- **Bidirectional path:** xMatters can POST back to an EDA webhook on AAC when
  an engineer clicks "remediate" on the page. Use the existing
  `extensions/eda/rulebooks/lab10_itsm_ticket_handler.yml` as the pattern (port 5005
  already in use → claim a new port, e.g. 5006).
- **No Ansible Galaxy collection** for xMatters — use `ansible.builtin.uri`.
- **Filter early:** xMatters page volume is expensive (literally — per-page
  cost). Filter to severity=CRITICAL or KEV-listed CVEs only. Other lower
  severities should go through ServiceNow / BigPanda.

## See also

- [`../bigpanda/`](../bigpanda/) — alert aggregation typically goes BEFORE xMatters (BigPanda dedupes, then forwards the surviving signal to xMatters for paging)
- [`../_examples/servicenow_itsm.md`](../_examples/servicenow_itsm.md) — push-from-AAC pattern reference
- [`../_common/patterns.md`](../_common/patterns.md) — § 1 + § 2 (hybrid event-driven + push)
