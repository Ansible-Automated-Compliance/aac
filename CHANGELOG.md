# Changelog

## Unreleased

### Changed — public-cut tree sweep (2026-10-23)

- Lab addresses leave the tree: the install-config hygiene gate, the security scan and
  `scripts/validate_rego_library.py` read them from the `LAB_ADDRESSES` Actions secret
  (comma-separated) instead of naming them; `.github/security-denylist.txt` no longer lists them.
- Lab hostname defaults in `seed_inventory_groups.yml` (`seed_rhel9_hosts`) and
  `seed_mythos_patch_workflow.yml` (`mythos_default_target_host`) are variables with neutral defaults.
- Personal paths removed from two rotation playbooks, `scripts/update_mcp_https.sh`
  (`AAC_PROJECT_PATH`, defaults to the repo) and four documents; three one-time Rego v1
  migration scripts deleted.
- Sales-demos pack comments name the platform, not a person, and no longer describe this
  repository as private; a partner name dropped from a schema comment; install-guide curl
  examples use `$AAP_ADMIN_PASSWORD`.

### Added — OpenShift Local (CRC) evaluation install guide: AAP 2.7 and Automation Orchestrator

- `install/openshift-local/README.md` (v2.0): one RHEL 9 host, OpenShift Local, AAP 2.7 with the Red Hat operator and Automation Orchestrator with its operator and a PostgreSQL for it, from five shipped manifests (`stable-2.7` subscription and a single-node platform CR with Lightspeed off; the Orchestrator subscription, its database with the two Secrets the CR reads, and the `AutomationOrchestrator` CR with the outbound allow list). Covers the hostpath permission fix, admin passwords, the gateway token, entitlement, connecting the Orchestrator to the platform, verification and the three things that break after a CRC restart. AAC itself is deferred to `install/existing-aap/extended/`, with the three values that guide needs from this install. Evaluation tier in `SUPPORT_MATRIX.md`; a row in the install chooser.

### Added — PQC Readiness collector (the policy had no facts; now it has them)

- **"AAC - PQC Readiness Assessment"** (`ansible/playbooks/pqc_readiness_assessment.yml`, seeded by `seed_pqc_readiness_template.yml`) feeds the library's `frameworks/federal/pqc` policy (FIPS 203/204/205, NIST IR 8547, EO 14412 / OMB M-26-15, CNSA 2.0) from real hosts. The collector (`ansible/tasks/collect_pqc_crypto_facts.yml`) reads, read-only, a Linux host's certificate public-key and signature algorithms, SSH host-key types, sshd's effective key-exchange list and the key-exchange group each listening TLS port negotiates, plus the crypto policy, FIPS state and whether OpenSSL offers ML-KEM; the mapper (`ansible/tasks/pqc_build_opa_input.yml`) turns them into the policy's `crypto_inventory` rows with the single-token algorithm spellings it classifies, and adds the site's program attestations from `ansible/vars/pqc_attestations.yml` (example shipped; every boolean false until a named person verifies it). Absent attestations stay absent, so the policy fails closed. Wiring: `pqc: compliance` in `opa_framework_map`, a `pqc` loader key on opa-compliance and a catalog row. `tests/pqc_mapper/` proves the playbook sends what the policy reads (the fixture evaluates 14 controls on the federal profile with 17 inventory rows, 10 quantum-vulnerable, 3 PQC, 9 violations) and that a hostile host string is copied, never evaluated. Known limits: Linux only; the TLS probe reads what a local `openssl s_client` negotiates, not every group the listener offers; certificates inside keystores are not read; OpenSSH's `sntrup761x25519` hybrid is quantum-resistant but not a FIPS PQC algorithm and is counted as neither vulnerable nor protected. Doc: `docs/frameworks/PQC_READINESS.md`.

### Changed — CIS pfSense assessment sends the CIS pfSense Firewall v1.1.1 evidence

- `ansible/playbooks/cis_pfsense_assessment.yml` now also sends `syslog`, `hasync` and `openvpn` (passed through when the device config has them), the text of `/etc/ssh/sshd_config` (CIS 1.1) and `/etc/motd` (CIS 1.3) read from the device, and an `attest` object for the seven review-only recommendations plus `ipv6_required` (1.6). Attestations come from the new `pfsense_attest` extra var (a mapping, or a survey textarea holding YAML/JSON); it defaults to empty, so those controls fail as "not attested" until someone signs them off. A section or file that cannot be read is left out so the policy reports evidence missing. The stored policy version now comes from the policy's own `benchmark` field, and the stored metadata records the attestations. The payload is a superset of what the v1.0.0 policy reads, so scores at the current library pin are unchanged. Harness: `tests/pfsense_collector/`. Operator impact: once the library pin carries v1.1.1, set `pfsense_attest` for the controls a person has reviewed.

