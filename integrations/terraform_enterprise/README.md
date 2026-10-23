# Terraform Enterprise (HashiCorp TFE)

## At a glance

- **Customer system:** HashiCorp Terraform Enterprise (the self-hosted edition; same shape applies to Terraform Cloud)
- **AAC pattern:** hybrid — AAC triggers TFE runs (push) AND consumes TFE run-state webhooks (event-driven)
- **Status in AAC today:** ⚠ partial — `policies/enforcement/terraform/` Rego exists (Sentinel-style policy validation) but no TFE API integration playbook yet
- **Effort estimate:** TBD — pending write-up
- **Required collections:**
  - `cloud.terraform` v4.0.0 (Galaxy + Automation Hub certified) — preferred
  - or raw `uri` to `/api/v2` if customer doesn't want the collection
- **Customer-side prerequisites:** TFE org + team token with run-trigger + state-read scopes; the workspaces AAC interacts with named upfront

## Customer use case (1-sentence summary)

Customer's cloud infrastructure changes flow through TFE (with Sentinel
policies). AAC complements TFE by:
  (1) running a compliance assessment **after** every TFE apply (catches drift TFE didn't predict);
  (2) validating new Terraform code against AAC's Rego policies **before** the customer's CI merges (gate via PR check);
  (3) optionally triggering remediation TFE runs when AAC detects drift on TFE-managed resources.

## Status

📝 **Pending full write-up.**

## Quick notes (for the eventual write-up)

- **Primary API:** TFE/TFC REST API at `https://<tfe-host>/api/v2/`
- **Auth:** Team tokens (preferred for AAC service identity) or User tokens for ad-hoc work
- **`cloud.terraform` modules of interest:**
  - `cloud.terraform.terraform_workspace` (manage workspaces)
  - `cloud.terraform.terraform_run` (trigger plan / apply runs)
  - `cloud.terraform.terraform_state` (read state for post-apply compliance checks)
- **Existing repo overlap:** `policies/enforcement/terraform/` has Rego policies that validate Terraform plan JSON. The AAC Sentinel demo
  (`extensions/eda/rulebooks/sentinel_github_webhook.yml`) already wraps these. Wiring the SAME validation into TFE's pre-apply hook is the missing piece.
- **Policy-as-code synergy:** TFE has Sentinel (paid) for policy gating. AAC's OPA is a free overlay — most customers run both, with overlapping concerns. The integration write-up should clarify the boundary.
- **Webhook → AAC:** TFE supports run notification configurations. POST to AAC EDA webhook (claim port 5007) when a run completes; AAC re-assesses affected resources.

## See also

- [`../kubernetes_capi/`](../kubernetes_capi/) — many customers do cloud K8s via TFE → CAPI; integration sequence matters
- [`../aws_ssm/`](../aws_ssm/) — TFE provisions EC2; AAC uses SSM to manage compliance on those EC2s
- `policies/enforcement/terraform/` — existing Rego policies for Terraform plan validation
- [`../_common/patterns.md`](../_common/patterns.md) — § 1 + § 2 hybrid pattern
