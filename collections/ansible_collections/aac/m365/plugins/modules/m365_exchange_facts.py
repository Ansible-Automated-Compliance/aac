#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_exchange_facts — collect Exchange Online state for CIS Section 4.

Covers the CIS controls that are reachable via Graph v1.0 plus the
published DNS records of the tenant's verified domains (SPF, DKIM and
DMARC are CIS v7.0.0 2.1.8-2.1.10; the 4.x numbers below are the pre-v7
ones this module was written against):

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
  dns_timeout:
    description:
      - Seconds allowed for each published-DNS lookup (SPF, DKIM, DMARC).
      - Lookups use the execution environment's own resolver configuration.
        They need the dnspython library; without it every customer domain is
        reported C(dns_unavailable) (evidence missing), never compliant.
    type: float
    default: 5.0
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
      description:
        - Domains the tenant has verified. Each customer (non-initial) domain
          carries C(spf_present), C(dkim_present) and C(dmarc_present) read
          from the records actually published in DNS, or C(dns_unavailable)
          with the reason they could not be read.
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


# ── Published DNS (2.1.8 SPF, 2.1.9 DKIM, 2.1.10 DMARC) ───────────────
#
# These controls are about what a receiving mail server sees, so the
# evidence is the record PUBLISHED in DNS. Graph's
# /domains/{id}/serviceConfigurationRecords is the list of records
# Microsoft says the domain SHOULD publish: it always contains the SPF TXT
# for a mail-enabled domain, so reading it made 2.1.8 pass whether or not
# the record exists.
#
# NXDOMAIN / no answer is a definite "not published". Anything else -- a
# timeout, SERVFAIL, no reachable name server, or no DNS library -- is
# "could not be read", which the policy reports as not evaluated.

try:
    import dns.exception
    import dns.resolver
    HAS_DNSPYTHON = True
except ImportError:  # pragma: no cover - depends on the EE
    HAS_DNSPYTHON = False

DNS_LIBRARY_MISSING = (
    "evidence missing: DNS lookup not available -- the dnspython library is "
    "not installed in this execution environment, so the published SPF, DKIM "
    "and DMARC records could not be read"
)

# Exchange Online signs with one of two rotating selectors, each published
# as a CNAME at selectorN._domainkey.<domain>.
DKIM_SELECTORS = ("selector1", "selector2")


class DnsLookupError(Exception):
    """A lookup that neither found the record nor proved it absent."""


class DnsResolver:
    """Thin wrapper over dnspython, injectable for tests.

    query(name, rtype) returns a list of strings -- the joined TXT strings or
    the CNAME targets -- and [] when the name or record does not exist. It
    raises DnsLookupError when the answer could not be obtained.
    """

    def __init__(self, timeout=5.0):
        self._resolver = dns.resolver.Resolver()
        self._resolver.lifetime = float(timeout)
        self._resolver.timeout = float(timeout)

    def query(self, name, rtype):
        try:
            answer = self._resolver.resolve(name, rtype)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return []
        except dns.exception.Timeout:
            raise DnsLookupError("DNS lookup for %s %s timed out" % (rtype, name))
        except dns.resolver.NoNameservers:
            raise DnsLookupError("no name server answered for %s %s" % (rtype, name))
        except dns.exception.DNSException as exc:
            raise DnsLookupError("DNS lookup for %s %s failed: %s"
                                 % (rtype, name, type(exc).__name__))
        out = []
        for rdata in answer:
            if rtype == "TXT":
                out.append(b"".join(rdata.strings).decode("utf-8", "replace"))
            else:
                out.append(str(getattr(rdata, "target", rdata)))
        return out


def published_mail_auth(domain, resolver):
    """Return the policy's {spf,dkim,dmarc}_present for one domain from
    published DNS, or {"dns_unavailable": reason}."""
    try:
        txt = resolver.query(domain, "TXT")
        dmarc = resolver.query("_dmarc." + domain, "TXT")
        dkim = [resolver.query("%s._domainkey.%s" % (sel, domain), "CNAME")
                for sel in DKIM_SELECTORS]
    except DnsLookupError as exc:
        return {"dns_unavailable": "evidence missing: %s" % exc}
    return {
        "spf_present": any(t.strip().lower().startswith("v=spf1") for t in txt),
        "dmarc_present": any(t.strip().lower().startswith("v=dmarc1") for t in dmarc),
        "dkim_present": any(bool(rows) for rows in dkim),
        "dns_source": "published_dns",
    }


def _classify_dns_records(records: list) -> dict:
    """Walk a domain's DNS record list and pick out SPF / DKIM /
    DMARC presence. Graph emits records as
    `{recordType, label, additionalProperties}`; SPF lives in a TXT
    record whose value starts with `v=spf1`, DMARC in a TXT at
    `_dmarc`, DKIM in CNAMEs at `selector1._domainkey` and
    `selector2._domainkey`.

    NOT used for the verdict any more: these are the records Microsoft
    requires, not the ones published (see published_mail_auth). Kept for
    reference by the unit tests of the classification itself."""
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


def collect_facts(client: GraphClient, mailbox_sample_size: int = 50,
                  resolver=None, dns_error=None) -> dict:
    """Pure function — Graph access via the injected client and DNS via the
    injected resolver, so the test suite can stub everything.

    `dns_error`, when set, is recorded for every customer domain instead of
    looking anything up (used when no resolver can be built)."""
    facts: dict = {}
    if resolver is None and dns_error is None:
        dns_error = DNS_LIBRARY_MISSING

    # ── 4.5.1 / 4.6.1 / 4.7.1 — DNS records on verified domains ────
    domains = client.get_all("/domains")
    verified: list = []
    for d in domains:
        if not d.get("isVerified"):
            continue
        domain_id = d.get("id")
        entry = {
            "id": domain_id,
            "is_default": bool(d.get("isDefault")),
            "is_initial": bool(d.get("isInitial")),
        }
        # The Microsoft-managed *initial* domain (…onmicrosoft.com) is
        # excluded from the SPF/DKIM/DMARC controls policy-side
        # (defender_validation.rego skips is_initial): the tenant cannot
        # publish DNS for it, so it is not looked up.
        if not entry["is_initial"]:
            # A domain whose records could NOT be read is marked
            # `dns_unavailable` so the policy reports it as not evaluated
            # rather than reading a missing record as a definite violation.
            if dns_error is not None:
                entry["dns_unavailable"] = dns_error
            else:
                entry.update(published_mail_auth(domain_id, resolver))
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
            dns_timeout=dict(type="float", default=5.0),
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
        resolver, dns_error = None, None
        if HAS_DNSPYTHON:
            try:
                resolver = DnsResolver(timeout=module.params["dns_timeout"])
            except Exception as exc:  # no resolv.conf, unreadable config
                dns_error = ("evidence missing: DNS lookup not available -- the "
                             "resolver could not be configured (%s)" % type(exc).__name__)
        else:
            dns_error = DNS_LIBRARY_MISSING
        facts = collect_facts(
            client, mailbox_sample_size=module.params["mailbox_sample_size"],
            resolver=resolver, dns_error=dns_error,
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
