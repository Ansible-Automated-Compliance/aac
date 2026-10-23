#!/usr/bin/env python3
"""Snapshot GitHub traffic data for the AAC repos into a data directory.

GitHub's traffic API (views/clones/referrers/paths) only retains 14 days,
so this runs daily (see .github/workflows/traffic-snapshot.yml) and
accumulates a permanent history on the `traffic-data` branch. The blog
cadence is weekly (Fridays), so the rolling CSVs are what show each
post's lift over time.

Layout, per repo, under --data-dir:

    traffic/<repo>/snapshots/<YYYY-MM-DD>.json   raw API responses (audit trail)
    traffic/<repo>/views.csv                     date,views,unique_visitors
    traffic/<repo>/clones.csv                    date,clones,unique_cloners
    traffic/<repo>/stars.csv                     date,stars,forks,watchers

CSV rows are upserted by date: GitHub revises the most recent days, so a
later snapshot's value for an already-recorded date replaces the old row.
Referrers/paths have no timestamps (rolling 14-day totals) and are kept
only in the dated JSON snapshots.

Token: env GITHUB_TOKEN (or TRAFFIC_PAT) — needs push access to each
repo, which is what the traffic API requires for read.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

OWNER = "ynotbhatc"
REPOS = ["rego_policy_libraries", "compliance", "AAC_Customer_Portal"]
API = "https://api.github.com"


def fetch(token: str, path: str) -> dict | list:
    req = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def upsert_csv(path: Path, header: list[str], rows_by_date: dict[str, list]) -> None:
    existing: dict[str, list] = {}
    if path.exists():
        with path.open() as f:
            for row in csv.reader(f):
                if row and row[0] != header[0]:
                    existing[row[0]] = row
    existing.update(rows_by_date)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for date in sorted(existing):
            w.writerow(existing[date])


def snapshot_repo(token: str, repo: str, data_dir: Path, today: str) -> str:
    base = data_dir / "traffic" / repo
    (base / "snapshots").mkdir(parents=True, exist_ok=True)

    views = fetch(token, f"/repos/{OWNER}/{repo}/traffic/views")
    clones = fetch(token, f"/repos/{OWNER}/{repo}/traffic/clones")
    referrers = fetch(token, f"/repos/{OWNER}/{repo}/traffic/popular/referrers")
    paths = fetch(token, f"/repos/{OWNER}/{repo}/traffic/popular/paths")
    meta = fetch(token, f"/repos/{OWNER}/{repo}")

    snapshot = {
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "views": views,
        "clones": clones,
        "referrers": referrers,
        "paths": paths,
        "stars": meta["stargazers_count"],
        "forks": meta["forks_count"],
        "watchers": meta["subscribers_count"],
    }
    (base / "snapshots" / f"{today}.json").write_text(
        json.dumps(snapshot, indent=2) + "\n"
    )

    upsert_csv(
        base / "views.csv",
        ["date", "views", "unique_visitors"],
        {v["timestamp"][:10]: [v["timestamp"][:10], v["count"], v["uniques"]]
         for v in views.get("views", [])},
    )
    upsert_csv(
        base / "clones.csv",
        ["date", "clones", "unique_cloners"],
        {c["timestamp"][:10]: [c["timestamp"][:10], c["count"], c["uniques"]]
         for c in clones.get("clones", [])},
    )
    upsert_csv(
        base / "stars.csv",
        ["date", "stars", "forks", "watchers"],
        {today: [today, snapshot["stars"], snapshot["forks"], snapshot["watchers"]]},
    )
    return (
        f"{repo}: {views.get('count', 0)}v/{views.get('uniques', 0)}u views, "
        f"{clones.get('count', 0)}c/{clones.get('uniques', 0)}u clones (14d)"
    )


def main() -> int:
    token = os.environ.get("TRAFFIC_PAT") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: set TRAFFIC_PAT or GITHUB_TOKEN", file=sys.stderr)
        return 1
    data_dir = Path(sys.argv[sys.argv.index("--data-dir") + 1]) if "--data-dir" in sys.argv else Path(".")
    today = dt.date.today().isoformat()
    failures = 0
    for repo in REPOS:
        try:
            print(snapshot_repo(token, repo, data_dir, today))
        except urllib.error.HTTPError as e:
            # Fail loudly per repo but keep snapshotting the others — a
            # 403 on one repo must not cost the day's data for the rest.
            print(f"ERROR {repo}: HTTP {e.code} {e.reason}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
