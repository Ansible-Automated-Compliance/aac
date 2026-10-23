# Governing What AI Can Do — MCP Tool Calls Under OPA Policy

**Version:** v1.0
**Date:** 2026-08-07
**Audience:** Internal engineering and security; customers and partners under NDA.
**Status:** Describes a shipped, running control. Example policy included for adoption.

---

## 1. The problem

Giving an AI agent an MCP server pointed at an automation platform hands it the
platform's entire API surface. In AAC's case that is **46 AAP controller tools** —
and among them are `api_hosts_delete`, `api_credentials_create`,
`api_users_create` and `api_settings_update`.

The agent is competent, fast, and operating from natural-language intent. That
combination is exactly why the boundary cannot be *the agent's own judgement*, a
system prompt, or a instruction to "be careful". Those are advisory. They are not
controls, they are not auditable, and they cannot be reviewed by anyone who does
not read prompts.

**The control has to sit outside the agent, in the call path, and be expressed as
policy.** That is what OPA is for, and AAC already governs every MCP tool call
this way.

---

## 2. Architecture

```
   Claude / agent
        │  MCP tool call: name + arguments
        ▼
  ┌─────────────────────────────────────────────┐
  │  MCP server  (OPAGovernedAAPServer)         │
  │                                             │
  │  Layer 1 — tool list filtering              │
  │    blocked tools never appear in the         │
  │    agent's catalog at all                    │
  │                                             │
  │  Layer 2 — call-time check ────────────┐    │
  └────────────────────────────────────────┼────┘
                                           │ POST /v1/data/ai_governance/mcp/response
                                           ▼
                                  ┌──────────────────┐
                                  │  OPA             │
                                  │  package         │
                                  │  ai_governance.  │
                                  │       mcp        │
                                  │                  │
                                  │  returns:        │
                                  │   allow          │
                                  │   decision       │
                                  │   risk_level     │
                                  │   reason         │
                                  └──────────────────┘
                                           │
        ┌──────────────────────────────────┘
        ▼
   allow == true  ──► call proceeds to the AAP controller
   allow != true  ──► denied, reason returned to the agent
```

**Two layers, doing different jobs.** Layer 1 is *reduction of temptation* — a
tool the agent cannot see is a tool it will not attempt, which keeps the
interaction clean. Layer 2 is *the actual control* — it runs on every call
regardless of what the catalog said, so a tool name arriving by any other route
is still evaluated.

Never rely on Layer 1 alone. Catalog filtering is a usability feature; the
security property comes from Layer 2.

---

## 3. The decision contract

**Input** the MCP server sends:

```json
{
  "input": {
    "tool":      "api_job_templates_launch_create",
    "arguments": { "id": 116 },
    "agent":     "claude-code"
  }
}
```

**Output** the policy returns:

| Field | Type | Purpose |
|---|---|---|
| `allow` | bool | The decision. The only field the enforcement point acts on |
| `decision` | `ALLOW` / `DENY` | Human-readable form for logs |
| `risk_level` | `read_only` / `low` / `medium` / `high` / `blocked` | Why, in one word |
| `reason` | string | Why, in a sentence — returned to the agent so it can adapt |

