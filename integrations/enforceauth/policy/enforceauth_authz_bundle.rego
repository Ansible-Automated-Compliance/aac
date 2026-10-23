# EnforceAuth-side OPA policy — BUNDLE mode.
#
# Identical decision semantics to enforceauth_authz.rego, but reads AAC compliance
# state from `data.aac.compliance` (delivered by the AAC Compliance-State API's
# /v1/bundle.tar.gz endpoint) instead of pulling per-decision via http.send.
#
# This is the preferred pattern for EnforceAuth's edge-deployed OPA (sidecar /
# gateway / in-app) and for air-gapped Herald: the bundle is pulled periodically,
# so the authorization decision itself does zero network I/O and stays well inside
# the sub-50ms budget. Same fail-closed guarantee — a host absent from the bundle,
# or a stale/non-compliant framework, resolves to deny.
package enforceauth.aac_compliance_bundle

import rego.v1

default required_frameworks := {"cis_rhel9"}

default min_compliance := 90.0

default max_age_seconds := 86400

# Preloaded state for the target host (undefined if the host isn't in the bundle).
host := data.aac.compliance.hosts[input.host]

default allow := false

allow if {
	count(required_frameworks) > 0
	host # host present in the bundle
	count(failing_frameworks) == 0
}

failing_frameworks contains fw if {
	some fw in required_frameworks
	not framework_ok(fw)
}

framework_ok(fw) if {
	f := host.frameworks[fw]
	f.compliant == true
	f.compliance_percentage >= min_compliance
	f.stale == false
	f.age_seconds <= max_age_seconds
}

deny_reasons contains "host_not_in_bundle" if not host

deny_reasons contains sprintf("framework_not_ok:%s", [fw]) if {
	host
	some fw in failing_frameworks
}

decision := {
	"allow": allow,
	"host": input.host,
	"required_frameworks": required_frameworks,
	"deny_reasons": deny_reasons,
}
