#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_intune_facts — collect CIS M365 v7.0.0 Section 4 state.

Section 4 (Microsoft Intune admin center) has 2 recommendations, both of
which the benchmark's Audit procedure reaches through Microsoft Graph:

  4.1  Devices without a compliance policy are marked 'not compliant'
       -> /deviceManagement/settings  (secureByDefault)
  4.2  Device enrollment for personally owned devices is blocked
       -> /deviceManagement/deviceEnrollmentConfigurations

Section 4 uses TWO-level control ids (4.1, 4.2), unlike every other
section in the benchmark. That is not a typo.

Requires the DeviceManagementConfiguration.Read.All application
permission, which is an addition to the app registration -- Intune state
is not reachable with the permissions the other collectors use.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: m365_intune_facts
short_description: Collect Microsoft Intune state for CIS v7.0.0 Section 4
description:
  - Authenticates to Microsoft Graph via Entra app registration
    (client credentials) and collects the device-management state that
    CIS Microsoft 365 Foundations Benchmark v7.0.0 Section 4 evaluates.
  - Facts that cannot be collected are reported in C(unavailable)
    rather than silently defaulted.
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
author:
  - "AAC maintainers"
notes:
  - >-
    Requires the DeviceManagementConfiguration.Read.All application
    permission. This is an ADDITION to the permissions the other aac.m365
    collectors need; without it both Section 4 controls report as
    unavailable rather than passing.
"""

EXAMPLES = r"""
- name: Collect Intune state for CIS v7.0.0 Section 4
  aac.m365.m365_intune_facts:
    tenant_id: "{{ m365_tenant_id }}"
    client_id: "{{ m365_client_id }}"
    client_secret: "{{ m365_client_secret }}"
  register: intune

- name: Evaluate against OPA
  ansible.builtin.uri:
    url: "{{ opa_security_url }}/v1/data/cis_m365_v7/intune/compliance_report"
    method: POST
    body_format: json
    body:
      input:
        intune: "{{ intune.facts }}"
"""

RETURN = r"""
facts:
  description: Section 4 tenant state.
  returned: always
  type: dict
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.aac.m365.plugins.module_utils.graph import (
    GraphClient,
    GraphError,
)

# Enrollment restrictions that apply to personally owned devices carry
# these platform restriction keys in deviceEnrollmentConfigurations.
PERSONAL_PLATFORMS = ("iosRestriction", "androidRestriction",
                      "windowsRestriction", "macOSRestriction",
                      "androidForWorkRestriction")


def collect_facts(client):
    facts, unavailable = {}, {}

    # ── CIS 4.1 -- untargeted devices must be treated as non-compliant ──
    # Intune calls this "secure by default": when no compliance policy is
    # assigned, the device is marked not compliant rather than compliant.
    settings, err = client.try_get("/deviceManagement/settings")
    if err:
        unavailable["device_management_settings"] = err
    else:
        facts["secure_by_default"] = settings.get("secureByDefault")

    # ── CIS 4.2 -- block enrolment of personally owned devices ─────────
    configs, err = client.try_get_all("/deviceManagement/deviceEnrollmentConfigurations")
    if err:
        unavailable["enrollment_configurations"] = err
    else:
        restrictions = []
        for c in configs:
            odata = c.get("@odata.type", "")
            if "PlatformRestrictions" not in odata:
                continue
            entry = {
                "id": c.get("id"),
                "display_name": c.get("displayName"),
                "priority": c.get("priority"),
                "platforms": {},
            }
            for key in PERSONAL_PLATFORMS:
                r = c.get(key)
                if isinstance(r, dict):
                    entry["platforms"][key] = {
                        # True here means personally owned devices ARE
                        # blocked -- which is what the control wants.
                        "personal_device_enrollment_blocked":
                            r.get("personalDeviceEnrollmentBlocked"),
                        "platform_blocked": r.get("platformBlocked"),
                    }
            restrictions.append(entry)
        facts["enrollment_platform_restrictions"] = restrictions

    facts["unavailable"] = unavailable
    facts["collected"] = True
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
        client = GraphClient(
            tenant_id=module.params["tenant_id"],
            client_id=module.params["client_id"],
            client_secret=module.params["client_secret"],
            timeout=module.params["timeout"],
            use_proxy=module.params["use_proxy"],
            proxy=module.params["proxy"],
        )
        facts = collect_facts(client)
    except GraphError as exc:
        module.fail_json(
            msg=f"Microsoft Graph error: {exc.status} at {exc.request_path}",
            details=exc.body[:2000],
        )
        return
    module.exit_json(changed=False, facts=facts)


if __name__ == "__main__":
    main()
