#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_sharepoint_facts — collect SharePoint Online state for CIS Section 6.

CIS Section 6 covers SharePoint Online sharing posture: external
sharing scope, guest access, link expiration, anonymous access,
and site classification. The /admin/sharepoint/settings endpoint
is in Graph beta — we use it where reachable and fall back to
Secure Score for the rest.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: m365_sharepoint_facts
short_description: Collect SharePoint Online state for CIS Section 6
options:
  tenant_id: {type: str, required: true}
  client_id: {type: str, required: true}
  client_secret: {type: str, required: true, no_log: true}
  timeout: {type: int, default: 30}
  use_proxy: {type: bool, default: true, description: Route Graph/token calls through the environment proxy (HTTPS_PROXY/HTTP_PROXY); set false to force a direct connection.}
  proxy: {type: str, required: false, description: Explicit proxy URL for Graph/token calls (e.g. http://proxy:8080); overrides the environment proxy.}
author: ["AAC maintainers"]
"""

EXAMPLES = r"""
- aac.m365.m365_sharepoint_facts:
    tenant_id: "{{ m365_tenant_id }}"
    client_id: "{{ m365_client_id }}"
    client_secret: >-
      {{ m365_client_secret }}
  register: sharepoint_facts
"""

RETURN = r"""
facts:
  description: SharePoint Online state.
  returned: always
  type: dict
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.aac.m365.plugins.module_utils.graph import (
    GraphClient,
    GraphError,
    fetch_secure_score_controls,
)


_RELEVANT_CONTROLS = {
    "SharePointLegacyAuthDisabled",  # 6.1.1
    "SharePointExternalSharing",     # 6.1.2 — sharing scope
    "SharePointGuestSharing",        # 6.2.1 — guest reshare
    "SharePointLinkReauth",          # 6.3.1 — reauth for shared links
    "SharePointDefaultLinkType",     # 6.4.1 — default link not anyone
}


def collect_facts(client: GraphClient) -> dict:
    facts: dict = {}

    controls = fetch_secure_score_controls(client, _RELEVANT_CONTROLS)
    facts["secure_score_controls"] = [
        {
            "id": c.get("id") or c.get("controlName"),
            "implementation_status": c.get("implementationStatus"),
            "max_score": c.get("maxScore"),
        }
        for c in controls
        if (c.get("id") or c.get("controlName")) in _RELEVANT_CONTROLS
    ]
    facts["controls_by_id"] = {
        c["id"]: c["implementation_status"] for c in facts["secure_score_controls"] if c["id"]
    }

    # SharePoint tenant settings — beta-only at the time of writing.
    # If the endpoint isn't reachable, fall back to Secure Score only.
    try:
        sp_settings = client.get("/admin/sharepoint/settings")
    except GraphError:
        sp_settings = {}
    facts["sharing_capability"] = sp_settings.get("sharingCapability")
    facts["default_sharing_link_type"] = sp_settings.get("defaultSharingLinkType")
    facts["default_link_permission"] = sp_settings.get("defaultLinkPermission")
    facts["legacy_auth_protocols_enabled"] = sp_settings.get(
        "legacyAuthProtocolsEnabled"
    )
    facts["settings_reachable"] = bool(sp_settings)

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
        module.fail_json(msg=f"Microsoft Graph error: {exc.status} at {exc.request_path}", details=exc.body[:2000])
        return
    module.exit_json(changed=False, facts=facts)


if __name__ == "__main__":
    main()
