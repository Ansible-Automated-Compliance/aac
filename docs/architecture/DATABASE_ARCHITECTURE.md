# AAC database architecture

**Version:** v1.7
**Date:** 2026-11-26
**Authors:** Tim Coulter and Claude (Anthropic)
**Status:** The goals are proposed for confirmation. Sections 1 to 3 describe the database as it is in this repository. Sections 4 to 12 are proposals, section 13 records decisions, and nothing in sections 4 to 12 is built. v1.6 takes in an outside review of v1.5 (section 10); each of its findings was checked against the code before it was accepted.

The column-by-column reference is the [database dictionary](../reference/DATABASE_DICTIONARY.md), which is generated from the code. This page explains the structure, answers whether types and sizes are consistent, and lists what the database would need to hold to cover everything AAC can collect.

## Goals

Proposed in v1.7 for confirmation. Earlier versions stated no goals; they described the tables and worked outward.

**The first goal of this database is evidence of compliance.** A row in it should let a customer show an auditor, without AAC's authors in the room, what was true of a system on a date and how that was established.

For a result to count as evidence, the database has to be able to show all of the following. The right-hand column is the state today.

| An auditor asks | The database must hold | Today |
|---|---|---|
| What was examined? | The subject, identified so that it is the same thing over time | Host name text. A renamed host loses its history |
| What was seen? | The facts collected, unaltered since collection | Stored, but not sealed and editable (10.1) |
| How was it gathered? | The collector, its version, and what it could not read | Job number only |
| Against what was it judged? | The standard, its version and profile, and the exact policy | Policy commit recorded. No standard version or profile (10.3) |
| What was the result, control by control? | Every control's result, passes included | Failures only (10.2) |
| Was a person's judgement involved? | Attestations and exceptions, with who and until when | A status value only |
| Has anything been changed since? | A chain that fails if a row, its facts or its control results are altered, and an anchor outside the database | Result rows are chained. Facts and passes are not. The anchor is an AAP artifact (10.5) |
| Can it be reproduced? | The same facts, policy and standard version give the same result later | Possible in principle. Not once a snapshot has moved to nearline, until the hash is carried (10.1) |
| Is it still there when asked for? | Retention that matches the standard, and a hold that stops removal | Not defined for evidence |

The other goals follow from the first and must not weaken it:

2. **Collect once, judge against any standard.** Facts are stored before they are evaluated, so a new or changed standard is answered from what is already held.
3. **Reports from one query layer.** A report is a query and a format, and never a second copy of the figures.
4. **Room for everything that can be collected**, with typed columns for what is common and declared JSON for what is specific to a technology.
5. **It stays the customer's.** On their site, readable without AAC, and nothing leaves except by a recorded push.

Where two of these pull against each other, evidence wins. An example is retention: moving snapshots to nearline saves storage, and it is only acceptable because the result keeps the snapshot's hash.

## 1. Summary

