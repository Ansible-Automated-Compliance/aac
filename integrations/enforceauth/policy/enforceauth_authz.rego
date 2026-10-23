# EnforceAuth-side OPA policy — AAC compliance STATE as runtime authorization context.
#
#   State (AAC)      : "Is this host configured to the standard we're accountable to, right now?"
#   Runtime (EnforceAuth): "May this identity (human or AI agent) act on it, right now?"
#
# This policy joins the two seams: EnforceAuth denies a runtime action against a
# target host UNLESS AAC holds a FRESH, COMPLIANT assessment for that host. It is
# fail-closed by construction — absence of evidence (API unreachable, host never
# assessed, stale result, framework missing) resolves to deny, never allow.
#
# Deploy this in EnforceAuth's OPA engine. It pulls host state at decision time
# from the AAC Compliance-State API (see integrations/enforceauth/).
package enforceauth.aac_compliance

import rego.v1

# ── Operator configuration (override via data document or bundle) ────────────
# Base URL of the AAC Compliance-State API, reachable from EnforceAuth's engine.
default aac_api_base := "http://aac-compliance-state:8090"

# Frameworks that must ALL be compliant + fresh for the action to be allowed.
# A resource gated on multiple standards (e.g. CIS + STIG) lists them all.
default required_frameworks := {"cis_rhel9"}

# Minimum compliance percentage required, per framework.
default min_compliance := 90.0

# Staleness ceiling enforced by THIS policy (defense in depth — the API also
# computes `stale`, but the decision does not trust that flag blindly).
default max_age_seconds := 86400 # 24h

# ── Fetch compliance state for the target host (runtime pull) ────────────────
# input.host is the identifier EnforceAuth resolved for the resource being
# accessed. The AAC API accepts either a hostname or an IP address.
state := body if {
	resp := http.send({
		"method": "GET",
		"url": sprintf("%s/v1/compliance/hosts/%s", [aac_api_base, input.host]),
		"timeout": "2s",
		"raise_error": false,
		"cache": true,
	})
	resp.status_code == 200
	body := resp.body
}

# ── Decision ─────────────────────────────────────────────────────────────────
default allow := false

allow if {
	count(required_frameworks) > 0
	state.found == true
	count(failing_frameworks) == 0
}

# A required framework fails if it is absent, non-compliant, below the score
# threshold, flagged stale by the API, or older than this policy's own ceiling.
failing_frameworks contains fw if {
	some fw in required_frameworks
	not framework_ok(fw)
}

framework_ok(fw) if {
	f := state.frameworks[fw]
	f.compliant == true
	f.compliance_percentage >= min_compliance
	f.stale == false
	f.age_seconds <= max_age_seconds
}

# ── Audit reasons — EnforceAuth logs these alongside every deny ──────────────
deny_reasons contains "aac_unreachable_or_no_state" if not state

deny_reasons contains "host_not_found_in_aac" if state.found == false

deny_reasons contains sprintf("framework_not_ok:%s", [fw]) if {
	state.found == true
	some fw in failing_frameworks
}

# Structured decision object EnforceAuth consumes at data.enforceauth.aac_compliance.decision
decision := {
	"allow": allow,
	"host": input.host,
	"required_frameworks": required_frameworks,
	"deny_reasons": deny_reasons,
}
