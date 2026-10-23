# Enabling Local (On-Prem) Automation Analytics — AAP 2.7

**Version:** v1.0
**Applies to:** Ansible Automation Platform **2.7** (operator `aap-operator.v2.7.x`, controller 4.8.x)
**Audience:** AAP platform operators who want automation ROI / reporting **without** sending data to Red Hat's cloud (`console.redhat.com`).
**Authors:** Tim Coulter; Claude (Anthropic) — AI pair.

---

## 1. The three "analytics" surfaces (know which you're on)

AAP 2.7 has **three** distinct things people call "analytics." Two are fully on-prem; one is cloud.

| Surface | Backend | Cloud round-trip? | What it gives you |
|---|---|---|---|
| **Automation Dashboard** (this doc) | `automationmetricsservice` (in-cluster) | **No** | In-UI ROI / **Automation Calculator**, template savings, subscription cost basis |
| **metrics-utility** | controller CLI + CronJobs | **No** | CCSP **consumption/usage report files** (xlsx) on a PVC |
| **Automation Analytics** (legacy) | controller `/api/controller/v2/analytics/` → `console.redhat.com` | **Yes** | The old cloud dashboards + Automation Calculator |

> **Key point:** the legacy **Analytics → Automation Calculator** page proxies to the cloud and will show
> `missing user for Automation Analytics` unless you configure Red Hat cloud credentials. That is **not**
> the on-prem calculator. The on-prem ROI lives in the new **Automation Dashboard** (Section 3–5).

---

## 2. Prerequisites

- **AAP 2.7** (the Automation Dashboard is a 2.7 feature). Verify:
  ```bash
  oc get csv -n <aap-namespace> | grep -i ansible-automation-platform   # operator .v2.7.x
  ```
- **Metrics service must be enabled** (it is by default in a standard 2.7 deploy). The installer/operator
  will fail preflight if you enable the dashboard without it. Verify the pods exist:
  ```bash
  oc get pods -n <aap-namespace> | grep automationmetricsservice
  ```

---

## 3. Enable the on-prem Automation Dashboard

The gate is the platform feature flag **`FEATURE_DASHBOARD_COLLECTION_ENABLED`** (default **false**).

### 3a. OpenShift / operator deployment (this lab)

Patch the top-level `AnsibleAutomationPlatform` CR's `feature_flags` map:

```bash
oc patch ansibleautomationplatform <cr-name> -n <aap-namespace> --type merge \
  -p '{"spec":{"feature_flags":{"FEATURE_DASHBOARD_COLLECTION_ENABLED":true}}}'
```

The operator reconciles and **rolls the metrics service + gateway** (~3 minutes). This is a brief,
rolling change — no full outage, but the gateway/metrics pods restart.

### 3b. RPM / containerized installer

Set in the installer inventory and re-run the installer:

```ini
[all:vars]
FEATURE_DASHBOARD_COLLECTION_ENABLED=true
```

> Dashboard collection **requires** the metrics service; the installer fails preflight if the dashboard is
> enabled without it, and dashboard settings are ignored if the metrics service is not configured.

---

## 4. Verify the collection is on and computing (API)

Use a gateway bearer token (`Authorization: Bearer <token>`), or `-u admin:<password>`.

```bash
GW=https://<gateway-host>

# Flag is on (metrics service + gateway both report it)
curl -sk -H "Authorization: Bearer $T" "$GW/api/metrics/v1/feature_flags_state/" | grep DASHBOARD

# Collection is enabled and the initial collection completed
curl -sk -H "Authorization: Bearer $T" "$GW/api/metrics/v1/dashboard_reports/collection_status/"
#   -> {"enabled": true, "initial_collection_status": "completed", "next_run": "..."}

# The ROI report computes on-prem (valid periods: last_7/14/30/60/90_days)
curl -sk -H "Authorization: Bearer $T" \
  "$GW/api/metrics/v1/dashboard_reports/report/?period=last_30_days"
#   -> per-template: runs, manual-vs-automation minutes, elapsed, savings

# Cost basis behind the calculator
curl -sk -H "Authorization: Bearer $T" "$GW/api/metrics/v1/dashboard_reports/subscription_costs/"
#   -> monthly_subscription_cost, engineer_avg_hourly_rate
```

---

## 5. Access it in the UI

1. **Hard-refresh the browser** (Ctrl/Cmd+Shift+R) — the flag and gateway just changed; the SPA reads
   feature flags at load.
2. Open the **Automation Dashboard** navigation item — **not** the legacy **Analytics → Automation
   Calculator**.
3. The dashboard shows automation ROI, template savings, and the calculator, all from local data.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| **"missing user for Automation Analytics"** on the Automation Calculator | You're on the **legacy cloud** Analytics view (controller `/analytics/` proxy). It wants `REDHAT_USERNAME/PASSWORD` or `SUBSCRIPTIONS_CLIENT_ID/SECRET`. | Ignore it — use the new **Automation Dashboard** instead. (Only set those creds if you actually want the *cloud* Automation Analytics.) |
| `remote:false` in that error | It only means "local **config** error" (a missing setting), **not** "local analytics." | Not a signal that on-prem is active. |
| Dashboard nav missing after enabling | Browser cached old feature flags | Hard-refresh; confirm the gateway pod restarted after the CR patch. |
| `collection_status.enabled=false` | Flag not propagated yet | Wait for the operator to roll the metrics service/gateway; re-check `feature_flags_state`. |
| Preflight/operator ignores dashboard settings | Metrics service not enabled | Enable the metrics service first. |

---

## 7. Bonus: the other on-prem path — `metrics-utility` (consumption reports)

For CCSP **consumption/usage report files** (xlsx) with no cloud, enable `metrics-utility` on the controller.
OpenShift operator:

```bash
# ConfigMap with directory (local) target — key fields
#   METRICS_UTILITY_SHIP_TARGET=directory
#   METRICS_UTILITY_SHIP_PATH=/metrics-utility
#   METRICS_UTILITY_REPORT_TYPE=CCSP
oc patch automationcontroller <name> -n <ns> --type merge -p '{"spec":{
  "metrics_utility_enabled": true,
  "metrics_utility_console_enabled": false,
  "metrics_utility_configmap": "metrics-utility-config",
  "metrics_utility_cronjob_gather_schedule": "@daily",
  "metrics_utility_cronjob_report_schedule": "@monthly"}}'
```

- `metrics_utility_console_enabled: false` keeps it **off the cloud**.
- The operator creates a PVC + gather (`@daily`) and report (`@monthly`) CronJobs.
- Reports land at `<PVC>/reports/<YYYY>/<MM>/CCSP-<YYYY-MM>.xlsx`.
- **CRC/hostpath gotcha:** the gather pod runs non-root and may hit `PermissionError` on the PVC. Fix the
  backing directory ownership/permissions on the node (e.g. `chmod 0777` the hostpath dir via
  `oc debug node/<node>`).

---

## 8. What still needs the cloud

Only the **cloud Automation Analytics** (uploading data to `console.redhat.com` and pulling the hosted
dashboards) requires a Red Hat subscription credential (`REDHAT_USERNAME/PASSWORD` or a service account
`SUBSCRIPTIONS_CLIENT_ID/SECRET`). Everything in Sections 3–7 is fully on-prem.
