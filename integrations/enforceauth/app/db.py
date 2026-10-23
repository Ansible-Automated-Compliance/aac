"""Read-only queries against the AAC compliance_results table.

Every query returns the LATEST row per (hostname, framework) — compliance_results
is append-only, so a host accumulates one row per framework per assessment cycle.
DISTINCT ON (…) ORDER BY … evaluation_timestamp DESC collapses that to current
state. Connections use the compliance_reader role (SELECT-only); this service
never writes.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras


def _dsn() -> dict:
    return dict(
        host=os.environ.get("AAC_DB_HOST", "host.containers.internal"),
        port=int(os.environ.get("AAC_DB_PORT", "5432")),
        dbname=os.environ.get("AAC_DB_NAME", "compliance"),
        user=os.environ.get("AAC_DB_USER", "compliance_reader"),
        password=os.environ.get("AAC_DB_PASSWORD", ""),
        connect_timeout=int(os.environ.get("AAC_DB_CONNECT_TIMEOUT", "5")),
        # Belt-and-braces: refuse to run anything but SELECT on this connection.
        options="-c default_transaction_read_only=on",
    )


@contextmanager
def _cursor():
    conn = psycopg2.connect(**_dsn())
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
    finally:
        conn.close()


# Latest row per framework for a single host, matched on hostname OR ip_address.
# EnforceAuth's notion of host identity may be either, so we accept both.
_HOST_SQL = """
    SELECT DISTINCT ON (framework)
        hostname, ip_address, framework, compliance_percentage, compliant,
        passed_controls, failed_controls, total_controls, violations,
        evaluation_timestamp
    FROM compliance_results
    WHERE hostname = %(key)s OR ip_address = %(key)s
    ORDER BY framework, evaluation_timestamp DESC
"""

# Latest row per (hostname, framework) across every assessed host.
_ALL_SQL = """
    SELECT DISTINCT ON (hostname, framework)
        hostname, ip_address, framework, compliance_percentage, compliant,
        evaluation_timestamp
    FROM compliance_results
    WHERE hostname IS NOT NULL
    ORDER BY hostname, framework, evaluation_timestamp DESC
"""


def fetch_host_rows(host_key: str) -> list[dict]:
    with _cursor() as cur:
        cur.execute(_HOST_SQL, {"key": host_key})
        return list(cur.fetchall())


def fetch_all_rows() -> list[dict]:
    with _cursor() as cur:
        cur.execute(_ALL_SQL)
        return list(cur.fetchall())


def ping() -> bool:
    with _cursor() as cur:
        cur.execute("SELECT 1")
        return cur.fetchone() is not None
