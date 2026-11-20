#!/usr/bin/env python3
"""
component_discovery.py - which technology components run on which host.

Reads host facts that "AAC - Gather Facts" has ALREADY stored (host_facts_latest)
and matches them against the detection catalog
(ansible/vars/component_catalog.yml). It collects nothing from hosts.

The module is the single home of the detection logic:

  validate_catalog()        catalog schema checks
  detect_host()             signals -> components, plus "running, not recognised"
  reconcile()               this run against the stored map; never deletes
  validate_overrides()      operator overrides; who / why / expiry are required
  apply_overrides()         the effective map, with an override shown as an override
  build_plan()              all of the above -> summary + one SQL script

CLI (used by ansible/playbooks/discover_host_components.yml):

  component_discovery.py plan --input in.json --sql-out apply.sql --summary-out summary.json

Reference: docs/reference/COMPONENT_DISCOVERY.md
"""
from __future__ import annotations

import argparse
import base64
import fnmatch
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - the execution environment ships PyYAML
    yaml = None

DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "ansible" / "vars" / "component_catalog.yml"

SIGNAL_KINDS = ("package", "service", "process", "container_image", "port")
ROLES = ("server", "client", "supporting")
OVERRIDE_ACTIONS = ("exclude", "confirm", "reclassify")
CAPABILITIES = ("act", "map", "rank")
# Which part of the stored facts each signal kind is read from.
DOMAIN_OF = {"package": "packages", "service": "services", "process": "processes",
             "container_image": "containers", "port": "ports"}
COMM_LEN = 15  # the kernel keeps 15 characters of a command name

REASON_GONE = "signal_gone_in_newer_facts"
REASON_NO_NEWER = "no_newer_facts"
REASON_CATALOG = "catalog_changed"
REASON_RECOGNISED = "now_recognised"

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


# ── Catalog ──────────────────────────────────────────────────────────────────

def load_catalog(path=None) -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML is required to read the component catalog")
    with open(path or DEFAULT_CATALOG, encoding="utf-8") as fh:
        catalog = yaml.safe_load(fh) or {}
    errors = validate_catalog(catalog)
    if errors:
        raise ValueError("component catalog is not valid:\n  " + "\n  ".join(errors))
    return catalog


def validate_catalog(catalog) -> list[str]:
    """Return every schema fault in the catalog (an empty list means valid)."""
    errs: list[str] = []
    if not isinstance(catalog, dict):
        return ["catalog is not a mapping"]
    if not isinstance(catalog.get("catalog_version"), str) or not catalog["catalog_version"].strip():
        errs.append("catalog_version must be a non-empty string")
    kinds = catalog.get("kinds")
    if not isinstance(kinds, list) or not kinds:
        errs.append("kinds must be a non-empty list")
        kinds = []
    comps = catalog.get("components")
    if not isinstance(comps, list) or not comps:
        return errs + ["components must be a non-empty list"]
    seen = set()
    for i, c in enumerate(comps):
        where = f"components[{i}]"
        if not isinstance(c, dict):
            errs.append(f"{where}: not a mapping")
            continue
        key = c.get("key")
        where = f"component {key!r}"
        if not isinstance(key, str) or not _KEY_RE.match(key):
            errs.append(f"{where}: key must match [a-z][a-z0-9_]*")
        elif key in seen:
            errs.append(f"{where}: duplicate key")
        seen.add(key)
        if not isinstance(c.get("name"), str) or not c["name"].strip():
            errs.append(f"{where}: name is required")
        if c.get("kind") not in kinds:
            errs.append(f"{where}: kind {c.get('kind')!r} is not listed in kinds")
        if not isinstance(c.get("collector"), str) or not c["collector"].strip():
            errs.append(f"{where}: collector is required (use 'none yet')")
        lk = c.get("loader_keys")
        if not isinstance(lk, list) or any(not isinstance(k, str) for k in lk):
            errs.append(f"{where}: loader_keys must be a list of strings")
        priv = c.get("privileged")
        if not isinstance(priv, dict) or set(priv) != set(CAPABILITIES) \
                or any(not isinstance(v, bool) for v in priv.values()):
            errs.append(f"{where}: privileged must be {{act, map, rank}} with true/false values")
        sigs = c.get("signals")
        if not isinstance(sigs, list) or not sigs:
            errs.append(f"{where}: signals must be a non-empty list")
            continue
        can_identify = False
        for s in sigs:
            if not isinstance(s, dict) or set(s) - {"kind", "match", "role", "strength"}:
                errs.append(f"{where}: signal {s!r} has unknown fields")
                continue
            if s.get("kind") not in SIGNAL_KINDS:
                errs.append(f"{where}: signal kind {s.get('kind')!r} is not one of {SIGNAL_KINDS}")
                continue
            if s.get("match") in (None, "") or isinstance(s.get("match"), (dict, list, bool)):
                errs.append(f"{where}: signal {s!r} needs a match")
            if s["kind"] == "port" and not str(s.get("match", "")).isdigit():
                errs.append(f"{where}: port signal {s.get('match')!r} must be a number")
            if s.get("role", "server") not in ROLES:
                errs.append(f"{where}: signal role {s.get('role')!r} is not one of {ROLES}")
            if "strength" in s and (s["kind"] != "container_image" or s["strength"] != "strong"):
                errs.append(f"{where}: strength may only be 'strong', on a container_image signal")
            if s["kind"] != "port" and s.get("role", "server") == "server":
                can_identify = True
        if not can_identify:
            errs.append(f"{where}: no signal can identify it (ports, client and supporting signals cannot)")
    base = catalog.get("base_os")
    if not isinstance(base, dict) or not isinstance(base.get("service_units"), list) \
            or not isinstance(base.get("listeners"), list):
        errs.append("base_os must carry service_units and listeners lists")
    else:
        for b in base["listeners"]:
            # A bare process name is not accepted: it would allowlist that name on any socket.
            if not isinstance(b, dict) or set(b) - {"process", "proto", "port", "scope"} \
                    or not isinstance(b.get("process"), str) or not b["process"].strip() \
                    or b.get("proto") not in ("tcp", "udp") \
                    or isinstance(b.get("port"), bool) or not isinstance(b.get("port"), int) \
                    or b.get("scope", "any") not in ("any", "loopback"):
                errs.append(f"base_os listener {b!r}: needs process, proto (tcp/udp) and a numeric "
                            "port; scope may be 'loopback'")
    return errs