| Question | Answer |
|---|---|
| How many tables? | 44 PostgreSQL tables and 16 views, defined in 20 files |
| Is there one schema file? | No. The core role creates 11 tables; the other 33 are created by the feature that owns them, when that feature first runs |
| Are types and sizes consistent? | Partly. Host names and framework keys are consistent. Timestamps, identifiers, severities, control ids and decimals are not |
| Are the tables related to each other? | Weakly. There are 12 foreign keys across 44 tables. Most tables are joined by matching the text of `hostname` |
| Where are the collected facts? | In two JSON columns, `host_facts.facts` and `compliance_facts.facts`. Only installed packages have typed columns |
| Can every job run on a database built from this repository? | No. Nine tables are read or written by jobs and never created |
| Is the evidence sealed end to end? | No. The result rows are hash-chained and append-only. The facts they were judged on are not hashed into the chain and can be edited, and the table can be emptied with `TRUNCATE` by its owner (section 10) |
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
| Row identifiers | `BIGSERIAL` in 27 tables, `SERIAL` in 9, none in 8 | `compliance_results.id` is `SERIAL` (32-bit) while `compliance_findings.last_result_id` and `remediation_status.latest_result_id`, which point at it, are `BIGINT`. The mismatch is the defect. At today's row rate a 32-bit id lasts for decades (section 12), so this is a tidy-up when the table is next changed, unless control rows were ever written into this table |
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
| Frameworks | Scoping results | Typed in `framework_catalog`, as one key with no version, profile or level | Standard, version, profile and level as separate tables (section 10.3) |
| The AAC installation | A customer may run several AAPs, each with its own AAC | Not stored | Typed: one generated id per installation, carried in every push and in the evidence chain (section 10.6) |
| Controls of each framework | Reporting by control, counting coverage | Not in the database. They are in the policy library | Typed: one row per control per framework version, loaded from the library |
| The crosswalk between standards | Answering "which controls in other standards does this satisfy" | Not in the database. It is in the policy library | Typed: loaded from the library, never edited in the database |
| Result per control (pass, fail, not applicable, manual) | Auditors ask for passes as well as failures | Failures only, as a JSON list in `compliance_results.violations` | Typed, insert-only rows that record a control's result only when it changes, sealed by a hash held in the parent evidence row (section 10.2). The current state is a view, not an editable table |
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
| Hashes | `CHAR(64)` for SHA-256; `CHAR(40)` for a Git SHA-1 commit | Chain hashes are SHA-256. `policy_sha` and `project_sha` are Git commits and are `VARCHAR(64)` today |
| Yes or no | `BOOLEAN NOT NULL` | With a default |
| Counts | `INTEGER`, or `BIGINT` where rows accumulate | |
| Percentages | `NUMERIC(5,2)` | 0.00 to 100.00 |
| Hours and money | `NUMERIC(12,2)` | One precision everywhere |
| Structured data | `JSONB` | With the schema named in a sibling column |
| Network address | `INET` | Replaces `VARCHAR(45)` |

Names: `snake_case`; a time ends in `_at`, a day ends in `_date` or `_on`; a reference ends in `_id`; the subject column is `subject_id` everywhere.

## 6. Order of work

A proposal, revised in v1.6. Integrity comes first, because every later step adds rows that should be sealed from the day they are written.

1. **Keep the dictionary current.** Done: the page is generated and the test fails when the schema and the page differ.
2. **Give the installation an id** (10.6). One row, written once.
3. **Version the evidence hash format** and record the format on each row (10.4). Nothing else in the evidence table changes until this is in.
4. **Seal the facts** (10.1): hash each snapshot, carry the hash into the result row and its hash, make the fact tables insert-only.
5. **Close the truncate gap and move the anchor out of AAP job history** (10.5).
6. **One name for each connection setting**, and one default port. No schema change.
7. **Retire or repair the jobs that use the nine missing tables.**
8. **Add the `subjects` table** and a `subject_id` on new rows, beside `hostname`.
9. **Add standards, versions, profiles and levels** (10.3), loaded from the library, with the controls and the crosswalk.
10. **Add the result per control** as sealed, change-only rows (10.2).
11. **Add typed tables for services, accounts, ports and certificates.**
12. **Record the collector and what it could not read** on each snapshot.
13. **Correct the type findings in section 3**, one migration per table. `compliance_results.id` can widen at any time. `evaluation_timestamp` changes only after step 3.

## 7. Retention of fact snapshots

Fact snapshots (`host_facts`, `compliance_facts`) stay in the database for 13 months and are then moved to nearline storage. Nothing implements this today: there is no retention job, and neither table is partitioned.

What the design needs:

- **Partition the two fact tables by month** on `collected_at`. Moving a month out is then detaching one partition, not deleting millions of rows. A partitioned table's primary key has to include `collected_at`, so the present foreign keys to `compliance_facts(id)` cannot stay as they are, and `fact_changes` uses `ON DELETE SET NULL`, which would blank its history. The links become the snapshot hash (10.1) plus a `fact_archive` catalog (month, file location, row count, hash, export time).
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

## 10. Review of v1.5 and what changed

