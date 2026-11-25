# AAC database architecture

**Version:** v1.5
**Date:** 2026-11-24
**Authors:** Tim Coulter and Claude (Anthropic)
**Status:** Sections 1 to 3 describe the database as it is in this repository. Sections 4 to 6 are proposals for discussion; nothing in them is built.

The column-by-column reference is the [database dictionary](../reference/DATABASE_DICTIONARY.md), which is generated from the code. This page explains the structure, answers whether types and sizes are consistent, and lists what the database would need to hold to cover everything AAC can collect.

## 1. Summary

| Question | Answer |
|---|---|
| How many tables? | 44 PostgreSQL tables and 16 views, defined in 20 files |
| Is there one schema file? | No. The core role creates 11 tables; the other 33 are created by the feature that owns them, when that feature first runs |
| Are types and sizes consistent? | Partly. Host names and framework keys are consistent. Timestamps, identifiers, severities, control ids and decimals are not |
| Are the tables related to each other? | Weakly. There are 12 foreign keys across 44 tables. Most tables are joined by matching the text of `hostname` |
| Where are the collected facts? | In two JSON columns, `host_facts.facts` and `compliance_facts.facts`. Only installed packages have typed columns |
| Can every job run on a database built from this repository? | No. Nine tables are read or written by jobs and never created |
| Is there a retention rule? | Decided: fact snapshots are kept 13 months, then moved to nearline storage. Not implemented yet |

## 2. Structure today

### 2.1 The areas

| Area | Tables | What it holds |
|---|---|---|
| Collected facts | `host_facts`, `compliance_facts`, `fact_changes`, `sidecar_datasets` | What collectors read from a target, stored as JSON with a few typed columns for the host and operating system |
| Inventory | `installed_inventory`, `manual_product_declarations`, `host_registry`, `product_lifecycle`, `support_status_map`, `host_support_status` | Packages per host, the list of known hosts and their lifecycle state, product end-of-life data |
| Evidence | `compliance_results`, `compliance_certifications`, `evidence_maintenance_log` | One row per evaluation of a framework on a host. Append-only and hash-chained |
| Findings and remediation | `compliance_findings`, `remediation_status`, `remediation_actions`, `remediation_log`, `remediation_drafts`, `helpdesk_tickets` | Open and closed findings, what was done about them, tickets |
| Frameworks | `framework_catalog`, `customer_frameworks`, `standards_watch_state` | Which policy bundles exist and which a customer has enabled |
| Technical debt | `technical_debt_items`, `technical_debt_summary`, `remediation_rates`, `remediation_budgets` | Effort and cost scoring of open findings |
| Patch lifecycle | `patch_worklist`, `patch_manifest_raw`, `patch_risk_scores`, `patch_risk_parameters`, `patch_heatmap_cells`, `patch_traffic_state`, `patch_backup_manifests`, `patch_assurance_results`, `patch_closure_evidence` | The patch worklist and each stage a patch goes through |
| Vulnerabilities | `cve_events_received`, `cve_vendor_remediations` | Vulnerability events received and the vendor fixes for them |
| AI governance | `ai_systems`, `ai_action_log`, `ai_approval_requests` | Registered AI systems, their actions and approvals |
| Other | `golden_image_baselines`, `nerc_cip_exposure`, `github_traffic`, `github_referrers` | Golden image baselines, exposure ranking, repository traffic |

Three more tables (`audit_schedule`, `executive_summaries`, `framework_metrics`) are created by `scripts/executive_dashboard.py` in a local SQLite file. They are not part of the compliance database.

### 2.2 How a row gets there

1. A collector reads a target and writes a fact snapshot to `host_facts` (nightly facts) or `compliance_facts` (facts for one framework).
2. An assessment sends facts to OPA and writes one row to `compliance_results`: the totals, a JSON list of violations and a JSON metadata object.
3. A sync job reads `compliance_results` and maintains one row per open finding in `compliance_findings`.
4. Reports, dashboards and the scoring jobs read from those tables.

