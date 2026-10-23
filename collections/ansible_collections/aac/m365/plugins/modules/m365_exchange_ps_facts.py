#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_exchange_ps_facts — collect CIS M365 v7.0.0 Section 6 state.

All 13 of section 6's recommendations are audited through Exchange Online
PowerShell. Microsoft exposes no REST equivalent for these settings, so
this is the only way to establish them.

Queries are grouped by cmdlet rather than by control, because several
cmdlets carry more than one control. Get-OrganizationConfig alone answers
four (6.1.1, 6.5.1, 6.5.2, 6.5.5), so it is fetched once.

  Get-OrganizationConfig           6.1.1, 6.5.1, 6.5.2, 6.5.5
  Get-EXOMailbox                   6.1.2
  Get-MailboxAuditBypassAssociation 6.1.3
  Get-TransportRule                6.2.1, 6.2.2
  Get-HostedOutboundSpamFilterPolicy 6.2.1
  Get-ExternalInOutlook            6.2.3
  Get-RoleAssignmentPolicy         6.3.1
  Get-OwaMailboxPolicy             6.3.2, 6.5.3
  Get-TransportConfig              6.5.4
  Get-SharingPolicy                1.3.3   (section 1, Exchange setting)
  Get-EXOMailbox -SharedMailbox    1.2.2   (section 1; Graph half in
                                            m365_admin_center_facts)

This supersedes the Graph-based proxy for 6.1.1. Graph v1.0 does not
expose the tenant-wide AuditDisabled flag, so the earlier collector
sampled per-user mailbox settings and could only ever be indicative.
Get-OrganizationConfig reads the flag directly, which is what the
benchmark's own audit procedure does.

Requires the aac-m365-ee execution environment (pwsh + the
ExchangeOnlineManagement module) and app-only certificate credentials.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: m365_exchange_ps_facts
short_description: Collect Exchange Online state for CIS v7.0.0 Section 6
description:
  - Connects to Exchange Online PowerShell app-only with a certificate and
    collects the state CIS Microsoft 365 Foundations Benchmark v7.0.0
    Section 6 evaluates.
  - Requires an execution environment carrying pwsh and the
    ExchangeOnlineManagement module (see aac-m365-ee).
  - Facts that cannot be collected are reported in C(unavailable) rather
    than silently defaulted.
options:
  app_id:
    description: Application (client) ID of the Entra app registration.
    required: true
    type: str
  organization:
    description: Tenant organization name, e.g. contoso.onmicrosoft.com.
    required: true
    type: str
  certificate_path:
    description: Path to the PFX certificate used for app-only auth.
    required: true
    type: str
  certificate_password:
    description: Password protecting the PFX certificate.
    required: true
    type: str
    no_log: true
  mailbox_sample_size:
    description: Maximum mailboxes to inspect for control 6.1.2.
    type: int
    default: 100
  timeout:
    description: Seconds to allow each PowerShell invocation.
    type: int
    default: 300
author:
  - "AAC maintainers"
notes:
  - >-
    Exchange Online PowerShell does NOT support client-secret app-only
    auth. A certificate is required, along with the Exchange.ManageAsApp
    application permission and an assigned Entra directory role.
"""

EXAMPLES = r"""
- name: Collect Exchange Online state for CIS v7.0.0 Section 6
  aac.m365.m365_exchange_ps_facts:
    app_id: "{{ m365_client_id }}"
    organization: "{{ m365_organization }}"
    certificate_path: "{{ m365_cert_path }}"
    certificate_password: "{{ m365_cert_password }}"
  register: exchange_ps

- name: Evaluate against OPA
  ansible.builtin.uri:
    url: "{{ opa_security_url }}/v1/data/cis_m365_v7/exchange/compliance_report"
    method: POST
    body_format: json
    body:
      input:
        exchange: "{{ exchange_ps.facts }}"
"""

RETURN = r"""
facts:
  description: Section 6 tenant state.
  returned: always
  type: dict
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.aac.m365.plugins.module_utils.pwsh import (
    PwshRunner,
    PwshError,
)

