#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_defender_ps_facts — collect CIS M365 v7.0.0 Section 2 state.

Section 2's policy controls are audited through Exchange Online
PowerShell, not Graph. This is what replaces the Microsoft Secure Score
wrapper the pre-v7 library used: Secure Score is Microsoft's own scoring
model with its own control set, and an implementationStatus from it does
not establish a CIS recommendation.

  Get-SafeLinksPolicy               2.1.1
  Get-MalwareFilterPolicy           2.1.2, 2.1.3, 2.1.11
  Get-SafeAttachmentPolicy/Rule     2.1.4
  Get-AtpPolicyForO365              2.1.5
  Get-HostedOutboundSpamFilterPolicy 2.1.6, 2.1.15
  Get-AntiPhishPolicy               2.1.7
  Get-HostedConnectionFilterPolicy  2.1.12, 2.1.13
  Get-HostedContentFilterPolicy     2.1.14
  Get-EOPProtectionPolicyRule       2.4.2
  Get-ATPProtectionPolicyRule       2.4.2
  Get-DkimSigningConfig             2.1.9 (signing enabled per domain)
  Get-TeamsProtectionPolicy         2.4.4

SPF, DKIM and DMARC (2.1.8, 2.1.9, 2.1.10) are NOT here -- those are
public DNS lookups and are already collected by the exchange domains
path. They are section 2 controls in v7.0.0 despite being about mail
domains.

NOT collected: 2.2.1, 2.4.3, 2.4.5. CIS marks all three Manual with no
PowerShell audit procedure. They remain in the attestation module's
unresolved set.

Every query is optional in the sense that a tenant without Defender for
Office 365 will not have the ATP cmdlets at all. That is recorded as
unavailable per fact rather than failing the whole collection -- a tenant
on a plan without those features should see "could not be evaluated", not
a crash and not a pass.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: m365_defender_ps_facts
short_description: Collect Microsoft Defender policy state for CIS v7.0.0 Section 2
description:
  - Connects to Exchange Online PowerShell app-only with a certificate and
    collects the Defender for Office 365 and EOP policy state that CIS
    Microsoft 365 Foundations Benchmark v7.0.0 Section 2 evaluates.
  - Replaces the Microsoft Secure Score wrapper used before v7, which
    could not establish a CIS control.
  - Facts that cannot be collected are reported in C(unavailable).
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
  timeout:
    description: Seconds to allow each PowerShell invocation.
    type: int
    default: 300
author:
  - "AAC maintainers"
notes:
  - >-
    Tenants without Defender for Office 365 do not expose the Safe Links,
    Safe Attachments or ATP cmdlets. Those facts report as unavailable
    rather than failing the run or reading as compliant.
"""

EXAMPLES = r"""
- name: Collect Defender policy state for CIS v7.0.0 Section 2
  aac.m365.m365_defender_ps_facts:
    app_id: "{{ m365_client_id }}"
    organization: "{{ m365_organization }}"
    certificate_path: "{{ m365_cert_path }}"
    certificate_password: "{{ m365_cert_password }}"
  register: defender_ps
"""

RETURN = r"""
facts:
  description: Section 2 policy state.
  returned: always
  type: dict
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.aac.m365.plugins.module_utils.pwsh import (
    LIST,
    OBJECT,
    PwshRunner,
    PwshError,
)