### 2.3 What is sound

- **Evidence is protected.** `compliance_results` is append-only, each row carries the hash of the previous one, and a function verifies the chain.
- **The host name is one type everywhere.** `hostname` is `VARCHAR(255)` in all 21 tables that have it.
- **Framework keys are one type.** `framework` and `loader_key` are `VARCHAR(100)` in every PostgreSQL table.
- **Facts are stored before they are evaluated.** A stored snapshot can be evaluated again against a new policy without reaching the host.
- **Most timestamps carry a time zone.** 65 of 68 timestamp columns do.

## 3. Are types and sizes consistent?

Partly. The table lists each inconsistency found in the 44 tables. The full list by column is in the dictionary under "The same column name with different types".

| Item | What was found | Why it matters |
|---|---|---|
| Timestamps without a time zone | 3 columns use `TIMESTAMP`: `compliance_results.evaluation_timestamp`, and `captured_at` in the two repository traffic tables | The evidence table is the one that matters. A time with no zone is read differently by a client in another zone, and it sorts wrongly against the `TIMESTAMPTZ` columns it is joined to |
| Two spellings of one type | `TIMESTAMPTZ` 53 times, `TIMESTAMP WITH TIME ZONE` 12 times | Same type, so no defect. It shows the tables were written at different times without a shared rule |
| Row identifiers | `BIGSERIAL` in 27 tables, `SERIAL` in 9, none in 8 | `compliance_results.id` is `SERIAL` (32-bit) while `compliance_findings.last_result_id` and `remediation_status.latest_result_id`, which point at it, are `BIGINT`. An append-only table that gets one row per host per framework per run is the one most likely to outgrow 32 bits |
| Severity | `VARCHAR(20)` in 5 tables, `VARCHAR(16)` in 2, `VARCHAR(32)` in 1 | The values are the same words. No constraint lists the allowed values, so "High", "high" and "HIGH" can all be stored |
| Control id | `VARCHAR(120)` in `compliance_findings`, `VARCHAR(50)` in two remediation tables | A control id that fits in the findings table can be cut off or rejected in the remediation tables |
| Vulnerability id | `VARCHAR(50)` in 6 tables, `VARCHAR(32)` in 2 | Same risk on a join |
| Ticket id | `INTEGER` in 3 patch tables, `VARCHAR(100)` in `remediation_status` | A ServiceNow or Jira ticket number is text. The integer columns can only hold the built-in ticket table's id |
| Tenant id | `VARCHAR(100)` in 3 tables, `TEXT` in 1, absent from the other 40 | The evidence and fact tables have no tenant column, so nothing in a row says which customer it belongs to |
| Decimal numbers | 10 different declarations, 15 columns with no precision at all. In `technical_debt_summary`, two columns are declared once with a precision and once without | Totals that are added across tables can round differently |
| Text sizes | 18 different `VARCHAR` lengths across 217 columns | Most are arbitrary. PostgreSQL stores `TEXT` and `VARCHAR(n)` the same way, so the lengths add limits without saving space |
| The subject of a row | `hostname` in 21 tables, `subject` in 1, `host_id` in 1, `system_id` in 1 | Covered in section 4.1 |
| Period columns | `period_start` and `period_end` are `DATE` in one table and `TIMESTAMPTZ` in another | Minor |

Three structural findings sit beside the type findings:

- **Tables used and never created.** `systems`, `system_facts`, `compliance_assessments`, `compliance_violations`, `compliance_frameworks`, `cis_policies`, `remediation_tasks`, `audit_log` and `policy_violations` are read or written by `compliance-assessment.yml`, `store_compliance_results.yml`, `store_compliance_facts.yml`, `opa-policy-deployment.yml`, `compliance_trending_report.yml` and `scripts/compliance_dashboard.py`. They look like an earlier data model that the current one replaced. Those jobs cannot run on a database built from this repository.
- **One table defined twice.** `compliance_results` is created in the core role and again in `scripts/install_postgres.sh`. The two definitions are identical today. Nothing keeps them so.
- **Few relationships are declared.** 12 foreign keys. A finding is linked to its host only by the text of the host name, so a renamed host leaves its history behind.

