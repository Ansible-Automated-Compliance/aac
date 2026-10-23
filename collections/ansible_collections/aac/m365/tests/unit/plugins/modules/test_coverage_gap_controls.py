"""Unit tests for the six controls that closed the m365_v7 coverage gap.

Until 2026-08-25 these were in no bucket at all -- 1.2.2, 1.3.3, 2.4.1,
5.1.6.1, 5.3.4 and 5.3.5 were neither evaluated nor flagged, so the
assessment described a 154-recommendation benchmark. Rego PR #65 made
them visible; this is the collector side that makes them measurable.

Every query here is written from the benchmark's own Audit procedure
rather than inferred from the control title, so the tests assert the
shape CIS documents:

  1.2.2    Get-EXOMailbox -RecipientTypeDetails SharedMailbox, joined to
           Graph AccountEnabled on the directory object id
  1.3.3    Get-SharingPolicy -> Enabled must be False
  2.4.1    Get-EmailTenantSettings -> EnablePriorityAccountProtection,
           AND Get-ProtectionAlert (Security & Compliance) for a passing
           Phish alert and a passing Malware alert
  5.1.6.1  /beta/legacy/policies -> B2BManagementPolicy, whose definition
           is a JSON *string*
  5.3.4    roleManagementPolicyAssignments -> policyId ->
  5.3.5    .../rules/Approval_EndUser_Assignment -> isApprovalRequired

The recurring assertion is that a fact which could not be read lands in
`unavailable` rather than being defaulted. An absent fact that reads as
a value is the defect the whole v7 tree exists to prevent.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
COLLECTIONS_PATH = REPO_ROOT / "collections"
if str(COLLECTIONS_PATH) not in sys.path:
    sys.path.insert(0, str(COLLECTIONS_PATH))


GA_ROLE = "62e90394-69f5-4237-9190-012177145e10"
PRA_ROLE = "e8611ab8-c189-46e8-94e1-60213ab1f814"


class FakeGraphClient:
    """Implements the try_* surface the collectors actually call.

    Returns (value, None) on success and (None, reason) on a recorded
    failure -- the same contract as the real client, whose whole point is
    that a caller cannot mistake an error for data.
    """

    def __init__(self, responses: dict, errors: dict | None = None):
        self.responses = responses
        self.errors = errors or {}
        self.calls: list[str] = []

    def _resolve(self, path: str):
        self.calls.append(path)
        if path in self.errors:
            return None, self.errors[path]
        if path not in self.responses:
            raise AssertionError(f"unexpected call: {path}")
        return self.responses[path], None

    def try_get(self, path, params=None, beta=False):
        return self._resolve(("beta:" if beta else "") + path)

    def try_get_all(self, path, params=None, beta=False):
        return self._resolve(("beta:" if beta else "") + path)


class FakePwsh:
    """Matches PwshRunner.try_run: (value, None) or (None, reason).

    Snippets are matched by substring so a test pins the cmdlet CIS
    names without restating the whole Select-Object projection.
    """

    def __init__(self, responses: dict, errors: dict | None = None):
        self.responses = responses
        self.errors = errors or {}
        self.snippets: list[str] = []

    def try_run(self, snippet):
        self.snippets.append(snippet)
        for needle, reason in self.errors.items():
            if needle in snippet:
                return None, reason
        for needle, value in self.responses.items():
            if needle in snippet:
                return value, None
        return [], None


# ── 1.3.3 and 1.2.2 -- Exchange Online ───────────────────────────────

from ansible_collections.aac.m365.plugins.modules import m365_exchange_ps_facts


class TestExchangeSectionOneControls:
    def test_1_3_3_sharing_policies_are_collected(self):
        runner = FakePwsh({
            "Get-SharingPolicy": [
                {"Name": "Default Sharing Policy", "Enabled": True, "Default": True},
            ],
        })
        facts = m365_exchange_ps_facts.collect_facts(runner)
        assert facts["sharing_policies"][0]["Enabled"] is True
        assert "sharing_policies" not in facts["unavailable"]

    def test_1_3_3_queries_every_policy_not_just_the_default(self):
        # A second enabled policy shares calendars just as effectively.
        runner = FakePwsh({"Get-SharingPolicy": []})
        m365_exchange_ps_facts.collect_facts(runner)
        sharing = [s for s in runner.snippets if "Get-SharingPolicy" in s]
        assert sharing, "Get-SharingPolicy was never run"
        assert "-Identity" not in sharing[0]

    def test_1_2_2_shared_mailboxes_carry_the_join_key(self):
        # CIS joins Exchange to Graph on ExternalDirectoryObjectId.
        runner = FakePwsh({
            "Get-EXOMailbox -RecipientTypeDetails SharedMailbox": [
                {"UserPrincipalName": "shared@example.com",
                 "ExternalDirectoryObjectId": "obj-1",
                 "DisplayName": "Shared"},
            ],
        })
        facts = m365_exchange_ps_facts.collect_facts(runner)
        assert facts["shared_mailboxes"][0]["ExternalDirectoryObjectId"] == "obj-1"

    def test_1_2_2_enumerates_all_shared_mailboxes(self):
        runner = FakePwsh({"Get-EXOMailbox -RecipientTypeDetails SharedMailbox": []})
        m365_exchange_ps_facts.collect_facts(runner)
        mbx = [s for s in runner.snippets
               if "Get-EXOMailbox -RecipientTypeDetails SharedMailbox" in s]
        assert "-ResultSize Unlimited" in mbx[0], "a sampled list would miss mailboxes"

    def test_a_failed_query_is_recorded_not_defaulted(self):
        runner = FakePwsh({}, errors={"Get-SharingPolicy": "insufficient permissions"})
        facts = m365_exchange_ps_facts.collect_facts(runner)
        assert "sharing_policies" in facts["unavailable"]
        assert "sharing_policies" not in facts


# ── 1.2.2 -- the Graph half ──────────────────────────────────────────

from ansible_collections.aac.m365.plugins.modules import m365_admin_center_facts


def _admin_center_responses(users):
    """Minimum viable payload: every other endpoint errors, which the
    module records and moves past. Only the 1.2.2 path is under test."""
    errors = {
        "/directoryRoles": "not under test",
        "/groups": "not under test",
        "/domains": "not under test",
        "/policies/activityBasedTimeoutPolicies": "not under test",
        "beta:/admin/appsAndServices": "not under test",
        "beta:/admin/forms": "not under test",
        "/servicePrincipals": "not under test",
    }
    return {"/users": users}, errors


class TestAdminCenterSignInState:
    def test_sign_in_state_is_keyed_by_directory_object_id(self):
        responses, errors = _admin_center_responses([
            {"id": "obj-1", "userPrincipalName": "shared@example.com",
             "accountEnabled": False},
        ])
        client = FakeGraphClient(responses, errors)
        facts = m365_admin_center_facts.collect_facts(client)
        assert facts["user_sign_in_state"]["obj-1"]["account_enabled"] is False
        assert facts["user_sign_in_state_count"] == 1

    def test_users_without_an_id_are_dropped(self):
        responses, errors = _admin_center_responses([
            {"userPrincipalName": "nokey@example.com", "accountEnabled": True},
        ])
        facts = m365_admin_center_facts.collect_facts(FakeGraphClient(responses, errors))
        assert facts["user_sign_in_state"] == {}

    def test_unreadable_users_endpoint_is_recorded(self):
        responses, errors = _admin_center_responses([])
        errors["/users"] = "Directory.Read.All not granted"
        facts = m365_admin_center_facts.collect_facts(FakeGraphClient(responses, errors))
        assert "user_sign_in_state" in facts["unavailable"]
        assert "user_sign_in_state" not in facts


# ── 2.4.1 -- Defender priority account protection ────────────────────

from ansible_collections.aac.m365.plugins.modules import m365_defender_ps_facts


class TestPriorityAccountProtection:
    def test_both_halves_are_collected(self):
        runner = FakePwsh({
            "Get-EmailTenantSettings": {"EnablePriorityAccountProtection": True},
        })
        ipps = FakePwsh({
            "Get-ProtectionAlert": [
                {"Name": "Phish", "Severity": "High", "ThreatType": "Phish",
                 "RecipientTags": "Priority account", "NotificationEnabled": True,
                 "Disabled": False},
            ],
        })
        facts = m365_defender_ps_facts.collect_facts(runner, ipps_runner=ipps)
        assert facts["email_tenant_settings"]["EnablePriorityAccountProtection"] is True
        assert facts["priority_account_alerts"][0]["ThreatType"] == "Phish"

    def test_alerts_are_filtered_to_priority_accounts(self):
        runner = FakePwsh({"Get-EmailTenantSettings": {}})
        ipps = FakePwsh({"Get-ProtectionAlert": []})
        m365_defender_ps_facts.collect_facts(runner, ipps_runner=ipps)
        alert = [s for s in ipps.snippets if "Get-ProtectionAlert" in s]
        assert "Priority account" in alert[0]

    def test_missing_compliance_session_blocks_only_2_4_1(self):
        # A tenant that cannot open Connect-IPPSSession still gets every
        # other Defender control.
        runner = FakePwsh({
            "Get-EmailTenantSettings": {"EnablePriorityAccountProtection": True},
            "Get-SafeLinksPolicy": [{"Name": "default"}],
        })
        facts = m365_defender_ps_facts.collect_facts(runner, ipps_runner=None)
        assert "2.4.1" in facts["unavailable"]["priority_account_alerts"]
        assert "safe_links_policies" in facts

    def test_tenant_setting_failure_names_the_control_it_blocks(self):
        runner = FakePwsh({}, errors={"Get-EmailTenantSettings": "cmdlet not found"})
        facts = m365_defender_ps_facts.collect_facts(runner, ipps_runner=None)
        assert "2.4.1" in facts["unavailable"]["email_tenant_settings"]


# ── 5.1.6.1, 5.3.4, 5.3.5 -- Entra ───────────────────────────────────

from ansible_collections.aac.m365.plugins.modules import m365_entra_facts


ASSIGN_PATH = "/policies/roleManagementPolicyAssignments"


def _approval_rule(required, approvers):
    return {"setting": {
        "isApprovalRequired": required,
        "approvalStages": [{"primaryApprovers": approvers}],
    }}


def _rule_path(policy_id):
    return ("/policies/roleManagementPolicies/%s"
            "/rules/Approval_EndUser_Assignment" % policy_id)


def _pim(responses, errors=None):
    facts, unavailable = {}, {}
    m365_entra_facts.collect_pim_approval(
        FakeGraphClient(responses, errors), facts, unavailable)
    return facts, unavailable


class TestPimApprovalControls:
    def test_both_roles_are_read_through_two_hops(self):
        facts, unavailable = _pim({
            ASSIGN_PATH: [{"policyId": "pol-x"}],
            _rule_path("pol-x"): _approval_rule(True, [{"id": "u1"}, {"id": "u2"}]),
        })
        assert unavailable == {}
        assert facts["pim_approval_%s" % GA_ROLE]["is_approval_required"] is True
        assert facts["pim_approval_%s" % PRA_ROLE]["primary_approver_count"] == 2

    def test_approvers_are_counted_across_every_stage(self):
        rule = {"setting": {"isApprovalRequired": True, "approvalStages": [
            {"primaryApprovers": [{"id": "a"}]},
            {"primaryApprovers": [{"id": "b"}, {"id": "c"}]},
        ]}}
        facts, _ = _pim({ASSIGN_PATH: [{"policyId": "p"}], _rule_path("p"): rule})
        assert facts["pim_approval_%s" % GA_ROLE]["primary_approver_count"] == 3

    def test_approval_required_with_no_approvers_is_reported_as_zero(self):
        # CIS requires isApprovalRequired AND at least one approver. The
        # collector must not conflate them -- the Rego needs both.
        facts, _ = _pim({
            ASSIGN_PATH: [{"policyId": "p"}],
            _rule_path("p"): _approval_rule(True, []),
        })
        got = facts["pim_approval_%s" % GA_ROLE]
        assert got["is_approval_required"] is True
        assert got["primary_approver_count"] == 0

    def test_role_not_governed_by_pim_is_unavailable_not_false(self):
        # "PIM does not manage this role" and "approval is switched off"
        # are different findings; reporting the first as the second would
        # invent a measurement.
        facts, unavailable = _pim({ASSIGN_PATH: []})
        assert facts == {}
        reason = unavailable["pim_approval_%s" % GA_ROLE]
        assert "does not govern" in reason and "5.3.4" in reason

    def test_unreadable_rule_names_the_control_it_blocks(self):
        facts, unavailable = _pim(
            {ASSIGN_PATH: [{"policyId": "p"}]},
            errors={_rule_path("p"): "RoleManagement.Read.All not granted"},
        )
        assert facts == {}
        assert "5.3.5" in unavailable["pim_approval_%s" % PRA_ROLE]

    def test_role_definition_guids_are_the_ones_cis_names(self):
        ids = [r[2] for r in m365_entra_facts.PIM_APPROVAL_ROLES]
        assert ids == [GA_ROLE, PRA_ROLE]


def _b2b(responses, errors=None):
    facts, unavailable = {}, {}
    m365_entra_facts.collect_b2b_management_policy(
        FakeGraphClient(responses, errors), facts, unavailable)
    return facts, unavailable


def _definition(**domains):
    import json
    return json.dumps({"B2BManagementPolicy": {
        "InvitationsAllowedAndBlockedDomainsPolicy": domains}})


LEGACY = "beta:/legacy/policies"


class TestB2bManagementPolicy:
    def test_definition_is_parsed_from_its_json_string(self):
        # The Graph payload nests a JSON *string*, not an object.
        facts, unavailable = _b2b({LEGACY: [
            {"type": "B2BManagementPolicy",
             "definition": _definition(AllowedDomains=["contoso.com"])},
        ]})
        assert unavailable == {}
        got = facts["b2b_management_policy"]
        assert got["allowed_domains"] == ["contoso.com"]
        assert got["blocked_domains_present"] is False

    def test_empty_allowed_domains_is_distinguished_from_absent(self):
        # CIS treats an EMPTY AllowedDomains as compliant (it permits
        # nothing) and an absent one as unrestricted. Collapsing None to
        # [] would invert the control, so the collector reports presence
        # separately from contents.
        empty, _ = _b2b({LEGACY: [
            {"type": "B2BManagementPolicy", "definition": _definition(AllowedDomains=[])},
        ]})
        absent, _ = _b2b({LEGACY: [
            {"type": "B2BManagementPolicy", "definition": _definition()},
        ]})
        assert empty["b2b_management_policy"]["allowed_domains_present"] is True
        assert empty["b2b_management_policy"]["allowed_domains"] == []
        assert absent["b2b_management_policy"]["allowed_domains_present"] is False

    def test_blocked_domains_presence_is_surfaced(self):
        facts, _ = _b2b({LEGACY: [
            {"type": "B2BManagementPolicy",
             "definition": _definition(BlockedDomains=["evil.example"])},
        ]})
        assert facts["b2b_management_policy"]["blocked_domains_present"] is True

    def test_policy_absent_is_a_readable_state_not_a_failure(self):
        facts, unavailable = _b2b({LEGACY: [{"type": "SomethingElse"}]})
        assert unavailable == {}
        assert facts["b2b_management_policy"] == {"policy_present": False}

    def test_unparseable_definition_is_unavailable_not_empty(self):
        facts, unavailable = _b2b({LEGACY: [
            {"type": "B2BManagementPolicy", "definition": "{not json"},
        ]})
        assert facts == {}
        assert "5.1.6.1" in unavailable["b2b_management_policy"]

    def test_unreadable_endpoint_is_recorded(self):
        facts, unavailable = _b2b({}, errors={LEGACY: "Policy.Read.All not granted"})
        assert facts == {}
        assert "5.1.6.1" in unavailable["b2b_management_policy"]
