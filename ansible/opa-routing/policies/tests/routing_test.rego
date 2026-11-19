# Tests for the Mythos patch-routing policy (aac.mythos.routing).
#
# The auto route patches without a human, so most of these tests are about the
# inputs that must NOT reach it: a fact that is missing, mistyped or written in
# a form the policy cannot read.
package aac.mythos.routing_test

import rego.v1

import data.aac.mythos.routing

clean_facts := {
	"affected_count": 12,
	"affected_cves": 3,
	"max_severity": "HIGH",
	"kev_present": false,
	"has_vendor_fix": true,
	"eol_exposed": false,
}

agent := {"recommended_route": "auto_patch", "rationale": "routine"}

decide(facts) := d if {
	d := routing.decision with input as {"agent": agent, "facts": facts}
}

without(key) := object.remove(clean_facts, [key])

with_fact(key, value) := object.union(clean_facts, {key: value})

# ── The auto route, and only with every fact readable ────────────────
test_clean_facts_route_auto if {
	d := decide(clean_facts)
	d.route == "auto"
	d.overrode_agent == false
}

test_string_typed_facts_route_auto if {
	d := decide({
		"affected_count": " 12 ", "max_severity": "high",
		"kev_present": "False", "has_vendor_fix": "true",
	})
	d.route == "auto"
}

test_zero_count_is_a_reading_not_a_gap if {
	decide(with_fact("affected_count", 0)).route == "auto"
}

# ── The three inputs that used to reach auto ─────────────────────────
test_missing_affected_count_needs_approval if {
	d := decide(without("affected_count"))
	d.route == "approve"
	"fact affected_count is missing or unreadable — human approval required" in d.reasons
}

test_count_with_thousands_separator_needs_approval if {
	d := decide(with_fact("affected_count", "1,321"))
	d.route == "approve"
	"fact affected_count is missing or unreadable — human approval required" in d.reasons
}

test_lowercase_critical_needs_approval if {
	d := decide(with_fact("max_severity", "critical"))
	d.route == "approve"
	"max_severity is CRITICAL — human approval required" in d.reasons
}

# ── Every other missing or malformed fact ────────────────────────────
test_missing_severity_needs_approval if decide(without("max_severity")).route == "approve"

test_unknown_severity_needs_approval if decide(with_fact("max_severity", "SEVERE")).route == "approve"

test_missing_kev_needs_approval if decide(without("kev_present")).route == "approve"

test_unreadable_kev_needs_approval if decide(with_fact("kev_present", "yes")).route == "approve"

test_negative_count_needs_approval if decide(with_fact("affected_count", -1)).route == "approve"

test_non_numeric_count_needs_approval if decide(with_fact("affected_count", "many")).route == "approve"

test_null_count_needs_approval if decide(with_fact("affected_count", null)).route == "approve"

test_missing_vendor_fix_investigates if {
	d := decide(without("has_vendor_fix"))
	d.route == "investigate"
	"vendor-fix status missing or unreadable — routing to investigate, nothing is patched" in d.reasons
	not "no vendor fix available — routing to investigate (replacement, not patch)" in d.reasons
}

test_no_facts_at_all_never_auto if {
	d := routing.decision with input as {"agent": agent}
	d.route == "investigate"
}

test_empty_input_still_returns_a_decision if {
	d := routing.decision with input as {}
	d.route == "investigate"
	d.agent_recommended == "absent"
	d.overrode_agent == true
}

# ── The high-consequence conditions ──────────────────────────────────
test_critical_needs_approval if decide(with_fact("max_severity", "CRITICAL")).route == "approve"

test_kev_needs_approval if decide(with_fact("kev_present", true)).route == "approve"

test_kev_string_needs_approval if decide(with_fact("kev_present", "true")).route == "approve"

test_blast_radius_over_threshold_needs_approval if {
	d := decide(with_fact("affected_count", "1321"))
	d.route == "approve"
	"blast radius 1321 exceeds threshold 100 — human approval required" in d.reasons
}

test_blast_radius_at_threshold_is_auto if decide(with_fact("affected_count", 100)).route == "auto"

test_no_vendor_fix_investigates if {
	d := decide(with_fact("has_vendor_fix", false))
	d.route == "investigate"
	"no vendor fix available — routing to investigate (replacement, not patch)" in d.reasons
}

# ── The agent never widens the route ─────────────────────────────────
test_agent_auto_recommendation_is_overridden if {
	d := decide(with_fact("kev_present", true))
	d.agent_recommended == "auto_patch"
	d.overrode_agent == true
}

test_route_is_always_one_of_three if {
	every facts in [clean_facts, {}, without("affected_count"), with_fact("max_severity", 7)] {
		decide(facts).route in {"auto", "approve", "investigate"}
	}
}