Returning `reason` to the agent matters more than it looks. A bare denial makes
an agent retry variations; an explained denial ("template 999 is not in the
approved set") makes it stop and ask a human. **Explaining the boundary makes the
boundary hold.**

---

## 4. Default deny, then earn allowance

Two defaults carry most of the safety:

```rego
default allow      := false
default risk_level := "high"
```

A tool nobody has classified is `high` risk, and `high` is not allowed. **New
tools appearing in a platform upgrade are therefore denied until someone
classifies them** — the failure mode is a blocked capability, not a silent new
one. That asymmetry is the whole design.

Capability is then granted by category:

| Category | Examples | Decision |
|---|---|---|
| `read_only` | list/get/status/logs across inventories, hosts, jobs, templates | **Allow** |
| `low` | Launching a job template that is on the approved list | **Allow** |
| `medium` | Project sync, demo scaffold creation | **Allow, logged** |
| `high` | Anything unclassified | **Deny** |
| `blocked` | Deletes, credential writes, user/org admin, settings, job cancel | **Deny, always** |

The `blocked` set is worth stating explicitly rather than relying on the default,
because it documents intent. Anyone reading the policy can see that deleting a
host was considered and refused, not merely overlooked.

---

## 5. Why OPA in a read-only posture matters

This is the heart of the model, and it has two distinct meanings that reinforce
each other.

### 5.1 OPA itself performs no actions

OPA is a **pure decision function**: input in, decision out, nothing mutated. It
holds no credentials to the systems it governs, opens no connections to them, and
has no capability to act on its own conclusions.

The consequences are worth spelling out:

| Property | Consequence |
|---|---|
| **Cannot be turned into an actuator** | Compromising the policy engine does not grant the attacker the ability to *do* anything. At worst they deny requests — an availability problem, not a breach |
| **No credentials at rest** | OPA never holds AAP tokens, SSH keys or cloud credentials. There is nothing in it worth stealing |
| **Deterministic and replayable** | Same input, same decision, forever. A decision from six months ago can be reproduced exactly for an auditor |
| **Testable in isolation** | Policy can be unit-tested with `opa test` against synthetic inputs, with no platform attached and no risk of side effects |
| **Reviewable by non-programmers** | Rego is declarative. A security lead can read `blocked_tools` and understand the control without reading Python |

Contrast the alternative — enforcement embedded in the MCP server's own code.
Then the thing making the decision is the same thing performing the action, in
the same process, with the same credentials. Every bug in the decision path is a
bug with hands.

### 5.2 The agent's default posture is read-only

The policy grants the agent an essentially **read-only view of the platform**,
with narrow, enumerated exceptions for launching pre-approved automation.

This is the right default because reading is where nearly all the agent's value
is. Diagnosing a failed job, correlating an assessment result, explaining why a
control failed, tracing a workflow — all reads. The agent can be enormously
useful with no write capability at all, which means write capability can be
granted sparingly rather than assumed.

**And the writes it does get are indirect and pre-vetted.** The agent cannot
craft an arbitrary change. It can launch a job template that a human wrote,
reviewed and registered. The blast radius of "launch template 116" is bounded by
what template 116 does — which is a human decision made in advance, in git, under
review.

> **A note on honesty.** The approved-template list includes the template that
> reloads OPA policies from git. In principle the agent can therefore cause its
> own governing policy to be reloaded. This is safe **only because that path
> reflects git**, and git requires a reviewed pull request. The agent cannot
> author policy; it can only cause the already-reviewed policy to be re-read.
> If you adopt this model, preserve that property: **the load path must have no
> way to inject content that has not passed human review.**

---

## 6. Example policy

A minimal, self-contained version of the model. Adapt the tool names to your own
MCP server.

```rego
package ai_governance.mcp

import rego.v1

# ---------------------------------------------------------------------------
# Input:  {tool, arguments, agent}
# Output: {allow, decision, risk_level, reason}
# ---------------------------------------------------------------------------

# Safety comes from these two defaults. An unclassified tool is high risk,
# and high risk is not allowed — so a platform upgrade that introduces new
# tools fails CLOSED (capability blocked) rather than open.
default allow      := false
default risk_level := "high"

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

read_only_tools := {
	"api_ping_list",
	"api_jobs_list", "api_jobs_read", "api_jobs_stdout_read",
	"api_hosts_list", "api_hosts_read",
	"api_inventories_list", "api_inventories_read",
	"api_job_templates_list", "api_job_templates_read",
}

# Stated explicitly even though `default allow := false` would already deny
# these. Enumerating them documents that the refusal was deliberate.
blocked_tools := {
	"api_hosts_delete", "api_inventories_delete", "api_job_templates_delete",
	"api_credentials_create", "api_credentials_update", "api_credentials_delete",
	"api_users_create", "api_users_update", "api_users_delete",
	"api_settings_update", "api_settings_delete",
	"api_jobs_cancel_create",
}

# Job templates a human has reviewed and approved for AI launch.
approved_template_ids := {10, 11, 12, 26, 27}

launch_tools := {"run_job", "api_job_templates_launch_create"}

# Accept either argument spelling without letting an absent id resolve to
# something accidentally permitted.
_template_id := id if { id := input.arguments.id }
_template_id := id if {
	not input.arguments.id
	id := input.arguments.template_id
}

# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------

risk_level := "read_only" if input.tool in read_only_tools

risk_level := "blocked" if input.tool in blocked_tools

risk_level := "low" if {
	input.tool in launch_tools
	_template_id in approved_template_ids
}

risk_level := "medium" if input.tool in {"api_projects_update_create"}

# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

allow if risk_level in {"read_only", "low", "medium"}

decision := "ALLOW" if allow
decision := "DENY" if not allow

# CRITICAL: `response` below is an object literal. In Rego, if ANY field in an
# object literal is undefined, the WHOLE object is undefined — OPA then returns
# {} and the enforcement point sees no decision at all. A `default` on every
# field that can fail to match guarantees the object always resolves.
default reason := "No specific rule matched — see risk_level for the basis"

reason := "Read-only operation — allowed" if risk_level == "read_only"

reason := sprintf("Job launch approved — template %v is in the approved set", [_template_id]) if {
	risk_level == "low"
}

reason := "Project sync — allowed with logging" if risk_level == "medium"

reason := sprintf("Tool '%v' is blocked for AI agents", [input.tool]) if {
	risk_level == "blocked"
}

response := {
	"allow":      allow,
	"decision":   decision,
	"risk_level": risk_level,
	"reason":     reason,
}
```

### 6.1 The `{}` trap

The comment above `default reason` is not decoration — it describes a real
failure this platform hit. If any field of an object literal is undefined, the
entire object is undefined and OPA returns `{}`. The enforcement point then sees
no `allow` field at all.

**Mitigate on both sides:**

- **In policy** — `default` every field that could fail to match.
- **At the enforcement point** — read the decision as
  `result.get("allow", False)`, so a missing or malformed response denies rather
  than passing an empty dict as truthy.

That pair is what makes an empty policy response safe instead of catastrophic.

### 6.2 Test it against empty input

The single most valuable test, because it is the case that collapses:

```bash
# Must return a populated object with allow=false — never {} and never undefined.
opa eval -d ai_mcp_governance.rego -f pretty 'data.ai_governance.mcp.response'

# Then the real cases:
opa eval -d ai_mcp_governance.rego -f pretty \
  -i <(echo '{"tool":"api_hosts_delete"}') 'data.ai_governance.mcp.response'
# expect: allow=false, risk_level="blocked"

opa eval -d ai_mcp_governance.rego -f pretty \
  -i <(echo '{"tool":"api_jobs_list"}') 'data.ai_governance.mcp.response'
# expect: allow=true, risk_level="read_only"

opa eval -d ai_mcp_governance.rego -f pretty \
  -i <(echo '{"tool":"api_job_templates_launch_create","arguments":{"id":999}}') \
  'data.ai_governance.mcp.response'
# expect: allow=false, risk_level="high" — 999 is not in the approved set, so no
# low-risk rule matched and it falls through to the default deny

opa eval -d ai_mcp_governance.rego -f pretty \
  -i <(echo '{"tool":"some_brand_new_tool"}') 'data.ai_governance.mcp.response'
# expect: allow=false, risk_level="high" — this is the platform-upgrade case
```

> **Verified.** The example policy above was extracted from this document and run
> against **OPA 1.8.0**; all six cases produce the stated results, including the
> empty-input case returning a populated object rather than `{}`.

---

## 7. Fail-closed behaviour

Enforcement is only as good as its behaviour when the decision point is
unavailable. In this implementation an OPA timeout or connection failure raises,
and the tool call is refused with an error rather than proceeding:

```python
except httpx.TimeoutException:
    raise RuntimeError(f"OPA timeout for '{tool_name}' — failing closed")
except Exception as e:
    raise RuntimeError(f"OPA unreachable for '{tool_name}': {e} — failing closed")
```

**If the policy engine is down, the agent can do nothing.** That is the correct
trade: an agent that cannot act is an inconvenience; an agent acting unchecked
because a health check failed is an incident.

Note the operational consequence and plan for it — OPA becomes a hard dependency
of agent usefulness, so it needs the availability you would give any other
control-plane component.

---

## 8. What this does not protect against

Stated plainly, because a control described without its limits invites misplaced
confidence:

- **A compromised approved template.** The agent may launch template 26. If
  someone changes what template 26 *does*, policy will not notice. Template
  content is protected by git review, not by this control.
- **Over-broad read access.** Read-only is not harmless. `api_credentials_list`
  reveals credential *names and structure*; job logs can contain sensitive
  output. Decide deliberately what the agent may read, not just what it may
  change.
- **Argument-level abuse within an allowed tool.** The example policy checks the
  template id. It does not inspect every argument of every allowed tool. Extend
  the policy where arguments carry risk.
- **Anything outside the MCP path.** This governs the agent's MCP tool calls. An
  agent with shell access, a second unmanaged MCP server, or direct network
  reach to the API is outside this boundary entirely.
- **Prompt injection producing a *permitted* action.** Policy constrains
  capability, not intent. If an injected instruction causes the agent to launch
  an approved template at an unhelpful moment, policy will allow it — because it
  is allowed. Bound the blast radius of approved actions accordingly.

---

## 9. Adoption checklist

1. Put the policy in **git**, reviewed by pull request. Policy that can be edited
   in place is not a control.
2. Set `default allow := false` and `default risk_level := "high"` before writing
   a single allow rule.
3. Enumerate `blocked_tools` explicitly, even though the default already denies
   them — it records intent.
4. `default` every field of the response object; verify with `opa eval` on
   **empty** input that you get a populated object rather than `{}`.
5. Read the decision at the enforcement point with a **deny-by-default accessor**
   (`.get("allow", False)`).
6. Fail closed on timeout and on unreachable.
7. Log every decision with tool, risk level and outcome — allow *and* deny. The
   allows are the audit trail.
8. Return `reason` to the agent so it can stop rather than retry.
9. Re-review the approved-template list whenever templates change. It is an
   allowlist, and allowlists rot.
10. Confirm the policy load path cannot accept unreviewed content.

---

## Authorship

Drafted by **Tim Coulter** with **Claude (Anthropic, Claude Opus 5)** as
co-author. Claude documented the model from the running implementation — the
`ai_governance.mcp` policy and the OPA-governed MCP server enforcement point —
and wrote the example policy for adoption. Tim edits and authorises all
shipped-state claims.