An outside review (`AAC_Database_Architecture_v1.5_Review.docx`, 2026-11-25) graded v1.5 a B: a sound base that is not yet ready to carry growth, and an A- once its first four items and an installation id are in. It lists 25 items. The five most serious are in the table below and were each checked against the code; all five hold. Section 10.7 gives the disposition of every item.

| # | Finding | Checked against | Result |
|---|---|---|---|
| 1 | Facts are not sealed. A result points at its snapshot by id only, and the fact tables can be edited | `evidence_row_canonical()` hashes `facts_id`, an integer. No trigger or grant protects `host_facts` or `compliance_facts` | Holds |
| 2 | The proposed per-control results sat in an editable "current" table outside the chain | Section 4.2 of v1.5 | Holds. It was a flaw in this document's proposal |
| 3 | Standards have no version, profile or level, and no record of which version replaces which | `framework_catalog` has one key and no version column. `policy_version` on a result is free text | Holds |
| 4 | The planned timestamp change would break every existing evidence hash | The hash input includes `to_char(evaluation_timestamp, ...)` on a column with no time zone | Holds |
| 5 | The anchor outside the database is an AAP job artifact, and a table owner can empty the evidence table | `verify_evidence_chain.yml` publishes the chain head with `set_stats`. The guards are row-level `BEFORE UPDATE OR DELETE` triggers, which `TRUNCATE` does not fire | Holds |

What the review found sound, and which stays as it is: the evidence table refuses edits and deletes, the writer role can only insert, facts are stored before they are evaluated, "not collected" is kept apart from "compliant", and every result records the policy commit.

### 10.1 Seal the facts

Today someone with write access can change a stored snapshot and every result that was judged on it still verifies.

- Each snapshot gets a SHA-256 of its canonical content, computed by the database on insert. `host_facts` has a `checksum` column today, but the collector computes it from Jinja `to_json`, which is not a canonical form, and `compliance_facts` has none.
- The review proposes hashing `facts::text`. That is stable within one PostgreSQL major version, as the review says. To stay verifiable across an upgrade, either define the canonical form independently of the server (sorted keys, fixed number and string rendering) or record the server version beside the hash and re-prove on upgrade. This needs deciding before the column is added.
- The result row carries that hash (`facts_sha256`) beside `facts_id`, and the hash goes into the result's own hash. A changed snapshot then breaks the chain at every result that used it.
- Both fact tables become insert-only, with the same guard the evidence table has. A correction is a new snapshot that supersedes the old one.
- The 13-month move to nearline storage (section 7) stays possible: the result keeps the hash, so a snapshot loaded back from the archive can be proved to be the one that was judged.

### 10.2 Seal the result per control

- One row per subject, control and change: the control's result, the evidence value, and the evidence row it came from. Insert-only.
- The parent evidence row carries one hash (`control_set_sha256`) over the full set of control results of that evaluation, and that hash is part of the parent's own hash. Passes are then evidence in the same sense failures are.
- The hash must cover the full evaluated set, computed when the evaluation is stored, even though only the changed rows are written (below). The review's sketch hashes "the ordered control_results rows" of the result; with change-only storage those rows are only the changes, so the two have to be stated separately: the stored rows are the changes, the hash is over the whole state.
- "Current state" is a view over the latest row per subject and control. Nothing in it can be edited.

**Store changes, not repeats.** The review estimates about 2.2 billion rows a year at 5,000 systems if every control result is written every day. The arithmetic is 5,000 subjects x 4 frameworks x about 300 controls x 365 days; the 4 and the 300 are the review's assumptions, not measurements (section 12). A control that passed yesterday and passes today needs no new row: the parent evidence row for today already seals the statement "nothing changed", because its control hash equals yesterday's. Rows are written when a result or its evidence value changes, and once per period (for example monthly) as a full restatement, so a reader never has to walk back further than that to rebuild the state.

**Store a snapshot once.** If a new snapshot's hash equals the previous one for that subject, record that it was seen again and when, and do not store the body a second time.

### 10.3 Standards, versions, profiles and levels

One framework key cannot say "CIS RHEL 9 v2.0.0, Level 1, Server", "the STIG release of this quarter" or "PCI DSS 4.0, which replaced 3.2.1".

