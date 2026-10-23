#!/usr/bin/env python3
"""
dependency_map.py — "if I change X, what do I have to re-check?"

Builds a reverse-dependency map of the repo so a change to one artifact surfaces
everything that referenced it. This exists because stale artifacts do not error:
a runbook describing a superseded flow, a health check probing dead endpoints, or
a guard testing a condition that no longer applies all read as authoritative and
get trusted at the worst possible moment.

WHAT IT TRACKS

  PROVIDERS — things that define an artifact
    *.sql                     -> the tables and views it CREATEs
    seed_*.yml                -> the AAP job template / workflow names it creates
    ansible/playbooks/*.yml   -> itself, by path and basename

  CONSUMERS — things that reference an artifact
    playbooks / scripts       -> tables they query, files they read, playbooks they call
    docs / runbooks / skills  -> playbooks, tables, template names they mention
    demo scripts              -> tables they query

USAGE
    dependency_map.py --impact patch_worklist        # who reads this table?
    dependency_map.py --impact identify_affected_components.yml
    dependency_map.py --check                        # uncommitted changes
    dependency_map.py --check --since origin/main    # a whole branch
    dependency_map.py --list-providers               # what defines what
    dependency_map.py --json                         # the whole graph

LIMITS — read these before trusting a clean result
    Text matching, not semantic analysis. It cannot see a table name assembled at
    runtime, a template referenced only by numeric id, or a dependency that exists
    only in someone's head. A clean report means "nothing obvious" — never
    "nothing". Treat it as a prompt to look, not a proof that you needn't.
"""
import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True).stdout.strip() or ".")

SCAN_DIRS = ["ansible", "scripts", "docs", "demos", "install", ".claude/skills", "extensions"]
SCAN_EXT = {".yml", ".yaml", ".sql", ".py", ".sh", ".md", ".j2"}
SKIP_PARTS = {".git", "node_modules", "__pycache__", ".venv", "policies"}

# SQL keywords that follow FROM/JOIN/INTO but are not tables
SQL_NOISE = {
    "select", "where", "values", "set", "as", "on", "and", "or", "not", "null",
    "table", "view", "if", "exists", "only", "lateral", "unnest", "generate_series",
    "dual", "information_schema", "pg_catalog", "public", "now", "current_schema",
}
# Table names too generic to be useful signal
TABLE_MIN_LEN = 4


def iter_files():
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_dir() or p.suffix not in SCAN_EXT:
                continue
            if SKIP_PARTS & set(p.parts):
                continue
            yield p


def rel(p):
    return str(p.relative_to(ROOT))


def extract(text, path):
    """Return (provides, consumes) sets of artifact keys."""
    provides, consumes = set(), set()
    suffix = path.suffix
    name = path.name

    # ---- providers -------------------------------------------------------
    if suffix == ".sql":
        for m in re.finditer(r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?"
                             r"(?:TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?"
                             r"([a-zA-Z_][a-zA-Z0-9_.]*)", text, re.I):
            provides.add("table:" + m.group(1).split(".")[-1].lower())
        for m in re.finditer(r"ALTER\s+TABLE\s+([a-zA-Z_][a-zA-Z0-9_.]*)", text, re.I):
            consumes.add("table:" + m.group(1).split(".")[-1].lower())

    if name.startswith("seed_") and suffix in (".yml", ".yaml"):
        for m in re.finditer(r'name:\s*"((?:AAC|AMI|CIS|Lab10|Friday|NERC)[^"]{3,80})"', text):
            provides.add("aap:" + m.group(1).strip())

    if suffix in (".yml", ".yaml") and "ansible/playbooks" in str(path):
        provides.add("playbook:" + name)

    # ---- consumers -------------------------------------------------------
    # SQL table references
    for m in re.finditer(r"\b(?:FROM|JOIN|INTO|UPDATE|TRUNCATE)\s+"
                         r"([a-zA-Z_][a-zA-Z0-9_]{%d,})" % (TABLE_MIN_LEN - 1),
                         text, re.I):
        t = m.group(1).lower()
        if t not in SQL_NOISE:
            consumes.add("table:" + t)

    # file references (schema sql, vars, other playbooks)
    for m in re.finditer(r"[\w./-]*files/([\w.-]+\.sql)", text):
        consumes.add("file:" + m.group(1))
    for m in re.finditer(r"(?:import_playbook|include_tasks|ansible-playbook)[:\s]+[\w./-]*?([\w-]+\.ya?ml)", text):
        consumes.add("playbook:" + m.group(1))

    # playbooks named anywhere (docs, skills, seeders reference them by path)
    for m in re.finditer(r"(?:ansible/playbooks/|playbook:\s*[\"']?[\w./-]*?)([\w-]+\.ya?ml)", text):
        consumes.add("playbook:" + m.group(1))

    # AAP template / workflow names
    for m in re.finditer(r'["\'`]((?:AAC|AMI|CIS|Lab10|Friday|NERC)[ _][^"\'`]{3,80})["\'`]', text):
        consumes.add("aap:" + m.group(1).strip())

    provides.discard(None)
    consumes -= provides          # a file does not depend on itself
    return provides, consumes


