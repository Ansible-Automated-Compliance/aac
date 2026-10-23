# What Is Your AI Agent Allowed to Do? Answer That in Policy, Not in a Prompt

**Version:** v1.0
**Date:** 2026-08-21
**Status:** Draft for publication. Describes a shipped, running control.

---

Regulators have started asking a question that most AI deployments cannot answer.

The EU AI Act requires operators of high-risk AI systems to maintain human
oversight and keep records of how the system behaves. The NIST AI Risk Management
Framework asks organisations to map what an AI system can affect and to measure
whether the controls around it actually work. Both frameworks converge on a
deceptively simple demand: **state what the AI is permitted to do, and produce
evidence that the boundary held.**

If your answer is "we told it to be careful in the system prompt," you do not
have an answer. You have an intention.

This post describes how we govern an AI agent's access to Ansible Automation
Platform using the Model Context Protocol (MCP) and Open Policy Agent (OPA) — and,
just as importantly, what that control does not cover.

## The problem MCP creates

MCP is what makes an AI agent genuinely useful against an automation platform. It
exposes the platform's API as a set of tools the agent can call directly, so
instead of a human translating "why did last night's job fail" into six API
requests, the agent does it.

The difficulty is the size of what you just handed over. Our MCP server exposes
**447 controller tools**. Among them are `api_hosts_delete`,
`api_credentials_create`, `api_users_create`, and `api_settings_update`.

The agent is fast, competent, and working from natural-language intent. That
combination is precisely why the boundary cannot be the agent's own judgement. A
system prompt saying "do not delete anything" is advisory. It is not auditable, it
cannot be tested, it cannot be reviewed by a security lead who does not read
prompts, and it produces no record a regulator would accept.

**The control has to sit outside the agent, in the call path, and be expressed as
policy.**

## The architecture

```
   AI agent
      │  MCP tool call: name + arguments
      ▼
  ┌──────────────────────────────────────┐
  │  MCP server                          │
  │                                      │
  │  Layer 1 — tool-list filtering       │
  │    blocked tools never enter the     │
  │    agent's catalog                   │
  │                                      │
  │  Layer 2 — call-time check ──────┐   │
  └──────────────────────────────────┼───┘
                                     │  POST /v1/data/…/response
                                     ▼
                            ┌──────────────────┐
                            │       OPA        │
                            │  returns:        │
                            │    allow         │
                            │    decision      │
                            │    risk_level    │
                            │    reason        │
                            └──────────────────┘
                                     │
       ┌─────────────────────────────┘
       ▼
  allow == true  ──►  call proceeds to the controller
  allow != true  ──►  denied, reason returned to the agent
```

Two layers, doing different jobs. Layer 1 reduces temptation — a tool the agent
cannot see is a tool it will not attempt. Layer 2 is the actual control: it runs
on every call regardless of what the catalog said, so a tool name arriving by any
other route is still evaluated.

Never rely on Layer 1 alone. Catalog filtering is a usability feature. The
security property comes from Layer 2.

## Default deny, then earn allowance

Two lines carry most of the safety:

```rego
default allow      := false
default risk_level := "high"
```

A tool nobody has classified is high risk, and high risk is not allowed.

The consequence is the part worth dwelling on. **When a platform upgrade
introduces new MCP tools, those tools are denied until a human classifies them.**
The failure mode of an upgrade is a blocked capability, not a silently granted
one. That asymmetry is the entire design.

Capability is then granted by category:

| Category | Examples | Decision |
|---|---|---|
| `read_only` | list/get/status/logs across inventories, hosts, jobs, templates | Allow |
| `low` | Launching a job template on the approved list | Allow |
| `medium` | Project sync, scaffold creation | Allow, logged |
| `high` | Anything unclassified | Deny |
| `blocked` | Deletes, credential writes, user/org admin, settings changes | Deny, always |

The `blocked` set is enumerated explicitly even though the default would already
deny it. Enumerating it documents intent: anyone reading the policy can see that
deleting a host was considered and refused, not merely overlooked. That
distinction matters enormously to an auditor.

## Why the decider must not be the actor

The obvious alternative is to put these checks inside the MCP server's own code.
Resist it.

If enforcement lives in the server, the thing making the decision is the same
thing performing the action, in the same process, holding the same credentials.
**Every bug in the decision path becomes a bug with hands.**

OPA is a pure decision function: input in, decision out, nothing mutated. It holds
no credentials to the systems it governs, opens no connections to them, and cannot
act on its own conclusions. The consequences are worth spelling out:

| Property | Consequence |
|---|---|
| Cannot become an actuator | Compromising the policy engine grants no ability to *do* anything. At worst an attacker denies requests — availability, not breach |
| No credentials at rest | Nothing in it worth stealing |
| Deterministic and replayable | Same input, same decision, forever. A decision from six months ago reproduces exactly for an auditor |
| Testable in isolation | Unit-testable against synthetic inputs with no platform attached |
| Reviewable by non-programmers | A security lead can read the blocked list without reading Python |

