"""Tests for scripts/layered_collection.py, the collector contract and the dispatcher.

Pins: the catalog and the shipped collectors satisfy the contract; a collector
runs only where its component was detected; a detected component with no
collector, no credential, a failed collector or an oversized result is recorded
as "detected, not assessed" with the reason and never dropped; a service
instance reached through two hosts is collected once; what is found inside a
component is inventoried with its parent and only assessed when the catalog
says so, to a bounded depth; secrets are not stored; and the generality proof:
a made-up component flows from detection to the coverage report with one
catalog entry and one collector file, and the dispatcher names no component.
"""
import copy
import importlib.util
import json
import pathlib
import re
import shutil

import pytest
import yaml

_root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("layered_collection", _root / "scripts" / "layered_collection.py")
lc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lc)
cd = lc.cd

SHIPPED_DIR = _root / "ansible" / "tasks" / "component_collectors"
STUBS = _root / "tests" / "fixtures" / "layered"
CATALOG = lc.load_catalog()
FIXTURE = json.loads((_root / "tests" / "fixtures" / "component_discovery_hosts.json").read_text())
NOW = "2026-11-19T12:00:00+00:00"

# The generic parts: nothing in these files may name a component.
GENERIC_FILES = [
    "ansible/playbooks/collect_component_facts.yml",
    "ansible/playbooks/layered_collection_pass.yml",
    "ansible/tasks/layered_run_collector.yml",
    "ansible/tasks/layered_store_results.yml",
    "ansible/files/layered_collection_schema.sql",
    "ansible/files/layered_collection_read_map.sql",
    "ansible/files/component_collector_contract.schema.json",
    "scripts/layered_collection.py",
]

ACME = {
    "key": "acme_queue", "name": "Acme queue (made up)", "kind": "database", "collector": "acme_queue_host",
    "loader_keys": [], "privileged": {"act": False, "map": False, "rank": False},
    "assess": True, "contains": ["postgresql"],
    "collectors": [
        {"layer": "host", "file": "acme_queue_host.yml", "version": "0.1", "cost": "cheap",
         "access": "Read access to /etc/acme over the connection already in use. Writes nothing."},
        {"layer": "service", "file": "acme_queue_service.yml", "version": "0.1", "cost": "heavy",
         "credential": {"type": "Acme Queue Read-Only", "env": ["ACME_QUEUE_URL", "ACME_QUEUE_TOKEN"]},
         "access": "A token with the read-only role on the queue API. No write scope."},
    ],
    "signals": [{"kind": "process", "match": "acme-queued"}, {"kind": "service", "match": "acme-queue.service"}],
}


def _components(*pairs, evidence=()):
    return [{"hostname": h, "host_id": h, "component_key": k, "status": "detected",
             "evidence": list(evidence)} for h, k in pairs]


def _begin(components, catalog=CATALOG, hosts=None, **kw):
    hosts = hosts if hosts is not None else sorted({c["hostname"] for c in components})
    return lc.begin(dict({"now": NOW, "inventory_hosts": hosts, "components": components}, **kw), catalog)


def _stub_result(path):
    """What a stub collector sets: its one set_fact, read without running Ansible."""
    tasks = yaml.safe_load(pathlib.Path(path).read_text())
    return tasks[0]["ansible.builtin.set_fact"]["lc_result"]


def _answer(selection, result_for):
    """Results in the shape ansible/tasks/layered_run_collector.yml produces."""
    out = {}
    for host, items in selection["by_host"].items():
        out[host] = [dict({"item_id": it["item_id"]}, **result_for(it)) for it in items]
    return out


def _ok(result):
    return {"result": result, "failed": False}


def _rows(state, **match):
    return [r for r in state["rows"] if all(r[k] == v for k, v in match.items())]


# ── Contract and catalog ─────────────────────────────────────────────────────

def test_shipped_catalog_satisfies_the_contract():
    assert lc.validate_layering(yaml.safe_load((_root / "ansible/vars/component_catalog.yml").read_text())) == []


def test_every_shipped_collector_file_is_named_by_the_catalog_and_the_reverse():
    named = {col["file"] for c in CATALOG["components"] for col in c.get("collectors") or []
             if col["file"] != lc.NO_COLLECTOR}
    assert named == {p.name for p in SHIPPED_DIR.glob("*.yml")}
    assert named, "at least one collector ships"


