#!/usr/bin/env python3
"""Write docs/reference/DATABASE_DICTIONARY.md from the table definitions in this repository.

Every CREATE TABLE, ALTER TABLE ... ADD COLUMN and CREATE VIEW in the code is
read (not the documents, tests or the policies submodule) and written out as one
dictionary: tables, columns, types, keys, and where each is defined. The page
also lists the places where the same column name has different types.

    python3 scripts/db_dictionary.py --write   # regenerate the page
    python3 scripts/db_dictionary.py --check   # exit 1 if the page is out of date

Standard library only. It reads SQL text; it does not connect to a database.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "reference" / "DATABASE_DICTIONARY.md"
SEARCH = ("ansible", "scripts", "collections", "install", "services", "integrations", "extensions")
SUFFIXES = {".sql", ".yml", ".yaml", ".py", ".sh", ".j2"}

CREATE = re.compile(r"CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][\w.]*)\s*\(", re.I)
ALTER = re.compile(r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?([A-Za-z_][\w.]*)\s+(ADD\s+COLUMN[^;]*)", re.I | re.S)
ADD = re.compile(r"ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_]\w*)\s+([^,;\"'\n]+)", re.I)
FUNCTION = re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([A-Za-z_]\w*)", re.I)
VIEW = re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_]\w*)", re.I)
USED = re.compile(r"\b(?:INSERT\s+INTO|FROM|JOIN|UPDATE|DELETE\s+FROM)\s+([a-z_][a-z0-9_]{3,})\b", re.I)
WRITTEN = re.compile(r"\bINSERT\s+INTO\s+([a-z_][a-z0-9_]{3,})\b", re.I)
TABLE_LEVEL = re.compile(r"(PRIMARY KEY|UNIQUE|FOREIGN KEY|CONSTRAINT|CHECK|EXCLUDE|LIKE)\b", re.I)
TYPE = re.compile(
    r"((?:character varying|double precision|timestamp with(?:out)? time zone|[A-Za-z_]+)(?:\s*\([^)]*\))?(?:\[\])?)", re.I
)
# Names that follow FROM or UPDATE in this tree and are not tables of the compliance database.
NOT_TABLES = re.compile(r"^(pg_|json|information_|generate_|regexp_|string_|ansible_|unnest|dba_|audit_unified|v_|__)")
IGNORED = {"site_config", "vault_secrets", "extra_vars", "group_vars", "opa_framework_map", "postgresql_query",
           "aac_host", "aac_demo_host", "zift_sentinel_demo", "_walk_module", "fw_map", "blast_radius",
           "hosts_auto", "hosts_manual", "current_state", "version_at_finding", "ai_governance_check"}


def _sources(root: Path):
    for top in SEARCH:
        for path in sorted((root / top).rglob("*")):
            if path.is_file() and path.suffix in SUFFIXES and "node_modules" not in path.parts and path != Path(__file__).resolve():
                yield path


def _body(text: str, start: int) -> str:
    depth, i = 1, start
    while i < len(text) and depth:
        depth += text[i] == "("
        depth -= text[i] == ")"
        i += 1
    return text[start:i - 1]


def _split(body: str) -> list[str]:
    parts, depth, current = [], 0, ""
    for ch in body:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    return parts + [current]


def _column(name: str, rest: str) -> dict:
    rest = " ".join(rest.split())
    match = TYPE.match(rest)
    kind = match.group(1) if match else rest
    return {"name": name.lower(), "type": re.sub(r"\s+\(", "(", kind.upper()), "rest": rest[len(kind):].strip()}


def read(root: Path = ROOT) -> dict:
    """Return {'tables': {name: {...}}, 'views': {name: [files]}, 'used': {name: [files]}}."""
    tables: dict[str, dict] = {}
    views: dict[str, set] = defaultdict(set)
    used: dict[str, set] = defaultdict(set)
    written: set[str] = set()
    functions: set[str] = set()
    counts: Counter = Counter()
    for path in _sources(root):
        raw = path.read_text(errors="replace")
        if not re.search(r"CREATE\s|ALTER\s+TABLE|INSERT\s+INTO|\bFROM\b", raw, re.I):
            continue
        rel = path.relative_to(root).as_posix()
        text = re.sub(r"--[^\n]*", "", raw)
        engine = "SQLite" if "sqlite3" in raw else "PostgreSQL"
        for match in CREATE.finditer(text):
            name = match.group(1).lower().split(".")[-1]
            entry = tables.setdefault(name, {"files": [], "columns": {}, "constraints": [], "engine": engine})
            if rel not in entry["files"]:
                entry["files"].append(rel)
            for part in _split(_body(text, match.end())):
                part = " ".join(part.split())
                if not part:
                    continue
                if TABLE_LEVEL.match(part):
                    if part not in entry["constraints"]:
                        entry["constraints"].append(part)
                    continue
                col = re.match(r'"?([A-Za-z_]\w*)"?\s+(.*)', part)
                if col:
                    column = _column(col.group(1), col.group(2))
                    entry["columns"].setdefault(column["name"], []).append({**column, "file": rel, "created": True})
        for match in ALTER.finditer(text):
            name = match.group(1).lower().split(".")[-1]
            entry = tables.setdefault(name, {"files": [], "columns": {}, "constraints": [], "engine": engine})
            for add in ADD.finditer(match.group(2)):
                column = _column(add.group(1), add.group(2))
                entry["columns"].setdefault(column["name"], []).append({**column, "file": rel})
                if rel not in entry["files"]:
                    entry["files"].append(rel)
        for match in VIEW.finditer(text):
            views[match.group(1).lower()].add(rel)
        for match in USED.finditer(raw if path.suffix == ".py" else text):
            used[match.group(1).lower()].add(rel)
            counts[match.group(1).lower()] += 1
        functions.update(m.group(1).lower() for m in FUNCTION.finditer(text))
        for match in WRITTEN.finditer(raw):
            written.add(match.group(1).lower())
    return {"tables": tables, "views": {k: sorted(v) for k, v in views.items()}, "used": {k: sorted(v) for k, v in used.items()},
            "written": sorted(written), "functions": sorted(functions), "counts": dict(counts)}


def _types(entry: dict, name: str) -> list[str]:
    return sorted({c["type"] for c in entry["columns"][name]})


def _link(path: str) -> str:
    return f"[`{Path(path).name}`](../../{path})"


def render(schema: dict) -> str:
    tables, views, used = schema["tables"], schema["views"], schema["used"]
    pg = {n: t for n, t in tables.items() if t["engine"] == "PostgreSQL"}
    other = {n: t for n, t in tables.items() if t["engine"] != "PostgreSQL"}
    out = [
        "# Database dictionary",
        "",
        "> Generated by `scripts/db_dictionary.py` from the table definitions in this repository. Do not edit by hand:",
        "> change the schema, then run `python3 scripts/db_dictionary.py --write`.",
        "",
        "This page lists every table the compliance database can hold: its columns, their types and where each is "
        "defined. A table is created only when the feature that owns it is installed, so a given database may hold "
        "fewer. For the design, the type rules and what is missing, see "
        "[Database architecture](../architecture/DATABASE_ARCHITECTURE.md).",
        "",
        "## Summary",
        "",
        "| Item | Count |",
        "|---|---:|",
        f"| PostgreSQL tables | {len(pg)} |",
        f"| Columns in those tables | {sum(len(t['columns']) for t in pg.values())} |",
        f"| Views | {len(views)} |",
        f"| Files that define a table or add a column | {len({f for t in pg.values() for f in t['files']})} |",
        f"| Tables in another store | {len(other)} |",
        "",
    ]

    by_column: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    usage: Counter = Counter()
    for name, table in pg.items():
        for column in table["columns"]:
            for kind in _types(table, column):
                by_column[column][kind].append(name)
                usage[kind] += 1

    out += ["## Types in use", "", "| Type | Columns |", "|---|---:|"]
    out += [f"| `{kind}` | {count} |" for kind, count in sorted(usage.items(), key=lambda item: (-item[1], item[0]))]
    out += ["", "## The same column name with different types", "",
            "A column name that means the same thing should have one type everywhere. These do not.", "",
            "| Column | Types and the tables that use each |", "|---|---|"]
    for column in sorted(by_column, key=lambda c: (-sum(len(v) for v in by_column[c].values()), c)):
        kinds = by_column[column]
        if len(kinds) > 1 and column != "id":
            cells = "; ".join(f"`{kind}` in {', '.join(sorted(names))}"
                              for kind, names in sorted(kinds.items(), key=lambda item: (-len(item[1]), item[0])))
            out.append(f"| `{column}` | {cells} |")
    ids = by_column.get("id", {})
    out += ["", "## Row identifiers", "", "| Type of `id` | Tables |", "|---|---:|"]
    out += [f"| `{kind}` | {len(names)} |" for kind, names in sorted(ids.items(), key=lambda item: -len(item[1]))]
    no_id = sorted(name for name, table in pg.items() if "id" not in table["columns"])
    out += [f"| no `id` column | {len(no_id)} |", "", "Tables without an `id` column: " + ", ".join(f"`{n}`" for n in no_id) + ".", ""]

    missing = sorted(name for name in used
                     if name not in tables and name not in views and name not in IGNORED and name not in schema["functions"]
                     and (name in schema["written"] or "_" in name) and not NOT_TABLES.match(name))
    known_missing = [name for name in missing if schema["counts"].get(name, 0) > 1 or name in schema["written"]]
    out += ["## Tables that are used and never created", "",
            "These names follow `INSERT INTO`, `FROM`, `JOIN` or `UPDATE` in the code, and no file in the repository "
            "creates a table or view with that name. Some are aliases inside a query; the others are jobs that "
            "cannot run on a database built from this repository.", "",
            "| Name | Used in |", "|---|---|"]
    out += [f"| `{name}` | {', '.join(_link(f) for f in used[name][:4])}{' and more' if len(used[name]) > 4 else ''} |"
            for name in known_missing]
    out += ["", "## Views", "", "| View | Defined in |", "|---|---|"]
    out += [f"| `{name}` | {', '.join(_link(f) for f in files)} |" for name, files in sorted(views.items())]

    out += ["", "## Tables", ""]
    for name in sorted(pg):
        table = pg[name]
        readers = [f for f in used.get(name, []) if f not in table["files"]]
        out += [f"### `{name}`", "",
                f"Defined in {', '.join(_link(f) for f in table['files'])}. "
                f"Used by {len(readers)} other file{'s' if len(readers) != 1 else ''}.", "",
                "| Column | Type | Rules and default |", "|---|---|---|"]
        ordered = sorted(table["columns"].items(), key=lambda item: not any(d.get("created") for d in item[1]))
        for column, definitions in ordered:
            kinds = " or ".join(f"`{k}`" for k in _types(table, column))
            rest = definitions[0]["rest"].replace("|", "\\|") or " "
            out.append(f"| `{column}` | {kinds} | {rest} |")
        if table["constraints"]:
            out += ["", "Table rules: " + "; ".join(f"`{c}`" for c in table["constraints"]) + "."]
        out.append("")
    if other:
        out += ["## Tables in another store", "",
                "These are created in a local SQLite file by a script. They are not in the compliance database.", "",
                "| Table | Columns | Defined in |", "|---|---:|---|"]
        out += [f"| `{name}` | {len(table['columns'])} | {', '.join(_link(f) for f in table['files'])} |"
                for name, table in sorted(other.items())]
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="regenerate the page")
    mode.add_argument("--check", action="store_true", help="exit 1 if the page is out of date")
    args = parser.parse_args(argv)
    text = render(read())
    if args.write:
        PAGE.parent.mkdir(parents=True, exist_ok=True)
        PAGE.write_text(text)
        return 0
    if not PAGE.exists() or PAGE.read_text() != text:
        print("docs/reference/DATABASE_DICTIONARY.md is out of date: run python3 scripts/db_dictionary.py --write", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
