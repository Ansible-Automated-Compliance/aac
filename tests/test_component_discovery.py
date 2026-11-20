"""Tests for scripts/component_discovery.py and the detection catalog.

Pins: the catalog is well formed and names only real loader keys; a client tool
never reports the server component; a port alone never yields a detection; a
component that disappears is marked, with the reason, and never deleted; a host
with no newer facts does not read as a removal; an expired override stops
applying; an override without who / why / expiry is refused; the SQL that
stores a run only inserts and updates.
"""
import copy
import importlib.util
import json
import pathlib
import re

import pytest
import yaml

_root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("component_discovery", _root / "scripts" / "component_discovery.py")
cd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cd)

CATALOG = cd.load_catalog()
FIXTURE = json.loads((_root / "tests" / "fixtures" / "component_discovery_hosts.json").read_text())
SCHEMA_SQL = (_root / "ansible" / "files" / "component_discovery_schema.sql").read_text()
RUN1, RUN2 = "2026-10-01T03:00:00+00:00", "2026-11-19T12:00:00+00:00"


def _latest(*rounds):
    """What host_facts_latest would return: the newest row per host, with a row id."""
    rows, n = {}, 0
    for rnd in rounds:
        for row in FIXTURE[rnd]:
            n += 1
            rows[row["host_id"]] = dict(row, facts_id=n)
    return list(rows.values())


def _detect(host_id, rnd="round1"):
    row = next(r for r in FIXTURE[rnd] if r["host_id"] == host_id)
    return cd.detect_host(cd.normalise_host(row), CATALOG)


def _keys(found):
    return {d["component_key"]: d for d in found["detections"]}


def _two_runs(overrides=()):
    one = cd.build_plan({"now": RUN1, "hosts": _latest("round1")}, CATALOG)
    two = cd.build_plan({"now": RUN2, "hosts": _latest("round1", "round2"),
                         "existing_components": one["payload"]["components"],
                         "existing_unrecognised": one["payload"]["unrecognised"],
                         "overrides": list(overrides)}, CATALOG)
    return one, two


def _row(plan, host, key):
    return next(r for r in plan["payload"]["components"]
                if r["host_id"] == host and r["component_key"] == key)


# ── Catalog ──────────────────────────────────────────────────────────────────

def test_catalog_is_valid_and_versioned():
    assert cd.validate_catalog(CATALOG) == []
    assert re.fullmatch(r"\d{4}\.\d{1,2}\.\d+", CATALOG["catalog_version"])


def test_catalog_covers_the_required_first_entries():
    keys = {c["key"] for c in CATALOG["components"]}
    required = {"awx", "aap_controller", "kubernetes_control_plane", "kubelet", "k3s", "rke2",
                "openshift_node", "podman", "containerd", "cri_o", "docker", "postgresql",
                "mysql_mariadb", "oracle_database", "apache_httpd", "nginx", "openssh_server",
                "freeipa_server", "samba_ad_dc", "satellite", "hashicorp_vault", "grafana", "opa"}
    assert required <= keys
    kinds = {c["kind"] for c in CATALOG["components"]}
    assert {"backup_server", "backup_agent"} <= kinds


def test_catalog_loader_keys_exist_in_the_framework_catalog():
    fw = yaml.safe_load((_root / "ansible" / "vars" / "framework_catalog.yml").read_text())
    known = set(re.findall(r"loader_key:\s*([a-z0-9_]+)", yaml.safe_dump(fw)))
    assert known, "no loader keys found in framework_catalog.yml"
    for comp in CATALOG["components"]:
        assert set(comp["loader_keys"]) <= known, comp["key"]


def test_catalog_schema_faults_are_reported():
    bad = copy.deepcopy(CATALOG)
    bad["catalog_version"] = ""
    bad["components"][0]["privileged"] = {"act": True}
    bad["components"][1]["signals"] = [{"kind": "port", "match": 8052}]
    bad["components"][2]["kind"] = "not_a_kind"
    bad["components"].append(copy.deepcopy(bad["components"][3]))
    errs = "\n".join(cd.validate_catalog(bad))
    for expected in ("catalog_version", "privileged must be", "no signal can identify it",
                     "not listed in kinds", "duplicate key"):
        assert expected in errs


def test_port_signals_are_always_supporting_and_clients_never_identify():
    for comp in CATALOG["components"]:
        ports_and_clients = [s for s in comp["signals"]
                             if s["kind"] == "port" or s.get("role") in ("client", "supporting")]
        only = dict(comp, signals=ports_and_clients or [{"kind": "port", "match": 1}])
        assert any("no signal can identify it" in e
                   for e in cd.validate_catalog(dict(CATALOG, components=[only]))), comp["key"]


# ── Detection ────────────────────────────────────────────────────────────────

def test_controller_host():
    found = _keys(_detect("controller01.example.com"))
    assert found["aap_controller"]["confidence"] == "high"
    assert found["aap_controller"]["run_state"] == "running"
    assert {"package", "service"} <= set(found["aap_controller"]["signal_kinds"])
    assert "awx" not in found


