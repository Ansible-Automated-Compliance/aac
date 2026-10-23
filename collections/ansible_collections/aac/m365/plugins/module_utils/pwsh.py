# -*- coding: utf-8 -*-
"""Shared PowerShell runner for the aac.m365 collection.

67 of the CIS M365 v7.0.0 controls can only be audited through PowerShell
-- Exchange Online, Teams, SharePoint and Security & Compliance have no
REST equivalent for the settings the benchmark checks. This runs those
cmdlets from a Linux execution environment and returns their output as
parsed JSON.

DESIGN NOTES

Unattended by construction. Collectors run inside an AAP job with no
human present, so every connection uses app-only **certificate**
authentication. Client secrets do not work for Exchange Online
PowerShell; only certificates do.

Secrets never appear in argv. A certificate password passed as a command
argument is visible in /proc and in any process listing. It is passed
through the environment instead, and the generated script reads it from
there.

Mirrors graph.py's fail-closed contract: `try_run` returns
(value, error) rather than raising, so a collector records what it could
not read instead of emitting a default that a policy would evaluate as a
pass.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import json
import os
import subprocess
import tempfile

PWSH = "/usr/local/bin/pwsh"
DEFAULT_TIMEOUT = 300

# Connection preambles per service. Each authenticates app-only with a
# certificate and suppresses the banner so stdout carries only our JSON.
CONNECT = {
    "exchange": (
        "Connect-ExchangeOnline -AppId $env:AAC_APP_ID "
        "-CertificateFilePath $env:AAC_CERT_PATH "
        "-CertificatePassword (ConvertTo-SecureString -String $env:AAC_CERT_PASSWORD -AsPlainText -Force) "
        "-Organization $env:AAC_ORGANIZATION -ShowBanner:$false -ErrorAction Stop | Out-Null"
    ),
    # Security & Compliance shares the ExchangeOnlineManagement module but
    # a different endpoint, so it needs its own session.
    "purview": (
        "Connect-IPPSSession -AppId $env:AAC_APP_ID "
        "-CertificateFilePath $env:AAC_CERT_PATH "
        "-CertificatePassword (ConvertTo-SecureString -String $env:AAC_CERT_PASSWORD -AsPlainText -Force) "
        "-Organization $env:AAC_ORGANIZATION -ErrorAction Stop | Out-Null"
    ),
    "teams": (
        "Connect-MicrosoftTeams -ApplicationId $env:AAC_APP_ID "
        "-CertificateThumbprint $env:AAC_CERT_THUMBPRINT "
        "-TenantId $env:AAC_TENANT_ID -ErrorAction Stop | Out-Null"
    ),
    "sharepoint": (
        "Connect-PnPOnline -Url $env:AAC_SHAREPOINT_ADMIN_URL "
        "-ClientId $env:AAC_APP_ID "
        "-CertificatePath $env:AAC_CERT_PATH "
        "-CertificatePassword (ConvertTo-SecureString -String $env:AAC_CERT_PASSWORD -AsPlainText -Force) "
        "-Tenant $env:AAC_ORGANIZATION -ErrorAction Stop | Out-Null"
    ),
}

DISCONNECT = {
    "exchange": "Disconnect-ExchangeOnline -Confirm:$false -ErrorAction SilentlyContinue | Out-Null",
    "purview": "Disconnect-ExchangeOnline -Confirm:$false -ErrorAction SilentlyContinue | Out-Null",
    "teams": "Disconnect-MicrosoftTeams -ErrorAction SilentlyContinue | Out-Null",
    "sharepoint": "Disconnect-PnPOnline -ErrorAction SilentlyContinue | Out-Null",
}


class PwshError(Exception):
    """Raised when pwsh cannot be run at all, or a connection fails.

    Per-cmdlet failures do not raise -- they come back through try_run so
    a partial collection still yields an evaluable, honestly-scoped result.
    """

    def __init__(self, message, stderr=""):
        self.message = message
        self.stderr = stderr
        super().__init__(message)


class PwshRunner:
    """Runs PowerShell audit snippets against a Microsoft 365 service."""

    def __init__(self, service, app_id, organization, tenant_id=None,
                 cert_path=None, cert_password=None, cert_thumbprint=None,
                 sharepoint_admin_url=None, timeout=DEFAULT_TIMEOUT,
                 pwsh_path=PWSH):
        if service not in CONNECT:
            raise PwshError(f"unknown service '{service}'")
        self.service = service
        self.timeout = timeout
        self.pwsh_path = pwsh_path
        # Secrets go in the environment, never argv.
        self._env = dict(os.environ)
        self._env.update({
            "AAC_APP_ID": app_id or "",
            "AAC_ORGANIZATION": organization or "",
            "AAC_TENANT_ID": tenant_id or "",
            "AAC_CERT_PATH": cert_path or "",
            "AAC_CERT_PASSWORD": cert_password or "",
            "AAC_CERT_THUMBPRINT": cert_thumbprint or "",
            "AAC_SHAREPOINT_ADMIN_URL": sharepoint_admin_url or "",
        })

    def available(self):
        """True when pwsh is present. Checked before anything else so a
        missing runtime is reported as such rather than as a tenant
        finding."""
        return os.path.exists(self.pwsh_path)

    def _wrap(self, body):
        """Build a script that connects, runs `body`, and emits JSON.

        -Depth 6 because several Exchange policy objects nest deeply
        enough that the default of 2 silently truncates them to strings.
        Compress keeps stdout to one line so partial writes cannot yield
        half-valid JSON.
        """
        return "\n".join([
            "$ErrorActionPreference = 'Stop'",
            "$ProgressPreference = 'SilentlyContinue'",
            CONNECT[self.service],
            "try {",
            f"  $result = & {{ {body} }}",
            "  $result | ConvertTo-Json -Depth 6 -Compress",
            "} finally {",
            f"  {DISCONNECT[self.service]}",
            "}",
        ])

    def try_run(self, body):
        """Run a snippet. Returns (value, error); never raises for a
        cmdlet-level failure."""
        if not self.available():
            return None, f"PowerShell not available at {self.pwsh_path} -- this EE cannot audit {self.service}"

        script = self._wrap(body)
        path = None
        try:
            # A temp file rather than -Command: long snippets hit argv
            # limits, and quoting rules differ between shells.
            with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False) as fh:
                fh.write(script)
                path = fh.name
            proc = subprocess.run(
                [self.pwsh_path, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", path],
                capture_output=True, text=True, timeout=self.timeout, env=self._env,
            )
        except subprocess.TimeoutExpired:
            return None, f"{self.service} PowerShell timed out after {self.timeout}s"
        except OSError as exc:
            return None, f"could not execute {self.pwsh_path}: {exc}"
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

        if proc.returncode != 0:
            return None, self._reason(proc.stderr)

        out = (proc.stdout or "").strip()
        if not out:
            # Distinct from "returned nothing meaningful": an empty stdout
            # after a zero exit means the cmdlet produced no object, which
            # a policy must not read as a configured-and-empty result.
            return None, f"{self.service} cmdlet returned no output"
        try:
            return json.loads(out), None
        except ValueError:
            return None, f"{self.service} returned output that is not JSON: {out[:200]}"

    def _reason(self, stderr):
        """Turn a PowerShell error into something an operator can act on."""
        text = (stderr or "").strip()
        low = text.lower()
        if "certificate" in low and ("password" in low or "not find" in low):
            return f"{self.service} certificate could not be loaded -- check the certificate path and password"
        if "unauthorized" in low or "access is denied" in low or "accessdenied" in low:
            return (f"{self.service} access denied -- the service principal needs the "
                    "Exchange.ManageAsApp application permission and an assigned Entra role")
        if "could not be found" in low and "module" in low:
            return f"{self.service} PowerShell module is not installed in this execution environment"
        return f"{self.service} PowerShell failed: {text[:300]}"
