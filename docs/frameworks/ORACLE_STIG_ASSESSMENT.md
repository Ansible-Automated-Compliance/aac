# DISA STIG assessment for Oracle Linux and Oracle Database 19c

**Version:** v1.0
**Date:** 2026-10-13
**Author:** Tim Coulter + Claude (Anthropic)

AAC assesses an Oracle Linux 8/9 host (and RHEL 8/9, which share the contract)
and an Oracle Database 19c instance against the DISA STIGs, stores the result as
evidence in `compliance_results`, and exports it as NIST OSCAL assessment
results and SARIF 2.1.0. The policy content is in the Rego library
(`policies/benchmarks/stig/{oracle_linux_9,oracle_linux_8,rhel_9,rhel_8,
oracle_database_19c}`, library v2.4.2); this document is the product path that
feeds it.

## The path

| Step | Oracle Linux / RHEL | Oracle Database 19c |
|---|---|---|
| Collect | `ansible/tasks/collect_linux_compliance_facts.yml` (shared) + `ansible/tasks/collect_linux_stig_facts.yml` (STIG supplement: sysctl, module blacklists, STIG packages and services, repo gpgcheck, crypto policy, faillock, sssd/PIV, dconf, FIPS, GRUB, permission sweeps, unsigned packages, trust anchors, AIDE, cron.allow) | `ansible/tasks/collect_oracle_db_facts.yml`: the STIG's own check queries (`ansible/playbooks/files/oracle_stig_collect.sql`) through `sqlplus / as sysdba` as the Oracle owner, plus listener.ora, sqlnet.ora, cman.ora, fips.ora, extproc.ora, `lsnrctl status` Security, and the modes of ORACLE_HOME, diag, data, redo, control and archive directories |
| Map | `ansible/tasks/stig_linux_build_opa_input.yml` | `ansible/tasks/oracle_db_build_opa_input.yml` |
| Evaluate | `POST {{ opa_security_url }}/v1/data/stig/<platform>/main/compliance_report` | `POST {{ opa_security_url }}/v1/data/stig/oracle_database_19c/main/compliance_report` |
| Store | `aac_store_results` → `compliance_results` + CAA row | same |
| Export | `export_oscal_assessment.yml` / `export_sarif_assessment.yml` with `framework=stig_oracle_linux_9` | same with `framework=stig_oracle_database_19c` |

Playbooks: `ansible/playbooks/stig_linux_assessment.yml` (platform read from
the distribution, or `stig_framework`), `ansible/playbooks/stig_oracle_database_19c_assessment.yml`.
Workflow: `ansible/playbooks/seed_oracle_stig_workflow.yml` creates
"AAC - Oracle STIG Assessment and Export" (sync → Linux → database → OSCAL ×2 → SARIF ×2).

## Rules of the path

- **Nothing is fabricated.** A fact the collector did not gather is not in the
  input; the module reports that rule Open. The Linux mapper and the Oracle
  mapper never carry a constant that reads as "configured".
- **Fail-closed at OPA.** Both playbooks refuse to store when OPA did not answer,
  when the report has no `facts_supplied: true`, or when it is empty. An empty
  input reports every rule Open with a `FAIL-CLOSED` finding.
- **Allowlists only remove.** The Oracle STIG says "if not documented and
  authorized, this is a finding" for object owners, direct admin privileges,
  database links, WITH ADMIN OPTION grants, PUBLIC object privileges, default
  admin roles, components and options. The site lists what is documented in
  `ansible/vars/oracle_stig_attestations.yml` (`oracle_authorized_*`); the
  mapper subtracts those rows from what the STIG query returned. Nothing is
  added.
