# Layered fact gathering

**Version:** v1.0
**Authors:** Tim Coulter, Claude (Anthropic)

Base host facts say what a host is. They do not say how the database server, the cluster or the web server on that host is configured. Layered fact gathering collects those facts, driven by what component discovery found: a collector runs only where its component was detected, and every detected component ends with a recorded outcome.

The model is generic. The dispatcher, the shared task files, the script and the schema hold no component names. A component is described by its catalog entry and collected by its collector file.

## The layers

| Layer | What | Collected by | Stored in |
|---|---|---|---|
| 0 | Base host facts | `AAC - Gather Facts` (`aac_facts_collector`) | `host_facts` |
| 1 | Detection: which component runs on which host | `AAC - Discover Host Components` | `host_components` |
| 2 | Component facts, host side: configuration files, process flags, file modes and owners | A host-side collector, over the connection already in use, only on hosts where the component was detected | `component_facts`, layer 2 |
| 3 | Component facts, service side: what only the service's own API can say | A service-side collector, once per service instance, with a credential of the type the catalog names | `component_facts`, layer 3 |
| 4 | What is inside a component | Reported by the layer 2 and 3 collectors, matched against the catalog, and collected in the next pass | `component_children`, then `component_facts` with depth 2 or more |

## How to add a component

1. Add one entry to `ansible/vars/component_catalog.yml` (signals, `collectors`, and `contains` and `assess` where they apply) and bump `catalog_version`.
2. Add one collector file, `ansible/tasks/component_collectors/<key>_<layer>.yml`, that reads `lc_target` and sets `lc_result` as the contract says.

Nothing else changes: no schema, no playbook, no script, no job template. `python3 scripts/layered_collection.py check-catalog` and `python3 -m pytest -q tests/test_layered_collection.py` confirm the entry and the file agree. The contract is `docs/reference/COMPONENT_COLLECTOR_CONTRACT.md`.

## Catalog fields

These are optional additions to a detection catalog entry. An entry without them is detected as before and reported as "detected, not assessed: no collector".

| Field | Meaning |
|---|---|
| `collectors` | At most one per layer. Each has the fields below |
| `collectors[].layer` | `host` (layer 2) or `service` (layer 3) |
| `collectors[].file` | `<key>_<layer>.yml`, or `none yet` when the collector is planned and not built. `none yet` is reported as not assessed for that layer |
| `collectors[].version` | Stored with every fact row the collector produces |
| `collectors[].cost` | `cheap` or `heavy` |
| `collectors[].access` | The least-privilege, read-only access the collector needs |
| `collectors[].credential` | Service side only: `{type, env}`. `type` is the credential type attached to the job template. `env` lists the environment variables that type injects |
| `contains` | Catalog keys that can be found inside the component (`"*"` for any). What a collector reports is matched against the signals of these entries only |
| `assess` | `true` (default) or `false`. With `false` the component is inventoried where it is found and no collector runs for it |

## Running it

| Item | Value |
|---|---|
| Playbook | `ansible/playbooks/collect_component_facts.yml` (imports `layered_collection_pass.yml` once per pass) |
| Job template | `AAC - Collect Component Facts` (`AAC_Collect_Component_Facts` in the extended install seeder) |
| Run after | `AAC - Discover Host Components` |
| Inventory | The compliance inventory, with no limit. The playbook targets only hosts where a selected component was detected, and only hosts that are in the inventory |
| Logic | `scripts/layered_collection.py` (tested by `tests/test_layered_collection.py`) |
| Shared tasks | `ansible/tasks/layered_run_collector.yml` runs one collector under the contract. `ansible/tasks/layered_store_results.yml` takes the results in |
| Schema | `ansible/files/layered_collection_schema.sql`, applied on every run: `CREATE ... IF NOT EXISTS` and `CREATE OR REPLACE VIEW` on its own objects only |

