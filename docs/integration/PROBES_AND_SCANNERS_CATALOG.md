# Probes and scanners — what AAC integrates today, and what it can

**Version:** v0.1
**Date:** 2026-10-18
**Authors:** Tim Coulter · Claude (Anthropic)
**Purpose:** one list of the probes, scanners, agents and platforms an estate already runs, with
whether AAC consumes or drives each one today and what it would take to add it, so the complete
state of an estate can be evaluated in one program.

---

## 1. How AAC takes in a result today

AAC has five generic intake paths. Almost every tool below maps onto one of them, which is why
most "can integrate" answers are days, not weeks.

| Path | Code | Takes | Produces |
|---|---|---|---|
| **Native facts** | `aac_facts_collector`, `aac.host_facts`, `aac.m365`, vendor collections in the EEs | Ansible modules against hosts, cloud APIs, Graph | `opa_input` → OPA → `compliance_results` |
| **ARF / XCCDF ingest** | `aac_oscap_scan` + `aac_oscap_ingest`, `openscap_assess.yml`, `scripts/openscap_xccdf_parse.py` | Any ARF 1.1 or XCCDF result file (oscap, CIS-CAT Pro, DISA SCC, Satellite's OpenSCAP reports) | `compliance_results` rows, waiver-aware |
| **HDF ingest** | `hdf_ingest.yml`, `scripts/hdf_parse.py` | MITRE Heimdall Data Format: InSpec natively, and 30+ scanners through `saf convert` (Nessus, Prowler, Snyk, Burp, ZAP, Twistlock, OpenSCAP, …) | same |
| **Scanner JSON ingest** | `ingest_scanner_findings.yml`, `scripts/ingest_scanner_findings.py` | Checkov and Trivy JSON (IaC, pre-apply) | same, on the same timeline as runtime verdicts |
| **Engine in the EE** | `trivy_assess_artifact.yml`, `kubescape_assess.yml`, `ansible_lockdown_audit.yml` (goss) | Runs the scanner CLI inside `aac-policy-tools-ee`, parses its JSON | same |

Plus the reverse direction: `export_oscal_assessment.yml`, `export_sarif_assessment.yml`,
`export_hdf.yml` push AAC findings out to OSCAL, SARIF (GitHub code scanning, SIEM) and Heimdall.
Signals and tickets: ServiceNow, Jira, Nagios/Icinga, Prometheus, BigPanda, xMatters, PagerDuty
(`integrations/`, `notify_*` playbooks). Runtime authorisation: EnforceAuth bridge.

**Rule for every row below:** AAC does not re-implement a scanner. It takes the scanner's own
result (the vendor's view), keeps the control mapping, and stores it as evidence next to its own
assessments. "Can integrate" therefore means "the tool has an export AAC can parse and a mapping
to controls we can keep", not "AAC can do what the tool does".

Legend for the **Today** column: **Yes** = shipped path; **Partial** = analysis or demo exists,
no shipped intake; **No** = nothing in the tree. **Effort** is for a first working intake on the
lab, including a parser test and a stored row.

## 2. Host configuration and benchmark scanners

| Tool | Measures | Today | Path to integrate | Effort |
|---|---|---|---|---|
| OpenSCAP (`oscap`, SSG) | XCCDF/OVAL benchmark results per host | **Yes** — scan and ingest roles, `openscap_assess.yml` | — | — |
| CIS-CAT Pro Assessor | CIS benchmark results (ARF, XCCDF, JSON, CSV) | **Yes** for its ARF output through `aac_oscap_ingest` (documented in the role README) | Point the ingest at the ARF; verify the JSON report format for richer metadata | days |
| DISA SCC (SCAP Compliance Checker) | STIG results as ARF/XCCDF | Partial — ARF path exists, SCC output untested | Ingest the ARF; map `V-`/`SV-` ids to the STIG policies already in the library | days |
| Evaluate-STIG (NAVSEA) | STIG checklists (CKL/CKLB) | No | CKL is XML; write a `ckl_parse.py` next to the XCCDF parser, same control mapping | 1 week |
| STIG Viewer / STIG Manager | Checklist store and API (`.ckl`, XCCDF import/export) | No | Export XCCDF from STIG Manager → ARF/XCCDF ingest; later push AAC results back as CKL | days for intake |
| Chef InSpec | Profile results (HDF JSON) | **Yes** — `hdf_ingest.yml` | — | — |
| goss (Ansible-Lockdown audits) | Audit results per host (JSON) | **Yes** — `ansible_lockdown_audit.yml` | — | — |
| Lynis | Host hardening audit (report `.dat`, key=value) | No | Small parser; findings are heuristics, store as a `lynis` framework with no control mapping | days |
| osquery / Fleet | SQL over host state; scheduled query results (JSON logs, Fleet API) | No | Two options: run osquery queries as a fact collector (facts path), or ingest Fleet API results | 1 week |
| Wazuh | SCA (CIS checks), FIM, vulnerability detection; REST API and JSON alerts | No | Pull `/sca/{agent}/checks` from the API; map CIS ids to the library | 1 week |
| Red Hat Insights Compliance | OpenSCAP results uploaded by `insights-client`; console CSV/JSON export, REST API | No | The results are OpenSCAP: either export from the console API and ingest as XCCDF, or run oscap locally and skip Insights. Also a candidate **source of truth comparison**: AAC's own CIS vs Insights' | days |
| Red Hat Satellite / Foreman | Host inventory, content, errata, OpenSCAP reports (API) | Partial — `aac-satellite-ee`, inventory plugin, `satellite_content_precheck.yml` (will the fix install?) | Pull OpenSCAP reports from Satellite's API → XCCDF ingest; errata → the patch lifecycle | days to 1 week |
| Microsoft Defender for Endpoint / Vulnerability Management | Device exposure, misconfig, TVM (Graph security API) | Partial — `aac.m365` covers Defender *for Office 365* and Intune settings, not endpoint TVM | Graph `/security/…` and `/deviceManagement/…` facts module in `aac.m365` | 1–2 weeks |
| Intune / SCCM | Device compliance policies | **Yes** for Intune configuration (`m365_intune_facts`); SCCM no | SCCM: SQL views or AdminService REST → facts | 1 week |
| WSUS | Patch state on Windows | No | `win_updates` facts already possible via `ansible.windows`; WSUS API optional | days |
| Tanium (Comply, Interact) | Endpoint state and CIS findings; Connect exports, API Gateway | Partial — a governed-drift comparison demo, no intake | Tanium Connect → JSON/CSV drop or SIEM, or API Gateway; map Comply CIS ids | 1–2 weeks |
| Puppet Comply / CEM | CIS assessment on Puppet-managed nodes | No | Comply exports CSV/JSON; parse like CIS-CAT | 1 week |
| ClamAV | Malware presence (log/JSON) | Partial — referenced in PCI facts | Fact collector: last scan time, signatures age, findings | days |

## 3. Vulnerability management and endpoint security

| Tool | Measures | Today | Path to integrate | Effort |
|---|---|---|---|---|
| Nessus / Tenable.io / Tenable.sc | Vulnerabilities and compliance audits (`.nessus` XML, API) | Partial — Nessus through HDF (`saf convert nessus2hdf`); Tenable mentioned in docs only | `.nessus` → HDF → ingest today; direct Tenable.io API for vulnerability-to-host feed into the patch lifecycle (`cve_cache`) | days (HDF), 1 week (API) |
| Qualys VMDR / Policy Compliance | Vulns and PC findings (API, XML/CSV) | No | Policy Compliance posture API → CIS mapping; VMDR → `cve_cache` | 1–2 weeks |
| Rapid7 InsightVM / Nexpose | Vulns, policy assessment (API) | No | Same pattern as Qualys | 1–2 weeks |
| CrowdStrike Falcon (Spotlight, Exposure) | Vulns, sensor state (API) | No (Rego mentions only) | Spotlight API → `cve_cache`; sensor-present → a control | 1 week |
| SentinelOne | Agent state, threats (API) | No | Agent-present and policy facts | 1 week |
| Greenbone / OpenVAS | Vuln scans (GMP XML) | No | XML → HDF-like parse or direct `cve_cache` | 1 week |
| Nmap | Open ports and services (XML) | Partial — PCI facts reference it | Run from the EE, parse XML → network facts (`host_facts` os_family network) | days |
| Snyk | Code and container vulns (SARIF, JSON) | Partial — via HDF | SARIF intake would also cover it (see section 5) | days |

## 4. Cloud posture, Kubernetes and containers

| Tool | Measures | Today | Path to integrate | Effort |
|---|---|---|---|---|
| AWS native APIs | Account and resource configuration | **Yes** — `cis_aws` through `amazon.aws` in the EEs; `integrations/aws_ssm` | — | — |
| AWS Security Hub / Config / Inspector / GuardDuty | Findings in ASFF; Config rule compliance; Inspector CVEs | No | ASFF is JSON with a control id per finding: one parser covers all four; Config compliance maps to CIS AWS | 1 week |
| Azure Policy / Defender for Cloud | Policy compliance states; recommendations and secure score (Resource Graph, REST) | No (Rego mentions) | Resource Graph query → facts; Defender recommendations → findings with built-in CIS/NIST mapping | 1 week |
| GCP Security Command Center / OS Config | Findings; OS patch and config compliance | No | SCC findings API; OS Config compliance reports | 1 week |
| Terraform providers (any) | Resource state via the provider protocol | No — researched (`AAP_TERRAFORM_PROVIDERS_RESEARCH.md`), planned (`AAC_TERRAFORM_REPLACEMENT_PLAN.md`) | Route B read-only | weeks |
| OpenShift Compliance Operator | ComplianceCheckResults (CRs) | **Yes** — `collate_ocp_nerc_cip.yml` for the NERC-CIP profile | Generalise the collator to any profile (`ocp4-cis`, `ocp4-stig`) | days |
| Red Hat Advanced Cluster Security | Compliance (CO-driven) and policy violations; CSV evidence export, API | Partial — integration analysis for NERC-CIP; CO path shipped | RHACS v2 compliance scan results API → findings; violations API → runtime posture | 1 week |
| Kubescape | K8s misconfig against regolibrary | **Yes** — `kubescape_assess.yml` | — | — |
| kube-bench | CIS Kubernetes benchmark (JSON) | No | JSON parser, maps directly to `cis_kubernetes` ids | days |
| Trivy | Images, IaC, SBOM, K8s misconfig (JSON, SARIF) | **Yes** — `trivy_assess_artifact.yml`, scanner JSON ingest, weekly CI scan | — | — |
| Falco | Runtime syscall events (JSON) | No (one doc mention) | EDA source: Falco JSON over webhook → rulebook → store as runtime findings; activities, not state, so keep it separate from assessment | 1 week |
| Kyverno / Gatekeeper | Admission policy reports (`PolicyReport` CRs) | No (Rego comparisons only) | `kubernetes.core` reads PolicyReport CRs → findings | days |
| Prisma Cloud / Wiz / Lacework / Aqua | CSPM/CNAPP findings (API) | No (Rego mentions) | Each has a findings API with framework tags; one parser per vendor | 1–2 weeks each |

## 5. Code, IaC and supply chain

| Tool | Measures | Today | Path to integrate | Effort |
|---|---|---|---|---|
| Checkov | IaC misconfig (JSON, SARIF) | **Yes** — scanner JSON ingest | — | — |
| KICS, tfsec, Semgrep, CodeQL, SonarQube, Snyk Code | Code and IaC findings | Partial — AAC *exports* SARIF; KICS named in the mapper | A generic **SARIF ingest** (the mirror of `export_sarif_assessment.yml`) covers all of them at once | 1 week, once |
| GitHub code scanning / Dependabot | Alerts (REST API, SARIF) | Partial — Dependabot runs on AAC itself | GitHub API alerts → findings per repository | days |
| Yor | IaC resource tagging provenance | **Yes** — `scripts/yor_provenance.py` | — | — |
| Conftest / OPA on CI artefacts | Policy on any structured file | **Yes** by construction (same OPA) | — | — |
| Sigstore / SBOM (SPDX, CycloneDX) | Artefact provenance and components | No | SBOM JSON → components facts; Trivy already emits SBOM | 1 week |

## 6. Network, OT and devices

| Tool | Measures | Today | Path to integrate | Effort |
|---|---|---|---|---|
| Network and storage device REST facts | Device configuration | **Yes** — `aac_gather_network_facts.yml` (simulators or real endpoints), pfSense and VyOS CIS assessments | Extend `device_endpoints` per vendor | days per vendor |
| Vendor collections (Cisco, Juniper, Arista, Fortinet, Palo Alto, F5) | Running configuration | No (none in the EEs today) | Add the certified collection to an EE; facts modules → OPA (STIG network policies exist in the library) | 1 week per vendor |
| NetBox / ServiceNow CMDB | Intended inventory | **Yes** for ServiceNow (change records, notifications, CMDB-vs-Ansible demo); NetBox no | NetBox API as inventory source and as the "expected estate" for the continuity check (#831) | days |
| IEC 62443 / AMI head-end, LwM2M devices | Device state | **Yes** — AMI simulators, OT policies; GEISA demo moved to aac-demos | Real head-end APIs replace simulators | per vendor |

## 7. Observability, SIEM and ticketing (signals out, and sometimes facts in)

| Tool | Today | Path to integrate | Effort |
|---|---|---|---|
| Prometheus, Grafana | **Yes** — exporter and dashboards | — | — |
| Nagios / Icinga, BigPanda, xMatters, PagerDuty | **Yes** — check plugin, passive sender, notification playbooks | — | — |
| ServiceNow, Jira | **Yes** — change records, violation tickets, approvals | — | — |
| Splunk, Elastic, Datadog, Dynatrace | Partial — in the discovery checklist; SARIF/JSON out | Push `compliance_results` deltas via HEC / bulk API; or ingest their alert feeds as runtime signals through EDA | days (out), 1 week (in) |
| Zabbix, Checkmk | No | Same pattern as Nagios | days |

## 8. What "complete state of the estate" needs beyond tools

1. **An expected-inventory source** (CMDB, NetBox, cloud account enumeration) so AAC can say what
   *should* exist. The estate continuity check (#831) is the start; the gap is a declared source of
   truth per environment.
2. **One identity for a host across tools.** Insights, Satellite, Tanium, Defender and AAC each key
   a host differently. A `host_identity` map (hostname, FQDN, cloud instance id, agent ids) in
   `host_facts` is the prerequisite for merging their findings.
3. **A generic SARIF ingest and an ASFF ingest.** Together with the existing ARF and HDF paths they
   cover most of sections 3 to 5 without per-vendor parsers.
4. **Freshness.** Every ingested result carries the scanner's own timestamp; assessment reports must
   show "as of" per source, or a merged view misleads.

## 9. Recommended order

| Order | Item | Why first |
|---|---|---|
| 1 | Generic SARIF ingest | One parser, a dozen tools, mirrors an exporter that already exists |
| 2 | AWS Security Hub ASFF ingest | One parser covers Security Hub, Config, Inspector, GuardDuty |
| 3 | Satellite OpenSCAP reports → XCCDF ingest, and Insights Compliance export | The Red Hat estate's own scanners, zero new format work |
| 4 | Compliance Operator collator generalised to any profile; kube-bench | Small changes to shipped code |
| 5 | Tenable / Qualys / Rapid7 API → `cve_cache` | Feeds the patch lifecycle the demos already show |
| 6 | Defender for Endpoint, Tanium, Wazuh | Endpoint posture, one vendor at a time |
| 7 | Terraform providers (Route B) | The planned next goal; weeks, not days |

---

| Version | Date | Change |
|---|---|---|
| v0.1 | 2026-10-18 | First inventory, from the tree at `a7f1b62a` plus the reorg branches, for Tim's question "what probes and scanners do we integrate, and which can we" |