def test_awx_by_container_image():
    found = _keys(_detect("awx01.example.com"))
    assert found["awx"]["confidence"] == "high"
    assert found["awx"]["signal_kinds"] == ["container_image"]


def test_kubernetes_control_plane_node():
    found = _keys(_detect("k8s-cp01.example.com"))
    assert {"kubernetes_control_plane", "kubelet", "containerd"} <= set(found)
    # process name truncated by the kernel to 15 characters still matches
    values = {e["value"] for e in found["kubernetes_control_plane"]["evidence"]}
    assert "kube-controller" in values


def test_kubectl_only_jump_host_is_not_a_kubernetes_server():
    found = _detect("jump01.example.com")
    keys = _keys(found)
    assert not {"kubernetes_control_plane", "kubelet", "k3s", "rke2", "openshift_node"} & set(keys)
    assert "postgresql" not in keys          # client package only
    assert "hashicorp_vault" not in keys     # package and a unit that is neither running nor enabled
    clients = {c["component_key"] for c in found["client_only"]}
    assert {"kubernetes_control_plane", "postgresql", "openshift_node"} <= clients


def test_database_host():
    pg = _keys(_detect("db01.example.com"))["postgresql"]
    assert (pg["confidence"], pg["run_state"]) == ("high", "running")


def test_port_alone_is_never_a_detection():
    found = _detect("app01.example.com")
    assert "mysql_mariadb" not in _keys(found)
    port = next(u for u in found["unrecognised"] if u["item"] == "tcp/3306")
    assert port["detail"]["port_also_used_by"] == ["mysql_mariadb"]


def test_unknown_service_is_listed_and_base_os_units_are_not():
    items = {(u["item_kind"], u["item"]) for u in _detect("app01.example.com")["unrecognised"]}
    assert ("service", "acme-agent.service") in items
    assert ("port", "tcp/9443") in items
    assert not any("chronyd" in i or "systemd" in i or "sshd" in i for _, i in items)
    assert ("port", "tcp/22") not in items


def test_single_signal_kind_is_medium_and_package_only_is_installed():
    host = cd.normalise_host({"host_id": "h", "facts": {"packages": {"installed": ["nginx"]}}})
    det = _keys(cd.detect_host(host, CATALOG))["nginx"]
    assert (det["confidence"], det["run_state"]) == ("medium", "installed")


def _listening(*lines):
    host = cd.normalise_host({"host_id": "h", "facts": {"network": {"listening_ports": list(lines)}}})
    return {u["item"]: u["detail"] for u in cd.detect_host(host, CATALOG)["unrecognised"]}


def test_base_listener_needs_name_port_and_scope_not_the_name_alone():
    ok = _listening('udp UNCONN 0 0 127.0.0.1:323 0.0.0.0:* users:(("chronyd",pid=7,fd=5))',
                    'udp UNCONN 0 0 [::1]:323 [::]:* users:(("chronyd",pid=7,fd=6))',
                    'tcp LISTEN 0 4096 127.0.0.53%lo:53 0.0.0.0:* users:(("systemd-resolve",pid=3,fd=14))')
    assert ok == {}
    # a process named like a base daemon on an unexpected port is reported
    odd = _listening('tcp LISTEN 0 128 0.0.0.0:4444 0.0.0.0:* users:(("chronyd",pid=666,fd=3))')
    assert odd["tcp/4444"]["processes"] == ["chronyd"]
    # right port, wrong protocol; right port, wrong bind scope
    assert "tcp/323" in _listening('tcp LISTEN 0 128 127.0.0.1:323 0.0.0.0:* users:(("chronyd",pid=1,fd=3))')
    assert "udp/323" in _listening('udp UNCONN 0 0 0.0.0.0:323 0.0.0.0:* users:(("chronyd",pid=1,fd=3))')
    assert "tcp/9090" in _listening('tcp LISTEN 0 4096 *:9090 *:* users:(("systemd",pid=1,fd=62))')


def test_base_listener_entries_must_name_a_port():
    bad = copy.deepcopy(CATALOG)
    bad["base_os"]["listeners"] = ["chronyd", {"process": "cupsd", "proto": "tcp"}]
    assert sum("base_os listener" in e for e in cd.validate_catalog(bad)) == 2


def test_sysv_service_names_are_read_as_units():
    units = {"ssh": {"state": "running", "status": "enabled", "source": "sysv"},
             "ssh.service": {"state": "running", "status": "enabled", "source": "systemd"},
             "apparmor": {"state": "running", "status": "enabled", "source": "sysv"},
             "acme": {"state": "running", "status": "enabled", "source": "sysv"}}
    found = cd.detect_host(cd.normalise_host({"host_id": "h", "facts": {"services": {"all": units}}}), CATALOG)
    assert "openssh_server" in _keys(found)
    assert [u["item"] for u in found["unrecognised"]] == ["acme.service"]


