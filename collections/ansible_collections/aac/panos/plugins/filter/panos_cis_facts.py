# -*- coding: utf-8 -*-
"""Map a PAN-OS running configuration to the facts the CIS Palo Alto policy reads.

The policy (policies/benchmarks/cis/network_devices/palo_alto/, package
``cis_palo_alto_panos``) reads ``input.panos_config`` in a flattened shape that
is not the device's XML tree: server profiles sit under ``shared.server_profile``,
high-availability group settings are lifted one level, zone-protection flood and
scan settings are keyed by kind, and so on. This filter builds exactly that shape
from the XML the firewall returns for ``show config running``.

Three rules shape the output.

1. Only what the policy reads is copied. The running configuration carries
   password hashes, pre-shared keys and SNMP secrets; none of them leave this
   filter. Where the policy only needs to know a secret is set (SNMP v3 trap
   ``authpwd``), the value is replaced by the marker ``(set)``.

2. A section the device does not have is sent as an empty object or list, not
   left out. The configuration was read in full, so absence is a fact about the
   device ("no password complexity configured"), and the policy must judge it as
   such rather than report "evidence missing". The one exception is ``licenses``:
   it comes from a second command, and when that command was not run the key is
   left out so the license-gated recommendations report evidence missing.

3. A value the configuration does not state is not invented. PAN-OS leaves out
   settings that are at their default; the policy reads an absent yes/no setting
   as "no".
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import xml.etree.ElementTree as ET

try:
    from ansible.errors import AnsibleFilterError
except ImportError:  # unit tests and harnesses import this file without Ansible
    class AnsibleFilterError(Exception):
        pass

try:  # preferred when the execution environment has it
    from defusedxml.ElementTree import fromstring as _safe_fromstring
except ImportError:  # the refusal in _parse() covers the same input without it
    _safe_fromstring = None

DOCUMENTATION = r"""
name: panos_cis_facts
short_description: Build the CIS Palo Alto policy input from a PAN-OS running configuration
description:
  - Takes the XML returned by the PAN-OS XML API for C(show config running) and
    returns the C(panos_config) object read by the C(cis_palo_alto_panos) policy.
  - Secrets in the configuration are never copied to the output.
options:
  _input:
    description: The running configuration as XML text (a C(<config>) element, or an API C(<response>) that contains one).
    type: str
    required: true
  licenses_xml:
    description: The XML returned for C(request license info). Leave empty when it was not collected.
    type: str
  vsys:
    description: The virtual system whose zones, profiles and rules are assessed.
    type: str
    default: vsys1
  site:
    description: Operator classification, C(untrusted_zones), C(internet_zones), C(url_block_categories).
    type: dict
  attest:
    description: Attestation booleans for the judgement recommendations.
    type: dict
