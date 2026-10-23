> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx3.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# AAC Technical Debt Heatmap

**Version:** v2.0
**Report date:** 2026-08-04
**Environment:** lab-aap (CRC/OpenShift, AAP_HOST), namespace `aac`
**Data source:** `compliance` database — `technical_debt_items`, `technical_debt_summary`, `remediation_rates`
**Authors:** Tim Coulter; Claude (Anthropic)

---

## Colour key

The DOCX and PDF renderings band every table by criticality using the AAC house palette.
Markdown carries the same bands as symbols so the text version conveys identical priority.

| Band | Level | Meaning | Palette |
|---|---|---|---|
| 🔴 | **Critical** | Immediate attention / severely stale | fill `#FAD7D7`, accent `#C0392B` |
| 🟠 | **High** | Significant exposure / stale | fill `#FDF2E0`, accent `#F39C12` |
| 🔵 | **Medium** | Monitor | fill `#E8F0F7`, accent `#1A5C8A` |
| 🟢 | **Low / current** | Acceptable or freshly assessed | fill `#E3F5E9`, accent `#27AE60` |

Table headers are navy `#1C2B3A` with white text.

---

## 1. Read this first — scope and freshness

This report is generated from live platform data. Two caveats determine how the numbers
should be read, and both are stated up front rather than buried.

**Only one of seven hosts is currently assessed.** The remaining six carry data between five
weeks and 3.5 months old, and three of them are container-ID hostnames that may no longer
exist. The portfolio total is therefore **not** a statement of present-day posture — it is the
sum of the most recent assessment for each host, whenever that happened to be.

| | Host | Open items | Effort (h) | Last assessed | Freshness |
|---|---|---:|---:|---|---|
| 🟢 | `localhost` | 116 | 1,926.0 | **2026-08-04** | current |
| 🔴 | `unknown` | 92 | 435.0 | 2026-04-22 | 3.5 months stale |
| 🔴 | `676354893a37` | 64 | 130.0 | 2026-04-20 | 3+ months stale, ephemeral hostname |
| 🔴 | `0d6785656747` | 64 | 130.0 | 2026-04-20 | 3+ months stale, ephemeral hostname |
| 🔴 | `7b698240fb47` | 64 | 130.0 | 2026-04-20 | 3+ months stale, ephemeral hostname |
| 🟠 | `aap-controller` | 2 | 2.0 | 2026-06-30 | 5 weeks stale |
| 🟠 | `aap-postgres` | 2 | 2.0 | 2026-06-30 | 5 weeks stale |

**Two tables measure different things.** `technical_debt_items` is a current-state table of open
findings (upserted, with `first_seen` / `last_seen` / `status`). `technical_debt_summary` is a
point-in-time snapshot written per assessment run. This report uses **`technical_debt_items`
filtered to `status = 'open'`**, because that is what the Grafana *Technical Debt Heatmap*
dashboard queries — so the document and the dashboard agree. Totals derived from the summary
table will differ and are not comparable.

---

## 2. Headline — the debt score rose because measurement improved

`localhost`, the one freshly assessed host, moved as follows:

| Metric | 2026-07-28 | 2026-08-04 | Change |
|---|---:|---:|---:|
| Debt items (summary) | 8 | 11 | +3 |
| Effort hours | 96.0 | 148.0 | +52.0 |
| Debt score | 67.50 | 115.50 | **+48.00** |

**This increase is a measurement improvement, not a posture regression.** Nothing on the host
got worse. On 2026-08-04 a set of defects was corrected in the policy library that had been
causing benchmarks to report compliance they had never measured:

- Every registered CIS framework key returned an empty result (`{}`) through the Generic
  Framework Assessment path; assessments recorded empty rows while reporting success.
- CIS Amazon Linux 2023 imported a package prefix that did not exist, so it reported **100%
  compliant on any input**, including no input at all.
- Seven benchmarks failed *open* on missing facts, reporting 69–99% compliance for assessments
  that evaluated nothing.

Those paths now fail closed. Debt that was previously invisible is now counted, so the score
rose. **A falling debt score achieved by not measuring is worse than a rising one that is
honest.** Expect a further one-time rise as the remaining six hosts are re-assessed.

---

## 3. Portfolio totals (open items)

| | Value |
|---|---:|
| Open debt items | **404** |
| Remediation effort | **2,755.0 hours** |
| Estimated cost | **$607,760** |
| Blended rate | $220.60 / hour |

Cost is computed per item from `remediation_rates` via the standard `LATERAL JOIN` on
`debt_category` — no rate is hardcoded.

---

## 4. Heatmap — framework × domain

Cost in USD. Darker weight = larger exposure.

| | Framework | Domain | Items | Hours | Cost |
|---|---|---|---:|---:|---:|
| 🔴 | Digital Sovereignty | sovereignty | 115 | 1,992.0 | **$448,200** |
| 🟠 | CIS RHEL 9 | compliance | 153 | 330.0 | $64,350 |
| 🟠 | NERC-CIP | critical_infrastructure | 8 | 120.0 | $34,200 |
| 🟠 | CIS RHEL 9 | security | 91 | 168.5 | $29,488 |
| 🔵 | AMI / NIST IR 7628 | critical_infrastructure | 7 | 60.0 | $17,100 |
| 🔵 | NCSC CAF | security | 11 | 66.0 | $11,550 |
| 🟢 | NCSC CAF | compliance | 2 | 8.0 | $1,560 |
| 🟢 | CIS RHEL 9 | operational | 17 | 10.5 | $1,313 |
| 🔴 | **Total** | | **404** | **2,755.0** | **$607,760** |

