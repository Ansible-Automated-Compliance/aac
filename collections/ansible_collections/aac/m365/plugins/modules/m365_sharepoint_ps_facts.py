#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_sharepoint_ps_facts — collect CIS M365 v7.0.0 Section 7 state.

Eleven of section 7's twelve recommendations read tenant properties that
the benchmark audits with Get-SPOTenant.

DELIBERATE, PERMANENT DEVIATION FROM THE BENCHMARK'S PROCEDURE:
Get-SPOTenant lives in Microsoft.Online.SharePoint.PowerShell, which is
Windows-only and cannot be installed in a Linux execution environment --
verified absent from aac-m365-ee. This collector uses Get-PnPTenant
instead, which reads the same CSOM tenant properties through
PnP.PowerShell. The values are equivalent; the tool is not the one CIS
documents, so every section 7 result carries an evidence note.

Property -> control, one Get-PnPTenant call for all of them:

  LegacyAuthProtocolsEnabled            7.2.1
  EnableAzureADB2BIntegration           7.2.2
  SharingCapability                     7.2.3, 7.2.6
  OneDriveSharingCapability             7.2.4
  PreventExternalUsersFromResharing     7.2.5
  DefaultSharingLinkType                7.2.7
  SharingDomainRestrictionMode          7.2.8
  ExternalUserExpirationRequired        7.2.9
  EmailAttestationRequired              7.2.10
  DefaultLinkPermission                 7.2.11
  DisallowInfectedFileDownload          7.3.1

FAIL-CLOSED ON UNKNOWN PROPERTIES: the whole tenant object is fetched
rather than a Select-Object list, and every expected property that is
absent is recorded in `unavailable`. A property name that is wrong, or
that a future PnP version renames, therefore reports the affected control
as unevaluable instead of silently reading null and passing.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: m365_sharepoint_ps_facts
short_description: Collect SharePoint Online tenant state for CIS v7.0.0 Section 7
description:
  - Connects to SharePoint Online app-only with a certificate via
    PnP.PowerShell and collects the tenant state CIS Microsoft 365
    Foundations Benchmark v7.0.0 Section 7 evaluates.
  - Uses C(Get-PnPTenant) rather than the C(Get-SPOTenant) the benchmark
    documents, because Microsoft.Online.SharePoint.PowerShell is
    Windows-only. The properties read are the same.
  - Facts that cannot be collected, including expected properties absent
    from the returned object, are reported in C(unavailable).
options:
  app_id:
    description: Application (client) ID of the Entra app registration.
    required: true
    type: str
  organization:
    description: Tenant organization name, e.g. contoso.onmicrosoft.com.
    required: true
    type: str
  sharepoint_admin_url:
    description: SharePoint admin URL, e.g. https://contoso-admin.sharepoint.com.
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
"""

EXAMPLES = r"""
- name: Collect SharePoint tenant state for CIS v7.0.0 Section 7
  aac.m365.m365_sharepoint_ps_facts:
    app_id: "{{ m365_client_id }}"
    organization: "{{ m365_organization }}"
    sharepoint_admin_url: "{{ m365_sharepoint_admin_url }}"
    certificate_path: "{{ m365_cert_path }}"
    certificate_password: "{{ m365_cert_password }}"
  register: sharepoint_ps
"""

RETURN = r"""
facts:
  description: Section 7 tenant state.
  returned: always
  type: dict
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.aac.m365.plugins.module_utils.pwsh import (
    PwshRunner,
    PwshError,
)

# Expected property -> the control(s) it answers. Used both to shape the
# facts and to decide which controls become unevaluable when a property is
# missing from the tenant object.
PROPERTY_CONTROLS = {
    "LegacyAuthProtocolsEnabled": ["7.2.1"],
    "EnableAzureADB2BIntegration": ["7.2.2"],
    "SharingCapability": ["7.2.3", "7.2.6"],
    "OneDriveSharingCapability": ["7.2.4"],
    "PreventExternalUsersFromResharing": ["7.2.5"],
    "DefaultSharingLinkType": ["7.2.7"],
    "SharingDomainRestrictionMode": ["7.2.8"],
    "ExternalUserExpirationRequired": ["7.2.9"],
    "EmailAttestationRequired": ["7.2.10"],
    "DefaultLinkPermission": ["7.2.11"],
    "DisallowInfectedFileDownload": ["7.3.1"],
}


def collect_facts(runner):
    facts, unavailable = {}, {}

    # Fetch the WHOLE object, not a Select-Object list. Selecting a
    # property that does not exist yields null, which is indistinguishable
    # from a genuinely-null setting; fetching everything lets us tell
    # "absent" from "set to nothing".
    tenant, err = runner.try_run("Get-PnPTenant")
    if err:
        unavailable["tenant"] = err
        facts["unavailable"] = unavailable
        facts["collected"] = True
        facts["source"] = "pnp_powershell"
        return facts

    if not isinstance(tenant, dict):
        unavailable["tenant"] = (
            "Get-PnPTenant returned %s rather than an object" % type(tenant).__name__
        )
        facts["unavailable"] = unavailable
        facts["collected"] = True
        facts["source"] = "pnp_powershell"
        return facts

    present, missing = {}, []
    for prop in PROPERTY_CONTROLS:
        if prop in tenant:
            present[prop] = tenant[prop]
        else:
            missing.append(prop)

    facts["tenant"] = present
    for prop in missing:
        controls = ", ".join(PROPERTY_CONTROLS[prop])
        unavailable[prop] = (
            "Get-PnPTenant did not return the '%s' property, so control(s) %s "
            "could not be evaluated -- the property may have been renamed in "
            "this PnP.PowerShell version" % (prop, controls)
        )

    facts["missing_properties"] = missing
    facts["unavailable"] = unavailable
    facts["collected"] = True
    facts["source"] = "pnp_powershell"
    # Recorded so the evaluation can state the deviation rather than
    # implying the benchmark's own procedure was followed.
    facts["cmdlet_used"] = "Get-PnPTenant"
    facts["cmdlet_documented_by_cis"] = "Get-SPOTenant"
    return facts


def main() -> None:
    module = AnsibleModule(
        argument_spec=dict(
            app_id=dict(type="str", required=True),
            organization=dict(type="str", required=True),
            sharepoint_admin_url=dict(type="str", required=True),
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
            service="sharepoint",
            app_id=module.params["app_id"],
            organization=module.params["organization"],
            sharepoint_admin_url=module.params["sharepoint_admin_url"],
            cert_path=module.params["certificate_path"],
            cert_password=module.params["certificate_password"],
            timeout=module.params["timeout"],
        )
        facts = collect_facts(runner)
    except PwshError as exc:
        module.fail_json(msg=str(exc), stderr=exc.stderr[:2000])
        return
    module.exit_json(changed=False, facts=facts)


if __name__ == "__main__":
    main()
