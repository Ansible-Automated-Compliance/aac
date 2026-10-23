# Extracting AAP Analytics Data via the API

**Version:** v1.0 · 2026-08-31
**Scope:** Red Hat Ansible Automation Platform 2.6 (also applies to 2.7)
**Purpose:** pull the data behind AAP's dashboards through the API, for loading
into external visualization tools (Grafana, Splunk, Power BI, Tableau, etc.)

**Authors:** Tim Coulter · Claude (Anthropic)

---

## 1 · The three data sources

AAP analytics data lives in three distinct places. Most extraction pipelines
need the first, may want the second, and only multi-cluster estates need the
third.

| Source | What it holds | History? |
|---|---|---|
| **Controller REST API** | Raw job runs, per-host outcomes, host automation counters — the data behind the dashboards | Yes — full job history |
| **Prometheus metrics endpoint** | Instantaneous operational gauges: running jobs, capacity, sessions | No — history comes from your scraper |
| **Automation Analytics (console.redhat.com)** | Red Hat-hosted aggregation across clusters: ROI, job explorer, subscription usage | Yes — if upload is enabled |

---

## 2 · API structure and authentication

Since AAP 2.5, all on-cluster services sit behind the **platform gateway**:

| Service | Base path |
|---|---|
| Platform gateway | `/api/gateway/v1/` |
| **Automation controller** | `/api/controller/v2/` |
| Event-Driven Ansible | `/api/eda/v1/` |
| Automation hub | `/api/galaxy/` |

**Authentication: use OAuth2 bearer tokens, not basic auth.** The gateway does
not reliably pass basic-auth credentials through to the controller — requests
that work in a browser session will 401 from `curl` with `-u user:pass`. Create
a token (UI: *Access Management → Users → Tokens*, or
`POST /api/gateway/v1/tokens/`) and send it on every request:

```bash
AAP=https://<your-gateway-host>
curl -sk -H "Authorization: Bearer $TOKEN" "$AAP/api/controller/v2/ping/"
```

**Pagination and filtering** — every list endpoint supports these, and the
incremental filter is what makes a repeatable extraction pipeline work:

```
?page_size=200            # then follow the "next" link in each response
?order_by=-finished       # sort
?created__gte=2026-08-01T00:00:00Z    # incremental pulls
?status=failed            # field filters
```

The API is self-documenting: open any endpoint in a browser for a browsable
schema, or `GET /api/controller/v2/` for the full index.

---

## 3 · Controller endpoints — the main dataset

### Jobs and execution history

| Endpoint | What it gives you |
|---|---|
| `/api/controller/v2/unified_jobs/` | **Start here.** Every job type — playbook runs, project updates, inventory syncs, workflows — one list with status, timestamps, elapsed |
| `/api/controller/v2/jobs/` | Playbook runs only, full detail per run |
| `/api/controller/v2/jobs/{id}/job_host_summaries/` | **The workhorse for success-rate dashboards** — per-host ok/changed/failed/unreachable counts for a run |
| `/api/controller/v2/jobs/{id}/job_events/` | Task-level events. ⚠️ Enormous on busy clusters — pull per drill-down, never as a bulk feed |
| `/api/controller/v2/workflow_jobs/` | Workflow-level history |
| `/api/controller/v2/workflow_jobs/{id}/workflow_nodes/` | Node-by-node results inside a workflow |

### Hosts and automation coverage

| Endpoint | What it gives you |
|---|---|
| `/api/controller/v2/host_metrics/` | Per host: first automated, last automated, automation count, deletion count. The adoption/licensing view and the basis for ROI math |
| `/api/controller/v2/hosts/` | Current inventory hosts |
| `/api/controller/v2/inventories/` | Inventory shape |

### Dimensions (the "group by" axes)

`/api/controller/v2/job_templates/` · `/projects/` · `/organizations/` ·
`/teams/` · `/users/` · `/labels/` · `/instance_groups/`

### Pre-computed aggregates

