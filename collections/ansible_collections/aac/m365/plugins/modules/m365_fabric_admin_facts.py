#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_fabric_admin_facts — collect CIS M365 v7.0.0 Section 9 state.

All 12 of section 9's recommendations are Fabric tenant settings.
Microsoft Graph does not expose them; they come from the Fabric / Power
BI admin API, which is a third authentication surface for this collection
(see module_utils/fabric.py).

The setting names below are taken from the benchmark itself -- each
control's audit procedure names the settingName to inspect -- rather than
inferred from the control title.

  9.1.1   AllowGuestUserToAccessSharedContent
  9.1.2   ExternalSharingV2
  9.1.3   ElevatedGuestsTenant
  9.1.4   PublishToWeb
  9.1.5   RScriptVisual
  9.1.6   EimInformationProtectionEdit
  9.1.7   ShareLinkToEntireOrg
  9.1.8   EnableDatasetInPlaceSharing
  9.1.9   BlockResourceKeyAuthentication
  9.1.10  ServicePrincipalAccessPermissionAPIs
  9.1.11  AllowServicePrincipalsCreateAndUseProfiles
  9.1.12  ServicePrincipalAccessGlobalAPIs

A setting the tenant does not return is recorded as unavailable with the
control it blocks, exactly as the SharePoint collector does for PnP
properties. Fabric adds settings over time and renames some; a missing
one must report its control unevaluable rather than reading as absent
and therefore compliant.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: m365_fabric_admin_facts
short_description: Collect Microsoft Fabric tenant settings for CIS v7.0.0 Section 9
description:
  - Authenticates to the Fabric / Power BI admin API with Entra client
    credentials and collects the tenant settings CIS Microsoft 365
    Foundations Benchmark v7.0.0 Section 9 evaluates.
  - Microsoft Graph does not expose these settings at all.
  - Settings the tenant does not return are reported in C(unavailable)
    with the control each one blocks.
options:
  tenant_id:
    description: Entra tenant GUID.
    required: true
    type: str
  client_id:
    description: Application (client) ID of the Entra app registration.
    required: true
    type: str
  client_secret:
    description: Client secret of the app registration.
    required: true
    type: str
    no_log: true
  timeout:
    description: HTTP timeout for Fabric admin API calls, seconds.
    type: int
    default: 30
  use_proxy:
    description:
      - Route Fabric/token calls through the environment proxy (HTTPS_PROXY/HTTP_PROXY); set false to force a direct connection.
    type: bool
    default: true
  proxy:
    description:
      - Explicit proxy URL for Fabric/token calls; overrides the environment proxy.
    type: str
    required: false
author:
  - "AAC maintainers"
notes:
  - >-
    Entra permissions alone are not sufficient. Fabric gates API access
    behind the admin-portal setting "Service principals can use Fabric
    APIs", which must name a security group containing this application.
    Without it the API returns 401/403 despite a valid token.
"""

EXAMPLES = r"""
- name: Collect Fabric tenant settings for CIS v7.0.0 Section 9
  aac.m365.m365_fabric_admin_facts:
    tenant_id: "{{ m365_tenant_id }}"
    client_id: "{{ m365_client_id }}"
    client_secret: "{{ m365_client_secret }}"
  register: fabric

- name: Evaluate against OPA
  ansible.builtin.uri:
    url: "{{ opa_security_url }}/v1/data/cis_m365_v7/fabric/compliance_report"
    method: POST
    body_format: json
    body:
      input:
        fabric: "{{ fabric.facts }}"
"""

RETURN = r"""
facts:
  description: Section 9 tenant settings.
  returned: always
  type: dict
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.aac.m365.plugins.module_utils.fabric import (
    FabricClient,
    FabricError,
)

# settingName -> control, taken from each control's audit procedure.
SETTING_CONTROLS = {
    "AllowGuestUserToAccessSharedContent": "9.1.1",
    "ExternalSharingV2": "9.1.2",
    "ElevatedGuestsTenant": "9.1.3",
    "PublishToWeb": "9.1.4",
    "RScriptVisual": "9.1.5",
    "EimInformationProtectionEdit": "9.1.6",
    "ShareLinkToEntireOrg": "9.1.7",
    "EnableDatasetInPlaceSharing": "9.1.8",
    "BlockResourceKeyAuthentication": "9.1.9",
    "ServicePrincipalAccessPermissionAPIs": "9.1.10",
    "AllowServicePrincipalsCreateAndUseProfiles": "9.1.11",
    "ServicePrincipalAccessGlobalAPIs": "9.1.12",
}


def collect_facts(client):
    facts, unavailable = {}, {}

    settings, err = client.try_get_tenant_settings()
    if err:
        # One failure blocks the whole section, so say so once with the
        # actionable reason rather than twelve times.
        unavailable["tenant_settings"] = err
        facts["unavailable"] = unavailable
        facts["collected"] = True
        facts["source"] = "fabric_admin_api"
        return facts

    present, missing = {}, []
    for name, control in SETTING_CONTROLS.items():
        if name in settings:
            present[name] = settings[name]
        else:
            missing.append(name)
            unavailable[name] = (
                "the Fabric admin API did not return the '%s' tenant setting, so "
                "control %s could not be evaluated -- Fabric renames and retires "
                "settings over time" % (name, control)
            )

    facts["settings"] = present
    facts["missing_settings"] = missing
    facts["settings_returned"] = len(settings)
    facts["unavailable"] = unavailable
    facts["collected"] = True
    facts["source"] = "fabric_admin_api"
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
        ),
        supports_check_mode=True,
    )
    if module.check_mode:
        module.exit_json(changed=False, facts={})
    try:
        client = FabricClient(
            tenant_id=module.params["tenant_id"],
            client_id=module.params["client_id"],
            client_secret=module.params["client_secret"],
            timeout=module.params["timeout"],
            use_proxy=module.params["use_proxy"],
            proxy=module.params["proxy"],
        )
        facts = collect_facts(client)
    except FabricError as exc:
        module.fail_json(
            msg=f"Fabric admin API error: {exc.status} at {exc.request_path}",
            details=exc.body[:2000],
        )
        return
    module.exit_json(changed=False, facts=facts)


if __name__ == "__main__":
    main()