| Variable | Set where | Default | Meaning |
|---|---|---|---|
| `layered_cost` | Survey, a closed choice | `all` | `cheap` runs cheap collectors only. `all` runs heavy ones too |
| `layered_layers` | Survey, a closed choice | `all` | `host`, `service` or `all` |
| `layered_max_depth` | `site_config.yml` | `3` | Number of passes, 1 to 5 |
| `layered_max_facts_kb` | `site_config.yml` | `512` | Size cap for one collector result, 16 to 4096 |
| `layered_become` | `site_config.yml` | `true` | Privilege escalation on managed hosts |
| `component_catalog_file`, `layered_collectors_dir` | `site_config.yml` | the shipped paths | Must stay inside the project checkout |

A schedule that runs `layered_cost: cheap` nightly and `all` weekly keeps heavy collectors off the nightly window. A collector left out by a filter is listed in the run summary under `not_in_this_run`. No row is written for it, so facts collected earlier stay the latest.

### Passes

An AAP workflow has no loop, so the passes are written out in the playbook: five imports of the same pass, of which `layered_max_depth` do work.

| Step in a pass | Where | What |
|---|---|---|
| Select host side | Controller | The collectors for what is at this depth, grouped by host |
| Run host side | Only the selected hosts | Each collector through `layered_run_collector.yml` |
| Store host side | Controller | Results checked against the contract; children matched against the catalog; next pass queued |
| Select service side | Controller | One item per service instance; an instance whose credential is not attached is recorded as not assessed |
| Run and store service side | Controller | As above |

Pass 1 handles components detected on hosts. Pass 2 handles what was found inside them, and so on. Something found beyond the depth limit is inventoried and recorded as not assessed with the reason "depth limit reached".

### Launch rules

The job holds the database credential and connects to managed hosts, so what a launcher can change is limited.

| Rule | Effect |
|---|---|
| The seeded job template has `ask_variables_on_launch: false` and no limit prompt | A launcher can set two closed choices and nothing else |
| The database host must be the `pg_host` that `ansible/vars/site_config.yml` names | Checked from the file before any connection, as in component discovery |
| The catalog and the collectors directory must be inside the project checkout | A path outside it is refused before it is read |
| Only inventory hosts are targeted | A host name stored in the database that is not in the job's inventory is recorded as not assessed. It never becomes a connection target |
| Collector file names come from the validated catalog | The name must be `<key>_<layer>.yml` and the file must exist in the collectors directory |

## Outcomes

Every detected component ends a run with one outcome per layer. The job stops without writing when a detected component has none.

| Outcome | When |
|---|---|
| `facts collected` | The collector ran and its result satisfied the contract |
| `detected, not assessed: no collector` | The catalog entry has no collector |
| `detected, not assessed: no collector for the host side yet` or `... service side yet` | The catalog names the layer with `none yet` |
| `detected, not assessed: service side not assessed: no credential of type '<type>' is attached to this job` | An environment variable of the credential type is empty |
| `detected, not assessed: collector failed: task "<name>" failed` | A task of the collector failed. Only the task name is kept |
| `detected, not assessed: no result returned` | The host was not reachable, or the collector did not finish |
| `detected, not assessed: collector result does not satisfy the contract` | With the first faults |
| `detected, not assessed: facts are N bytes, over the size cap` | Nothing is stored |
| `detected, not assessed: collector returned private key material` | Nothing is stored |
| `detected, not assessed: host is not in the inventory of this job` | |
| `detected, not assessed: assessment is switched off` | `assess: false` |
| `detected, not assessed: depth limit (N) reached` | Found inside a component beyond the limit |

A reason the collector gives itself (`status: not_collected`) is stored as written, for example "no running postmaster with a readable data directory found on this host".

## Tables

### `component_facts`

Keyed by service instance. An instance, such as a cluster or a database server, is not a host: it can be reached through several hosts, and a host can carry several instances.