def test_host_without_usable_facts_is_not_evaluated():
    plan = cd.build_plan({"now": RUN1, "hosts": _latest("round1")}, CATALOG)
    assert plan["summary"]["hosts_without_usable_facts"] == ["win01.example.com"]


def test_listener_parsing_handles_ss_and_netstat():
    got = cd.parse_listeners([
        "Netid State  Recv-Q Send-Q Local Address:Port Peer Address:PortProcess",
        'tcp   LISTEN 0      128             [::]:22           [::]:*    users:(("sshd",pid=642,fd=4))',
        "tcp        0      0 0.0.0.0:5432            0.0.0.0:*               LISTEN      812/postgres",
    ])
    assert [(g["port"], g["processes"]) for g in got] == [(22, ["sshd"]), (5432, ["postgres"])]


# ── The map over time ────────────────────────────────────────────────────────

def test_component_gone_in_newer_facts_is_marked_not_deleted():
    one, two = _two_runs()
    assert _row(one, "web01.example.com", "nginx")["status"] == "detected"
    row = _row(two, "web01.example.com", "nginx")
    assert row["status"] == "not_seen"
    assert row["not_seen_reason"] == cd.REASON_GONE
    assert row["not_seen_since"].startswith("2026-11-18")      # the facts that show it gone
    assert row["last_seen"].startswith("2026-10-01") and row["first_seen"].startswith("2026-10-01")
    assert row["evidence"]                                      # what it was identified by is kept
    events = [e for e in two["payload"]["history"] if e["component_key"] == "nginx"]
    assert [(e["host_id"], e["event"]) for e in events] == [("web01.example.com", "not_seen")]


def test_no_newer_facts_is_not_a_removal():
    _, two = _two_runs()
    row = _row(two, "legacy01.example.com", "mysql_mariadb")
    assert row["status"] == "detected" and row["not_seen_reason"] is None
    assert row["facts_collected_at"].startswith("2026-10-01")
    listed = two["summary"]["components_per_host"]["legacy01.example.com"]
    assert {c["component"]: c["freshness"] for c in listed}["mysql_mariadb"] == "no newer facts"
    assert not any(n["host"] == "legacy01.example.com" for n in two["summary"]["not_seen"])


def test_failed_collection_does_not_read_as_removal():
    _, two = _two_runs()
    row = _row(two, "partial01.example.com", "apache_httpd")
    assert (row["status"], row["not_seen_reason"]) == ("not_seen", cd.REASON_NO_NEWER)
    assert "did not collect" in row["not_seen_detail"]
    listed = {c["component"] for c in two["summary"]["components_per_host"]["partial01.example.com"]}
    assert "apache_httpd" in listed                              # still listed, as unverified
    assert not any(n["host"] == "partial01.example.com" for n in two["summary"]["not_seen"])


def test_host_missing_from_facts_keeps_its_rows():
    one, _ = _two_runs()
    plan = cd.build_plan({"now": RUN2, "hosts": [], "existing_components": one["payload"]["components"]}, CATALOG)
    assert len(plan["payload"]["components"]) == len(one["payload"]["components"])
    assert {r["not_seen_reason"] for r in plan["payload"]["components"]} == {cd.REASON_NO_NEWER}


def test_rerun_on_the_same_facts_changes_nothing_and_writes_no_history():
    _, two = _two_runs()
    three = cd.build_plan({"now": "2026-11-19T13:00:00+00:00", "hosts": _latest("round1", "round2"),
                           "existing_components": two["payload"]["components"],
                           "existing_unrecognised": two["payload"]["unrecognised"]}, CATALOG)
    assert three["payload"]["history"] == []
    assert all(r["status"] == "detected" for r in three["payload"]["components"])


def test_component_seen_again_is_recorded():
    _, two = _two_runs()
    back = cd.build_plan({"now": "2026-12-01T00:00:00+00:00",
                          "hosts": [dict(r, facts_id=99, collected_at="2026-11-30T02:00:00+00:00")
                                    for r in FIXTURE["round1"] if r["host_id"] == "web01.example.com"],
                          "existing_components": [r for r in two["payload"]["components"]
                                                  if r["host_id"] == "web01.example.com"]}, CATALOG)
    row = _row(back, "web01.example.com", "nginx")
    assert row["status"] == "detected" and row["not_seen_since"] is None
    assert row["first_seen"].startswith("2026-10-01") and row["last_seen"].startswith("2026-11-30")
    assert any(e["event"] == "detected_again" for e in back["payload"]["history"])


def test_catalog_change_on_the_same_facts_is_its_own_reason():
    one, _ = _two_runs()
    slim = dict(CATALOG, catalog_version="2099.1.1",
                components=[c for c in CATALOG["components"] if c["key"] != "nginx"])
    plan = cd.build_plan({"now": RUN1, "hosts": _latest("round1"),
                          "existing_components": one["payload"]["components"]}, slim)
    row = _row(plan, "web01.example.com", "nginx")
    assert (row["status"], row["not_seen_reason"]) == ("not_seen", cd.REASON_CATALOG)


