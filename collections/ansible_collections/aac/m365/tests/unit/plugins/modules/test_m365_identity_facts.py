"""Unit tests for m365_identity_facts.

We mock the GraphClient so no actual Microsoft Graph calls are
made. The point is to pin:

  - Security Defaults state is read from the policy endpoint.
  - Global admins are pulled from the directoryRoles role-template-id
    matching the Global Administrator template GUID.
  - Each admin gets their MFA methods enumerated.
  - has_strong_mfa is true only when at least one method is in
    STRONG_MFA_METHODS.
  - PIM 403 fallback: the module records an empty list and
    pim_available=false rather than failing.
  - Conditional Access policies are normalized to id /
    display_name / state / conditions / grant_controls.

The ansible_collections.* import path is wired up by the
package-level conftest.py — we don't manipulate sys.path here.
"""
from __future__ import annotations

import pytest

from ansible_collections.aac.m365.plugins.modules import m365_identity_facts


GLOBAL_ADMIN_TEMPLATE_ID = m365_identity_facts.GLOBAL_ADMIN_ROLE_TEMPLATE_ID
STRONG_METHODS = m365_identity_facts.STRONG_MFA_METHODS


class FakeGraphClient:
    """Lightweight stub. Each test sets the `responses` dict mapping
    Graph paths → return values. Unknown paths raise so tests fail
    loud instead of silently masking a regression."""

    def __init__(self, responses: dict, raises: set | None = None):
        self.responses = responses
        self.raises = raises or set()

    def get(self, path: str, params=None):
        if path in self.raises:
            from ansible_collections.aac.m365.plugins.module_utils.graph import GraphError
            raise GraphError(403, "synthetic forbidden", path)
        if path not in self.responses:
            raise AssertionError(f"unexpected get({path})")
        return self.responses[path]

    def get_all(self, path: str, params=None):
        if path in self.raises:
            from ansible_collections.aac.m365.plugins.module_utils.graph import GraphError
            raise GraphError(403, "synthetic forbidden", path)
        if path not in self.responses:
            raise AssertionError(f"unexpected get_all({path})")
        return self.responses[path]


# ── Security Defaults ────────────────────────────────────────────────


def test_security_defaults_enabled_is_read_from_policy_endpoint():
    client = FakeGraphClient(
        {
            "/policies/identitySecurityDefaultsEnforcementPolicy": {
                "isEnabled": True,
            },
            "/directoryRoles": [],
            "/identity/conditionalAccess/policies": [],
            "/roleManagement/directory/roleEligibilityScheduleInstances": [],
        }
    )
    facts = m365_identity_facts.collect_facts(client)
    assert facts["security_defaults_enabled"] is True


def test_security_defaults_disabled_when_isenabled_false():
    client = FakeGraphClient(
        {
            "/policies/identitySecurityDefaultsEnforcementPolicy": {
                "isEnabled": False,
            },
            "/directoryRoles": [],
            "/identity/conditionalAccess/policies": [],
            "/roleManagement/directory/roleEligibilityScheduleInstances": [],
        }
    )
    facts = m365_identity_facts.collect_facts(client)
    assert facts["security_defaults_enabled"] is False


# ── Global admins ────────────────────────────────────────────────────


def _baseline_responses(global_admin_members, member_methods=None):
    """Set up the minimum response set with `global_admin_members`
    in the Global Admin directory role. `member_methods` is a dict
    of user_id → list of methods to return for that user."""
    member_methods = member_methods or {}
    responses = {
        "/policies/identitySecurityDefaultsEnforcementPolicy": {"isEnabled": False},
        "/directoryRoles": [
            {"id": "role-ga-1", "roleTemplateId": GLOBAL_ADMIN_TEMPLATE_ID},
        ],
        "/directoryRoles/role-ga-1/members": global_admin_members,
        "/identity/conditionalAccess/policies": [],
        "/roleManagement/directory/roleEligibilityScheduleInstances": [],
    }
    for uid, methods in member_methods.items():
        responses[f"/users/{uid}/authentication/methods"] = methods
    return responses


