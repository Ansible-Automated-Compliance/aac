# aac.panos

Collects what the **CIS Palo Alto Firewall 11 Benchmark v1.2.1** policy needs from a
PAN-OS firewall and maps it to the policy's input.

The policy is `cis_palo_alto_panos` in the policy library
(`policies/benchmarks/cis/network_devices/palo_alto/`): 79 recommendations, 66
decided from the configuration and 13 attested. This collection supplies the
facts; `ansible/playbooks/cis_palo_alto_panos_assessment.yml` runs the
assessment and stores the result.

## What it does on the firewall

Three read-only operational requests to the XML API, nothing else:

| Request | Used for |
|---|---|
| `show config running` | every configuration recommendation |
| `request license info` | 6.8 and 6.22-6.25, which apply only when a subscription is active |
| `show system info` | hostname, model, serial and PAN-OS version stored with the result |

It uses `ansible.builtin.uri`. The execution environment needs **no** Palo Alto
collection and no extra Python library. `defusedxml` is used when present.

## What never leaves the collector

The running configuration contains password hashes, pre-shared keys and SNMP
secrets. The mapper copies only the settings the policy reads. Where the policy
needs to know that a secret is set (the SNMP v3 trap password), it sends the
marker `(set)`. The API tasks run with `no_log`, and the raw replies are
discarded as soon as the facts are built.

## Setting it up in AAP

**1. Credential type** (Credential Types, Add). Input configuration:

```yaml
fields:
  - id: api_key
    type: string
    label: PAN-OS API key
    secret: true
required:
  - api_key
```

Injector configuration:

```yaml
extra_vars:
  panos_api_key: '{{ api_key }}'
```

Create a credential of this type with the API key of a **read-only** admin
account whose role allows XML API operational requests. Never put the key in a
playbook, inventory, survey default or `-e` on a command line.

**2. Inventory.** One host per firewall in a group named `panos_firewalls`
(or pass `panos_hosts`), `ansible_host` set to the management address. Panorama
is not a target; list the firewalls.

**3. Framework.** Enrol and load `cis_network_devices` (it carries
`cis_palo_alto_panos`) so the policy is in OPA.

**4. Job template.** Playbook `ansible/playbooks/cis_palo_alto_panos_assessment.yml`,
the inventory above, the PAN-OS credential and the AAC database credential.

## Variables

| Variable | Default | Meaning |
|---|---|---|
| `panos_api_key` | none (required) | from the credential |
| `panos_host` | `ansible_host` | management address |
| `panos_port`, `panos_scheme` | `443`, `https` | where the API answers |
| `panos_validate_certs` | `aac_validate_certs`, else `true` | certificate checking |
| `panos_vsys` | `vsys1` | virtual system assessed |
| `panos_cis_level` | `2` | CIS profile, 1 or 2 |
| `panos_site` | `{}` | zone and URL classification, below |
| `panos_attest` | `{}` | attestations, below |
| `panos_store_results` | `true` | `false` assesses and prints without storing |

### Site classification

The benchmark asks about "untrusted zones" and "the Internet". The device
cannot say which of its zones those are, so the operator does. A list left out
makes the recommendations that need it report evidence missing.

```yaml
panos_site:
  untrusted_zones: [untrust, guest]
  internet_zones: [untrust]
  url_block_categories: [malware, phishing, command-and-control]
```

### Attestations

Thirteen recommendations are a human judgement. Each is a finding until
attested `true`.

| Name | Recommendation |
|---|---|
| `management_permitted_ips_reviewed` | 1.2.1 |
| `management_profile_permitted_ips_reviewed` | 1.2.2 |
| `admin_web_certificate_valid` | 1.2.5 |
| `vpn_certificate_valid` | 1.6.3 |
| `ikev2_post_quantum_ppk_enabled` | 1.7.1 |
| `user_mapping_verified_in_logs` | 2.1 |
| `userid_account_minimal_groups` | 2.5 |
| `userid_account_no_interactive_logon` | 2.6 |
| `userid_account_no_remote_access` | 2.7 |
| `wildfire_file_size_limits_reviewed` | 5.1 |
| `wildfire_cloud_region_approved` | 5.7 |
| `ssl_inbound_inspection_reviewed` | 8.2 |
| `decryption_certificate_trusted` | 8.3 |

## Types

The device returns every value as text. Whole-number settings the policy reads are sent as numbers; yes/no settings are sent as the device wrote them (`yes` / `no`); attestations are booleans. A value that should be a whole number and is not is passed through unchanged, and the policy reports it as invalid evidence.

## How absence is treated

- A section the device does not have (no HA, no password complexity) is sent
  empty, so the policy judges it as a finding rather than "evidence missing":
  the configuration was read in full.
- License information comes from a second request. If that request fails, the
  key is left out and 6.8 and 6.22-6.25 report evidence missing.
- A setting the configuration does not state is not filled in. PAN-OS omits
  settings left at their default; the policy reads an absent yes/no as "no".

## Limits

- **Not yet run against a real firewall.** The mapper was built from the PAN-OS
  XML structure and checked against Palo Alto Networks' public iron-skillet
  day-one configurations for PAN-OS 10.2 and 11.0, and end to end against the
  simulator below. Run it with `panos_store_results: false` against a
  non-production firewall first and compare a few findings with the device.
- **Policy pushed from Panorama** is not part of a firewall's local running
  configuration. A firewall whose rules and profiles all come from Panorama
  will report the rule and profile recommendations as failing or evidence
  missing. Reading the merged configuration is not implemented.
- **One virtual system per run** (`panos_vsys`). Shared objects are included.
- Zone-protection scan entries have no enable flag in the configuration; an
  entry is treated as on when it exists with an action other than `allow`.
- The element names for WildFire inline cloud rules (5.8) follow the policy's
  input contract and were not seen in a device configuration.

## Simulator

`examples/simulators/network/network_sim.py` answers the same three requests on
port 8093 (`POST /api/`, key in `X-PAN-KEY`) and serves
`panos_running_config.xml`, a deliberately weak configuration. Point the
assessment at it with `panos_scheme: http`, `panos_port: 8093`.

## Tests

```bash
python -m pytest collections/ansible_collections/aac/panos/tests/unit tests/test_network_sim_panos_api.py
python3 tests/panos_collector/score_fixture.py --opa "$(command -v opa)"   # mapper + policy verdicts
```
