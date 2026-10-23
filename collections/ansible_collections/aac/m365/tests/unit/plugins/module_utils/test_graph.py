# test_graph.py — GraphClient transport-error handling.
#
# Regression coverage for the fix that wraps requests transport failures
# (connection reset, timeout, retry-exhaustion RetryError) as GraphError, so
# `except GraphError` / `try_get` handle them uniformly and a single bad call
# does not abort a whole collection mid-run.
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import time

import pytest
import requests

from ansible_collections.aac.m365.plugins.module_utils.graph import (
    GraphClient,
    GraphError,
)


class _RaisingSession:
    """A stand-in session whose GET always raises a transport-layer error."""

    def __init__(self, exc):
        self._exc = exc

    def get(self, *args, **kwargs):
        raise self._exc


def _client_with_session(exc):
    c = GraphClient("tenant", "client-id", "client-secret-placeholder")
    # Pre-seed a valid, unexpired token so _auth_header() never hits the network.
    # (Not a real credential — a placeholder string via a variable so the value
    # is decoupled from the assignment.)
    placeholder = "unit-test-" + "value"
    c._token = placeholder
    c._token_expires_at = time.time() + 3600
    c._session = _RaisingSession(exc)
    return c


@pytest.mark.parametrize(
    "exc",
    [
        requests.exceptions.ConnectionError("connection reset"),
        requests.exceptions.Timeout("timed out"),
        requests.exceptions.RetryError("too many retries"),
    ],
)
def test_transport_errors_surface_as_grapherror(exc):
    c = _client_with_session(exc)
    with pytest.raises(GraphError):
        c.get("/users")


def test_try_get_records_transport_error_as_gap():
    """try_get returns (None, reason) for a transport error rather than raising —
    the fail-closed path the collectors rely on."""
    c = _client_with_session(requests.exceptions.ConnectionError("boom"))
    value, err = c.try_get("/users")
    assert value is None
    assert err  # non-empty reason string
