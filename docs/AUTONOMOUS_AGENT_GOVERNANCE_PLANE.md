# The Autonomous-Agent Governance Plane

**Version:** v1.1
**Date:** 2026-09-21
**Audience:** enterprises operating autonomous AI agents against production infrastructure — architecture and security leadership. Customer-adaptable.
**Authors:** Tim Coulter · Claude (Anthropic) — co-authored
**Status of claims:** every capability in this document is labeled **BUILT** (running today in the AAC reference implementation), **POLICY-BUILT** (policy code exists and is tested; enforcement wiring is engagement work), or **DESIGNED** (architecture defined, not yet implemented). Nothing is presented as more than it is.

---

## 1. The problem, stated the way it actually arrives

AI agents are now operating inside enterprise environments — optimizing configurations, updating
software, changing systems — at machine speed and increasing autonomy. Three questions follow
immediately, and they are the right ones:

1. **Control:** can we force every agent action through a policy decision — not ask agents to
   behave, but make misbehavior structurally impossible on the governed paths?
2. **Evidence:** can we know, afterward and provably, what every agent actually did — and what it
   *tried* to do and was refused?
3. **Detection:** can the record of agent activity tell us when an actor — a human, an agent, or a
   compromised credential driving an agent — is doing bad things?

Behind all three sits the real stake. The most valuable artifacts in the environment are the
**business rules** — the logic that runs the business, including the policies that govern the agents
themselves — and the **data**. Those are the jewels. Agent governance exists to protect them, not to
slow agents down.

## 2. The architecture: one plane, two halves

```
  agents ──► interposition ──► policy decision ──► allow / hold / deny
                (forced)        (per action)            │
                                                        ▼
                              evidence stream ◄── every verdict persisted
                                    │
                                    ▼
                        activity evaluation (bad-actor detection)
```

**Inline control half** — agents reach infrastructure only through governed channels; every action
receives a policy verdict before it executes.
**Activity/evidence half** — every verdict (allows *and* denies) persists as signed, append-only
evidence; the accumulated stream is the substrate for detecting the bad actor.

The two halves are one system: the gateway is what makes the activity record trustworthy, and the
activity record is what makes the gateway auditable.

## 3. Interposition — what "forced" actually requires

An agent is only *forced* through policy if it has no way around it. Two channel patterns:

- **Tool-calling agents (MCP or equivalent)** — **BUILT.** In the AAC reference implementation,
  every tool call an agent makes against the automation platform passes through a policy engine
  before execution: default-deny (unclassified operations are refused), fail-closed (policy engine
  unreachable or timing out → the call is refused, never waved through), and **unconditional — the
  server has no configuration path that disables the gate; a deployment attempting to set one
  refuses to start** (an earlier disable flag was removed for exactly this reason: a governance
  claim with an off-switch is not a governance claim). The policy itself is in version control
  under mandatory human review, and destructive platform operations are additionally filtered out
  of the agent's tool catalog before it ever sees them.
- **Direct-API / CLI agents** — **DESIGNED.** Agents that call infrastructure APIs directly are
  governed by **credential custody**: the agents hold no ambient credentials; the only credentials
  that reach infrastructure live behind a policy-enforcing broker. The agent asks; policy decides;
  the broker acts. Interposition becomes a property of credential architecture, not of agent
  good manners.

The honest boundary, stated plainly: a governed channel governs what passes through it. An agent
handed shell access or standing credentials is outside any gateway's authority — which is precisely
why the credential-custody pattern, not the gateway alone, is the complete answer.

## 4. The decision layers

1. **Operation gate** — **BUILT.** Per-call authorization by operation class and named-automation
   registry: read-only operations allowed; approved automation launches allowed; platform mutations
   (credential changes, deletions, administrative writes) denied; everything unclassified denied by
   default.
2. **Action layer** — **POLICY-BUILT** (tested policy code; enforcement wiring is engagement work).
   Named business actions classified by risk; per-role permissions (from read-only through emergency);
   approval workflows with configurable approver counts and timeouts; time-boxed emergency access;
   environment and maintenance-window context gates that fail closed.
3. **Obligations layer** — **DESIGNED.** Each verdict carries the compliance obligations the action
   implicates, so one governed activity produces evidence across every framework the organization
   answers to — assessed once, reported many times. The strictest gate tier corresponds to the
   controls that every major framework independently agrees on. (How this mapping is computed is
   proprietary; what it produces — obligation-aware verdicts and multi-framework evidence — is the
   deliverable.)

## 5. The crown-jewels tier

Actions touching the jewels get the strictest class of gate, regardless of which agent or role asks.
(The table describes the tier's target behavior; per-row implementation status is in §8 — nothing
below is claimed as live beyond what that table says.)