# Each entry: fact key -> (PowerShell snippet, controls it answers).
# Select-Object keeps the payload small and the JSON shape stable; without
# it these cmdlets return very large objects whose shape varies by tenant.
QUERIES = {
    "organization_config": (
        # Also carries two SECTION 1 controls: customer lockbox (1.3.6)
        # and shared bookings (1.3.9). Fetching them here avoids a second
        # Exchange session for two fields.
        "Get-OrganizationConfig | Select-Object "
        "AuditDisabled, OAuth2ClientProfileEnabled, MailTipsAllTipsEnabled, "
        "MailTipsExternalRecipientsTipsEnabled, RejectDirectSend, "
        "CustomerLockBoxEnabled, BookingsEnabled, "
        "BookingsSocialSharingRestricted, BookingsAuthEnabled",
        ["6.1.1", "6.5.1", "6.5.2", "6.5.5", "1.3.6", "1.3.9"],
    ),
    "transport_config": (
        "Get-TransportConfig | Select-Object SmtpClientAuthenticationDisabled",
        ["6.5.4"],
    ),
    # SECTION 1 control, collected here for the same reason as 1.3.6/1.3.9:
    # it is an Exchange setting and this session is already open.
    #
    # CIS audits `Get-SharingPolicy -Identity "Default Sharing Policy"` and
    # checks Enabled is False. Every policy is returned rather than only
    # the default one -- a tenant can add further sharing policies, and a
    # second enabled policy shares calendars just as effectively as the
    # default would. Narrowing to the default is what the benchmark
    # documents; it is not what establishes the control.
    "sharing_policies": (
        "@(Get-SharingPolicy | Select-Object Name, Enabled, Default, Domains)",
        ["1.3.3"],
    ),
    # SECTION 1 control. Half of it: CIS's procedure is Get-EXOMailbox for
    # the shared mailboxes, then Get-MgUser for each one's AccountEnabled.
    # The Graph half runs in m365_admin_center_facts (this session has no
    # Graph token), and the Rego joins the two on the directory object id
    # -- which is the key CIS itself joins on.
    "shared_mailboxes": (
        "@(Get-EXOMailbox -RecipientTypeDetails SharedMailbox -ResultSize Unlimited | "
        "Select-Object UserPrincipalName, ExternalDirectoryObjectId, DisplayName)",
        ["1.2.2"],
    ),
    "transport_rules": (
        "@(Get-TransportRule | Select-Object Name, State, "
        "SetSCL, SenderDomainIs, FromAddressContainsWords, RedirectMessageTo, "
        "BlindCopyTo, CopyTo)",
        ["6.2.1", "6.2.2"],
    ),
    "outbound_spam_policies": (
        "@(Get-HostedOutboundSpamFilterPolicy | Select-Object "
        "Name, AutoForwardingMode, IsDefault)",
        ["6.2.1"],
    ),
    "external_in_outlook": (
        "@(Get-ExternalInOutlook | Select-Object Identity, Enabled)",
        ["6.2.3"],
    ),
    "role_assignment_policies": (
        "@(Get-RoleAssignmentPolicy | Select-Object Name, IsDefault, AssignedRoles)",
        ["6.3.1"],
    ),
    "owa_mailbox_policies": (
        "@(Get-OwaMailboxPolicy | Select-Object Name, IsDefault, "
        "AdditionalStorageProvidersAvailable, AllowedFileTypes)",
        ["6.3.2", "6.5.3"],
    ),
    "audit_bypass_associations": (
        "@(Get-MailboxAuditBypassAssociation -ResultSize Unlimited | "
        "Where-Object { $_.AuditBypassEnabled -eq $true } | "
        "Select-Object Identity, AuditBypassEnabled)",
        ["6.1.3"],
    ),
}


def collect_facts(runner, mailbox_sample=100):
    facts, unavailable = {}, {}

    for key, (snippet, _controls) in QUERIES.items():
        value, err = runner.try_run(snippet)
        if err:
            unavailable[key] = err
        else:
            facts[key] = value

    # 6.1.2 -- mailbox audit actions. Sampled rather than exhaustive: a
    # large tenant has tens of thousands of mailboxes and the control is
    # about configuration, not per-user enumeration. The sample size is
    # reported so a reader can judge the strength of the result.
    value, err = runner.try_run(
        f"@(Get-EXOMailbox -ResultSize {int(mailbox_sample)} -Properties "
        "AuditEnabled, AuditAdmin, AuditDelegate, AuditOwner | "
        "Select-Object UserPrincipalName, AuditEnabled, AuditAdmin, "
        "AuditDelegate, AuditOwner)"
    )
    if err:
        unavailable["mailbox_audit"] = err
    else:
        rows = value if isinstance(value, list) else [value]
        facts["mailbox_audit"] = {
            "sampled": len(rows),
            "sample_limit": int(mailbox_sample),
            "audit_disabled": [
                {"user_principal_name": r.get("UserPrincipalName")}
                for r in rows if r.get("AuditEnabled") is False
            ],
        }

    facts["unavailable"] = unavailable
    facts["collected"] = True
    facts["source"] = "exchange_online_powershell"
    return facts


def main() -> None:
    module = AnsibleModule(
        argument_spec=dict(
            app_id=dict(type="str", required=True),
            organization=dict(type="str", required=True),
            certificate_path=dict(type="str", required=True),
            certificate_password=dict(type="str", required=True, no_log=True),
            mailbox_sample_size=dict(type="int", default=100),
            timeout=dict(type="int", default=300),
        ),
        supports_check_mode=True,
    )
    if module.check_mode:
        module.exit_json(changed=False, facts={})
    try:
        runner = PwshRunner(
            service="exchange",
            app_id=module.params["app_id"],
            organization=module.params["organization"],
            cert_path=module.params["certificate_path"],
            cert_password=module.params["certificate_password"],
            timeout=module.params["timeout"],
        )
        facts = collect_facts(runner, mailbox_sample=module.params["mailbox_sample_size"])
    except PwshError as exc:
        module.fail_json(msg=str(exc), stderr=exc.stderr[:2000])
        return
    module.exit_json(changed=False, facts=facts)


if __name__ == "__main__":
    main()
