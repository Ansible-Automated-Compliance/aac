# Component collector contract

**Version:** v1.2
**Authors:** Tim Coulter, Claude (Anthropic)

A collector gathers the facts of one technology component on one layer. This page is the contract between a collector and the framework that runs it. The machine-checked parts are `ansible/files/component_collector_contract.schema.json` (contract version `1`: catalog entries, collector input, collector result) and the code rules in `ansible/files/component_collector_guard.py` (`check_code`). `scripts/layered_collection.py` applies both in the tests, in `check-catalog` and on every run; the guard applies the code rules again on the host before a collector starts.

The framework holds no component logic. If a collector needs a special case in the dispatcher, the shared task files, the script, the guard or the schema, the contract is wrong and the contract is what changes.

## Where a collector lives

| Item | Rule |
|---|---|
| Directory | `ansible/tasks/component_collectors/`, the only one |
| File | One file per component and layer: a Python body that the guard runs |
| Name | `<component key>_<layer>.py`, where layer is `host` or `service`, for example `postgresql_host.py` |
| Declared in | The component's entry in `ansible/vars/component_catalog.yml`, under `collectors` |
| Runs on | The managed host for the host side (Python 3.6 or later, standard library only); the controller for the service side |

## The guard

A collector does not touch a host by itself. It is run by `ansible/files/component_collector_guard.py`, which gives it two names: `target` (its input) and `g` (the guard). Everything it reads, it reads through `g`.

| Call | What it does |
|---|---|
| `g.processes(*names, exe_names=None, accounts="root")` | Every verified main process with one of these command names, in pid order. Each process that carries a name is recorded in `g.candidates` with the decision and the reason; one that fails a check is never returned |
| `g.seen(name)` | Whether any process carries the name, verified or not |
| `proc.flags()`, `proc.args`, `proc.cwd`, `proc.user` | What a verified process was started with. A flag whose name marks a secret has its value replaced |
| `g.flags_of(words)` | The same flag reading for a list of words from a trusted file |
| `g.stat(paths, under, tree=False)` | Mode, owner and group of each path that resolves under one of the `under` directories |
| `g.read(path, under, proc=None)` | The text of one regular file, with secret-shaped values already replaced. With a verified process it is read as that process's own account. Without one, only a root-owned system file is read. `None`, with a note, when a rule below is not met |
| `g.parse_yaml(text)` | Parsed YAML: PyYAML when the host has it, otherwise a small reader for block mappings, lists and plain scalars. `None` when the text is outside that subset |
| `g.env(name)` | Service side: the value of an environment variable, only for the names the catalog lists under `credential.env` |
| `g.collected(facts, instance=None, children=None)` | The result when facts were gathered |
| `g.not_collected(reason)`, `g.unverified(what)` | The result when they were not. `unverified` gives the standard reason for a missing or unverified process |
| `g.notes` | Short statements a reader needs, for example that a list was capped. The guard adds one line per process that carried an expected name: accepted or refused, and why |

### Code rules (checked by `check_code`)

| Rule | Why |
|---|---|
| No `import` | A collector uses `g`, `target`, `re` and plain Python |
| No `open`, `exec`, `eval`, `getattr`, `os`, `sys`, `subprocess` and similar names | Files and processes are reached only through the guard |
| No attribute that starts with an underscore | The guard's internals stay out of reach |
| No string that contains `/proc` | Processes come from `g.processes()`, which verifies them |
| No `{{`, `{%` or `{#` anywhere in the file | A collector file is never a template |

A file that breaks a rule fails the tests and `check-catalog`, and is refused on the host.

### Process verification

A process name proves nothing: any local user can choose one. Three rules come first.

1. **Identity never comes from the inspected process or from its container.** The expected accounts are named by the collector and resolved on the host. Nothing is read from a container's own files to decide who a process is.
2. **Collection inside a container is opt-in per catalog entry** (`in_container` on the collector entry), and no entry can switch it on in this version: there is no sound way here yet to tie a container to an expected image or manifest, so a process in another mount namespace is refused.
3. **Every candidate is recorded.** The guard returns every verified process, never only the first, and reports each process that carried the name with the decision and the reason. The collector states what several verified processes mean; it does not pick one silently.

`g.processes()` returns a process only when all of these hold.

| Check | Rule |
|---|---|
| Namespace | The process is in the host's mount namespace. A process in a container is refused |
| Executable | `/proc/<pid>/exe` resolves to a file with one of the expected names, in a system path (`/usr/bin`, `/usr/sbin`, `/usr/libexec`, `/usr/lib`, `/usr/lib64`, `/usr/local/bin`, `/usr/local/sbin`, `/bin`, `/sbin`, `/opt`, plus `collector_guard.binary_dirs` in the catalog). The file and every directory above it are owned by root and not writable by group or others. A deleted or replaced executable is refused |
| Account | The process runs under one user id. With `accounts="root"` it is 0. With a list of account names it is the host uid of one of those accounts, and never 0 |
| Parent | The parent is init (pid 1). A process whose parent is a process of the same service is a worker and is left out |