| Jewel | Examples | Gate behavior |
|---|---|---|
| **Business rules** | pricing/recommendation/workflow logic; configuration that governs decisions; **the governance plane's own policies, decision data, and policy-load paths** | Deny by default · mandatory human approval · immutable signed evidence · emergency access only via time-boxed dual control |
| **Data** | datasets, databases, data pipelines, model artifacts | Same class; egress-shaped operations (broad reads followed by outbound movement) rank as jewel-touching |

**The plane governs changes to itself.** The governance layer's policies are business rules — the
most sensitive ones in the system. Under this tier a governed agent cannot modify, reload, or
re-register its own gate, and cannot mint new self-approved action routes; attempts are denied and
the denial is itself evidence. This property came from red-teaming our own reference
implementation: we found exactly this class of escalation path (a policy-reload route the agent
could launch, and a create-then-launch chain through auto-approved naming) and closed both in the
gate policy, with deny-verdict tests proving each path refuses (status in §8). Governance layers
that cannot protect themselves from their governed agents are decorative.

## 6. The activity/evidence plane

Every decision — allow and deny — persists with: a trace identifier, the authenticated actor
identity, the action and a digest of its arguments, the verdict and its reason, the tier, and the
exact policy version that decided. Evidence rows are append-only and cryptographically signed
(**BUILT** for assessment evidence today: signature, policy-library version, input hash, evaluating
job identity; **engagement work** extends the same store to per-decision agent verdicts).

What the accumulated stream answers — the bad-actor catalog:

- **Action outside role** — an actor doing what its role never does.
- **Denied-attempt signal** — refusals are not noise; a rising denial rate *is* the alarm, and an
  attempt to touch the governance plane is the loudest alarm in the system.
- **Off-pattern behavior** — novel operation mix, velocity, or hours against that actor's baseline.
- **Compromised-credential indicators** — a known agent identity behaving like a different actor.
- **Exfiltration-shaped sequences** — broad reads followed by outbound actions, ranked above
  configuration noise.
- **Jewel-touching activity, always ranked first** — who touched business rules or data, under what
  authorization, and how that deviates from their baseline.

These are control-grounded detections over decision records — a different instrument from (and a
complement to, not a replacement for) statistical anomaly detection or an EDR's runtime telemetry.

## 7. The integrity loop — when state changes anyway

Governance of the forced channels pairs with verification of the resulting state. In the reference
implementation (**BUILT**, measured): an unauthorized change to governed configuration is detected
by the event-driven loop and **reverted to the known-good baseline in ~12 seconds**, unattended,
with a help-desk record and evidence written — and a managed-change hold path routes *authorized*
change windows to human approval instead of blind enforcement. Agents change state; the plane
verifies the state they leave behind.

## 8. Built vs. extension — the honest table

| Capability | Status |
|---|---|
| Policy gate on every tool call (default-deny, fail-closed, **no disable path**) | **BUILT** |
| Destructive operations filtered from agent catalogs | **BUILT** |
| Policy under version control, human-reviewed | **BUILT** |
| Signed, append-only evidence store with provenance | **BUILT** (assessment evidence) |
| Integrity loop: detect → revert ~12 s + managed-change hold | **BUILT** |
| Role/risk/approval/emergency action layer | **POLICY-BUILT** — enforcement wiring is engagement work |
| Persisted per-decision log (trace id, identity, verdict, append-only) | **POLICY-BUILT** — schema + server write path shipped; deploy per environment |
| Load-bearing agent identity in the policy | **POLICY-BUILT** — enforced once the identity registry is published per environment |
| Crown-jewels tier incl. plane self-protection | **POLICY-BUILT** — escalation paths closed in the gate policy with deny-verdict tests; live once the policy bundle deploys |
| Credential-custody broker for direct-API agents | **DESIGNED** |
| Obligation-aware verdicts / multi-framework evidence projection | **DESIGNED** (proprietary method) |
| Bad-actor analytics catalog over the verdict stream | **DESIGNED** (queries specified; requires the persisted log) |

## 9. What an engagement looks like

1. **Map the agent surfaces** — every channel an agent can act through; classify governed vs open.
2. **Interpose** — gateway on tool-calling channels; credential custody for direct-API agents.
3. **Land the decision log** — every verdict persisted from day one; the analytics need history.
4. **Classify the jewels** — the customer names its business rules and data stores; the strictest
   tier lands on them and on the governance plane itself.
5. **Wire the action layer** — roles, approvals, emergency access against the customer's org model.
6. **Turn on the analytics** — the bad-actor catalog over the accumulating verdict stream.
7. **Prove it** — red-team the gate (including the self-protection recursion), measure the loop,
   hand the evidence to the customer's compliance organization.