| Column | Meaning |
|---|---|
| `instance_id` | `<component key>:<identity>`. The identity comes from the collector when it returns one, otherwise `host/<inventory name>` |
| `target_id` | What the collector was pointed at: the identity the framework gives the target before the collector runs. It stays the same when a collector later returns a better instance identity, so the outcomes of one target line up from run to run |
| `component_key` | Catalog key |
| `layer` | 2 (host side) or 3 (service side) |
| `parent_kind`, `parent_id` | The host or the instance the component was found through. For the service side of a component detected on hosts, the parent is the instance itself and the hosts are in `reached_through` |
| `reached_through` | Inventory hosts that lead to the instance |
| `depth` | 1 for a component detected on a host; 2 or more for something found inside another component |
| `status`, `reason` | `collected`, or `not_collected` with the reason |
| `collector`, `collector_version`, `cost`, `credential_type` | From the catalog entry that was used |
| `catalog_version` | The catalog version of the run |
| `collected_at`, `last_confirmed_at` | When this outcome was first recorded, and the latest run that found the same outcome |
| `facts`, `facts_bytes`, `facts_sha256` | The facts, their size and their digest |
| `notes` | Statements from the collector and the framework, for example a redaction or a capped list |
| `first_run_id`, `last_run_id` | Rows of `component_collection_runs` |

A row is added when the outcome for its key (target, component, layer, parent) changes. A run that finds the same status, reason, facts and collector version only moves `last_confirmed_at`. Rows are never deleted or rewritten, so earlier facts stay readable.

### `component_children`

| Column | Meaning |
|---|---|
| `parent_instance_id`, `parent_component_key`, `parent_layer` | What it was found inside, and by which layer's collector |
| `via_host` | The host whose collector reported it; empty for the service side |
| `child_kind`, `child_value`, `child_name`, `detail` | As the collector reported it |
| `recognised_as` | The catalog key it matched, or empty |
| `disposition` | `assess` (its collectors are queued), `inventory_only` (`assess: false`), `no_collector`, `depth_limit` or `not_recognised` |
| `child_instance_id` | Identity used for its own rows in `component_facts` |
| `depth` | 2 or more |
| `status`, `first_seen`, `last_seen`, `not_seen_since` | A child that a collected parent no longer reports is marked `not_seen`. Rows are never deleted |

### Other tables

| Table | Content |
|---|---|
| `component_collection_runs` | One row per run: time, catalog and contract version, depth, passes run, filters, job id, summary |
| `component_collectors` | Copy of the collectors the catalog declares: file, version, cost, credential type, access needed, `assess`, `contains` |

## Views for coverage

| View | Question it answers |
|---|---|
| `v_component_coverage` | For every detected component and layer: `facts collected`, or `detected, not assessed` with the reason. A component no collection run has looked at yet is listed as not assessed. Things found inside components are listed with their parent |
| `v_component_coverage_collected` | The first group only |
| `v_component_coverage_not_assessed` | The second group only |
| `v_host_unrecognised` (step 1) | What is running or listening that the catalog does not explain |
| `v_component_children` | What is inside each component now, with its parent and disposition |
| `v_component_instances` | Service instances and the hosts each is reached through |
| `v_component_facts_latest` | The latest outcome per target, component, layer and parent |

"Facts collected" means the facts are stored. The compliance decision is still OPA's, in a separate step that reads these facts.

## Collectors shipped

| Component | Layer | File | Cost | Collects |
|---|---|---|---|---|
| `kubernetes_control_plane` | 2 | `kubernetes_control_plane_host.yml` | cheap | Flags of the API server, controller manager, scheduler and etcd as started; mode and owner of the static pod manifests, the etcd data directory, the control plane kubeconfig files, the PKI tree and the CNI files; the audit policy; resource and provider names of the encryption configuration; the anonymous section of the authentication configuration; the image of each static pod, reported as found inside |
| `kubelet` | 2 | `kubelet_host.yml` | cheap | Kubelet flags and configuration file; mode and owner of the kubelet unit file, kubeconfig, client CA file, configuration file and configuration directory; whether kube-proxy runs, its flags, its metrics bind address and the mode and owner of its kubeconfig |
| `postgresql` | 2 | `postgresql_host.yml` | cheap | Settings in `postgresql.conf` and `postgresql.auto.conf`; rules in `pg_hba.conf`; mode and owner of the data directory and those files; server version; the account the postmaster runs as |

None of them calls a service API. None reads a key file, the content of a kubeconfig, an encryption key or a password. Flag values and settings whose name marks a secret are replaced on the way out.

### Kubernetes facts and the CIS Kubernetes policy