When no process passes, the outcome is `not collected: process could not be verified: ...` with the first reason.

### File access

All file access is descriptor-based and confined.

| Rule | Detail |
|---|---|
| Resolve, then compare | Every path is resolved (`realpath`) and must sit under a directory the collector names in `under`: a literal directory, or the working directory of a verified process. `/` is never accepted. `..` and symbolic links cannot leave an allowed directory |
| Open by descriptor | The resolved path is then opened one component at a time, each relative to the descriptor of the one before, with no symbolic link followed at any step. A component that is swapped for a link between the comparison and the open makes the open fail, and the file is not read |
| Judge the opened file | Type, owner and mode are read from the opened descriptor, and the data is read from that same descriptor. Regular files only, up to a size cap |
| Paths from a command line | A path taken from a flag or a setting is used only through `g.stat()` or `g.read()` with `under` |
| A service's file | `g.read(path, under, proc)` opens and reads in a child process that has dropped to the verified process's user and group, and returns the file only when it is owned by that account or by root |
| A system file | `g.read(path, under)` with no process returns only a root-owned file that group and others cannot write, reached through directories with the same property |
| Never as root for someone else | Root reads only root-owned system files and the files of a verified root process. Nothing is read as root on behalf of another account or of a container |

## What a collector receives

`target` (schema definition `target`).

| Field | Meaning |
|---|---|
| `component_key` | Catalog key of the component |
| `layer`, `layer_number` | `host` (2) or `service` (3) |
| `host` | Inventory name of the host it runs on. Empty for the service side |
| `instance_id` | Provisional identity of the service instance. The collector can return a better one |
| `parent` | `{kind, id}`: the host or the instance this component was found through |
| `reached_through` | Inventory hosts that lead to the instance |
| `depth`, `max_depth` | 1 for a component detected on a host, 2 for something found inside it, and so on |
| `credential_type`, `credential_env` | Service side: the credential type the catalog names and the environment variables it injects. Values are read with `g.env()` |
| `locator` | How the component was found: the matched signals for a detection, or the entry the parent reported. These are strings a host supplied: data, never code |
| `max_facts_bytes` | Size cap for the facts |
| `collector` | `{file, version, cost}` from the catalog |
| `guard` | `collector_guard.binary_dirs` from the catalog |

## What a collector returns

Through `g.collected()` or `g.not_collected()` (schema definition `result`).

| Field | Required | Meaning |
|---|---|---|
| `status` | Yes | `collected` or `not_collected` |
| `reason` | With `not_collected` | Why, in one plain sentence of at most 300 characters |
| `facts` | With `collected` | An object. Empty facts are recorded as not collected |
| `instance` | No | `{identity, name}`. A stable identity of the service instance. Two hosts that return the same identity are one instance, and its service side is collected once |
| `children` | No | What was found inside the component: `{kind, value, name, detail}`, with `kind` a signal kind of the detection catalog. At most 2000 |
| `notes` | No | Added by the guard from `g.notes` |

## Rules

| Rule | How it is enforced |
|---|---|
| Read-only | The guard opens nothing for writing and runs no command. The catalog entry states the access the collector needs |
| Nothing a host returned is templated | The guard, the collector and its input reach the target base64-encoded, and the result comes back as one base64 line that only `scripts/layered_collection.py` decodes. No such string is ever an Ansible variable as text. The few names that are (inventory host, collector file, item id) are refused when they carry a template delimiter, with the outcome `not collected: unsafe value`. The component map is read from the database as one base64 value, and the summary a job prints has template delimiters broken apart |
| No secrets | Store an allowlist of the settings the policies need, not whole files. Never key material, tokens or passwords. The guard replaces secret-shaped values in everything a collector reads and returns: `password=` and similar names with a value, `user:password@` in a URL, bearer and JWT-like tokens, cloud access keys, private key blocks. The shared store path applies the same patterns again to every collector's result, replaces the value of any field named like a secret, and refuses a whole result that contains a private key |
| Size cap | A result whose facts exceed `max_facts_bytes` is recorded as not collected, with the sizes |
| Cost hint | `cheap` or `heavy` in the catalog. A cheap run leaves heavy collectors out |
| Fail closed | A collector that fails, returns nothing, or returns a result that does not satisfy the schema is recorded as "detected, not assessed" with the reason. It never fails the job and never leaves a result that looks complete |

## How results are stored

Every outcome becomes one row of `component_facts`: the instance, the component, the layer, the parent, the hosts it was reached through, the depth, the collector and its version, the catalog version, the status and reason, the facts and their size. See `docs/reference/LAYERED_FACT_GATHERING.md`.
