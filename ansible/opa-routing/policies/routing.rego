# AAC — Mythos-on-AO remediation routing policy
#
# The governance boundary for the AO Mythos demo. The AI triage agent
# REASONS and produces a recommendation; this policy DECIDES the route the
# workflow switch acts on. The agent proposes, policy disposes — enforced by
# OPA, not by the model's own output.
#
# Entrypoint: data.aac.mythos.routing.decision
#   POST /v1/data/aac/mythos/routing/decision  with body {"input": {...}}
#
# Input contract (from the AO workflow: identify set_stats + triage_agent):
#   {
#     "agent":  { "recommended_route": "auto_patch|approve_patch|investigate",
#                 "rationale": "<free text, informational only>" },
#     "facts":  { "affected_count": <int blast radius>,
#                 "affected_cves":  <int>,
#                 "max_severity":   "CRITICAL|HIGH|MEDIUM|LOW",
#                 "kev_present":    <bool, actively exploited>,
#                 "has_vendor_fix": <bool>,
#                 "eol_exposed":    <bool> }
#   }
#
# Output (decision): { route, authority, agent_recommended, overrode_agent, reasons }
#   route ∈ {auto, approve, investigate}
#
# The thresholds below are OWNED BY THE OPERATOR, not the model. This policy is
# AAC-demo-specific and lives here, never in the vendor-neutral rego library.

package aac.mythos.routing

import rego.v1

# ── Operator-owned thresholds ─────────────────────────────────────────
# A change touching more than this many host/component pairs is high-
# consequence and needs a human, even if everything else looks routine.
blast_radius_threshold := 100

# ── Input normalization (fail closed) ─────────────────────────────────
# The AO http_request node templates the identify facts in, and depending on
# how set_stats typed them they can arrive as native JSON or as strings
# ("1321", "true"). Each fact is normalized here, and a fact that is missing or
# cannot be read is recorded in `unreadable` instead of being given a default.
# Until 2026-11-18 a missing affected_count defaulted to 0, a count written as
# "1,321" failed to parse and fell back to 0, and a severity of "critical" did
# not match "CRITICAL" -- all three reached the auto route. A fact the policy
# cannot read is never evidence that a change is low-consequence.

# A count is a non-negative whole number, or a string of digits. Anything else
# ("1,321", "many", "") is unreadable: a separator can mean thousands or a
# decimal point, and guessing is not a basis for patching without a human.
affected_count := input.facts.affected_count if {
	is_number(input.facts.affected_count)
	input.facts.affected_count >= 0

	# A count of hosts is a whole number. 5.5 is a sign the fact was computed
	# or parsed wrongly, and is unreadable like any other malformed count.
	floor(input.facts.affected_count) == input.facts.affected_count
}

affected_count := to_number(trim_space(input.facts.affected_count)) if {
	is_string(input.facts.affected_count)
	regex.match(`^[0-9]+$`, trim_space(input.facts.affected_count))
}

known_severities := {"CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE"}

max_severity := upper(trim_space(input.facts.max_severity)) if {
	is_string(input.facts.max_severity)
	upper(trim_space(input.facts.max_severity)) in known_severities
}

_as_bool(x) := x if is_boolean(x)

_as_bool(x) if {
	is_string(x)
	lower(trim_space(x)) == "true"
}

_as_bool(x) := false if {
	is_string(x)
	lower(trim_space(x)) == "false"
}

vendor_fix := _as_bool(input.facts.has_vendor_fix)

kev := _as_bool(input.facts.kev_present)

has_vendor_fix if vendor_fix == true

kev_present if kev == true

_count_known if affected_count >= 0

_severity_known if max_severity in known_severities

_vendor_fix_known if is_boolean(vendor_fix)

_kev_known if is_boolean(kev)

unreadable contains "affected_count" if not _count_known

unreadable contains "max_severity" if not _severity_known

unreadable contains "has_vendor_fix" if not _vendor_fix_known

unreadable contains "kev_present" if not _kev_known

# ── Route decision ────────────────────────────────────────────────────
# Default is a human approval. Auto-remediation is the route that has to be
# earned: every fact present and readable, a vendor fix, and none of the
# high-consequence conditions. investigate and auto are mutually exclusive
# (one requires no confirmed vendor fix, the other requires one), so there is
# no rule conflict.

default route := "approve"

# No confirmed vendor fix -- either the facts say there is none (a replacement
# problem, not a patch) or the fix status is missing or unreadable. Routed to
# investigate regardless of what the agent said; it is the route that patches
# nothing.
route := "investigate" if not has_vendor_fix

route := "auto" if {
	has_vendor_fix
	count(unreadable) == 0
	not requires_human
}

requires_human if max_severity == "CRITICAL"

requires_human if kev_present

requires_human if affected_count > blast_radius_threshold

# ── Compare against the agent's recommendation (for the override story) ──
# Normalize the agent's vocabulary (auto_patch/approve_patch/investigate) to the
# policy's (auto/approve/investigate) so we can tell when policy overrode it.
# A missing recommendation is "absent"; without that default the whole decision
# object was undefined when the agent returned nothing.
agent_recommended := object.get(object.get(input, "agent", {}), "recommended_route", "absent")

default agent_route := "absent"

agent_route := "auto" if agent_recommended == "auto_patch"

agent_route := "approve" if agent_recommended == "approve_patch"

agent_route := "investigate" if agent_recommended == "investigate"

agent_route := agent_recommended if {
	is_string(agent_recommended)
	not agent_recommended in {"auto_patch", "approve_patch", "investigate"}
}

overrode_agent := route != agent_route

# ── Human-readable reasons (evidence + presenter narration) ───────────
reasons contains "no vendor fix available — routing to investigate (replacement, not patch)" if {
	vendor_fix == false
}

reasons contains "vendor-fix status missing or unreadable — routing to investigate, nothing is patched" if {
	not _vendor_fix_known
}

reasons contains sprintf("fact %v is missing or unreadable — human approval required", [name]) if {
	has_vendor_fix
	some name in unreadable
}

reasons contains "max_severity is CRITICAL — human approval required" if {
	has_vendor_fix
	max_severity == "CRITICAL"
}

reasons contains "actively exploited (KEV) — human approval required" if {
	has_vendor_fix
	kev_present
}

reasons contains sprintf("blast radius %v exceeds threshold %v — human approval required", [affected_count, blast_radius_threshold]) if {
	has_vendor_fix
	affected_count > blast_radius_threshold
}

reasons contains "low-consequence change (vendor fix, not actively exploited, within blast-radius threshold) — auto-remediation permitted" if {
	route == "auto"
}

# ── The decision object the workflow switch reads ─────────────────────
decision := {
	"route": route,
	"authority": "policy",
	"agent_recommended": agent_recommended,
	"overrode_agent": overrode_agent,
	"reasons": reasons,
}
