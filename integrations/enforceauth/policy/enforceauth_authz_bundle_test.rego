# Unit tests for BUNDLE-mode decision. State is injected via `with data.aac...`,
# mirroring what the /v1/bundle.tar.gz endpoint delivers. Run: opa test policy/ -v
package enforceauth.aac_compliance_bundle

import rego.v1

_bundle(hosts) := {"aac": {"compliance": {"hosts": hosts}}}

_compliant_fresh := _bundle({"web-01": {"frameworks": {"cis_rhel9": {"compliant": true, "compliance_percentage": 94.67, "stale": false, "age_seconds": 36000}}}})

_stale := _bundle({"web-01": {"frameworks": {"cis_rhel9": {"compliant": true, "compliance_percentage": 94.67, "stale": true, "age_seconds": 200000}}}})

_below := _bundle({"web-01": {"frameworks": {"cis_rhel9": {"compliant": false, "compliance_percentage": 71.0, "stale": false, "age_seconds": 100}}}})

test_allow_when_compliant_and_fresh if {
	data.enforceauth.aac_compliance_bundle.allow with data.aac as _compliant_fresh.aac with input as {"host": "web-01"}
}

test_deny_when_stale if {
	not data.enforceauth.aac_compliance_bundle.allow with data.aac as _stale.aac with input as {"host": "web-01"}
}

test_deny_when_below_threshold if {
	not data.enforceauth.aac_compliance_bundle.allow with data.aac as _below.aac with input as {"host": "web-01"}
}

test_deny_when_host_absent_from_bundle if {
	not data.enforceauth.aac_compliance_bundle.allow with data.aac as _compliant_fresh.aac with input as {"host": "unknown-host"}
}

test_reason_host_not_in_bundle if {
	"host_not_in_bundle" in data.enforceauth.aac_compliance_bundle.deny_reasons with data.aac as _compliant_fresh.aac
		with input as {"host": "unknown-host"}
}