def test_unrecognised_items_are_marked_not_deleted():
    one, two = _two_runs()
    first = {(r["host_id"], r["item"]) for r in one["payload"]["unrecognised"]}
    assert ("app01.example.com", "acme-agent.service") in first
    gone = cd.reconcile_unrecognised(one["payload"]["unrecognised"],
                                     {"app01.example.com": cd.normalise_host(
                                         dict(FIXTURE["round2"][-2], host_id="app01.example.com", facts_id=500))},
                                     {"app01.example.com": []}, RUN2)
    assert {r["status"] for r in gone if r["host_id"] == "app01.example.com"} == {"not_seen"}
    assert len(two["payload"]["unrecognised"]) >= len(first)


# ── Overrides ────────────────────────────────────────────────────────────────

GOOD = {"host": "db01.example.com", "component": "postgresql", "action": "exclude",
        "who": "A. Operator", "why": "build dependency only", "expires": "2027-01-31"}


@pytest.mark.parametrize("missing", ["who", "why", "expires"])
def test_override_without_who_why_or_expiry_is_refused(missing):
    entry = {k: v for k, v in GOOD.items() if k != missing}
    good, errs = cd.validate_overrides([entry], CATALOG)
    assert good == [] and f"{missing} is required" in errs[0]
    plan = cd.build_plan({"now": RUN1, "hosts": _latest("round1"), "overrides": [entry]}, CATALOG)
    assert plan["ok"] is False and plan["payload"] is None     # nothing to write


def test_override_validation_rejects_unknown_values():
    _, errs = cd.validate_overrides([
        dict(GOOD, action="delete"), dict(GOOD, component="no_such_component"),
        dict(GOOD, expires="next week"), dict(GOOD, action="reclassify"),
        dict(GOOD, who="   "),
    ], CATALOG)
    assert len(errs) == 5


def test_override_in_force_is_shown_as_an_override_not_as_detection():
    _, two = _two_runs([GOOD])
    assert "postgresql" not in {c["component"] for c in two["summary"]["components_per_host"]["db01.example.com"]}
    row = _row(two, "db01.example.com", "postgresql")
    assert row["status"] == "detected"                           # what detection found is untouched
    assert "override" not in json.dumps(row)
    assert two["summary"]["overrides_in_force"][0]["who"] == "A. Operator"


def test_expired_override_stops_applying():
    expired = dict(GOOD, expires="2026-11-01")
    _, two = _two_runs([expired])
    assert "postgresql" in {c["component"] for c in two["summary"]["components_per_host"]["db01.example.com"]}
    assert two["summary"]["overrides_in_force"] == []
    assert len(two["summary"]["overrides_expired"]) == 1
    assert two["payload"]["overrides"][0]["expires_at"].startswith("2026-11-01")   # still recorded


def test_confirm_and_reclassify():
    overrides = [
        {"host": "jump01.example.com", "component": "hashicorp_vault", "action": "confirm",
         "who": "A. Operator", "why": "runs from a shell", "expires": "2026-11-25"},
        {"host": "db01.example.com", "component": "postgresql", "action": "reclassify",
         "reclassify_to": "satellite", "who": "A. Operator", "why": "embedded database", "expires": "2027-01-31"},
    ]
    _, two = _two_runs(overrides)
    jump = {c["component"]: c for c in two["summary"]["components_per_host"]["jump01.example.com"]}
    assert jump["hashicorp_vault"]["basis"] == "override" and jump["hashicorp_vault"]["confidence"] is None
    db = {c["component"]: c for c in two["summary"]["components_per_host"]["db01.example.com"]}
    assert db["satellite"]["basis"] == "override" and "postgresql" not in db
    assert [o["component"] for o in two["summary"]["overrides_expiring_soon"]] == ["hashicorp_vault"]


def test_override_beyond_the_maximum_expiry_window_is_refused():
    far = dict(GOOD, expires="2027-03-01")                       # 102 days after RUN2
    _, errs = cd.validate_overrides([far], CATALOG, now=RUN2)
    assert "more than 90 days away" in errs[0]
    good, errs = cd.validate_overrides([far], CATALOG, now=RUN2, max_expiry_days=120)
    assert errs == [] and len(good) == 1
    plan = cd.build_plan({"now": RUN2, "hosts": _latest("round1"), "overrides": [far]}, CATALOG)
    assert plan["ok"] is False and plan["payload"] is None
    plan = cd.build_plan({"now": RUN2, "hosts": _latest("round1"), "overrides": [far],
                          "override_max_expiry_days": 120}, CATALOG)
    assert plan["ok"] is True


PRIV = {"host": "controller01.example.com", "component": "aap_controller", "action": "exclude",
        "who": "A. Operator", "approver": "brev01", "why": "decommissioned, awaiting rebuild",
        "expires": "2026-12-31"}
# The approver list is keyed by controller username; a display name is optional.
APPROVERS = [{"username": "brev01", "name": "B. Reviewer"}, "csecond"]