| Table | One row per | Holds |
|---|---|---|
| `standards` | Standard | Key, name, publisher. Example: CIS Red Hat Enterprise Linux 9 Benchmark |
| `standard_versions` | Published version | Version, published and effective dates, retired date, and the version it replaces |
| `profiles` | Profile or level within a version | Example: Level 1 Server, Level 2 Workstation, a STIG classification, a NIST baseline (Low, Moderate, High) |
| `controls` | Control within a version | Control id, title, whether it is checked by machine or attested |
| `profile_controls` | Control in a profile | Which controls a profile includes |
| `control_lineage` | Control carried between versions | The control in the new version that continues one in the old, so a finding keeps its history across an upgrade |

An evaluation then records the version and the profile it was judged against, and a customer's enrolment (`customer_frameworks`) names a version and profile, not only a key. All six tables are reference data, loaded from the policy library and from what AAC pulls from the Portal (section 9), never edited in place.

### 10.4 Version the hash format before changing anything it covers

The hash input starts with the text `aac-evidence-v1`, and that is the only version marker; it is fixed in the function, not stored on the row. Changing `evaluation_timestamp` to carry a time zone changes how it is rendered into the hash input, so every existing row would fail verification.

- Add a `canon_version` column, set to 1 on every existing row.
- Verification picks the canonical form by the row's `canon_version`. Old rows verify with the old form for ever.
- Version 2 renders every time in UTC, and includes the facts hash (10.1), the control-results hash (10.2) and the installation id (10.6).
- Only after that is `evaluation_timestamp` converted, with the stored values interpreted as UTC. The zone the existing values were written in must be confirmed first; the column has no zone and the default is the server's local time.

### 10.5 The anchor and the truncate gap

Two gaps, both confirmed.

- **Truncate.** The guards fire per row on update and delete. `TRUNCATE` fires neither. The writer role has `TRUNCATE` revoked, but the table owner does not. Add a statement-level `BEFORE TRUNCATE` trigger that refuses, on the evidence table and on the fact tables. A superuser can still drop a trigger, which is why the anchor below has to be outside the database.
- **The anchor.** The chain head is published as an AAP job artifact. AAP's job-history cleanup can remove it, and it is not signed. What is described as signed evidence is a hash chain plus that record.

Proposal: a daily checkpoint holding the installation id, the chain head id and hash, the row count and the time, signed with a key held by the customer's AAC. The checkpoint is written to a place the database owner cannot alter (a file store with write-once retention on the customer's site), and it can be pushed to the Portal as a second copy.

The push to the Portal is the customer's choice, in line with section 9: every transfer starts as a job the customer launches or schedules. A checkpoint contains no evidence, only a hash, so it reveals nothing about the estate. A customer who forwards nothing still has the on-site copy.

### 10.6 An id for each installation

A customer can run more than one AAP, each with its own AAC and database. One generated id per installation, created when the database is initialised and never changed:

- it is carried in every push, so the Portal keeps two installations of one customer apart;
- it is part of the hash input from canonical version 2, so rows cannot be moved from one installation's chain into another's;
- it is the first part of every checkpoint.

### 10.7 Every review item and what was done with it

"Accepted" means the item is taken into this design. Nothing is built.

