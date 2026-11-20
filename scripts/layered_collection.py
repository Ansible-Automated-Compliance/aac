#!/usr/bin/env python3
"""
layered_collection.py - which collector runs where, and what came back.

Layered fact gathering: base host facts (0) -> detection (1) -> component facts,
host side (2) -> component facts, service side (3) -> what is inside a component
(4), fed back to detection, to a bounded depth.

This module holds no component-specific logic. Everything it knows about a
component comes from the detection catalog (ansible/vars/component_catalog.yml)
and from the collector result. It is the single home of:

  validate()                  the collector contract, checked against the schema
  validate_layering()         the catalog fields for layered collection
  begin()                     component map -> work queue and "not assessed" rows
  select()                    the collectors to run in one pass, for one layer
  record()                    collector results -> fact rows, children, next pass
  finish()                    summary, coverage table and one SQL script

CLI (used by ansible/playbooks/collect_component_facts.yml):

  layered_collection.py check-launch | check-catalog | begin | select | record | finish | dry-run

Reference: docs/reference/LAYERED_FACT_GATHERING.md and
docs/reference/COMPONENT_COLLECTOR_CONTRACT.md
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("component_discovery", _HERE / "component_discovery.py")
cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cd)

PROJECT_ROOT = _HERE.parent
# The host-side guard: the same secret patterns and code rules are applied here.
_gspec = importlib.util.spec_from_file_location(
    "component_collector_guard", _HERE.parent / "ansible" / "files" / "component_collector_guard.py")
guard = importlib.util.module_from_spec(_gspec)
_gspec.loader.exec_module(guard)

DEFAULT_CATALOG = cd.DEFAULT_CATALOG
DEFAULT_COLLECTORS_DIR = PROJECT_ROOT / "ansible" / "tasks" / "component_collectors"
SCHEMA_FILE = PROJECT_ROOT / "ansible" / "files" / "component_collector_contract.schema.json"

CONTRACT_VERSION = "1"
LAYER_NUMBER = {"host": 2, "service": 3}
HARD_MAX_DEPTH = 5
DEFAULT_MAX_DEPTH = 3
DEFAULT_MAX_FACTS_BYTES = 512 * 1024
MAX_CHILDREN = 2000
NO_COLLECTOR = "none yet"
REDACTED = "<redacted>"

_SECRET_KEYS = guard.SECRET_KEYS
_PRIVATE_KEY = guard.PRIVATE_KEY
_JINJA_MARKS = ("{{", "{%", "{#")
_ID_UNSAFE = re.compile(r"[^A-Za-z0-9._:/@-]")


def has_template_marks(value) -> bool:
    """True when any string in the value carries a template delimiter."""
    if isinstance(value, dict):
        return any(has_template_marks(k) or has_template_marks(v) for k, v in value.items())
    if isinstance(value, list):
        return any(has_template_marks(v) for v in value)
    return isinstance(value, str) and any(m in value for m in _JINJA_MARKS)


def display_safe(value):
    """A copy for job output: template delimiters are broken apart so that
    printing a stored string can never evaluate it. Storage keeps the original."""
    if isinstance(value, dict):
        return {display_safe(k): display_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [display_safe(v) for v in value]
    if isinstance(value, str):
        for m in _JINJA_MARKS:
            value = value.replace(m, m[0] + " " + m[1])
        return value
    return value


# ── The contract schema and a validator for the subset of JSON Schema it uses ─

def load_schema(path=None) -> dict:
    with open(path or SCHEMA_FILE, encoding="utf-8") as fh:
        return json.load(fh)


_SCHEMA = None


def _schema() -> dict:
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = load_schema()
    return _SCHEMA


_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool}


def _check(value, schema, root, where, errs):
    if "$ref" in schema:
        schema = root["$defs"][schema["$ref"].rsplit("/", 1)[1]]
    if "const" in schema and value != schema["const"]:
        errs.append(f"{where}: must be {schema['const']!r}")
        return
    if "enum" in schema and (isinstance(value, bool) or value not in schema["enum"]):
        errs.append(f"{where}: {value!r} is not one of {schema['enum']}")
        return
    t = schema.get("type")
    if t == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            errs.append(f"{where}: must be an integer")
            return
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{where}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{where}: above {schema['maximum']}")
    elif t in _TYPES:
        if not isinstance(value, _TYPES[t]) or (t != "boolean" and isinstance(value, bool)):
            errs.append(f"{where}: must be of type {t}")
            return
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errs.append(f"{where}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append(f"{where}: longer than {schema['maxLength']} characters")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{where}: does not match {schema['pattern']}")
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{where}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append(f"{where}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, v in enumerate(value[:5000]):
                _check(v, schema["items"], root, f"{where}[{i}]", errs)
    elif isinstance(value, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{where}: {k} is required")
        if schema.get("additionalProperties") is False:
            for k in value:
                if k not in props:
                    errs.append(f"{where}: unknown field {str(k)[:60]!r}")
        for k, sub in props.items():
            if k in value:
                _check(value[k], sub, root, f"{where}.{k}", errs)


def validate(value, definition, where=None) -> list[str]:
    """Faults of `value` against one definition of the contract schema ([] means valid)."""
    errs: list[str] = []
    root = _schema()
    _check(value, root["$defs"][definition], root, where or definition, errs)
    return errs


# ── Catalog fields for layered collection ────────────────────────────────────

def validate_layering(catalog, collectors_dir=None) -> list[str]:
    """Faults in the layered-collection fields of the catalog ([] means valid)."""
    errs = list(cd.validate_catalog(catalog))
    if errs:
        return errs
    cdir = Path(collectors_dir or DEFAULT_COLLECTORS_DIR)
    keys = {c["key"] for c in catalog["components"]}
    for comp in catalog["components"]:
        key = comp["key"]
        where = f"component {key!r}"
        errs += validate({k: comp[k] for k in ("assess", "contains", "collectors") if k in comp},
                         "catalog_layering", where)
        for other in comp.get("contains") or []:
            if isinstance(other, str) and other != "*" and other not in keys:
                errs.append(f"{where}: contains {other!r}, which is not a catalog key")
        seen = set()
        for col in comp.get("collectors") or []:
            if not isinstance(col, dict) or col.get("layer") not in LAYER_NUMBER:
                continue
            layer = col["layer"]
            if layer in seen:
                errs.append(f"{where}: two collectors for the {layer} side")
            seen.add(layer)
            fname = col.get("file")
            if layer == "service" and "credential" not in col:
                errs.append(f"{where}: the service-side collector must name its credential type")
            if layer == "host" and "credential" in col:
                errs.append(f"{where}: a host-side collector uses the connection already in use; no credential")
            if fname and fname != NO_COLLECTOR:
                if fname != f"{key}_{layer}.py":
                    errs.append(f"{where}: collector file must be named {key}_{layer}.py")
                elif not (cdir / fname).is_file():
                    errs.append(f"{where}: collector file {fname} does not exist in {cdir.name}/")
                else:
                    # A collector reaches a host only through the guard.
                    for fault in guard.check_code((cdir / fname).read_text(encoding="utf-8")):
                        errs.append(f"{where}: collector {fname}: {fault}")
                if "version" not in col:
                    errs.append(f"{where}: collector {fname} needs a version")
    return errs


def load_catalog(path=None, collectors_dir=None) -> dict:
    catalog = cd.load_catalog(path)
    errs = validate_layering(catalog, collectors_dir)
    if errs:
        raise ValueError("component catalog is not valid for layered collection:\n  " + "\n  ".join(errs))
    return catalog


def collector_rows(catalog) -> list[dict]:
    """The declared collectors as rows for the component_collectors table."""
    rows = []
    for comp in catalog["components"]:
        for col in comp.get("collectors") or []:
            rows.append({
                "component_key": comp["key"], "layer": LAYER_NUMBER[col["layer"]],
                "collector": col["file"], "collector_version": col.get("version"),
                "cost": col["cost"], "credential_type": (col.get("credential") or {}).get("type"),
                "access_needed": col["access"], "assess": comp.get("assess", True),
                "contains": list(comp.get("contains") or []),
            })
    return rows


# ── Work queue ───────────────────────────────────────────────────────────────

def _now(value=None):
    return cd.iso(cd.parse_ts(value) or datetime.now(timezone.utc))


def _row(state, *, instance_id, key, layer, parent, reached, depth, status, reason="",
         col=None, facts=None, notes=None, target_id=None) -> dict:
    """One fact row. Every row names its layer and its parent."""
    facts = facts or {}
    blob = json.dumps(facts, sort_keys=True, separators=(",", ":"))
    return {
        "instance_id": instance_id, "target_id": target_id or instance_id,
        "component_key": key, "layer": LAYER_NUMBER[layer],
        "parent_kind": parent["kind"], "parent_id": parent["id"],
        "reached_through": sorted(set(h for h in reached if h)), "depth": depth,
        "status": status, "reason": reason,
        "collector": (col or {}).get("file") if (col or {}).get("file") != NO_COLLECTOR else None,
        "collector_version": (col or {}).get("version"), "cost": (col or {}).get("cost"),
        "credential_type": ((col or {}).get("credential") or {}).get("type"),
        "catalog_version": state["catalog_version"], "collected_at": state["now"],
        "facts": facts, "facts_bytes": len(blob.encode("utf-8")) if facts else 0,
        "facts_sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest() if facts else "",
        "notes": list(notes or []),
    }


def _not_collected(state, reason, **kw):
    state["rows"].append(_row(state, status="not_collected", reason=reason, **kw))


def _filtered_out(state, col) -> str:
    s = state["settings"]
    if s["layers"] != "all" and col["layer"] != s["layers"]:
        return f"{col['layer']} side is not part of this run"
    if s["cost"] == "cheap" and col["cost"] != "cheap":
        return "heavy collector, not part of a cheap run"
    return ""


def _enqueue(state, comp, *, host, depth, parent, instance_id, locator):
    """Queue the collectors of one detected component, or record why none runs."""
    key = comp["key"]
    common = dict(instance_id=instance_id, key=key, parent=parent, reached=[host], depth=depth)
    cols = comp.get("collectors") or []
    if not comp.get("assess", True):
        _not_collected(state, "assessment is switched off for this component in the catalog (assess: false)",
                       layer="host", **common)
        return
    if not cols:
        _not_collected(state, "no collector", layer="host", **common)
        return
    for col in cols:
        layer = col["layer"]
        if col["file"] == NO_COLLECTOR:
            _not_collected(state, f"no collector for the {layer} side yet", layer=layer, col=col, **common)
            continue
        why = _filtered_out(state, col)
        if why:
            state["filtered"].append({"host": host, "component": key, "layer": layer,
                                      "collector": col["file"], "why": why})
            continue
        entry = {"component_key": key, "layer": layer, "host": host, "depth": depth, "parent": parent,
                 "instance_id": instance_id, "locator": locator, "collector": col}
        if layer == "host":
            if not host:
                _not_collected(state, "found through the service side: there is no host to run a host-side "
                               "collector on", layer=layer, col=col, **common)
            elif host not in state["inventory_hosts"]:
                _not_collected(state, "host is not in the inventory of this job", layer=layer, col=col, **common)
            else:
                state["queue"].append(entry)
        else:
            state["service_pending"].append(entry)


def begin(data, catalog) -> dict:
    """The component map of step 1 -> the work queue of pass 1.

    data: {now, job_id, cost: cheap|all, layers: host|service|all, max_depth,
    max_facts_bytes, inventory_hosts: [...], components: [rows of
    v_host_components_current], known_instances: [{host, component_key,
    instance_id}] from earlier runs}
    """
    if data.get("map_b64"):
        # The component map as the database returned it, base64 so that names
        # stored there never pass through a template.
        stored = json.loads(base64.b64decode(data["map_b64"]).decode("utf-8"))
        data = dict(data, components=stored.get("components") or [],
                    known_instances=stored.get("known_instances") or [])
    depth = int(data.get("max_depth", DEFAULT_MAX_DEPTH))
    if not 1 <= depth <= HARD_MAX_DEPTH:
        raise ValueError(f"max_depth must be 1 to {HARD_MAX_DEPTH}")
    cost, layers = data.get("cost", "all"), data.get("layers", "all")
    if cost not in ("cheap", "all") or layers not in ("host", "service", "all"):
        raise ValueError("cost must be cheap or all; layers must be host, service or all")
    state = {
        "now": _now(data.get("now")), "catalog_version": catalog["catalog_version"],
        "settings": {"cost": cost, "layers": layers, "max_depth": depth, "job_id": data.get("job_id"),
                     "max_facts_bytes": int(data.get("max_facts_bytes", DEFAULT_MAX_FACTS_BYTES))},
        "inventory_hosts": sorted({str(h) for h in data.get("inventory_hosts") or []}),
        "queue": [], "service_pending": [], "awaiting": {}, "rows": [], "children": [], "filtered": [],
        "instances": {f"{k['host']}|{k['component_key']}": k["instance_id"]
                      for k in data.get("known_instances") or []},
        "passes_run": 0, "seq": 0, "detected": [],
        "guard": {k: list(v) for k, v in (catalog.get("collector_guard") or {}).items()
                  if k in ("binary_dirs", "runtime_parents")},
    }
    by_key = {c["key"]: c for c in catalog["components"]}
    seen = set()
    for r in sorted(data.get("components") or [], key=lambda r: (str(r.get("hostname")), str(r.get("component_key")))):
        host, key = str(r.get("hostname") or r.get("host_id") or ""), str(r.get("component_key") or "")
        if not host or not key or (host, key) in seen:
            continue
        seen.add((host, key))
        state["detected"].append({"host": host, "component": key})
        parent, iid = {"kind": "host", "id": host}, f"{key}:host/{host}"
        comp = by_key.get(key)
        if comp is None:
            _not_collected(state, "the component is not in the current catalog", instance_id=iid, key=key,
                           layer="host", parent=parent, reached=[host], depth=1)
            continue
        locator = {"found_by": "detection", "evidence": [
            {"kind": e.get("kind"), "value": e.get("value")} for e in (r.get("evidence") or [])[:50]
            if isinstance(e, dict)]}
        _enqueue(state, comp, host=host, depth=1, parent=parent, instance_id=iid, locator=locator)
    return state


def _target(state, entry, reached, credential_ok=True) -> dict:
    col = entry["collector"]
    cred = col.get("credential") or {}
    state["seq"] += 1
    item_id = f"i{state['seq']}"
    target = {
        "contract_version": CONTRACT_VERSION, "component_key": entry["component_key"],
        "layer": entry["layer"], "layer_number": LAYER_NUMBER[entry["layer"]],
        "instance_id": entry["instance_id"], "parent": entry["parent"],
        "host": entry["host"] if entry["layer"] == "host" else "",
        "reached_through": sorted(set(h for h in reached if h)),
        "depth": entry["depth"], "max_depth": state["settings"]["max_depth"],
        "credential_type": cred.get("type", ""), "credential_env": list(cred.get("env") or []),
        "locator": entry.get("locator") or {}, "max_facts_bytes": state["settings"]["max_facts_bytes"],
        "collector": {"file": col["file"], "version": col.get("version", "0.0"), "cost": col["cost"]},
        "guard": state.get("guard") or {},
    }
    errs = validate(target, "target")
    if errs:  # a framework fault, never a collector's: stop.
        raise ValueError("collector input does not satisfy the contract: " + "; ".join(errs))
    state["awaiting"][item_id] = {"entry": entry, "target": target}
    # What Ansible sees of an item: an id, a file name from the validated
    # catalog, and the collector input as one base64 value. No string that a
    # host or a database row supplied is ever an Ansible variable as text.
    blob = base64.b64encode(json.dumps(target, sort_keys=True).encode("utf-8")).decode("ascii")
    return {"item_id": item_id, "file": col["file"], "target_b64": blob, "target": target}


def select(state, pass_no, layer, env=None) -> dict:
    """The collectors to run in this pass for one layer: {items, by_host}."""
    env = os.environ if env is None else env
    items = []
    if pass_no > state["settings"]["max_depth"]:
        return {"items": [], "by_host": {}}
    if layer == "host":
        todo = [e for e in state["queue"] if e["depth"] == pass_no]
        state["queue"] = [e for e in state["queue"] if e["depth"] != pass_no]
        for e in todo:
            items.append(_target(state, e, [e["host"]]))
    else:
        todo = [e for e in state["service_pending"] if e["depth"] == pass_no]
        state["service_pending"] = [e for e in state["service_pending"] if e["depth"] != pass_no]
        groups: dict[tuple, dict] = {}
        for e in todo:
            # One run per service instance, however many hosts lead to it.
            iid = state["instances"].get(f"{e['host']}|{e['component_key']}", e["instance_id"]) \
                if e["depth"] == 1 else e["instance_id"]
            g = groups.setdefault((e["component_key"], iid), {"entry": dict(e, instance_id=iid), "hosts": []})
            g["hosts"].append(e["host"])
        for (key, iid), g in sorted(groups.items()):
            e = g["entry"]
            if e["depth"] == 1:
                e["parent"] = {"kind": "instance", "id": iid}
            cred = e["collector"].get("credential") or {}
            missing = [n for n in cred.get("env") or [] if not str(env.get(n, "")).strip()]
            if missing:
                _not_collected(state, f"service side not assessed: no credential of type "
                               f"'{cred.get('type')}' is attached to this job",
                               instance_id=iid, key=key, layer="service", parent=e["parent"],
                               reached=g["hosts"], depth=e["depth"], col=e["collector"])
                continue
            items.append(_target(state, e, g["hosts"]))
    safe = []
    for it in items:
        host = it["target"]["host"] or "localhost"
        # The only strings that become Ansible variables as text. Refuse rather than escape.
        if has_template_marks([host, it["file"], it["item_id"]]) or not re.fullmatch(r"[A-Za-z0-9+/=]+", it["target_b64"]):
            held = state["awaiting"].pop(it["item_id"])
            e, t = held["entry"], held["target"]
            _not_collected(state, "unsafe value: a name that would become an Ansible variable carries a template "
                           "delimiter", instance_id=t["instance_id"], key=e["component_key"], layer=e["layer"],
                           parent=t["parent"], reached=t["reached_through"], depth=e["depth"], col=e["collector"])
            continue
        safe.append(it)
    items = safe
    if items:
        state["passes_run"] = max(state["passes_run"], pass_no)
    by_host: dict[str, list] = {}
    for it in items:
        by_host.setdefault(it["target"]["host"] or "localhost", []).append(it)
    return {"items": items, "by_host": by_host}


def for_ansible(selection) -> dict:
    """The selection as the playbook receives it: ids, file names and base64 only."""
    return {"by_host": {h: [{"item_id": i["item_id"], "file": i["file"], "target_b64": i["target_b64"]}
                            for i in items] for h, items in selection["by_host"].items()},
            "count": len(selection["items"])}


# ── Results ──────────────────────────────────────────────────────────────────

def scrub(value, notes, path="facts"):
    """Remove values that must never be stored, whatever collector returned them.

    Returns (clean value, private key found). Values of fields named like a
    secret and secret-shaped text inside any string (password=..., user:pass@
    in a URL, bearer and JWT-like tokens, cloud access keys) are replaced; the
    patterns are the host-side guard's, applied a second time here.
    """
    if isinstance(value, dict):
        out, found = {}, False
        for k, v in value.items():
            if isinstance(v, str) and v and str(k).lower() in _SECRET_KEYS and v != REDACTED:
                out[k] = REDACTED
                notes.append(f"redacted {path}.{str(k)[:60]}")
                continue
            out[k], f = scrub(v, notes, f"{path}.{str(k)[:60]}")
            found = found or f
        return out, found
    if isinstance(value, list):
        out, found = [], False
        for v in value:
            c, f = scrub(v, notes, path)
            out.append(c)
            found = found or f
        return out, found
    if isinstance(value, str):
        if _PRIVATE_KEY.search(value):
            return REDACTED, True
        clean = guard.scrub_text(value)
        if clean != value:
            notes.append(f"redacted a secret-shaped value in {path}")
        return clean, False
    return value, False


def recognise(child, parent_comp, catalog):
    """The catalog entry a child matches, limited to what the parent may contain."""
    allowed = parent_comp.get("contains") or []
    for comp in catalog["components"]:
        if "*" not in allowed and comp["key"] not in allowed:
            continue
        for sig in comp["signals"]:
            if sig["kind"] != child["kind"] or sig["kind"] == "port" or sig.get("role", "server") != "server":
                continue
            match = cd._match_comm if sig["kind"] == "process" else cd._match
            if match(sig["match"], child["value"]):
                return comp
    return None


def _children(state, catalog, entry, target, iid, children, notes):
    by_key = {c["key"]: c for c in catalog["components"]}
    parent_comp = by_key[entry["component_key"]]
    depth = entry["depth"] + 1
    via = target["host"]
    seen = set()
    for ch in children[:MAX_CHILDREN]:
        ident = (ch["kind"], ch["value"], ch.get("name", ""))
        if ident in seen:
            continue
        seen.add(ident)
        comp = recognise(ch, parent_comp, catalog)
        label = ch.get("name") or ch["value"]
        # The label is a name a host supplied: only identifier characters go into an identity.
        child_iid = f"{comp['key']}:in/{iid}/{via + '/' if via else ''}{_ID_UNSAFE.sub('_', label)}"[:600] \
            if comp else None
        runnable = comp and any(c["file"] != NO_COLLECTOR for c in comp.get("collectors") or [])
        if comp is None:
            disposition = "not_recognised"
        elif not comp.get("assess", True):
            disposition = "inventory_only"
        elif not runnable:
            disposition = "no_collector"
        elif depth > state["settings"]["max_depth"]:
            disposition = "depth_limit"
        else:
            disposition = "assess"
        state["children"].append({
            "parent_instance_id": iid, "parent_component_key": entry["component_key"],
            "parent_layer": LAYER_NUMBER[entry["layer"]], "via_host": via,
            "child_kind": ch["kind"], "child_value": ch["value"], "child_name": ch.get("name", ""),
            "detail": ch.get("detail") or {}, "recognised_as": comp["key"] if comp else None,
            "child_instance_id": child_iid, "disposition": disposition, "depth": depth,
            "seen_at": state["now"], "catalog_version": state["catalog_version"]})
        if comp is None or disposition == "inventory_only":
            continue
        parent = {"kind": "instance", "id": iid}
        if disposition == "depth_limit":
            _not_collected(state, f"depth limit ({state['settings']['max_depth']}) reached", instance_id=child_iid,
                           key=comp["key"], layer="host", parent=parent, reached=[via], depth=depth)
            continue
        _enqueue(state, comp, host=via, depth=depth, parent=parent, instance_id=child_iid,
                 locator={"found_by": "parent", "kind": ch["kind"], "value": ch["value"],
                          "name": ch.get("name", ""), "detail": ch.get("detail") or {}})
    if len(children) > MAX_CHILDREN:
        notes.append(f"children capped at {MAX_CHILDREN} of {len(children)}")


def record(state, catalog, results) -> dict:
    """Collector results of one pass and layer -> fact rows, children and the next queue.

    results: {host: [{item_id, result_b64, failed, error}]}: the result is the
    guard's one base64 line, decoded here and nowhere else. (`result`, a plain
    object, is accepted from tests.) An item that was selected and has no
    result is recorded as not collected.
    """
    got = {}
    for host, entries in (results or {}).items():
        for r in entries or []:
            if isinstance(r, dict) and r.get("item_id") in state["awaiting"]:
                got[r["item_id"]] = r
    counts = {"collected": 0, "not_collected": 0}
    for item_id in sorted(state["awaiting"], key=lambda s: int(s[1:])):
        entry, target = state["awaiting"][item_id]["entry"], state["awaiting"][item_id]["target"]
        common = dict(key=entry["component_key"], layer=entry["layer"], parent=target["parent"],
                      reached=target["reached_through"], depth=entry["depth"], col=entry["collector"],
                      target_id=target["instance_id"])
        r = got.get(item_id)
        iid = target["instance_id"]
        if r is None:
            reason = "no result returned: the host was not reachable or the collector did not finish"
        elif r.get("failed"):
            reason = ("collector failed: " + str(r.get("error") or "no detail"))[:300]
        else:
            res = r.get("result")
            if "result_b64" in r:
                try:
                    res = json.loads(base64.b64decode(str(r["result_b64"]), validate=True).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    res = None
            errs = validate(res, "result", "result") if res is not None else \
                ["the collector returned no readable result"]
            if not errs and res["status"] == "not_collected" and not str(res.get("reason", "")).strip():
                errs = ["result: not_collected needs a reason"]
            if errs:
                reason = ("collector result does not satisfy the contract: " + "; ".join(errs[:3]))[:300]
            else:
                notes = list(res.get("notes") or [])
                if res.get("instance"):
                    iid = f"{entry['component_key']}:{res['instance']['identity']}"
                if res["status"] == "not_collected":
                    reason = guard.scrub_text(res["reason"])
                else:
                    facts, key_found = scrub(res.get("facts") or {}, notes)
                    kids, kids_key = scrub(res.get("children") or [], notes, "children")
                    key_found = key_found or kids_key
                    notes = [guard.scrub_text(n) for n in dict.fromkeys(notes)][:50]
                    size = len(json.dumps(facts, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                    if key_found:
                        reason = "collector returned private key material: nothing stored"
                    elif size > target["max_facts_bytes"]:
                        reason = f"facts are {size} bytes, over the size cap of {target['max_facts_bytes']}"
                    elif not facts:
                        reason = "collector returned no facts"
                    else:
                        if entry["layer"] == "host" and entry["depth"] == 1:
                            state["instances"][f"{entry['host']}|{entry['component_key']}"] = iid
                        _children(state, catalog, entry, target, iid, kids, notes)
                        state["rows"].append(_row(state, instance_id=iid, status="collected", facts=facts,
                                                  notes=notes, **common))
                        counts["collected"] += 1
                        continue
        _not_collected(state, reason, instance_id=iid, **common)
        counts["not_collected"] += 1
    state["awaiting"] = {}
    counts["queued_next"] = len(state["queue"]) + len(state["service_pending"])
    return counts


# ── Summary, coverage and SQL ────────────────────────────────────────────────

def coverage_rows(state) -> list[dict]:
    out = []
    for r in state["rows"]:
        out.append({
            "hosts": ",".join(r["reached_through"]) or "-", "component": r["component_key"],
            "layer": r["layer"], "depth": r["depth"], "instance": r["instance_id"],
            "parent": f"{r['parent_kind']}:{r['parent_id']}",
            "coverage": "facts collected" if r["status"] == "collected" else "detected, not assessed",
            "reason": r["reason"], "collector": r["collector"] or "-", "facts_bytes": r["facts_bytes"]})
    return sorted(out, key=lambda c: (c["hosts"], c["depth"], c["component"], c["layer"]))


def finish(state, catalog) -> dict:
    """Close the run: anything still queued is recorded, never dropped."""
    for e in state["queue"] + state["service_pending"]:
        _not_collected(state, "not reached: the run ended before this pass", instance_id=e["instance_id"],
                       key=e["component_key"], layer=e["layer"], parent=e["parent"], reached=[e["host"]],
                       depth=e["depth"], col=e["collector"])
    state["queue"], state["service_pending"] = [], []
    cov = coverage_rows(state)
    reasons: dict[str, int] = {}
    for c in cov:
        if c["coverage"] != "facts collected":
            reasons[c["reason"]] = reasons.get(c["reason"], 0) + 1
    dispositions: dict[str, int] = {}
    for ch in state["children"]:
        dispositions[ch["disposition"]] = dispositions.get(ch["disposition"], 0) + 1
    covered = {(h, r["component_key"]) for r in state["rows"] for h in r["reached_through"]}
    covered |= {(f["host"], f["component"]) for f in state["filtered"]}
    summary = {
        "catalog_version": state["catalog_version"], "contract_version": CONTRACT_VERSION,
        "run_at": state["now"], "max_depth": state["settings"]["max_depth"],
        "cost_filter": state["settings"]["cost"], "layer_filter": state["settings"]["layers"],
        "passes_run": state["passes_run"],
        "components_detected": len(state["detected"]),
        "hosts_with_components": len({d["host"] for d in state["detected"]}),
        "collected": sum(1 for c in cov if c["coverage"] == "facts collected"),
        "not_assessed": sum(1 for c in cov if c["coverage"] != "facts collected"),
        "not_assessed_by_reason": reasons,
        "not_in_this_run": state["filtered"],
        "children_inventoried": len(state["children"]), "children_by_disposition": dispositions,
        "instances": len({r["instance_id"] for r in state["rows"] if r["status"] == "collected"}),
        "unaccounted": sorted(f"{d['host']}/{d['component']}" for d in state["detected"]
                              if (d["host"], d["component"]) not in covered),
        "coverage": [{k: c[k] for k in ("hosts", "component", "layer", "depth", "coverage", "reason",
                                         "collector", "instance", "parent")} for c in cov],
    }
    if summary["unaccounted"]:  # fail closed: every detected component must have an outcome
        raise RuntimeError("detected components with no recorded outcome: " + ", ".join(summary["unaccounted"]))
    payload = {
        "run": {k: summary[k] for k in ("catalog_version", "contract_version", "run_at", "max_depth",
                                        "passes_run", "cost_filter", "layer_filter")},
        "collectors": collector_rows(catalog), "facts": state["rows"], "children": state["children"],
        "collected_parents": [{"instance_id": r["instance_id"], "layer": r["layer"],
                               "via_host": r["reached_through"][0] if r["layer"] == 2 and r["reached_through"] else ""}
                              for r in state["rows"] if r["status"] == "collected"],
    }
    payload["run"]["job_id"] = state["settings"].get("job_id")
    payload["run"]["summary"] = {k: v for k, v in summary.items() if k != "coverage"}
    return {"summary": summary, "payload": payload}


def format_summary(s) -> str:
    lines = [
        "Layered fact gathering",
        f"  catalog version          {s['catalog_version']} (collector contract {s['contract_version']})",
        f"  cost / layers / depth    {s['cost_filter']} / {s['layer_filter']} / {s['max_depth']}",
        f"  passes run               {s['passes_run']}",
        f"  components detected      {s['components_detected']} on {s['hosts_with_components']} hosts",
        f"  facts collected          {s['collected']}",
        f"  detected, not assessed   {s['not_assessed']}",
        f"  found inside components  {s['children_inventoried']} {s['children_by_disposition'] or ''}",
        f"  not in this run (filter) {len(s['not_in_this_run'])}",
        "", "Coverage",
        f"  {'host':<24} {'component':<26} {'L':<2} {'D':<2} {'coverage':<23} reason / collector",
    ]
    for c in s["coverage"]:
        tail = c["collector"] if c["coverage"] == "facts collected" else c["reason"]
        lines.append(f"  {c['hosts'][:24]:<24} {c['component'][:26]:<26} {c['layer']:<2} {c['depth']:<2} "
                     f"{c['coverage']:<23} {tail}")
    if s["not_assessed_by_reason"]:
        lines += ["", "Detected, not assessed: by reason"]
        lines += [f"  {n:>4}  {r}" for r, n in sorted(s["not_assessed_by_reason"].items(), key=lambda x: -x[1])]
    return "\n".join(lines)


# One script, one transaction; the data travels as one base64 value, so nothing
# a host returned can alter the SQL. Inserts and updates only.
_TS = "TIMESTAMPTZ"
_KEY = "target_id, component_key, layer, parent_kind, parent_id"
PERSIST_SQL = f"""\
BEGIN;
CREATE TEMP TABLE _lc_payload ON COMMIT DROP AS
  SELECT convert_from(decode('__PAYLOAD__', 'base64'), 'UTF8')::jsonb AS p;