def test_every_collector_documents_its_access_and_cost():
    for c in CATALOG["components"]:
        for col in c.get("collectors") or []:
            assert col["cost"] in ("cheap", "heavy") and len(col["access"]) >= 20, c["key"]
            if col["layer"] == "service":
                assert col["credential"]["type"] and col["credential"]["env"], c["key"]


@pytest.mark.parametrize("change, fault", [
    (lambda c: c["collectors"][0].update(file="other_name_host.yml"), "must be named"),
    (lambda c: c["collectors"][0].update(cost="free"), "not one of"),
    (lambda c: c["collectors"][0].pop("access"), "access is required"),
    (lambda c: c["collectors"][1].pop("credential"), "must name its credential type"),
    (lambda c: c["collectors"][0].update(credential={"type": "abc", "env": ["X"]}), "no credential"),
    (lambda c: c.update(contains=["no_such_component"]), "not a catalog key"),
    (lambda c: c["collectors"].append(dict(c["collectors"][0])), "two collectors"),
    (lambda c: c["collectors"][0].update(surprise=1), "unknown field"),
])
def test_catalog_faults_are_refused(change, fault, tmp_path):
    cat = copy.deepcopy(CATALOG)
    entry = copy.deepcopy(ACME)
    change(entry)
    cat["components"].append(entry)
    errs = lc.validate_layering(cat, _collectors_dir(tmp_path))
    assert any(fault in e for e in errs), errs


def test_collector_file_must_exist(tmp_path):
    cat = copy.deepcopy(CATALOG)
    cat["components"].append(copy.deepcopy(ACME))
    errs = lc.validate_layering(cat, SHIPPED_DIR)       # the stub is not in the shipped directory
    assert any("acme_queue_host.yml does not exist" in e for e in errs)


@pytest.mark.parametrize("result, fault", [
    ({}, "status is required"),
    ({"status": "done"}, "not one of"),
    ({"status": "collected", "facts": []}, "type object"),
    ({"status": "collected", "facts": {}, "extra": 1}, "unknown field"),
    ({"status": "collected", "children": [{"kind": "port", "value": "22"}]}, "not one of"),
    ({"status": "collected", "instance": {"identity": "has space"}}, "does not match"),
    ({"status": "not_collected", "reason": "x" * 301}, "longer than"),
])
def test_result_faults_are_found(result, fault):
    assert any(fault in e for e in lc.validate(result, "result")), lc.validate(result, "result")


def test_builtin_validator_agrees_with_jsonschema_when_it_is_installed():
    try:
        import jsonschema
    except ImportError:
        return
    schema = lc.load_schema()
    for sample in ({"status": "collected", "facts": {"a": 1}}, {"status": "nope"}, {"facts": {}},
                   {"status": "collected", "children": [{"kind": "process", "value": "x", "name": "n"}]}):
        ours = lc.validate(sample, "result") == []
        ref = {"$ref": "#/$defs/result", "$defs": schema["$defs"]}
        theirs = not list(jsonschema.Draft202012Validator(ref).iter_errors(sample))
        assert ours == theirs, sample


# ── Selection ────────────────────────────────────────────────────────────────

def test_collector_runs_only_where_its_component_was_detected():
    state = _begin(_components(("db01", "postgresql"), ("web01", "nginx"), ("idle01", "openssh_server")),
                   hosts=["db01", "web01", "idle01", "empty01"])
    sel = lc.select(state, 1, "host")
    assert set(sel["by_host"]) == {"db01"}
    assert [i["file"] for i in sel["by_host"]["db01"]] == ["postgresql_host.yml"]
    target = sel["items"][0]["target"]
    assert lc.validate(target, "target") == []
    assert target["layer_number"] == 2 and target["parent"] == {"kind": "host", "id": "db01"}


def test_detected_component_with_no_collector_is_recorded_not_dropped():
    state = _begin(_components(("web01", "nginx")))
    assert lc.select(state, 1, "host")["items"] == []
    row = _rows(state, component_key="nginx")[0]
    assert row["status"] == "not_collected" and row["reason"] == "no collector"
    assert row["layer"] == 2 and row["parent_kind"] == "host" and row["parent_id"] == "web01"
    done = lc.finish(state, CATALOG)
    assert done["summary"]["not_assessed_by_reason"] == {"no collector": 1}


def test_declared_but_unbuilt_service_side_is_reported_with_its_layer():
    state = _begin(_components(("db01", "postgresql")))
    row = _rows(state, component_key="postgresql", layer=3)[0]
    assert row["status"] == "not_collected" and "no collector for the service side yet" in row["reason"]


