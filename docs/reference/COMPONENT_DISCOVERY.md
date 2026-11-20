# Component discovery: which technology runs on which host

**Version:** v1.2
**Authors:** Tim Coulter, Claude (Anthropic)

AAC already stores per-host facts (`host_facts`) and turns coarse signals such as the operating system and the cloud provider into enabled policy bundles. Component discovery adds the missing record: which technology components (a database server, a Kubernetes control plane, an automation controller) run on which host.

This is step 1. It detects components from facts that are already stored. It connects to no managed host, launches no collector and changes no enabled framework.

## The two maps

| Map | Where it lives | Who maintains it | Content |
|---|---|---|---|
| Detection catalog | `ansible/vars/component_catalog.yml` (copied to the `component_catalog` table on each run) | Shipped with the product, versioned by `catalog_version` | For each component: the signals that identify it, its kind, its collector, its policy loader keys, capability hints |
| Per-host component map | `host_components` table | Built only by discovery | One row per host and component: status, confidence, evidence, the catalog version that identified it, first and last seen, the facts row it came from |

Operator overrides are a third, separate record (`component_overrides`). The views apply them. The detection columns of the map always show what detection found.

## Running it

| Item | Value |
|---|---|
| Playbook | `ansible/playbooks/discover_host_components.yml` |
| Job template | `AAC - Discover Host Components` (`AAC_Discover_Host_Components` in the extended install seeder) |
| Runs on | `localhost`, against the compliance database |
| Run after | `AAC - Gather Facts` |
| Detection logic | `scripts/component_discovery.py` (tested by `tests/test_component_discovery.py`) |
| Schema | `ansible/files/component_discovery_schema.sql`, applied on every run; `CREATE ... IF NOT EXISTS`, `CREATE OR REPLACE VIEW` and `ADD COLUMN IF NOT EXISTS` on its own tables only |

| Variable | Set where | Default | Meaning |
|---|---|---|---|
| `component_stale_after_days` | Survey, 1 to 365 | `7` | A detection whose facts are older than this is labelled "no newer facts" |
| `component_override_soon_days` | Survey, 1 to 90 | `14` | Window for "overrides expiring soon" in the summary |
| `component_override_max_days` | `site_config.yml` | `90` | The longest an override may run, counted from the run that reads it |
| `component_override_approvers` | `site_config.yml` only (read from the file, never from a variable) | empty | People who may approve an override that hides a privileged component. With an empty list every such override is refused |
| `component_override_entries` | `site_config.yml` | contents of `ansible/vars/component_overrides.yml` | Operator overrides |
| `component_catalog_file`, `component_overrides_file` | `site_config.yml` | the shipped files | Must stay inside the project checkout |

### Launch rules

The job holds the database credential, so what a launcher can change is limited.

| Rule | Effect |
|---|---|
| The seeded job template has `ask_variables_on_launch: false` | A launcher can set the two survey fields above, each a bounded integer, and nothing else |
| The database host must be the `pg_host` that `ansible/vars/site_config.yml` names | The playbook reads the value from the file itself (following `"{{ aac_host }}"` inside the file) and refuses to run when the host it was given differs, when the file is missing, or when the value cannot be checked |
| The catalog and override files must be inside the project checkout | A path that resolves outside it, directly, through `..` or through a symbolic link, is refused before the file is read |
| Tuning values must be within bounds | The playbook checks the same ranges as the survey |

The job prints a summary and publishes it with `set_stats` under `component_discovery`: components per host, components detected with no collector, counts of running services and ports that were not recognised, entries with no newer facts, entries no longer present, privileged services, client tools found without the server, overrides in force and overrides expiring soon.

## Signals and strength

| Signal kind | Read from the stored facts | Strength | Can identify a component alone |
|---|---|---|---|
| `package` | `packages.installed` (package name) | Strong for "installed" | Yes |
| `service` | `services.all`, `services.enabled_at_boot` | Strong when the unit is running or enabled | Yes, when running or enabled. A unit file that is neither is supporting evidence only |
| `process` | `processes.processes_raw` (command name) and the process named on each listening socket | Medium | Yes |
| `container_image` | `containers.running[].image` | Medium, or strong where the catalog entry says so | Yes |
| `port` | `network.listening_ports` | Weak | Never |

Each signal also has a role.

| Role | Meaning |
|---|---|
| `server` (default) | Can identify the component |
| `client` | A client tool, for example `kubectl` or the `postgresql` client package. It is recorded and reported as "client tools only". It never identifies the server component |
| `supporting` | Recorded as evidence when the component is otherwise detected. It never identifies the component alone |

## Confidence and run state

Confidence is derived from the kinds of signal that matched. Only server-role signals other than ports count.