INSERT INTO component_collection_runs (run_at, catalog_version, contract_version, max_depth, passes_run,
                                       cost_filter, layer_filter, job_id, summary)
SELECT (p->'run'->>'run_at')::{_TS}, p->'run'->>'catalog_version', p->'run'->>'contract_version',
       (p->'run'->>'max_depth')::int, (p->'run'->>'passes_run')::int, p->'run'->>'cost_filter',
       p->'run'->>'layer_filter', NULLIF(p->'run'->>'job_id', '')::bigint, p->'run'->'summary'
  FROM _lc_payload;

UPDATE component_collectors c SET in_current_catalog = false, updated_at = now()
 WHERE c.in_current_catalog
   AND NOT EXISTS (SELECT 1 FROM _lc_payload, jsonb_array_elements(p->'collectors') x
                    WHERE x->>'component_key' = c.component_key AND (x->>'layer')::int = c.layer);

INSERT INTO component_collectors (component_key, layer, collector, collector_version, cost, credential_type,
                                  access_needed, assess, contains, catalog_version, in_current_catalog, updated_at)
SELECT x->>'component_key', (x->>'layer')::int, x->>'collector', x->>'collector_version', x->>'cost',
       x->>'credential_type', x->>'access_needed', (x->>'assess')::boolean,
       ARRAY(SELECT jsonb_array_elements_text(x->'contains')), p->'run'->>'catalog_version', true, now()
  FROM _lc_payload, jsonb_array_elements(p->'collectors') x
