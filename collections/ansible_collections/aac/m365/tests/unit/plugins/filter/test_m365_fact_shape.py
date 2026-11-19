"""Shape capture records structure, never tenant content."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

UNIT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "m365_shape", UNIT.parents[1] / "plugins" / "filter" / "m365_shape.py")
m365_shape = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m365_shape)

SECRETS = ["jane@contoso.com", "contoso.com", "Contoso Finance Policy",
           "00000000-0000-0000-0000-0000000000ab", "192.0.2.10", "free text reason"]

FACTS = {
    "sharepoint": {"tenant": {"SharingCapability": "ExternalUserAndGuestSharing",
                              "DefaultLinkPermission": 2}, "collected": True},
    "exchange": {
        "transport_rules": [
            {"Name": "Contoso Finance Policy", "State": "Enabled", "SetSCL": -1,
             "SenderDomainIs": ["contoso.com"]},
            {"Name": "Second", "State": "Disabled", "SetSCL": None},
        ],
        "audit_bypass_associations": [],
        "shared_mailboxes": [{"UserPrincipalName": "jane@contoso.com",
                              "ExternalDirectoryObjectId": "00000000-0000-0000-0000-0000000000ab"}],
        "unavailable": {"sharing_policies": "free text reason"},
        "verified_domains": [{"id": "contoso.com", "spf_present": False}],
    },
    "defender": {"connection_filter_policies": [{"Name": "Default", "IPAllowList": ["192.0.2.10"]}]},
    "admin_center": {"user_sign_in_state": {"00000000-0000-0000-0000-0000000000ab": {"account_enabled": True}}},
    "teams": {"federation_configuration": {"AllowedDomains": {"AllowAllKnownDomains": {}}}},
    "attestations": [{"control_id": "5.2.4.1", "attested_by": "jane@contoso.com", "observed": True}],
}


def _doc():
    return m365_shape.m365_fact_shape(FACTS)


def test_no_tenant_content_in_the_document():
    text = json.dumps(_doc())
    for secret in SECRETS:
        assert secret not in text, secret


def test_list_shape_union_and_types():
    rules = _doc()["sections"]["exchange"]["transport_rules"]
    assert rules["type"] == "array"
    assert (rules["min_length"], rules["max_length"]) == (2, 2)
    fields = rules["items"]["fields"]
    assert set(fields) == {"Name", "State", "SetSCL", "SenderDomainIs"}
    assert fields["SenderDomainIs"]["present_in"] == 1
    assert fields["SetSCL"]["type"] == ["null", "number"]
    assert fields["Name"]["type"] == "string" and "values" not in fields["Name"]


def test_allowlisted_enum_values_are_recorded():
    doc = _doc()["sections"]
    rules = doc["exchange"]["transport_rules"]["items"]["fields"]
    assert rules["State"]["values"] == ["Disabled", "Enabled"]
    assert rules["SetSCL"]["values"] == [-1]
    tenant = doc["sharepoint"]["tenant"]["fields"]
    # an enum arriving as an int is exactly what the capture must show
    assert tenant["DefaultLinkPermission"] == {"type": "number", "present_in": 1, "values": [2]}
    assert tenant["SharingCapability"]["values"] == ["ExternalUserAndGuestSharing"]


def test_empty_list_and_free_text_maps():
    doc = _doc()["sections"]["exchange"]
    assert doc["audit_bypass_associations"] == {"type": "array", "min_length": 0, "max_length": 0}
    assert doc["unavailable"]["fields"]["sharing_policies"] == {"type": "string", "present_in": 1}


def test_maps_keyed_by_ids_do_not_list_keys():
    sign_in = _doc()["sections"]["admin_center"]["user_sign_in_state"]
    assert sign_in["type"] == "object"
    assert "fields" not in sign_in
    assert sign_in["max_key_count"] == 1 and sign_in["value_types"] == ["object"]


def test_nested_object_structure_is_kept():
    allowed = _doc()["sections"]["teams"]["federation_configuration"]["fields"]["AllowedDomains"]
    assert allowed["type"] == "object"
    assert "AllowAllKnownDomains" in allowed["fields"]


def test_too_many_distinct_values_are_suppressed():
    rows = [{"State": "S%d" % i} for i in range(m365_shape.MAX_VALUES + 1)]
    shape = m365_shape.shape_of(rows)
    assert "values" not in shape["items"]["fields"]["State"]
    assert "values_suppressed" in shape["items"]["fields"]["State"]
