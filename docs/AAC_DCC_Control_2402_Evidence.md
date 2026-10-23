# AAC Evidence for UK MoD DCC Control 2402 (Vulnerability Management)

**Version:** v1.1
**Date:** 2026-10-06
**Authors:** Tim Coulter (Red Hat) with Claude (Anthropic)
**Audience:** Defence suppliers preparing for DCC certification; AAC sellers and architects

---

## The certification context

The UK MoD **Defence Cyber Certification (DCC)** scheme (MOD + IASME) certifies
defence suppliers against **DEF STAN 05-138 Issue 4** (14 May 2024) at four Cyber
Risk Profiles — Level 0 "Basic" (3 controls) through Level 3 "Expert" (144
controls). All MOD supply-chain suppliers are expected to hold **DCC Level 0 by
31 December 2026**; contracts risk-assessed at higher CRP levels require the
matching certification. Certification runs three years with annual attestation.

**Control 2402 (Vulnerability management, Levels 1–3)** requires an approved
vulnerability and patch management process that identifies, reports, and
remediates vulnerabilities by:

1. performing **vulnerability scans monthly** and during major system changes,
2. implementing vendor patches or fixes **prioritised using CVSS v3 scoring**, and
3. developing a **Risk Treatment Plan** for identified vulnerabilities —
   retaining evidence of what was found, what was done, and why any exception
   was accepted.

The practical tension every supplier faces: a CVE notice is a compliance event
*and* an engineering decision. A noisy alert pipeline (an alert firing every
minute under a short suppression window) satisfies neither — the certification
asks for **prioritised, evidenced, risk-based treatment**, not alert volume.

## What AAC provides, control element by element

| 2402 element | AAC capability (shipped) | Evidence artifact |
|---|---|---|
| Documented, approved process | DCC attestation module (`dcc.main`, all 148 Issue 4 controls) — merged in the AAC policy library (rego #166). AAC deployment wiring (submodule pin + OPA loader key) is **in review**; until it lands, the module evaluates in any OPA loaded with the library, and persistence to the compliance database is pending | OPA `compliance_report` (database history once wiring lands) |
| Identify vulnerabilities | Portal CVE pipeline: NVD + CISA KEV feed ingest, matched to the supplier's own estate two ways — **CPE** against the tenant inventory catalog, and **PURL against OSV.dev** for application SBOM components (CycloneDX) — portal #160/#161, on main | Per-tenant match rows (`tenant_cve_matches`), one per (tenant, CVE) |
| CVSS v3 prioritisation | CVSS v3 score → severity ranking is native to the feed pipeline; per-tenant severity thresholds, with **CISA KEV pass-through** so actively-exploited CVEs cannot be filtered out by a threshold | Tenant filter preferences + match rows carrying severity and KEV state |
| Risk Treatment Plan | Every match row preserves `delivered_at` / `acknowledged_at` / `suppressed_at` — suppression quiets the alert but **never erases the record** (waived-never-hidden). Accepted exceptions are visible to an assessor, with who/when | Match-row audit columns; waiver register |
| Remediation timeliness | **Exposure-window KPI**: mean time from CVE match to proven closure (portal #196, on main) | KPI series; per-CVE drill one-pager (cryptographically signed artifact, portal #185) |
| Evidence retention | All assessment results land in the compliance PostgreSQL history; the per-CVE drill artifact is signed for integrity | `compliance_results` history; signed drill artifacts |

Adjacent Issue 4 controls the same pipeline evidences:

- **2405 (Patch management)** — best-practice-timeline tracking is the exposure-window KPI read against policy; emergency out-of-band events are visible as KEV-flagged matches.
- **3110 (Monitor alerts/advisories and take action)** and **3203 (Indicators of compromise)** — the feed ingest *is* the advisory monitor; acknowledgement state is the "action taken" trail.
- **1301 (Automated asset inventory)** — the tenant inventory catalog and SBOM component store that the matcher runs against.

## Boundaries — what AAC does not do

- AAC is **not a certification body**; DCC certification is assessed by IASME-licensed assessors. AAC produces the operational evidence an assessment consumes.
- AAC **does not run vulnerability scans**. The monthly-scan obligation is met by the supplier's scanner; AAC ingests scanner output (Checkov and Trivy JSON importers today; SARIF is produced for export, not yet accepted for import) and independently matches the estate against the public feeds — continuous known-CVE matching that complements, not replaces, the scheduled scan.
- The DCC module evaluates **attestations** for the 148 controls; it deepens into measured evidence only where AAC collects the underlying data (the vulnerability/patching/monitoring slice above). Attestation for the remaining controls is the supplier's claim, and the module reports it as such.

## Running it

- DCC profile evaluation (once the policy library is loaded into your OPA deployment): `POST /v1/data/dcc/main/compliance_report` with `{"dcc": {"target_level": <0-3>, "controls": {"<id>": true, ...}}}` — fail-closed: unattested, malformed, or unknown entries are violations; an absent level evaluates the strictest profile.
- CVE evidence: portal feed pipeline (NVD, CISA KEV, OSV) runs on schedule; per-tenant matches, suppression audit trail, and the exposure-window KPI are available through the portal API.

---

*Co-authored by Claude (Anthropic). Sources: DEF STAN 05-138 Issue 4 (UK MoD, 14 May 2024); IASME DCC scheme guidance; CISA KEV catalog; NIST NVD; OSV.dev.*