ON CONFLICT (component_key, layer) DO UPDATE SET
       collector = EXCLUDED.collector, collector_version = EXCLUDED.collector_version, cost = EXCLUDED.cost,
       credential_type = EXCLUDED.credential_type, access_needed = EXCLUDED.access_needed,
       assess = EXCLUDED.assess, contains = EXCLUDED.contains, catalog_version = EXCLUDED.catalog_version,
       in_current_catalog = true, updated_at = now();

CREATE TEMP TABLE _lc_facts ON COMMIT DROP AS
SELECT x->>'instance_id' AS instance_id, x->>'target_id' AS target_id,
       x->>'component_key' AS component_key, (x->>'layer')::smallint AS layer,
       x->>'parent_kind' AS parent_kind, x->>'parent_id' AS parent_id,
       ARRAY(SELECT jsonb_array_elements_text(x->'reached_through')) AS reached_through,
       (x->>'depth')::int AS depth, x->>'status' AS status, COALESCE(x->>'reason', '') AS reason,
       x->>'collector' AS collector, x->>'collector_version' AS collector_version, x->>'cost' AS cost,
       x->>'credential_type' AS credential_type, x->>'catalog_version' AS catalog_version,
       (x->>'collected_at')::{_TS} AS collected_at, x->'facts' AS facts, (x->>'facts_bytes')::int AS facts_bytes,
       x->>'facts_sha256' AS facts_sha256, x->'notes' AS notes,
       (SELECT f.id FROM component_facts f
         WHERE (f.{_KEY.replace(', ', ', f.')}) = (x->>'target_id', x->>'component_key', (x->>'layer')::smallint,
                                                  x->>'parent_kind', x->>'parent_id')
         ORDER BY f.id DESC LIMIT 1) AS latest_id
  FROM _lc_payload, jsonb_array_elements(p->'facts') x;

