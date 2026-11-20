"""Filters for fetch_redhat_cve_data.yml: turn one Red Hat Security Data API
CVE document into rows for the AAC CVE cache.

The API (https://access.redhat.com/hydra/rest/securitydata/cve/<CVE>.json)
returns, per CVE:

  affected_release  one entry per product and fixed build:
                    {product_name, release_date, advisory, cpe, package}
                    where package is  name-epoch:version-release
  package_state     one entry per product with no fixed build:
                    {product_name, fix_state, package_name, cpe}

Only parsing happens here. Which installed build is lower than which fixed
build is decided in the database (ansible/files/rpm_evr_functions.sql).

Tested by tests/test_redhat_cve_rows.py against a recorded response.
"""
from __future__ import annotations

import re
from collections import Counter

SOURCE = "redhat_security_data_api"

CVE_ID_RE = re.compile(r"^CVE-[0-9]{4}-[0-9]{4,}$")

# name-epoch:version-release. Neither version nor release may contain '-'.
_NEVR_RE = re.compile(r"^(?P<name>[^/\s]+)-(?P<epoch>[0-9]+):(?P<version>[^-:\s]+)-(?P<release>[^-:\s]+)$")

# Same pattern as aac_rpm_dist_tag() in rpm_evr_functions.sql.
_DIST_TAG_RE = re.compile(r"(?:^|[.+])((?:el|fc|amzn|sle|oe)[0-9]+(?:_[0-9]+)?)(?![0-9])")

# cpe:/o:redhat:enterprise_linux:9.4::baseos -> token enterprise_linux, major 9
_CPE_RE = re.compile(r"^cpe:/[aho]:redhat:(?P<token>[a-z0-9_]+):(?P<major>[0-9]+)(?:\.[0-9]+)?(?::|$)")

# The operating system's own repositories, including its extended-support
# branches (rhel_eus, rhel_e4s, rhel_aus, rhel_tus, rhel_els ...). Anything else
# (openshift, enterprise_linux_nvidia, enterprise_linux_ai ...) is a layered
# product: kept for the record, not matched against hosts.
_BASE_OS_TOKENS = ("enterprise_linux", "enterprise_linux_eus")

_SEVERITY = {"critical": "CRITICAL", "important": "HIGH", "moderate": "MEDIUM", "low": "LOW"}

_FIX_STATE = {
    "not affected": "not_affected",
    "affected": "affected",
    "will not fix": "will_not_fix",
    "fix deferred": "fix_deferred",
    "out of support scope": "out_of_support",
    "under investigation": "under_investigation",
}


def valid_cve_ids(value) -> list:
    """Split a comma / whitespace separated string (or a list) into CVE ids.

    Raises ValueError on anything that is not a CVE id: the id is the only
    thing sent to the API, and it goes into the URL.
    """
    if isinstance(value, (list, tuple)):
        parts = [str(v).strip() for v in value]
    else:
        parts = re.split(r"[,\s]+", str(value or "").strip())
    ids = []
    for part in parts:
        if not part:
            continue
        cve = part.upper()
        if not CVE_ID_RE.match(cve):
            raise ValueError("not a CVE id: %r" % part)
        if cve not in ids:
            ids.append(cve)
    return ids


def _cpe_parts(cpe):
    m = _CPE_RE.match(cpe or "")
    if not m:
        return None, None
    return m.group("token"), m.group("major")


def _base_os(cpe) -> bool:
    token, _major = _cpe_parts(cpe)
    return bool(token) and (token in _BASE_OS_TOKENS or token.startswith("rhel_"))


def _stream_from_cpe(cpe):
    token, major = _cpe_parts(cpe)
    if token and (token in _BASE_OS_TOKENS or token.startswith("rhel_")):
        return "el" + major
    return None


def parse_nevr(package):
    """'kernel-0:5.14.0-687.64.1.el9_8' -> ('kernel', '5.14.0-687.64.1.el9_8').

    The EVR is returned in the canonical form the catalog stores: a zero epoch
    is left out. Returns None when the string is not name-epoch:version-release
    (a container image reference, or a bare name such as 'kpatch-patch').
    """
    m = _NEVR_RE.match((package or "").strip())
    if not m:
        return None
    epoch = int(m.group("epoch"))
    evr = "%s-%s" % (m.group("version"), m.group("release"))
    if epoch:
        evr = "%d:%s" % (epoch, evr)
    return m.group("name"), evr