def catalog_rows(catalog) -> list[dict]:
    """The catalog as rows for the component_catalog table."""
    return [{
        "component_key": c["key"], "name": c["name"], "kind": c["kind"],
        "collector": c["collector"], "loader_keys": list(c["loader_keys"]),
        "can_act": c["privileged"]["act"], "can_map": c["privileged"]["map"],
        "can_rank": c["privileged"]["rank"],
    } for c in catalog["components"]]


# ── Reading the stored facts ─────────────────────────────────────────────────

def _match(pattern, value) -> bool:
    return fnmatch.fnmatchcase(str(value).lower(), str(pattern).lower())


def _match_comm(pattern, comm) -> bool:
    """Command names are truncated by the kernel; compare what it keeps."""
    return _match(pattern, comm) or _match(str(pattern)[:COMM_LEN], comm)


_PS_SKIP = re.compile(r"^(kworker|ksoftirqd|migration|cpuhp|idle_inject|rcu_|kthreadd|pool_workqueue)")
_SS_USERS = re.compile(r'\("([^"]+)",pid=')
_SS_PORT = re.compile(r":(\d+)$")


def parse_listeners(lines) -> list[dict]:
    """`ss -tlnpu` (or netstat) lines -> [{proto, port, bind, processes}]."""
    out = []
    for line in lines or []:
        parts = str(line).split()
        if len(parts) < 5 or parts[0].lower() not in ("tcp", "udp", "tcp6", "udp6"):
            continue
        proto = parts[0].lower().rstrip("6")
        # ss: Netid State Recv-Q Send-Q Local ... ; netstat: Proto Recv-Q Send-Q Local ...
        local = parts[4] if parts[1].isalpha() else parts[3]
        m = _SS_PORT.search(local)
        if not m:
            continue
        procs = sorted(set(_SS_USERS.findall(str(line))))
        if not procs and "/" in parts[-1] and parts[-1].split("/")[0].isdigit():
            procs = [parts[-1].split("/", 1)[1]]  # netstat "pid/name"
        out.append({"proto": proto, "port": int(m.group(1)),
                    "bind": local[: m.start()], "processes": procs})
    return out


def is_loopback(bind) -> bool:
    b = str(bind or "").strip().strip("[]").lower()
    return b.startswith("127.") or b == "::1" or b.endswith("%lo") or b == "localhost"


def base_listener(lsn, proc, base) -> bool:
    """True when this process on this socket is a base operating system listener.

    The process name alone is not enough: protocol and port must match too, and
    the bind address where the catalog states a scope.
    """
    for b in base.get("listeners", []):
        if (_match_comm(b["process"], proc) and b["proto"] == lsn["proto"] and int(b["port"]) == lsn["port"]
                and (b.get("scope", "any") != "loopback" or is_loopback(lsn["bind"]))):
            return True
    return False


def normalise_host(row) -> dict:
    """A host_facts_latest row (or its trimmed projection) -> what detection reads.

    `domains` lists the parts of the facts that were actually collected. A domain
    that is missing was not collected, which is different from "collected and
    empty of this component".
    """
    facts = row.get("facts") or {}
    if isinstance(facts, str):
        facts = json.loads(facts)
    domains = set()

    services = {}
    all_units = (facts.get("services") or {}).get("all")
    if isinstance(all_units, dict) and all_units:
        domains.add("services")
        for name, unit in all_units.items():
            unit = unit if isinstance(unit, dict) else {}
            if "." not in name:
                # A SysV init script is reported by its bare name ("ssh", "cron"),
                # often beside the systemd unit of the same service. Give it the
                # unit form, and let the systemd entry win when both exist.
                if f"{name}.service" in all_units:
                    continue
                name = f"{name}.service"
            services[name] = {"state": str(unit.get("state") or ""), "status": str(unit.get("status") or "")}
    enabled = {str(u) for u in ((facts.get("services") or {}).get("enabled_at_boot") or []) if u}

    installed = (facts.get("packages") or {}).get("installed")
    packages = set()
    if isinstance(installed, (dict, list)) and installed:
        domains.add("packages")
        packages = {str(p) for p in installed}

    listeners = []
    ports_raw = (facts.get("network") or {}).get("listening_ports")
    if isinstance(ports_raw, list) and ports_raw:
        domains.add("ports")
        listeners = parse_listeners(ports_raw)

    processes = set()
    ps_raw = (facts.get("processes") or {}).get("processes_raw")
    if isinstance(ps_raw, str) and ps_raw.strip():
        domains.add("processes")
        for line in ps_raw.splitlines():
            comm = line.split()[-1] if line.split() else ""
            if comm and not _PS_SKIP.match(comm):
                processes.add(comm)
    for lsn in listeners:  # a process that holds a listening socket is running
        processes.update(lsn["processes"])
    if listeners:
        domains.add("processes")

    images = []
    containers = facts.get("containers")
    if isinstance(containers, dict) and isinstance(containers.get("running"), list):
        domains.add("containers")
        for c in containers["running"]:
            image = c.get("image") if isinstance(c, dict) else c
            if image:
                images.append(str(image))

    return {
        "host_id": row.get("host_id"), "hostname": row.get("hostname") or row.get("host_id"),
        "facts_id": row.get("facts_id", row.get("id")),
        "collected_at": row.get("collected_at"),
        "services": services, "enabled": enabled, "packages": packages,
        "processes": processes, "listeners": listeners, "images": images,
        "domains": domains,
    }


# ── Detection ────────────────────────────────────────────────────────────────

