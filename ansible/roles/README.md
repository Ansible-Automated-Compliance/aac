# AAC roles

Roles under `ansible/roles/` are the product's shared building blocks. Playbooks in
`ansible/playbooks/` call them; nothing here is a demo or a lab fixture.

| Role | Purpose |
|---|---|
| `aac_bundle_consumer` | Pull, verify (ed25519), load and acknowledge a tenant's signed customer-policy bundle from the Customer Portal into a dedicated OPA container |
| `aac_compliance_db` | Deploy and initialise the containerised PostgreSQL compliance database |
| `aac_enforceauth_bridge` | Deploy the read-only Compliance-State API that feeds compliance state to EnforceAuth as authorisation context |
| `aac_facts_collector` | Collect the fact domains an assessment needs and assemble `aac_core_facts` (Linux, Windows, AWS detection) |
| `aac_findings_sync` | Derive first-class findings (identity, state, blast radius, target lists) from stored `compliance_results` evidence |
| `aac_mcp_server` | Deploy and manage the AAP MCP server container |
| `aac_opa_containers` | Deploy and manage the three purpose-specific OPA containers |
| `aac_oscap_ingest` | Parse an ARF (oscap or any ARF 1.1 emitter) and store the normalised result through `aac_store_results` |
| `aac_oscap_scan` | Run a read-only OpenSCAP XCCDF evaluation on a target host and fetch the ARF for ingest |
| `aac_post_boot` | Post-boot configuration of a freshly provisioned assessment host |
| `aac_store_certification` | The single authoritative INSERT into `compliance_certifications` (Certifiable Audit Artifact row with provenance and integrity hash) |
| `aac_store_results` | The single authoritative INSERT into `compliance_results`; every assessment playbook stores through it |

## Where the CIS fact collectors are

The per-domain CIS collectors (`gather_auditd_facts`, `gather_ssh_config`, `gather_pam_config`,
`gather_user_security`, `gather_firewalld_detailed`, `gather_grub_security`,
`gather_filesystem_config`, `gather_logging_config`, `gather_file_permissions`,
`gather_service_config`, `gather_network_config`) live in the `aac.cis_facts` collection at
`collections/ansible_collections/aac/cis_facts/roles/`. The legacy copies that used to sit in
this directory were removed on 2026-10-17; no playbook called them.

## Conventions

- One role, one job. Storage goes through `aac_store_results` or `aac_store_certification`,
  never through inline SQL.
- Defaults carry no lab hostnames or credentials; environment values come from the profile
  (`ansible/vars/profiles/`) or the inventory.
- `scripts/check_role_include_targets.py` (CI) verifies that every `include_tasks` /
  `import_tasks` target in these roles exists.