def _check(entry, approvers=APPROVERS, recorded_by="jdoe", existing=()):
    return cd.validate_overrides([entry], CATALOG, now=RUN2, approvers=approvers,
                                 recorded_by=recorded_by, existing=existing)


@pytest.mark.parametrize("action,extra", [("exclude", {}), ("reclassify", {"reclassify_to": "awx"})])
def test_hiding_a_privileged_component_needs_a_listed_approver(action, extra):
    entry = dict(PRIV, action=action, **extra)
    good, errs = _check(entry)
    assert errs == [] and good[0]["approved_by"] == "brev01" and good[0]["privileged"] is True
    assert "needs an approver" in _check(dict(entry, approver=""))[1][0]
    assert "not a controller username" in _check(dict(entry, approver="znobody"))[1][0]


def test_approver_given_as_a_display_name_is_refused():
    # "B. Reviewer" is the display name of a listed approver, but not a listed username
    _, errs = _check(dict(PRIV, approver="B. Reviewer"))
    assert "not a controller username" in errs[0] and "display name" in errs[0]
    # and a launcher cannot pass the separation check by naming themselves through a display name
    _, errs = _check(dict(PRIV, approver="B. Reviewer"), recorded_by="brev01")
    assert errs and "not a controller username" in errs[0]


def test_launcher_equal_to_the_approver_username_is_refused():
    for launcher in ("brev01", "BREV01", " brev.01 "):
        _, errs = _check(PRIV, recorded_by=launcher)
        assert "the approver is the account that launched the job" in errs[0], launcher
    good, errs = _check(PRIV, recorded_by="jdoe")
    assert errs == [] and (good[0]["approved_by"], good[0]["recorded_by"]) == ("brev01", "jdoe")


def test_requester_is_recorded_as_a_claim_and_cannot_be_the_approver():
    good, _ = _check(dict(PRIV, who="Anyone at all"))
    assert good[0]["requested_by"] == "Anyone at all"            # free text, stored as written
    for who in ("brev01", "B. Reviewer", "b reviewer"):       # the approver's username or display name
        assert "different person from who asked" in _check(dict(PRIV, who=who))[1][0]


def test_one_entry_per_host_and_component():
    _, errs = cd.validate_overrides([GOOD, dict(GOOD, action="confirm")], CATALOG, now=RUN2)
    assert len(errs) == 1 and "second entry for the same host and component" in errs[0]


def test_with_no_approvers_configured_every_privileged_override_is_refused():
    _, errs = _check(PRIV, approvers=[])
    assert "no approvers are configured" in errs[0] and "component_override_approvers" in errs[0]
    plan = cd.build_plan({"now": RUN2, "hosts": _latest("round1"), "overrides": [PRIV],
                          "launched_by": "jdoe"}, CATALOG)
    assert plan["ok"] is False and plan["payload"] is None


def test_privileged_override_outside_the_controller_is_refused():
    _, errs = _check(PRIV, recorded_by="")
    assert "launched from the automation controller" in errs[0]


@pytest.mark.parametrize("same", ["asmith", "ASmith", " a.smith ", "a_smith", "A  Smith"])
def test_names_differing_by_case_spacing_or_punctuation_are_one_account(same):
    assert cd.norm_name(same) == cd.norm_name("asmith")
    entry = dict(PRIV, approver=same)
    # the approver list lookup, and launcher vs approver, use the same normalisation
    good, errs = _check(entry, approvers=["asmith"], recorded_by="jdoe")
    assert errs == [] and good[0]["approved_by"] == "asmith"      # stored as the site lists the account
    _, errs = _check(dict(PRIV, approver="asmith"), approvers=["A.Smith"], recorded_by=same)
    assert "the approver is the account that launched the job" in errs[0]
    # requester vs approver
    _, errs = _check(dict(PRIV, who=same, approver="asmith"), approvers=["asmith"])
    assert "different person from who asked" in errs[0]


def test_confirm_and_unprivileged_overrides_need_no_approver():
    entries = [dict(PRIV, action="confirm", approver=""), dict(GOOD)]   # postgresql has no capability hint
    good, errs = cd.validate_overrides(entries, CATALOG, now=RUN2)
    assert errs == [] and len(good) == 2


def test_approved_override_on_a_privileged_component_stays_visible():
    one = cd.build_plan({"now": RUN1, "hosts": _latest("round1")}, CATALOG)
    two = cd.build_plan({"now": RUN2, "hosts": _latest("round1", "round2"),
                         "existing_components": one["payload"]["components"],
                         "overrides": [PRIV], "approvers": APPROVERS, "launched_by": "jdoe"}, CATALOG)
    s = two["summary"]
    assert "aap_controller" not in {c["component"] for c in s["components_per_host"]["controller01.example.com"]}
    shown = s["overrides_on_privileged_components"]
    assert [(o["component"], o["who"], o["approver"], o["recorded_by"]) for o in shown] == [
        ("aap_controller", "A. Operator", "brev01", "jdoe")]
    assert shown == s["overrides_in_force"]
    assert "[privileged component]" in cd.format_summary(s)
    assert _row(two, "controller01.example.com", "aap_controller")["status"] == "detected"


