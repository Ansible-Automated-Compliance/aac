#!/usr/bin/env python3
"""
Grafana dashboard data-coverage checker.

For every dashboard in Grafana, pull each panel's rawSql, normalise the Grafana
macros/template-variables, and execute the query **as the same PostgreSQL role
the Grafana datasource uses** (default: `compliance`). A panel is "filled" if its
query returns >= 1 row (what Grafana needs to render instead of "No data").

This deliberately connects as the datasource role, not a superuser, so it also
catches missing GRANTs — the exact class of bug that silently blanked the
technical-debt heatmap (see docs / PR #342).

Config is read from the environment so it works unchanged inside an AAP EE:
  GRAFANA_URL   (required — the playbook passes it from site_config)
  GRAFANA_USER  (default admin)
  GRAFANA_PASSWORD
  PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD

Emits a single JSON object on stdout. Always exits 0 — the playbook decides
whether an empty/error panel is a failure.
"""
import base64
import json
import os
import re
import sys
import urllib.request

import psycopg2

def _require_env(name):
    """No hardcoded endpoint fallbacks — the playbook passes these from
    site_config. A missing value is a config error that should fail loudly."""
    value = os.environ.get(name)
    if not value:
        sys.exit(f"{name} must be set (passed by the playbook from site_config; no hardcoded default)")
    return value


GRAFANA_URL = _require_env("GRAFANA_URL").rstrip("/")
GRAFANA_USER = os.environ.get("GRAFANA_USER", "admin")
GRAFANA_PASSWORD = os.environ.get("GRAFANA_PASSWORD", "")


def grafana_get(path):
    req = urllib.request.Request(GRAFANA_URL + path)
    token = base64.b64encode(f"{GRAFANA_USER}:{GRAFANA_PASSWORD}".encode()).decode()
    req.add_header("Authorization", "Basic " + token)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def panels_of(dashboard):
    """Yield (panel_title, panel_type, rawSql) for every SQL target, incl. panels nested in rows."""
    out = []

    def walk(panels):
        for p in panels or []:
            for t in p.get("targets", []) or []:
                sql = t.get("rawSql")
                if sql:
                    out.append((p.get("title", "(untitled)"), p.get("type", "?"), sql))
            if p.get("panels"):
                walk(p["panels"])

    walk(dashboard.get("panels", []))
    return out


def sanitize(q):
    """Replace Grafana macros/template vars so the query runs standalone and time-unbounded."""
    q = q.strip().rstrip(";")
    q = re.sub(r"\$__timeFilter\s*\([^)]*\)", "TRUE", q, flags=re.I)
    q = re.sub(r"\$__unixEpochFilter\s*\([^)]*\)", "TRUE", q, flags=re.I)
    q = re.sub(r"\$__timeGroupAlias\s*\(\s*([^,]+)\s*,[^)]*\)", r"date_trunc('hour', \1) AS time", q, flags=re.I)
    q = re.sub(r"\$__timeGroup\s*\(\s*([^,]+)\s*,[^)]*\)", r"date_trunc('hour', \1)", q, flags=re.I)
    q = re.sub(r"\$__timeFrom\s*\(\s*\)", "'1970-01-01'::timestamptz", q, flags=re.I)
    q = re.sub(r"\$__timeTo\s*\(\s*\)", "now()", q, flags=re.I)
    q = re.sub(r"\$__interval\w*", "'1 hour'", q, flags=re.I)
    # col IN ($var)  ->  col IS NOT NULL   (multi-value template filter, unconstrained)
    q = re.sub(r"([\w\.]+)\s+IN\s*\(\s*'?\$\{?\w+(:\w+)?\}?'?\s*\)", r"\1 IS NOT NULL", q, flags=re.I)
    # col = '$var'   ->  col IS NOT NULL
    q = re.sub(r"([\w\.]+)\s*=\s*'?\$\{?\w+(:\w+)?\}?'?", r"\1 IS NOT NULL", q, flags=re.I)
    return q


def main():
    dashboards = grafana_get("/api/search?type=dash-db")

    conn = psycopg2.connect(
        host=_require_env("PGHOST"),
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ.get("PGDATABASE", "compliance"),
        user=os.environ.get("PGUSER", "compliance"),
        password=os.environ.get("PGPASSWORD", "compliance"),
        connect_timeout=15,
    )
    conn.autocommit = True

    results = []
    totals = {"panels": 0, "filled": 0, "empty": 0, "error": 0, "skipped": 0}

    for d in dashboards:
        full = grafana_get(f"/api/dashboards/uid/{d['uid']}")
        dash = full.get("dashboard", {})
        entry = {"uid": d["uid"], "title": d["title"],
                 "filled": 0, "empty": 0, "error": 0, "skipped": 0, "issues": []}

        for (ptitle, ptype, sql) in panels_of(dash):
            totals["panels"] += 1
            s = sanitize(sql)
            if "$" in s:  # a template var we could not resolve — report, don't crash
                entry["skipped"] += 1
                totals["skipped"] += 1
                entry["issues"].append({"panel": ptitle, "status": "skipped", "info": "unresolved variable"})
                continue
            cur = conn.cursor()
            try:
                cur.execute(f"SELECT count(*) FROM ( {s} ) _q")
                n = cur.fetchone()[0]
                if n > 0:
                    entry["filled"] += 1
                    totals["filled"] += 1
                else:
                    entry["empty"] += 1
                    totals["empty"] += 1
                    entry["issues"].append({"panel": ptitle, "status": "empty", "info": "0 rows"})
            except Exception as e:  # noqa: BLE001 — surface any DB error (perms, missing table, bad SQL)
                entry["error"] += 1
                totals["error"] += 1
                entry["issues"].append({"panel": ptitle, "status": "error", "info": str(e).splitlines()[0][:120]})
            finally:
                cur.close()

        entry["ok"] = entry["empty"] == 0 and entry["error"] == 0
        results.append(entry)

    conn.close()
    ok = totals["empty"] == 0 and totals["error"] == 0
    print(json.dumps({"ok": ok, "totals": totals, "dashboards": results}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
