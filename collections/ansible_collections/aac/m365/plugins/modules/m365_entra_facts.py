#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_entra_facts — collect CIS M365 v7.0.0 Section 5 state.

Section 5 (Microsoft Entra admin center) is the largest in the benchmark:
63 of its 160 recommendations. This collector covers the ones the
benchmark's own Audit procedure reaches through Microsoft Graph.

The single highest-value endpoint is /policies/authorizationPolicy, which
carries SEVEN controls on its own (5.1.2.2, 5.1.2.3, 5.1.3.1, 5.1.4.6,
5.1.5.1, 5.1.6.2, 5.1.6.3). It is fetched once and the Rego reads
different fields from it.

Control -> endpoint, from the cmdlets CIS names in each Audit procedure:

  5.1.2.1              /beta/users/{id}/authentication/requirements
  5.1.2.2 5.1.2.3      /policies/authorizationPolicy
  5.1.3.1 5.1.4.6
  5.1.5.1 5.1.6.2 5.1.6.3
  5.1.5.2              /policies/adminConsentRequestPolicy
  5.1.8.1              /directory/onPremisesSynchronization
  5.2.2.x 5.3.1        /identity/conditionalAccess/policies, PIM eligibility
  5.2.3.2 5.2.3.3      /groupSettings                       (password protection)
  5.2.3.4              /reports/authenticationMethods/userRegistrationDetails
  5.2.3.5 5.2.3.6 5.2.3.7  /policies/authenticationMethodsPolicy

NOT collected here, deliberately: 5.1.6.1 (allowed collaboration domains)
and 5.3.4 (GA activation approval). CIS names no cmdlet for either and we
have not established their endpoint. Guessing one and emitting a default
would manufacture a result -- they stay unresolved until the live-tenant
probe.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: m365_entra_facts
short_description: Collect Microsoft Entra state for CIS v7.0.0 Section 5
description:
  - Authenticates to Microsoft Graph via Entra app registration
    (client credentials) and collects the identity state that CIS
    Microsoft 365 Foundations Benchmark v7.0.0 Section 5 evaluates.
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
  mfa_report_limit:
    description:
      - Maximum user rows to pull from the authentication-method
        registration report for control 5.2.3.4.
    type: int
    default: 999
author:
  - "AAC maintainers"
notes:
  - >-
    Required application permissions: Policy.Read.All,
    Directory.Read.All, RoleManagement.Read.Directory,
    AuditLog.Read.All and UserAuthenticationMethod.Read.All.
  - >-
    Control 5.1.2.1 reads a /beta endpoint. Microsoft documents /beta as
    subject to change and unsupported for production; the fact carries an
    api_version marker so the evaluation can record that caveat.
"""

EXAMPLES = r"""
- name: Collect Entra state for CIS v7.0.0 Section 5
  aac.m365.m365_entra_facts:
    tenant_id: "{{ m365_tenant_id }}"
    client_id: "{{ m365_client_id }}"
    client_secret: "{{ m365_client_secret }}"
  register: entra

- name: Evaluate against OPA
  ansible.builtin.uri:
    url: "{{ opa_security_url }}/v1/data/cis_m365_v7/entra/compliance_report"
    method: POST
    body_format: json
    body:
      input:
        entra: "{{ entra.facts }}"
"""

RETURN = r"""
facts:
  description: Section 5 tenant state.
  returned: always
  type: dict