def test_host_outside_the_inventory_is_never_targeted():
    state = _begin(_components(("ghost01", "postgresql")), hosts=["db01"])
    assert lc.select(state, 1, "host")["by_host"] == {}
    assert _rows(state, layer=2)[0]["reason"] == "host is not in the inventory of this job"


def test_cost_and_layer_filters_leave_no_false_gap():
    state = _begin(_components(("db01", "postgresql")), layers="service")
    assert lc.select(state, 1, "host")["items"] == []
    done = lc.finish(state, CATALOG)
    skipped = done["summary"]["not_in_this_run"]
    assert skipped and skipped[0]["collector"] == "postgresql_host.yml" and "not part of this run" in skipped[0]["why"]
    assert not [r for r in done["payload"]["facts"] if r["layer"] == 2]      # no row that would hide older facts


def test_settings_out_of_range_are_refused():
    with pytest.raises(ValueError):
        _begin([], max_depth=6)
    with pytest.raises(ValueError):
        _begin([], cost="free")


def test_dry_run_reports_selection_without_results():
    plan = lc.dry_run({"now": NOW, "inventory_hosts": ["db01"],
                       "components": _components(("db01", "postgresql"), ("db01", "openssh_server"))}, CATALOG, env={})
    assert plan["would_run"] == [{"host": "db01", "component": "postgresql", "layer": 2,
                                  "collector": "postgresql_host.yml", "cost": "cheap"}]
    assert {(n["component"], n["reason"]) for n in plan["not_assessed"]} >= {("openssh_server", "no collector")}


# ── Results ──────────────────────────────────────────────────────────────────

def _one(result=None, max_facts_bytes=None, entry=None):
    kw = {"max_facts_bytes": max_facts_bytes} if max_facts_bytes else {}
    state = _begin(_components(("db01", "postgresql")), **kw)
    sel = lc.select(state, 1, "host")
    lc.record(state, CATALOG, _answer(sel, lambda it: entry or _ok(result)))
    return state, _rows(state, component_key="postgresql", layer=2)[0]


def test_collected_result_is_stored_with_layer_parent_collector_and_size():
    _, row = _one({"status": "collected", "facts": {"settings": {"ssl": "on"}},
                   "instance": {"identity": "host/db01/port/5432"}})
    assert row["status"] == "collected" and row["instance_id"] == "postgresql:host/db01/port/5432"
    assert (row["layer"], row["parent_kind"], row["parent_id"], row["depth"]) == (2, "host", "db01", 1)
    assert row["collector"] == "postgresql_host.yml" and row["collector_version"] == "1.0" and row["cost"] == "cheap"
    assert row["facts_bytes"] == len(json.dumps(row["facts"], sort_keys=True, separators=(",", ":")))
    assert row["catalog_version"] == CATALOG["catalog_version"] and len(row["facts_sha256"]) == 64


def test_refined_instance_identity_keeps_the_same_target_key():
    """A collector that fails once and later returns an identity must not leave a stale twin."""
    _, failed = _one(entry={"failed": True, "error": "x"})
    _, ok = _one({"status": "collected", "facts": {"a": 1}, "instance": {"identity": "host/db01/port/5432"}})
    assert failed["instance_id"] != ok["instance_id"]
    key = ("target_id", "component_key", "layer", "parent_kind", "parent_id")
    assert [failed[k] for k in key] == [ok[k] for k in key] and ok["target_id"] == "postgresql:host/db01"


@pytest.mark.parametrize("entry, reason", [
    ({"failed": True, "error": 'task "x" failed'}, "collector failed"),
    ({"result": {}, "failed": False}, "does not satisfy the contract"),
    ({"result": {"status": "not_collected"}, "failed": False}, "needs a reason"),
    ({"result": {"status": "collected", "facts": {}}, "failed": False}, "returned no facts"),
    ({"result": {"status": "not_collected", "reason": "service stopped"}, "failed": False}, "service stopped"),
])
def test_every_bad_outcome_is_not_assessed_with_a_reason(entry, reason):
    _, row = _one(entry=entry)
    assert row["status"] == "not_collected" and reason in row["reason"] and row["facts"] == {}


def test_missing_result_is_not_assessed():
    state = _begin(_components(("db01", "postgresql")))
    lc.select(state, 1, "host")
    lc.record(state, CATALOG, {})                       # host not reachable: nothing came back
    assert "no result returned" in _rows(state, layer=2)[0]["reason"]