def _signal_hits(sig, host) -> list[dict]:
    """Every fact on this host that one catalog signal matches."""
    kind, pattern, role = sig["kind"], sig["match"], sig.get("role", "server")
    hits = []

    def hit(value, detail, strength, hit_role=None, running=False, holders=()):
        hits.append({"kind": kind, "match": str(pattern), "value": value, "detail": detail,
                     "strength": strength, "role": hit_role or role, "running": running,
                     "holders": list(holders)})

    if kind == "package":
        for pkg in sorted(host["packages"]):
            if _match(pattern, pkg):
                hit(pkg, "installed", "strong")
    elif kind == "service":
        for name in sorted(host["services"]):
            if not _match(pattern, name):
                continue
            unit = host["services"][name]
            enabled = unit["status"] == "enabled" or name in host["enabled"]
            detail = f"{unit['state'] or 'unknown'}/{unit['status'] or 'unknown'}"
            if unit["state"] == "running":
                hit(name, detail, "strong", running=True)
            elif enabled:
                hit(name, detail, "strong")
            else:
                # The unit file exists but the service is neither running nor
                # enabled: it shows the software is present, nothing more.
                hit(name, detail, "weak", hit_role="client" if role == "client" else "supporting")
    elif kind == "process":
        for comm in sorted(host["processes"]):
            if _match_comm(pattern, comm):
                hit(comm, "running process", "medium", running=True)
    elif kind == "container_image":
        for image in sorted(set(host["images"])):
            if _match(pattern, image):
                hit(image, "running container", sig.get("strength", "medium"), running=True)
    elif kind == "port":
        for lsn in host["listeners"]:
            if lsn["port"] == int(pattern):
                procs = ",".join(lsn["processes"]) or "unknown process"
                hit(f"{lsn['proto']}/{lsn['port']}", f"listening ({procs})", "weak", hit_role="supporting",
                    holders=lsn["processes"])
    return hits


def _dedupe(hits) -> list[dict]:
    seen, out = set(), []
    for h in hits:
        k = (h["kind"], h["value"], h["role"])
        if k not in seen:
            seen.add(k)
            out.append(h)
    return out


def confidence_of(evidence) -> str | None:
    """high / medium from the kinds of signal that matched; None means no detection.

    Only server-role signals other than ports can identify a component. A
    running service or a strong container image is enough for `high`; so are
    two different kinds of identifying signal, and so is an identifying process
    that holds one of the component's own ports (the process name and the port
    are two separate facts). One identifying kind alone is `medium`. A port, a
    client tool or a bare unit file never yields a detection.
    """
    ident = [e for e in evidence if e["role"] == "server" and e["kind"] != "port"]
    if not ident:
        return None
    if any(e["strength"] == "strong" and e["running"] for e in ident):
        return "high"
    if len({e["kind"] for e in ident}) >= 2:
        return "high"
    named = {e["value"] for e in ident if e["kind"] == "process"}
    if any(e["kind"] == "port" and named & set(e.get("holders") or []) for e in evidence):
        return "high"
    return "medium"


def detect_host(host, catalog) -> dict:
    """Match one normalised host against the catalog.

    Returns {usable, detections, client_only, unrecognised}.
    """
    result = {"usable": bool(host["domains"]), "detections": [], "client_only": [], "unrecognised": []}
    if not host["domains"]:
        return result

    explained_units, explained_procs, explained_ports = set(), set(), set()
    port_hints: dict[int, list[str]] = {}
    for comp in catalog["components"]:
        evidence = _dedupe([h for sig in comp["signals"] for h in _signal_hits(sig, host)])
        if not evidence:
            continue
        confidence = confidence_of(evidence)
        if confidence is None:
            clients = [e for e in evidence if e["role"] == "client"]
            if clients:
                result["client_only"].append({"component_key": comp["key"], "evidence": _public(clients)})
            for e in evidence:
                if e["kind"] == "port":
                    port_hints.setdefault(int(e["value"].split("/")[1]), []).append(comp["key"])
            continue
        ident = [e for e in evidence if e["role"] == "server" and e["kind"] != "port"]
        result["detections"].append({
            "component_key": comp["key"],
            "confidence": confidence,
            "run_state": "running" if any(e["running"] for e in ident) else "installed",
            "signal_kinds": sorted({e["kind"] for e in ident}),
            "evidence": _public(evidence),
        })
        for e in evidence:
            if e["kind"] == "service":
                explained_units.add(e["value"])
            elif e["kind"] == "process":
                explained_procs.add(e["value"])
            elif e["kind"] == "port":
                explained_ports.add(int(e["value"].split("/")[1]))
        # Every unit and process the catalog names for a detected component is explained.
        for sig in comp["signals"]:
            if sig["kind"] == "service":
                explained_units.update(n for n in host["services"] if _match(sig["match"], n))
            elif sig["kind"] == "process":
                explained_procs.update(p for p in host["processes"] if _match_comm(sig["match"], p))

    base = catalog.get("base_os") or {}
    for name in sorted(host["services"]):
        if host["services"][name]["state"] != "running" or name in explained_units:
            continue
        if any(_match(p, name) for p in base.get("service_units", [])):
            continue
        result["unrecognised"].append({"item_kind": "service", "item": name,
                                       "detail": {"status": host["services"][name]["status"]}})
    seen = set()
    for lsn in host["listeners"]:
        procs = lsn["processes"]
        if procs:
            unexplained = [p for p in procs if p not in explained_procs
                           and not base_listener(lsn, p, base)]
            if not unexplained:
                continue
        elif lsn["port"] in explained_ports:
            continue
        else:
            unexplained = []
        item = f"{lsn['proto']}/{lsn['port']}"
        if item in seen:
            continue
        seen.add(item)
        detail = {"processes": unexplained, "bind": lsn["bind"]}
        if port_hints.get(lsn["port"]):
            # A port alone is weak: name the candidate, do not record a detection.
            detail["port_also_used_by"] = sorted(set(port_hints[lsn["port"]]))
        result["unrecognised"].append({"item_kind": "port", "item": item, "detail": detail})
    return result


def _public(evidence) -> list[dict]:
    return [{k: e[k] for k in ("kind", "match", "value", "detail", "strength", "role")} for e in evidence]


# ── Time helpers ─────────────────────────────────────────────────────────────