| Endpoint | Notes |
|---|---|
| `/api/controller/v2/dashboard/` | The counts behind the dashboard page. Point-in-time only — filtered pulls from `unified_jobs` are usually more useful to an external tool |
| `/api/controller/v2/ping/` | Version, nodes, capacity — useful as a pipeline health check |

---

## 4 · Prometheus metrics endpoint

```
GET /api/controller/v2/metrics/          # Prometheus exposition format
```

Instantaneous gauges: running/pending jobs per node, capacity, active sessions,
license consumption. **No history is kept** — point Prometheus (or any
OpenMetrics scraper) at it on an interval and the history accumulates on your
side. If the target is Grafana, this plus a scrape config is the shortest path
for operational panels; the job data in section 3 feeds the business panels.

---

## 5 · Automation Analytics API (console.redhat.com)

If the cluster uploads analytics data to Red Hat (Settings → *Automation
Analytics*), the cross-cluster aggregation has its own API:

- Base: `https://console.redhat.com/api/tower-analytics/v1/`
- Mirrors the Reports UI: job explorer, host metrics, ROI, subscription usage
- Auth via a console.redhat.com service account
- The report frontend is open source (`redhatinsights/tower-analytics-frontend`
  on GitHub), so the exact API call behind any report is inspectable

This is the only source that aggregates **across multiple AAP clusters** for
free. Single-cluster estates that want everything local can skip it entirely.

## 6 · `metrics-utility` — the offline batch alternative

Where API extraction or Red Hat upload does not fit, `metrics-utility` runs on
the controller node on a cron and builds usage/billing-style reports
(spreadsheet output) from the local database. Red Hat KB article 7127789.

---

## 7 · Recommended pipeline

For "replace the dashboards with our own visualization":

1. **`unified_jobs`** pulled incrementally with `created__gte` since the last
   run — the job fact table
2. **`job_host_summaries`** per new job — the per-host outcome fact table
3. **`host_metrics`** on a daily pull — the adoption dimension
4. **`job_templates` / `organizations` / `projects`** — slowly-changing
   dimensions, refresh daily
5. Land in whatever store the viz tool reads; join on template/org/project ids
6. Optional: Prometheus scraping `/metrics/` for live operational panels

⚠️ Two cautions: `job_events` will hurt you as a bulk feed on any busy cluster;
and tokens expire — build the re-auth into the pipeline rather than discovering
it as a 401 three weeks in.

---

## Appendix — verified against a live cluster

Tested 2026-08-31 against a lab AAP CRC deployment (platform gateway topology,
controller 4.8.6 / AAP 2.7 — endpoint paths identical to 2.6). All calls made
with a gateway-issued OAuth2 bearer token. Output below is sanitized.

| Test | Result |
|---|---|
| `GET /api/controller/v2/ping/` | ✅ version 4.8.6, 1 control node, capacity reported |
| `GET /api/controller/v2/me/` | ✅ authenticated as expected user |
| `GET /api/controller/v2/unified_jobs/?order_by=-finished&page_size=3` | ✅ 3,531 jobs; latest three returned with type, status, finished timestamp |
| `GET /api/controller/v2/jobs/{id}/job_host_summaries/` | ✅ per-host `ok/changed/failed/unreachable` counts returned for the latest job |
| `GET /api/controller/v2/host_metrics/?order_by=-automated_counter` | ✅ 10 hosts with first/last automation dates and run counters (top host: 1,840 runs) |
| `GET /api/controller/v2/dashboard/` | ✅ host/inventory/project totals returned |
| `GET /api/controller/v2/metrics/` | ✅ Prometheus format; `awx_hosts_total`, `awx_instance_info` gauges present |
| `GET /api/controller/v2/unified_jobs/?created__gte=…` | ✅ incremental time filter honored |

Notable during verification: **basic auth to the controller API through the
gateway fails with 401 even with valid credentials** — the bearer-token
requirement in section 2 is load-bearing, not a recommendation.

---

*Prepared with Claude (Anthropic).*