def dist_tag(evr):
    release = (evr or "").rsplit("-", 1)[-1]
    m = _DIST_TAG_RE.search(release)
    return m.group(1) if m else None


def redhat_cve_rows(doc) -> dict:
    """One API document -> {'cve_id', 'event', 'fixed_builds', 'skipped'}."""
    if not isinstance(doc, dict) or not CVE_ID_RE.match(str(doc.get("name", ""))):
        raise ValueError("not a Red Hat Security Data API CVE document (no CVE 'name')")
    cve_id = doc["name"]

    rows, skipped, seen = [], [], set()

    def add(row):
        key = (row["product_name"], row["package_name"], row["fixed_evr"] or "")
        if key in seen:
            return
        seen.add(key)
        rows.append(row)

    for rel in doc.get("affected_release") or []:
        package = rel.get("package") or ""
        parsed = parse_nevr(package)
        if parsed is None:
            skipped.append({
                "product_name": rel.get("product_name", ""),
                "package": package,
                "advisory_id": rel.get("advisory", ""),
                "reason": ("container image reference" if "/" in package
                           else "no version in the package field"),
            })
            continue
        name, evr = parsed
        tag = dist_tag(evr)
        stream = re.match(r"[a-z]+[0-9]+", tag).group(0) if tag else _stream_from_cpe(rel.get("cpe"))
        add({
            "package_name": name,
            "fixed_evr": evr,
            "fix_state": "fixed",
            "stream": stream,
            "dist_tag": tag,
            "product_name": rel.get("product_name", ""),
            "cpe": rel.get("cpe"),
            "advisory_id": rel.get("advisory"),
            "released_at": rel.get("release_date"),
            "base_os": _base_os(rel.get("cpe")),
        })

    for state in doc.get("package_state") or []:
        name = state.get("package_name") or ""
        if not name or "/" in name:
            skipped.append({
                "product_name": state.get("product_name", ""),
                "package": name,
                "advisory_id": "",
                "reason": "container image reference" if name else "no package name",
            })
            continue
        raw = str(state.get("fix_state", "")).strip()
        add({
            "package_name": name,
            "fixed_evr": None,
            "fix_state": _FIX_STATE.get(raw.lower(), re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_") or "unknown"),
            "stream": _stream_from_cpe(state.get("cpe")),
            "dist_tag": None,
            "product_name": state.get("product_name", ""),
            "cpe": state.get("cpe"),
            "advisory_id": None,
            "released_at": None,
            "base_os": _base_os(state.get("cpe")),
        })

    # The CVE row carries ONE product: the base-OS package named most often.
    names = Counter(r["package_name"] for r in rows if r["base_os"] and r["fix_state"] == "fixed")
    if not names:
        names = Counter(r["package_name"] for r in rows if r["base_os"])
    product = sorted(names.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if names else None

    cvss = (doc.get("cvss3") or {}).get("cvss3_base_score")
    try:
        cvss = float(cvss) if cvss not in (None, "") else None
    except (TypeError, ValueError):
        cvss = None

    references = []
    for block in doc.get("references") or []:
        references.extend(u.strip() for u in str(block).splitlines() if u.strip())

    return {
        "cve_id": cve_id,
        "event": {
            "cve_id": cve_id,
            "cvss_v3": cvss,
            "severity": _SEVERITY.get(str(doc.get("threat_severity", "")).lower()),
            "published_at": doc.get("public_date"),
            "vendor": "redhat",
            "product": product,
            "description": (doc.get("bugzilla") or {}).get("description")
                           or " ".join(str(d) for d in (doc.get("details") or []))[:500] or None,
            "references": references,
            "source": SOURCE,
        },
        "fixed_builds": rows,
        "skipped": skipped,
    }


class FilterModule:
    def filters(self):
        return {
            "aac_valid_cve_ids": valid_cve_ids,
            "aac_redhat_cve_rows": redhat_cve_rows,
        }