-- Same outcome as the latest stored row: confirm it. Otherwise add a row.
UPDATE component_facts f
   SET last_confirmed_at = n.collected_at, reached_through = n.reached_through,
       last_run_id = currval(pg_get_serial_sequence('component_collection_runs', 'id'))
  FROM _lc_facts n
 WHERE f.id = n.latest_id AND f.status = n.status AND f.reason = n.reason
   AND f.facts_sha256 = n.facts_sha256 AND f.instance_id = n.instance_id AND f.notes = n.notes
   AND f.collector_version IS NOT DISTINCT FROM n.collector_version;

INSERT INTO component_facts (instance_id, {_KEY}, reached_through, depth, status, reason, collector, collector_version,
       cost, credential_type, catalog_version, collected_at, last_confirmed_at, facts, facts_bytes,
       facts_sha256, notes, first_run_id, last_run_id)
SELECT n.instance_id, n.target_id, n.component_key, n.layer, n.parent_kind, n.parent_id, n.reached_through, n.depth,
       n.status, n.reason, n.collector, n.collector_version, n.cost, n.credential_type, n.catalog_version,
       n.collected_at, n.collected_at, n.facts, n.facts_bytes, n.facts_sha256, n.notes,
       currval(pg_get_serial_sequence('component_collection_runs', 'id')),
       currval(pg_get_serial_sequence('component_collection_runs', 'id'))
  FROM _lc_facts n
 WHERE NOT EXISTS (SELECT 1 FROM component_facts f
                    WHERE f.id = n.latest_id AND f.status = n.status AND f.reason = n.reason
                      AND f.facts_sha256 = n.facts_sha256 AND f.instance_id = n.instance_id AND f.notes = n.notes
                      AND f.collector_version IS NOT DISTINCT FROM n.collector_version);