def test_approver_list_is_read_from_the_site_file_not_from_a_variable(tmp_path):
    site = tmp_path / "site_config.yml"
    site.write_text("component_override_approvers: []\n")
    data = {"now": RUN2, "hosts": _latest("round1"), "overrides": [PRIV], "launched_by": "jdoe",
            "approvers": APPROVERS, "site_config_file": str(site)}
    assert cd.build_plan(data, CATALOG)["ok"] is False          # the file wins over the passed list
    site.write_text('component_override_approvers:\n  - {username: brev01, name: B. Reviewer}\n')
    assert cd.build_plan(data, CATALOG)["ok"] is True
    shipped = yaml.safe_load((_root / "ansible" / "vars" / "site_config.yml.example").read_text())
    assert shipped["component_override_approvers"] == []        # shipped empty


# ── The override record is append-only ───────────────────────────────────────

def _stored(plan, start_id=1):
    """What component_overrides would hold after this plan's inserts."""
    return [dict(o, id=start_id + n, withdrawn_at=None) for n, o in enumerate(plan["payload"]["overrides"])]


def _plan(entries, existing=(), launched_by="jdoe"):
    return cd.build_plan({"now": RUN2, "hosts": _latest("round1"), "overrides": entries,
                          "approvers": APPROVERS, "launched_by": launched_by,
                          "existing_overrides": list(existing)}, CATALOG)


def test_unchanged_override_is_not_rewritten_and_keeps_its_first_recorder():
    first = _plan([PRIV], launched_by="jdoe")
    rows = _stored(first)
    assert [(r["recorded_by"], r["approved_by"]) for r in rows] == [("jdoe", "brev01")]
    again = _plan([PRIV], existing=rows, launched_by="")        # e.g. a scheduled run, no launching user
    assert again["ok"] is True
    assert again["payload"]["overrides"] == [] and again["payload"]["override_withdrawals"] == []
    assert again["summary"]["overrides_in_force"][0]["recorded_by"] == "jdoe"


def test_changed_approver_withdraws_the_old_row_and_inserts_a_new_one_with_attribution():
    rows = _stored(_plan([PRIV], launched_by="jdoe"), start_id=7)
    changed = _plan([dict(PRIV, approver="csecond")], existing=rows, launched_by="asmith")
    assert changed["ok"] is True
    assert changed["payload"]["override_withdrawals"] == [
        {"id": 7, "withdrawn_by": "asmith", "withdrawn_reason": "replaced by a changed entry"}]
    new = changed["payload"]["overrides"]
    assert [(o["approved_by"], o["recorded_by"], o["source"]) for o in new] == [("csecond", "asmith", "file")]
    events = [(e["event"], e["detail"].get("approved_by"), e["detail"].get("withdrawn_by"),
               e["detail"].get("recorded_by")) for e in changed["payload"]["history"]
              if e["event"].startswith("override_")]
    assert events == [("override_withdrawn", "brev01", "asmith", "jdoe"),
                      ("override_recorded", "csecond", None, "asmith")]
    # the changed entry is checked against the account that launched THIS run
    refused = _plan([dict(PRIV, approver="csecond")], existing=rows, launched_by="C.Second")
    assert "launched the job" in refused["override_errors"][0]


@pytest.mark.parametrize("change", [{"why": "another reason"}, {"expires": "2026-12-20"}])
def test_any_changed_field_is_a_withdrawal_plus_a_new_row(change):
    rows = _stored(_plan([GOOD], launched_by="jdoe"))
    changed = _plan([dict(GOOD, **change)], existing=rows, launched_by="asmith")
    assert len(changed["payload"]["override_withdrawals"]) == 1
    assert [o["recorded_by"] for o in changed["payload"]["overrides"]] == ["asmith"]


def test_entry_removed_from_the_list_is_withdrawn_with_attribution():
    rows = _stored(_plan([GOOD], launched_by="jdoe"))
    gone = _plan([], existing=rows, launched_by="asmith")
    assert gone["payload"]["override_withdrawals"] == [
        {"id": 1, "withdrawn_by": "asmith", "withdrawn_reason": "removed from the list"}]
    assert gone["payload"]["overrides"] == []


def test_override_sql_never_updates_a_row_in_place():
    sql = cd.PERSIST_SQL
    block = sql[sql.index("UPDATE component_overrides"):sql.index("COMMIT;")]
    assert "ON CONFLICT" not in block
    update = block[:block.index("INSERT INTO component_overrides")]
    assert set(re.findall(r"(\w+) = ", update.split(" FROM ")[0])) == {
        "withdrawn_at", "withdrawn_by", "withdrawn_reason"}
    assert "component_overrides_append_only" in SCHEMA_SQL