The connection settings are also inconsistent, which is what makes each report look different. The database name is `pg_db` in 87 files, and it also appears as `pg_database` (12 files), `compliance_db_name` (7), `db_name` (6), `aac_db_name` (4) and `postgres_db` (1). The default port is written as 5432 in 113 places and 5433 in 60.

## 4. What the database needs to hold

This section is a proposal. It starts from what collectors gather, what the policies read and what the reports ask for, and lists each item with where it lives today.

### 4.1 The subject: more than a host

Twenty-one tables identify what a row is about with `hostname`. AAC already collects from things that are not hosts. A Microsoft 365 tenant, a firewall, an Oracle database instance, an OpenShift cluster, a source repository and a metering head end are all stored today by putting a name in the host name column.

| Subject | Example | Stored today as |
|---|---|---|
| Host | A RHEL or Windows server | `hostname` |
| Network or storage device | Router, firewall, storage array | `hostname`, with the device name |
| Service instance on a host | An Oracle database, a web server, an application | Not stored as its own thing. Its facts are inside the host's JSON |
| SaaS tenant | A Microsoft 365 tenant | `hostname`, with the tenant name |
| Cluster and its objects | An OpenShift cluster, a namespace | `hostname`, with the cluster name |
| Cloud account or resource | An AWS account, an EC2 instance | Partly: `host_facts.aws_instance_id` and `host_registry.provider_ref` |
| Code | A repository, a playbook, a Terraform plan | Not stored, or `subject` in the findings table |

The proposal is one `subjects` table: a generated id, a type from the list above, a name, the parent subject where there is one (a database instance belongs to a host), and the source of record. Every other table then refers to the subject id. `hostname` stays as a column for as long as existing reports need it.

**A renamed host keeps its history (decided).** The subject id is therefore the identity and the name is an attribute of it. This needs two things. A `subject_names` table holds each name a subject has had and the dates it applied, so an old report still resolves. And the collector needs something more stable than the name to recognise the same machine: the machine id on Linux, the machine GUID on Windows, the instance id in a cloud, the serial number on a device, the tenant id for a SaaS tenant. Without one of those, a renamed host is indistinguishable from a new one. Today rows are matched on the text of `hostname`, so a rename starts a new history.

### 4.2 The items

"Typed" means the item has its own columns and can be queried and reported directly. "JSON" means it is inside a JSON document and each report has to know the path to it.