"""

import json

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.aac.m365.plugins.module_utils.graph import (
    GraphClient,
    GraphError,
)

GLOBAL_ADMIN_ROLE = "Global Administrator"
# Methods the benchmark treats as weak for 5.2.3.5.
WEAK_METHODS = ("sms", "voice")


def object_scope(review):
    """Access review scope is nested and shape-varying; flatten just the
    query string so the policy can tell a guest review from a privileged
    role review without reaching through four optional levels."""
    scope = review.get("scope", {}) or {}
    return scope.get("query", "")


def _authorization_policy(client, facts, unavailable):
    """One call, seven controls. Field -> control:

      allowedToCreateApps                 5.1.2.2
      defaultUserRolePermissions          5.1.3.1, 5.1.4.6
      allowedToCreateTenants              5.1.2.3
      permissionGrantPolicyIdsAssigned    5.1.5.1
      guestUserRoleId                     5.1.6.2
      allowInvitesFrom                    5.1.6.3
    """
    pol, err = client.try_get("/policies/authorizationPolicy")
    if err:
        unavailable["authorization_policy"] = err
        return
    perms = pol.get("defaultUserRolePermissions", {}) or {}
    facts["authorization_policy"] = {
        "allowed_to_create_apps": perms.get("allowedToCreateApps"),
        "allowed_to_create_security_groups": perms.get("allowedToCreateSecurityGroups"),
        "allowed_to_create_tenants": perms.get("allowedToCreateTenants"),
        "allowed_to_read_bitlocker_keys_for_owned_device":
            perms.get("allowedToReadBitlockerKeysForOwnedDevice"),
        "permission_grant_policy_ids_assigned":
            perms.get("permissionGrantPoliciesAssigned", []),
        "guest_user_role_id": pol.get("guestUserRoleId"),
        "allow_invites_from": pol.get("allowInvitesFrom"),
    }


def _authentication_methods(client, facts, unavailable):
    """5.2.3.5 weak methods, 5.2.3.6 system-preferred MFA, 5.2.3.7 email OTP."""
    pol, err = client.try_get("/policies/authenticationMethodsPolicy")
    if err:
        unavailable["authentication_methods_policy"] = err
        return
    configs = {c.get("id"): c for c in pol.get("authenticationMethodConfigurations", [])}
    facts["authentication_methods"] = {
        mid: {"state": cfg.get("state")} for mid, cfg in configs.items()
    }
    facts["weak_methods_enabled"] = sorted(
        m for m in WEAK_METHODS
        if configs.get(m, {}).get("state") == "enabled"
    )
    facts["email_otp_state"] = configs.get("email", {}).get("state")

    # 5.2.3.1 / 5.2.3.10 -- Microsoft Authenticator feature settings. These
    # ride on the same policy object already fetched above; they were simply
    # not being projected.
    authenticator = configs.get("microsoftAuthenticator", {}) or {}
    features = authenticator.get("featureSettings", {}) or {}
    facts["authenticator"] = {
        "state": authenticator.get("state"),
        "number_matching_state": (features.get("numberMatchingRequiredState", {}) or {}).get("state"),
        "show_app_information_state": (features.get("displayAppInformationRequiredState", {}) or {}).get("state"),
        "show_geographic_location_state": (features.get("displayLocationInformationRequiredState", {}) or {}).get("state"),
        "companion_app_allowed_state": (features.get("companionAppAllowedState", {}) or {}).get("state"),
    }
    # systemCredentialPreferences is the system-preferred MFA switch.
    facts["system_preferred_mfa_state"] = (
        pol.get("systemCredentialPreferences", {}) or {}
    ).get("state")


# The two role definition ids CIS names in the 5.3.4 / 5.3.5 audit
# procedures. These are the well-known built-in role GUIDs and are
# identical in every tenant.
PIM_APPROVAL_ROLES = (
    ("5.3.4", "Global Administrator", "62e90394-69f5-4237-9190-012177145e10"),
    ("5.3.5", "Privileged Role Administrator", "e8611ab8-c189-46e8-94e1-60213ab1f814"),
)


def collect_pim_approval(client, facts, unavailable):
    """5.3.4 / 5.3.5 -- approval required to activate a privileged role.

    Two hops, both on Graph v1.0, exactly as CIS documents:

      1. roleManagementPolicyAssignments filtered to the role definition
         -> policyId
      2. roleManagementPolicies/{policyId}/rules/Approval_EndUser_Assignment
         -> isApprovalRequired + approvalStages.primaryApprovers

    A role PIM does not govern is reported as unavailable, not as
    non-compliant: "no policy assignment" and "approval switched off" are
    different findings and an auditor needs to be told which.
    """
    for control, role_name, role_id in PIM_APPROVAL_ROLES:
        key = "pim_approval_%s" % role_id
        assignments, err = client.try_get_all(
            "/policies/roleManagementPolicyAssignments",
            params={
                "$filter": (
                    "scopeId eq '/' and scopeType eq 'DirectoryRole' "
                    "and roleDefinitionId eq '%s'" % role_id
                ),
                "$select": "policyId",
            },
        )
        if err:
            unavailable[key] = "%s (blocks %s)" % (err, control)
            continue
        policy_id = next((a.get("policyId") for a in assignments if a.get("policyId")), None)
        if not policy_id:
            unavailable[key] = (
                "no roleManagementPolicyAssignment for the %s role -- PIM does "
                "not govern its activation (blocks %s)" % (role_name, control)
            )
            continue
        rule, err = client.try_get(
            "/policies/roleManagementPolicies/%s/rules/Approval_EndUser_Assignment" % policy_id
        )
        if err:
            unavailable[key] = "%s (blocks %s)" % (err, control)
            continue
        setting = rule.get("setting") or {}
        approvers = []
        for stage in setting.get("approvalStages") or []:
            approvers.extend(stage.get("primaryApprovers") or [])
        facts[key] = {
            "control": control,
            "role": role_name,
            "policy_id": policy_id,
            "is_approval_required": setting.get("isApprovalRequired"),
            "primary_approver_count": len(approvers),
        }


def collect_b2b_management_policy(client, facts, unavailable):
    """5.1.6.1 -- collaboration invitations only to allowed domains.

    CIS reads the B2BManagementPolicy out of /beta/legacy/policies and
    parses its `definition`, which is a JSON *string* rather than a
    nested object -- the trap in this endpoint.

    Per the benchmark, compliant means an AllowedDomains list is present
    (an EMPTY list is explicitly compliant: it permits nothing) and no
    BlockedDomains property, since a block list is an
    allow-everything-else posture. The parsing happens here; the verdict
    is the Rego's.
    """
    legacy, err = client.try_get_all("/legacy/policies", beta=True)
    if err:
        unavailable["b2b_management_policy"] = "%s (blocks 5.1.6.1)" % err
        return
    b2b = next((p for p in legacy if p.get("type") == "B2BManagementPolicy"), None)
    if b2b is None:
        # No policy object at all means no domain restriction is in place.
        # That is a readable state, not a collection failure.
        facts["b2b_management_policy"] = {"policy_present": False}
        return
    definition = b2b.get("definition")
    if isinstance(definition, list):
        definition = definition[0] if definition else "{}"
    try:
        parsed = json.loads(definition or "{}")
        domains = (
            parsed.get("B2BManagementPolicy", {})
            .get("InvitationsAllowedAndBlockedDomainsPolicy", {})
        ) or {}
    except (ValueError, AttributeError, TypeError) as exc:
        unavailable["b2b_management_policy"] = (
            "B2BManagementPolicy definition is not parseable JSON: %s "
            "(blocks 5.1.6.1)" % exc
        )
        return
    facts["b2b_management_policy"] = {
        "policy_present": True,
        # Distinguish "absent" from "present but empty" -- CIS treats
        # those two states oppositely, so None must not collapse to [].
        "allowed_domains": domains.get("AllowedDomains"),
        "allowed_domains_present": "AllowedDomains" in domains,
        "blocked_domains": domains.get("BlockedDomains"),
        "blocked_domains_present": "BlockedDomains" in domains,
    }


def collect_facts(client, mfa_limit=999):
    facts, unavailable = {}, {}

    _authorization_policy(client, facts, unavailable)
    _authentication_methods(client, facts, unavailable)

    # ── 5.1.4.x -- device registration (beta only) ────────────────────
    # Five controls from one policy object. CIS documents these as Entra
    # portal steps and names no cmdlet, so this reaches the benchmark's
    # answer by a path it does not describe.
    drp, err = client.try_get("/policies/deviceRegistrationPolicy", beta=True)
    if err:
        unavailable["device_registration_policy"] = err
    else:
        azure_ad_join = drp.get("azureADJoin", {}) or {}
        local_admins = azure_ad_join.get("localAdmins", {}) or {}
        facts["device_registration"] = {
            "azure_ad_join_allowed_to_join": azure_ad_join.get("appliesTo"),
            "azure_ad_join_is_admin_configurable": azure_ad_join.get("isAdminConfigurable"),
            "user_device_quota": drp.get("userDeviceQuota"),
            "local_admin_registering_user_enabled":
                (local_admins.get("registeringUsers", {}) or {}).get("appliesTo"),
            "local_admin_global_admins_enabled":
                (local_admins.get("enableGlobalAdmins")),
            "multi_factor_auth_configuration": drp.get("multiFactorAuthConfiguration"),
            "api_version": "beta",
        }

    # 5.1.4.5 -- Local Administrator Password Solution is a separate
    # directory setting, not part of the device registration policy.
    laps, err = client.try_get("/policies/deviceRegistrationPolicy/localAdminPassword", beta=True)
    if err:
        # Older tenants do not expose this sub-resource at all; record it
        # rather than inferring LAPS is off.
        unavailable["laps_policy"] = err
    else:
        facts["laps_enabled"] = laps.get("isEnabled")

    # ── 5.1.5.x -- application management policy ──────────────────────
    # Four controls: password addition blocked, password lifetime,
    # system-generated passwords, certificate lifetime.
    amp, err = client.try_get("/policies/defaultAppManagementPolicy")
    if err:
        unavailable["app_management_policy"] = err
    else:
        app_restrictions = (amp.get("applicationRestrictions", {}) or {})
        facts["app_management"] = {
            "is_enabled": amp.get("isEnabled"),
            "password_credentials": app_restrictions.get("passwordCredentials", []),
            "key_credentials": app_restrictions.get("keyCredentials", []),
        }

    # ── 5.3.2 / 5.3.3 -- access reviews ───────────────────────────────
    reviews, err = client.try_get_all("/identityGovernance/accessReviews/definitions")
    if err:
        unavailable["access_reviews"] = err
    else:
        facts["access_reviews"] = [
            {
                "id": r.get("id"),
                "display_name": r.get("displayName"),
                "status": r.get("status"),
                "scope_query": object_scope(r),
            }
            for r in reviews
        ]

    # ── 5.1.5.2 -- admin consent workflow ─────────────────────────────
    pol, err = client.try_get("/policies/adminConsentRequestPolicy")
    if err:
        unavailable["admin_consent_request_policy"] = err
    else:
        facts["admin_consent_workflow_enabled"] = pol.get("isEnabled")

    # ── 5.1.8.1 -- password hash sync for hybrid deployments ──────────
    sync, err = client.try_get("/directory/onPremisesSynchronization")
    if err:
        unavailable["on_premises_synchronization"] = err
    else:
        # Graph returns a collection here; take the tenant's configuration.
        entries = sync.get("value", [sync]) if isinstance(sync, dict) else []
        cfg = (entries[0] if entries else {}).get("features", {}) or {}
        facts["on_premises_sync"] = {
            "configured": bool(entries),
            "password_sync_enabled": cfg.get("passwordSyncEnabled"),
        }

    # ── 5.2.2.x / 5.3.1 -- Conditional Access and PIM ─────────────────
    ca, err = client.try_get_all("/identity/conditionalAccess/policies")
    if err:
        unavailable["conditional_access_policies"] = err
    else:
        facts["conditional_access_policies"] = [
            {
                "id": p.get("id"),
                "display_name": p.get("displayName"),
                "state": p.get("state"),
                "conditions": p.get("conditions", {}),
                "grant_controls": p.get("grantControls", {}),
                # sessionControls carries sign-in frequency, persistent
                # browser, token protection and reauthentication -- four
                # section 5.2.2 controls that are invisible without it.
                "session_controls": p.get("sessionControls", {}),
            }
            for p in ca
        ]

    # 5.2.2.14 / 5.2.2.15 -- trusted and geographic named locations.
    locations, err = client.try_get_all("/identity/conditionalAccess/namedLocations")
    if err:
        unavailable["named_locations"] = err
    else:
        facts["named_locations"] = [
            {
                "id": l.get("id"),
                "display_name": l.get("displayName"),
                "odata_type": l.get("@odata.type"),
                "is_trusted": l.get("isTrusted"),
                "countries_and_regions": l.get("countriesAndRegions", []),
            }
            for l in locations
        ]

    pim, err = client.try_get_all("/roleManagement/directory/roleEligibilityScheduleInstances")
    if err:
        unavailable["pim_role_assignments"] = err
    else:
        facts["pim_role_assignments"] = [
            {"principal_id": i.get("principalId"),
             "role_definition_id": i.get("roleDefinitionId")}
            for i in pim
        ]
        facts["pim_available"] = len(pim) > 0

    collect_pim_approval(client, facts, unavailable)
    collect_b2b_management_policy(client, facts, unavailable)

    # ── 5.2.3.2 / 5.2.3.3 -- password protection settings ─────────────
    settings, err = client.try_get_all("/groupSettings")
    if err:
        unavailable["group_settings"] = err
    else:
        # Three controls read from this one payload -- password protection
        # (5.2.3.2 / 5.2.3.3), smart lockout (5.2.3.8 / 5.2.3.9) and M365 group
        # creation (5.1.3.4). Collected in a single pass so every
        # groupSettings-derived key is gathered in one place.
        PWD_KEYS = ("BannedPasswordList", "EnableBannedPasswordCheck",
                    "EnableBannedPasswordCheckOnPremises",
                    "BannedPasswordCheckOnPremisesMode")
        LOCKOUT_KEYS = ("LockoutThreshold", "LockoutDurationInSeconds")
        GROUP_KEYS = ("EnableGroupCreation", "GroupCreationAllowedGroupId")

        gs = {}
        for s in settings:
            for v in s.get("values", []):
                if v.get("name") in PWD_KEYS + LOCKOUT_KEYS + GROUP_KEYS:
                    gs[v["name"]] = v.get("value")

        # `settings_present` means "the payload carried settings in this group
        # at all", so it is true if ANY key in the group came back. Testing one
        # specific key would report a tenant that returned only the other key as
        # unconfigured, which reads downstream as "nothing to assess" rather
        # than "partially configured".
        facts["password_protection"] = {
            "custom_banned_list": gs.get("BannedPasswordList", ""),
            "banned_password_check_enabled": gs.get("EnableBannedPasswordCheck"),
            "on_premises_check_enabled": gs.get("EnableBannedPasswordCheckOnPremises"),
            "on_premises_mode": gs.get("BannedPasswordCheckOnPremisesMode"),
            "settings_present": any(k in gs for k in PWD_KEYS),
        }
        facts["lockout"] = {
            "threshold": gs.get("LockoutThreshold"),
            "duration_seconds": gs.get("LockoutDurationInSeconds"),
            "settings_present": any(k in gs for k in LOCKOUT_KEYS),
        }
        facts["group_creation"] = {
            "enabled": gs.get("EnableGroupCreation"),
            "allowed_group_id": gs.get("GroupCreationAllowedGroupId", ""),
            "settings_present": any(k in gs for k in GROUP_KEYS),
        }

    # ── 5.2.3.4 -- member users must be MFA capable ───────────────────
    report, err = client.try_get_all(
        "/reports/authenticationMethods/userRegistrationDetails",
        params={"$top": mfa_limit},
    )
    if err:
        unavailable["mfa_registration_report"] = err
    else:
        members = [r for r in report if r.get("userType") == "member"]
        facts["mfa_registration"] = {
            "members_total": len(members),
            "members_not_mfa_capable": [
                {"user_principal_name": r.get("userPrincipalName")}
                for r in members if r.get("isMfaCapable") is False
            ],
            "report_rows": len(report),
        }

    # ── 5.1.2.1 -- per-user MFA must be disabled (beta) ───────────────
    # CIS marks this Manual, but /beta exposes perUserMfaState directly.
    # The beta dependency is recorded so the evaluation can carry it as an
    # evidence caveat rather than presenting it as a v1.0 guarantee.
    users, err = client.try_get_all(
        "/users", params={"$select": "id,userPrincipalName", "$top": mfa_limit}
    )
    if err:
        unavailable["per_user_mfa"] = err
    else:
        legacy, gap = [], None
        for u in users:
            req, e = client.try_get(
                f"/users/{u['id']}/authentication/requirements", beta=True
            )
            if e:
                gap = gap or e
                break
            if req.get("perUserMfaState") in ("enabled", "enforced"):
                legacy.append({"user_principal_name": u.get("userPrincipalName"),
                               "state": req.get("perUserMfaState")})
        if gap:
            unavailable["per_user_mfa"] = gap
        else:
            facts["per_user_mfa"] = {
                "users_checked": len(users),
                "legacy_per_user_mfa": legacy,
                "api_version": "beta",
            }

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
            mfa_report_limit=dict(type="int", default=999),
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
        facts = collect_facts(client, mfa_limit=module.params["mfa_report_limit"])
    except GraphError as exc:
        module.fail_json(
            msg=f"Microsoft Graph error: {exc.status} at {exc.request_path}",
            details=exc.body[:2000],
        )
        return
    module.exit_json(changed=False, facts=facts)


if __name__ == "__main__":
    main()
