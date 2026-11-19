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

# Result shapes. Every query states which one it is, because the policy
# either iterates a fact (a list) or dereferences fields of it (an
# object), and PowerShell's JSON output does not preserve the difference.
RAW = "raw"
LIST = "list"
OBJECT = "object"

JSON_DEPTH = 6
TRUNCATED_MARKER = "AAC_JSON_DEPTH_EXCEEDED"

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


def as_list(value, service="powershell"):
    """Normalise a collection result to a list of objects.

    Returns (rows, error). null -> [], one object -> [object], and null
    rows are dropped. A row that is not an object is an error: a policy
    reading `row.Field` on a string or number gets undefined and passes.
    """
    if value is None:
        return [], None
    rows = value if isinstance(value, list) else [value]
    rows = [r for r in rows if r is not None]
    bad = sorted({type(r).__name__ for r in rows if not isinstance(r, dict)})
    if bad:
        return None, (f"{service} returned a collection whose rows are not objects "
                      f"({', '.join(bad)}), so its fields cannot be read")
    return rows, None


def as_object(value, service="powershell"):
    """Normalise a single-object result. Returns (object, error).

    A one-element list is unwrapped. null, an empty list or several rows
    are errors: an organisation-level setting that arrives as an array
    makes every `.Field` dereference undefined, which reads as a pass.
    """
    if isinstance(value, list):
        rows = [r for r in value if r is not None]
        if len(rows) == 1:
            value = rows[0]
        else:
            return None, (f"{service} returned {len(rows)} objects where exactly one "
                          "was expected")
    if value is None:
        return None, f"{service} cmdlet returned no object"
    if not isinstance(value, dict):
        return None, (f"{service} returned {type(value).__name__} where an object "
                      "was expected")
    return value, None


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

    def _wrap(self, body, shape=RAW):
        """Build a script that connects, runs `body`, and emits JSON.

        Shape. ConvertTo-Json unrolls a one-element pipeline into a bare
        object, and a policy that iterates a list then walks the object's
        field values and passes. For a LIST query the body's output is
        collected with the array subexpression operator directly around
        the invocation -- `@(& { body })` -- and handed to -InputObject,
        which serialises an array as an array: zero rows become [], one
        row [row]. It is deliberately not `$r = & { body }; @($r)`: an
        empty pipeline assigns $null, and `@($null)` is a one-element
        array, so zero rows would come back as [null].

        -EnumsAsStrings: without it ConvertTo-Json writes .NET enum values
        as integers (the cmdlet's own examples show "DayOfWeek": 5), while
        every policy comparison on these fields is against the enum NAME
        ("Enabled", "Off", "ExternalUserAndGuestSharing"). Strings are left
        unchanged, so the switch can only turn an int into the name the
        policy expects.

        Depth: ConvertTo-Json (PowerShell 7.1+) warns and truncates when an
        object nests deeper than -Depth. The warning is captured, and a
        truncated document is an error rather than evidence -- truncated
        members serialise as type-name strings that a policy would read.
        The throw sits inside `try` so the session is still disconnected.

        Compress keeps stdout to one line so partial writes cannot yield
        half-valid JSON.
        """
        if shape == LIST:
            collect = f"  $aacValue = @(& {{ {body} }})"
            depth = JSON_DEPTH + 1   # the wrapping array costs one level
        else:
            collect = f"  $aacValue = & {{ {body} }}"
            depth = JSON_DEPTH
        return "\n".join([
            "$ErrorActionPreference = 'Stop'",
            "$ProgressPreference = 'SilentlyContinue'",
            CONNECT[self.service],
            "try {",
            collect,
            f"  $aacJson = ConvertTo-Json -InputObject $aacValue -Depth {depth} -Compress -EnumsAsStrings "
            "-WarningAction SilentlyContinue -WarningVariable aacJsonWarnings",
            "  if ($aacJsonWarnings) { throw \"" + TRUNCATED_MARKER + ": $($aacJsonWarnings -join ' ')\" }",
            "  $aacJson",
            "} finally {",
            f"  {DISCONNECT[self.service]}",
            "}",
        ])

    def try_run(self, body, shape=RAW):
        """Run a snippet. Returns (value, error); never raises for a
        cmdlet-level failure.

        shape=LIST    the value is always a list of objects (see as_list)
        shape=OBJECT  the value is always one object (see as_object)
        shape=RAW     the parsed JSON as returned (legacy behaviour)
        """
        if shape not in (RAW, LIST, OBJECT):
            raise PwshError("unknown result shape '%s'" % shape)
        if not self.available():
            return None, f"PowerShell not available at {self.pwsh_path} -- this EE cannot audit {self.service}"

        script = self._wrap(body, shape)
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
            value = json.loads(out)
        except ValueError:
            return None, f"{self.service} returned output that is not JSON: {out[:200]}"
        if shape == LIST:
            return as_list(value, self.service)
        if shape == OBJECT:
            return as_object(value, self.service)
        return value, None

    def _reason(self, stderr):
        """Turn a PowerShell error into something an operator can act on."""
        text = (stderr or "").strip()
        low = text.lower()
        if TRUNCATED_MARKER.lower() in low:
            return (f"evidence missing: {self.service} output exceeded the JSON "
                    f"depth limit ({JSON_DEPTH}) and would have been truncated")
        if "certificate" in low and ("password" in low or "not find" in low):
            return f"{self.service} certificate could not be loaded -- check the certificate path and password"
        if "unauthorized" in low or "access is denied" in low or "accessdenied" in low:
            return (f"{self.service} access denied -- the service principal needs the "
                    "Exchange.ManageAsApp application permission and an assigned Entra role")
        if "could not be found" in low and "module" in low:
            return f"{self.service} PowerShell module is not installed in this execution environment"
        return f"{self.service} PowerShell failed: {text[:300]}"
