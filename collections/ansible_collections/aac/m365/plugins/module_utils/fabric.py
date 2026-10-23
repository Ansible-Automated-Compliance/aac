# -*- coding: utf-8 -*-
"""Fabric (Power BI) admin API client for the aac.m365 collection.

Section 9 of the CIS M365 v7.0.0 benchmark is 12 tenant settings that
Microsoft Graph does not expose at all. They live behind the Fabric /
Power BI admin API, which is a THIRD authentication surface for this
collection:

  Graph       -> https://graph.microsoft.com/.default
  Exchange PS -> app-only certificate (Connect-ExchangeOnline)
  Fabric      -> https://analysis.windows.net/powerbi/api/.default   <- here

Client credentials work here, unlike Exchange Online PowerShell, so this
is a plain REST client rather than another pwsh wrapper.

TENANT PREREQUISITE the token cannot tell you about: a service principal
can hold the right Entra permissions and still be refused, because Fabric
gates API access behind an admin-portal switch ("Service principals can
use Fabric APIs") that must name the app's security group. The failure is
a 401/403 at call time, not a token error, so `_reason` calls that out
explicitly -- otherwise it reads as a credential problem and sends the
operator to the wrong place.

Mirrors graph.py's fail-closed contract: try_get returns (value, error)
so a collector records what it could not read rather than emitting a
default a policy would evaluate as a pass.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import time
from typing import Any, Dict, Optional

from ansible_collections.aac.m365.plugins.module_utils.graph import (
    build_proxied_session,
)

try:
    import requests
except ImportError:
    requests = None

FABRIC_BASE = "https://api.fabric.microsoft.com/v1"
POWERBI_BASE = "https://api.powerbi.com/v1.0/myorg"
TOKEN_HOST = "https://login.microsoftonline.com"
SCOPE = "https://analysis.windows.net/powerbi/api/.default"


class FabricError(Exception):
    def __init__(self, status: int, body: str, request_path: str = ""):
        self.status = status
        self.body = body
        self.request_path = request_path
        super().__init__(f"Fabric API error {status} at {request_path}: {body[:500]}")


class FabricClient:
    """Reads Fabric/Power BI tenant settings with an app-only token."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str,
                 timeout: int = 30, use_proxy: bool = True, proxy: Optional[str] = None):
        if requests is None:
            raise FabricError(0, "the `requests` library is required", "(init)")
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self.use_proxy = use_proxy
        self.proxy = proxy
        self._token: Optional[str] = None
        self._expires_at: float = 0
        # Pooled, retrying, proxy-aware session — see graph.build_proxied_session.
        self._session = build_proxied_session(use_proxy, proxy)

    def _refresh_token(self) -> None:
        url = f"{TOKEN_HOST}/{self.tenant_id}/oauth2/v2.0/token"
        r = self._session.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": SCOPE,
            },
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise FabricError(r.status_code, r.text, "/oauth2/v2.0/token")
        payload = r.json()
        self._token = payload["access_token"]
        self._expires_at = time.time() + int(payload["expires_in"]) - 60

    def _auth_header(self) -> Dict[str, str]:
        if self._token is None or time.time() >= self._expires_at:
            self._refresh_token()
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, url: str, path: str) -> Dict[str, Any]:
        r = self._session.get(url, headers=self._auth_header(), timeout=self.timeout)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "5")))
            r = self._session.get(url, headers=self._auth_header(), timeout=self.timeout)
        if r.status_code != 200:
            raise FabricError(r.status_code, r.text, path)
        return r.json()

    def try_get_tenant_settings(self):
        """Return (settings_by_name, error).

        The Fabric endpoint is preferred; the Power BI endpoint is the
        older path for the same data and is tried as a fallback so a
        tenant that has not been migrated still reports settings rather
        than a gap.
        """
        last_err = None
        for base, path in (
            (FABRIC_BASE, "/admin/tenantsettings"),
            (POWERBI_BASE, "/admin/tenantsettings"),
        ):
            try:
                payload = self._get(f"{base}{path}", path)
            except FabricError as exc:
                last_err = self._reason(exc)
                continue
            rows = payload.get("tenantSettings", payload.get("value", []))
            # Key by settingName -- that is how the benchmark refers to
            # them, so the policy can look each control's setting up
            # directly instead of scanning a list.
            return {
                s.get("settingName"): {
                    "enabled": s.get("enabled"),
                    "can_specify_security_groups": s.get("canSpecifySecurityGroups"),
                    "enabled_security_groups": s.get("enabledSecurityGroups", []),
                    "excluded_security_groups": s.get("excludedSecurityGroups", []),
                    "tenant_setting_group": s.get("tenantSettingGroup"),
                }
                for s in rows
                if s.get("settingName")
            }, None
        return None, last_err or "no Fabric tenant settings endpoint responded"

    @staticmethod
    def _reason(exc: "FabricError") -> str:
        if exc.status in (401, 403):
            return (
                f"Fabric admin API returned {exc.status} at {exc.request_path}. "
                "Holding the Entra permission is not sufficient: Fabric gates "
                "API access behind the admin-portal setting 'Service principals "
                "can use Fabric APIs', which must name a security group "
                "containing this app."
            )
        if exc.status == 404:
            return f"Fabric admin API endpoint not found ({exc.request_path})"
        return f"Fabric admin API error {exc.status} at {exc.request_path}"