| Item | Summary | Checked | Disposition |
|---|---|---|---|
| C1 | Facts are not sealed into the chain | Yes, holds | Accepted, 10.1. One point added: the canonical form across PostgreSQL versions |
| C2 | Per-control results outside the chain | Yes, holds | Accepted, 10.2. One point added: the set hash covers the full state, the stored rows are the changes |
| H1 | No versions, profiles or supersession | Yes, holds | Accepted, 10.3. The review's `parent_id` on controls is adopted for hierarchy (enhancements, sub-requirements) |
| H2 | Timestamp change breaks verification | Yes, holds | Accepted, 10.4 |
| H3 | The anchor is an AAP artifact; `TRUNCATE` is not blocked | Yes, holds | Accepted, 10.5, with a `chain_checkpoints` table. Pushing checkpoints to the Portal stays the customer's choice (section 9) |
| H4 | No identity for an installation | Yes: nothing stores it | Accepted, 10.6, as an `aac_instance` table with site name and environment. Pushes carry the instance id and a sequence number |
| H5 | Secrets and personal data in facts; broad read access; TLS | Partly | Accepted in substance, section 11. Two corrections there |
| H6 | No volume estimate | True of v1.5 | Accepted, section 12 |
| M1 | Crosswalk has no relationship type or status | The library has authoritative and pending maps | Accepted: `control_mappings` with relationship (equivalent, subset, superset, intersects), status, source and map version. A satisfied result flows only across equivalent or subset links |
| M2 | Status words differ from the library | Yes. The library uses satisfied, gap, not_applicable, not_evaluated, not_reviewed, not_covered | Accepted: one checked list taken from the library, with "not collected" kept separate from "not reviewed". Section 4.2's "pass, fail" wording is superseded |
| M3 | Exceptions and attestations need more fields and must be insert-only | Consistent with what is stored today | Accepted. Both change a reported status, so both are evidence, and a result row records the exception or attestation it applied |
| M4 | Custom bundle traceability | Section 9 identified it | Accepted: `policy_bundles` with source, version, hash, signature result, signer, load time and OPA version, and a bundle id on each result |
| M5 | De-duplicate facts | Not measured | Accepted in principle, 10.2. Content-addressed storage is the right shape; how much it saves needs a real estate |
| M6 | Partitioning conflicts with the foreign keys | Yes. `fact_changes` and `remediation_actions` reference `compliance_facts(id)`, and `fact_changes` uses `ON DELETE SET NULL` | Accepted. Section 7 is corrected: the links become the snapshot hash plus a `fact_archive` catalog, not an id that stops resolving |
| M7 | Evidence retention and legal hold | Nothing defined | Accepted as a requirement. The retention periods the review quotes per framework were not checked here and need a source before they go in a customer document |
| M8 | Relationships between subjects, and several identifiers per subject | Section 4.1 had one parent and one stable id | Accepted: `subject_edges` for relationships and `subject_identifiers` for serial, MAC, cloud id and the like. It replaces the single stable id in 4.1 |
| M9 | Versions beyond RPM | `installed_inventory` already has `cpe` and `purl` columns | Accepted for devices, firmware and applications; packages already carry both |
| M10 | Time source | Evaluation time is the database clock | Accepted: keep the target's collection time and the database time. A timestamp authority on the checkpoint is optional |
| M11 | Query patterns and rollups for dashboards | Not defined | Accepted. It is the same work as the single query layer in section 4.4 |
| M12 | The push summary has no schema | Section 9 proposed only the record | Accepted: a versioned contract with instance id, sequence, period, aggregates, checkpoint and its own hash. It belongs to the Portal work |
| L1 | Status line and numbering out of date | Yes | Fixed in this version |
| L2 | No evidence rule for backup and restore | True | Accepted: after any restore, verify the chain against the last signed checkpoint before the restore is declared good |
| L3 | Hash column types are mixed | Yes. `policy_sha` and `project_sha` are `VARCHAR(64)`, chain hashes `CHAR(64)` | Accepted. A Git SHA-1 is 40 characters, so the two are different kinds of value and section 5 now says so |
| L4 | The urgency on `compliance_results.id` was overstated | Yes. At the review's own figures the 32-bit id lasts decades at today's row rate | Accepted. Section 3 is corrected: widen it when the table is next changed, not as a priority |
| L5 | Byline should name Grok | No | Not accepted. This document was written with Claude, and the byline says who wrote it. The review is credited here as an outside review |

## 11. Security of the data

From review item H5, checked against the repository.

