> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx3, SPLIT-PORTSx3.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Digital Sovereignty Controls Reference

**70 controls across 7 domains**
**OPA Container:** `opa-compliance` (port 8182)
**Policy path:** `digital_sovereignty/`

---

## How Controls Work

Each control follows the same pattern:
1. **Ansible** collects facts from the target system/cloud environment
2. **OPA** evaluates the facts against Rego policy rules
3. Violations are returned with `control_id`, `severity`, and `message`

Input data is passed as a JSON object to the OPA REST API:
```bash
POST http://AAP_HOST:8182/v1/data/digital_sovereignty/main/report
Content-Type: application/json
{ "input": { ... } }
```

---

## Input Requirements by Domain

### Data Residency
**Required input fields:**
| Field | Type | Description |
|-------|------|-------------|
| `approved_jurisdictions` | `[string]` | ISO country codes e.g. `["AU","DE"]` |
| `approved_cloud_regions` | `[string]` | Cloud region IDs e.g. `["ap-southeast-2"]` |
| `cloud_resources` | `[object]` | Each resource needs `country`, `region`, `data_classification`, `stores_regulated_data`, `infrastructure_type` |
| `backup_configurations` | `[object]` | `backup_country`, `offsite_country` per resource |
| `dr_configurations` | `[object]` | `dr_country` per resource |
| `metadata_storage` | `object` | `location_country`, `in_approved_jurisdiction` |
| `telemetry_and_logs` | `object` | `location_country`, `in_approved_jurisdiction`, `vendor_access_to_logs` |
| `data_flows` | `[object]` | `source_country`, `destination_country`, `data_classification`, `transfer_mechanism_documented` |
| `data_flow_inventory` | `object` | `maintained` (bool), `last_review_date` (ISO 8601) |

**CSP access needed:** Read access to cloud resource metadata (region/location tags), storage bucket configs, database instance configs.

---

### Cryptographic Sovereignty
**Required input fields:**
| Field | Type | Description |
|-------|------|-------------|
| `cloud_resources` | `[object]` | `key_management` (`customer_managed`/`provider_managed`), `algorithm`, `byok_enabled`, `hyok_enabled`, `data_classification` |
| `hsm_configuration` | `object` | `deployed`, `type` (`fips_140_2_level3`/etc.), `location_country`, `vendor_access_possible`, `key_material_leaves_hsm` |
| `key_management_policies` | `object` | `rotation_policy_documented`, `rotation_frequency_days`, `dual_control_enforced`, `split_knowledge_enforced`, `escrow.exists` |
| `encryption_standards` | `object` | `algorithms_approved` (list), `tls_minimum_version`, `prohibited_algorithms` (list) |
| `encrypted_resources_in_transit` | `[object]` | `tls_version`, `cipher_suite`, `involves_regulated_data` |
| `code_signing` | `object` | `implemented`, `key_location_country`, `private_key_in_approved_jurisdiction` |

**CSP access needed:** KMS key policy read, CloudHSM/equivalent config, certificate manager, TLS policy configs.

---

### Infrastructure Sovereignty
**Required input fields:**
| Field | Type | Description |
|-------|------|-------------|
| `infrastructure_components` | `[object]` | `provider`, `provider_hq_country`, `physical_location_country`, `data_classification`, `subject_to_foreign_surveillance_law`, `foreign_government_access_risk`, `mitigation.encryption_before_upload` |
| `cloud_providers` | `[object]` | `hq_country`, `subject_to_cloud_act`, `sovereign_cloud_offering`, `data_processed_pct` |
| `hardware_components` | `[object]` | `manufacturer_country`, `firmware_origin_country`, `supply_chain_audited`, `known_vulnerabilities.hardware_backdoor` |
| `network_infrastructure` | `object` | `dns_provider.location_country`, `cdn.provider_hq_country`, `cdn.content_cached_in_approved_regions` |
| `concentration_limits` | `object` | `max_single_provider_pct`, `max_foreign_provider_pct` |
| `exit_strategy` | `object` | `documented`, `portability_tested`, `estimated_migration_days`, `data_portability_format_open` |