def parse_ts(value):
    """ISO text / date / datetime -> aware UTC datetime (None stays None)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    else:
        text = str(value).strip().replace("Z", "+00:00").replace(" ", "T", 1)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            text += "T00:00:00+00:00"
        # PostgreSQL prints 1 to 6 fractional digits and may shorten the offset
        # to "+00"; older Python versions only read the full forms.
        text = re.sub(r"\.(\d{1,6})", lambda m: "." + m.group(1).ljust(6, "0"), text, count=1)
        text = re.sub(r"([+-]\d{2})$", r"\1:00", text)
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt):
    return None if dt is None else parse_ts(dt).isoformat()


# ── Reconciling a run with the stored map (never deletes) ────────────────────

def _absence(existing, host, needed_domains):
    """Why a previously seen item did not match this run: (reason, detail, since).

    `since` is None when the run time should be used.
    """
    if host is None:
        return REASON_NO_NEWER, "host has no row in host_facts_latest", None
    seen_at = parse_ts(existing.get("facts_collected_at"))
    now_at = parse_ts(host.get("collected_at"))
    same_row = existing.get("facts_id") is not None and existing.get("facts_id") == host.get("facts_id")
    if same_row or (seen_at and now_at and now_at <= seen_at):
        return None, "", None  # same facts: the caller names the cause (catalog)
    missing = sorted(set(needed_domains) - set(host["domains"]))
    if missing:
        return (REASON_NO_NEWER,
                "the newer facts row did not collect: " + ", ".join(missing), None)
    return REASON_GONE, f"not present in facts row {host.get('facts_id')}", now_at


def reconcile(existing_rows, hosts, detections, catalog_version, now) -> tuple[list[dict], list[dict]]:
    """Merge this run's detections into the stored component map.

    existing_rows  rows of host_components
    hosts          {host_id: normalised host}
    detections     {host_id: [detection, ...]} for hosts that were evaluated
    Returns (rows to upsert, history events). A row is never removed: a
    component that stops appearing becomes `not_seen` with the reason.
    """
    now = parse_ts(now)
    existing = {(r["host_id"], r["component_key"]): r for r in existing_rows}
    rows, events = [], []

    def event(host_id, key, name, old, new, detail):
        events.append({"host_id": host_id, "component_key": key, "event": name,
                       "from_status": old, "to_status": new, "detail": detail})

    for host_id, found in detections.items():
        host = hosts[host_id]
        collected = parse_ts(host["collected_at"]) or now
        for det in found:
            key = det["component_key"]
            old = existing.pop((host_id, key), None)
            first = parse_ts(old.get("first_seen")) if old else None
            last = parse_ts(old.get("last_seen")) if old else None
            row = {
                "host_id": host_id, "hostname": host["hostname"], "component_key": key,
                "status": "detected", "run_state": det["run_state"], "confidence": det["confidence"],
                "signal_kinds": det["signal_kinds"], "evidence": det["evidence"],
                "catalog_version": catalog_version,
                "first_seen": iso(min(first, collected) if first else collected),
                "last_seen": iso(max(last, collected) if last else collected),
                "facts_id": host["facts_id"], "facts_collected_at": iso(collected),
                "not_seen_since": None, "not_seen_reason": None, "not_seen_detail": None,
            }
            rows.append(row)
            if old is None:
                event(host_id, key, "first_detected", None, "detected",
                      {"confidence": det["confidence"], "run_state": det["run_state"]})
            elif old.get("status") != "detected":
                event(host_id, key, "detected_again", old.get("status"), "detected",
                      {"was_not_seen_since": iso(old.get("not_seen_since")),
                       "was_reason": old.get("not_seen_reason")})
            elif (old.get("confidence"), old.get("run_state")) != (det["confidence"], det["run_state"]):
                event(host_id, key, "confidence_changed", "detected", "detected",
                      {"from": [old.get("confidence"), old.get("run_state")],
                       "to": [det["confidence"], det["run_state"]]})

    # Whatever is left in `existing` did not match this run.
    for (host_id, key), old in sorted(existing.items()):
        host = hosts.get(host_id)
        needed = [DOMAIN_OF[k] for k in (old.get("signal_kinds") or []) if k in DOMAIN_OF]
        reason, detail, since = _absence(old, host, needed)
        if reason is None:
            reason, since = REASON_CATALOG, None
            detail = (f"same facts row; catalog {old.get('catalog_version')} matched, "
                      f"catalog {catalog_version} does not")
        if old.get("status") == "not_seen":
            # Already recorded. Only a firmer answer changes it: newer, complete
            # facts that still do not show the component.
            if reason != REASON_GONE or old.get("not_seen_reason") == REASON_GONE:
                continue
        row = dict(old)
        row.update({
            "status": "not_seen",
            "not_seen_since": iso(since or now), "not_seen_reason": reason, "not_seen_detail": detail,
            "first_seen": iso(old.get("first_seen")), "last_seen": iso(old.get("last_seen")),
            "facts_collected_at": iso(old.get("facts_collected_at")),
            "signal_kinds": old.get("signal_kinds") or [], "evidence": old.get("evidence") or [],
        })
        rows.append(row)
        event(host_id, key, "not_seen", old.get("status"), "not_seen",
              {"reason": reason, "detail": detail, "last_seen": iso(old.get("last_seen"))})
    return rows, events


def reconcile_unrecognised(existing_rows, hosts, found, now) -> list[dict]:
    """Same rule for "running, not recognised": mark not seen, never delete."""
    now = parse_ts(now)
    existing = {(r["host_id"], r["item_kind"], r["item"]): r for r in existing_rows}
    rows = []
    for host_id, items in found.items():
        host = hosts[host_id]
        collected = parse_ts(host["collected_at"]) or now
        for it in items:
            old = existing.pop((host_id, it["item_kind"], it["item"]), None)
            first = parse_ts(old.get("first_seen")) if old else None
            last = parse_ts(old.get("last_seen")) if old else None
            rows.append({
                "host_id": host_id, "hostname": host["hostname"],
                "item_kind": it["item_kind"], "item": it["item"], "detail": it["detail"],
                "status": "present",
                "first_seen": iso(min(first, collected) if first else collected),
                "last_seen": iso(max(last, collected) if last else collected),
                "facts_id": host["facts_id"], "facts_collected_at": iso(collected),
                "not_seen_since": None, "not_seen_reason": None,
            })
    for (host_id, kind, item), old in sorted(existing.items()):
        host = hosts.get(host_id)
        reason, _detail, since = _absence(old, host, ["services" if kind == "service" else "ports"])
        if reason is None:
            reason = REASON_RECOGNISED  # same facts, and the catalog now explains it
        elif reason == REASON_GONE and host is not None and _still_running(host, kind, item):
            reason = REASON_RECOGNISED
        if old.get("status") == "not_seen" and (
                reason == REASON_NO_NEWER or old.get("not_seen_reason") == reason):
            continue
        row = dict(old)
        row.update({"status": "not_seen", "not_seen_since": iso(since or now), "not_seen_reason": reason,
                    "first_seen": iso(old.get("first_seen")), "last_seen": iso(old.get("last_seen")),
                    "facts_collected_at": iso(old.get("facts_collected_at")),
                    "detail": old.get("detail") or {}})
        rows.append(row)
    return rows


def _still_running(host, kind, item) -> bool:
    if kind == "service":
        return host["services"].get(item, {}).get("state") == "running"
    return any(f"{lsn['proto']}/{lsn['port']}" == item for lsn in host["listeners"])


# ── Operator overrides ───────────────────────────────────────────────────────

DEFAULT_MAX_EXPIRY_DAYS = 90


def is_privileged(comp) -> bool:
    return any((comp.get("privileged") or {}).get(c) for c in CAPABILITIES)


def validate_overrides(entries, catalog, now=None, max_expiry_days=DEFAULT_MAX_EXPIRY_DAYS,
                       recorded_by="", source="file") -> tuple[list[dict], list[str]]:
    """Return (accepted overrides, refusals).

    An entry is refused unless it names host, component, a known action, who
    asked for it, why, and an expiry date no further away than
    `max_expiry_days`. Hiding or renaming a component the catalog marks as
    privileged (exclude / reclassify) also needs an `approver` who is not the
    requester. Nothing is applied from a refused entry; the playbook stops
    before it writes anything.

    `who` is what the entry declares. `recorded_by` is the account that
    launched the job and `source` is where the list came from; both are stored
    beside the declared requester and are not taken from the entry.
    """
    keys = {c["key"] for c in catalog["components"]}
    by_key = {c["key"]: c for c in catalog["components"]}
    now = parse_ts(now) or datetime.now(timezone.utc)
    max_expiry_days = int(max_expiry_days)
    good, errs = [], []
    if entries in (None, ""):
        return good, errs
    if not isinstance(entries, list):
        return good, ["component_override_entries must be a list"]
    for i, e in enumerate(entries):
        where = f"override[{i}]"
        if not isinstance(e, dict):
            errs.append(f"{where}: not a mapping")
            continue
        problems = []
        vals = {k: str(e.get(k) if e.get(k) is not None else "").strip()
                for k in ("host", "component", "action", "who", "why", "expires", "reclassify_to", "approver")}
        where = f"override[{i}] ({vals['host'] or '?'} / {vals['component'] or '?'})"
        for field in ("host", "component", "action", "who", "why", "expires"):
            if not vals[field]:
                problems.append(f"{field} is required")
        if vals["action"] and vals["action"] not in OVERRIDE_ACTIONS:
            problems.append(f"action must be one of {', '.join(OVERRIDE_ACTIONS)}")
        if vals["component"] and vals["component"] not in keys:
            problems.append(f"component {vals['component']!r} is not in the catalog")
        expires = None
        if vals["expires"]:
            try:
                expires = parse_ts(vals["expires"])
            except ValueError:
                problems.append(f"expires {vals['expires']!r} is not a date (YYYY-MM-DD)")
        if expires and expires > now + timedelta(days=max_expiry_days):
            problems.append(f"expires {vals['expires']} is more than {max_expiry_days} days away "
                            "(the longest an override may run)")
        if vals["action"] in ("exclude", "reclassify") and is_privileged(by_key.get(vals["component"], {})):
            if not vals["approver"]:
                problems.append(f"{vals['action']} of a privileged component needs an approver")
            elif vals["approver"].casefold() == vals["who"].casefold():
                problems.append("the approver must be a different person from who asked")
        if vals["action"] == "reclassify":
            if vals["reclassify_to"] not in keys:
                problems.append("reclassify needs reclassify_to, a component key in the catalog")
            elif vals["reclassify_to"] == vals["component"]:
                problems.append("reclassify_to is the same component")
        elif vals["reclassify_to"]:
            problems.append("reclassify_to is only valid with action reclassify")
        if problems:
            errs.append(f"{where}: " + "; ".join(problems))
            continue
        good.append({"host": vals["host"], "component_key": vals["component"], "action": vals["action"],
                     "reclassify_to": vals["reclassify_to"], "requested_by": vals["who"],
                     "reason": vals["why"], "expires_at": iso(expires),
                     "approved_by": vals["approver"], "recorded_by": str(recorded_by or "").strip(),
                     "source": str(source or "file"),
                     "privileged": is_privileged(by_key[vals["component"]])})
    return good, errs


def overrides_in_force(overrides, now) -> list[dict]:
    """An override past its expiry stops applying by itself."""
    now = parse_ts(now)
    return [o for o in overrides if parse_ts(o["expires_at"]) > now]


def apply_overrides(rows, overrides, now) -> list[dict]:
    """The effective map: every stored row, plus what the overrides in force change.

    The detection columns are left as detection wrote them. An override is
    reported in `basis` and `override`, never as a detection.
    """
    live = overrides_in_force(overrides, now)
    out, used = [], set()
    for r in rows:
        eff = dict(r)
        eff.update({"effective_component": r["component_key"], "effective_status": r["status"],
                    "basis": "detection", "override": None})
        for n, o in enumerate(live):
            if o["component_key"] != r["component_key"] or o["host"] not in (r["host_id"], r.get("hostname")):
                continue
            used.add(n)
            eff["override"] = o
            eff["basis"] = "override"
            if o["action"] == "exclude":
                eff["effective_status"] = "excluded"
            elif o["action"] == "confirm":
                eff["effective_status"] = "confirmed"
            elif o["action"] == "reclassify":
                eff["effective_component"] = o["reclassify_to"]
        out.append(eff)
    for n, o in enumerate(live):
        if n in used or o["action"] != "confirm":
            continue
        # Confirmed by an operator on a host where detection found nothing.
        out.append({"host_id": o["host"], "hostname": o["host"], "component_key": o["component_key"],
                    "status": "not_detected", "confidence": None, "run_state": None, "evidence": [],
                    "effective_component": o["component_key"], "effective_status": "confirmed",
                    "basis": "override", "override": o})
    return out


# ── Plan: summary + SQL ──────────────────────────────────────────────────────

def build_plan(data, catalog=None) -> dict:
    """Everything one run decides, from one input document.

    data: {now, stale_after_days, expiring_within_days, job_id, facts_rows: [rows
    of the trimmed host_facts_latest projection], existing_components,
    existing_unrecognised, overrides: [entries as written by the operator]}
    """
    catalog = catalog or load_catalog()
    now = parse_ts(data.get("now")) or datetime.now(timezone.utc)
    stale_days = int(data.get("stale_after_days", 7))
    soon_days = int(data.get("expiring_within_days", 14))
    version = catalog["catalog_version"]
    by_key = {c["key"]: c for c in catalog["components"]}

    overrides, refusals = validate_overrides(
        data.get("overrides"), catalog, now=now,
        max_expiry_days=data.get("override_max_expiry_days", DEFAULT_MAX_EXPIRY_DAYS),
        recorded_by=data.get("launched_by", ""), source=data.get("override_source", "file"))
    if refusals:
        return {"ok": False, "override_errors": refusals, "summary": {}, "payload": None}

    hosts, detections, unrec, client_only, unusable = {}, {}, {}, [], []
    for row in data.get("facts_rows") or data.get("hosts") or []:
        host = normalise_host(row)
        hosts[host["host_id"]] = host
        found = detect_host(host, catalog)
        if not found["usable"]:
            unusable.append(host["hostname"])
            continue
        detections[host["host_id"]] = found["detections"]
        unrec[host["host_id"]] = found["unrecognised"]
        for c in found["client_only"]:
            client_only.append({"host": host["hostname"], "component": c["component_key"],
                                "tools": sorted({e["value"] for e in c["evidence"]})})

    rows, events = reconcile(data.get("existing_components") or [], hosts, detections, version, now)
    unrec_rows = reconcile_unrecognised(data.get("existing_unrecognised") or [], hosts, unrec, now)

    # The full map after this run = rows written now + stored rows left untouched.
    touched = {(r["host_id"], r["component_key"]) for r in rows}
    full = rows + [r for r in (data.get("existing_components") or [])
                   if (r["host_id"], r["component_key"]) not in touched]
    effective = apply_overrides(full, overrides, now)
    stale_before = now - timedelta(days=stale_days)

    per_host: dict[str, list] = {}
    no_collector, privileged, stale, not_seen = [], [], [], []
    for e in sorted(effective, key=lambda r: (str(r.get("hostname")), r["effective_component"])):
        name = e.get("hostname") or e["host_id"]
        # No newer usable facts is not a removal: the component stays listed, unverified.
        unverified = e["status"] == "not_seen" and e.get("not_seen_reason") == REASON_NO_NEWER
        if e["status"] == "not_seen" and not unverified:
            not_seen.append({"host": name, "component": e["component_key"],
                             "not_seen_since": e.get("not_seen_since"), "reason": e.get("not_seen_reason")})
        current = (e["effective_status"] == "confirmed"
                   or (e["effective_status"] != "excluded" and (e["status"] == "detected" or unverified)))
        if not current:
            continue
        comp = by_key.get(e["effective_component"], {})
        collected = parse_ts(e.get("facts_collected_at"))
        is_stale = bool(unverified or (e["status"] == "detected" and collected and collected < stale_before))
        per_host.setdefault(name, []).append({
            "component": e["effective_component"], "confidence": e.get("confidence"),
            "run_state": e.get("run_state"), "basis": e["basis"],
            "override": e["override"]["action"] if e["override"] else None,
            "facts_collected_at": e.get("facts_collected_at"),
            "freshness": "no newer facts" if is_stale else "current"})
        if is_stale:
            stale.append({"host": name, "component": e["effective_component"],
                          "no_newer_facts_since": e.get("facts_collected_at")})
        if comp.get("collector", "none yet") == "none yet":
            no_collector.append({"host": name, "component": e["effective_component"]})
        caps = [c for c in CAPABILITIES if (comp.get("privileged") or {}).get(c)]
        if caps:
            privileged.append({"host": name, "component": e["effective_component"], "capabilities": caps})

    unrec_counts: dict[str, dict] = {}
    for r in unrec_rows:
        if r["status"] == "present":
            c = unrec_counts.setdefault(r["hostname"], {"service": 0, "port": 0})
            c[r["item_kind"]] += 1
    live = overrides_in_force(overrides, now)
    soon = [o for o in live if parse_ts(o["expires_at"]) <= now + timedelta(days=soon_days)]

    def brief(o):
        return {"host": o["host"], "component": o["component_key"], "action": o["action"],
                "who": o["requested_by"], "approver": o["approved_by"] or None,
                "recorded_by": o["recorded_by"] or None, "source": o["source"],
                "privileged_component": o["privileged"], "expires": o["expires_at"][:10]}

    summary = {
        "catalog_version": version, "catalog_components": len(by_key),
        "run_at": iso(now), "stale_after_days": stale_days,
        "hosts_in_facts": len(hosts), "hosts_evaluated": len(detections),
        "hosts_without_usable_facts": sorted(unusable),
        "hosts_with_components": len(per_host),
        "components_current": sum(len(v) for v in per_host.values()),
        "components_per_host": per_host,
        "detected_no_collector_count": len(no_collector), "detected_no_collector": no_collector,
        "privileged_services": privileged,
        "unrecognised_count": sum(c["service"] + c["port"] for c in unrec_counts.values()),
        "unrecognised_per_host": unrec_counts,
        "stale_count": len(stale), "stale": stale,
        "not_seen_count": len(not_seen), "not_seen": not_seen,
        "client_tools_only": client_only,
        "overrides_in_force": [brief(o) for o in live],
        "overrides_expiring_soon": [brief(o) for o in soon],
        "overrides_expired": [brief(o) for o in overrides if o not in live],
        "overrides_on_privileged_components": [brief(o) for o in live if o["privileged"]],
        "history_events": len(events),
    }
    payload = {
        "run": {"catalog_version": version, "stale_after_days": stale_days, "job_id": data.get("job_id"),
                "run_at": iso(now), "hosts_evaluated": len(detections),
                "summary": {k: v for k, v in summary.items() if k != "components_per_host"}},
        "catalog": catalog_rows(catalog), "components": rows, "history": events,
        "unrecognised": unrec_rows, "overrides": overrides,
    }
    return {"ok": True, "override_errors": [], "summary": summary, "payload": payload}


# ── SQL ──────────────────────────────────────────────────────────────────────
# One script, one transaction. The run's data travels as a single base64 value
# (base64 has no quote characters, so nothing in the facts can alter the SQL).
# The script only inserts and updates; it contains no DELETE, TRUNCATE or DROP
# of a product table.

_TS = "TIMESTAMPTZ"
PERSIST_SQL = f"""\
BEGIN;
CREATE TEMP TABLE _cd_payload ON COMMIT DROP AS
  SELECT convert_from(decode('__PAYLOAD__', 'base64'), 'UTF8')::jsonb AS p;

