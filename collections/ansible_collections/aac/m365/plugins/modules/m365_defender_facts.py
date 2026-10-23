#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_defender_facts — collect Defender for Office 365 state for CIS Section 2.

CIS Section 2 covers Microsoft Defender for Office 365 policy
hygiene: Safe Attachments, Safe Links, anti-phishing, zero-hour
auto-purge, anti-malware filtering. Most of these are surfaced via
the Microsoft Secure Score control catalog; we project the
controls that map to CIS recommendations.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: m365_defender_facts
short_description: Collect Microsoft Defender for Office 365 state for CIS Section 2
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
- aac.m365.m365_defender_facts:
    tenant_id: "{{ m365_tenant_id }}"
    client_id: "{{ m365_client_id }}"
    client_secret: >-
      {{ m365_client_secret }}
  register: defender_facts
"""

RETURN = r"""
facts:
  description: M365 Defender for Office 365 state.
  returned: always
  type: dict
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.aac.m365.plugins.module_utils.graph import (
    GraphClient,
    GraphError,
    fetch_secure_score_controls,
)


# Secure Score control IDs that map to CIS Defender controls.
# Microsoft publishes these IDs in the Secure Score documentation;
# the set has been stable since Defender for O365 P1 launched.
_RELEVANT_CONTROLS = {
    "ATPSafeAttachments",            # 2.1.1 — Safe Attachments
    "ATPSafeLinks",                  # 2.1.2 — Safe Links
    "AntiPhishPolicy",               # 2.1.3 — anti-phishing baseline
    "MailboxIntelligence",           # 2.1.4 — impersonation protection
    "ZeroHourAutoPurge",             # 2.1.5 — ZAP for malware + phish
    "CommonAttachmentTypesFiltered", # 2.1.7 — block known-bad ext
    "AntiMalwarePolicy",             # 2.1.8 — anti-malware baseline
    "OutboundSpamPolicy",            # 2.2.1 — outbound spam mgmt
}


def collect_facts(client: GraphClient) -> dict:
    facts: dict = {}

    controls = fetch_secure_score_controls(client, _RELEVANT_CONTROLS)
    facts["secure_score_controls"] = [
        {
            "id": c.get("id") or c.get("controlName"),
            "name": c.get("title") or c.get("controlName"),
            "implementation_status": c.get("implementationStatus"),
            "max_score": c.get("maxScore"),
            "tier": c.get("tier"),
            "service": c.get("service"),
            "compliance_information": c.get("complianceInformation", []),
        }
        for c in controls
        if (c.get("id") or c.get("controlName")) in _RELEVANT_CONTROLS
    ]

    # Most recent Secure Score (overall + percentage)
    try:
        scores_page = client.get(
            "/security/secureScores",
            params={"$top": 1, "$orderby": "createdDateTime desc"},
        )
        scores = scores_page.get("value", [])
    except GraphError:
        scores = []
    if scores:
        latest = scores[0]
        facts["latest_score"] = {
            "current": latest.get("currentScore"),
            "max": latest.get("maxScore"),
            "active_user_count": latest.get("activeUserCount"),
            "created_date_time": latest.get("createdDateTime"),
        }
    else:
        facts["latest_score"] = None

    # Project the implementation_status by control id for easy Rego.
    facts["controls_by_id"] = {
        c["id"]: c["implementation_status"]
        for c in facts["secure_score_controls"]
        if c["id"]
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
