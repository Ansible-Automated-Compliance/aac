# -*- coding: utf-8 -*-
"""Describe the SHAPE of collected M365 facts, never their content.

Used by the role's opt-in shape-capture mode (m365_shape_capture). The
document it produces lets the items that could not be settled without a
tenant -- enum serialisation, empty results, nested property shapes -- be
settled from one real assessment, without the capture carrying tenant data.

What is recorded, per fact key:
  - the JSON type(s) of every value;
  - for arrays: the minimum and maximum length, and the merged shape of
    the elements (for arrays of objects: the union of field names, how
    many rows carry each field, and each field's JSON types);
  - for objects: field names, but only when every key looks like a
    property name (an identifier or an OData annotation) and there are at
    most MAX_KEYS of them; otherwise
    only the key count and the value types -- maps keyed by object ids,
    user names or domains are therefore never listed;
  - distinct VALUES only for scalar fields whose name is on
    VALUE_ALLOWLIST: closed Microsoft enumerations, booleans and numeric
    settings. At most MAX_VALUES distinct values of at most MAX_VALUE_LEN
    characters are kept; anything more is reported as suppressed.

What is never recorded: any string value of a field not on the allowlist
(names, addresses, domains, tenant and object ids, mailbox data, free
text such as `unavailable` reasons or attestation fields).
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re

DOCUMENTATION = r"""
name: m365_fact_shape
short_description: Describe the JSON shape of collected CIS M365 facts without their values
description:
  - Returns, for every fact key, the JSON types, list lengths, field-name
    unions and field types. Distinct values are recorded only for scalar
    fields on an allowlist of non-sensitive configuration fields.
options:
  _input:
    description: The assembled fact document (the policy input).
    type: dict
    required: true
