# Network-free unit tests for the EnforceAuth authorization policy.
# http.send is mocked so the allow/deny decision is verified against the API
# response contract without a running service. Run: opa test policy/ -v
package enforceauth.aac_compliance

import rego.v1

# ── Mocked API responses (shape = GET /v1/compliance/hosts/{host}) ───────────
_resp(body) := {"status_code": 200, "body": body}

_fresh_compliant := _resp({
	"host_key": "web-01.lab.local",
	"found": true,
	"frameworks": {"cis_rhel9": {
		"compliant": true,
		"compliance_percentage": 94.67,
		"stale": false,
		"age_seconds": 36000,
	}},
})

_stale := _resp({
	"host_key": "web-01.lab.local",
	"found": true,
	"frameworks": {"cis_rhel9": {
		"compliant": true,
		"compliance_percentage": 94.67,
		"stale": true,
		"age_seconds": 200000,
	}},
})

_below_threshold := _resp({
	"found": true,
	"frameworks": {"cis_rhel9": {
		"compliant": false,
		"compliance_percentage": 71.0,
		"stale": false,
		"age_seconds": 100,
	}},
})

# Host assessed for a DIFFERENT framework than the one gating this resource.
_wrong_framework := _resp({
	"found": true,
	"frameworks": {"stig_rhel9": {
		"compliant": true,
		"compliance_percentage": 99.0,
		"stale": false,
		"age_seconds": 100,
	}},
})

_not_found := _resp({"found": false, "frameworks": {}})

_unreachable := {"status_code": 503, "body": {}}

# ── Tests: exactly one path allows, every failure mode denies ────────────────
test_allow_when_fresh_and_compliant if {
	data.enforceauth.aac_compliance.allow with http.send as _fresh_compliant
		with input as {"host": "web-01.lab.local"}
}

test_deny_when_stale if {
	not data.enforceauth.aac_compliance.allow with http.send as _stale
		with input as {"host": "web-01.lab.local"}
}

test_deny_when_below_threshold if {
	not data.enforceauth.aac_compliance.allow with http.send as _below_threshold
		with input as {"host": "web-01.lab.local"}
}

test_deny_when_required_framework_absent if {
	not data.enforceauth.aac_compliance.allow with http.send as _wrong_framework
		with input as {"host": "web-01.lab.local"}
}

test_deny_when_host_not_found if {
	not data.enforceauth.aac_compliance.allow with http.send as _not_found
		with input as {"host": "ghost-host"}
}

test_deny_when_api_unreachable if {
	not data.enforceauth.aac_compliance.allow with http.send as _unreachable
		with input as {"host": "web-01.lab.local"}
}

# ── Audit-reason coverage ────────────────────────────────────────────────────
test_reason_host_not_found if {
	"host_not_found_in_aac" in data.enforceauth.aac_compliance.deny_reasons with http.send as _not_found
		with input as {"host": "ghost-host"}
}

test_reason_unreachable if {
	"aac_unreachable_or_no_state" in data.enforceauth.aac_compliance.deny_reasons with http.send as _unreachable
		with input as {"host": "web-01.lab.local"}
}

test_reason_framework_not_ok if {
	"framework_not_ok:cis_rhel9" in data.enforceauth.aac_compliance.deny_reasons with http.send as _below_threshold
		with input as {"host": "web-01.lab.local"}
}