| Item | Why it is needed | Today | Proposed |
|---|---|---|---|
| Subject identity and type | Every query starts here | `hostname` text in 21 tables | `subjects` table (4.1) |
| Operating system, version, architecture | Scoping every benchmark | Typed in `host_facts` | Keep, on the subject |
| Running kernel and installed kernels | Patch decisions depend on the running one | Running kernel is collected, inside the JSON. Installed kernels are package rows. Nothing compares them | Typed: running kernel on the subject, plus a flag when a newer one is installed and not booted |
| Installed packages with full version | Vulnerability matching | Typed in `installed_inventory`; the version is one string | Keep. Split epoch, version and release so a fix version can be compared |
| Services and their state | CIS and STIG service controls | JSON | Typed: one row per service per subject |
| Service instances (database, web server, application) | Application benchmarks, per-application credentials | Not stored | Typed: one row per instance, child of a host subject |
| Users, groups and privileged accounts | Access controls in every standard | JSON | Typed |
| Listening ports and network interfaces | Exposure, firewall controls | JSON | Typed |
| Certificates and keys (algorithm, size, expiry) | Cryptography and post-quantum readiness | JSON | Typed |
| Configuration settings (sysctl, sshd, PAM, audit rules, registry values) | The bulk of every benchmark | JSON | JSON, with a declared schema per collector (4.3) |
| Device configuration | Network benchmarks | JSON | JSON, with a declared schema |
| SaaS tenant settings | CIS Microsoft 365 | JSON | JSON, with a declared schema |
| Which collector produced a snapshot | Tracing a result to how it was gathered | Job number only (`collection_job`) | Typed: collector id from the collector catalog, collection name and version, and whether the read succeeded |
| What a collector tried and could not read | Telling "compliant" from "not collected" | Not stored | Typed: one row per item not collected, with the reason |
| Frameworks | Scoping results | Typed in `framework_catalog` | Keep |
| Controls of each framework | Reporting by control, counting coverage | Not in the database. They are in the policy library | Typed: one row per control per framework version, loaded from the library |
| The crosswalk between standards | Answering "which controls in other standards does this satisfy" | Not in the database. It is in the policy library | Typed: loaded from the library, never edited in the database |
| Result per control (pass, fail, not applicable, manual) | Auditors ask for passes as well as failures | Failures only, as a JSON list in `compliance_results.violations` | Typed: one current row per subject and control, with the full history kept in the evidence table |
| The evidence value behind a result | Showing what was seen | JSON in `metadata`, not always present | JSON on the result row, with the fact snapshot id it came from |
| Policy version and commit | Reproducing a result | Typed (`policy_version`, `policy_sha`, `project_sha`) | Keep |
| Attestations for manual controls | Controls a machine cannot check | In files passed to the job | Typed: who attested, when, for which control and until when |
| Exceptions and accepted risk | Suppressing a known finding with an owner and an expiry | Partly. `accepted_risk` is a value of `remediation_status.status` and `remediation_actions.action_type`. Who approved it and when it expires are not stored | Typed: approver, reason, expiry |
| Findings and their lifecycle | Remediation tracking | Typed in `compliance_findings` | Keep |
| Tenant or customer | Reports per customer | 4 tables | Decided: the AAC database is on the customer's site and dedicated to that customer, so no tenant column is added here. The Customer Portal separates by tenant in its own database |
| Collection schedule and freshness | Detecting stale data | Derived by query | Derived. A view, not a table |

### 4.3 Columns or JSON

Some items belong in JSON. The rule proposed here decides which.

| Store it as | When | Examples |
|---|---|---|
| Typed columns | The item has the same meaning on every kind of target, and reports filter, join or count by it | Subject, operating system, package, service, account, port, certificate, control, result, finding |
| JSON with a declared schema | The item is specific to one technology, has many keys, or changes shape between versions | sshd settings, audit rules, a firewall rule base, tenant policies, an application's own settings |
| JSON with no schema | The raw answer from a module, kept as evidence and never queried by a report | The unprocessed return value of a facts module |

Two conditions make JSON workable for reports:

1. **Every JSON document names its schema and version.** `host_facts` and `compliance_facts` already have a `schema_version` column. The schema itself is not written down anywhere a report author can read. The policy library has started to publish the input each policy reads, and that is the place to take it from.
2. **A placeholder is a declared key, not an empty column.** An application that is not installed should have no row and no key. The schema says the key can exist, so a report can tell "not present on this subject" from "the collector does not gather this".

This keeps the typed part small and stable, and lets the technology-specific part grow one collector at a time without a schema change for each.

### 4.4 Reports on top of it

With the items above in typed tables or schema-declared JSON, the report design proposed in the project discussion becomes direct: one query layer that returns rows with no formatting, and one playbook per output format on top. The query layer needs three things from the database that it lacks today: a subject to join on, a result per control, and one name for each connection setting.

## 5. A standard for types and sizes

A proposal. It applies to new tables at once, and to existing ones as they are next changed.