def test_global_admins_extracted_from_global_admin_role():
    client = FakeGraphClient(
        _baseline_responses(
            global_admin_members=[
                {
                    "id": "alice-uid",
                    "displayName": "Alice Admin",
                    "userPrincipalName": "alice@example.com",
                }
            ],
            member_methods={"alice-uid": []},
        )
    )
    facts = m365_identity_facts.collect_facts(client)
    assert len(facts["global_admins"]) == 1
    assert facts["global_admins"][0]["id"] == "alice-uid"
    assert facts["global_admins"][0]["display_name"] == "Alice Admin"


def test_has_strong_mfa_true_when_at_least_one_strong_method():
    strong = next(iter(STRONG_METHODS))
    client = FakeGraphClient(
        _baseline_responses(
            global_admin_members=[{"id": "u1", "displayName": "u1"}],
            member_methods={"u1": [{"@odata.type": strong}]},
        )
    )
    facts = m365_identity_facts.collect_facts(client)
    assert facts["global_admins"][0]["has_strong_mfa"] is True


def test_has_strong_mfa_false_with_only_weak_methods():
    client = FakeGraphClient(
        _baseline_responses(
            global_admin_members=[{"id": "u1", "displayName": "u1"}],
            member_methods={
                "u1": [
                    {"@odata.type": "#microsoft.graph.passwordAuthenticationMethod"},
                    {"@odata.type": "#microsoft.graph.smsAuthenticationMethod"},
                ]
            },
        )
    )
    facts = m365_identity_facts.collect_facts(client)
    assert facts["global_admins"][0]["has_strong_mfa"] is False


# ── PIM fallback ─────────────────────────────────────────────────────


def test_pim_403_results_in_empty_list_and_pim_available_false():
    """PIM endpoint requires Entra Premium P2. Tenants without it
    return 403. We don't want that to fail the whole assessment;
    Rego should emit a 'PIM not configured' violation instead."""
    responses = _baseline_responses(global_admin_members=[], member_methods={})
    raises = {"/roleManagement/directory/roleEligibilityScheduleInstances"}
    client = FakeGraphClient(responses, raises=raises)
    facts = m365_identity_facts.collect_facts(client)
    assert facts["pim_role_assignments"] == []
    assert facts["pim_available"] is False


def test_pim_available_true_when_endpoint_returns_data():
    responses = _baseline_responses(global_admin_members=[], member_methods={})
    responses["/roleManagement/directory/roleEligibilityScheduleInstances"] = [
        {
            "principalId": "user-x",
            "roleDefinitionId": "role-y",
            "status": "Provisioned",
        }
    ]
    client = FakeGraphClient(responses)
    facts = m365_identity_facts.collect_facts(client)
    assert facts["pim_available"] is True
    assert len(facts["pim_role_assignments"]) == 1


# ── Conditional Access shape ────────────────────────────────────────


def test_conditional_access_policies_are_normalized():
    responses = _baseline_responses(global_admin_members=[], member_methods={})
    responses["/identity/conditionalAccess/policies"] = [
        {
            "id": "ca-1",
            "displayName": "Require MFA for all users",
            "state": "enabled",
            "conditions": {"users": {"includeUsers": ["All"]}},
            "grantControls": {"builtInControls": ["mfa"]},
            "extraField": "ignored",
        }
    ]
    client = FakeGraphClient(responses)
    facts = m365_identity_facts.collect_facts(client)
    assert len(facts["conditional_access_policies"]) == 1
    p = facts["conditional_access_policies"][0]
    assert p["id"] == "ca-1"
    assert p["display_name"] == "Require MFA for all users"
    assert p["state"] == "enabled"
    assert p["conditions"] == {"users": {"includeUsers": ["All"]}}
    assert p["grant_controls"]["builtInControls"] == ["mfa"]
    # The extra field is stripped — we only carry what Rego uses.
    assert "extraField" not in p
