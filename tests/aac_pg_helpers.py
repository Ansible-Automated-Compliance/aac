"""Helpers for the database-backed tests: run SQL in a PostgreSQL container
through `podman exec ... psql`, and render a playbook's query + named_args as
plain SQL. The fixtures that provide the container are in conftest.py.
"""
from __future__ import annotations

import subprocess


class Pg:
    """Run SQL in one throwaway database of a PostgreSQL container."""

    def __init__(self, container: str, database: str):
        self.container = container
        self.database = database

    def _psql(self, sql: str, database: str, *flags: str) -> str:
        proc = subprocess.run(
            ["podman", "exec", "-i", self.container, "psql", "-U", "postgres", "-d", database,
             "-v", "ON_ERROR_STOP=1", "-q", "-X", *flags],
            input=sql, capture_output=True, text=True, timeout=180,
        )
        if proc.returncode != 0:
            raise AssertionError("psql failed:\n%s\n--- SQL (first 2000 chars) ---\n%s"
                                 % (proc.stderr.strip(), sql[:2000]))
        return proc.stdout

    def run(self, sql: str) -> None:
        """Execute statements; fail the test on the first SQL error."""
        self._psql(sql, self.database)

    def rows(self, sql: str) -> list:
        """Run one query; return rows as lists of strings ('' for NULL)."""
        out = self._psql(sql, self.database, "-At", "-F", "\x1f")
        lines = out.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        return [line.split("\x1f") for line in lines]

    def value(self, sql: str) -> str:
        rows = self.rows(sql)
        assert len(rows) == 1 and len(rows[0]) == 1, rows
        return rows[0][0]


def sql_literal(value) -> str:
    """A Python value as a SQL literal (what the driver does for a named arg)."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def render_named(query: str, args: dict) -> str:
    """Render a community.postgresql `query` + `named_args` pair as plain SQL:
    %(name)s becomes a literal and %% becomes %."""
    for key, value in args.items():
        query = query.replace("%%(%s)s" % key, sql_literal(value))
    assert "%(" not in query, "unrendered named argument in query"
    return query.replace("%%", "%")
