# AAC Portal Bridge

Read-only API that serves the AAC software-inventory catalog to the **AAC Customer
Portal**. The portal's inventory puller calls this per tenant, pulls the catalog
into `tenant_inventory_catalog`, and matches it against CVE feeds to produce
per-customer patch intelligence.

## The two legs of the pipe

This service is only the **outbound** half. The full loop:

```
  outbound │ AAC ──► Portal      this service; the Portal PULLS the catalog
           │                     inventory_catalog aggregates hostnames away
           │                     → Portal sees {vendor, product, version, host_count}
           │
  inbound  │ AAC ◄── Portal      ansible/playbooks/pull_patch_worklist.yml
           │                     pulls GET /portal/v1/tenants/{id}/patches
           │                     → resolves host_count back to real hostnames
           │                       locally, against installed_inventory
```

**Hostnames never leave the customer.** The catalog groups
`installed_inventory` by `(package_vendor, package_name, package_version)` and
serves only a count. The inbound leg reverses that aggregation locally — the
Portal supplies the CVE, its criticality, and the fix address; AAC supplies the
"where". See `ansible/files/patch_worklist_schema.sql` for the landing tables and
`patch_worklist_resolve.sql` for the resolution.

**No binaries move either way.** The Portal hosts no patch artifacts; what comes
down the inbound leg is package coordinates, an install command, and an advisory
link. The customer fetches from their own entitled source.

## Endpoints

| Method | Path | Auth | Returns |
|---|---|---|---|
| GET | `/api/aac/v1/inventory_catalog?cursor=&limit=` | Bearer | `{catalog:[…], next_cursor, count}` |
| GET | `/api/aac/v1/whoami` | Bearer | token identity + scopes |
| GET | `/api/aac/v1/healthz` | none | `{status, version}` |

Catalog row: `{vendor, product, version, cpe, host_count, source, first_seen_at, last_seen_at}`.
Pagination is cursor/offset based; the portal follows `next_cursor` until it is `null`.

## Data source

Reads the `inventory_catalog` materialized view in the compliance DB, populated by
`ansible/playbooks/refresh_inventory_catalog.yml` from `host_facts` (the fact
collection's installed-package inventory) + `manual_product_declarations`. The
bridge holds **no state of its own** and connects read-only (`compliance_reader`).

## Run locally
```bash
pip install -r requirements.txt
export PG_HOST=… PG_PASSWORD=… AAC_BRIDGE_TOKENS='tok-acme:s3cret'
uvicorn app:app --host 0.0.0.0 --port 8005
curl -H 'Authorization: Bearer s3cret' \
  'http://localhost:8005/api/aac/v1/inventory_catalog?limit=5'
```

## Deploy (OpenShift, `aac` namespace)
See `deploy-ocp.yaml` header — build/push the image, create the `aac-portal-bridge`
secret (DB password + bridge token), `oc apply`. The Route host becomes the
tenant's `aac_bridge_url` in the portal.

## Config (env)
`PG_HOST PG_PORT PG_DB PG_USER PG_PASSWORD` · `AAC_BRIDGE_TOKENS` (`id:secret,…`)
or `AAC_BRIDGE_TOKEN`/`AAC_BRIDGE_TOKEN_ID` · `BRIDGE_PORT` (default 8005).