"""

SECRET_MARKER = "(set)"

LOG_TYPES = ("system", "config", "userid", "hipmatch", "iptag", "globalprotect", "correlation")
SEND_KEYS = ("send-syslog", "send-snmptrap", "send-email", "send-http")
PROFILE_KINDS = ("virus", "spyware", "vulnerability", "url-filtering", "data-filtering",
                 "wildfire-analysis", "file-blocking")
# zone-protection reconnaissance entries are named by threat id
SCAN_IDS = {"8001": "tcp_port_scan", "8002": "host_sweep", "8003": "udp_port_scan",
            "8006": "ip_protocol_scan"}
# containers whose single child element is a choice: the child's tag is the value
CHOICE_KEYS = ("action", "type", "mode")
ATTEST_TRUE = ("true", "yes", "1", "on")
# Settings PAN-OS holds as whole numbers. The device XML carries every value as
# text; the policy takes a number only as a JSON number, so these are converted.
# A value that is not a whole number is left as the text the device returned and
# the policy reports it as invalid evidence.
NUMERIC_KEYS = frozenset((
    "minimum_length", "minimum_uppercase_letters", "minimum_lowercase_letters",
    "minimum_numeric_letters", "minimum_special_characters", "block_repeated_characters",
    "new_password_differs_by_characters", "password_history_count",
    "expiration_period", "expiration_warning_period", "post_expiration_admin_login_count",
    "post_expiration_grace_period", "idle_timeout", "failed_attempts", "lockout_time",
    "alert_threshold", "block_threshold", "activate_rate", "alarm_rate", "maximal_rate",
    "interval", "threshold", "duration",
))


def _u(tag):
    return tag.replace("-", "_")


def _find(elem, path):
    return None if elem is None else elem.find(path)


def _text(elem, path=None):
    """Stripped text of an element, or None when it is absent or empty."""
    node = elem if path is None else _find(elem, path)
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value if value else None


def _members(elem, path):
    node = _find(elem, path)
    if node is None:
        return []
    return [m.text.strip() for m in node.findall("member") if m.text and m.text.strip()]


def _entries(elem, path):
    node = _find(elem, path)
    return [] if node is None else node.findall("entry")


def _choice(elem, path=None):
    """Tag of the first child element: PAN-OS writes a choice as an empty child."""
    node = elem if path is None else _find(elem, path)
    if node is None:
        return None
    for child in node:
        return child.tag
    return _text(node)


def _pick(elem, names):
    """Simple text children named in ``names``, keyed with underscores; absent ones are left out."""
    out = {}
    if elem is None:
        return out
    for name in names:
        value = _text(elem, name)
        if value is not None:
            out[_u(name)] = value
    return out


def _simple_children(elem):
    """Every child that carries only text, keyed with underscores."""
    out = {}
    if elem is None:
        return out
    for child in elem:
        if len(child) == 0:
            value = _text(child)
            if value is not None:
                out[_u(child.tag)] = value
    return out


def _conv(elem):
    """Generic conversion, used only for security profiles (they hold no secrets).

    ``<entry>`` lists become arrays of objects keyed by ``name``, ``<member>``
    lists become arrays of strings, a choice written as a single child element
    of ``action`` / ``type`` / ``mode`` becomes that child's tag.
    """
    children = list(elem)
    if not children:
        value = _text(elem)
        return value if value is not None else {}
    tags = {c.tag for c in children}
    if tags == {"member"}:
        return [c.text.strip() for c in children if c.text and c.text.strip()]
    if tags == {"entry"}:
        return [_conv_entry(c) for c in children]
    out = {}
    for child in children:
        if child.tag == "entry":
            out.setdefault("entry", []).append(_conv_entry(child))
        elif child.tag in CHOICE_KEYS and len(child) == 1:
            out[_u(child.tag)] = child[0].tag
            if len(child[0]):
                out[_u(child.tag) + "_options"] = _conv(child[0])
        else:
            out[_u(child.tag)] = _conv(child)
    return out


def _conv_entry(entry):
    body = _conv(entry) if len(entry) else {}
    out = {"name": entry.get("name", "")}
    if isinstance(body, dict):
        out.update(body)
    return out


def _parse(xml_text, what):
    if not isinstance(xml_text, str) or not xml_text.strip():
        raise AnsibleFilterError("panos_cis_facts: the %s is empty" % what)
    # A device configuration has no document type declaration, and entities can
    # only be declared inside one. Refusing it anywhere in the text closes
    # entity expansion and external entities before any parser sees the input;
    # defusedxml, when installed, refuses the same input a second time.
    if "<!DOCTYPE" in xml_text or "<!ENTITY" in xml_text:
        raise AnsibleFilterError("panos_cis_facts: the %s contains a document type declaration" % what)
    try:
        if _safe_fromstring is not None:
            return _safe_fromstring(xml_text)
        return ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise AnsibleFilterError("panos_cis_facts: the %s is not well-formed XML: %s" % (what, exc))
    except Exception as exc:  # defusedxml raises its own exception types
        raise AnsibleFilterError("panos_cis_facts: the %s was refused by the XML parser: %s" % (what, exc))


def _api_ok(root, what):
    if root.tag == "response" and root.get("status", "success") != "success":
        raise AnsibleFilterError(
            "panos_cis_facts: the device answered the %s request with status '%s'" % (what, root.get("status")))


def _config_root(root):
    _api_ok(root, "configuration")
    if root.tag == "config":
        return root
    node = root.find(".//config")
    if node is None:
        raise AnsibleFilterError("panos_cis_facts: no <config> element in the configuration")
    return node


# ── device setup ──────────────────────────────────────────────────────────────

def _update_schedule(node):
    out = {}
    if node is None:
        return out
    for kind in node:
        rec = kind.find("recurring")
        item = {}
        if rec is not None:
            for choice in rec:
                if choice.tag in ("threshold", "sync-to-peer"):
                    continue
                item["recurrence"] = choice.tag
                action = _text(choice, "action")
                if action is not None:
                    item["action"] = action
                break
        out[_u(kind.tag)] = item
    return out


def _system(sysn):
    out = _pick(sysn, ("login-banner", "server-verification"))
    out["service"] = _simple_children(_find(sysn, "service"))
    snmp = _find(sysn, "snmp-setting")
    out["snmp_setting"] = {}
    if snmp is not None:
        version = _choice(snmp, "access-setting/version")
        if version is not None:
            out["snmp_setting"] = {"access_setting": {"version": version}}
    ntp = {}
    for which in ("primary-ntp-server", "secondary-ntp-server"):
        addr = _text(sysn, "ntp-servers/%s/ntp-server-address" % which)
        if addr is not None:
            ntp[_u(which)] = {"ntp_server_address": addr}
    out["ntp_servers"] = ntp
    out["update_schedule"] = _update_schedule(_find(sysn, "update-schedule"))
    return out


def _setting(setn):
    return {
        "management": _pick(_find(setn, "management"), ("enable-log-high-dp-load", "idle-timeout")),
        "ssl_decrypt": _pick(_find(setn, "ssl-decrypt"), ("allow-forward-decrypted-content",)),
        "wildfire": {"session_info_select": _simple_children(_find(setn, "wildfire/session-info-select"))},
    }


def _monitor(node, groups_key, group_entries, members_of):
    if node is None:
        return None
    out = _pick(node, ("enabled", "failure-condition"))
    groups = []
    for entry in group_entries(node):
        group = {"name": entry.get("name", "")}
        group.update(_pick(entry, ("enabled", "failure-condition")))
        group.update(members_of(entry))
        groups.append(group)
    out[groups_key] = groups
    return out


def _path_group_entries(node):
    pg = node.find("path-group")
    found = []
    if pg is not None:
        for kind in pg:  # virtual-wire, vlan, virtual-router, logical-router
            found.extend(kind.findall("entry"))
    return found


def _path_destinations(entry):
    ips = _members(entry, "destination-ip")
    for group in _entries(entry, "destination-ip-group"):
        ips.extend(_members(group, "destination-ip"))
    return {"destination_ip": ips}


def _high_availability(ha):
    if ha is None:
        return {}
    out = _pick(ha, ("enabled",))
    port = _text(ha, "interface/ha2/port")
    if port is not None:
        out["interface"] = {"ha2": {"port": port}}
    group = ha.find("group")
    if group is not None and group.find("entry") is not None:  # PAN-OS 8 and earlier
        group = group.find("entry")
    if group is None:
        return out
    sync = _pick(_find(group, "state-synchronization"), ("enabled",))
    if sync:
        out["state_synchronization"] = sync
    election = _pick(_find(group, "election-option"), ("preemptive",))
    if election:
        out["election_option"] = election
    passive = _pick(_find(group, "mode/active-passive"), ("passive-link-state",))
    if passive:
        out["active_passive"] = passive
    link = _monitor(
        _find(group, "monitoring/link-monitoring"), "link_group",
        lambda n: _entries(n, "link-group"),
        lambda e: {"interface": _members(e, "interface")})
    if link is not None:
        out["link_monitoring"] = link
    path = _monitor(
        _find(group, "monitoring/path-monitoring"), "path_group",
        _path_group_entries, _path_destinations)
    if path is not None:
        out["path_monitoring"] = path
    return out


def _mgt_config(mgt):
    pc = _find(mgt, "password-complexity")
    complexity = _simple_children(pc)
    change = _simple_children(_find(pc, "password-change"))
    if change:
        complexity["password_change"] = change
    profiles = []
    for entry in _entries(mgt, "password-profile"):
        profiles.append({"name": entry.get("name", ""),
                         "password_change": _simple_children(_find(entry, "password-change"))})
    return {"password_complexity": complexity, "password_profile": profiles}


# ── logging ───────────────────────────────────────────────────────────────────

def _match_list(node, with_log_type):
    out = []
    for entry in _entries(node, "match-list"):
        item = {"name": entry.get("name", "")}
        item.update(_pick(entry, ("filter", "send-to-panorama") + (("log-type",) if with_log_type else ())))
        for key in SEND_KEYS:
            targets = _members(entry, key)
            if targets:
                item[_u(key)] = targets
        out.append(item)
    return out


def _syslog_profiles(shared):
    out = []
    for entry in _entries(shared, "log-settings/syslog"):
        servers = []
        for srv in _entries(entry, "server"):
            item = {"name": srv.get("name", "")}
            item.update(_pick(srv, ("server", "transport", "port", "format")))
            servers.append(item)
        out.append({"name": entry.get("name", ""), "server": servers})
    return out


def _snmptrap_profiles(shared):
    out = []
    for entry in _entries(shared, "log-settings/snmptrap"):
        version = _choice(entry, "version")
        servers = []
        for srv in _entries(entry, "version/%s/server" % version) if version else []:
            item = {"name": srv.get("name", "")}
            item.update(_pick(srv, ("manager", "user", "engineid")))
            for secret in ("authpwd", "privpwd", "community"):
                if _text(srv, secret) is not None:
                    item[secret] = SECRET_MARKER
            servers.append(item)
        profile = {"name": entry.get("name", ""), "server": servers}
        if version:
            profile["version"] = version
        out.append(profile)
    return out


def _shared(shared, vs):
    log_settings = {}
    for kind in LOG_TYPES:
        node = _find(shared, "log-settings/%s" % kind)
        # the five types the policy checks are always present, so "nothing
        # forwarded" is judged rather than reported as evidence missing
        if node is not None or kind in LOG_TYPES[:5]:
            log_settings[kind] = {"match_list": _match_list(node, False)}
    auth = []
    for scope in (shared, vs):
        for entry in _entries(scope, "authentication-profile"):
            auth.append({"name": entry.get("name", ""),
                         "lockout": _pick(_find(entry, "lockout"), ("failed-attempts", "lockout-time"))})
    forwarding = []
    for scope in (shared, vs):
        for entry in _entries(scope, "log-settings/profiles"):
            forwarding.append({"name": entry.get("name", ""), "match_list": _match_list(entry, True)})
    return {
        "server_profile": {"syslog": _syslog_profiles(shared), "snmptrap": _snmptrap_profiles(shared)},
        "log_settings": log_settings,
        "authentication_profile": auth,
        "log_forwarding_profile": forwarding,
    }


# ── network profiles, zones, User-ID ──────────────────────────────────────────

def _flood(node):
    out = {}
    if node is None:
        return out
    for kind in node:  # tcp-syn, udp, icmp, icmpv6, other-ip
        item = _pick(kind, ("enable",))
        for mode in ("syn-cookies", "red"):
            rates = kind.find(mode)
            if rates is not None:
                if kind.tag == "tcp-syn":
                    item["action"] = mode
                item.update(_pick(rates, ("alarm-rate", "activate-rate", "maximal-rate")))
                break
        out[_u(kind.tag)] = item
    return out


def _scan(node):
    out = {}
    for entry in ([] if node is None else node.findall("entry")):
        key = SCAN_IDS.get(entry.get("name", ""))
        if key is None:
            continue
        item = _pick(entry, ("interval", "threshold"))
        action = entry.find("action")
        choice = _choice(action) if action is not None else None
        if choice is not None:
            item["action"] = choice
            item.update(_pick(action.find(choice), ("track-by", "duration")))
        # the configuration has no enable flag for a scan entry: it is on when
        # the entry exists with an action other than allow
        item["enable"] = "yes" if choice not in (None, "allow") else "no"
        out[key] = item
    return out


def _network_profiles(dev):
    mgmt = []
    for entry in _entries(dev, "network/profiles/interface-management-profile"):
        item = {"name": entry.get("name", "")}
        item.update(_simple_children(entry))
        item["permitted_ip"] = [e.get("name", "") for e in _entries(entry, "permitted-ip")]
        mgmt.append(item)
    zpp = []
    for entry in _entries(dev, "network/profiles/zone-protection-profile"):
        item = {"name": entry.get("name", "")}
        item.update(_simple_children(entry))
        item["flood"] = _flood(entry.find("flood"))
        item["scan"] = _scan(entry.find("scan"))
        zpp.append(item)
    return {"interface_management": mgmt, "zone_protection": zpp}


def _zones(vs):
    out = []
    for entry in _entries(vs, "zone"):
        item = {"name": entry.get("name", "")}
        item.update(_pick(entry, ("enable-user-identification",)))
        item.update(_pick(_find(entry, "network"), ("zone-protection-profile",)))
        out.append(item)
    return out


def _user_id(vs):
    collector = _find(vs, "user-id-collector")
    networks = []
    for entry in _entries(collector, "include-exclude-network"):
        item = {"name": entry.get("name", "")}
        item.update(_pick(entry, ("discovery", "network-address", "enabled")))
        networks.append(item)
    return {"setting": _pick(_find(collector, "setting"), ("enable-probing",)),
            "include_exclude_network": networks}


# ── security profiles and rules ───────────────────────────────────────────────

def _profiles(shared, vs):
    out = {}
    for kind in PROFILE_KINDS:
        found = []
        for scope in (shared, vs):
            for entry in _entries(scope, "profiles/%s" % kind):
                found.append(_conv_entry(entry))
        out[_u(kind)] = found
    # the policy reads a data-filtering rule's data object as a list
    for profile in out["data_filtering"]:
        for rule in profile.get("rules", []) if isinstance(profile.get("rules"), list) else []:
            if isinstance(rule.get("data_object"), str):
                rule["data_object"] = [rule["data_object"]]
    return out


def _profile_groups(shared, vs):
    out = []
    for scope in (shared, vs):
        for entry in _entries(scope, "profile-group"):
            group = {"name": entry.get("name", "")}
            for kind in PROFILE_KINDS:
                names = _members(entry, kind)
                if names:
                    group[_u(kind)] = names
            out.append(group)
    return out


def _profile_setting(entry):
    node = entry.find("profile-setting")
    if node is None:
        return None
    out = {}
    group = _members(node, "group")
    if group:
        out["group"] = group
    profiles = {}
    for kind in PROFILE_KINDS:
        names = _members(node, "profiles/%s" % kind)
        if names:
            profiles[_u(kind)] = names
    if profiles:
        out["profiles"] = profiles
    return out


def _rule(entry, lists, texts):
    item = {"name": entry.get("name", "")}
    for key in lists:
        if entry.find(key) is not None:
            item[_u(key)] = _members(entry, key)
    item.update(_pick(entry, texts))
    setting = _profile_setting(entry)
    if setting is not None:
        item["profile_setting"] = setting
    return item


def _rulebase(vs):
    security = [
        _rule(e, ("from", "to", "source", "destination", "application", "service", "category", "source-user"),
              ("action", "disabled", "log-start", "log-end", "log-setting"))
        for e in _entries(vs, "rulebase/security/rules")]
    defaults = [
        _rule(e, (), ("action", "log-start", "log-end", "log-setting"))
        for e in _entries(vs, "rulebase/default-security-rules/rules")]
    decryption = []
    for e in _entries(vs, "rulebase/decryption/rules"):
        item = _rule(e, ("from", "to", "source", "destination", "category"), ("action", "disabled", "profile"))
        kind = _choice(e, "type")
        if kind is not None:
            item["type"] = kind
        decryption.append(item)
    return {"security": security, "default_security_rules": defaults, "decryption": decryption}


# ── licenses, attestations ────────────────────────────────────────────────────

def _licenses(xml_text):
    root = _parse(xml_text, "license information")
    _api_ok(root, "license")
    out = []
    for entry in root.iter("entry"):
        item = _pick(entry, ("feature", "expired", "expires"))
        if "feature" in item:
            out.append(item)
    return out


def _attest(attest):
    if attest is None or attest == "":
        return {}
    if not isinstance(attest, dict):
        raise AnsibleFilterError("panos_cis_facts: attest must be a mapping of name to true/false")
    out = {}
    for key, value in attest.items():
        if isinstance(value, bool):
            out[str(key)] = value
        else:
            out[str(key)] = str(value).strip().lower() in ATTEST_TRUE
    return out


def _site(site):
    if site is None or site == "":
        return {}
    if not isinstance(site, dict):
        raise AnsibleFilterError("panos_cis_facts: site must be a mapping")
    out = {}
    for key in ("untrusted_zones", "internet_zones", "url_block_categories"):
        value = site.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple)):
            raise AnsibleFilterError("panos_cis_facts: site.%s must be a list" % key)
        out[key] = [str(v) for v in value]
    return out


def _numbers(node, skip=("site", "attest")):
    """Convert the whole-number settings (NUMERIC_KEYS) from device text to numbers, in place."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in skip:
                continue
            if key in NUMERIC_KEYS and isinstance(value, str) and value.strip().isdigit():
                node[key] = int(value.strip())
            else:
                _numbers(value, skip=())
    elif isinstance(node, list):
        for item in node:
            _numbers(item, skip=())
    return node