| Point | What was found | Proposal |
|---|---|---|
| Secrets in facts | No redaction step exists in the collectors. The nightly host facts are a chosen set of values, not a dump of everything `gather_facts` returns, which limits the exposure. The compliance facts read configuration files and command output, where a secret can appear | A redaction pass before insert, with a deny-list per schema, and a stored list of what was redacted so the redaction is itself on record |
| Personal data | Accounts, groups and Microsoft 365 users are stored | Mark those columns and JSON paths in the dictionary. Only aggregates are pushed to the Portal |
| Read access | `compliance_reader`, which Grafana uses, has `SELECT` on every table and view, including raw facts | Dashboards read views only. A separate auditor role reads raw evidence |
| Encryption in transit | The review says no TLS setting was found. That is not quite right: `ssl_mode` is set in 17 places, with a default of `prefer`. `prefer` encrypts when the server offers it and does not require or verify it | Require TLS on the server and `verify-full` on clients, with the customer's certificate authority |
| Encryption at rest | Not addressed by AAC | The customer's storage control, stated as such |

## 12. Size and growth

The figures are the review's working assumptions, not measurements: daily collection, 4 frameworks per subject, about 300 controls per framework, about 30 KB per compressed host snapshot and 15 KB per framework snapshot, 13 months of facts, about 2% of control results changing per day and about 90% of snapshots unchanged from the day before. The arithmetic was checked and is consistent with those assumptions. They should be replaced with counts from a real estate.

| Subjects | Evidence rows a year | Control rows a year, every result | Control rows a year, changes only | Facts for 13 months | Facts with de-duplication |
|---:|---:|---:|---:|---:|---:|
| 500 | 0.7 million | 220 million | 4 to 5 million | about 18 GB | about 2 GB |
| 5,000 | 7.3 million | 2.2 billion | about 45 million | about 180 GB | about 18 GB |
| 50,000 | 73 million | 22 billion | about 450 million | about 1.8 TB | about 180 GB |

What follows from it:

- The evidence table in its present shape is small at every scale shown.
- Writing every control result every day is not workable beyond a small estate. Change-only rows with a sealed set hash (10.2) are.
- The single chain, which serialises writers, is sound at the evidence-row rate and would not be at the control-row rate. Sealing the control set into the parent keeps the chain at the lower rate.
- Facts are most of the storage. De-duplication and monthly partitions decide whether a large estate fits on ordinary storage.
- Dashboards should read a daily rollup and a latest-state view, never the history.

## 13. Decisions

Made by Tim Coulter on 2026-11-24.

| Question | Decision | What it means for the design |
|---|---|---|
| How are customers separated? | The AAC database is on the customer's site and dedicated to that customer. The Customer Portal separates by tenant | No tenant column is added to the AAC tables. The four tables that have `tenant_id` today (`customer_frameworks`, `remediation_budgets`, `remediation_rates`, `patch_manifest_raw`) keep it; it holds one value and costs nothing, and removing it would be a change for tidiness only. |
| Does a renamed host keep its history? | Yes | The subject id is the identity; names are kept with their dates (section 4.1) |
| How does the Customer Portal get data? | By push. The customer's AAC instance forwards what the Portal needs. The Portal never pulls from, or connects to, a customer's database | The database needs no inbound access from outside the customer's network. AAC needs a record of what was forwarded: which data set, when, and whether the Portal accepted it, so a customer can see exactly what left their site. The Portal adds the tenant when it receives the data |
| What does AAC take from the Portal? | AAC pulls it: the set of standards the customer is enrolled in, custom Rego policies and similar content | Every connection starts from the customer's site (section 9). What is pulled is reference data and policy, never evidence |
| Where does the database run? | It follows how the customer's Ansible Automation Platform is set up | The AAC database sits with the customer's AAP: same site, same operator, same network boundary. Its availability, backup and access rules follow what the customer already does for AAP, and AAC adds no second operating model |
| How long are fact snapshots kept? | 13 months in the database, then moved to nearline storage | Section 7 |

## 14. Open questions

- Which nearline store on the customer's site, and who can load a month back? The store is the customer's, so the export has to be a plain file format they can keep without AAC.
- Executive dashboard script: repoint it at the compliance database, or retire it?
- What time zone were existing `evaluation_timestamp` values written in? It decides how they convert (10.4).
- Where is the write-once store for checkpoints on a customer's site, and who holds the signing key?
- What is the canonical form of a snapshot for hashing, so a hash survives a PostgreSQL upgrade (10.1)?
- How often is the full restatement of control results written: monthly, or per assessment period?