# fact key -> (snippet, controls it answers, shape). LIST for every
# policy collection the Rego iterates or counts; OBJECT for the two
# tenant singletons it dereferences (Get-AtpPolicyForO365,
# Get-TeamsProtectionPolicy). A tenant with only the Default policy used
# to return a bare object for the LIST keys, and the rules then passed.
QUERIES = {
    "safe_links_policies": (
        "@(Get-SafeLinksPolicy | Select-Object Name, IsEnabled, "
        "EnableSafeLinksForEmail, EnableSafeLinksForTeams, "
        "EnableSafeLinksForOffice, TrackClicks, AllowClickThrough)",
        ["2.1.1"],
        LIST,
    ),
    "malware_filter_policies": (
        "@(Get-MalwareFilterPolicy | Select-Object Identity, IsDefault, "
        "EnableFileFilter, FileTypes, EnableInternalSenderAdminNotifications, "
        "ZapEnabled)",
        ["2.1.2", "2.1.3", "2.1.11"],
        LIST,
    ),
    "safe_attachment_policies": (
        "@(Get-SafeAttachmentPolicy | Select-Object Name, Enable, Action, "
        "Redirect, QuarantineTag)",
        ["2.1.4"],
        LIST,
    ),
    "atp_policy_for_o365": (
        "Get-AtpPolicyForO365 | Select-Object Name, "
        "EnableATPForSPOTeamsODB, EnableSafeDocs, AllowSafeDocsOpen",
        ["2.1.5"],
        OBJECT,
    ),
    "outbound_spam_policies": (
        "@(Get-HostedOutboundSpamFilterPolicy | Select-Object Name, IsDefault, "
        "NotifyOutboundSpam, NotifyOutboundSpamRecipients, "
        "RecipientLimitExternalPerHour, RecipientLimitInternalPerHour, "
        "RecipientLimitPerDay, ActionWhenThresholdReached)",
        ["2.1.6", "2.1.15"],
        LIST,
    ),
    "anti_phish_policies": (
        "@(Get-AntiPhishPolicy | Select-Object Name, Enabled, "
        "EnableMailboxIntelligence, EnableMailboxIntelligenceProtection, "
        "EnableSpoofIntelligence, PhishThresholdLevel, "
        "EnableFirstContactSafetyTips, EnableTargetedUserProtection, "
        "AuthenticationFailAction)",
        ["2.1.7"],
        LIST,
    ),
    "connection_filter_policies": (
        "@(Get-HostedConnectionFilterPolicy | Select-Object Name, IsDefault, "
        "IPAllowList, EnableSafeList)",
        ["2.1.12", "2.1.13"],
        LIST,
    ),
    "content_filter_policies": (
        "@(Get-HostedContentFilterPolicy | Select-Object Name, IsDefault, "
        "AllowedSenders, AllowedSenderDomains)",
        ["2.1.14"],
        LIST,
    ),
    "eop_protection_rules": (
        "@(Get-EOPProtectionPolicyRule | Select-Object Name, State, Priority, "
        "SentTo, SentToMemberOf, RecipientDomainIs)",
        ["2.4.2"],
        LIST,
    ),
    # 2.4.2 -- the strict preset has two rules, one per protection stack
    # (EOP above, Defender for Office 365 here); the policy needs both enabled
    # and scoped to recipients.
    "atp_protection_rules": (
        "@(Get-ATPProtectionPolicyRule | Select-Object Name, State, Priority, "
        "SentTo, SentToMemberOf, RecipientDomainIs)",
        ["2.4.2"],
        LIST,
    ),
    # 2.1.9 -- published selector CNAMEs (read from DNS by m365_exchange_facts)
    # do not show that Exchange Online signs: the signing configuration has to
    # be enabled per domain.
    "dkim_signing_configs": (
        "@(Get-DkimSigningConfig | Select-Object Domain, Name, Enabled, Status)",
        ["2.1.9"],
        LIST,
    ),
    "teams_protection_policy": (
        "Get-TeamsProtectionPolicy | Select-Object Name, ZapEnabled",
        ["2.4.4"],
        OBJECT,
    ),
}


