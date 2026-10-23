# Estate continuity: retired, disappeared or not responding

**Version:** v1.0
**Authors:** Tim Coulter · Claude (Anthropic)

An assessment only judges the hosts it reaches. A host that stops answering, or
is deleted, produces no facts and so no failing result: it simply drops out of
the evidence. The estate continuity check closes that gap. Every night it
accounts for every host the estate is expected to contain.

| Piece | Where |
|---|---|
| Decision | OPA policy `estate_continuity.main` (rego library, `governance/estate_continuity`) |
| Collector | `ansible/playbooks/estate_continuity_check.yml` |
| Registry | `host_registry` (`ansible/files/host_registry_schema.sql`) |
| Decommission records | `ansible/vars/decisions/estate_continuity.yml` (from the `.example`) |
| Template and schedule | `ansible/playbooks/seed_estate_continuity_schedule.yml` → "AAC - Estate Continuity Check", daily 03:00 UTC |

## The rule

Silence is never retirement. A host leaves the estate cleanly only through a
decommission record that names the reference, the person and the date. A host
that vanishes without one is a finding, even when AAP's activity stream shows
who deleted it.

## What each host is checked against

| Input | Source |
|---|---|
| Still in an inventory? | AAP inventories named in `estate_continuity_inventories` |
| Does the provider still have it? | EC2 (`estate_continuity_aws_regions`); the provider is the authority on existence, so an inventory sync that drops stopped instances does not create disappearances |
| How old is its newest evidence? | `compliance_results` |
| What happened on the last attempt? | AAP job host summary: unreachable, failed or ok |
| Was it retired? | the decommission records, or a retirement already in the registry |
| Who removed it? | AAP activity stream host deletions |

## States

| State | Meaning | Finding? |
|---|---|---|
| active | evaluated within 26 h | no |
| late | last evaluation 26–52 h ago | advisory |
| new | first seen recently, not yet evaluated | advisory |
| stopped | the provider says powered off | advisory (configurable out of scope) |
| retired | a decommission record, and gone | no |
| retirement_incomplete | a record, but still in the inventory | advisory |
| stale_unreachable / stale_failing / stale_no_evidence / stale_not_targeted | no evaluation for 52 h; the last attempt explains why | **yes** (NIST CA-7) |
| missing | gone, with no record of any kind | **yes** (NIST CM-8, CIS 1.1) |
| removed_unrecorded | removed by a named actor, no decommission record | **yes** |
| unmanaged_running | running at the provider, in no inventory | **yes** (CIS 1.1) |
| zombie | recorded as retired, but answered afterwards | **yes** (CIS 1.2) |
| invalid_record | the host record could not be classified | **yes** |

Windows are policy input (`estate_continuity_config`: `freshness_hours`,
`stale_after_hours`, `stopped_in_scope`).

## Evidence

One `compliance_results` row per host per run, framework `estate_continuity`,
with the state and its reason in `metadata`. The registry is state, updated in
place; the rows are the evidence.

## Known limits

- **Host names must match.** Evidence is joined to the inventory by host name. Rows stored under an execution-context name (a pod name, a blank hostname) do not count for any host, so a host whose evidence is filed that way shows as stale. That is accurate about the evidence, and the fix belongs in the assessment that stored it (`resolve_evidence_provenance.yml`).
- **The registry starts on the first run.** A host deleted before the first run is unknown to it. `estate_continuity_seed_from_evidence: true` seeds from old evidence instead, at the cost of the naming problem above.
- **One page per inventory.** Inventories with more than 200 hosts stop the run rather than report the unread hosts as missing. Paging is the next step.
- **Providers:** EC2 today. Other providers (vCenter, OpenShift) report `unknown`, so inventory absence alone decides for them.
