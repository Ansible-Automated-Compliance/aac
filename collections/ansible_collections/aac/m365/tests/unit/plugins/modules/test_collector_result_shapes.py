"""Recorded-shape fixtures for the PowerShell and Graph collectors.

Fixtures are constructed from Microsoft's documented shapes (cited in the
collector source), never captured from a tenant. RecordingPwsh plays back
what PowerShell PRINTS for a cmdlet that emits `rows`, under the shape the
collector asks for, and applies the runner's own normalisation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT / "collections") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "collections"))

from ansible_collections.aac.m365.plugins.module_utils import pwsh  # noqa: E402
from ansible_collections.aac.m365.plugins.modules import (  # noqa: E402
    m365_defender_ps_facts as defender,
    m365_entra_facts as entra,
    m365_exchange_facts as exchange_graph,
    m365_exchange_ps_facts as exchange,
    m365_purview_ps_facts as purview,
    m365_teams_ps_facts as teams,
)


class RecordingPwsh:
    def __init__(self, rows_by_cmdlet=None, default_rows=None):
        self.rows = rows_by_cmdlet or {}
        self.default_rows = default_rows if default_rows is not None else [{"Name": "Default"}]
        self.calls = []

    def try_run(self, snippet, shape="raw"):
        self.calls.append((snippet, shape))
        rows = self.default_rows
        for needle in sorted(self.rows, key=len, reverse=True):
            if needle in snippet:
                rows = self.rows[needle]
                break
        if shape == pwsh.LIST:
            # ConvertTo-Json -InputObject @(...) prints an array, always.
            return pwsh.as_list(list(rows))
        if shape == pwsh.OBJECT:
            return pwsh.as_object(rows[0] if len(rows) == 1 else list(rows))
        raise AssertionError("collector asked for a RAW result: %s" % snippet)


# ── per-key shape decisions (pinned so a change is deliberate) ───────

EXPECTED_SHAPES = {
    exchange: {
        "organization_config": pwsh.OBJECT, "transport_config": pwsh.OBJECT,
        "sharing_policies": pwsh.LIST, "shared_mailboxes": pwsh.LIST,
        "transport_rules": pwsh.LIST, "outbound_spam_policies": pwsh.LIST,
        "external_in_outlook": pwsh.LIST, "role_assignment_policies": pwsh.LIST,
        "owa_mailbox_policies": pwsh.LIST, "audit_bypass_associations": pwsh.LIST,
    },
    defender: {
        "safe_links_policies": pwsh.LIST, "malware_filter_policies": pwsh.LIST,
        "safe_attachment_policies": pwsh.LIST, "atp_policy_for_o365": pwsh.OBJECT,
        "outbound_spam_policies": pwsh.LIST, "anti_phish_policies": pwsh.LIST,
        "connection_filter_policies": pwsh.LIST, "content_filter_policies": pwsh.LIST,
        "eop_protection_rules": pwsh.LIST, "atp_protection_rules": pwsh.LIST,
        "dkim_signing_configs": pwsh.LIST, "teams_protection_policy": pwsh.OBJECT,
    },
    teams: {
        "client_configuration": pwsh.OBJECT, "federation_configuration": pwsh.OBJECT,
        "meeting_policies": pwsh.LIST, "messaging_policies": pwsh.LIST,
    },
    purview: {"dlp_policies": pwsh.LIST, "label_policies": pwsh.LIST},
}


@pytest.mark.parametrize("module", list(EXPECTED_SHAPES), ids=lambda m: m.__name__.split(".")[-1])
def test_every_query_declares_the_expected_shape(module):
    assert {k: v[2] for k, v in module.QUERIES.items()} == EXPECTED_SHAPES[module]


def test_no_collector_asks_for_a_raw_result():
    RecordingPwsh().try_run  # noqa: B018 - RecordingPwsh raises on RAW
    exchange.collect_facts(RecordingPwsh())
    defender.collect_facts(RecordingPwsh(), ipps_runner=RecordingPwsh())
    teams.collect_facts(RecordingPwsh(default_rows=[{"Identity": "Global"}]))
    purview.collect_facts(RecordingPwsh())


# ── single row, zero rows, many rows ─────────────────────────────────

def test_single_row_collections_arrive_as_one_element_lists():
    facts = exchange.collect_facts(RecordingPwsh())
    for key, shape in EXPECTED_SHAPES[exchange].items():
        if shape == pwsh.LIST:
            assert facts[key] == [{"Name": "Default"}], key
        else:
            assert facts[key] == {"Name": "Default"}, key
    assert facts["unavailable"] == {}


def test_zero_rows_are_an_empty_list_not_a_gap():
    # 6.1.3: a compliant tenant has no bypass association. The HEAD script
    # printed nothing and the key was recorded unavailable on every
    # compliant tenant; now it is [] and the control can pass.
    facts = exchange.collect_facts(RecordingPwsh({"Get-MailboxAuditBypassAssociation": [],
                                                  "Get-TransportRule": [],
                                                  "Get-EXOMailbox -RecipientTypeDetails": []}))
    assert facts["audit_bypass_associations"] == []
    assert facts["transport_rules"] == []
    assert facts["shared_mailboxes"] == []
    assert "audit_bypass_associations" not in facts["unavailable"]


def test_many_rows_are_kept():
    rows = [{"Name": "Default"}, {"Name": "Strict"}, {"Name": "Custom"}]
    facts = defender.collect_facts(RecordingPwsh({"Get-SafeLinksPolicy": rows}), ipps_runner=RecordingPwsh())
    assert [p["Name"] for p in facts["safe_links_policies"]] == ["Default", "Strict", "Custom"]


def test_an_organisation_object_that_arrives_twice_is_unavailable():
    facts = exchange.collect_facts(RecordingPwsh({"Get-OrganizationConfig": [{"A": 1}, {"A": 2}]}))
    assert "organization_config" not in facts
    assert "exactly one" in facts["unavailable"]["organization_config"]
    assert "6.1.1" in facts["unavailable"]["organization_config"]   # blocks list


def test_teams_global_policy_from_a_single_row():
    facts = teams.collect_facts(RecordingPwsh(default_rows=[{"Identity": "Global"}]))
    assert facts["meeting_policies"] == [{"Identity": "Global"}]
    assert facts["meeting_policies_global"] == {"Identity": "Global"}


def test_mailbox_audit_sample_with_one_mailbox():
    facts = exchange.collect_facts(RecordingPwsh(
        {"Get-EXOMailbox -ResultSize": [{"UserPrincipalName": "u@contoso.com", "AuditEnabled": False}]}))
    assert facts["mailbox_audit"]["sampled"] == 1
    assert facts["mailbox_audit"]["audit_disabled"] == [{"user_principal_name": "u@contoso.com"}]


# ── field names confirmed from the documentation ─────────────────────

def test_2_1_11_selects_file_types_and_publishes_both_names():
    snippet = defender.QUERIES["malware_filter_policies"][0]
    assert "FileTypes" in snippet and "FileTypeFilter" not in snippet
    facts = defender.collect_facts(RecordingPwsh(
        {"Get-MalwareFilterPolicy": [{"Identity": "Default", "FileTypes": ["exe", "bat"]}]}),
        ipps_runner=RecordingPwsh())
    pol = facts["malware_filter_policies"][0]
    assert pol["FileTypes"] == ["exe", "bat"]
    assert pol["FileTypeFilter"] == ["exe", "bat"]


def test_2_1_11_missing_file_types_reads_as_empty_not_null():
    facts = defender.collect_facts(RecordingPwsh(
        {"Get-MalwareFilterPolicy": [{"Identity": "Default", "FileTypes": None}]}),
        ipps_runner=RecordingPwsh())
    assert facts["malware_filter_policies"][0]["FileTypeFilter"] == []


def test_8_5_8_property_is_selected():
    assert "AllowExternalNonTrustedMeetingChat" in teams.QUERIES["meeting_policies"][0]


def test_6_3_2_personal_accounts_property_is_selected():
    assert "PersonalAccountsEnabled" in exchange.QUERIES["owa_mailbox_policies"][0]


class FakeGraph:
    def __init__(self, responses):
        self.responses = responses

    def try_get(self, path, params=None, beta=False):
        if path in self.responses:
            return self.responses[path], None
        return {}, None

    def try_get_all(self, path, params=None, beta=False):
        return [], None


# authenticationMethodConfigurations ids as the v1.0 GET example returns them.
AUTH_METHODS = {"authenticationMethodConfigurations": [
    {"id": "MicrosoftAuthenticator", "state": "enabled", "featureSettings": {
        "numberMatchingRequiredState": {"state": "enabled"},
        "displayAppInformationRequiredState": {"state": "default"},
        "displayLocationInformationRequiredState": {"state": "enabled"},
        "companionAppAllowedState": {"state": "enabled"}}},
    {"id": "Sms", "state": "enabled"},
    {"id": "Voice", "state": "disabled"},
    {"id": "Email", "state": "enabled"},
    {"id": "Fido2", "state": "enabled"},
]}


def test_5_2_3_x_auth_method_ids_are_matched_case_insensitively():
    facts, unavailable = {}, {}
    entra._authentication_methods(
        FakeGraph({"/policies/authenticationMethodsPolicy": AUTH_METHODS}), facts, unavailable)
    assert facts["weak_methods_enabled"] == ["sms"]                 # 5.2.3.5
    assert facts["email_otp_state"] == "enabled"                    # 5.2.3.7
    assert facts["authenticator"]["state"] == "enabled"             # 5.2.3.1
    assert facts["authenticator"]["show_app_information_state"] == "default"
    assert facts["authenticator"]["companion_app_allowed_state"] == "enabled"   # 5.2.3.10
    assert set(facts["authentication_methods"]) == {"MicrosoftAuthenticator", "Sms", "Voice", "Email", "Fido2"}


def _drp(join_type, registering_type, laps=False):
    # beta deviceRegistrationPolicy GET example shape
    return {
        "userDeviceQuota": 2,
        "multiFactorAuthConfiguration": "notRequired",
        "azureADJoin": {
            "isAdminConfigurable": True,
            "allowedToJoin": {"@odata.type": join_type},
            "localAdmins": {"enableGlobalAdmins": True,
                            "registeringUsers": {"@odata.type": registering_type, "users": [], "groups": []}},
        },
        "localAdminPassword": {"isEnabled": laps},
    }


ALL = "#microsoft.graph.allDeviceRegistrationMembership"
ENUM = "#microsoft.graph.enumeratedDeviceRegistrationMembership"
NONE = "#microsoft.graph.noDeviceRegistrationMembership"


@pytest.mark.parametrize("join, reg, expect_join, expect_reg", [
    (ALL, ALL, "all", "all"),
    (ENUM, NONE, "selected", "none"),
    ("microsoft.graph.noDeviceRegistrationMembership", ENUM, "none", "selected"),
])
def test_5_1_4_1_and_5_1_4_4_read_the_membership_type(join, reg, expect_join, expect_reg):
    facts, unavailable = {}, {}
    entra._device_registration(_drp(join, reg), facts, unavailable)
    assert unavailable == {}
    assert facts["device_registration"]["azure_ad_join_allowed_to_join"] == expect_join
    assert facts["device_registration"]["local_admin_registering_user_enabled"] == expect_reg


def test_unknown_membership_is_unavailable_not_none():
    facts, unavailable = {}, {}
    drp = _drp(ALL, ALL)
    drp["azureADJoin"]["allowedToJoin"] = {"appliesTo": "1"}      # the old, wrong key
    entra._device_registration(drp, facts, unavailable)
    assert "device_registration" not in facts
    assert "5.1.4.1" in unavailable["device_registration_policy"]


def test_5_1_4_5_laps_is_read_from_the_same_policy_object():
    facts, unavailable = {}, {}
    entra._device_registration(_drp(ALL, ALL, laps=True), facts, unavailable)
    assert facts["laps_enabled"] is True
    facts, unavailable = {}, {}
    drp = _drp(ALL, ALL)
    del drp["localAdminPassword"]
    entra._device_registration(drp, facts, unavailable)
    assert "laps_enabled" not in facts and "5.1.4.5" in unavailable["laps_policy"]


# ── published-DNS resolver against dnspython's documented exceptions ─

def test_dns_resolver_maps_dnspython_outcomes(monkeypatch):
    dns_resolver = pytest.importorskip("dns.resolver")
    import dns.exception

    class Answer(list):
        pass

    class TXT:
        def __init__(self, *parts):
            self.strings = [p.encode() for p in parts]

    outcomes = {
        "contoso.com": Answer([TXT("v=spf1 ", "-all")]),
        "_dmarc.contoso.com": dns_resolver.NXDOMAIN(),
        "slow.contoso.com": dns.exception.Timeout(),
        "dead.contoso.com": dns_resolver.NoNameservers(),
    }

    def fake_resolve(self, name, rtype):
        out = outcomes[name]
        if isinstance(out, Exception):
            raise out
        return out

    monkeypatch.setattr(dns_resolver.Resolver, "resolve", fake_resolve)
    r = exchange_graph.DnsResolver(timeout=1)
    assert r.query("contoso.com", "TXT") == ["v=spf1 -all"]
    assert r.query("_dmarc.contoso.com", "TXT") == []
    with pytest.raises(exchange_graph.DnsLookupError):
        r.query("slow.contoso.com", "TXT")
    with pytest.raises(exchange_graph.DnsLookupError):
        r.query("dead.contoso.com", "TXT")
