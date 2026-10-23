#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_teams_facts — collect Microsoft Teams state for CIS Section 7.

CIS Section 7 covers Teams external access, federation, meeting
policy, guest access, and third-party app permissions. Most Teams
admin settings are surfaced via Secure Score; the /teamwork
endpoints in Graph v1.0 cover federation + a few meeting policies.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: m365_teams_facts
short_description: Collect Microsoft Teams state for CIS Section 7
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
- aac.m365.m365_teams_facts:
    tenant_id: "{{ m365_tenant_id }}"
    client_id: "{{ m365_client_id }}"
    client_secret: >-
      {{ m365_client_secret }}
  register: teams_facts
"""

RETURN = r"""
facts:
  description: Microsoft Teams state.
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
    "TeamsExternalAccess",           # 7.1.1 — external access restricted
    "TeamsGuestAccess",              # 7.1.2 — guest access scoped
    "TeamsAnonymousJoin",            # 7.2.1 — anonymous can't join meetings
    "TeamsAutoAdmit",                # 7.2.2 — lobby for external
    "TeamsCloudRecording",           # 7.3.1 — cloud recording governance
    "TeamsThirdPartyApps",           # 7.4.1 — 3p apps restricted
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

    # Teams app catalog count — useful evidence for 7.4.1. Per-tenant
    # the list can be hundreds; we just report the count, not the
    # whole catalog.
    try:
        apps_page = client.get("/appCatalogs/teamsApps", params={"$top": 100})
        apps = apps_page.get("value", [])
    except GraphError:
        apps = []
    facts["teams_apps_count"] = len(apps)

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