**CSP access needed:** Provider account metadata, billing/usage breakdown by provider, hardware inventory system.

---

### Software Sovereignty
**Required input fields:**
| Field | Type | Description |
|-------|------|-------------|
| `sbom` | `object` | `maintained`, `format` (`spdx`/`cyclonedx`), `last_updated`, `coverage_pct`, `includes_transitive_dependencies` |
| `software_components` | `[object]` | `vendor_country`, `source_available`, `audited`, `forced_update_mechanism`, `telemetry_to_vendor`, `telemetry_can_be_disabled`, `license_type`, `license_reviewed` |
| `update_mechanisms` | `[object]` | `update_type` (`manual`/`automatic`), `requires_approval_before_update`, `update_source_in_jurisdiction` |
| `software_provenance` | `object` | `signing.all_artifacts_signed`, `signing.key_in_approved_jurisdiction`, `verification.integrity_checked_on_deploy`, `verification.hash_validation` |
| `dependency_management` | `object` | `private_registry_used`, `registry_in_approved_jurisdiction`, `dependency_pinning_enforced`, `vulnerability_scanning.enabled`, `vulnerability_scanning.last_scan_date` |
| `code_repositories` | `[object]` | `location_country`, `hosting_provider_jurisdiction`, `access_controls_adequate` |

**CSP access needed:** Package registry configs, code repository metadata, CI/CD pipeline configs, artifact signing configs.

---

### Operational Sovereignty
**Required input fields:**
| Field | Type | Description |
|-------|------|-------------|
| `personnel` | `[object]` | `role`, `location_country`, `nationality_screened`, `access_level`, `vetting_current`, `foreign_government_connection` |
| `vendor_access` | `[object]` | `vendor_hq_country`, `access_type`, `sessions_monitored`, `sessions_logged`, `sessions_recorded`, `access_requires_approval`, `data_classification_accessed` |
| `support_contracts` | `[object]` | `support_personnel_location`, `right_to_refuse_foreign_access`, `data_handling_agreement`, `foreign_government_disclosure_clause` |
| `privileged_access_management` | `object` | `pam_solution_deployed`, `session_recording_enabled`, `credential_vaulting_enabled`, `just_in_time_provisioning`, `privileged_access_review_current`, `review_frequency_days` |
| `foreign_access_requests` | `object` | `policy_documented`, `legal_review_required`, `notification_to_data_owner`, `right_to_challenge` |
| `remote_operations` | `object` | `vpn_in_jurisdiction`, `jump_host_in_jurisdiction`, `remote_from_approved_countries_only` |

**CSP access needed:** IAM/identity system for personnel records, PAM tool API, access review records.

---

### Network Sovereignty
**Required input fields:**
| Field | Type | Description |
|-------|------|-------------|
| `bgp_configuration` | `object` | `autonomous_system_number_owned`, `route_filtering_enabled`, `rpki_deployed`, `route_origin_validation`, `peer_list_reviewed_date`, `routes_documented` |
| `dns_configuration` | `object` | `resolver_location_country`, `resolver_under_org_control`, `dnssec_enabled`, `dns_over_https_or_tls`, `public_dns_providers_blocked`, `zone_transfers_controlled`, `dns_logs_retained_days` |
| `internet_egress` | `object` | `single_controlled_egress_point`, `egress_country`, `traffic_inspected_at_egress`, `allowed_destinations_documented`, `blocked_destinations_documented` |
| `traffic_routing` | `object` | `sensitive_traffic_transits_foreign_country`, `traffic_routed_over_approved_paths`, `encrypted_if_transits_foreign` |
| `network_monitoring` | `object` | `netflow_collection_enabled`, `deep_packet_inspection.enabled`, `anomaly_detection_enabled`, `foreign_destination_alerting`, `retention_days` |
| `network_segments` | `[object]` | `location_country`, `handles_regulated_data`, `traffic_inspected`, `encrypted_in_transit`, `routing_policy_documented` |
| `private_connectivity` | `object` | `vpn_used_for_sensitive`, `vpn_termination_country` |