def build():
    providers = defaultdict(set)   # artifact -> {files that define it}
    consumers = defaultdict(set)   # artifact -> {files that reference it}
    file_provides = defaultdict(set)
    cache = {}

    # Pass 1 — syntax-driven extraction
    for p in iter_files():
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        cache[rel(p)] = text
        prov, cons = extract(text, p)
        for a in prov:
            providers[a].add(rel(p))
            file_provides[rel(p)].add(a)
        for a in cons:
            consumers[a].add(rel(p))

    # Pass 2 — now that every table name is known, find BARE mentions of them.
    # Docs and scripts routinely name a table in prose with no SQL keyword in
    # front of it, and those are precisely the references that rot unnoticed:
    # a runbook telling you to query a view that was renamed still reads fine.
    known = [a.split(":", 1)[1] for a in providers if a.startswith("table:")]
    known = [t for t in known if len(t) >= 8 and "_" in t]   # specific enough to be safe
    if known:
        pat = re.compile(r"\b(" + "|".join(sorted(map(re.escape, known), key=len, reverse=True)) + r")\b")
        for f, text in cache.items():
            for m in pat.finditer(text):
                key = "table:" + m.group(1).lower()
                if f not in providers.get(key, set()):
                    consumers[key].add(f)

    return providers, consumers, file_provides


def norm(term):
    """Accept 'patch_worklist', 'table:patch_worklist', 'foo.yml', a path."""
    t = term.strip()
    if ":" in t.split("/")[-1] and t.split(":")[0] in ("table", "file", "playbook", "aap"):
        return [t]
    cands = []
    if t.endswith((".yml", ".yaml")):
        cands.append("playbook:" + Path(t).name)
    if t.endswith(".sql"):
        cands.append("file:" + Path(t).name)
    cands += ["table:" + t.lower(), "aap:" + t, "playbook:" + t, "file:" + t]
    # dedupe, preserving order — 'foo.yml' generates the same playbook key twice
    return list(dict.fromkeys(cands))


def report_impact(term, providers, consumers, file_provides):
    hits = 0
    for key in norm(term):
        prov, cons = providers.get(key, set()), consumers.get(key, set())
        if not prov and not cons:
            continue
        hits += 1
        kind, _, val = key.partition(":")
        print(f"\n\033[1m{kind.upper()}: {val}\033[0m")
        if prov:
            print("  defined by:")
            for f in sorted(prov):
                print(f"    {f}")
        if cons:
            print(f"  referenced by ({len(cons)}) — CHECK THESE:")
            for f in sorted(cons):
                print(f"    {f}")
        else:
            print("  referenced by: nothing found")
    if not hits:
        print(f"No artifact matching '{term}'. Try --list-providers, or the bare table name.")
        return 1
    return 0


def report_change(paths, providers, consumers, file_provides):
    """For each changed file: what does it define, and who consumes that?"""
    if not paths:
        print("No changed files.")
        return 0
    print("\033[1mCHANGE IMPACT\033[0m")
    any_downstream = False
    for f in sorted(paths):
        arts = file_provides.get(f, set())
        downstream = set()
        for a in arts:
            downstream |= (consumers.get(a, set()) - {f})
        # a changed file is itself an artifact others may reference
        for key in ("playbook:" + Path(f).name, "file:" + Path(f).name):
            downstream |= (consumers.get(key, set()) - {f})
        print(f"\n  \033[1m{f}\033[0m")
        if arts:
            print(f"    defines: {', '.join(sorted(arts))}")
        if downstream:
            any_downstream = True
            print(f"    → re-check {len(downstream)}:")
            for d in sorted(downstream):
                print(f"        {d}")
        else:
            print("    → nothing obvious references it")
    if any_downstream:
        print("\n\033[1mStale artifacts do not error. Open each one above.\033[0m")
    return 0


def changed_files(since):
    if since:
        cmd = ["git", "diff", "--name-only", f"{since}...HEAD"]
    else:
        cmd = ["git", "status", "--porcelain"]
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT).stdout
    files = []
    for line in out.splitlines():
        f = line[3:].strip() if not since else line.strip()
        if f and (ROOT / f).exists() and Path(f).suffix in SCAN_EXT:
            files.append(f)
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--impact", metavar="ARTIFACT", help="who references this?")
    ap.add_argument("--check", action="store_true", help="impact of changed files")
    ap.add_argument("--since", metavar="REF", help="with --check: diff against REF")
    ap.add_argument("--list-providers", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    providers, consumers, file_provides = build()

    if a.json:
        print(json.dumps({
            "providers": {k: sorted(v) for k, v in providers.items()},
            "consumers": {k: sorted(v) for k, v in consumers.items()},
        }, indent=1, sort_keys=True))
        return 0
    if a.list_providers:
        for k in sorted(providers):
            print("%-52s %s" % (k, ", ".join(sorted(providers[k]))))
        print(f"\n{len(providers)} defined artifacts · {len(consumers)} referenced artifacts")
        return 0
    if a.impact:
        return report_impact(a.impact, providers, consumers, file_provides)
    if a.check:
        return report_change(changed_files(a.since), providers, consumers, file_provides)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