- **Attestations are named.** The attestation map has 51 booleans in
  `oracle_stig_attestations`: 45 rules whose whole check is a documentation or
  procedure review, two hybrid rules that need a query result *and* a review
  (O19C-00-002000 auditing events, O19C-00-011800 DBA OS accounts), and four
  "not a finding if the AO documented that…" exceptions (extproc authorized,
  encryption not required, data-at-rest encryption not required, integrity
  protection not required). Every one is false until a named person
  (`oracle_stig_attested_by`) has done the review. The stored row records how
  many were true and who attested.
- **Patches need the expected id.** O19C-00-018600 passes only when
  `oracle_expected_patch_id` (from the quarterly CPU notice) is among the
  SUCCESS entries of `DBA_REGISTRY_SQLPATCH`. Without it the rule stays Open.
- **No secrets leave the host.** `/etc/shadow` yields account names with an
  empty password field, never hashes; sssd.conf is grepped for four keys;
  the Oracle password file and GRUB user.cfg are stat'ed or counted, not read;
  sqlplus uses OS authentication.

## Running it without an instance

`stig_oracle_database_19c_assessment.yml` accepts `oracle_facts_file`, a
previously collected `oracle_raw` JSON. The shipped
`tests/stig_mapper/fixture_oracle19c_raw.json` is a synthetic hardened
instance (no real host, RFC 5737 addresses). A row stored from a file carries
`metadata.facts_source = "file"` and the report says so; present it as the
shape of the evidence, not as an assessment of a system.

## Proof without AAP

`tests/stig_mapper/` renders both mappers with Ansible's own engine against the
fixtures and evaluates the result against the library (see its README). As
shipped: Oracle Linux 9 fixture 92/93, RHEL 9 140/143, Oracle Linux 8 67/68,
RHEL 8 71/73; Oracle Database 19c 43/96 with no attestations and empty
allowlists, and 96/96 with the 47 review attestations true (the four exceptions
stay false) and the fixture's owner, database link, admin role, component,
option and patch id listed as authorized. `tests/test_sarif_mapper.py` and
`tests/test_oscal_mapper.py` prove STIG object findings export under their STIG
id (`OL09-00-002413`) with CAT I/II/III folded to high/medium/low.

## What the exports look like

Both exporters name the STIG control, with one difference in severity:

- the **product** exporters (`scripts/sarif_mapper.py`, `scripts/oscal_mapper.py`,
  reading `compliance_results`): SARIF `ruleId` `stig_oracle_linux_9/OL09-00-002413`,
  message = the DISA rule title plus the fix text, CAT I/II/III folded to
  `high`/`medium`/`low` (`level` error/warning/note, GitHub `security-severity`
  8.0/5.0/3.0) with the original label kept as `stig_severity`;
- the **library** exporters (`converters/exports/{sarif,oscal,ocsf}` in rego
  v2.4.2, reading an `opa eval` report): `ruleId` `stig_oracle_linux_9-OL09-00-002413`,
  `properties.severity` = `CAT I` as the module states it, and OSCAL findings
  targeting the control's statement in the library's catalog.

## Known limits (2026-10-13)

- The Oracle Linux modules cover 93 (OL9) and 68 (OL8) of 450 / 378 DISA rules;
  RHEL 9 143 of 450. The collector gathers for the whole RHEL 9 contract, so
  rules added to the modules evaluate without collector changes.
- `O19C-00-011700` reads `SQLNET.ALLOWED_LOGON_VERSION_SERVER` from the default
  `$ORACLE_HOME/network/admin`; set `TNS_ADMIN` in `oracle_env_file` when the
  site uses another location.
- Windows-hosted Oracle Database is not collected (the STIG's Windows checks are
  not implemented).
- The CIS Oracle Database 23ai module shares the `input.oracle` contract but
  reads grants, audit options and listener parameters this collector does not
  yet gather; running it on this input reports those Open. Collector extension
  is the next step.
- Not run against a live Oracle instance in the lab yet; the SQL is the STIG's
  own text and parses under the 19c JSON functions, but the first live run
  should be watched for a view that errors (the fact is then missing and listed
  in `system_info.facts_missing`).
