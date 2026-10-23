#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_exchange_facts — collect Exchange Online state for CIS Section 4.

Covers the CIS Section 4 controls that are reachable via Graph
v1.0 + the public DNS surface for the tenant's verified domains:

  - 4.1.1 Mailbox auditing enabled tenant-wide
  - 4.5.1 SPF record present for every verified domain
  - 4.6.1 DKIM signing record present for every verified domain
  - 4.7.1 DMARC record present for every verified domain
  - 4.8.1 External email tagging (Defender for Office 365 setting)
  - 4.11.1 SMTP AUTH disabled at the tenant level

Controls that need Exchange Online PowerShell (e.g., transport
rules, anti-phishing policy detail) are out of scope for this
module — Graph doesn't expose them in v1.0. A future
m365_exchange_ps_facts module would cover them via the
ExchangeOnlineManagement PowerShell module behind a wrapper.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: m365_exchange_facts
short_description: Collect Exchange Online state for CIS Section 4 evaluation
description:
  - Authenticates to Microsoft Graph via Azure AD app registration
    (client credentials), pulls Exchange Online state, and emits
    flat JSON facts.
  - The companion Rego policies under
    C(policies/benchmarks/cis/saas/m365/) evaluate these facts.
options:
  tenant_id:
    description: Azure AD tenant GUID.
    required: true
    type: str
  client_id:
    description: Application (client) ID of the Azure AD app registration.
    required: true
    type: str
  client_secret:
    description: Client secret of the app registration.
    required: true
    type: str
    no_log: true
  timeout:
    description: HTTP timeout for Graph calls, seconds.
    type: int
    default: 30
  use_proxy:
    description:
      - Route Graph and token calls through the environment proxy
        (C(HTTPS_PROXY)/C(HTTP_PROXY)). Set C(false) to force a direct connection.
    type: bool
    default: true
  proxy:
    description:
      - Explicit proxy URL for Graph and token calls (e.g. C(http://proxy:8080)).
        Overrides the environment proxy when set.
    type: str
    required: false
  mailbox_sample_size:
    description:
      - Number of mailboxes to sample for the CIS 4.1.1 per-mailbox audit read
        (a single Graph page, not a full-directory enumeration).
      - This is a best-effort sample only. The B(authoritative) tenant-wide
        answer is C(Get-OrganizationConfig | AuditDisabled) in
        M(aac.m365.m365_exchange_ps_facts).
      - Supply per environment as needed (survey/extra_vars) rather than relying
        on the default.
    type: int
    default: 50
author:
  - "AAC maintainers"
"""

EXAMPLES = r"""
- name: Gather M365 Exchange state for CIS evaluation
  aac.m365.m365_exchange_facts:
    tenant_id: "{{ m365_tenant_id }}"
    client_id: "{{ m365_client_id }}"
    client_secret: >-
      {{ m365_client_secret }}
  register: exchange_facts

- name: POST to OPA for evaluation
  ansible.builtin.uri:
    url: "{{ opa_security_url }}/v1/data/cis_m365_v7/exchange/compliance_report"
    method: POST
    body_format: json
    body:
      input: "{{ exchange_facts.facts }}"
"""

RETURN = r"""
facts:
  description: M365 Exchange state shaped for CIS Rego evaluation.
  returned: always
  type: dict
  contains:
    verified_domains:
      description: Domains the tenant has verified; each carries DNS records.
      type: list
    mailbox_audit_summary:
      description: Aggregate of per-mailbox audit-enabled state.
      type: dict
    secure_score_controls:
      description: Microsoft Secure Score controls relevant to Exchange.
      type: list
    org_settings:
      description: Tenant-level Exchange-related organization settings.
      type: dict
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.aac.m365.plugins.module_utils.graph import (
    GraphClient,
    GraphError,
    fetch_secure_score_controls,
)


# Secure-Score control IDs that map to CIS Section 4 evidence. Graph
# returns dozens; we project just the ones the Rego cares about so
# the fact payload stays bounded.
_RELEVANT_SECURE_SCORE_CONTROLS = {
    "MFARegistrationV2",       # MFA coverage — useful cross-reference
    "ATPSafeLinks",            # 4.x — Defender for Office safe-links
    "ATPSafeAttachments",      # 4.x — Defender for Office safe-attachments
    "AntiPhishPolicy",         # 4.x — anti-phish settings
    "MailboxAuditEnabled",     # 4.1.1
    "SMTPAuthDisabled",        # 4.11.1
    "ExternalSenderTagging",   # 4.8.1
    "DKIMSigning",             # 4.6.1
}


def _classify_dns_records(records: list) -> dict:
    """Walk a domain's DNS record list and pick out SPF / DKIM /
    DMARC presence. Graph emits records as
    `{recordType, label, additionalProperties}`; SPF lives in a TXT
    record whose value starts with `v=spf1`, DMARC in a TXT at
    `_dmarc`, DKIM in CNAMEs at `selector1._domainkey` and
    `selector2._domainkey`."""
    spf_present = False
    dmarc_present = False
    dkim_present = False

    for r in records:
        label = (r.get("label") or "").lower()
        rtype = (r.get("recordType") or "").upper()
        text = (
            r.get("text")
            or r.get("additionalProperties", {}).get("text")
            or r.get("additionalProperties", {}).get("recordValue")
            or ""
        )
        if rtype == "TXT" and text.lower().startswith("v=spf1"):
            spf_present = True
        if rtype == "TXT" and label.startswith("_dmarc") and text.lower().startswith("v=dmarc1"):
            dmarc_present = True
        if rtype == "CNAME" and "_domainkey" in label:
            dkim_present = True

    return {
        "spf_present": spf_present,
        "dmarc_present": dmarc_present,
        "dkim_present": dkim_present,
    }


def collect_facts(client: GraphClient, mailbox_sample_size: int = 50) -> dict:
    """Pure function — Graph access via the injected client so the
    test suite can stub everything."""
    facts: dict = {}

    # ── 4.5.1 / 4.6.1 / 4.7.1 — DNS records on verified domains ────
    domains = client.get_all("/domains")
    verified: list = []
    for d in domains:
        if not d.get("isVerified"):
            continue
        domain_id = d.get("id")
        records: list = []
        dns_error = None
        try:
            records = client.get_all(
                f"/domains/{domain_id}/serviceConfigurationRecords"
            )
        except GraphError as e:
            # Store a SANITIZED short reason, not str(e) (which carries the raw
            # Graph response body) -- this is interpolated into the OPA
            # violation/report downstream.
            dns_error = GraphClient._reason(e)
        entry = {
            "id": domain_id,
            "is_default": bool(d.get("isDefault")),
            "is_initial": bool(d.get("isInitial")),
        }
        # A domain whose records could NOT be queried is marked
        # `dns_unavailable` so the policy reports it as not-evaluated rather
        # than reading a missing record as a definite violation. The
        # Microsoft-managed *initial* domain (…onmicrosoft.com) is excluded from
        # the SPF/DKIM/DMARC controls policy-side (defender_validation.rego skips
        # is_initial) -- the tenant cannot publish DNS for it -- so we never
        # fabricate DNS absence for an errored domain here.
        if dns_error is not None:
            entry["dns_unavailable"] = dns_error
        else:
            entry.update(_classify_dns_records(records))
        verified.append(entry)
    facts["verified_domains"] = verified

    # ── 4.1.1 — Mailbox auditing (best-effort per-mailbox sample) ────
    # The AUTHORITATIVE tenant-wide answer is `Get-OrganizationConfig |
    # AuditDisabled` in m365_exchange_ps_facts — that is the benchmark's
    # own audit procedure. Graph v1.0 exposes no tenant audit toggle, so
    # this collector contributes only a best-effort per-mailbox sample.
    # Use a single page (`get`, NOT `get_all`): a bounded sample of
    # `mailbox_sample_size` users (module option, default 50), never a
    # full-directory enumeration. `mailbox_audit_summary.evaluable` tells Rego
    # whether the sample yielded any readable audit state, and `sampled`
    # records how many mailboxes were actually asked.
    users = client.get(
        "/users",
        params={"$top": mailbox_sample_size, "$select": "id,userPrincipalName,assignedPlans"},
    ).get("value", [])
    audit_enabled_count = 0
    audit_disabled_count = 0
    sampled = 0
    for u in users:
        uid = u.get("id")
        if not uid:
            continue
        try:
            settings = client.get(f"/users/{uid}/mailboxSettings")
        except GraphError:
            # User without a mailbox (no Exchange license) — skip.
            continue
        sampled += 1
        # We count a mailbox only when /mailboxSettings actually
        # returns `mailboxAuditEnabled` — no silent approximation.
        # mailbox_audit_summary below records `sampled` (how many we
        # asked about) vs. enabled/disabled so Rego can be honest
        # about evaluable coverage vs. unknown for this tenant.
        if "mailboxAuditEnabled" in settings:
            if settings.get("mailboxAuditEnabled"):
                audit_enabled_count += 1
            else:
                audit_disabled_count += 1
    facts["mailbox_audit_summary"] = {
        "sampled": sampled,
        "audit_enabled": audit_enabled_count,
        "audit_disabled": audit_disabled_count,
        "evaluable": audit_enabled_count + audit_disabled_count > 0,
    }

    # ── Secure Score controls (cross-section evidence) ──────────────
    controls = fetch_secure_score_controls(client, _RELEVANT_SECURE_SCORE_CONTROLS)
    relevant: list = []
    for c in controls:
        cid = c.get("id") or c.get("controlName")
        if cid not in _RELEVANT_SECURE_SCORE_CONTROLS:
            continue
        relevant.append(
            {
                "id": cid,
                "name": c.get("title") or c.get("controlName"),
                "implementation_status": c.get("implementationStatus"),
                "max_score": c.get("maxScore"),
                "compliance_information": c.get("complianceInformation", []),
            }
        )
    facts["secure_score_controls"] = relevant

    # ── 4.11.1 / 4.8.1 — Tenant-level org settings ──────────────────
    # The closest Graph-v1.0 endpoint exposing tenant Exchange
    # settings is /organization. SMTP AUTH state isn't there; it's
    # admin-portal-only. We surface the org info so Rego can flag
    # "tenant-level settings not evaluable via Graph; see
    # operator-side runbook."
    try:
        org = client.get("/organization")
        org_value = org.get("value", [{}])[0] if "value" in org else org
    except GraphError:
        org_value = {}
    facts["org_settings"] = {
        "display_name": org_value.get("displayName"),
        "tenant_type": org_value.get("tenantType"),
        "verified_domain_count": len(facts["verified_domains"]),
    }

    return facts


def main() -> None:
    module = AnsibleModule(
        argument_spec=dict(
            tenant_id=dict(type="str", required=True),
            client_id=dict(type="str", required=True),
            client_secret=dict(type="str", required=True, no_log=True),
            timeout=dict(type="int", default=30),
            use_proxy=dict(type="bool", default=True),
            proxy=dict(type="str", required=False, default=None),
            mailbox_sample_size=dict(type="int", default=50),
        ),
        supports_check_mode=True,
    )

    if module.check_mode:
        module.exit_json(changed=False, facts={})

    try:
        client = GraphClient(
            tenant_id=module.params["tenant_id"],
            client_id=module.params["client_id"],
            client_secret=module.params["client_secret"],
            timeout=module.params["timeout"],
            use_proxy=module.params["use_proxy"],
            proxy=module.params["proxy"],
        )
        facts = collect_facts(
            client, mailbox_sample_size=module.params["mailbox_sample_size"]
        )
    except GraphError as exc:
        module.fail_json(
            msg=f"Microsoft Graph error: {exc.status} at {exc.request_path}",
            details=exc.body[:2000],
        )
        return

    module.exit_json(changed=False, facts=facts)


if __name__ == "__main__":
    main()