def test_launching_account_and_source_are_recorded_apart_from_the_declared_requester():
    entry = dict(GOOD, recorded_by="someone else", source="file")     # not taken from the entry
    plan = cd.build_plan({"now": RUN2, "hosts": _latest("round1"), "overrides": [entry],
                          "launched_by": "jdoe", "override_source": "variable"}, CATALOG)
    stored = plan["payload"]["overrides"][0]
    assert (stored["requested_by"], stored["recorded_by"], stored["source"]) == ("A. Operator", "jdoe", "variable")
    shown = plan["summary"]["overrides_in_force"][0]
    assert (shown["who"], shown["recorded_by"], shown["source"]) == ("A. Operator", "jdoe", "variable")
    sql = cd.persist_sql(plan["payload"])
    assert "recorded_by" in sql and "approved_by" in sql and "source" in sql
    plain = cd.build_plan({"now": RUN2, "hosts": _latest("round1"), "overrides": [GOOD]}, CATALOG)
    assert plain["payload"]["overrides"][0]["recorded_by"] == ""      # no launching account known
    assert plain["payload"]["overrides"][0]["source"] == "file"


# ── Launch guard ─────────────────────────────────────────────────────────────

def _site(tmp_path, text):
    path = tmp_path / "site_config.yml"
    path.write_text(text)
    return path


def _paths():
    return {"catalog": _root / "ansible" / "vars" / "component_catalog.yml",
            "overrides": _root / "ansible" / "vars" / "component_overrides.yml"}


def test_launch_is_refused_when_the_database_host_is_not_the_site_value(tmp_path):
    site = _site(tmp_path, 'aac_host: "db.example.com"\npg_host: "{{ aac_host }}"\n')
    assert cd.check_launch("db.example.com", site, _paths()) == []
    assert cd.check_launch("DB.example.com ", site, _paths()) == []
    problems = cd.check_launch("elsewhere.example.net", site, _paths())
    assert len(problems) == 1 and "not the configured site value" in problems[0]


def test_launch_is_refused_when_the_site_value_cannot_be_established(tmp_path):
    assert "does not exist" in cd.check_launch("db.example.com", tmp_path / "missing.yml", _paths())[0]
    assert "sets no pg_host" in cd.check_launch("db.example.com", _site(tmp_path, "other: 1\n"), _paths())[0]
    expr = _site(tmp_path, 'pg_host: "{{ lookup(\'env\', \'DB\') }}"\n')
    assert "cannot be checked" in cd.check_launch("db.example.com", expr, _paths())[0]


def test_launch_is_refused_for_files_outside_the_project_checkout(tmp_path):
    site = _site(tmp_path, 'pg_host: "db.example.com"\n')
    outside = tmp_path / "catalog.yml"
    outside.write_text("catalog_version: x\n")
    problems = cd.check_launch("db.example.com", site, dict(_paths(), catalog=outside))
    assert problems == [f"catalog file {str(outside)!r} is outside the project checkout"]
    sneaky = _root / "ansible" / "vars" / ".." / ".." / ".." / outside.name
    assert "outside the project checkout" in cd.check_launch(
        "db.example.com", site, dict(_paths(), overrides=sneaky))[0]
    link = _root / "tests" / "fixtures" / "_cd_link_test.yml"
    try:
        link.symlink_to(outside)                                  # inside by name, outside by target
        assert "outside the project checkout" in cd.check_launch(
            "db.example.com", site, dict(_paths(), overrides=link))[0]
    finally:
        link.unlink(missing_ok=True)


def test_seeded_job_template_takes_no_variables_at_launch():
    base = _root / "install" / "existing-aap" / "extended" / "playbooks"
    tasks = yaml.safe_load((base / "automation_execution" / "templates" / "discover_host_components.yml").read_text())
    jt = next(t["ansible.controller.job_template"] for t in tasks if "ansible.controller.job_template" in t)
    assert jt["ask_variables_on_launch"] is False and jt["survey_enabled"] is True
    assert "extra_vars" not in jt
    spec = yaml.safe_load((base / "vars" / "discover_components_survey.yml").read_text())
    fields = spec["aac_discover_components_survey_spec"]["spec"]
    assert {f["variable"] for f in fields} == {"component_stale_after_days", "component_override_soon_days"}
    for f in fields:
        assert f["type"] == "integer" and isinstance(f["min"], int) and isinstance(f["max"], int)


# ── Summary and SQL ──────────────────────────────────────────────────────────

def test_summary_counts():
    _, two = _two_runs()
    s = two["summary"]
    assert s["hosts_evaluated"] == 9 and len(s["hosts_without_usable_facts"]) == 2
    assert s["not_seen"] == [{"host": "web01.example.com", "component": "nginx",
                              "not_seen_since": "2026-11-18T02:00:00+00:00", "reason": cd.REASON_GONE}]
    assert s["stale_count"] == 4
    assert {"host": "controller01.example.com", "component": "aap_controller"} in s["detected_no_collector"]
    assert {p["component"] for p in s["privileged_services"]} >= {"aap_controller", "awx", "kubernetes_control_plane"}
    assert "Components per host" in cd.format_summary(s)


