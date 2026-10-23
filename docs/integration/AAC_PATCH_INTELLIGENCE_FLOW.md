# AAC Patch Intelligence — From Compliance Audit to Per-Customer Patch Plan

**Version:** v1.1
**Date:** 2026-07-21
**Audience:** AAC platform + Customer Portal stakeholders; customer-facing where noted.
**Authors:** Tim Coulter; Claude (Anthropic).
**Status:** Proven live end-to-end (see §0.1).

---

## 1. The idea in one sentence

**Every compliance audit already collects the complete installed-software inventory of each managed device — so the same data that proves compliance also tells us, per customer, exactly what is running, what is vulnerable, and what to patch first.**

No new agent, no separate inventory tool. The audit *is* the inventory source.

### 0.1 Proven live end-to-end (2026-07-21)

The entire chain was executed with **real code and real data** — not mocked:

| Stage | Evidence |
|---|---|
| Audit → inventory | `host_facts` → `installed_inventory` **33,113 rows / 98 hosts** → `inventory_catalog` matview **3,921 rows / 2,808 products** |
| AAC Portal Bridge | Built in-cluster and **deployed to OpenShift** (Deployment/Service/Route); serving over HTTPS with token auth (401 without token; paginated) |
| Portal inventory puller | The real `src.feeds.runner pull_inventory` pulled **3,921 rows** into `tenant_inventory_catalog` (`status: success, bridge_version: 1.0.0`) |
| Portal matcher | The real `src.feeds.runner match` produced the per-customer patch list |

**The resulting prioritized patch list** (tenant "Acme Utilities (lab)"):

| CVE | Severity | KEV | Affected | Hosts |
|---|---|---|---|---|
| **CVE-2023-4911** (glibc "Looney Tunables") | HIGH | **KEV** | 3 versions | 94 |
| **CVE-2023-38545** (curl SOCKS5 overflow) | CRITICAL | – | 5 versions | 94 |

The KEV (actively-exploited) glibc item ranks **above** the CRITICAL curl item — real-world
risk beats raw CVSS, exactly the intended prioritization. *(CVE feed here was a 2-CVE seed
fixture; production uses the full NVD + CISA-KEV pull.)*

---

## 2. Why this is valuable

| Today (typical) | With AAC Patch Intelligence |
|---|---|
| Inventory and patching are separate tools with separate agents | One data source — the compliance audit — feeds both |
| "What's installed?" answered per-host, manually | Per-customer catalog: every product, every version, host counts, in one place |
| Patch decisions by gut / vendor bulletins | Patches ranked by **actual exposure** (your installed versions × live CVE feeds) and **real-world risk** (CVSS + CISA KEV actively-exploited) |
| Customer environments patched generically | Patch plan **scoped to each customer's actual environment** and their enrolled vendors/frameworks |
| Identify → hand off → hope it gets done | Identify → prioritize → **trigger the AAP patch job** → evidence back in the audit trail |

The compliance history (PostgreSQL) means this is also **longitudinal** — you can show a customer their exposure trend and mean-time-to-patch over time, not just a point-in-time list.

---

## 3. The full flow

```
 ┌─ CUSTOMER ENVIRONMENT ──────────────────────────────────────────────┐
 │  AAP-managed devices (RHEL/Ubuntu/Amazon/Windows/appliances)         │
 │        │  aac_gather_facts (package_facts / win software)            │
 │        ▼                                                             │
 │  host_facts   (full installed inventory: product, version, patch)    │
 │        │  refresh_inventory_catalog.yml                              │
 │        ▼                                                             │
 │  installed_inventory ─▶ inventory_catalog (materialized view)        │
 │        │                                                             │
 │  AAC Portal Bridge  GET /api/aac/v1/inventory_catalog  (token-auth)  │
 └────────┼────────────────────────────────────────────────────────────┘
          │  nightly pull (per tenant, scope: inventory_pull)
 ┌─ AAC CUSTOMER PORTAL (operator-hosted, multi-tenant) ───────────────┐
          ▼                                                             │
 │  inventory_puller ─▶ tenant_inventory_catalog  (per customer)        │
 │        │                                                             │
 │  matcher  ──join {cpe | vendor+product}──▶  CVE feeds (NVD + CISA KEV)│
 │        │                                    + vendor advisories       │
 │        ▼                                    (RHSA / USN / MSRC)        │
 │  per-tenant CVE hits ─ filtered by enrollment (buckets/vendors/       │
 │        │                frameworks) + severity/KEV preferences         │
 │        ▼                                                             │
 │  PRIORITIZED PATCH PLAN  (what to patch, on which hosts, in what order)│
 │        │                                                             │
 │  routers/aap.py  ─trigger─▶  AAP patch job (scoped to customer hosts) │
 └─────────────────────────────────────────────────────────────────────┘
```

**Two clean halves, one boundary:**
- **AAC (assessment/intelligence):** collect inventory → expose it → the portal matches, prioritizes, and decides *what* to patch and *in what order*.
- **AAP (execution):** the portal *triggers* an AAP job that actually downloads and installs the patches. AAC/portal is the brain; AAP is the hands. This keeps AAC in its assessment lane while enabling full automation.

---

## 4. Architecture details

### 4.1 AAC side (per customer environment)
- **`host_facts`** — nightly fact snapshots; `facts->'packages'->'installed'` (Linux: name→version/release/arch) and `facts->'packages'->'installed_raw'` (Windows: DisplayName/DisplayVersion/Publisher).
- **`installed_inventory`** — per-host rows normalized from host_facts (`hostname, package_name, package_version, package_vendor, cpe, os_*, architecture, source`).
- **`manual_product_declarations`** — operator-declared products package_facts can't see (appliance firmware, network-OS versions, agents).
- **`inventory_catalog`** (materialized view) — the normalized, host-count-aggregated catalog: `{vendor, product, version, cpe, host_count, source, first_seen_at, last_seen_at}`. Rebuilt by **`refresh_inventory_catalog.yml`**.
- **AAC Portal Bridge** — read-only API (`/api/aac/v1/inventory_catalog`, `/whoami`, `/healthz`), token-auth'd, cursor-paginated. Holds no state; connects read-only.

