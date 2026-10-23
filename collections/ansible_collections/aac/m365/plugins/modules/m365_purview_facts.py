#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_purview_facts — collect Purview / audit / DLP state for CIS Section 3.

CIS Section 3 covers audit logging, eDiscovery, retention, DLP, and
Customer Key. Some of these are surfaced via Secure Score; others
need the Purview Activity API + audit-log query endpoints.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: m365_purview_facts
short_description: Collect Microsoft Purview state for CIS Section 3
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
- aac.m365.m365_purview_facts:
    tenant_id: "{{ m365_tenant_id }}"
    client_id: "{{ m365_client_id }}"
    client_secret: >-
      {{ m365_client_secret }}
  register: purview_facts
"""

RETURN = r"""
facts:
  description: Microsoft Purview state.
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
    "UnifiedAuditLogEnabled",        # 3.1.1
    "AuditLogRetention",             # 3.1.2 — retention >= 365 days for E5
    "AlertsForMaliciousEmails",      # 3.2.1
    "DLPPolicy",                     # 3.3.1 — DLP exists
    "CustomerKeyEncryption",         # 3.4.1
    "InsiderRiskPolicy",             # 3.5.1
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

    # Audit retention via /auditLogs/directoryAudits — sample most-recent
    # entry's timestamp; combined with the oldest reachable timestamp we
    # can approximate retention. Use a single page only — get_all would
    # follow @odata.nextLink through the entire audit history.
    try:
        audit_page = client.get(
            "/auditLogs/directoryAudits",
            params={"$top": 1, "$orderby": "activityDateTime desc"},
        )
        audit_sample = audit_page.get("value", [])
    except GraphError:
        audit_sample = []
    # NOTE: /auditLogs/directoryAudits is the Entra *directory* audit stream,
    # populated on essentially every tenant. It is NOT the CIS 3.1.1 signal,
    # which is Unified Audit Log *search* ingestion
    # (Get-OrganizationConfig | UnifiedAuditLogIngestionEnabled — exposed only
    # via Exchange Online PowerShell). Deriving audit_log_accessible from
    # directoryAudits made 3.1.1 pass almost unconditionally (a false pass).
    # Until the real signal is wired from the EXO collector, do NOT emit a
    # boolean here: with a non-boolean value purview_validation.rego's
    # facts_present is false, so 3.1.1 reports "could not be evaluated"
    # (fail-closed) rather than a misleading pass. The directoryAudits
    # timestamp below is kept only as a retention hint, not a compliance signal.
    facts["audit_log_accessible"] = None
    facts["audit_log_most_recent"] = audit_sample[0].get("activityDateTime") if audit_sample else None

    # eDiscovery cases — a tenant configured for Purview should have at
    # least one (even if just a default case). Absence is a soft signal
    # that Purview is not in active use. Count only the first page.
    try:
        ediscovery_page = client.get(
            "/security/cases/ediscoveryCases",
            params={"$top": 5},
        )
        ediscovery = ediscovery_page.get("value", [])
    except GraphError:
        ediscovery = []
    facts["ediscovery_cases_count"] = len(ediscovery)

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