"""

MAX_KEYS = 64
MAX_VALUES = 25
MAX_VALUE_LEN = 64

# A key is listed only when it looks like a property name: an identifier,
# or an OData annotation ("@odata.type", "includeTargets@odata.context").
# Dots, '@' elsewhere, spaces and leading digits all fail, so domains,
# addresses, GUIDs and display names used as map keys are never listed.
_PROPERTY_NAME = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*|[A-Za-z]*@odata\.[A-Za-z]+)$")

# Fields whose distinct values are recorded. Every entry is a Microsoft
# configuration setting with a closed value set (enum), a boolean, or a
# number -- never a name, address, identifier or free text. The reason
# for each group is the question the capture has to answer.
VALUE_ALLOWLIST = frozenset([
    # Exchange / Defender enums compared by name in the policy (6.2.1,
    # 6.2.2, 2.4.1) and the transport-rule SCL compared as -1 (6.2.2).
    "State", "AutoForwardingMode", "SetSCL", "Severity", "ThreatType",
    "Action", "ActionWhenThresholdReached", "AuthenticationFailAction",
    "PhishThresholdLevel", "Priority",
    # Defender / Exchange booleans the rules read.
    "Enabled", "IsEnabled", "Enable", "IsDefault", "Default", "Disabled",
    "NotificationEnabled", "EnableFileFilter", "EnableInternalSenderAdminNotifications",
    "EnableSafeLinksForOffice", "EnableSafeLinksForEmail", "EnableSafeLinksForTeams",
    "EnableATPForSPOTeamsODB", "NotifyOutboundSpam", "EnableSafeList", "ZapEnabled",
    "EnablePriorityAccountProtection", "AuditBypassEnabled", "AuditEnabled",
    "AuditDisabled", "OAuth2ClientProfileEnabled", "MailTipsAllTipsEnabled",
    "MailTipsExternalRecipientsTipsEnabled", "RejectDirectSend", "CustomerLockBoxEnabled",
    "BookingsEnabled", "BookingsAuthEnabled", "BookingsSocialSharingRestricted",
    "SmtpClientAuthenticationDisabled", "AdditionalStorageProvidersAvailable",
    "PersonalAccountsEnabled",
    # Numeric outbound-spam limits (2.1.15).
    "RecipientLimitExternalPerHour", "RecipientLimitInternalPerHour", "RecipientLimitPerDay",
    # Purview DLP / label enums (3.2.x): Mode and the Workload flags enum.
    "Mode", "Workload",
    # SharePoint (PnP) CSOM enums (7.2.x) and booleans.
    "SharingCapability", "OneDriveSharingCapability", "DefaultSharingLinkType",
    "SharingDomainRestrictionMode", "DefaultLinkPermission", "LegacyAuthProtocolsEnabled",
    "EnableAzureADB2BIntegration", "PreventExternalUsersFromResharing",
    "ExternalUserExpirationRequired", "EmailAttestationRequired", "DisallowInfectedFileDownload",
    # Teams enums (8.2.4, 8.5.x) and booleans.
    "ExternalAccessWithTrialTenants", "MeetingChatEnabledType", "AutoAdmittedUsers",
    "DesignatedPresenterRoleMode", "AllowFederatedUsers", "AllowPublicUsers",
    "AllowTeamsConsumer", "AllowTeamsConsumerInbound", "AllowAnonymousUsersToJoinMeeting",
    "AllowAnonymousUsersToStartMeeting", "AllowPSTNUsersToBypassLobby",
    "AllowExternalParticipantGiveRequestControl", "AllowExternalNonTrustedMeetingChat",
    "AllowCloudRecording", "AllowRecordingAndTranscription", "AllowSecurityEndUserReporting",
    "AllowDropBox", "AllowBox", "AllowGoogleDrive", "AllowShareFile", "AllowEgnyte",
    "AllowEmailIntoChannel", "AllowAllKnownDomains",
    # Graph enums (section 5): method / feature states, CA modes, the
    # device-registration membership type, OData type names.
    "state", "@odata.type", "mode", "frequencyInterval", "restrictionType",
    "authenticationType", "isEnabled", "isTrusted", "transferMethods",
    "allow_invites_from", "system_preferred_mfa_state", "email_otp_state",
    "number_matching_state", "show_app_information_state",
    "show_geographic_location_state", "companion_app_allowed_state",
    "azure_ad_join_allowed_to_join", "local_admin_registering_user_enabled",
    "local_admin_global_admins_enabled", "multi_factor_auth_configuration",
    "user_device_quota", "laps_enabled", "secure_by_default", "is_approval_required",
    "primary_approver_count", "policyMigrationState",
])


def _json_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _new():
    return {"types": set()}


def _add(node, value, field):
    t = _json_type(value)
    node["types"].add(t)
    if t == "array":
        n = len(value)
        node["min_length"] = min(node.get("min_length", n), n)
        node["max_length"] = max(node.get("max_length", n), n)
        items = node.setdefault("items", _new())
        for v in value:
            # Elements of an allowlisted field (e.g. transferMethods as a
            # list) inherit the field name for the value rule.
            _add(items, v, field)
    elif t == "object":
        keys = list(value)
        named = len(keys) <= MAX_KEYS and all(
            isinstance(k, str) and _PROPERTY_NAME.match(k) for k in keys)
        if named and not node.get("unnamed"):
            node["objects"] = node.get("objects", 0) + 1
            fields = node.setdefault("fields", {})
            for k in keys:
                child = fields.setdefault(k, _new())
                child["present_in"] = child.get("present_in", 0) + 1
                _add(child, value[k], k)
        else:
            node["unnamed"] = True
            node.pop("fields", None)
            node["max_key_count"] = max(node.get("max_key_count", 0), len(keys))
            vals = node.setdefault("value_types", set())
            for v in value.values():
                vals.add(_json_type(v))
    elif t in ("boolean", "number", "string") and field in VALUE_ALLOWLIST:
        if t == "string" and len(value) > MAX_VALUE_LEN:
            node["values_suppressed"] = "value longer than %d characters" % MAX_VALUE_LEN
            return
        values = node.setdefault("values", set())
        values.add(value)
        if len(values) > MAX_VALUES:
            node.pop("values")
            node["values_suppressed"] = "more than %d distinct values" % MAX_VALUES


def _finish(node):
    out = {}
    types = sorted(node["types"])
    out["type"] = types[0] if len(types) == 1 else types
    for k in ("present_in", "objects", "min_length", "max_length", "max_key_count",
              "values_suppressed"):
        if k in node:
            out[k] = node[k]
    if node.get("unnamed"):
        out["keys"] = "not listed (not property names, or more than %d)" % MAX_KEYS
        out["value_types"] = sorted(node.get("value_types", ()))
    if "fields" in node:
        out["fields"] = {k: _finish(v) for k, v in sorted(node["fields"].items())}
    if "items" in node and node["items"]["types"]:
        out["items"] = _finish(node["items"])
    if "values" in node:
        out["values"] = sorted(node["values"], key=lambda v: (str(type(v)), str(v)))
    return out


def shape_of(value, field=None):
    node = _new()
    _add(node, value, field)
    return _finish(node)


def m365_fact_shape(facts):
    """{section: {fact_key: shape}} for the assembled input document.

    Section and fact-key names come from the collectors, so they are
    listed even where they would fail the property-name rule (the PIM
    keys carry a role-definition GUID, which is a Microsoft constant)."""
    out = {}
    for section, body in sorted((facts or {}).items()):
        if isinstance(body, dict):
            out[section] = {key: shape_of(val, key) for key, val in sorted(body.items())}
        else:
            out[section] = shape_of(body, section)
    return {"schema": "aac.m365.fact_shape/v1", "sections": out}


class FilterModule(object):
    def filters(self):
        return {"m365_fact_shape": m365_fact_shape}