The two Kubernetes collectors use the field names of the input contract of the CIS Kubernetes policy in the policy library (`benchmarks/cis/kubernetes`). A control plane node carries both components, so an assessment merges the facts of the two rows for the host.

| Policy input | Fed by |
|---|---|
| `api_server.flags`, `controller_manager.flags`, `scheduler.flags`, `etcd.flags` | `kubernetes_control_plane_host.yml` |
| `api_server.audit_policy`, `api_server.encryption_config`, `api_server.authentication_config` | `kubernetes_control_plane_host.yml`, when the API server names the file and it is under `/etc/kubernetes` |
| `files.manifests`, `files.etcd_data`, `files.control_plane_confs`, `files.pki`, `files.cni` | `kubernetes_control_plane_host.yml` |
| `kubelet.flags`, `kubelet.config` | `kubelet_host.yml` |
| `kube_proxy.running`, `kube_proxy.flags`, `kube_proxy.config` | `kubelet_host.yml` |
| `files.kubelet_service`, `files.kubelet_kubeconfig`, `files.kubelet_client_ca`, `files.kubelet_config_yaml`, `files.kubelet_config_dir`, `files.kube_proxy_kubeconfig` | `kubelet_host.yml` |
| `etcd.member_count` | Not fed (optional in the policy) |
| `service_accounts.default`, `network_policies.namespaces_without_policy`, `secrets.env_var_usage_count`, `cluster.namespace_resources`, `collection_status.*` | Not fed: these need the cluster API (service side, not built) |
| `attest.*` | Not fed: attestations by a person |
| `cis_profile` | Set by the assessment, not collected |

## Base facts that detection needs

`aac_facts_collector` gained three things. Existing keys keep their meaning.

| New key | Content | Cap |
|---|---|---|
| `containers.running[]` | `{image, name, runtime, user}` for running containers: Podman for the collecting account and, as root, for every user that already has Podman state under its runtime directory; CRI through `crictl`; Docker | 500, `containers.capped` |
| `containers.runtimes[]` | `{runtime, user, result}`: which runtimes were read and whether the read worked. A runtime that is not installed is absent | |
| `processes.command_names` | The distinct command names of every process. `processes_raw` still holds the first 100 lines | 2000, `processes.command_names_capped` |
| `processes.process_total`, `processes.command_names_total` | Counts before the cap | |
| `services.user_units[]` | `{user, unit, state}` for running user-level systemd units | 500, `services.user_units_capped` |
| `services.user_units_read[]` | `{user, result}`: which users were read | |

Only image names and container names are stored. Container command lines, environment, labels and mounts are not read.

## Limits

| Limit | Effect |
|---|---|
| No service-side collector ships yet | Layer 3 is exercised by tests and by a stub. Components whose catalog entry names a service side with `none yet` are reported as not assessed for that layer |
| The Kubernetes collectors do not return a cluster identity | Each control plane node is its own instance until the service-side collector supplies the cluster identifier |
| Flags written as `--name value` (two arguments) are read as a flag set to `true` | Kubernetes components are started with `--name=value` by kubeadm and by the distributions checked. A component started the other way would be misread |
| The static pod manifest directory is taken as `/etc/kubernetes/manifests` | A kubelet with another `staticPodPath` has no manifest file facts |
| Files named by API server flags are read only under `/etc/kubernetes` | A file elsewhere is listed in `collection.files_not_read` |
| `postgresql_host.yml` reads the first postmaster it finds | Others are counted in `notes`. Files named by `include` directives are not read, and the result says so |
| The component map is read in one query and results pass through the controller's memory | Suitable for estates of hundreds of hosts |
| Results are stored once, at the end of the run | A job that is cancelled stores nothing from that run |
| Rootless containers are read only for users with a runtime directory | See `docs/reference/COMPONENT_DISCOVERY.md` |

## Next

- Service-side collector for the Kubernetes control plane (cluster API, read-only service account).
- Service-side collector for the automation controller (its API, read-only token).
- OpenShift collectors, host side and service side.
- Collectors for backup servers and agents.
- PostgreSQL service side (effective settings and role attributes through a read-only role).
- An assessment job that hands `component_facts` to OPA under each component's loader keys and stores the results.
