#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_admin_center_facts — collect CIS M365 v7.0.0 Section 1 state.

Section 1 (Microsoft 365 admin center) has 15 recommendations. This
module collects the Graph-sourced ones. The Exchange-sourced ones
(1.3.3, 1.3.6, 1.3.9, and the mailbox half of 1.2.2) are collected by
m365_exchange_ps_facts; 1.1.2 and 1.3.8 remain unresolved.

Control -> Graph endpoint, taken from the cmdlets CIS names in each
control's Audit procedure rather than inferred:

  1.1.1  cloud-only admin accounts     /directoryRoles, /members, onPremisesSyncEnabled
  1.1.3  two-to-four global admins     /directoryRoles/{ga}/members
  1.1.4  reduced-footprint licences    /users/{id}/licenseDetails
  1.2.1  no unmanaged public groups    /groups?$filter=visibility
  1.3.1  password never expires        /domains passwordValidityPeriodInDays
  1.3.2  idle session timeout <= 3h    /policies/activityBasedTimeoutPolicies
  1.3.4  user-owned apps restricted    /admin/appsAndServices        (beta)
  1.3.5  Forms phishing protection     /admin/forms                  (beta)
  1.3.7  third-party storage           /servicePrincipals
  1.2.2  shared-mailbox sign-in        /users?$select=id,accountEnabled
         (Graph half; joined in Rego to the Exchange mailbox list)

Every fact that could not be collected is recorded in `unavailable`
rather than defaulted, so the Rego fails closed on it instead of
evaluating a value nobody measured.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: m365_admin_center_facts
short_description: Collect Microsoft 365 admin center state for CIS v7.0.0 Section 1
description:
  - Authenticates to Microsoft Graph via Entra app registration
    (client credentials) and collects the tenant state that CIS
    Microsoft 365 Foundations Benchmark v7.0.0 Section 1 evaluates.
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
  user_sample_size:
    description:
      - Maximum number of privileged users to expand licence detail for.
      - Guards against a very large directory turning one control into
        thousands of Graph calls.
    type: int
    default: 100
author:
  - "AAC maintainers"
notes:
  - >-
    Required application permissions: RoleManagement.Read.Directory,
    Group.Read.All, Domain.Read.All, Policy.Read.All,
    Application.Read.All, User.Read.All, and
    OrgSettings-AppsAndServices.Read.All plus OrgSettings-Forms.Read.All
    for controls 1.3.4 and 1.3.5.
"""

EXAMPLES = r"""
- name: Collect M365 admin center state for CIS v7.0.0 Section 1
  aac.m365.m365_admin_center_facts:
    tenant_id: "{{ m365_tenant_id }}"
    client_id: "{{ m365_client_id }}"
    client_secret: "{{ m365_client_secret }}"
  register: admin_center

- name: Evaluate against OPA
  ansible.builtin.uri:
    url: "{{ opa_security_url }}/v1/data/cis_m365_v7/admin_center/compliance_report"
    method: POST
    body_format: json
    body:
      input:
        admin_center: "{{ admin_center.facts }}"
"""

RETURN = r"""
facts:
  description: Section 1 tenant state.
  returned: always
  type: dict
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.aac.m365.plugins.module_utils.graph import (
    GraphClient,
    GraphError,
)

GLOBAL_ADMIN_ROLE = "Global Administrator"


def _role_members(client, facts, unavailable):
    """CIS 1.1.1 / 1.1.3 / 1.1.4 all start from the Global Administrator
    role membership, so resolve it once."""
    roles, err = client.try_get_all("/directoryRoles")
    if err:
        unavailable["global_admins"] = err
        return None

    ga = next((r for r in roles if r.get("displayName") == GLOBAL_ADMIN_ROLE), None)
    if ga is None:
        # An activated-roles list without Global Administrator is a real
        # finding, not a collection gap -- record it as an empty set.
        facts["global_admin_role_activated"] = False
        return []

    facts["global_admin_role_activated"] = True
    members, err = client.try_get_all(f"/directoryRoles/{ga['id']}/members")
    if err:
        unavailable["global_admins"] = err
        return None
    return members


def _expand_admins(client, members, sample, facts, unavailable):
    """CIS 1.1.1 needs onPremisesSyncEnabled per admin; 1.1.4 needs the
    licences assigned to each."""
    admins, licence_gap = [], None
    for m in members[:sample]:
        uid = m.get("id")
        if not uid:
            continue
        rec = {
            "id": uid,
            "display_name": m.get("displayName"),
            "user_principal_name": m.get("userPrincipalName"),
            # Present on the member object when Graph expands it; fall back
            # to an explicit lookup rather than assuming cloud-only.
            "on_premises_sync_enabled": m.get("onPremisesSyncEnabled"),
        }
        if rec["on_premises_sync_enabled"] is None:
            user, err = client.try_get(f"/users/{uid}?$select=onPremisesSyncEnabled,userPrincipalName")
            if err:
                unavailable.setdefault("admin_sync_state", err)
            else:
                rec["on_premises_sync_enabled"] = user.get("onPremisesSyncEnabled")
        lic, err = client.try_get_all(f"/users/{uid}/licenseDetails")
        if err:
            licence_gap = licence_gap or err
        else:
            rec["licenses"] = [
                {"sku_part_number": l.get("skuPartNumber"), "sku_id": l.get("skuId")}
                for l in lic
            ]
        admins.append(rec)

    if licence_gap:
        unavailable["admin_licenses"] = licence_gap
    facts["global_admins"] = admins
    facts["global_admin_count"] = len(members)
    facts["global_admins_sampled"] = len(admins)


