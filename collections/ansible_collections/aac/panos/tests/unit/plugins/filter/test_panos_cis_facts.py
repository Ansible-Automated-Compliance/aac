"""The PAN-OS mapper builds the shape the CIS Palo Alto policy reads, and nothing else.

The fixture is a running configuration in the device's own XML structure
(checked against Palo Alto Networks' public iron-skillet day-one configurations
for PAN-OS 10.2 and 11.0). Scoring the mapped fixture against the policy itself
is done by tests/panos_collector/score_fixture.py, which needs an opa binary and
the policy library; these tests need neither.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

UNIT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "panos_cis_facts", UNIT.parents[1] / "plugins" / "filter" / "panos_cis_facts.py")
mapper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mapper)

HARDENED = (UNIT / "fixtures" / "panos_hardened_running_config.xml").read_text()
LICENSES = (
    '<response status="success"><result><licenses>'
    "<entry><feature>PAN-DB URL Filtering</feature><expires>Never</expires><expired>no</expired></entry>"
    "<entry><feature>DNS Security</feature><expired>yes</expired></entry>"
    "</licenses></result></response>")
MINIMAL = (
    '<config><devices><entry name="localhost.localdomain"><deviceconfig><system>'
    "<hostname>bare</hostname></system></deviceconfig>"
    '<vsys><entry name="vsys1"/></vsys></entry></devices></config>')


@pytest.fixture(scope="module")
def facts():
    return mapper.panos_cis_facts(HARDENED, LICENSES)


def test_no_secret_leaves_the_mapper(facts):
    text = json.dumps(facts)
    for secret in ("FIXTURE", "phash", "$5$", "pre-shared", "privpwd\": \"-", "authpwd\": \"-"):
        assert secret not in text
    trap = facts["shared"]["server_profile"]["snmptrap"][0]["server"][0]
    assert trap["authpwd"] == mapper.SECRET_MARKER
    assert trap["privpwd"] == mapper.SECRET_MARKER
    assert "users" not in facts["mgt_config"]


def test_device_setup(facts):
    system = facts["deviceconfig"]["system"]
    assert system["login_banner"] == "Authorised use only."
    assert system["server_verification"] == "yes"
    assert system["service"] == {"disable_http": "yes", "disable_telnet": "yes"}
    assert system["snmp_setting"] == {"access_setting": {"version": "v3"}}
    assert system["ntp_servers"]["secondary_ntp_server"]["ntp_server_address"] == "192.0.2.124"
    assert system["update_schedule"]["anti_virus"] == {"recurrence": "hourly", "action": "download-and-install"}
    # the threshold beside the schedule is not mistaken for the recurrence
    assert system["update_schedule"]["threats"]["recurrence"] == "every-30-mins"
    assert system["update_schedule"]["wildfire"] == {"recurrence": "real-time"}
    assert facts["deviceconfig"]["setting"]["management"] == {
        "enable_log_high_dp_load": "yes", "idle_timeout": "10"}
    assert facts["mgt_config"]["password_complexity"]["password_change"] == {"expiration_period": "90"}
    assert facts["mgt_config"]["password_profile"] == [
        {"name": "svc", "password_change": {"expiration_period": "60"}}]


def test_high_availability_group_settings_are_lifted(facts):
    ha = facts["deviceconfig"]["high_availability"]
    assert ha["enabled"] == "yes"
    assert ha["interface"] == {"ha2": {"port": "ethernet1/5"}}
    assert ha["state_synchronization"] == {"enabled": "yes"}
    assert ha["election_option"] == {"preemptive": "no"}
    assert ha["active_passive"] == {"passive_link_state": "auto"}
    assert ha["link_monitoring"]["link_group"] == [{
        "name": "uplinks", "enabled": "yes", "failure_condition": "any",
        "interface": ["ethernet1/1", "ethernet1/2"]}]
    assert "path_monitoring" not in ha


def test_logging(facts):
    shared = facts["shared"]
    assert shared["server_profile"]["syslog"][0]["server"][0]["server"] == "192.0.2.30"
    assert shared["server_profile"]["snmptrap"][0]["version"] == "v3"
    for kind in ("system", "config", "userid", "hipmatch", "iptag"):
        match = shared["log_settings"][kind]["match_list"][0]
        assert match["filter"] == "All Logs"
        assert match["send_syslog"] == ["syslog-siem"]
        assert match["send_snmptrap"] == ["trap-v3"]
    assert shared["authentication_profile"] == [
        {"name": "admin-auth", "lockout": {"failed_attempts": "5", "lockout_time": "15"}}]
    wildfire = shared["log_forwarding_profile"][0]["match_list"][0]
    assert wildfire["log_type"] == "wildfire" and wildfire["send_syslog"] == ["syslog-siem"]


def test_zone_protection(facts):
    profile = facts["network"]["profiles"]["zone_protection"][0]
    assert profile["flood"]["tcp_syn"] == {
        "enable": "yes", "action": "syn-cookies",
        "alarm_rate": "10000", "activate_rate": "10000", "maximal_rate": "40000"}
    assert "action" not in profile["flood"]["udp"]
    assert profile["flood"]["other_ip"]["maximal_rate"] == "40000"
    assert profile["scan"]["tcp_port_scan"] == {
        "interval": "5", "threshold": "20", "action": "block-ip",
        "track_by": "source", "duration": "600", "enable": "yes"}
    assert profile["scan"]["host_sweep"]["action"] == "block"
    assert profile["scan"]["udp_port_scan"]["action"] == "alert"
    assert profile["discard_ip_spoof"] == "yes"
    mgmt = facts["network"]["profiles"]["interface_management"][0]
    assert mgmt["permitted_ip"] == ["192.0.2.0/24"] and "http" not in mgmt


def test_scan_entry_with_allow_action_is_off():
    xml = HARDENED.replace(
        '<entry name="8003"><action><alert/></action>', '<entry name="8003"><action><allow/></action>')
    scan = mapper.panos_cis_facts(xml)["network"]["profiles"]["zone_protection"][0]["scan"]
    assert scan["udp_port_scan"]["enable"] == "no"


def test_zones_and_user_id(facts):
    zones = {z["name"]: z for z in facts["zone"]}
    assert zones["trust"] == {
        "name": "trust", "enable_user_identification": "yes", "zone_protection_profile": "zp-strict"}
    assert "enable_user_identification" not in zones["untrust"]
    assert facts["user_id"]["setting"] == {"enable_probing": "no"}
    assert facts["user_id"]["include_exclude_network"][0] == {
        "name": "corp", "discovery": "include", "network_address": "10.0.0.0/8", "enabled": "yes"}


def test_profiles(facts):
    profiles = facts["profiles"]
    spyware = profiles["spyware"][0]
    # a choice written as an empty child element becomes its tag, hyphen kept
    assert spyware["rules"][0]["action"] == "reset-both"
    assert spyware["rules"][0]["severity"] == ["critical", "high", "medium"]
    assert spyware["botnet_domains"]["lists"][0]["action"] == "sinkhole"
    assert spyware["botnet_domains"]["dns_security_categories"][0] == {
        "name": "pan-dns-sec-cc", "action": "sinkhole", "packet_capture": "extended-capture"}
    assert profiles["vulnerability"][0]["rules"][1]["action"] == "default"
    assert profiles["virus"][0]["decoder"][2] == {
        "name": "imap", "action": "alert", "wildfire_action": "alert", "mlav_action": "alert"}
    url = profiles["url_filtering"][0]
    assert url["credential_enforcement"]["mode"] == "ip-user"
    assert url["credential_enforcement"]["continue"] == ["news", "business-and-economy"]
    assert url["override"] == ["command-and-control"]
    assert profiles["data_filtering"][0]["rules"][0]["data_object"] == ["credit-card-numbers"]
    assert profiles["wildfire_analysis"][0]["inline_cloud_rules"][0]["file_type"] == ["pe"]
    assert facts["profile_group"][0]["wildfire_analysis"] == ["wf-strict"]


def test_rulebase(facts):
    rules = {r["name"]: r for r in facts["rulebase"]["security"]}
    assert rules["outbound-web"]["profile_setting"]["profiles"]["url_filtering"] == ["url-strict"]
    assert rules["outbound-dns"]["profile_setting"] == {"group": ["pg-strict"]}
    assert rules["deny-msrpc-untrusted"]["to"] == ["untrust", "guest"]
    assert rules["old-any-any"]["disabled"] == "yes"
    assert "description" not in rules["outbound-web"]
    assert facts["rulebase"]["default_security_rules"][1] == {
        "name": "interzone-default", "action": "deny", "log_start": "no", "log_end": "yes"}
    decrypt = facts["rulebase"]["decryption"][0]
    assert decrypt["type"] == "ssl-forward-proxy" and decrypt["action"] == "decrypt"


def test_licenses_are_left_out_when_not_collected():
    assert "licenses" not in mapper.panos_cis_facts(HARDENED)
    assert "licenses" not in mapper.panos_cis_facts(HARDENED, "")
    assert mapper.panos_cis_facts(HARDENED, LICENSES)["licenses"] == [
        {"feature": "PAN-DB URL Filtering", "expired": "no", "expires": "Never"},
        {"feature": "DNS Security", "expired": "yes"}]


def test_a_section_the_device_lacks_is_sent_empty_not_left_out():
    facts = mapper.panos_cis_facts(MINIMAL)
    assert facts["deviceconfig"]["system"]["service"] == {}
    assert facts["deviceconfig"]["system"]["snmp_setting"] == {}
    assert facts["deviceconfig"]["system"]["update_schedule"] == {}
    assert facts["deviceconfig"]["setting"]["management"] == {}
    assert facts["deviceconfig"]["high_availability"] == {}
    assert facts["mgt_config"] == {"password_complexity": {}, "password_profile": []}
    assert facts["shared"]["server_profile"] == {"syslog": [], "snmptrap": []}
    assert set(facts["shared"]["log_settings"]) == {"system", "config", "userid", "hipmatch", "iptag"}
    assert facts["shared"]["log_settings"]["system"] == {"match_list": []}
    assert facts["network"]["profiles"] == {"interface_management": [], "zone_protection": []}
    assert facts["zone"] == [] and facts["profile_group"] == []
    assert facts["rulebase"] == {"security": [], "default_security_rules": [], "decryption": []}
    assert facts["user_id"] == {"setting": {}, "include_exclude_network": []}
    assert facts["site"] == {} and facts["attest"] == {}


def test_site_and_attest():
    facts = mapper.panos_cis_facts(
        MINIMAL, site={"untrusted_zones": ["untrust"], "internet_zones": "untrust", "ignored": 1},
        attest={"admin_web_certificate_valid": "yes", "vpn_certificate_valid": "no",
                "decryption_certificate_trusted": True, "x": "{{ lookup('env','HOME') }}"})
    assert facts["site"] == {"untrusted_zones": ["untrust"], "internet_zones": ["untrust"]}
    assert facts["attest"] == {"admin_web_certificate_valid": True, "vpn_certificate_valid": False,
                               "decryption_certificate_trusted": True, "x": False}
    with pytest.raises(Exception, match="attest must be a mapping"):
        mapper.panos_cis_facts(MINIMAL, attest=["yes"])
    with pytest.raises(Exception, match="must be a list"):
        mapper.panos_cis_facts(MINIMAL, site={"untrusted_zones": {"a": 1}})


def test_refusals():
    with pytest.raises(Exception, match="document type declaration"):
        mapper.panos_cis_facts('<!DOCTYPE c [<!ENTITY a "b">]>' + MINIMAL)
    with pytest.raises(Exception, match="not well-formed"):
        mapper.panos_cis_facts("<config><devices>")
    with pytest.raises(Exception, match="is empty"):
        mapper.panos_cis_facts("  ")
    with pytest.raises(Exception, match="status 'error'"):
        mapper.panos_cis_facts('<response status="error" code="403"><result><msg>x</msg></result></response>')
    with pytest.raises(Exception, match="virtual system 'vsys2' is not in the configuration .found: vsys1"):
        mapper.panos_cis_facts(MINIMAL, vsys="vsys2")
    panorama = MINIMAL.replace("<deviceconfig>", '<device-group><entry name="dg"/></device-group><deviceconfig>')
    with pytest.raises(Exception, match="Panorama"):
        mapper.panos_cis_facts(panorama)


def test_system_info():
    xml = ('<response status="success"><result><system><hostname>fw1</hostname><model>PA-440</model>'
           "<serial>0123</serial><sw-version>11.1.4</sw-version></system></result></response>")
    assert mapper.panos_system_info(xml) == {
        "hostname": "fw1", "model": "PA-440", "serial": "0123", "sw_version": "11.1.4"}