**Digital Sovereignty is 74% of total exposure** on 28% of the items — 1,992 hours against a
$225/hour specialist rate. It is the single decision that dominates the budget: a scope
judgement about the sovereignty programme, not an accumulation of small fixes.

**CIS RHEL 9 is the volume driver** — 261 items (65% of all findings) but 18% of cost, at 1.95
hours per item. This is the bulk-remediable tier, and the most automatable.

**OT carries a rate premium.** NERC-CIP and AMI together are 15 items / 180 hours, but at
$285/hour they cost $51,300 — more than the 91-item CIS security tier. OT effort is roughly
2.3× the cost of equivalent operational effort.

---

## 5. Severity distribution

| | Severity | Items | Hours | Share of effort |
|---|---|---:|---:|---:|
| 🔴 | CRITICAL | 49 | 644.0 | 23.4% |
| 🟠 | HIGH | 301 | 1,794.5 | 65.1% |
| 🔵 | MEDIUM | 46 | 312.5 | 11.3% |
| 🟢 | LOW | 8 | 4.0 | 0.1% |

CRITICAL averages 13.1 hours per item against HIGH's 6.0 — the critical tier is not just more
urgent, it is individually more expensive to close.

---

## 6. Rate card

From `remediation_rates` (tenant `default`, effective 2024-01-01). Domain-specific rates replaced
a flat $185/hour, which materially understated OT work.

| | Domain | Rate | Rationale |
|---|---|---:|---|
| 🔴 | critical_infrastructure | $285 | OT / ICS / SCADA specialist |
| 🟠 | sovereignty | $225 | Privacy / legal engineer |
| 🟠 | compliance | $195 | GRC specialist |
| 🔵 | security | $175 | General security engineer |
| 🔵 | technology_lifecycle | $150 | IT asset management |
| 🟢 | operational | $125 | SysAdmin / DevOps |

---

## 7. Budget comparison — no data

`remediation_budgets` contains **0 rows**. The OT/IT budget-separation capability exists in
schema, and the domain groupings are defined, but no budget figures have been loaded. Any
budget-versus-debt or burn-down analysis is therefore unavailable in this report rather than
estimated. Populating that table is a prerequisite for funding-gap reporting.

---

## 8. Recommended sequence

1. 🔴 **Re-assess the six stale hosts.** The portfolio total mixes one current host with six
   historical ones. Until they are re-run against the corrected policy library, the figures
   above understate real debt — the same false-compliance defects that hid 52 hours on
   `localhost` were active during those assessments. This is the highest-value next action and
   it changes every number in this report.
2. 🟠 **Retire the ephemeral hostnames.** `0d6785656747`, `676354893a37` and `7b698240fb47` are
   container IDs. If those workloads are gone, their 192 hours are phantom debt inflating the
   total; if they still exist, they need stable identifiers.
3. 🟠 **Take a scope decision on Digital Sovereignty.** At $448,200 it is 74% of exposure. This
   warrants an explicit in-scope / deferred call rather than being carried as backlog.
4. 🔵 **Automate the CIS RHEL 9 tier.** 261 items at ~1.95 hours each is the best candidate for
   bulk remediation via existing Ansible roles.
5. 🟢 **Load `remediation_budgets`** so funding gaps can be reported rather than inferred.

---

## 9. Reproducing these figures

```bash
# On the RHEL host (AAP_HOST)
export PATH="$HOME/.crc/bin/oc:$PATH"
P="oc -n aac exec deploy/compliance-db -- psql -U postgres -d compliance"

# Portfolio total (open items, rate-joined) — matches the Grafana heatmap
$P -c "SELECT count(*) items, round(sum(i.effort_hours),1) hrs,
       round(sum(i.effort_hours*r.hourly_rate_usd),0) cost_usd
FROM technical_debt_items i
LEFT JOIN LATERAL (SELECT hourly_rate_usd FROM remediation_rates
  WHERE tenant_id='default' AND debt_category=i.debt_category
    AND effective_from<=CURRENT_DATE ORDER BY effective_from DESC LIMIT 1) r ON TRUE
WHERE i.status='open';"

# Per-host freshness — always check before quoting the total
$P -c "SELECT hostname, count(*) items, round(sum(effort_hours),1) hrs,
       max(last_seen)::date last_seen FROM technical_debt_items
WHERE status='open' GROUP BY 1 ORDER BY 3 DESC;"
```

Refresh the data by launching AAP job template **142 — AAC - Technical Debt Assessment**
(the run behind this report is job 1900). The Grafana dashboard is
*Technical Debt Heatmap* at `http://grafana-aac.apps.<cluster-domain>`.

---

## Document control

| | |
|---|---|
| Version | v2.0 — adds colour-coded criticality banding |
| Date | 2026-08-04 |
| Environment | lab-aap CRC (AAP_HOST), namespace `aac` |
| Source job | AAP job 1900 (template 142) |
| Data scope | `technical_debt_items` where `status = 'open'` |
| Supersedes | v1.0 (2026-08-04, monochrome). `aac_technical_debt_budget.docx` (2026-04-19) covered budget only |
| Authors | Tim Coulter; Claude (Anthropic) |

*Figures reflect the lab environment and are illustrative of method, not a customer posture
statement.*