| Kind of value | Type | Notes |
|---|---|---|
| Row identifier | `BIGINT GENERATED ALWAYS AS IDENTITY` | Replaces `SERIAL` and `BIGSERIAL` |
| Reference to another row | `BIGINT` with a foreign key | Declared, so the database refuses an orphan |
| Any point in time | `TIMESTAMPTZ` | Never `TIMESTAMP` without a zone, never text |
| A calendar day | `DATE` | Due dates, end-of-life dates |
| Names, keys, ids from outside (host, control, vulnerability, ticket) | `TEXT` | No length. Add a `CHECK` only where a real limit exists |
| A fixed list of values (severity, status, subject type) | `TEXT` with a `CHECK`, or a lookup table | One spelling, lower case |
| Hashes | `CHAR(64)` for SHA-256 | As the evidence chain does today |
| Yes or no | `BOOLEAN NOT NULL` | With a default |
| Counts | `INTEGER`, or `BIGINT` where rows accumulate | |
| Percentages | `NUMERIC(5,2)` | 0.00 to 100.00 |
| Hours and money | `NUMERIC(12,2)` | One precision everywhere |
| Structured data | `JSONB` | With the schema named in a sibling column |
| Network address | `INET` | Replaces `VARCHAR(45)` |

Names: `snake_case`; a time ends in `_at`, a day ends in `_date` or `_on`; a reference ends in `_id`; the subject column is `subject_id` everywhere.

## 6. Order of work

A proposal, smallest safe step first. Each step is useful by itself and none rewrites history in the evidence table.

1. **Keep the dictionary current.** Done in this change: the page is generated and the test fails when the schema and the page differ.
2. **One name for each connection setting**, and one default port. No schema change. It removes the largest source of difference between reports.
3. **Retire or repair the jobs that use the nine missing tables.** Decide per job; some are superseded.
4. **Add the `subjects` table** and a `subject_id` on new rows, beside `hostname`.
5. **Add the result per control**, which the per-control pass record work already needs.
6. **Load controls and the crosswalk from the library** into reference tables.
7. **Add typed tables for services, accounts, ports and certificates**, filled by the existing collectors from what they already gather.
8. **Record the collector and what it could not read** on each snapshot.
9. **Correct the type findings in section 3** in one migration per table, when that table is next touched. `compliance_results.id` and `evaluation_timestamp` are the two that should not wait.

## Decisions

Made by Tim Coulter on 2026-11-24.

| Question | Decision | What it means for the design |
|---|---|---|
| How are customers separated? | The AAC database is on the customer's site and dedicated to that customer. The Customer Portal separates by tenant | No tenant column is added to the AAC tables. The four tables that have `tenant_id` today (`customer_frameworks`, `remediation_budgets`, `remediation_rates`, `patch_manifest_raw`) keep it; it holds one value and costs nothing, and removing it would be a change for tidiness only. |
| Does a renamed host keep its history? | Yes | The subject id is the identity; names are kept with their dates (section 4.1) |
| How does the Customer Portal get data? | By push. The customer's AAC instance forwards what the Portal needs. The Portal never pulls from, or connects to, a customer's database | The database needs no inbound access from outside the customer's network. AAC needs a record of what was forwarded: which data set, when, and whether the Portal accepted it, so a customer can see exactly what left their site. The Portal adds the tenant when it receives the data |
| What does AAC take from the Portal? | AAC pulls it: the set of standards the customer is enrolled in, custom Rego policies and similar content | Every connection starts from the customer's site (section 9). What is pulled is reference data and policy, never evidence |
| Where does the database run? | It follows how the customer's Ansible Automation Platform is set up | The AAC database sits with the customer's AAP: same site, same operator, same network boundary. Its availability, backup and access rules follow what the customer already does for AAP, and AAC adds no second operating model |
| How long are fact snapshots kept? | 13 months in the database, then moved to nearline storage | Section 7 |

## 7. Retention of fact snapshots

