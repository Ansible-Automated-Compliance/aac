# aac.m365

Microsoft 365 compliance assessment for Ansible: fact-collection modules
and a role that runs a complete **CIS Microsoft 365 Foundations Benchmark
v7.0.0** assessment end to end.

## Why three authentication surfaces

No single Microsoft API reaches the whole benchmark. Of its 160
recommendations, roughly 29 are audited through Microsoft Graph — the
rest need PowerShell or the Fabric admin API. A Graph-only collection
caps out below 20% coverage, so this one speaks all three:

| Surface | Sections | Auth |
|---|---|---|
| Microsoft Graph | 1, 4, 5, and DNS-based mail controls | client credentials |
| Exchange Online PowerShell | 2, 3, 6 | app-only **certificate** |
| Teams / SharePoint PowerShell | 7, 8 | app-only certificate |
| Fabric admin API | 9 | client credentials |

Exchange Online PowerShell does **not** accept a client secret. A
certificate is required, along with the `Exchange.ManageAsApp`
application permission and an assigned Entra directory role.

## Fail-closed collection

Every collector records what it could **not** read rather than emitting a
default. A permission gap, an absent cmdlet, or a tenant on a plan
without Defender for Office 365 produces an explicit `unavailable` entry
naming the controls it blocks — never a silent success.

This matters more than it sounds. A collector that returns an empty list
when it lacks permission is indistinguishable from one reporting a
correctly-configured tenant, and an evaluating policy will read it as a
pass. The collectors here return `None` and a reason instead.

## Quick start

```yaml
- hosts: localhost
  roles:
    - role: aac.m365.m365_assessment
      vars:
        m365_tenant_id: "..."
        m365_client_id: "..."
        m365_client_secret: "{{ vault_m365_client_secret }}"
        m365_organization: "contoso.onmicrosoft.com"
        # Sections 2, 3, 6, 7 and 8 additionally need:
        m365_certificate_path: /etc/aac/m365/app-cert.pfx
        m365_certificate_password: "{{ vault_m365_certificate_password }}"
        m365_certificate_thumbprint: "{{ vault_m365_certificate_thumbprint }}"
        m365_sharepoint_admin_url: "https://contoso-admin.sharepoint.com"
```

Set `m365_include_powershell_sections: false` to run Graph-only. The
report records the skip rather than implying those sections passed.

## Execution environment

The PowerShell-backed sections need `pwsh` plus
`ExchangeOnlineManagement`, `MicrosoftTeams` and `PnP.PowerShell`.
`Microsoft.Online.SharePoint.PowerShell` is Windows-only and cannot be
used on Linux, so SharePoint is collected with PnP.

Published DNS. SPF, DKIM and DMARC (2.1.8-2.1.10) are read from the
records actually published for each verified customer domain (TXT at the
domain, TXT at `_dmarc.<domain>`, CNAME at `selector1|2._domainkey.<domain>`)
with the EE's resolver. This needs the `dnspython` Python library; without
it every customer domain is reported "evidence missing: DNS lookup not
available", never compliant.

## Attestations

Controls the policy cannot measure (its `no_collector_path` ledger) are
attested through `m365_attestations`, the same contract as the Windows
collector's `cis_windows_attestations`:

```yaml
m365_attestations:
  - control_id: "5.2.4.1"
    observed: true
    attested_by: "Jane Operator, Identity team"
    attested_on: "2026-11-18"
    evidence_ref: "CHG0012345"
```

The ids are checked against the ledger the policy reports, so a measured
control cannot be attested away; `observed: false` is refused (leave the
control out instead, and it is reported as not attested).

## Stored counts

`passed_controls` counts only controls the policy evaluated and found
compliant. A control that was not evaluated is stored in
`metadata.not_evaluated_count` / `not_evaluated_control_ids`, never as
passed; `metadata.count_basis` says whether the counts came from the
policy's per-control `control_results` or from its messages.

## Shape capture (diagnostic)

Some collector questions can only be settled against a real tenant: how
an enum serialises, what an empty result looks like, the nested shape of
properties such as `AllowedDomains`, `RecipientTags` or `AssignedRoles`.
Run one assessment with

```yaml
m365_shape_capture: true
m365_shape_capture_dir: /tmp/aac_m365_shape   # default: $TMPDIR (or /tmp)/aac_m365_shape
```

and the role, after collection, records the SHAPE of every collected
fact: JSON types, list lengths, the union of field names with each
field's types, and distinct values only for an allowlist of closed
configuration enums, booleans and numeric settings
(`plugins/filter/m365_shape.py`, `VALUE_ALLOWLIST`). Names, addresses,
domains, tenant and object ids, mailbox data and free text are never
recorded; maps keyed by ids or names list only their key count.

It lands in three places, because an AAP execution environment's files
are discarded when the job ends: the file
`<m365_shape_capture_dir>/m365_fact_shape_<UTC timestamp>.json`, the
job's artifacts (`set_stats` key `m365_fact_shape`, visible on the AAP
job and passed down a workflow), and the job output. The assessment
itself runs and persists as usual. Leave it off for routine runs.

## Modules

| Module | Section | Source |
|---|---|---|
| `m365_admin_center_facts` | 1 | Graph |
| `m365_defender_ps_facts` | 2 | Exchange PowerShell |
| `m365_purview_ps_facts` | 3 | Security & Compliance PowerShell |
| `m365_intune_facts` | 4 | Graph |
| `m365_entra_facts` | 5 | Graph |
| `m365_exchange_ps_facts` | 6 | Exchange PowerShell |
| `m365_sharepoint_ps_facts` | 7 | PnP PowerShell |
| `m365_teams_ps_facts` | 8 | Teams PowerShell |
| `m365_fabric_admin_facts` | 9 | Fabric admin API |

## Evaluation

The modules emit facts only. Evaluation is done by Rego policies
published separately at
[rego_policy_libraries](https://github.com/ynotbhatc/rego_policy_libraries)
under `benchmarks/cis/saas/m365_v7/`, queried through Open Policy Agent.
The collection does not embed policy logic, so the benchmark can be
updated without changing collection code.

## Relationship to CIS

This collection is not affiliated with or endorsed by the Center for
Internet Security. It collects Microsoft 365 configuration state; the
CIS Microsoft 365 Foundations Benchmark is published by CIS and is
subject to their terms of use. Control identifiers are referenced so
results can be traced; recommendation text is not reproduced here.

## Licence

Apache-2.0.