### Added — CIS Linux collector supplement (RHEL 9 family, Fedora, Ubuntu 22.04, AL2023)

- The shared Linux collector (`ansible/tasks/collect_linux_compliance_facts.yml`) gathers nine new read-only blocks: boot/AIDE/core-dump state, running network kernel parameters with IPv6/wireless/firewall state, local user and group hygiene (names only, no hashes), umask/TMOUT/INACTIVE, package signing keys and repositories, storage encryption (LUKS, crypttab, swap, FIPS), service certificates, `authorized_keys` fingerprints, and file modes for GRUB, banners, cron and audit files. The shared mapper (`ansible/tasks/cis_linux_build_opa_input.yml`) now emits `boot_security`, the network section, `user_group`, `storage_encryption`, `certificates`, `authorized_keys` and the missing `initial_setup`, `cron`, `pam` and `auditd` fields. On the synthetic RHEL 9 fixture, `assessment_coverage_percentage` goes from 79 to 100 and `sections_not_assessed` from 3 sections to none. Facts stored before this change still render, and the new sections stay NOT ASSESSED until the host is collected again. Operator impact: hosts that were scored on partial input will now show real findings in those sections.

### Added — estate continuity (retired vs disappeared vs not responding)

- **"AAC - Estate Continuity Check"** (`ansible/playbooks/estate_continuity_check.yml`, seeded daily at 03:00 UTC by `seed_estate_continuity_schedule.yml`). Accounts for every host the estate is expected to contain: evaluated recently, explained (stopped, retired under a decommission record) or reported (missing, removed without a record, running but in no inventory, unreachable, failing, never targeted, retired but still answering). The decision is the rego library's `estate_continuity.main` policy; the playbook gathers inventory presence, EC2 state, evidence age, the last job outcome, decommission records and AAP host deletions, then stores one evidence row per host. A new `host_registry` table remembers hosts after the inventory and the provider have forgotten them. Decommission records go in `ansible/vars/decisions/estate_continuity.yml`. Docs: `docs/operations/ESTATE_CONTINUITY.md`.

### Added — the findings workbook (generic, decision-aware reporting)

- **`scripts/findings_workbook.py` + "AAC - Compliance Findings Workbook"**
  (`ansible/playbooks/compliance_findings_workbook.yml`): one report for ANY
  framework — Summary, Findings (one row per control × subject with a stable
  finding identity, explainable risk, remediation, owner, decision, delta, age
  and an evidence pointer), Unassessable (split by cause: benchmark manual /
  attestation required / collector not built / facts not collected / not
  evaluated, with who acts), Decisions, Delta (new / fixed / regressed /
  still open vs the previous run) and Passed. Written as `.xlsx` (standard
  library emitter, no new EE package), one CSV per sheet, HTML, Markdown and
  JSON. Column contract published in `docs/operations/FINDINGS_WORKBOOK_CONTRACT.md`
  and pinned by test so it cannot drift from the code.
- **Decisions files** (`ansible/vars/decisions/<framework>.yml`,
  `examples/decisions_example.yml`): owner, remediate / accept / review,
  justification, named approver, expiry and risk override per finding, plus
  default owners by section. Joined to live findings on every run; evidence is
  never edited and the workbook is never hand-edited. Accepted deviations
  export as OPA waiver entries (`--emit-waivers`).
- **CIS M365 assessment now applies security exception waivers** at persist
  time (same OPA `exceptions` decision as `aac_store_results`); waived findings
  are stored in `metadata.waivers_applied`, visible and never hidden, and the
  row's `compliant` / `violation_count` are recomputed from the active set.
  `m365_waivers_enabled` (default true).
- **`seed_report_templates.yml`** registers the report job templates on the
  controller (create-or-update by name, with surveys): Sync Compliance
  Findings, Compliance Findings Workbook, Risk Scoring, Mitigation Guidance,
  Closure Report, M365 CIS Findings Report, M365 CIS Violations Report.

### Changed — `aac.cis_facts` becomes `aac.host_facts` 2.0.0, the one copy of the gatherer roles (reorganisation R2 / extraction plan E0)

