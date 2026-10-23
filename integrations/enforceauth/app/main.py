"""AAC Compliance-State API — read-only authorization context for EnforceAuth.

Exposes the LATEST compliance assessment per host from AAC's compliance_results
table in two shapes EnforceAuth's OPA runtime can consume:

  * http.send (runtime pull):  GET /v1/compliance/hosts/{host_key}
  * OPA bundle (preloaded):    GET /v1/bundle.tar.gz  -> data.aac.compliance.hosts

Fail-closed by design: unknown hosts return found=false, missing timestamps read
as infinitely stale, and NULL compliance flags read as non-compliant. The
consuming policy (policy/enforceauth_authz.rego) denies on all of these.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from . import db, bundle
from .shape import host_state, hosts_summary

MAX_AGE_SECONDS = int(os.environ.get("AAC_MAX_AGE_SECONDS", "86400"))

app = FastAPI(
    title="AAC Compliance-State API",
    description="Read-only compliance state as runtime authorization context for EnforceAuth.",
    version="1.0.0",
)


@app.get("/health")
def health():
    try:
        db.ping()
        return {"status": "healthy", "database": "reachable", "max_age_seconds": MAX_AGE_SECONDS}
    except Exception as exc:  # noqa: BLE001 — health must report, not raise
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "unreachable", "error": str(exc)},
        )


@app.get("/v1/compliance/hosts")
def list_hosts():
    return {"hosts": hosts_summary(db.fetch_all_rows(), MAX_AGE_SECONDS)}


@app.get("/v1/compliance/hosts/{host_key}")
def get_host(host_key: str):
    # Always HTTP 200 with found=true/false so the OPA policy reasons over the
    # body rather than branching on status codes. Absence -> found=false -> deny.
    return host_state(host_key, db.fetch_host_rows(host_key), MAX_AGE_SECONDS)


@app.get("/v1/bundle.tar.gz")
def get_bundle():
    hosts = hosts_summary(db.fetch_all_rows(), MAX_AGE_SECONDS)
    compliance = {"hosts": {h["hostname"]: h for h in hosts}}
    body = bundle.build_bundle(compliance)
    return Response(
        content=body,
        media_type="application/gzip",
        headers={"Content-Disposition": "attachment; filename=compliance.tar.gz"},
    )