INSERT INTO component_discovery_runs (run_at, catalog_version, stale_after_days, hosts_evaluated, job_id, summary)
SELECT (p->'run'->>'run_at')::{_TS}, p->'run'->>'catalog_version', (p->'run'->>'stale_after_days')::int,
       (p->'run'->>'hosts_evaluated')::int, NULLIF(p->'run'->>'job_id', '')::bigint, p->'run'->'summary'
  FROM _cd_payload;

UPDATE component_catalog SET in_current_catalog = false, updated_at = now()
 WHERE in_current_catalog
   AND component_key NOT IN (SELECT x->>'component_key' FROM _cd_payload, jsonb_array_elements(p->'catalog') x);

INSERT INTO component_catalog (component_key, name, kind, collector, loader_keys,
                               can_act, can_map, can_rank, catalog_version, in_current_catalog, updated_at)
SELECT x->>'component_key', x->>'name', x->>'kind', x->>'collector',
       ARRAY(SELECT jsonb_array_elements_text(x->'loader_keys')),
       (x->>'can_act')::boolean, (x->>'can_map')::boolean, (x->>'can_rank')::boolean,
       p->'run'->>'catalog_version', true, now()
  FROM _cd_payload, jsonb_array_elements(p->'catalog') x
ON CONFLICT (component_key) DO UPDATE SET
       name = EXCLUDED.name, kind = EXCLUDED.kind, collector = EXCLUDED.collector,
       loader_keys = EXCLUDED.loader_keys, can_act = EXCLUDED.can_act, can_map = EXCLUDED.can_map,
       can_rank = EXCLUDED.can_rank, catalog_version = EXCLUDED.catalog_version,
       in_current_catalog = true, updated_at = now();

