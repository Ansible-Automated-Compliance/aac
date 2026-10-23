# AAP Execution Nodes and Automation Mesh — and how AAC uses them

**Version:** v2.0  
**Date:** 2026-08-25  
**Audience:** Internal — architecture, delivery, and anyone scoping an AAC deployment into a segmented estate  
**Related:** `AAC_COMPONENTS_AND_TRAFFIC_FLOW.md` (the assessment path), `AAP_OPA_INTEGRATION_ARCHITECTURE.md` (evaluation, including the EDA/local-OPA sidecar pattern)  
**Authors:** Tim Coulter (Red Hat) with Claude (Anthropic)

---

## 1. Why this matters for AAC

AAC's collection problem is rarely "can we read this system". It is **"can we reach it at
all, from where the control plane lives"** — and in the estates that need compliance
evidence most, the answer from the network team is no.

Regulated and operational networks are segmented on purpose. An OT network behind an
electronic security perimeter, a customer site across a VPN, a PCI zone, an isolated
management VLAN, a cloud VPC with no inbound path. In each case the systems that most need
assessing are the ones a central scanner cannot see.

**Automation mesh is the answer, and it is the reason AAC's collection model works where a
scanner's does not.** Rather than reaching in, AAP places an execution node *inside* the
segment. It gathers facts locally and returns results over a connection it initiated
outbound.

---

## 2. The node types

AAP separates the control plane from the execution plane. Four roles:

| Type | Control services | Runs jobs | What it is for |
|---|---|---|---|
| **Control** | ✅ | ❌ | Web, API and task services only — no job execution |
| **Hybrid** | ✅ | ✅ | Both. The default in a single-node install |
| **Execution** | ❌ | ✅ | Pure capacity. Where playbooks actually run |
| **Hop** | ❌ | ❌ | A relay. Bridges segments that cannot reach each other directly, runs no jobs |

An **execution node** is the unit of reach. Placing one inside a network segment is what
makes the systems in that segment assessable.

A **hop node** matters when the topology is not a simple star — segment A cannot see the
control plane but can see segment B, which can. The hop node relays without executing
anything, which also makes it a small, defensible thing to place in a sensitive zone.

Jobs run inside an **execution environment** — a container image — via podman on the
execution node. That containerisation is why the operating-system question in §5 has two
different answers, and why §3.3 exists at all.

---

## 3. How the mesh works

Three separate questions get compressed into "how does it connect", and answering them
together is what causes confusion. They are: which way the *connection* is dialled, which
way *work* flows, and how the *EE image* arrives. The answers are not the same.

### 3.1 Connection direction — outbound only, if you want it

The transport is **receptor**, which distinguishes two roles:

| Directive | Behaviour |
|---|---|
| `tcp-listeners` | Passive. Accepts inbound connections |
| `tcp-peers` | Active. Dials outbound to a listener |

A node configured with **only `tcp-peers`** dials the control plane and holds the
connection open. Receptor supports TCP, UDP and websocket backends and re-dials
automatically when `redial` is enabled, so the mesh recovers from a dropped link without
intervention.

> **A remote execution node can be configured to connect outbound only. No inbound
> firewall rule is required at the remote site.**

```
   Segmented network (OT / customer site / PCI zone)      Control plane
 ┌────────────────────────────────────┐
 │  execution node                    │ ─── dials out ───▶  AAP control plane
 │    gather_facts ──▶ local systems  │   (nothing inbound at the perimeter)
 └────────────────────────────────────┘                          │
                                                                 ▼
                                                          OPA ──▶ PostgreSQL
```

Three things are true at once here, and a network owner usually needs all three before
agreeing:

1. **Nothing crosses the perimeter inbound.**
2. **No new listening service exists inside the segment.**
3. **No agent is installed on the assessed systems** — collection uses `gather_facts` over
   the connection AAP already uses to manage them.

### 3.2 What moves, in which direction, and who starts it

"Push or pull" is too coarse a question, because **three different things move and they do
not all move the same way**:

| # | What moves | Data direction | Who initiates | Path |
|---|---|---|---|---|
| 1 | **Work unit + job payload** — playbook/project content, inventory, variables | control plane → node | **Control plane** | mesh |
| 2 | **Execution environment image** | registry → node | **Node** (`podman pull`) | **not the mesh** |
| 3 | **Results, output, job events** | node → control plane | **Control plane** — streams results back to itself and polls work status | mesh |

**Work is pushed.** `receptorctl work submit` takes a `--node <Node ID>` argument naming
which node executes the work. The control plane decides placement (§4), addresses the work
unit to that node and dispatches it. The execution node is a **passive recipient** — it
does not poll a queue and does not request work. Receptor's documentation notes the target
*"is not aware that [the submitter] is the one that issued the command"*; the unit is
routed to it by node ID across the mesh.

**Connection direction and work direction are independent**, and assuming they are coupled
is the most common error here:

> An execution node that dials outbound is **not** an agent polling for work. Receptor is
> an overlay mesh — once a link exists, dialled by either side, it is bidirectional, and
> work is routed over it by node ID.

Both properties therefore hold at once: **no inbound firewall rule** at the remote site,
and **no polling agent** with its poll interval and dispatch lag. Raise both together in a
security review — the objections usually come from different people. The network team
wants no inbound rules; the security team is wary of anything that phones home for
instructions. This answers both, and neither answer costs the other.

**Results are the counter-intuitive one.** The instinct is that the execution node pushes
its logs back. Receptor says otherwise:

> *"foo will stream work results back to itself and store it on disk. It also periodically
> gets the `work status` of the work running on bar."*

The **submitting node initiates** — it streams result output back to itself and polls the
remote unit's status. Data moves node → control plane; initiation is control-plane-side.
This changes nothing about connectivity, since it all traverses the existing link, but it
matters when reasoning about failure behaviour.

**Results are stored on both nodes.** The executing node keeps `stdin`, `stdout` and
`status` during the run; the submitter keeps duplicates plus metadata identifying the
remote node and unit id. That redundancy is why a job survives a restart on either side
rather than being lost mid-run. Combined with `redial`, a dropped mesh link is a
recoverable condition rather than a failed assessment.

### 3.3 The EE image — the one transfer that does not use the mesh

The execution node pulls its execution environment from a **container registry** using
podman, entirely outside receptor. AAC's own environment profiles show this plainly: EE
images are registry references — `quay.io/…`, an in-cluster registry, or a Private
Automation Hub endpoint with its own container-registry credential.

**Consequence: a mesh connection alone is not sufficient.** An execution node inside an
isolated segment still needs a way to obtain its EE image. Three workable answers, ordered
for a regulated estate:

| Option | How it works | Trade-off |
|---|---|---|
| **Private Automation Hub inside the segment** | The node pulls from a registry on the same side of the perimeter | Cleanest — nothing egresses, and **no internet access is required at all**. This is the pattern AAC already uses |
| **Pre-load the image, pull policy `never`** | The image is placed on the node out of band | No registry dependency whatsoever; image updates become a manual, change-controlled step |
| **Allow egress to a named registry** | The node reaches an external registry directly | Simplest to build, but it is an egress rule through the perimeter — expect scrutiny, and expect refusal in an OT context |

Raise this alongside the mesh design, not after. Discovering it once the firewall request
is approved means going back for a second one, which in a regulated estate costs weeks.

#### How often is the image pulled?

Two things make this a non-issue, and the first is the one people miss.

**The EE is per job, not per host.** A job template run against 500 hosts is **one**
execution environment container on the execution node. Ansible fans out to all 500 from
*inside* that container over SSH, using forks. Host count never multiplies image pulls,
containers or registry traffic — it drives forks, and therefore CPU and memory (§7).

**Then it is cached.** After the first successful pull the image stays in the node's local
podman storage and is reused. Whether the registry is contacted again is governed by the
EE's **pull policy**:

| Policy | Behaviour | Suitable for an isolated node |
|---|---|---|
| `always` | Contacts the registry on **every job run** | ❌ Every job fails when the registry is unreachable — even though the image is already local |
| `missing` | Pulls only when the image is not present locally | ✅ **The right default.** AAC's bootstrap sets `pull: "missing"` |
| `never` | Never pulls; the image must be pre-loaded | ✅ Fully air-gapped |

An execution node with no route to a registry runs fine on `missing` once the image is in
place — and the same node on `always` fails every single job while the image sits locally.
**Check the policy before diagnosing anything else**, because an `always` policy presents
as a networking fault and is not one.

> **The trap: `missing` plus a mutable tag is silent staleness.** With an image tagged
> `:latest`, a node keeps using whatever it first pulled and never notices a new build —
> indefinitely, and without erroring. AAC avoids this only because it uses immutable
> version tags (`v1.3.0`), so a version bump forces the pull. **Keep that convention
> deliberately** — it is what makes `missing` safe, and it breaks the moment someone adds a
> `:latest` EE for convenience.

---

## 4. Controlling where collection runs

Placement is enforced in configuration, not by convention. Job templates are assigned to
**instance groups**, and an instance group maps to specific execution nodes.

That is the mechanism behind a statement like *"OT assessments execute only on the OT
execution node."* It is demonstrable — you can point at the instance-group assignment —
rather than asserted in a runbook nobody re-reads.

For a regulated estate this is worth designing deliberately:

| Instance group | Execution nodes | Runs |
|---|---|---|
| `default` | control-plane-adjacent | corporate IT assessments |
| `ot-segment` | execution node inside the perimeter | OT and BES-adjacent assessments only |
| `customer-<name>` | execution node at the customer site | that customer's estate only |

The separation is also an evidence property: **which execution node produced a result is a
fact about where the measurement was taken.**

---

## 5. Operating system and architecture requirements

Two different questions hide inside *"does it have to be the same OS?"*, and they have
opposite answers. Conflating them is the most common misunderstanding here.

### 5.1 The execution node itself — constrained

It must run a RHEL version supported by the AAP version in use:

| AAP | RPM install | Containerized |
|---|---|---|
| 2.4 | RHEL 8, RHEL 9 | RHEL 9 (tech preview) |
| 2.5 | RHEL 8, RHEL 9 | RHEL 9, RHEL 10 |
| **2.6** | **RHEL 9 only** | RHEL 9, RHEL 10 |

**2.6 dropped RHEL 8 for RPM installs** — worth checking before planning an upgrade that
assumes existing nodes carry over.

Plan on every node in a deployment running the **same major RHEL version**. Mixing majors
across the control and execution plane is not a configuration to rely on.

### 5.2 The managed nodes — unconstrained

**The execution node's OS says nothing about what it can assess.** The execution node runs
RHEL; the systems it assesses do not have to. Because automation runs inside an execution
environment container and connects outward over SSH, WinRM or HTTPS, targets can be:

- Windows servers and workstations
- Other Linux distributions
- Network devices, firewalls, hypervisors
- Cloud, SaaS and platform APIs

This matters disproportionately in OT and in any real enterprise estate, where
heterogeneity is the normal condition rather than an exception.

### 5.3 Architecture must match

**The execution environment image architecture must match the execution node's
architecture.** An `x86_64` EE image will not run on an `aarch64` node.

Not theoretical — it is why AAC's EE builds must run on an `x86_64` build host rather than
on Apple silicon. An execution node on a different architecture from the rest of the fleet
needs EE images built for it.

---

## 6. How AAC uses this

The collection path is unchanged by distribution — only *where* the collection step happens
moves:

```
execution node (inside the segment)
   gather_facts / API queries against local systems
        │  results returned over the mesh
        ▼
control plane
        │
        ▼
   OPA  ── evaluate state against versioned policy
        │
        ▼
   PostgreSQL  ── the evidence series
```

### Two placement options for evaluation

There is a design choice about *where policy is evaluated*, and both patterns exist:

