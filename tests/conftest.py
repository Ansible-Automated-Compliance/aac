"""Shared fixtures for the tests in this directory.

`aac_pg` gives the database-backed tests (rpm version comparison, CVE
matching) a real PostgreSQL, because the code under test is SQL: it starts
quay.io/sclorg/postgresql-16-c9s with podman, or uses a container that is
already running when AAC_TEST_PG_CONTAINER names one. SQL goes through
`podman exec ... psql`, so no host port and no Python driver are needed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid

import pytest

from aac_pg_helpers import Pg

PG_IMAGE = os.environ.get("AAC_TEST_PG_IMAGE", "quay.io/sclorg/postgresql-16-c9s:latest")


def _ready(container: str) -> bool:
    proc = subprocess.run(
        ["podman", "exec", container, "psql", "-U", "postgres", "-Atc", "select 1"],
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode == 0 and proc.stdout.strip() == "1"


@pytest.fixture(scope="session")
def _pg_container():
    existing = os.environ.get("AAC_TEST_PG_CONTAINER")
    if existing:
        assert _ready(existing), "AAC_TEST_PG_CONTAINER=%s is not accepting connections" % existing
        yield existing
        return
    if shutil.which("podman") is None:
        pytest.skip("podman is not installed and AAC_TEST_PG_CONTAINER is not set: "
                    "the SQL under test needs a PostgreSQL to run in")
    name = "aac-test-pg-" + uuid.uuid4().hex[:8]
    started = subprocess.run(
        ["podman", "run", "-d", "--rm", "--name", name,
         "-e", "POSTGRESQL_ADMIN_PASSWORD=" + uuid.uuid4().hex, PG_IMAGE],
        capture_output=True, text=True, timeout=600,
    )
    assert started.returncode == 0, "could not start %s: %s" % (PG_IMAGE, started.stderr)
    try:
        # The image starts the server once to initialise it and then again for
        # real, so one good answer is not enough: wait for two in a row.
        good, deadline = 0, time.time() + 120
        while good < 2:
            assert time.time() < deadline, "PostgreSQL in %s did not become ready" % name
            good = good + 1 if _ready(name) else 0
            time.sleep(1)
        yield name
    finally:
        subprocess.run(["podman", "rm", "-f", name], capture_output=True, timeout=60)


@pytest.fixture(scope="module")
def aac_pg(_pg_container):
    """A fresh, empty database for one test module."""
    database = "aac_test_" + uuid.uuid4().hex[:10]
    admin = Pg(_pg_container, "postgres")
    admin.run('CREATE DATABASE "%s";' % database)
    try:
        yield Pg(_pg_container, database)
    finally:
        admin.run('DROP DATABASE IF EXISTS "%s" WITH (FORCE);' % database)