def test_persist_sql_never_deletes_and_carries_data_as_base64():
    _, two = _two_runs([dict(GOOD, why="it's a quote'; DROP TABLE host_facts; --")])
    sql = cd.persist_sql(two["payload"])
    body = re.sub(r"decode\('[A-Za-z0-9+/=]*'", "decode('<payload>'", sql)
    assert "DROP TABLE host_facts" not in body and "it's" not in body
    # the only DROP is the temporary payload table's own ON COMMIT DROP
    assert not re.search(r"\b(DELETE|TRUNCATE|DROP|ALTER)\b", body.replace("ON COMMIT DROP", ""))
    assert body.strip().startswith("BEGIN;") and body.strip().endswith("COMMIT;")


def test_schema_sql_is_additive_and_idempotent():
    code = re.sub(r"--[^\n]*", "", SCHEMA_SQL)
    code = re.sub(r"\$cd\$.*?\$cd\$", "$body$", code, flags=re.S)      # the trigger function body
    statements = [s.strip() for s in re.split(r";[ \t]*\n", code) if s.strip()]
    assert statements
    allowed = (r"CREATE (TABLE|INDEX|UNIQUE INDEX) IF NOT EXISTS |CREATE OR REPLACE (VIEW|FUNCTION|TRIGGER) "
               r"|ALTER TABLE component_overrides ADD COLUMN IF NOT EXISTS |DO \$body\$$")
    for stmt in statements:
        assert re.match(allowed, stmt), stmt[:60]
    # the only mentions of DELETE / TRUNCATE are the triggers that forbid them
    for stmt in statements:
        if not stmt.startswith("CREATE OR REPLACE TRIGGER component_overrides_append_only"):
            assert not re.search(r"\b(DROP|DELETE|TRUNCATE)\b", stmt), stmt[:60]
    # the migration finds the old constraint by its columns and names no constraint itself
    migration = re.search(r"DO \$cd\$(.*?)\$cd\$", SCHEMA_SQL, flags=re.S).group(1)
    assert "pg_constraint" in migration and "DROP CONSTRAINT %I" in migration
    assert "component_overrides_host" not in migration
    assert "uq_component_overrides_live" in code and "WHERE withdrawn_at IS NULL" in code
    for view in ("v_host_components_current", "v_components_not_assessed",
                 "v_host_unrecognised", "v_privileged_services"):
        assert f"CREATE OR REPLACE VIEW {view} " in code


def test_committed_files_carry_no_addresses():
    for rel in ("ansible/vars/component_catalog.yml", "ansible/vars/component_overrides.yml",
                "tests/fixtures/component_discovery_hosts.json"):
        text = (_root / rel).read_text()
        for ip in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text):
            assert ip.startswith(("0.0.0.0", "127.")), (rel, ip)


# ── Layer 0 keys added for detection: command names, user units, containers ──

def test_process_names_beyond_the_first_100_lines_are_read():
    """processes_raw holds the first 100 lines; command_names holds every distinct name."""
    row = copy.deepcopy(next(r for r in FIXTURE["round1"] if r["host_id"] == "jump01.example.com"))
    assert "hashicorp_vault" not in _keys(cd.detect_host(cd.normalise_host(row), CATALOG))
    row["facts"]["processes"]["command_names"].append("vault")
    found = _keys(cd.detect_host(cd.normalise_host(row), CATALOG))
    assert found["hashicorp_vault"]["signal_kinds"] == ["process"]


def test_command_names_alone_count_as_the_process_domain():
    row = {"host_id": "h", "facts": {"processes": {"command_names": ["etcd", "kube-apiserver"]}}}
    host = cd.normalise_host(row)
    assert "processes" in host["domains"] and "kube-apiserver" in host["processes"]


def test_running_user_unit_identifies_a_component():
    found = _keys(_detect("rootless01.example.com"))
    assert found["opa"]["confidence"] == "high" and found["opa"]["run_state"] == "running"
    ev = [e for e in found["opa"]["evidence"] if e["kind"] == "service"]
    assert ev and "user unit (svcpolicy)" in ev[0]["detail"]


def test_container_entries_carry_runtime_and_user_and_images_are_matched():
    row = next(r for r in FIXTURE["round1"] if r["host_id"] == "k8s-cp01.example.com")
    assert {"image", "name", "runtime", "user"} == set(row["facts"]["containers"]["running"][0])
    found = _keys(_detect("k8s-cp01.example.com"))
    assert "container_image" in found["kubernetes_control_plane"]["signal_kinds"]


def test_host_without_a_container_list_has_no_container_domain():
    row = copy.deepcopy(next(r for r in FIXTURE["round1"] if r["host_id"] == "jump01.example.com"))
    row["facts"]["containers"] = {}
    assert "containers" not in cd.normalise_host(row)["domains"]