- **Collection renamed** `collections/ansible_collections/aac/cis_facts` → `aac/host_facts`; fact
  keys `cis_<area>_facts` → `host_<area>_facts` in all eleven roles and their READMEs; `galaxy.yml`
  2.0.0 with a framework-neutral description. CIS, STIG and NERC CIP all consume the same host
  facts, so the collection is named for the host. Done now because nothing calls it yet: no
  playbook, role or Rego file read the old keys, so the rename has no consumer to break.
- **Two legacy task fixes ported** from the removed `ansible/roles/gather_*` copies: the sticky-bit /
  world-writable analysis in `gather_filesystem_config` and the log-file permission analysis in
  `gather_logging_config`. The collection versions used `&`, `0o007` and `'%04o' | format()` on an
  octal *string*, which Jinja cannot render, so those facts were never collected; the ported logic
  reads the octal digits directly (verified: 1777 sticky, 0777 world-writable, 0660 group-writable).
- The collection README states it is the source of truth. Wiring it in as the gatherer behind
  `aac_facts_collector` is the next extraction step (E2), not this change.

### Changed

- **M365 CSV results export** (`scripts/m365_findings_report.py`): the DETAIL
  section is now one column per field (category, control, status, level,
  assessment, risk, basis, where, action, method, detail) instead of a
  sentence to parse.

### Changed — the demos split (restructure Phase 6)