def test_size_cap_drops_the_facts_and_says_so():
    _, row = _one({"status": "collected", "facts": {"blob": "x" * 5000}}, max_facts_bytes=2048)
    assert row["status"] == "not_collected" and "over the size cap" in row["reason"] and row["facts"] == {}


def test_secret_values_are_not_stored():
    _, row = _one({"status": "collected", "facts": {"a": {"password": "hunter2", "Token": "abc", "port": "5432"},
                                                    "password_encryption": "scram-sha-256"}})
    assert row["facts"]["a"] == {"password": lc.REDACTED, "Token": lc.REDACTED, "port": "5432"}
    assert row["facts"]["password_encryption"] == "scram-sha-256"
    assert "hunter2" not in json.dumps(row) and any("redacted" in n for n in row["notes"])


def test_private_key_material_stops_the_whole_result():
    _, row = _one({"status": "collected", "facts": {"cert": "ok", "k": "-----BEGIN RSA PRIVATE KEY-----\nMIIE"}})
    assert row["status"] == "not_collected" and "private key" in row["reason"] and row["facts"] == {}


def test_untrusted_strings_cannot_alter_the_sql():
    _, row = _one({"status": "collected", "facts": {"note": "'); DROP TABLE component_facts; --"}})
    state = _begin(_components(("db01", "postgresql")))
    state["rows"].append(row)
    sql = lc.persist_sql(lc.finish(state, CATALOG)["payload"])
    assert "DROP TABLE component_facts" not in sql
    body = re.sub(r"--[^\n]*", "", sql.replace("ON COMMIT DROP", ""))
    assert not re.search(r"\b(DELETE|TRUNCATE|DROP|ALTER)\b", body)


def test_schema_is_additive():
    ddl = re.sub(r"--[^\n]*", "", (_root / "ansible/files/layered_collection_schema.sql").read_text())
    assert not re.search(r"\b(DROP|DELETE|TRUNCATE|ALTER)\b", ddl)
    for stmt in re.findall(r"CREATE\s+[^;]+;", ddl):
        assert re.match(r"CREATE (TABLE|INDEX) IF NOT EXISTS|CREATE OR REPLACE VIEW", stmt), stmt[:60]


def test_finish_fails_closed_when_a_detected_component_has_no_outcome():
    state = _begin(_components(("db01", "postgresql")))
    state["rows"], state["queue"], state["service_pending"] = [], [], []
    with pytest.raises(RuntimeError):
        lc.finish(state, CATALOG)


# ── Generality proof: a made-up component, one catalog entry + one collector file ──

def _collectors_dir(tmp_path):
    d = tmp_path / "collectors"
    d.mkdir(exist_ok=True)
    for p in list(SHIPPED_DIR.glob("*.yml")) + list(STUBS.glob("acme_queue_*.yml")):
        shutil.copy(p, d / p.name)
    return d


def _acme_catalog(tmp_path):
    raw = yaml.safe_load((_root / "ansible/vars/component_catalog.yml").read_text())
    raw["components"].append(copy.deepcopy(ACME))
    path = tmp_path / "catalog.yml"
    path.write_text(yaml.safe_dump(raw))
    return lc.load_catalog(path, _collectors_dir(tmp_path)), _collectors_dir(tmp_path)


def _acme_host(name):
    row = copy.deepcopy(next(r for r in FIXTURE["round1"] if r["host_id"] == "jump01.example.com"))
    row["host_id"] = row["hostname"] = name
    row["facts"]["processes"]["command_names"].append("acme-queued")
    return row