def collect_facts(client, sample=100):
    facts, unavailable = {}, {}

    # ── 1.1.1 / 1.1.3 / 1.1.4 -- privileged accounts ──────────────────
    members = _role_members(client, facts, unavailable)
    if members is not None:
        _expand_admins(client, members, sample, facts, unavailable)

    # ── 1.2.1 -- public groups must be organizationally approved ──────
    groups, err = client.try_get_all(
        "/groups", params={"$select": "id,displayName,visibility,groupTypes"}
    )
    if err:
        unavailable["groups"] = err
    else:
        facts["public_groups"] = [
            {"id": g.get("id"), "display_name": g.get("displayName")}
            for g in groups
            if g.get("visibility") == "Public"
        ]
        facts["group_count"] = len(groups)

    # ── 1.3.1 -- password expiration policy ───────────────────────────
    domains, err = client.try_get_all("/domains")
    if err:
        unavailable["domains"] = err
    else:
        facts["domains"] = [
            {
                "id": d.get("id"),
                "is_verified": bool(d.get("isVerified")),
                # CIS wants 2147483647 ("never expire") on every domain.
                "password_validity_period_in_days": d.get("passwordValidityPeriodInDays"),
            }
            for d in domains
        ]

    # ── 1.3.2 -- idle session timeout ─────────────────────────────────
    timeouts, err = client.try_get_all("/policies/activityBasedTimeoutPolicies")
    if err:
        unavailable["activity_based_timeout"] = err
    else:
        facts["activity_based_timeout_policies"] = [
            {"id": p.get("id"), "display_name": p.get("displayName"),
             "is_organization_default": p.get("isOrganizationDefault"),
             "definition": p.get("definition", [])}
            for p in timeouts
        ]

    # ── 1.3.4 / 1.3.5 -- admin center org settings (beta only) ────────
    apps, err = client.try_get("/admin/appsAndServices", beta=True)
    if err:
        unavailable["apps_and_services"] = err
    else:
        settings = apps.get("settings", {})
        facts["user_owned_apps_and_services"] = {
            "is_office_store_enabled": settings.get("isOfficeStoreEnabled"),
            "is_app_and_services_trial_enabled": settings.get("isAppAndServicesTrialEnabled"),
        }

    forms, err = client.try_get("/admin/forms", beta=True)
    if err:
        unavailable["forms"] = err
    else:
        settings = forms.get("settings", {})
        facts["forms"] = {
            "is_internal_phishing_protection_enabled":
                settings.get("isInternalPhishingProtectionEnabled"),
        }

    # ── 1.3.7 -- third-party storage services ─────────────────────────
    sps, err = client.try_get_all(
        "/servicePrincipals",
        params={"$filter": "startswith(displayName,'Office 365 SharePoint Online')",
                "$select": "id,displayName,accountEnabled,appId"},
    )
    if err:
        unavailable["service_principals"] = err
    else:
        facts["third_party_storage_service_principals"] = [
            {"id": s.get("id"), "display_name": s.get("displayName"),
             "account_enabled": s.get("accountEnabled")}
            for s in sps
        ]

    # ── 1.2.2 -- sign-in state, for the shared-mailbox join ───────────
    # CIS's procedure is two-step: Get-EXOMailbox lists the shared
    # mailboxes, then Get-MgUser reports AccountEnabled for each. The
    # Exchange half runs in m365_exchange_ps_facts; this is the Graph
    # half, keyed by directory object id so the Rego can join on the same
    # key CIS does.
    #
    # Fetched as a map of ALL users rather than per-mailbox lookups: the
    # collectors run independently, so this one cannot know which ids the
    # Exchange collector found. `$select` keeps the payload to three
    # fields. If a shared mailbox's id is absent from this map, the Rego
    # reports the control as unevaluated rather than passing it -- an
    # absent user is not an account that is blocked.
    users, err = client.try_get_all(
        "/users", params={"$select": "id,userPrincipalName,accountEnabled"}
    )
    if err:
        unavailable["user_sign_in_state"] = err
    else:
        facts["user_sign_in_state"] = {
            u["id"]: {
                "user_principal_name": u.get("userPrincipalName"),
                "account_enabled": u.get("accountEnabled"),
            }
            for u in users if u.get("id")
        }
        facts["user_sign_in_state_count"] = len(facts["user_sign_in_state"])

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
            user_sample_size=dict(type="int", default=100),
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
        facts = collect_facts(client, sample=module.params["user_sample_size"])
    except GraphError as exc:
        # Only auth/token failures reach here -- per-endpoint failures are
        # captured in facts.unavailable so partial collection still yields
        # an evaluable, honestly-scoped result.
        module.fail_json(
            msg=f"Microsoft Graph error: {exc.status} at {exc.request_path}",
            details=exc.body[:2000],
        )
        return
    module.exit_json(changed=False, facts=facts)


if __name__ == "__main__":
    main()
