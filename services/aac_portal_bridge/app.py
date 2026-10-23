"""
AAC Portal Bridge — read-only inventory catalog API for the AAC Customer Portal.

Serves the normalized software-inventory catalog the portal pulls per tenant:

    GET /api/aac/v1/inventory_catalog?cursor=<int>&limit=<int>
        Auth: Authorization: Bearer <token>   (+ optional X-Token-Id header)
        -> {"catalog": [ {vendor, product, version, cpe, host_count, source,
                          first_seen_at, last_seen_at}, ... ],
            "next_cursor": <int|null>, "count": <int>}

    GET /api/aac/v1/whoami   (auth)     -> token identity + scopes
    GET /api/aac/v1/healthz  (no auth)  -> {status, version}

The catalog comes from the `inventory_catalog` materialized view in the compliance
DB (populated by refresh_inventory_catalog.yml from host_facts). This service is
read-only and holds no customer data of its own — the portal pulls, matches against
CVE feeds, and drives per-tenant patch intelligence.

Config via environment:
    PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD   — compliance DB connection
    AAC_BRIDGE_TOKENS   — comma-separated "token_id:secret" pairs (preferred)
    AAC_BRIDGE_TOKEN / AAC_BRIDGE_TOKEN_ID          — single-token fallback
    BRIDGE_PORT (default 8005)
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

import asyncpg
from fastapi import Depends, FastAPI, Header, HTTPException, Query

BRIDGE_VERSION = "1.0.0"
DEFAULT_LIMIT = 10_000
MAX_LIMIT = 50_000

_PG = {
    "host": os.getenv("PG_HOST", "compliance-db.aac.svc.cluster.local"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "database": os.getenv("PG_DB", "compliance"),
    "user": os.getenv("PG_USER", "compliance_reader"),
    "password": os.getenv("PG_PASSWORD", ""),
}


def _load_tokens() -> dict[str, str]:
    """Map secret -> token_id. Supports multi-token and single-token config."""
    tokens: dict[str, str] = {}
    for pair in os.getenv("AAC_BRIDGE_TOKENS", "").split(","):
        pair = pair.strip()
        if ":" in pair:
            tid, secret = pair.split(":", 1)
            if secret:
                tokens[secret] = tid
    single = os.getenv("AAC_BRIDGE_TOKEN")
    if single:
        tokens[single] = os.getenv("AAC_BRIDGE_TOKEN_ID", "default")
    return tokens


_TOKENS = _load_tokens()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(min_size=1, max_size=5, **_PG)
    try:
        yield
    finally:
        await app.state.pool.close()


app = FastAPI(title="AAC Portal Bridge", version=BRIDGE_VERSION, lifespan=lifespan)


def require_token(
    authorization: Optional[str] = Header(default=None),
    x_token_id: Optional[str] = Header(default=None),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    secret = authorization.split(" ", 1)[1].strip()
    token_id = _TOKENS.get(secret)
    if token_id is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return {"token_id": token_id, "scopes": ["inventory_pull", "cve_feed"]}


@app.get("/api/aac/v1/healthz")
async def healthz():
    return {"status": "ok", "version": BRIDGE_VERSION, "service": "aac-portal-bridge"}


@app.get("/api/aac/v1/whoami")
async def whoami(ident: dict = Depends(require_token)):
    return {
        "token_id": ident["token_id"],
        "scopes": ident["scopes"],
        "service": "aac-portal-bridge",
        "version": BRIDGE_VERSION,
    }


@app.get("/api/aac/v1/inventory_catalog")
async def inventory_catalog(
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    ident: dict = Depends(require_token),
):
    rows = await app.state.pool.fetch(
        """
        SELECT vendor, product, version, cpe, host_count, source,
               first_seen_at, last_seen_at
          FROM inventory_catalog
         ORDER BY product, vendor, version, source
         LIMIT $1 OFFSET $2
        """,
        limit,
        cursor,
    )
    catalog = [
        {
            "vendor": r["vendor"],
            "product": r["product"],
            "version": r["version"],
            "cpe": r["cpe"],
            "host_count": r["host_count"],
            "source": r["source"],
            "first_seen_at": r["first_seen_at"].isoformat() if r["first_seen_at"] else None,
            "last_seen_at": r["last_seen_at"].isoformat() if r["last_seen_at"] else None,
        }
        for r in rows
    ]
    next_cursor = cursor + limit if len(rows) == limit else None
    return {"catalog": catalog, "next_cursor": next_cursor, "count": len(catalog)}