Fact snapshots (`host_facts`, `compliance_facts`) stay in the database for 13 months and are then moved to nearline storage. Nothing implements this today: there is no retention job, and neither table is partitioned.

What the design needs:

- **Partition the two fact tables by month** on `collected_at`. Moving a month out is then detaching one partition, not deleting millions of rows.
- **Export before removal.** Each month is written to a file in nearline storage with its row count and a hash, and the export is recorded, so a snapshot can be found and loaded back.
- **Evidence rows are not part of this.** `compliance_results` is append-only and hash-chained; removing rows from it would break the chain. Results stay, and each keeps the id of the snapshot it was evaluated from.
- **A result must still be explainable after its snapshot has moved.** `compliance_results.facts_id` points at a snapshot. After 13 months that snapshot is in nearline storage, so the reference has to resolve to the archive record and not fail. The foreign keys from `fact_changes` and `remediation_actions` to `compliance_facts` need the same treatment.
- **Baselines are exempt.** A snapshot marked `is_baseline` is what later runs are compared with, so it stays until it is replaced.

Because the database is on the customer's site, the nearline store is the customer's own storage, and the export job must work without any connection outside their network.

Thirteen months keeps a full year of comparisons plus one month of overlap, which covers a year-over-year report and an annual audit window.

## 8. The executive dashboard tables

`scripts/executive_dashboard.py` creates three tables (`audit_schedule`, `executive_summaries`, `framework_metrics`) in a SQLite file named `compliance_metrics.db`, in whatever directory the script is run from.

It is a small issue, for these reasons:

- **It is a second store of compliance figures.** The script runs `opa eval` itself and saves scores in its own file. It never reads the compliance database, so its numbers can differ from the evidence.
- **It has none of the protections.** The file is not append-only, not hash-chained, not backed up with the database and not covered by the retention rule above.
- **Nothing runs it.** No playbook, job template or dashboard uses the script. It is mentioned in `README.md` and one operations document.

Recommendation: do not move these tables into the compliance database. The executive view that is in use is the set of Grafana dashboards, which read PostgreSQL. Either point the script at the compliance database for its figures and drop its own store, or retire it. It has not been run for this review, so whether it still works is not known; check that before retiring it.

## 9. What crosses the customer's boundary

Every connection is opened by the customer's AAC instance. The Portal never connects to a customer.

| Direction | Started by | What | In the database |
|---|---|---|---|
| AAC to Portal (push) | Customer's AAC | What the Portal needs to show: the data sets the customer chooses to forward | A record of each push: data set, time, and whether the Portal accepted it. Not built |
| Portal to AAC (pull) | Customer's AAC | The standards the customer is enrolled in, custom Rego policies, and their versions | What was pulled, its version and signature check, and when it was loaded. Partly built |

The pull exists today for policy. `sync_customer_bundle.yml` fetches the customer's signed policy bundle from the Portal, verifies the signature offline, loads it into a dedicated OPA container and reports back whether it loaded. `customer_frameworks` holds which frameworks are enabled. What is missing is a record in the database of each bundle pulled (version, hash, signature result, time loaded), so that a result can be traced to the exact custom policy that produced it, in the same way `policy_sha` traces it to the library.

**To begin with, every push and pull is triggered.** Each one is a job the customer launches from their AAP, and nothing is forwarded or fetched on a schedule or by an event until the customer chooses to schedule it. The record of pushes and pulls therefore also holds who or what started each one (the AAP job and the user).

Two rules keep this simple:

- **Pulled content is reference data.** Standards, controls, the crosswalk and custom policies are loaded and replaced, never edited in the customer's database. The typed control and crosswalk tables in section 4.2 are filled this way.
- **Evidence only leaves by a recorded push.** Nothing in the evidence or fact tables is readable from outside.

## Open questions

- Which nearline store on the customer's site, and who can load a month back? The store is the customer's, so the export has to be a plain file format they can keep without AAC.
- Executive dashboard script: repoint it at the compliance database, or retire it?