INSERT INTO host_components (host_id, hostname, component_key, status, run_state, confidence,
       signal_kinds, evidence, catalog_version, first_seen, last_seen, facts_id, facts_collected_at,
       not_seen_since, not_seen_reason, not_seen_detail, last_run_id, updated_at)
SELECT x->>'host_id', x->>'hostname', x->>'component_key', x->>'status', x->>'run_state', x->>'confidence',
       ARRAY(SELECT jsonb_array_elements_text(x->'signal_kinds')), x->'evidence', x->>'catalog_version',
       (x->>'first_seen')::{_TS}, (x->>'last_seen')::{_TS}, (x->>'facts_id')::bigint,
       (x->>'facts_collected_at')::{_TS}, (x->>'not_seen_since')::{_TS},
       x->>'not_seen_reason', x->>'not_seen_detail',
       currval(pg_get_serial_sequence('component_discovery_runs', 'id')), now()
  FROM _cd_payload, jsonb_array_elements(p->'components') x
ON CONFLICT (host_id, component_key) DO UPDATE SET
       hostname = EXCLUDED.hostname, status = EXCLUDED.status, run_state = EXCLUDED.run_state,
       confidence = EXCLUDED.confidence, signal_kinds = EXCLUDED.signal_kinds, evidence = EXCLUDED.evidence,
       catalog_version = EXCLUDED.catalog_version, first_seen = EXCLUDED.first_seen,
       last_seen = EXCLUDED.last_seen, facts_id = EXCLUDED.facts_id,
       facts_collected_at = EXCLUDED.facts_collected_at, not_seen_since = EXCLUDED.not_seen_since,
       not_seen_reason = EXCLUDED.not_seen_reason, not_seen_detail = EXCLUDED.not_seen_detail,
       last_run_id = EXCLUDED.last_run_id, updated_at = now();