INSERT INTO component_children (parent_instance_id, parent_component_key, parent_layer, via_host, child_kind,
       child_value, child_name, detail, recognised_as, child_instance_id, disposition, depth, status,
       first_seen, last_seen, catalog_version, last_run_id)
SELECT x->>'parent_instance_id', x->>'parent_component_key', (x->>'parent_layer')::smallint, x->>'via_host',
       x->>'child_kind', x->>'child_value', x->>'child_name', x->'detail', x->>'recognised_as',
       x->>'child_instance_id', x->>'disposition', (x->>'depth')::int, 'present',
       (x->>'seen_at')::{_TS}, (x->>'seen_at')::{_TS}, x->>'catalog_version',
       currval(pg_get_serial_sequence('component_collection_runs', 'id'))
  FROM _lc_payload, jsonb_array_elements(p->'children') x
ON CONFLICT (parent_instance_id, parent_layer, via_host, child_kind, child_value, child_name) DO UPDATE SET
       detail = EXCLUDED.detail, recognised_as = EXCLUDED.recognised_as,
       child_instance_id = EXCLUDED.child_instance_id, disposition = EXCLUDED.disposition,
       depth = EXCLUDED.depth, status = 'present', last_seen = EXCLUDED.last_seen, not_seen_since = NULL,
       catalog_version = EXCLUDED.catalog_version, last_run_id = EXCLUDED.last_run_id;