| Confidence | Rule |
|---|---|
| `high` | A running service, or a strong container image; or two different kinds of identifying signal (for example package and process); or an identifying process that holds one of the component's own ports |
| `medium` | One kind of identifying signal only: a package alone, a process alone, a medium container image alone, or a service that is enabled but not running |
| no detection | Only ports, client tools, or unit files that are neither running nor enabled matched. Nothing is written to the map |

| Run state | Rule |
|---|---|
| `running` | A running service, a process or a running container matched |
| `installed` | Only a package, or a service that is enabled but not running, matched |

A port that matches a catalog entry with nothing else is listed under "running, not recognised" with the candidate component named in `port_also_used_by`.

## Catalog entry fields

| Field | Meaning |
|---|---|
| `key` | Stable identifier (lower case, digits, underscore) |
| `name` | Display name |
| `kind` | One of the values in the catalog's `kinds` list |
| `collector` | Name of the collector that gathers this component's own facts, or `none yet` |
| `loader_keys` | Loader keys from `ansible/vars/framework_catalog.yml` whose policies assess the component |
| `privileged` | Capability hints, each true or false: `act` (can act on other systems), `map` (holds a map of the estate), `rank` (reveals which systems matter most) |
| `signals` | List of `{kind, match, role, strength}`; `match` is a shell-style pattern, compared without regard to case |

The catalog also carries `base_os`: service units and listening sockets that ship with the supported operating systems. They are left out of "running, not recognised". A base listener is an entry of process name, protocol and port, with a bind scope (`loopback`) where one applies, for example `chronyd` on `udp/323` on loopback. All of them must match. A process that carries the name of a base daemon but listens anywhere else is reported as not recognised.

To add a component: add an entry, bump `catalog_version`, run `python3 scripts/component_discovery.py check-catalog` and `python3 -m pytest -q tests/test_component_discovery.py`. Use package, unit and process names taken from the vendor's documentation or from a host that runs the product.

## Tables

### `host_components`

| Column | Meaning |
|---|---|
| `host_id`, `hostname` | The host, as stored in `host_facts` |
| `component_key` | Catalog key |
| `status` | `detected` or `not_seen` |
| `run_state` | `running` or `installed` |
| `confidence` | `high` or `medium` |
| `signal_kinds` | The identifying kinds of signal that matched |
| `evidence` | Every matched signal: kind, catalog pattern, matched value, detail, strength, role |
| `catalog_version` | The catalog version that identified the component |
| `first_seen`, `last_seen` | Collection time of the first and the latest facts row that showed the component |
| `facts_id`, `facts_collected_at` | The `host_facts` row the detection was derived from |
| `not_seen_since`, `not_seen_reason`, `not_seen_detail` | Set when the component stops appearing |
| `last_run_id` | The discovery run that last wrote the row |

### When a component stops appearing

Rows are never deleted.

| Situation | What is recorded | How the views show it |
|---|---|---|
| The host has newer facts, the newer facts collected the relevant domains, and no signal matches | `not_seen`, reason `signal_gone_in_newer_facts`, `not_seen_since` = collection time of the newer facts | Not in the current list; "not seen since <date>" in the full map |
| The host has no newer facts at all | The row stays `detected` against the old facts row | Still in the current list; freshness "no newer facts since <date>" once the facts are older than `component_stale_after_days` |
| The newer facts row did not collect the relevant domains (a failed or partial collection), or the host has no row in `host_facts_latest` | `not_seen`, reason `no_newer_facts`, with the missing domains in `not_seen_detail` | Still in the current list, status `unverified` |
| Same facts row, but the catalog no longer matches | `not_seen`, reason `catalog_changed` | Not in the current list |

`host_component_history` records each transition: `first_detected`, `not_seen`, `detected_again`, `confidence_changed`, and for overrides `override_recorded` and `override_withdrawn`.

### Other tables

| Table | Content |
|---|---|
| `component_catalog` | Copy of the shipped catalog, refreshed on each run; `in_current_catalog` is false for a key that has left the catalog |
| `host_unrecognised` | Per host, running services and listening ports that no detected component and no `base_os` entry explains; marked `not_seen` when they go, never deleted |
| `component_overrides` | Operator overrides (below) |
| `component_discovery_runs` | One row per run: time, catalog version, stale threshold, hosts evaluated, summary |
| `host_component_history` | Transitions of the component map |

## Operator overrides

Overrides are entered in `ansible/vars/component_overrides.yml` (shipped empty) or passed as `component_override_entries`.

| Field | Required | Meaning |
|---|---|---|
| `host` | Yes | `host_id` or `hostname` as stored in `host_facts` |
| `component` | Yes | Catalog key |
| `action` | Yes | `exclude` (leave the detection out for this host), `confirm` (the component is there, whatever detection found), `reclassify` (report it as another component) |
| `reclassify_to` | With `reclassify` | Catalog key to report instead |
| `who` | Yes | The person who asked for the override |
| `why` | Yes | The reason |
| `expires` | Yes | `YYYY-MM-DD`, no further away than `component_override_max_days` (90 by default) |
| `approver` | For `exclude` or `reclassify` of a privileged component | A second person; see "Overrides on privileged components" |