INSERT INTO host_component_history (host_id, component_key, event, from_status, to_status, detail, run_id)
SELECT x->>'host_id', x->>'component_key', x->>'event', x->>'from_status', x->>'to_status', x->'detail',
       currval(pg_get_serial_sequence('component_discovery_runs', 'id'))
  FROM _cd_payload, jsonb_array_elements(p->'history') x;

INSERT INTO host_unrecognised (host_id, hostname, item_kind, item, detail, status, first_seen, last_seen,
       facts_id, facts_collected_at, not_seen_since, not_seen_reason, last_run_id, updated_at)
SELECT x->>'host_id', x->>'hostname', x->>'item_kind', x->>'item', x->'detail', x->>'status',
       (x->>'first_seen')::{_TS}, (x->>'last_seen')::{_TS}, (x->>'facts_id')::bigint,
       (x->>'facts_collected_at')::{_TS}, (x->>'not_seen_since')::{_TS}, x->>'not_seen_reason',
       currval(pg_get_serial_sequence('component_discovery_runs', 'id')), now()
  FROM _cd_payload, jsonb_array_elements(p->'unrecognised') x
ON CONFLICT (host_id, item_kind, item) DO UPDATE SET
       hostname = EXCLUDED.hostname, detail = EXCLUDED.detail, status = EXCLUDED.status,
       first_seen = EXCLUDED.first_seen, last_seen = EXCLUDED.last_seen, facts_id = EXCLUDED.facts_id,
       facts_collected_at = EXCLUDED.facts_collected_at, not_seen_since = EXCLUDED.not_seen_since,
       not_seen_reason = EXCLUDED.not_seen_reason, last_run_id = EXCLUDED.last_run_id, updated_at = now();

INSERT INTO component_overrides (host, component_key, action, reclassify_to, requested_by, reason,
       expires_at, approved_by, recorded_by, source)
SELECT x->>'host', x->>'component_key', x->>'action', COALESCE(x->>'reclassify_to', ''),
       x->>'requested_by', x->>'reason', (x->>'expires_at')::{_TS},
       NULLIF(x->>'approved_by', ''), NULLIF(x->>'recorded_by', ''), COALESCE(x->>'source', 'file')
  FROM _cd_payload, jsonb_array_elements(p->'overrides') x
-- recorded_by and source keep the values of the run that first recorded the entry.
ON CONFLICT (host, component_key, action, reclassify_to, requested_by, expires_at) DO UPDATE SET
       reason = EXCLUDED.reason, approved_by = EXCLUDED.approved_by, withdrawn_at = NULL;

UPDATE component_overrides o SET withdrawn_at = now()
 WHERE o.withdrawn_at IS NULL
   AND NOT EXISTS (
       SELECT 1 FROM _cd_payload, jsonb_array_elements(p->'overrides') x
        WHERE x->>'host' = o.host AND x->>'component_key' = o.component_key AND x->>'action' = o.action
          AND COALESCE(x->>'reclassify_to', '') = o.reclassify_to AND x->>'requested_by' = o.requested_by
          AND (x->>'expires_at')::{_TS} = o.expires_at);
