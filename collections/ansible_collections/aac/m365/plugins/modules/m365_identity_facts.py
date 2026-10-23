#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_identity_facts — collect M365 identity state for CIS evaluation.

Pulls the state needed for the CIS Microsoft 365 Foundations Benchmark
Section 1 (Microsoft Entra) controls:

  - 1.1.1 Security Defaults disabled (with CA in use)
  - 1.1.2 Two-to-four Global Administrators designated
  - 1.1.3 All Global Admins have MFA enabled / strong methods
  - 1.1.4 User MFA enforced via Conditional Access
  - 1.1.5 Privileged Identity Management eligibility configured

The fact shape is intentionally flat and predictable so the
companion Rego policies under policies/benchmarks/cis/saas/m365/
can evaluate without reaching into deeply-nested objects.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: m365_identity_facts
short_description: Collect Microsoft 365 identity state for CIS evaluation
description:
  - Authenticates to Microsoft Graph via Azure AD app registration
    (client credentials), pulls the identity state CIS Section 1
    cares about, and emits flat JSON facts.
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
author:
  - "AAC maintainers"
"""

EXAMPLES = r"""
- name: Gather M365 identity state for CIS evaluation
  aac.m365.m365_identity_facts:
    tenant_id: "{{ m365_tenant_id }}"
    client_id: "{{ m365_client_id }}"
    client_secret: >-
      {{ m365_client_secret }}
  register: identity_facts

- name: POST to OPA for evaluation
  ansible.builtin.uri:
    url: "{{ opa_security_url }}/v1/data/cis_m365_v7/identity/compliance_report"
    method: POST
    body_format: json
    body:
      input: "{{ identity_facts.facts }}"
"""

RETURN = r"""
facts:
  description: M365 identity state shaped for CIS Rego evaluation.
  returned: always
  type: dict
  contains:
    security_defaults_enabled:
      description: Whether Security Defaults are turned on.
      type: bool
    global_admins:
      description: >
        List of global admins. Each entry carries C(id), C(display_name),
        C(user_principal_name), C(mfa_methods) (list of Graph
        C(@odata.type) strings), and C(has_strong_mfa) (bool — whether
        any method is in the CIS-acceptable strong-method set).
      type: list
    conditional_access_policies:
      description: >
        All Conditional Access policies. Each entry carries C(id),
        C(display_name), C(state), C(conditions), and C(grant_controls).
      type: list
    pim_role_assignments:
      description: >
        Privileged Identity Management eligibility schedule instances.
        Each entry carries C(principal_id), C(role_definition_id), and
        C(status). Empty when PIM is not in use or the tenant lacks
        the Premium P2 license.
      type: list
    pim_available:
      description: >
        True when PIM eligibility schedule instances were enumerable
        (any non-empty result). False on 403 from Graph (no P2 license)
        or no eligibility configured.
      type: bool
"""

from ansible.module_utils.basic import AnsibleModule

# Resolved at runtime via Ansible's collection-aware import path.
from ansible_collections.aac.m365.plugins.module_utils.graph import (
    GraphClient,
    GraphError,
)


# Microsoft's static GUID for the Global Administrator directory role
# template. The actual roleId in directoryRoles varies per tenant; the
# template id is stable.
GLOBAL_ADMIN_ROLE_TEMPLATE_ID = "62e90394-69f5-4237-9190-012177145e10"

# Strong vs weak MFA methods, per CIS 1.1.3 guidance. The list isn't
# exhaustive — it's the set Graph emits today; new method types fall
# through to "weak" so unknown methods don't get a free pass.
STRONG_MFA_METHODS = {
    "#microsoft.graph.fido2AuthenticationMethod",
    "#microsoft.graph.windowsHelloForBusinessAuthenticationMethod",
    "#microsoft.graph.microsoftAuthenticatorAuthenticationMethod",
    "#microsoft.graph.softwareOathAuthenticationMethod",
    "#microsoft.graph.temporaryAccessPassAuthenticationMethod",
}


def collect_facts(client: GraphClient) -> dict:
    """Single function so it's straightforward to mock in unit tests."""
    facts: dict = {}

    # 1.1.1 — Security Defaults state.
    sd = client.get("/policies/identitySecurityDefaultsEnforcementPolicy")
    facts["security_defaults_enabled"] = bool(sd.get("isEnabled", False))

    # 1.1.2 + 1.1.3 — Global Administrators (members of the Global
    # Admin directory role template). Each admin's MFA methods are
    # fetched per-user via /authentication/methods.
    roles = client.get_all("/directoryRoles")
    global_admin_role_id = None
    for r in roles:
        if r.get("roleTemplateId") == GLOBAL_ADMIN_ROLE_TEMPLATE_ID:
            global_admin_role_id = r.get("id")
            break

    global_admins: list = []
    if global_admin_role_id:
        members = client.get_all(f"/directoryRoles/{global_admin_role_id}/members")
        for m in members:
            uid = m.get("id")
            if not uid:
                continue
            try:
                methods = client.get_all(
                    f"/users/{uid}/authentication/methods"
                )
            except GraphError:
                methods = []
            global_admins.append(
                {
                    "id": uid,
                    "display_name": m.get("displayName"),
                    "user_principal_name": m.get("userPrincipalName"),
                    "mfa_methods": [
                        meth.get("@odata.type") for meth in methods
                    ],
                    "has_strong_mfa": any(
                        meth.get("@odata.type") in STRONG_MFA_METHODS
                        for meth in methods
                    ),
                }
            )
    facts["global_admins"] = global_admins

    # 1.1.4 — Conditional Access policies. We don't analyze them
    # here; Rego does. We just shape the data.
    ca = client.get_all("/identity/conditionalAccess/policies")
    facts["conditional_access_policies"] = [
        {
            "id": p.get("id"),
            "display_name": p.get("displayName"),
            "state": p.get("state"),    # enabled | enabledForReportingButNotEnforced | disabled
            "conditions": p.get("conditions", {}),
            "grant_controls": p.get("grantControls", {}),
        }
        for p in ca
    ]

    # 1.1.5 — PIM role assignments. The endpoint requires the Premium
    # P2 license; if Graph returns 403 we fall back to an empty list
    # and flag it so Rego can emit a "not configured" violation
    # rather than failing the whole assessment.
    try:
        pim = client.get_all("/roleManagement/directory/roleEligibilityScheduleInstances")
    except GraphError:
        pim = []
    facts["pim_role_assignments"] = [
        {
            "principal_id": item.get("principalId"),
            "role_definition_id": item.get("roleDefinitionId"),
            "status": item.get("status"),
        }
        for item in pim
    ]
    facts["pim_available"] = bool(pim)

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