-- A parent that was collected in this run and no longer reports a child: the
-- child is marked, never deleted.
UPDATE component_children ch
   SET status = 'not_seen', not_seen_since = (p->'run'->>'run_at')::{_TS}
  FROM _lc_payload, jsonb_array_elements(p->'collected_parents') x
 WHERE ch.parent_instance_id = x->>'instance_id' AND ch.parent_layer = (x->>'layer')::smallint
   AND ch.via_host = x->>'via_host' AND ch.status = 'present'
   AND ch.last_run_id IS DISTINCT FROM currval(pg_get_serial_sequence('component_collection_runs', 'id'));
COMMIT;
"""


def persist_sql(payload) -> str:
    blob = base64.b64encode(json.dumps(payload, sort_keys=True).encode("utf-8")).decode("ascii")
    return PERSIST_SQL.replace("__PAYLOAD__", blob)


# ── Launch guard ─────────────────────────────────────────────────────────────

def check_launch(pg_host, site_config_path, catalog_path, collectors_dir, root=PROJECT_ROOT) -> list[str]:
    """Reasons to refuse the run. The job holds the database credential and
    connects to managed hosts, so the database must be the site's own and the
    catalog and collectors must come from inside the project checkout."""
    problems = cd.check_launch(pg_host, site_config_path, {"catalog": catalog_path}, root=root)
    root = Path(root).resolve()
    cdir = Path(collectors_dir).resolve()
    if root != cdir and root not in cdir.parents:
        problems.append(f"collectors directory {str(collectors_dir)!r} is outside the project checkout")
    elif not cdir.is_dir():
        problems.append(f"collectors directory {str(collectors_dir)!r} does not exist")
    return problems


# ── CLI ──────────────────────────────────────────────────────────────────────

def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _dump(path, value):
    Path(path).write_text(json.dumps(value, indent=1, sort_keys=True), encoding="utf-8")


def dry_run(data, catalog, env=None) -> dict:
    """Selection only: what would run where, and what would be reported as not assessed.
    Nothing is collected, so nothing found inside a component is known: pass 1 only."""
    state = begin(data, catalog)
    would = select(state, 1, "host", env=env)["items"] + select(state, 1, "service", env=env)["items"]
    state["awaiting"] = {}
    return {"would_run": [{"host": i["target"]["host"] or ",".join(i["target"]["reached_through"]),
                           "component": i["target"]["component_key"], "layer": i["target"]["layer_number"],
                           "collector": i["file"], "cost": i["target"]["collector"]["cost"]} for i in would],
            "not_assessed": [{"host": ",".join(r["reached_through"]), "component": r["component_key"],
                              "layer": r["layer"], "reason": r["reason"]} for r in state["rows"]],
            "not_in_this_run": state["filtered"], "components_detected": len(state["detected"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, state=True):
        p.add_argument("--catalog", default=str(DEFAULT_CATALOG))
        p.add_argument("--collectors-dir", default=str(DEFAULT_COLLECTORS_DIR))
        if state:
            p.add_argument("--state", required=True)
        return p

    common(sub.add_parser("check-catalog"), state=False)
    g = common(sub.add_parser("check-launch"), state=False)
    g.add_argument("--pg-host", required=True)
    g.add_argument("--site-config", required=True)
    b = common(sub.add_parser("begin"))
    b.add_argument("--input", required=True)
    d = common(sub.add_parser("dry-run"), state=False)
    d.add_argument("--input", required=True)
    s = common(sub.add_parser("select"))
    s.add_argument("--pass", dest="pass_no", type=int, required=True)
    s.add_argument("--layer", choices=sorted(LAYER_NUMBER), required=True)
    s.add_argument("--out", required=True)
    r = common(sub.add_parser("record"))
    r.add_argument("--results", required=True)
    f = common(sub.add_parser("finish"))
    f.add_argument("--sql-out", required=True)
    f.add_argument("--summary-out", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "check-launch":
        problems = check_launch(args.pg_host, args.site_config, args.catalog, args.collectors_dir)
        for line in problems:
            print(line, file=sys.stderr)
        return 4 if problems else 0
    try:
        catalog = load_catalog(args.catalog, args.collectors_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        if args.cmd == "check-catalog":
            n = sum(1 for c in catalog["components"] for col in c.get("collectors") or []
                    if col["file"] != NO_COLLECTOR)
            print(f"catalog {catalog['catalog_version']}: {len(catalog['components'])} components, "
                  f"{n} collectors, valid")
        elif args.cmd == "dry-run":
            print(json.dumps(dry_run(_load(args.input), catalog), indent=1, sort_keys=True))
        elif args.cmd == "begin":
            _dump(args.state, begin(_load(args.input), catalog))
        elif args.cmd == "select":
            state = _load(args.state)
            out = select(state, args.pass_no, args.layer)
            _dump(args.state, state)
            _dump(args.out, for_ansible(out))
            print(f"pass {args.pass_no}, {args.layer} side: {len(out['items'])} collectors on "
                  f"{len(out['by_host'])} targets")
        elif args.cmd == "record":
            state = _load(args.state)
            counts = record(state, catalog, _load(args.results))
            _dump(args.state, state)
            print(json.dumps(counts, sort_keys=True))
        elif args.cmd == "finish":
            done = finish(_load(args.state), catalog)
            Path(args.sql_out).write_text(persist_sql(done["payload"]), encoding="utf-8")
            # The summary is printed and published by the playbook: display copy only.
            out = display_safe(dict(done["summary"]))
            out["text"] = format_summary(out)
            _dump(args.summary_out, out)
            print(out["text"])
    except (ValueError, RuntimeError, KeyError) as exc:
        print(f"layered collection stopped: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