COMMIT;
"""

def persist_sql(payload) -> str:
    blob = base64.b64encode(json.dumps(payload, sort_keys=True).encode("utf-8")).decode("ascii")
    return PERSIST_SQL.replace("__PAYLOAD__", blob)


def format_summary(summary) -> str:
    """The run summary as plain text for the job output."""
    s = summary
    lines = [
        "Component discovery",
        f"  catalog version            {s['catalog_version']} ({s['catalog_components']} components)",
        f"  hosts in stored facts      {s['hosts_in_facts']}",
        f"  hosts evaluated            {s['hosts_evaluated']}",
        f"  hosts without usable facts {len(s['hosts_without_usable_facts'])}",
        f"  hosts with components      {s['hosts_with_components']}",
        f"  components (current)       {s['components_current']}",
        f"  detected, no collector     {s['detected_no_collector_count']}",
        f"  running, not recognised    {s['unrecognised_count']}",
        f"  no newer facts (> {s['stale_after_days']} d)    {s['stale_count']}",
        f"  no longer present          {s['not_seen_count']}",
        f"  overrides in force         {len(s['overrides_in_force'])}",
        f"  overrides expiring soon    {len(s['overrides_expiring_soon'])}",
        "", "Components per host",
    ]
    for host in sorted(s["components_per_host"]):
        lines.append(f"  {host}")
        for c in s["components_per_host"][host]:
            how = f"override: {c['override']}" if c["basis"] == "override" else "detection"
            lines.append(f"    {c['component']:<28} {c['confidence'] or '-':<7} {c['run_state'] or '-':<10}"
                         f" {how:<22} {c['freshness']}")
    if s["not_seen"]:
        lines += ["", "No longer present"]
        lines += [f"  {n['host']}: {n['component']} since {str(n['not_seen_since'])[:10]} ({n['reason']})"
                  for n in s["not_seen"]]
    if s["unrecognised_per_host"]:
        lines += ["", "Running, not recognised (services / ports)"]
        lines += [f"  {h}: {c['service']} / {c['port']}" for h, c in sorted(s["unrecognised_per_host"].items())]
    if s["client_tools_only"]:
        lines += ["", "Client tools only (not reported as the server component)"]
        lines += [f"  {c['host']}: {', '.join(c['tools'])} (not {c['component']})" for c in s["client_tools_only"]]
    for title, key in (("Overrides in force", "overrides_in_force"),
                       ("Overrides expiring soon", "overrides_expiring_soon")):
        if s[key]:
            lines += ["", title]
            lines += [f"  {o['host']}: {o['action']} {o['component']} asked by {o['who']}"
                      + (f", approved by {o['approver']}" if o["approver"] else "")
                      + (f", recorded by {o['recorded_by']}" if o["recorded_by"] else "")
                      + f" ({o['source']}), expires {o['expires']}"
                      + (" [privileged component]" if o["privileged_component"] else "")
                      for o in s[key]]
    return "\n".join(lines)


# ── Launch guard ─────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REF_RE = re.compile(r"^\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}$")


def configured_db_host(site_config_path):
    """The database host the site configuration names, or (None, why).

    Read straight from the file, so a variable supplied at launch cannot change
    the answer. `pg_host: "{{ aac_host }}"` is followed inside the same file.
    """
    path = Path(site_config_path)
    if not path.is_file():
        return None, f"{path.name} does not exist in the project checkout"
    try:
        site = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return None, f"{path.name} could not be read: {exc}"
    value = site.get("pg_host") if isinstance(site, dict) else None
    for _ in range(5):
        m = _REF_RE.match(str(value or "").strip())
        if not m:
            break
        value = site.get(m.group(1))
    value = str(value or "").strip()
    if not value:
        return None, f"{path.name} sets no pg_host"
    if "{{" in value:
        return None, f"pg_host in {path.name} is an expression that cannot be checked: {value}"
    return value, ""


def check_launch(pg_host, site_config_path, paths, root=PROJECT_ROOT) -> list[str]:
    """Reasons to refuse the run (an empty list means go).

    The job holds the database credential, so it only connects to the database
    host the site configuration names, and it only reads its catalog and
    override files from inside the project checkout.
    """
    problems = []
    expected, why = configured_db_host(site_config_path)
    if expected is None:
        problems.append(f"the database host cannot be verified: {why}")
    elif str(pg_host or "").strip().casefold() != expected.casefold():
        problems.append(f"database host {str(pg_host)!r} is not the configured site value "
                        f"(pg_host in {Path(site_config_path).name})")
    root = Path(root).resolve()
    for label, raw in paths.items():
        resolved = Path(raw).resolve()
        if root != resolved and root not in resolved.parents:
            problems.append(f"{label} file {str(raw)!r} is outside the project checkout")
        elif not resolved.is_file():
            problems.append(f"{label} file {str(raw)!r} does not exist")
    return problems


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    plan = sub.add_parser("plan", help="detect, reconcile and write the SQL that stores the result")
    plan.add_argument("--input", required=True, help="JSON document (see build_plan)")
    plan.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    plan.add_argument("--sql-out", required=True)
    plan.add_argument("--summary-out", required=True)
    check = sub.add_parser("check-catalog", help="validate the catalog file")
    check.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    guard = sub.add_parser("check-launch", help="refuse a run aimed at another database or at outside files")
    guard.add_argument("--pg-host", required=True)
    guard.add_argument("--site-config", required=True)
    guard.add_argument("--catalog", required=True)
    guard.add_argument("--overrides", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "check-launch":
        problems = check_launch(args.pg_host, args.site_config,
                                {"catalog": args.catalog, "overrides": args.overrides})
        for line in problems:
            print(line, file=sys.stderr)
        return 4 if problems else 0

    try:
        catalog = load_catalog(args.catalog)
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.cmd == "check-catalog":
        print(f"catalog {catalog['catalog_version']}: {len(catalog['components'])} components, valid")
        return 0

    with open(args.input, encoding="utf-8") as fh:
        data = json.load(fh)
    result = build_plan(data, catalog)
    if not result["ok"]:
        print("Refused operator overrides (nothing was written):", file=sys.stderr)
        for e in result["override_errors"]:
            print(f"  {e}", file=sys.stderr)
        return 3
    Path(args.sql_out).write_text(persist_sql(result["payload"]), encoding="utf-8")
    out = dict(result["summary"])
    out["text"] = format_summary(result["summary"])
    Path(args.summary_out).write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print(out["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