The agent's granted posture is essentially read-only, with narrow enumerated
exceptions for launching pre-approved automation. This is the right default
because reading is where nearly all of the agent's value already is — diagnosing a
failed job, correlating an assessment result, tracing a workflow. An agent can be
enormously useful with no write capability at all, which means write capability
can be granted sparingly rather than assumed.

And the writes it does get are indirect. The agent cannot craft an arbitrary
change; it can launch a job template that a human wrote, reviewed, and registered
in git. The blast radius of "launch template 116" is bounded by what template 116
does — a human decision made in advance, under review.

## Fail closed, and mean it

Enforcement is only as good as its behaviour when the decision point is
unavailable. An OPA timeout or connection failure raises, and the call is refused:

```python
except httpx.TimeoutException:
    raise RuntimeError(f"OPA timeout for '{tool_name}' — failing closed")
except Exception as e:
    raise RuntimeError(f"OPA unreachable for '{tool_name}': {e} — failing closed")
```

If the policy engine is down, the agent can do nothing. That is the correct trade:
an agent that cannot act is an inconvenience; an agent acting unchecked because a
health check failed is an incident.

Plan for the operational consequence — OPA becomes a hard dependency of agent
usefulness, and needs the availability you would give any other control-plane
component.

## One Rego trap that will bite you

If any field in a Rego object literal is undefined, **the entire object is
undefined** and OPA returns `{}`. Your enforcement point then receives no `allow`
field at all — and an empty dict is not obviously a denial to code that was not
written carefully.

We hit this in production policy. Mitigate on both sides:

- **In policy** — put a `default` on every field of the response object.
- **At the enforcement point** — read the decision with a deny-by-default
  accessor, `result.get("allow", False)`, so a missing or malformed response
  denies rather than passing an empty object as truthy.

Then test against **empty input**, because that is the case that collapses:

```bash
# Must return a populated object with allow=false — never {} and never undefined.
opa eval -d mcp_governance.rego -f pretty 'data.ai_governance.mcp.response'
```

A policy that passes every realistic test case and collapses on an empty one will
fail in exactly the circumstance you least want it to.

## What this does not protect against

A control described without its limits invites misplaced confidence. Stated
plainly:

- **A compromised approved template.** The agent may launch template 26. If
  someone changes what template 26 *does*, policy will not notice. Template
  content is protected by git review, not by this control.
- **Over-broad read access.** Read-only is not harmless. Credential listings
  reveal names and structure; job logs can contain sensitive output. Decide
  deliberately what the agent may read, not only what it may change.
- **Argument-level abuse within an allowed tool.** Our policy checks the template
  id on a launch. It does not inspect every argument of every allowed tool. Extend
  the policy wherever arguments carry risk.
- **Anything outside the MCP path.** This governs MCP tool calls. An agent with
  shell access, a second unmanaged MCP server, or direct network reach to the API
  is outside this boundary entirely.
- **Prompt injection producing a *permitted* action.** Policy constrains
  capability, not intent. If an injected instruction causes the agent to launch an
  approved template at an unhelpful moment, policy will allow it — because it is
  allowed. Bound the blast radius of approved actions accordingly.

There is one more, and it is the sharpest. **Our approved-template list includes
the template that reloads OPA policy from git.** In principle the agent can cause
its own governing policy to be re-read. This is safe *only* because that path
reflects git, and git requires a reviewed pull request — the agent cannot author
policy, only cause already-reviewed policy to be reloaded. If you adopt this
model, preserve that property exactly: the load path must have no way to accept
content that has not passed human review.

## What the regulator actually gets

Come back to where we started. Under this model, the answer to "what is your AI
agent allowed to do?" is a file in git, reviewed by pull request, unit-tested, and
readable by someone who does not write code. The answer to "prove the boundary
held" is a decision log with tool, risk level, and outcome for every call —
the allows as much as the denies.

That is not the same thing as being compliant with the EU AI Act or the NIST AI
RMF. Compliance is a state an assessor determines. But it is the evidence an
assessor will ask for, produced automatically, as a by-product of the control
doing its job — rather than assembled by hand the week before an audit.

## Adoption checklist

1. Put the policy in **git**, reviewed by pull request. Policy that can be edited
   in place is not a control.
2. Set `default allow := false` and `default risk_level := "high"` before writing
   a single allow rule.
3. Enumerate blocked tools explicitly, even though the default denies them — it
   records intent.
4. `default` every field of the response object; verify with `opa eval` on
   **empty** input that you get a populated object rather than `{}`.
5. Read the decision with a deny-by-default accessor.
6. Fail closed on timeout and on unreachable.
7. Log every decision — allow *and* deny. The allows are the audit trail.
8. Return the reason to the agent so it stops rather than retries. A bare denial
   makes an agent try variations; an explained one makes it ask a human.
9. Re-review the approved list whenever templates change. Allowlists rot.
10. Confirm the policy load path cannot accept unreviewed content.

---

## Authorship

Drafted by **Tim Coulter** with **Claude (Anthropic, Claude Opus 5)** as
co-author. Claude documented the model from the running implementation and
verified the enforcement behaviour described here against the live policy engine.
Tim edits and authorises all shipped-state claims.