- **Demo content moved to the [aac-demos](https://github.com/ynotbhatc/aac-demos)
  repository** (which pins this repo as its `product/` submodule at release tags):
  the entire `demos/` tree, the 7 demo EDA rulebooks, the RHPDS provisioning stack
  (10 playbooks + seed script + install guide — RHPDS is demo delivery), the 19
  demo job-template CaC entries, demo customer profiles, the demo bundle
  validator, and the two demo guides. `demo-datacenter` became its own
  repository ([aac-demo-datacenter](https://github.com/ynotbhatc/aac-demo-datacenter)).
- The core/demos boundary gate is now zero-tolerance (job-template path strings
  included); the install-config hygiene gate no longer scans a demos/ root.
- Last unified state is tagged `v2.9.0-pre-split`.

All notable changes to Ansible Automated Compliance (AAC).

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning is [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Two numbering schemes existed before 2.8.0, and this file is the one that
> continues.** This changelog and `CLAUDE.md` tracked a `2.x` lineage (2.0.0 →
> 2.7.0). The GitHub *releases* used an unrelated `0.x` scheme — "Beta Release
> 0.2" (tag `AnsibleAutomatedCompliance`, 2026-02-27) and "R0_2_0" (tag
> `PreRelease`, 2026-05-14) — with tag names that describe neither the version
> nor each other. Nothing reconciled them, and no release was ever cut from the
> `2.x` line.
>
> From 2.8.0 the `2.x` lineage is authoritative: `VERSION` holds it, this file
> records it, and the git tag is `vMAJOR.MINOR.PATCH`. The two `0.x` releases
> are left in place as historical artifacts rather than renamed. See
> `RELEASING.md`.

**On the policy library.** `policies/` is a git submodule with its own history.
Each release below records the commit it pins, which is the only version of the
policy content a given AAC release actually ships.

---

## [Unreleased]

### Changed — CIS RHEL 9 assessments follow the library's CIS v3.0.0 rebuild

- The `policies/` pin moves to rego `001dbe08`, where RHEL 9 is CIS Red Hat Enterprise Linux 9 Benchmark v3.0.0 (352 recommendations; profiles `level1_server` (default), `level2_server`, `level1_workstation`, `level2_workstation`). Every recommendation fails closed: a field the collector did not gather is reported as "evidence missing", never passed.
- The shared Linux collector (`ansible/tasks/collect_linux_compliance_facts.yml`) gains seven read-only blocks: kernel module availability / deny-listing / load state; running and persisted (systemd-sysctl precedence) kernel parameters; RPM package state and versions plus systemctl unit state (including `.socket` units); crypto policy, dnf, faillock / pwhistory, authselect, chrony, MTA listeners, firewalld zones, GDM dconf, `su` pam_wheel, `augenrules --check` and AIDE rules; file modes for SSH, sudo, critical account files, GRUB, rsyslog, audit tools and `/var/log`; password state and aging (no hashes), shells, root umask and root PATH ownership; one bounded sweep per local filesystem for unowned / ungrouped files, non-sticky world-writable directories and privileged (SUID/SGID) commands. Each block keeps the existing contract (`end:ok`, watchdog, `missing_cmd` / `truncated` never read as a pass).
- The shared mapper (`ansible/tasks/cis_linux_build_opa_input.yml`) emits the v3 input shapes from those blocks, plus mapper-only fields from evidence already collected (banner sensitive-information flags, banner / cron allow-deny groups, GID 0 accounts and groups, login.defs UMASK, rsyslog `config_raw`, separate rescue / emergency sulogin flags, the forwarding and route_localnet parameters). Package booleans are emitted only where the RPM database manages the system.
- On the synthetic RHEL 9 fixture `level2_server` goes from 99 pass / 253 fail (184 evidence missing) with the old mapper to 271 pass / 81 fail (1 evidence missing: 2.4.1.7, `/etc/cron.yearly` is absent, as on stock RHEL 9.8, and the library reads only its mode; the mapper reports `cron_yearly_exists: false`). A real RHEL 9.8 host run on 2026-10-22 found four more gaps, fixed here: a faillock.conf / pwhistory.conf whose lines are all comments read as not collected (now `no active settings`), unset TMOUT and GDM idle-delay read as missing (now 0, a fail), wireless driver modules were not collected, and an incomplete filesystem sweep (rootless podman storage) dropped known non-zero unowned counts (now kept as a lower bound with `truncated: true`; the privileged-command list carries a sentinel that no audit rule matches). Stored-facts rows collected before this change report the new fields as evidence missing until they are collected again.
- `tests/cis_nginx_1_20_test.rego` is re-pointed at the library's CIS NGINX v3.1.0 input contract (the v1.x helper rules it called were removed).

### Fixed — assessments that save facts on the controller failed with "sudo: command not found"

- Seven playbooks run with `become: yes` and delegate a task to `localhost`, typically "Save facts to local file". The delegated task inherited `become`, and the current execution environment has no `sudo`, so the task failed after the host had been assessed. The nightly AWS-lab run on 2026-10-17 hit it on Amazon Linux 2023. All 21 such tasks now set `become: false`; a scan of every play with `become: yes` finds no remaining localhost-delegated task without an explicit `become`.


### Fixed — the nightly AWS-lab CIS assessments had not reached an AWS host since 2026-09-29

Found 2026-10-14, fixed 2026-10-16. The nightly parent workflow reported success throughout because the child's failures feed only "always" edges.

- **Stale addresses.** Starting the lab syncs the EC2 inventory source as a launch dependency while the instances are still stopped, so every host got its private address; the 300-second inventory cache made the gather and the assessments reuse that sync. The source is now seeded as code (`seed_aws_lab_inventory_source.yml`) with `update_cache_timeout: 0`.
- **Wrong key.** The RHEL 9 and Amazon Linux assessment templates connected with the on-premises SSH key; the instances accept only the AWS lab key. The Ubuntu assessment had no signing key for its certification row and failed closed. Both corrected on the lab controller (the templates are not defined as code).
- **Junk evidence and a lab left running.** The "Store Compliance Results" node wrote placeholder rows with no hostname into the evidence store on every run (each assessment already stores its own row), and the stop node hung off its success path, so a failed assessment would have left the AWS lab running. `seed_cis_compliance_workflow.yml` now builds start → assessments → (always) stop, with no store node, resolves every object by name (its old ids had been reused by unrelated objects), and includes the Amazon Linux assessment.
- **The failure was invisible.** A parent workflow reports success when a child fails on an "always" edge. The platform readiness check gains `readiness_required_recent_workflows`: each named workflow's newest run must have succeeded within `readiness_recent_workflow_hours` (default 26), checked directly.
- **Review follow-up.** The stop node waits for all six assessments (`all_parents_must_converge: true`; with the default, the first assessment to finish, even a quick failure, would stop the hosts under the other five). A separate stop node on the start job's failure edge stops instances that a failed start left running, since no assessment runs and the converge node never fires. The EC2 source is looked up inside its inventory, so a same-named source in another inventory is never the one patched.


### Fixed — PostgreSQL tasks use `login_db` (community.postgresql 4.x removed `db`)

- 191 `postgresql_query` / `postgresql_script` / `postgresql_user` tasks across 61 playbooks and roles passed the database as `db:`. community.postgresql 4.0 removed that parameter ("Unsupported parameters for (community.postgresql.postgresql_query) module: db"), so any execution environment built with the current collection failed at the first database task; `login_db` is accepted by every supported version. Mechanical rewrite, no other change. Found by a reviewer running against a freshly built EE.


### Fixed — M365 persist preflight names the blank variable

- `aac.m365.m365_assessment` preflight: a debug line now says which of `m365_opa_url`, `pg_host`, `m365_db_user`, `m365_db_password` is BLANK (never the values) before the assertion fires; the failure message names the right variable (`m365_db_user`, which now defaults to `compliance_db_user` when set, else `postgres`) and the usual cause — an optional survey question left blank passes `""`, and the role fails closed on purpose (#626). A customer site hit the assertion "with all variables set" because the message pointed at `compliance_db_user`, a name the role never read.


### Fixed — CIP-010 baseline capture against the shipped schema

- `ansible/playbooks/cip_010_baseline_capture.yml` read and wrote columns the evidence table never had (`host`, `details`, `captured_at`, `score`, `passing_controls`, `trigger`), so every check-mode run failed and no capture could find its own row. It now reads `hostname` / `metadata` / `evaluation_timestamp`, stores both the baseline and the deviation check through `aac_store_results` (hash chain, append-only writer), records the capture as one control so the fail-closed nonempty gate accepts it, honours `pg_*` as well as `compliance_db_*`, and publishes `cip010_has_deviations` / `cip010_unauthorized` / `cip010_evidence_row_id` for workflows.


### Added
- **Install preflight: podman ≥ 5.8.2-6 gate for container-host topologies.**
  Rootless podman below that build could hard-link the host's `/dev/null` during
  image layer normalization and strip its world-write bits, breaking
  sudo/ssh/systemd redirects and surfacing as intermittent AAP gateway
  503 "No Healthy Upstream" errors that reinstalls only temporarily mask
  (root-caused by Red Hat engineering on a customer POC, 2026-09; fixed in
  podman 5.8.2-6.el9_8). `install_preflight.yml` now fails closed on vulnerable
  podman for `topology: containers` profiles; OpenShift profiles record n/a.
- **Install preflight: /dev/null integrity check for container-host topologies.**
  Companion to the podman gate: asserts /dev/null is a character device, mode
  666, hard-link count exactly 1. Links created by *pre-fix* podman extractions
  persist under the service account's container storage even after updating
  podman — and any /home permission-hardening sweep then chmods the shared
  inode, re-breaking /dev/null host-wide. Field-derived from the same customer
  POC: their org policy strips o+w under /home, which collided with the leftover
  link. Fails closed on `topology: containers`; n/a elsewhere.

### Fixed
- `RELEASING.md` v1.1 — the versioning section argued for a `0.x` lineage, based
  on the GitHub release titles rather than on this file, which has tracked `2.x`
  since 2.0.0. Two snippets were also not runnable as written.
- **Removed `collections/requirements.yml`**, which required `redhat.openshift`
  at project-sync time. AAP performs that install as root into the shared
  project cache, leaving `root:awx` directories the controller's task container
  cannot clear; the next sync then fails in `shutil.rmtree`, the project goes to
  `error`, and every job template using it fails at `elapsed: 0.07` before
  running anything. The collection was never used — every OpenShift object is
  read and written with `kubernetes.core`, which is a declared requirement of
  the EE. The
  recurring outage bought nothing. `collections/README.md` records why nothing
  should be added there again.

---

## [2.8.0] — 2026-08-29

First tagged release in 3.5 months. 257 pull requests since 2.7.0, which is itself the
finding that prompted the release process in `RELEASING.md`: work was shipping
continuously to `main` with no cut, no version, and no way for anyone to say
which build they were running.

Policy submodule pinned at `75bb5f1`.

### Added

**Compliance content**
- `aac.m365` Ansible collection — Microsoft 365 CIS benchmark: identity, admin
  centre, Intune, SharePoint and Teams collectors; results persisted to
  PostgreSQL with a Grafana dashboard.
- TSA Pipeline Security Directives registered as a framework.
- Kubernetes and OpenShift STIG wired into the framework catalog.
- `geisa.device_management` collection and GEISA device provisioning.

**Compliance Attestation Authority (CAA)**
- `compliance_certifications` schema and writer role.
- Cosign key-based signing of certification rows.
- CAA writes auto-derived from the framework catalog rather than hand-wired.
- CIS RHEL 8/9, NERC-CIP + CIP-015 INSM, and Digital Sovereignty wired as
  fleet-scoped CAA rows.

**OpenShift Compliance Operator**
- Collation of `ocp4-nerc-cip` results into AAC evidence.
- Gated drift remediation for CIP-010 R3.
- Unified NERC-CIP Grafana dashboard spanning host-based and cluster results.

**Demos**
- Windows Golden Image — drift detection and auto-remediation.
- AMI Golden Meter drift, with both webhook and EDA-triggered paths.
- Mythos patch lifecycle, with evidence provenance.
- RHEL 10 Showcase Lab — five AAP customer use cases.
- CIP-010 baseline capture and drift detection, single-click driver.

**Install and operations**
- Profile-driven install with preflight and verify gates.
- Single operator-owned install inventory (see **Changed**).
- Post-boot recovery hook — a reboot no longer leaves AAC down.
- Disk-backed OPA via initContainer, so loaded policies survive a restart.
- Domain execution environments for sovereignty, Windows and AMI.

**AI**
- Ansible Lightspeed remediation drafting. Proposal only: drafts are marked
  `evidence_source: ai_generated`, never applied, never scored, and never
  written into the evidence series.

**Validation — the layer that had none**
- `.github/workflows/ansible-validation.yml`: YAML parse, `ansible-playbook
  --syntax-check`, Jinja renderability, and repository hygiene policy on every
  PR touching `ansible/`.
- `.github/workflows/install-config-hygiene.yml`: no site addresses or
  credentials in shipped files, and operator config must stay untracked.
- `scripts/check_jinja_renderable.py`: every Jinja expression must lex.
- `scripts/check_playbook_contracts.py`: `hosts:` variables must be supplied by
  something.
- Policy rules backing these live in the library under `enforcement/repo/` and
  `enforcement/ansible/`, with unit tests.

### Changed

- **Install configuration is now one operator-owned file.**
  `install/aac-install-inventory`, patterned on the AAP containerized
  installer's `inventory`. Precedence is `profiles/<env>.yml` → `site_config.yml`
  → inventory/`-e`, with the operator's file winning. Previously profile
  defaults silently overrode the operator's own values, because `include_vars`
  outranks inventory variables in Ansible's precedence table.
- **`env_profile` no longer defaults to `lab`.** An unset profile fails the run
  with instructions instead of quietly pointing the install at the maintainer's
  lab.
- Framework-key bridges moved out of the policy library into this repository,
  keeping the library vendor-neutral.

### Removed

- **`ansible/vars/site_config.yml` and `ansible/vars/vault_secrets.yml` are no
  longer tracked.** Only their `.example` templates ship. Both were tracked
  *and* listed in `.gitignore`, which does nothing for an already-tracked file:
  the tracked copies carried lab addresses and three working credentials, every
  clone inherited them, and every local edit was a staged lab value waiting to
  be committed.

  **Upgrade step:** run `./scripts/aac-configure.sh` after pulling. It creates
  all three config files from their templates and never overwrites an existing
  one. 174 playbooks read `site_config.yml`, so a fresh clone will not run until
  this is done — the same contract the AAP installer has.

### Fixed

- **Shipped credentials removed.** The maintainer's Grafana password appeared in
  20 files; an AAP admin password sat in a copy-paste command in an install
  README; an Ansible Vault password — the credential protecting every other
  credential — was hardcoded as a default in `bootstrap_rhpds_environment.yml`;
  and a database password was shared by every RHPDS environment. One script
  built its password by concatenating three string literals at runtime, hiding
  it from a secret scan without making it any less hardcoded.
- **47 fail-open secret defaults** became `| mandatory`. On a correctly
  configured install nothing changes; on a misconfigured one the run now stops
  instead of authenticating with a password baked into the repository.
- **Lab addresses removed** from install READMEs, demo scripts and operator
  tooling, and from a generated auditor-facing document.
- **Six Jinja templates that could never render** — tasks that failed the moment
  they were reached. Two were in fact-gathering roles that had therefore never
  produced facts. Causes included `&` used as a bitwise operator (Jinja has
  none), `0o007` literals, `stat.mode` treated as decimal when it is an octal
  string, and escaped quotes inside Jinja expressions in block scalars.
- **An `ansible-lint` crash** that had been masking all of the above: a Jinja
  lexer error aborted the run and its traceback replaced every other finding.
- Playbooks that could not parse, including the documented CIS fact-collection
  entry point, whose `shell:` values contained awk programs with `': '` that
  YAML read as mappings.
- `loop_var` at task level instead of under `loop_control` in the CIP-008
  incident-response playbook.
- Two task files misfiled in `ansible/playbooks/` moved to `ansible/tasks/`.
- Grafana datasource health check that reported a false negative on every run.
- `framework` column omitted from evidence INSERTs, where it is `NOT NULL`.

### Security

- No credential literal, and no address belonging to one environment, may appear
  in a shipped file. Enforced in CI, not by convention.
- Operator config files must not be tracked by git. Enforced in CI, because a
  `.gitignore` entry cannot express it.
- A secret must not have a fallback default. Enforced in CI.

### Known limitations

Stated because a release that only lists wins is not a useful record.

- **Three roles cannot run.** `compliance_base`, `fisma_compliance` and
  `nerc_cip_compliance` include 18 task files that do not exist;
  `nerc_cip_compliance` contains only `main.yml`. `./scripts/validate_playbooks.sh`
  exits non-zero for this reason alone. Consider whether
  `nerc_cip_compliance` should exist at all — NERC-CIP assessment is already
  delivered through the playbook + OPA path.
- **The delivery layer is thinly tested.** 221 playbooks, 9 tests. The CI gates
  added here check structure, not behaviour.
- **`install/mac-aap/**` is allowlisted** by the hygiene gate. It is maintainer
  laptop tooling that legitimately carries lab identifiers, but it ships in a
  repository customers clone.
- `policy_sha` is NULL on assessment rows written by template 18, so those rows
  cannot state which policy version produced them.
- License mismatch: this repository is MIT, the policy library is Apache-2.0.

---

## [2.7.0] — 2026-06-26

### Added
- **EU Cyber Resilience Act (CRA) policy framework** — Regulation (EU) 2024/2847. 17 modules / 244 control checks / 65 tests / COVERAGE.md v0.5. Manufacturer + authorised representative + importer + distributor + online marketplace + OSS steward + FOSS exclusion + Annex II/IV/VII content + Article 11 substantial-modification + Article 14 24h/72h/14d cascade + evidence bridges to SLSA + ISO 27001 crypto. Endpoint `/v1/data/cra/main/compliance_report`.
- **`/main/compliance_report` contract on 30 frameworks** (was 6) — every framework with a `<key>.main` package now exposes the universal contract `{framework, compliant, total_controls, violations, violation_count, module_summary}`. Includes NIST 800-53 Rev 5 (7 families), NIST CSF 2.0 (all 6 functions), NIS2, CFR Part 11, FedRAMP, NIST AI RMF, DORA, HITRUST, NIST 800-82, NY DFS, SEC Cyber, SWIFT CSP, TISAX, CCPA, CSA CCM, EU AI Act, ISO 27701, NCSC CAF, NIST 800-171, STIG Kubernetes, STIG OpenShift 4.
- **mac-aap install** — third named AAP instance via OpenShift Local (CRC). `install/mac-aap/` runbook + Containerfiles + scripts + 4 demos (Day-2 Lifecycle, Golden Image, AI Governance, NIST OCP Assessment). All AAC services (OPA × 3, PostgreSQL, MCP, Grafana, Smart Meter sim) deployed as OpenShift resources inside CRC.
- **Headless-Chrome dashboard validator** — `install/mac-aap/scripts/check-dashboards-rendered.sh` loads each Grafana panel via `/d-solo/` and inspects the rendered DOM for "No data" markers. CI workflow `validate-mac-aap-dashboards.yml` runs static SQL validator on every dashboard JSON change.
- **Lab10 RHEL 10 Showcase demo on mac-aap** — `install/mac-aap/playbooks/seed_lab10_macaap.yml` wires the 8 Lab10 templates + workflow against the refactored topology-agnostic originals.
- **CAA (Certifiable Audit Artifact) item 2** — `compliance_certifications` schema + writer role for storing per-system certifications.
- **Vault file separation** — `vault_secrets.lab.yml.example` + `vault_secrets.rhpds.yml.example` for per-cluster credential isolation.
- **AAC strategic docs** — Certifiable Audit Results Status, Hybrid Certified Tools Architecture, Tool Certification Roadmap, Salesforce 3-Year AAP Adoption Timeline.

### Changed
- **Topology-agnostic playbook refactor** — 43 playbooks across 5 PRs (#236, #238, #239, #240, #241): Lab10 step playbooks + daily health-check + verify_installation + comply preflight + sentinel preflight + 8 report / notification playbooks + 8 credential-rotation playbooks + 19 seed_* template/workflow seeders. Pattern: drop `vars_files: vault_secrets.yml`, replace `{{ aac_host }}:port` with canonical site_config URL vars (`opa_security_url`, `opa_compliance_url`, `opa_ot_url`, `grafana_url`, `mcp_url`, `smart_meter_*_url`, `aap_url`, `pg_host`), parameterise `vault_aap_local_mcp_token` → `aap_token` extra_var. Surface of playbooks touching `{{ aac_host }}` went from **45 → 20**.
- **Mac-aap Lab10 forks consolidated** — `install/mac-aap/playbooks/lab10_*_macaap.yml` (3 forks) deleted; mac-aap seeder now points at the refactored originals in `ansible/playbooks/`.
- **`opa_framework_map`** — added `cra: compliance` so generic_framework_assessment can resolve CRA queries to opa-compliance (:8182).
- **Policies submodule pointer** advanced to include the rego_policy_libraries CRA + contract-expansion merges.
- **README badges** updated: Frameworks 55+ → 65+, Rego Policies 444+ → 505+.

### Documentation
- **`docs/` restructured** — 78-file flat directory categorized into `install/`, `integration/`, `architecture/`, `frameworks/`, `operations/`, `reference/`, `strategy/`. New `docs/README.md` index.

### Operational
- `aap-demo/` (RedHatOfficial clone for mac-aap install) added to `.gitignore`.

---

## [2.6.0] — 2026-04-28

### Added
- NCSC CAF 4.0 — 23 Cyber Outcomes (16 technical + 7 governance)
- Technical Debt scoring — per-domain hourly rates, OT/IT budget separation, 17 frameworks in debt heatmap
- Digital Sovereignty framework — 7 domains (Data Residency, Encryption, Sovereignty Level)
- DORA, NIS2, NY DFS, SEC Cyber, SWIFT CSP, HITRUST, TISAX, CFR Part 11, CIS GCP policies
- Config-as-code RHPDS bootstrap via `infra.aap_configuration` (13 YAML files)
- EDA Golden Image Enforcement — file-watch → drift detect → rollback → notify pipeline
- MCP governance policy (`governance/mcp/mcp_governance.rego`) — tool-call authorization
- OIDC token validation policy (`governance/oidc/oidc_token_validation.rego`)
- OSCAL 1.1.2 export playbook (`export_oscal_assessment.yml`) + Python mapper
- Single-workflow RHPDS provisioning ("AAC - Full RHPDS Provisioning" — 7-node chain)
- Per-cluster SSH credential support for parallel RHPDS provisioning
- Community files: CONTRIBUTING.md, SECURITY.md, CHANGELOG.md, issue templates, CODE_OF_CONDUCT.md
- opcr.io publishing via GitHub Actions

### Changed
- Repository structure simplified from ~30 top-level directories to ~10
- EE image upgraded to `quay.io/rh-ee-tcoulter/aac-compliance-ee:v1.2.0`
- AAP API path updated for 2.6: `/api/controller/v2/` (was `/api/v2/`)
- OPA version pinned to 1.10.0 across all CI and deployment

### Fixed
- Sovereignty Level Grafana panel — `textMode` value not name
- SOX package collision — renamed to avoid OPA eval_conflict_error
- NERC-CIP simplified package — `package nerc.cip.simplified` to avoid conflict with main
- EDA activation project=null bug — activations recreated with proper project/rulebook links

---

## [2.5.0] — 2026-03-28

### Added
- CIS RHEL 9 v2.0.0 — 338/338 controls (100%) across 14 modules
- Three-container OPA architecture (security :8181, compliance :8182, OT :8183)
- NERC-CIP CIP-002 through CIP-015 + INSM (CIP-015)
- AMI / NIST IR 7628 smart meter compliance
- IEC 62443 — all 51 System Requirements, SL 1–4 tiering
- PostgreSQL 15 compliance_results schema with JSONB violations
- Grafana compliance dashboards
- EDA integration for continuous drift detection

---

## [2.0.0] — 2025-12-01

### Added
- Initial multi-framework release (CIS RHEL 9, ISO 27001, SOC 2, PCI-DSS)
- OPA policy-as-code evaluation engine
- AAP 2.5 integration

---

> **On the older `2.x` entries.** 2.0.0 through 2.7.0 were recorded here but
> never tagged, so there is no release to link them to and no way to check out
> exactly what any of them shipped. 2.8.0 is the first entry in this lineage
> with a git tag behind it. That gap is the reason `RELEASING.md` exists.

[Unreleased]: https://github.com/ansible-automated-compliance/aac/compare/v2.8.0...HEAD
[2.8.0]: https://github.com/ansible-automated-compliance/aac/releases/tag/v2.8.0