def test_made_up_component_flows_from_detection_to_coverage(tmp_path):
    catalog, cdir = _acme_catalog(tmp_path)

    # Layer 1: detection, from stored facts, with the unchanged step-1 code.
    plan = cd.build_plan({"now": NOW, "hosts": [_acme_host("q01.example.com"), _acme_host("q02.example.com")]}, catalog)
    detected = [r for r in plan["payload"]["components"] if r["component_key"] == "acme_queue"]
    assert {r["hostname"] for r in detected} == {"q01.example.com", "q02.example.com"}

    # Dispatch: host side on both hosts, and on no other.
    state = _begin([dict(r, status="detected") for r in plan["payload"]["components"]], catalog,
                   hosts=["q01.example.com", "q02.example.com", "other01.example.com"])
    sel = lc.select(state, 1, "host")
    acme_items = [i for i in sel["items"] if i["target"]["component_key"] == "acme_queue"]
    assert {i["target"]["host"] for i in acme_items} == {"q01.example.com", "q02.example.com"}
    assert all((cdir / i["file"]).is_file() for i in sel["items"])
    stub = _stub_result(cdir / "acme_queue_host.yml")
    lc.record(state, catalog, _answer(sel, lambda it: _ok(stub) if it["file"] == "acme_queue_host.yml"
                                      else {"failed": True, "error": "not part of this test"}))

    # Storage: one instance, reached through two hosts, one layer-2 row per host.
    l2 = _rows(state, component_key="acme_queue", layer=2)
    assert {r["instance_id"] for r in l2} == {"acme_queue:cluster/acme-prod"} and len(l2) == 2
    assert {r["parent_id"] for r in l2} == {"q01.example.com", "q02.example.com"}

    # Service side: once per instance; without the credential it is recorded, not failed.
    assert lc.select(copy.deepcopy(state), 1, "service", env={})["items"] == []
    no_cred = copy.deepcopy(state)
    lc.select(no_cred, 1, "service", env={})
    row = _rows(no_cred, component_key="acme_queue", layer=3)[0]
    assert row["status"] == "not_collected" and "no credential of type 'Acme Queue Read-Only'" in row["reason"]
    assert row["reached_through"] == ["q01.example.com", "q02.example.com"]

    svc = lc.select(state, 1, "service", env={"ACME_QUEUE_URL": "https://q.example.com", "ACME_QUEUE_TOKEN": "t"})
    assert len(svc["items"]) == 1 and list(svc["by_host"]) == ["localhost"]
    target = svc["items"][0]["target"]
    assert target["reached_through"] == ["q01.example.com", "q02.example.com"] and target["layer_number"] == 3
    assert target["credential_type"] == "Acme Queue Read-Only"
    assert "t" not in json.dumps(target["credential_env"]) or target["credential_env"] == ["ACME_QUEUE_URL", "ACME_QUEUE_TOKEN"]
    lc.record(state, catalog, _answer(svc, lambda it: _ok(_stub_result(cdir / it["file"]))))
    assert _rows(state, component_key="acme_queue", layer=3)[0]["status"] == "collected"

    # Layer 4: what the stub reported inside it is inventoried with its parent.
    kids = {(c["via_host"], c["child_value"]): c for c in state["children"]}
    pg = kids[("q01.example.com", "quay.io/sclorg/postgresql-16-c9s:latest")]
    assert pg["recognised_as"] == "postgresql" and pg["disposition"] == "assess" and pg["depth"] == 2
    assert pg["parent_instance_id"] == "acme_queue:cluster/acme-prod"
    assert kids[("q01.example.com", "acme-worker")]["disposition"] == "not_recognised"

    # Pass 2: the recognised child gets its collector, on the host it was found through.
    sel2 = lc.select(state, 2, "host")
    assert {(i["target"]["host"], i["file"], i["target"]["depth"]) for i in sel2["items"]} == {
        ("q01.example.com", "postgresql_host.yml", 2), ("q02.example.com", "postgresql_host.yml", 2)}
    assert sel2["items"][0]["target"]["parent"] == {"kind": "instance", "id": "acme_queue:cluster/acme-prod"}
    lc.record(state, catalog, _answer(sel2, lambda it: _ok({"status": "collected", "facts": {"version": "16"}})))

    # Coverage report and the SQL that stores it.
    done = lc.finish(state, catalog)
    cov = [c for c in done["summary"]["coverage"] if c["component"] == "acme_queue"]
    assert {(c["layer"], c["coverage"]) for c in cov} == {(2, "facts collected"), (3, "facts collected")}
    assert "acme_queue" in lc.format_summary(done["summary"])
    assert done["summary"]["passes_run"] == 2 and done["summary"]["unaccounted"] == []
    assert {r["component_key"] for r in lc.collector_rows(catalog)} >= {"acme_queue"}
    assert "INSERT INTO component_facts" in lc.persist_sql(done["payload"])


def test_depth_limit_inventories_but_does_not_collect(tmp_path):
    catalog, cdir = _acme_catalog(tmp_path)
    state = _begin(_components(("q01", "acme_queue")), catalog, max_depth=1, layers="host")
    sel = lc.select(state, 1, "host")
    lc.record(state, catalog, _answer(sel, lambda it: _ok(_stub_result(cdir / it["file"]))))
    kid = next(c for c in state["children"] if c["recognised_as"] == "postgresql")
    assert kid["disposition"] == "depth_limit"
    assert lc.select(state, 2, "host")["items"] == []
    assert any("depth limit (1) reached" in r["reason"] for r in _rows(state, component_key="postgresql"))