### 4.2 Portal side (operator-hosted, multi-tenant)
- **`tenants` / `tenant_tokens`** — one row per customer; the bridge URL + pull tokens (scopes `inventory_pull`, `cve_feed`).
- **`inventory_puller`** — nightly, per tenant: pulls the bridge catalog into **`tenant_inventory_catalog`**.
- **CVE feeds** — NVD + CISA KEV; vendor catalog with CPE keys + advisory references (RHSA/USN/MSRC).
- **`matcher`** — intersects each tenant's inventory with CVE events, by CPE or by vendor+product name; emits the affected products per CVE.
- **Enrollment** — `tenant_enrollments` (buckets), `tenant_vendor_subscriptions` (per-vendor opt-in/out), `framework_enrollments`; plus severity/KEV delivery preferences.
- **`routers/aap.py`** — the seam to trigger AAP jobs from the portal.

### 4.3 Prioritization signal
- **Severity:** CVSS v3 (`CRITICAL/HIGH/MEDIUM/…`) with per-tenant minimum threshold.
- **Exploited-in-the-wild:** CISA KEV membership → always surfaced (pass-through), regardless of CVSS. This is the "importance and security risk" ranking — patch the actively-exploited things first.

---

## 5. Use cases

1. **"What's running in customer X's environment?"** — one query on `tenant_inventory_catalog`: every product, every version, how many hosts. Instant environment software bill-of-materials.
2. **Per-customer patch list.** The matcher output: for each installed product/version, the CVEs that affect it and the fixing advisory (RHSA/USN/MSRC) → the concrete patch set for that customer.
3. **Risk-ranked patch plan.** Sort by CISA-KEV then CVSS → "these 6 actively-exploited items on 40 hosts first, then 22 criticals."
4. **Enroll a customer into a vendor/framework "VCE".** `tenant_enrollments` / `framework_enrollments` scope the feed to what the customer runs and cares about — no noise from products they don't have.
5. **Automated remediation flow.** Portal hands the scoped, prioritized patch set to an AAP job (per host group) → download + install → the next audit confirms closure. Fully automated, evidence-backed.
6. **Version-drift & EOL detection.** `inventory_catalog` shows the same product at N versions across the fleet (e.g. python3 at 5 versions) → standardization and end-of-life targets.
7. **Longitudinal exposure reporting.** Using the compliance history: exposure count and mean-time-to-patch trends per customer over time — a renewal/QBR artifact.

---

## 6. Boundaries & principles

- **Assessment vs execution.** AAC/portal identify and prioritize (assessment/intelligence — in lane). Actual download + install is **AAP-executed**, triggered by the portal. AAC never becomes the runtime patch agent itself.
- **Inventory fidelity.** package_facts covers OS-managed software (RPM/DEB/Windows installed programs). Things outside the package manager (hand-compiled binaries, container-image layers, appliance firmware) are covered by `manual_product_declarations` or dedicated collectors as needed.
- **CVE matching precision.** v1 matches by vendor+product name (via the portal's vendor-alias/classification tables); CPE enrichment on the AAC side improves precision and is a natural follow-up.
- **Multi-tenant isolation.** Each customer's catalog is pulled over its own token into its own `tenant_inventory_catalog`; the portal never co-mingles tenant inventories.

---

## 7. Status — what's live vs to-build

| Piece | Status |
|---|---|
| Compliance audit collects full installed inventory (Linux + Windows) | ✅ live |
| `installed_inventory` + `inventory_catalog` schema | ✅ live (codified in repo) |
| `refresh_inventory_catalog.yml` (host_facts → catalog) | ✅ proven: 33k rows / 98 hosts → 2,808 products |
| AAC Portal Bridge (`/api/aac/v1/inventory_catalog`) | ✅ **deployed to OpenShift**, proven live over HTTPS route |
| Portal inventory_puller (bridge → tenant_inventory_catalog) | ✅ **proven live**: 3,921 rows pulled by the real puller |
| Portal matcher → per-customer patch list | ✅ **proven live**: KEV-first patch list produced |
| CPE enrichment on catalog rows | 🔨 follow-up (matching precision) |
| Available-updates collection (`dnf updateinfo` / `apt`/ Windows) | 🔨 optional: host-truth of applicable patches |
| Full NVD + CISA-KEV feed pull (vs the seed fixture) | 🔨 productionize before customer use |
| Read-only DB user for the bridge (`compliance_reader`) | 🔨 switch from `postgres` before it leaves the lab |
| AAP patch-execution job (portal-triggered) | 🔨 the execution half of the flow |

---

## 8. Appendix — the bridge contract

```
GET /api/aac/v1/inventory_catalog?cursor=<int>&limit=<int>
    Authorization: Bearer <token>      X-Token-Id: <token_id>
 -> { "catalog": [
        { "vendor": "openssl", "product": "openssl", "version": "3.0.7",
          "cpe": null, "host_count": 42, "source": "auto",
          "first_seen_at": "…", "last_seen_at": "…" }, … ],
      "next_cursor": <int|null>, "count": <int> }

GET /api/aac/v1/whoami    -> { token_id, scopes, service, version }
GET /api/aac/v1/healthz   -> { status, version }        (no auth)
```

The portal follows `next_cursor` until `null`, then fully rewrites that tenant's
`tenant_inventory_catalog` — idempotent, safe to re-run nightly.
