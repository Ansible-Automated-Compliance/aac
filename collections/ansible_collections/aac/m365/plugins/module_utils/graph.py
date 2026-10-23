# -*- coding: utf-8 -*-
"""Shared Microsoft Graph client for the aac.m365 collection.

Every fact module in this collection uses this client. It handles:

  - Client-credentials OAuth (Azure AD app registration) — no user
    interaction; the app's tenant + client id + client secret are
    the only inputs.
  - Automatic token refresh when the cached token is within 60s of
    expiry.
  - Retry-after handling for Graph's documented 429 throttling.
  - A `get_all` helper that follows @odata.nextLink across pages
    so callers don't have to handle pagination themselves.

The module DELIBERATELY does NOT take a hard dependency on the
official microsoft.graph SDK — keeping the dependency surface to
just `requests` makes the collection installable without a
post-install step. If the SDK ever becomes worth pulling in we
can swap the implementation without touching call sites.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import os
import time
from typing import Any, Dict, List, Optional

try:
    import requests
    from requests.adapters import HTTPAdapter
    try:
        from urllib3.util.retry import Retry
    except ImportError:  # very old urllib3 shipped under requests
        from requests.packages.urllib3.util.retry import Retry  # type: ignore
except ImportError:
    requests = None    # caller checks; module fails loudly if missing
    HTTPAdapter = None
    Retry = None


def build_proxied_session(use_proxy: bool = True, proxy: Optional[str] = None):
    """A requests.Session with explicit proxy handling + retries.

    Shared by the Graph and Fabric clients so both survive corporate proxies:
    - explicit `proxy` wins (http + https); else honor env HTTP(S)_PROXY when
      `use_proxy`; else force direct (proxies={}, trust_env off).
    - a pooled session reuses the proxy CONNECT tunnel instead of opening a
      fresh one per call, and retries transient connect/SSL/5xx failures — the
      cause of the SSLEOFError seen mid-pagination behind proxies.
    """
    session = requests.Session()
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
        session.trust_env = True
    elif not use_proxy:
        session.proxies = {}
        session.trust_env = False
    else:
        env_https = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        env_http = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        proxies = {}
        if env_https:
            proxies["https"] = env_https
        if env_http:
            proxies["http"] = env_http
        if proxies:
            session.proxies = proxies
        session.trust_env = True
    if Retry is not None and HTTPAdapter is not None:
        try:
            retry = Retry(total=3, connect=3, read=2, backoff_factor=1.5,
                          status_forcelist=(500, 502, 503, 504),
                          allowed_methods=frozenset(["GET", "POST"]))
        except TypeError:   # urllib3 < 1.26
            retry = Retry(total=3, connect=3, read=2, backoff_factor=1.5,
                          status_forcelist=(500, 502, 503, 504),
                          method_whitelist=frozenset(["GET", "POST"]))
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
    return session


GRAPH_HOST = "https://graph.microsoft.com"
GRAPH_BASE = GRAPH_HOST + "/v1.0"
GRAPH_BETA = GRAPH_HOST + "/beta"
TOKEN_HOST = "https://login.microsoftonline.com"
SCOPE = "https://graph.microsoft.com/.default"


class GraphError(Exception):
    """Raised on any non-success response from Graph or the token
    endpoint. The exception carries the HTTP status and the raw
    response body so the module can surface a useful error."""

    def __init__(self, status: int, body: str, request_path: str = ""):
        self.status = status
        self.body = body
        self.request_path = request_path
        super().__init__(f"Graph error {status} at {request_path}: {body[:500]}")


class GraphClient:
    """Lightweight Microsoft Graph client.

    Caches the access token across calls; refreshes when it has less
    than 60 seconds left. Not thread-safe — Ansible modules run
    single-threaded so we don't need to be.
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        timeout: int = 30,
        use_proxy: bool = True,
        proxy: Optional[str] = None,
    ):
        if requests is None:
            raise GraphError(0, "the `requests` library is required", "(init)")
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self.use_proxy = use_proxy
        self.proxy = proxy
        self._token: Optional[str] = None
        self._token_expires_at: float = 0
        # One pooled session for the whole client. Reusing the proxy CONNECT
        # tunnel (rather than a fresh one per call) and adding retries is what
        # makes this survive a proxy that transiently drops TLS handshakes
        # (the SSLEOFError seen behind corporate proxies on pagination).
        self._session = self._build_session()

    def _build_session(self):
        return build_proxied_session(self.use_proxy, self.proxy)

    # ── Auth ──────────────────────────────────────────────────────────

    def _refresh_token(self) -> None:
        url = f"{TOKEN_HOST}/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": SCOPE,
        }
        r = self._session.post(url, data=data, timeout=self.timeout)
        if r.status_code != 200:
            raise GraphError(r.status_code, r.text, "/oauth2/v2.0/token")
        payload = r.json()
        self._token = payload["access_token"]
        # expires_in is seconds. Refresh 60s before actual expiry so a
        # call doesn't race the boundary.
        self._token_expires_at = time.time() + int(payload["expires_in"]) - 60

    def _auth_header(self) -> Dict[str, str]:
        if self._token is None or time.time() >= self._token_expires_at:
            self._refresh_token()
        return {"Authorization": f"Bearer {self._token}"}

    # ── HTTP ──────────────────────────────────────────────────────────

    def _request_with_throttle(
        self,
        url: str,
        request_path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """GET with one 429 retry. Used by both single-shot `get` and
        every page of `get_all` so pagination doesn't lose throttle
        handling.

        Graph documents Retry-After for 429. Honor it once; a second
        429 raises so callers see throttling rather than hanging."""
        try:
            r = self._session.get(url, headers=self._auth_header(), params=params, timeout=self.timeout)

            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", "5"))
                time.sleep(retry_after)
                r = self._session.get(
                    url, headers=self._auth_header(), params=params, timeout=self.timeout
                )
        except requests.exceptions.RequestException as exc:
            # Transport-layer failures (connection reset, timeout, and
            # retry-exhaustion `RetryError` from the HTTPAdapter) are NOT
            # GraphError, so `except GraphError` / `try_get` would let them
            # escape mid-collection and abort the whole module. Wrap them so
            # every caller handles transport and HTTP failures uniformly —
            # e.g. the per-mailbox loop skips a bad user and keeps going.
            # status 0 == no HTTP response (transport failure).
            raise GraphError(0, str(exc), request_path) from exc

        if r.status_code != 200:
            raise GraphError(r.status_code, r.text, request_path)
        return r.json()

    @staticmethod
    def _base(beta: bool) -> str:
        """Several CIS-relevant policy objects (device registration, default
        app management, authentication method detail) are only exposed on
        /beta. Callers opt in per call rather than the client pinning one
        version globally."""
        return GRAPH_BETA if beta else GRAPH_BASE

    def get(self, path: str, params: Optional[Dict[str, Any]] = None,
            beta: bool = False) -> Dict[str, Any]:
        """Single GET against a Graph path (e.g. `/users`)."""
        return self._request_with_throttle(f"{self._base(beta)}{path}", path, params=params)

    def get_all(self, path: str, params: Optional[Dict[str, Any]] = None,
                beta: bool = False) -> List[Dict[str, Any]]:
        """Follow @odata.nextLink across pages and return the union
        of `value` arrays. For Graph collection endpoints (users,
        directoryRoles, etc.) this is what you usually want."""
        results: List[Dict[str, Any]] = []
        page = self._request_with_throttle(f"{self._base(beta)}{path}", path, params=params)
        results.extend(page.get("value", []))
        next_link = page.get("@odata.nextLink")
        while next_link:
            # nextLink is a full URL, not a path; reuse the same
            # throttle-aware GET so subsequent pages survive 429 too.
            page = self._request_with_throttle(next_link, next_link)
            results.extend(page.get("value", []))
            next_link = page.get("@odata.nextLink")
        return results

    # ── Fail-closed collection ────────────────────────────────────────
    #
    # A collector that swallows a Graph error and emits a default is the
    # collection-layer version of a policy that passes on missing facts:
    # the assessment looks green because nothing was measured. These
    # helpers make unavailability explicit so the Rego can fail closed on
    # it rather than evaluating a fabricated default.

    def try_get(self, path: str, params: Optional[Dict[str, Any]] = None,
                beta: bool = False):
        """Return (value, error). `error` is None on success; on failure
        `value` is None and `error` is a short reason string. Never raises
        for HTTP-level failures -- the caller records the gap."""
        try:
            return self.get(path, params=params, beta=beta), None
        except GraphError as exc:
            return None, self._reason(exc)

    def try_get_all(self, path: str, params: Optional[Dict[str, Any]] = None,
                    beta: bool = False):
        """Collection form of `try_get`. On failure returns (None, reason)
        -- NOT an empty list, which a policy could not distinguish from
        "the tenant genuinely has none"."""
        try:
            return self.get_all(path, params=params, beta=beta), None
        except GraphError as exc:
            return None, self._reason(exc)

    @staticmethod
    def _reason(exc: "GraphError") -> str:
        if exc.status == 403:
            return f"permission denied ({exc.request_path}) -- app registration lacks the required scope"
        if exc.status == 404:
            return f"not found ({exc.request_path}) -- endpoint unavailable on this API version or tenant"
        if exc.status == 401:
            return f"unauthorized ({exc.request_path}) -- token rejected"
        return f"HTTP {exc.status} ({exc.request_path})"


def fetch_secure_score_controls(
    client: "GraphClient",
    control_ids,
) -> List[Dict[str, Any]]:
    """Fetch Secure Score control profiles by id.

    Uses GET /security/secureScoreControlProfiles/{id} per control instead
    of paginating the full catalog (~400+ profiles). Missing or
    unreachable controls are skipped rather than failing the caller."""
    controls: List[Dict[str, Any]] = []
    for control_id in sorted(control_ids):
        try:
            controls.append(
                client.get(f"/security/secureScoreControlProfiles/{control_id}")
            )
        except GraphError:
            continue
    return controls