# CIS 2.4.1 is a compound control spanning two PowerShell endpoints:
#
#   Exchange Online          Get-EmailTenantSettings
#                            -> EnablePriorityAccountProtection must be true
#   Security & Compliance    Get-ProtectionAlert
#                            -> a passing Phish alert AND a passing Malware
#                               alert, both tagged to priority accounts
#
# The second needs Connect-IPPSSession, a different endpoint from the one
# every other Defender cmdlet here uses, so it takes its own runner. The
# whole control is unavailable if either half is -- an enabled tenant flag
# with no alert policies is not the control CIS describes.
PRIORITY_ALERTS_QUERY = (
    "@(Get-ProtectionAlert | Where-Object { $_.RecipientTags -Match 'Priority account' } | "
    "Select-Object Name, Severity, Filter, RecipientTags, ThreatType, "
    "NotificationEnabled, NotifyUser, Disabled)"
)


def _with_file_type_filter(policy):
    """2.1.11 -- the common attachment filter's list is the FileTypes
    property (Set-MalwareFilterPolicy -FileTypes <String[]>; the cmdlet's
    own example reads it with `Get-MalwareFilterPolicy | select -Expand
    FileTypes`). FileTypeFilter, which this collector used to select, is
    not a property: Select-Object filled it with null, `count(null)` is
    undefined in Rego, and 2.1.11 could never fire.

    The shipped policy still reads `FileTypeFilter`, so the real list is
    published under both names. A missing or null list becomes [] -- the
    direction that reports a violation rather than a pass.
    """
    types = policy.get("FileTypes")
    if types is None:
        types = []
    elif not isinstance(types, list):
        types = [types]
    out = dict(policy)
    out["FileTypes"] = types
    out["FileTypeFilter"] = types
    return out


def collect_facts(runner, ipps_runner=None):
    facts, unavailable = {}, {}
    for key, (snippet, controls, shape) in QUERIES.items():
        value, err = runner.try_run(snippet, shape=shape)
        if err:
            # A tenant without Defender for Office 365 simply does not have
            # some of these cmdlets. Record which controls that blocks
            # rather than letting the absence read as compliance.
            unavailable[key] = "%s (blocks %s)" % (err, ", ".join(controls))
        else:
            facts[key] = value

    if "malware_filter_policies" in facts:
        facts["malware_filter_policies"] = [
            _with_file_type_filter(p) for p in facts["malware_filter_policies"]
        ]

    # ── 2.4.1, part 1 -- the tenant-level toggle (Exchange Online) ────
    value, err = runner.try_run(
        "Get-EmailTenantSettings | Select-Object EnablePriorityAccountProtection",
        shape=OBJECT,
    )
    if err:
        unavailable["email_tenant_settings"] = "%s (blocks 2.4.1)" % err
    else:
        facts["email_tenant_settings"] = value

    # ── 2.4.1, part 2 -- the alert policies (Security & Compliance) ───
    if ipps_runner is None:
        unavailable["priority_account_alerts"] = (
            "Security & Compliance PowerShell session not established "
            "(blocks 2.4.1)"
        )
    else:
        value, err = ipps_runner.try_run(PRIORITY_ALERTS_QUERY, shape=LIST)
        if err:
            unavailable["priority_account_alerts"] = "%s (blocks 2.4.1)" % err
        else:
            facts["priority_account_alerts"] = value

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
        # 2.4.1's alert half lives behind Connect-IPPSSession. A tenant
        # that cannot open that session still gets every other Defender
        # control -- 2.4.1 alone is then recorded unavailable, rather than
        # the whole module failing.
        try:
            ipps_runner = PwshRunner(
                service="purview",
                app_id=module.params["app_id"],
                organization=module.params["organization"],
                cert_path=module.params["certificate_path"],
                cert_password=module.params["certificate_password"],
                timeout=module.params["timeout"],
            )
        except PwshError:
            ipps_runner = None
        facts = collect_facts(runner, ipps_runner=ipps_runner)
    except PwshError as exc:
        module.fail_json(msg=str(exc), stderr=exc.stderr[:2000])
        return
    module.exit_json(changed=False, facts=facts)


if __name__ == "__main__":
    main()