Two more values are stored with every override and are not taken from the entry:

| Stored column | Source |
|---|---|
| `recorded_by` | The account that launched the job (`awx_user_name` / `tower_user_name`), when the job runs in the automation controller. It is kept apart from `requested_by`, which is only what the entry declares |
| `source` | `file` when the list came from the overrides file, `variable` when it came from `component_override_entries` |

Rules:

- An entry without `who`, `why` or `expires` is refused. The job stops before it writes anything and names the entry.
- An entry whose expiry is further away than `component_override_max_days` is refused.
- An `exclude` or `reclassify` of a component with a capability hint (`act`, `map` or `rank`) needs a second person (next section). Once accepted it stays visible: the summary lists it under overrides in force and under `overrides_on_privileged_components`, and the full map keeps the detection with `basis` `override`.
- An override past its expiry stops applying by itself. The views compare `expires_at` with the current time, so no job has to run for it to lapse. Its record stays in the table.
- Removing an entry from the list withdraws its record at the next run (`withdrawn_at`, `withdrawn_by`, `withdrawn_reason`).
- The override table is append-only. A row is never updated in place. A change to the approver, the reason, the expiry or any other field withdraws the old row and inserts a new one that carries the `recorded_by` and `source` of the run that made the change. Both steps are written to `host_component_history` (`override_withdrawn`, `override_recorded`). A database trigger rejects any other update, and any delete or truncate, of `component_overrides`.
- An entry that is identical to a live row was checked when it was recorded. It keeps that row's `recorded_by`, so a scheduled run does not rewrite or re-attribute it.
- The map shows an override as an override: `basis` is `override`, with the action, who asked, who approved, who recorded it, its source, why and expiry beside it. `detection_status`, `confidence` and `evidence` keep what detection found.

### Overrides on privileged components

Hiding or renaming a privileged component is accepted only when all of these hold. Names are reduced to lower-case letters and digits before every comparison, so `A. Operator`, `a operator` and `A.OPERATOR` are one person.

| Check | Based on |
|---|---|
| The `approver` is on the site's approver list | `component_override_approvers` in `ansible/vars/site_config.yml`, read from the file. The entry's author cannot add a name at launch |
| The account that launched the job is known | `awx_user_name` / `tower_user_name`, set by the automation controller. A run outside the controller, or a scheduled run recording a new entry, has no launching account and the entry is refused |
| The launching account is not the approver | The stored `recorded_by` against `approver` |
| The approver is not the declared requester | `approver` against `who` |

This is a recorded control, not cryptographic proof. It establishes which controller account launched the job that recorded the override and that the named approver is someone the site allows. It does not prove that the approver agreed: a person who can edit the overrides list and launch the job can still name an approver who was never asked. The record makes that visible afterwards. The stronger option is a separate approval job that the approver launches under their own controller account, so that approval is an act by a second account and not a field in the requester's entry. That job is not built.

## Views for an auditor

| View | Question it answers |
|---|---|
| `v_host_components_current` | Which components are on each host now, on what basis (detection or override), with what confidence, and how fresh are the facts |
| `v_components_not_assessed` | Which detected components are not assessed, and why: no collector, no policy bundle, or no stored result for the host under any of the component's loader keys |
| `v_host_unrecognised` | What is running or listening on each host that the catalog does not explain |
| `v_privileged_services` | Where the components with `act`, `map` or `rank` capability hints are |
| `v_host_component_map` | The whole map, including components no longer seen and detections excluded by an override |
| `v_component_overrides` | Every override with its state: `in_force`, `expired` or `withdrawn` |

## What the stored facts can and cannot show

| Limit | Effect |
|---|---|
| `processes.processes_raw` holds the first 100 processes and the command name only | On most hosts the list is kernel threads. In practice the process signal comes from the process named on each listening socket |
| No shipped collector stores running container images | `container_image` signals match only when a collector writes `containers.running[].image`. A component that runs only as a container (AWX, a containerised controller, OPA under Podman) is not detected from today's facts |
| `services.all` lists system units | Rootless containers managed by user units (`systemctl --user`) are not visible |
| A workload inside a cluster or a virtual machine is not part of the host's facts | The host shows the hypervisor or the cluster runtime, not what runs inside it |
| Windows hosts and network devices store facts in a different shape | They are reported as "hosts without usable facts" and are not evaluated |
| The read query returns unit, package and process names for every host in one result | Suitable for estates of hundreds of hosts; batching is needed beyond that |

## Not in this step

- No second-stage collectors are launched for detected components.
- No separate approval job. Approval of an override on a privileged component is a named, listed approver plus the recorded launching account, not an action by the approver's own account.
- `enroll_discovered_frameworks.yml` is unchanged and does not read the component map.