**CSP access needed:** VPC/network configs, DNS resolver settings, firewall/NGFW configs, flow log settings, BGP router configs.

---

### AI/ML Sovereignty
**Required input fields:**
| Field | Type | Description |
|-------|------|-------------|
| `ai_services` | `[object]` | `provider`, `provider_hq_country`, `deployment_type`, `inference_location_country`, `data_sent_for_inference`, `data_used_for_training`, `data_classification_processed`, `opt_out_of_training.available`, `opt_out_of_training.enabled`, `data_retention_by_provider_days` |
| `ml_training` | `object` | `training_data_location_country`, `training_infrastructure_country`, `data_leaves_jurisdiction_for_training` |
| `ml_models` | `[object]` | `origin`, `origin_country`, `audited_for_backdoors`, `model_weights_location_country`, `inference_in_jurisdiction` |
| `ai_governance` | `object` | `policy_documented`, `approved_ai_services_list`, `shadow_ai_controls`, `data_handling_procedures`, `human_oversight_for_decisions` |
| `ai_output_controls` | `object` | `outputs_reviewed_before_action`, `output_logging_enabled`, `output_jurisdiction` |

**CSP access needed:** AI/ML service configs (SageMaker, Azure ML, Vertex AI), API gateway logs for AI calls, model registry metadata.

---

## Control Severity Definitions

| Severity | Meaning | Effect on Level |
|----------|---------|-----------------|
| `critical` | Immediate sovereignty breach — data or keys outside jurisdiction, no mitigations | Forces `NON_SOVEREIGN` regardless of score |
| `high` | Significant risk — controls missing but not yet a confirmed breach | Prevents `SOVEREIGN`; may prevent `HIGH_ASSURANCE` |
| `medium` | Documentation or procedural gaps | Reduces score; does not block top levels |

---

## Frequently Skipped Controls (and Why They Fail)

| Control | Common Failure | Fix |
|---------|---------------|-----|
| DR-002 | Sovereign data in public S3/Blob | Move to on-prem or sovereign cloud tier |
| CS-002 | HYOK not enabled for sovereign workloads | Configure HYOK in your KMS (Thales, AWS XKS, Azure mHSM) |
| CS-008 | Key escrow with foreign vendor | Remove escrow or ensure escrow provider is in-jurisdiction |
| IS-002 | Unmitigated CLOUD Act exposure | Enable `encryption_before_upload: true` or use sovereign cloud |
| IS-009 | Exit strategy not tested | Run data portability drill, update `portability_tested: true` |
| SS-004 | Automatic OS/package updates enabled | Require approval before updates (`requires_approval_before_update: true`) |
| SS-007 | Artifacts not signed | Implement sigstore/cosign or GPG signing in CI pipeline |
| OS-003 | Privileged user with foreign government connection | Review access, revoke if required |
| NS-001 | Using 8.8.8.8 or 1.1.1.1 for DNS | Deploy in-jurisdiction recursive resolver |
| AI-001 | Regulated data sent to ChatGPT/Gemini/Claude (SaaS) | Route through self-hosted or sovereign-cloud AI only |
| AI-005 | ML training in foreign cloud | Use in-jurisdiction GPU infrastructure or federated learning |

---

## Example Assessment Commands

```bash
# Full assessment (all 7 domains)
curl -X POST http://AAP_HOST:8182/v1/data/digital_sovereignty/main/report \
  -H 'Content-Type: application/json' \
  -d @examples/digital_sovereignty/compliant.json | jq '.result.sovereignty_level'

# Single domain check
curl -X POST http://AAP_HOST:8182/v1/data/digital_sovereignty/ai_sovereignty/report \
  -H 'Content-Type: application/json' \
  -d @examples/digital_sovereignty/compliant.json | jq '.result'

# Via AAP workflow (recommended)
# Resources → Templates → AAC - Digital Sovereignty Workflow
# Survey: select domains → provide input file path → Launch
```