def test_child_whose_catalog_entry_is_not_for_assessment_is_inventory_only(tmp_path):
    catalog, cdir = _acme_catalog(tmp_path)
    next(c for c in catalog["components"] if c["key"] == "postgresql")["assess"] = False
    state = _begin(_components(("q01", "acme_queue")), catalog, layers="host")
    sel = lc.select(state, 1, "host")
    lc.record(state, catalog, _answer(sel, lambda it: _ok(_stub_result(cdir / it["file"]))))
    kid = next(c for c in state["children"] if c["recognised_as"] == "postgresql")
    assert kid["disposition"] == "inventory_only" and lc.select(state, 2, "host")["items"] == []


def test_child_outside_what_the_parent_may_contain_is_not_recognised(tmp_path):
    catalog, cdir = _acme_catalog(tmp_path)
    next(c for c in catalog["components"] if c["key"] == "acme_queue")["contains"] = []
    state = _begin(_components(("q01", "acme_queue")), catalog, layers="host")
    sel = lc.select(state, 1, "host")
    lc.record(state, catalog, _answer(sel, lambda it: _ok(_stub_result(cdir / it["file"]))))
    assert {c["disposition"] for c in state["children"]} == {"not_recognised"}


def test_dispatcher_and_shared_tasks_name_no_component():
    """The generic parts must work for any component, so they may name none."""
    words = {c["key"] for c in CATALOG["components"]}
    for c in CATALOG["components"]:
        for col in c.get("collectors") or []:
            words.add(col["file"].rsplit(".", 1)[0])
            words.add((col.get("credential") or {}).get("type", ""))
    words |= {"kubernetes", "kubelet", "kube", "etcd", "postgres", "postmaster", "pg_hba"}
    words.discard("")
    words.discard(lc.NO_COLLECTOR)
    for rel in GENERIC_FILES:
        text = (_root / rel).read_text().lower()
        # The Ansible collection and the module that talk to the compliance database are not components.
        text = text.replace("community.postgresql.postgresql_", "db_module_")
        # Nor is the default login of the compliance database (same default as step 1).
        text = text.replace("pg_user | default('postgres')", "pg_user")
        for w in sorted(words):
            assert not re.search(r"(?<![a-z0-9_])" + re.escape(w.lower()) + r"(?![a-z0-9_])", text), \
                f"{rel} names the component {w!r}"


def test_dispatcher_runs_collectors_only_through_the_shared_tasks_file():
    text = (_root / "ansible/playbooks/layered_collection_pass.yml").read_text()
    assert text.count("../tasks/layered_run_collector.yml") == 2
    assert text.count("../tasks/layered_store_results.yml") == 2
    assert "component_collectors" not in text
    main = (_root / "ansible/playbooks/collect_component_facts.yml").read_text()
    assert main.count("import_playbook: layered_collection_pass.yml") == lc.HARD_MAX_DEPTH


def test_seeded_job_template_takes_no_free_variables():
    tpl = yaml.safe_load((_root / "install/existing-aap/extended/playbooks/automation_execution/templates/"
                          "collect_component_facts.yml").read_text())
    jt = next(t["ansible.controller.job_template"] for t in tpl if "ansible.controller.job_template" in t)
    assert jt["ask_variables_on_launch"] is False and jt["survey_enabled"] is True
    assert "limit" not in jt and jt.get("ask_limit_on_launch", False) is False
    survey = yaml.safe_load((_root / "install/existing-aap/extended/playbooks/vars/"
                             "collect_component_facts_survey.yml").read_text())
    for q in survey["aac_collect_component_facts_survey_spec"]["spec"]:
        assert q["type"] == "multiplechoice", q["variable"]


def test_launch_guard_refuses_other_database_and_outside_paths(tmp_path):
    site = tmp_path / "site_config.yml"
    site.write_text("pg_host: db.example.com\n")
    inside = _root / "ansible/vars/component_catalog.yml"
    assert lc.check_launch("db.example.com", site, inside, SHIPPED_DIR) == []
    assert any("not the configured" in p for p in lc.check_launch("evil.example.com", site, inside, SHIPPED_DIR))
    assert any("outside the project" in p for p in lc.check_launch("db.example.com", site, inside, tmp_path))
