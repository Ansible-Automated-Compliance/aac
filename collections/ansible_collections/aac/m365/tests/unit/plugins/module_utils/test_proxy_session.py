# -*- coding: utf-8 -*-
"""Unit tests for build_proxied_session (the shared proxy-aware client).

Regression cover for a corporate-proxy outage: behind such a proxy the
M365 collection failed with SSLEOFError mid-pagination because every call
opened a fresh transient request with no proxy control and no retry.
build_proxied_session gives Graph and Fabric one pooled, retrying,
proxy-aware Session; use_proxy/proxy expose the control to the modules.

The proxy-resolution contract these lock in:
  - explicit `proxy` wins for both http and https,
  - `use_proxy=False` forces a direct connection (proxies={}, trust_env off),
  - otherwise env HTTP(S)_PROXY is honored,
and every session carries a retrying adapter on both schemes.
"""
from __future__ import annotations

import pytest

from ansible_collections.aac.m365.plugins.module_utils.graph import (
    build_proxied_session,
)


def test_explicit_proxy_wins_both_schemes():
    s = build_proxied_session(proxy="http://proxy.example:8080")
    assert s.proxies == {
        "http": "http://proxy.example:8080",
        "https": "http://proxy.example:8080",
    }


def test_use_proxy_false_forces_direct():
    s = build_proxied_session(use_proxy=False)
    # No proxy, and trust_env off so an ambient HTTPS_PROXY can't sneak back in.
    assert s.proxies == {}
    assert s.trust_env is False


def test_env_proxy_honored_when_enabled(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://envproxy:3128")
    s = build_proxied_session(use_proxy=True)
    assert s.proxies.get("https") == "http://envproxy:3128"


def test_explicit_proxy_beats_env(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://envproxy:3128")
    s = build_proxied_session(proxy="http://explicit:8080")
    assert s.proxies["https"] == "http://explicit:8080"


def test_retry_adapter_mounted_on_https():
    s = build_proxied_session()
    adapter = s.get_adapter("https://graph.microsoft.com")
    # 3 total retries with backoff — the pagination SSLEOFError is now retried
    # rather than aborting the whole assessment.
    assert adapter.max_retries.total == 3
    assert adapter.max_retries.backoff_factor >= 1