def panos_cis_facts(config_xml, licenses_xml=None, vsys="vsys1", site=None, attest=None):
    config = _config_root(_parse(config_xml, "configuration"))
    dev = config.find("devices/entry")
    if dev is None:
        raise AnsibleFilterError("panos_cis_facts: the configuration has no devices/entry element")
    if dev.find("device-group") is not None or dev.find("template") is not None:
        raise AnsibleFilterError(
            "panos_cis_facts: this is a Panorama configuration. The CIS Palo Alto Firewall benchmark "
            "is assessed on each firewall; point the assessment at the firewalls.")
    vs_all = _entries(dev, "vsys")
    vs = next((v for v in vs_all if v.get("name") == vsys), None)
    if vs is None:
        raise AnsibleFilterError(
            "panos_cis_facts: virtual system '%s' is not in the configuration (found: %s)"
            % (vsys, ", ".join(v.get("name", "") for v in vs_all) or "none"))
    shared = config.find("shared")

    out = {
        "deviceconfig": {
            "system": _system(_find(dev, "deviceconfig/system")),
            "setting": _setting(_find(dev, "deviceconfig/setting")),
            "high_availability": _high_availability(_find(dev, "deviceconfig/high-availability")),
        },
        "mgt_config": _mgt_config(config.find("mgt-config")),
        "shared": _shared(shared, vs),
        "network": {"profiles": _network_profiles(dev)},
        "user_id": _user_id(vs),
        "zone": _zones(vs),
        "profiles": _profiles(shared, vs),
        "profile_group": _profile_groups(shared, vs),
        "rulebase": _rulebase(vs),
        "site": _site(site),
        "attest": _attest(attest),
    }
    if licenses_xml is not None and str(licenses_xml).strip():
        out["licenses"] = _licenses(licenses_xml)
    return _numbers(out)


def panos_system_info(system_xml):
    """Hostname, model, serial and software version from ``show system info``."""
    root = _parse(system_xml, "system information")
    _api_ok(root, "system information")
    node = root.find(".//system")
    return _pick(node, ("hostname", "model", "serial", "sw-version", "ip-address", "multi-vsys"))


class FilterModule(object):
    def filters(self):
        return {"panos_cis_facts": panos_cis_facts, "panos_system_info": panos_system_info}
