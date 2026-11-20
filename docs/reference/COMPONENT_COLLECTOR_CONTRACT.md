# Component collector contract

**Version:** v1.0
**Authors:** Tim Coulter, Claude (Anthropic)

A collector gathers the facts of one technology component on one layer. This page is the contract between a collector and the framework that runs it. The machine-checked form is `ansible/files/component_collector_contract.schema.json` (contract version `1`). `scripts/layered_collection.py` checks every catalog entry, every collector input and every collector result against it, in the tests and on every run.

The framework holds no component logic. If a collector needs a special case in the dispatcher, the shared task files, the script or the schema, the contract is wrong and the contract is what changes.

## Where a collector lives

| Item | Rule |
|---|---|
| Directory | `ansible/tasks/component_collectors/`, the only one |
| File | One Ansible tasks file per component and layer |
| Name | `<component key>_<layer>.yml`, where layer is `host` or `service`, for example `postgresql_host.yml` |
| Declared in | The component's entry in `ansible/vars/component_catalog.yml`, under `collectors` |
| Variables it creates | Prefixed with a short name of its own, so two collectors on one host do not collide |

## What a collector receives

One variable, `lc_target` (schema definition `target`).

| Field | Meaning |
|---|---|
| `component_key` | Catalog key of the component |
| `layer`, `layer_number` | `host` (2) or `service` (3) |
| `host` | Inventory name of the host it runs on. Empty for the service side, which runs on the controller |
| `instance_id` | Provisional identity of the service instance. The collector can replace it (see `instance` below) |
| `parent` | `{kind, id}`: the host or the instance this component was found through |
| `reached_through` | Inventory hosts that lead to the instance. One for the host side; all of them for the service side |
| `depth`, `max_depth` | 1 for a component detected on a host, 2 for something found inside it, and so on; and the site's limit |
| `credential_type`, `credential_env` | Service side only: the credential type the catalog names and the environment variables it injects. The collector reads the values from the environment. They are never passed as variables |
| `locator` | How the component was found: the matched signals for a detection, or the entry the parent reported for something found inside a component |
| `max_facts_bytes` | Size cap for the facts it returns |
| `collector` | `{file, version, cost}` from the catalog |

A host-side collector runs over the connection the job already uses, with privilege escalation when the site allows it, only on hosts where its component was detected. A service-side collector runs once per service instance, on the controller.

## What a collector must return

One fact, `lc_result` (schema definition `result`).

| Field | Required | Meaning |
|---|---|---|
| `status` | Yes | `collected` or `not_collected` |
| `reason` | With `not_collected` | Why, in one plain sentence of at most 300 characters |
| `facts` | With `collected` | An object. Empty facts are recorded as not collected |
| `instance` | No | `{identity, name}`. A stable identity of the service instance, for example a cluster identifier. Two hosts that return the same identity are one instance, and its service side is collected once |
| `children` | No | What was found inside the component: `{kind, value, name, detail}`, where `kind` is a signal kind of the detection catalog (`package`, `service`, `process`, `container_image`). At most 2000 |
| `notes` | No | Short statements a reader needs, for example that a list was capped |

## Rules

| Rule | How it is enforced |
|---|---|
| Read-only | By review, and by the access statement each catalog entry carries. A collector changes nothing on the host or in the service |
| Least privilege | The catalog entry states the access the collector needs (`access`). The service side names a credential type whose access is read-only |
| No secrets | Collect settings, modes and owners. Never key material, tokens or passwords. Replace a secret value on the host where that is possible. The framework also replaces the value of any field named like a secret (`password`, `token`, `secret`, `private_key` and similar) and refuses a whole result that contains a private key |
| Collected text is data | Never put a string read from a host into the text of a script or a template. Pass it through the task's `environment`. Parse it with filters |
| Size cap | A result whose facts exceed `max_facts_bytes` is recorded as not collected, with the sizes. Cap lists in the collector and say so in `notes` |
| Cost hint | `cheap` or `heavy` in the catalog. A cheap run leaves heavy collectors out |
| Fail closed | A collector that fails, sets no `lc_result`, or returns a result that does not satisfy the schema is recorded as "detected, not assessed" with the reason. It never fails the job and never leaves a result that looks complete |
| Changed state | Every `command` or `shell` task sets `changed_when: false` |

## How results are stored

Every outcome becomes one row of `component_facts`: the instance, the component, the layer, the parent, the hosts it was reached through, the depth, the collector and its version, the catalog version, the status and reason, the facts and their size. See `docs/reference/LAYERED_FACT_GATHERING.md`.