| Pattern | Where OPA runs | When to use it |
|---|---|---|
| **Central evaluation** (default) | OPA alongside the control plane | The normal case. One policy version governs every segment and the evidence series is unified |
| **Local sidecar** | OPA on the execution node | Latency-sensitive or event-driven paths — see the EDA drift pattern in `AAP_OPA_INTEGRATION_ARCHITECTURE.md`. Costs you a policy-version-per-location problem to manage |

Default to central evaluation. A single policy version producing every verdict is a
material evidence-quality property — it is what makes "which rule decided this" answerable
across the whole estate.

### What this unlocks

| Situation | Without mesh | With an execution node |
|---|---|---|
| OT network behind an ESP | Not assessable without an inbound path nobody will grant | Assessed from inside; nothing inbound |
| Customer site across a VPN | Requires a route to every managed host | One outbound connection from the site |
| Cloud VPC with no ingress | Not reachable | Execution node in the VPC |
| Segments that cannot see the control plane | Not reachable | Hop node relays |

---

## 7. Sizing

**Fact gathering is where the load lands.** Execution nodes carry the fork, CPU and memory
pressure during collection; the control plane is comparatively idle while an assessment
runs.

Size execution nodes against **how many systems are swept concurrently**, not against the
size of the control plane. If a segment holds 400 hosts and the assessment window is short,
that is an execution-node capacity question — adding control-plane resources will not help.

---

## 8. Verification status

| Claim | Basis |
|---|---|
| RHEL support by AAP version and deployment type | Red Hat's AAP lifecycle and update policy page |
| Receptor `tcp-peers` / `tcp-listeners` semantics; outbound-only supported; TCP/UDP/websocket backends; `redial` | Receptor project documentation |
| Work is pushed — `work submit --node <ID>`, remote node is a passive recipient, not polling | Receptor `work submit` and remote-work documentation |
| Results are streamed by the *submitting* node, which also polls work status; results stored on both nodes | Receptor remote-work documentation, quoted directly |
| The EE image is pulled by the node from a container registry, outside the mesh | AAC's own environment profiles reference EE images as registry endpoints (quay.io, in-cluster registry, PAH), and a container-registry credential exists for the PAH path |
| The EE is instantiated per job, not per host — one container serves all hosts in a run | Ansible's execution model; forks fan out from inside the EE |
| `pull: "missing"` is AAC's configured policy | `ansible/playbooks/bootstrap_rhpds_environment.yml:221` |
| EE image architecture must match node architecture | Observed directly — AAC EE builds fail on `aarch64` for `x86_64` targets |
| Node type taxonomy (control / hybrid / execution / hop) | General AAP knowledge — **not** re-verified against 2.6/2.7 documentation |
| **Default mesh port 27199** | General AAP knowledge — **not verified. Confirm before writing a firewall request** |
| Same-major-RHEL-version guidance | General AAP knowledge and prudence — an explicit supported/unsupported statement was **not** located |
| The job payload travels with the pushed work unit | **Reasonably confident, not verified from source.** If a design depends on exactly what crosses the mesh versus what the node fetches, confirm against the install guide |

`docs.redhat.com` returns HTTP 403 to automated retrieval, so the AAP 2.6/2.7 installation
and planning guides could not be read directly. **Confirm the unverified rows against the
install guide for the deployed version before a design or a firewall request depends on
them.**

---

## Revision history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-08-25 | Initial version — node types, mesh connection, OS requirements, sizing |
| v1.1–v1.4 | 2026-08-25 | Successive corrections: push versus pull; the EE image is a pull outside the mesh; results are streamed by the submitter rather than pushed by the node; the EE is per job not per host, and pull policy decides whether an isolated node works |
| **v2.0** | 2026-08-25 | **Consolidation.** The v1.x corrections had accumulated as layered patches, leaving §3.1 and §3.2 covering overlapping ground and a stray unnumbered subsection. §3 is rewritten as one coherent treatment of the three questions that genuinely differ — connection direction (§3.1), what moves and who initiates it (§3.2), and the EE image and registry access (§3.3). No claim changed and nothing was dropped; the verification table is consolidated in place. |
