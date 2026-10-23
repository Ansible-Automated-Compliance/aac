package cis_nginx_1_20_compliance_test

# Compliance-side contract test for the library's CIS NGINX Benchmark v3.1.0 module (package cis_nginx_1_20,
# policies/benchmarks/cis/nginx). The package name is kept by the library; the input contract is the v3.1.0
# one documented at the top of that module (input.nginx.version, .user, .files, .directives, ...).
# The previous version of this file exercised v1.x helper rules (ssl_enabled, strong_ssl_protocols, ...) that
# the rebuild removed.
#
# Run: opa test policies/benchmarks/cis/nginx tests/cis_nginx_1_20_test.rego

import rego.v1

pkg := data.cis_nginx_1_20

# A fully compliant host as collected (every recommendation decided, judgement ones attested).
green := {"nginx": {
	"access_log_off_outside_location": false,
	"attest": {
		"connection_limits_reviewed": true,
		"dynamic_modules_reviewed": true,
		"ip_allow_deny_reviewed": true,
		"package_repositories_reviewed": true,
		"rate_limits_reviewed": true,
	},
	"certificates": [{
		"chain_trusted": true,
		"path": "/etc/nginx/ssl/site.crt",
	}],
	"default_server": {
		"present": true,
		"return_code": 444,
		"ssl_reject_handshake": true,
	},
	"directives": {
		"access_log": ["/var/log/nginx/access.json main_json"],
		"add_header": [
			"Strict-Transport-Security \"max-age=63072000; includeSubDomains\" always",
			"X-Content-Type-Options \"nosniff\" always",
			"Content-Security-Policy \"default-src 'self'; frame-ancestors 'self'\" always",
			"Referrer-Policy \"strict-origin-when-cross-origin\" always",
			"Alt-Svc 'h3=\":443\"; ma=86400'",
		],
		"client_body_timeout": ["10"],
		"client_header_timeout": ["10"],
		"client_max_body_size": ["1m"],
		"error_log": ["/var/log/nginx/error.log info"],
		"http2": ["on"],
		"keepalive_timeout": ["10"],
		"limit_except": ["GET HEAD POST"],
		"listen": [
			"80",
			"443 ssl",
			"443 quic reuseport",
		],
		"log_format": ["main_json escape=json '{\"time\":\"$time_iso8601\",\"remote_addr\":\"$remote_addr\",\"remote_user\":\"$remote_user\",\"request\":\"$request\",\"status\":\"$status\",\"user_agent\":\"$http_user_agent\"}'"],
		"proxy_hide_header": [
			"X-Powered-By",
			"Server",
		],
		"proxy_set_header": [
			"X-Forwarded-For $proxy_add_x_forwarded_for",
			"X-Real-IP $remote_addr",
		],
		"proxy_ssl_certificate": ["/etc/nginx/ssl/client.crt"],
		"proxy_ssl_certificate_key": ["/etc/nginx/ssl/client.key"],
		"proxy_ssl_name": ["backend.internal"],
		"proxy_ssl_protocols": ["TLSv1.3"],
		"proxy_ssl_trusted_certificate": ["/etc/nginx/ssl/upstream-ca.crt"],
		"proxy_ssl_verify": ["on"],
		"resolver": ["10.0.0.53"],
		"send_timeout": ["10s"],
		"server_tokens": ["off"],
		"ssl_protocols": ["TLSv1.3"],
		"ssl_stapling": ["on"],
		"ssl_stapling_verify": ["on"],
		"ssl_trusted_certificate": ["/etc/nginx/ssl/chain.pem"],
	},
	"files": {
		"dir_modes": {
			"/etc/nginx": "750",
			"/etc/nginx/conf.d": "750",
		},
		"file_modes": {
			"/etc/nginx/conf.d/app.conf": "600",
			"/etc/nginx/nginx.conf": "640",
		},
		"not_root_owned": [],
	},
	"hidden_files_denied": true,
	"listen_ports": [
		80,
		443,
	],
	"package": {"update_available": false},
	"pid_file": {
		"group": "root",
		"mode": "644",
		"owner": "root",
	},
	"private_keys": {"/etc/nginx/ssl/site.key": "400"},
	"probe": {"error_page_mentions_nginx": false},
	"profiles": [
		"webserver",
		"proxy",
		"loadbalancer",
	],
	"servers": [
		{
			"name": "app",
			"ssl": true,
		},
		{
			"name": "redirect",
			"redirects_to_https": true,
			"ssl": false,
		},
	],
	"user": {
		"groups": ["nginx"],
		"name": "nginx",
		"password_locked": true,
		"shell": "/sbin/nologin",
		"sudo_allowed": false,
		"uid": 988,
	},
	"version": "1.28.0",
}}

_id_in(vs, id) if {
	some v in vs
	startswith(v, concat("", [id, ":"]))
}

test_compliant_configuration_passes if {
	pkg.compliant with input as green
	r := pkg.compliance_report with input as green
	r.failed_controls == 0
	r.passed_controls == r.applicable_controls
	r.standard_total == 44
}

# Fail closed: no facts is never compliant, and every decided recommendation reports missing evidence.
test_empty_input_fails_closed if {
	not pkg.compliant with input as {}
	r := pkg.compliance_report with input as {"nginx": {}}
	r.failed_controls == r.applicable_controls
	v := pkg.violations with input as {"nginx": {}}
	"1.1.1: evidence missing — nginx.version not collected" in v
	"2.4.3: evidence missing — nginx.directives not collected" in v
}

# The v1.x input shape (nginx.config.*, nginx.ssl.*) is not read any more: it must not pass.
test_legacy_shape_is_not_compliant if {
	legacy := {"nginx": {"user": "nginx", "config": {"server_tokens": "off"}, "ssl": {"enabled": true, "protocols": ["TLSv1.2", "TLSv1.3"]}}}
	not pkg.compliant with input as legacy
	v := pkg.violations with input as legacy
	"2.4.3: evidence missing — nginx.directives not collected" in v
}

test_server_tokens_on_fails if {
	inp := json.patch(green, [{"op": "replace", "path": "/nginx/directives/server_tokens", "value": ["on"]}])
	not pkg.compliant with input as inp
}

test_weak_tls_protocols_fail if {
	inp := json.patch(green, [{"op": "replace", "path": "/nginx/directives/ssl_protocols", "value": ["SSLv3 TLSv1 TLSv1.2"]}])
	v := pkg.violations with input as inp
	_id_in(v, "4.1.4")
}

test_root_service_account_fails if {
	inp := json.patch(green, [{"op": "replace", "path": "/nginx/user/name", "value": "root"}, {"op": "replace", "path": "/nginx/user/uid", "value": 0}])
	v := pkg.violations with input as inp
	_id_in(v, "2.2.1")
}

test_world_writable_config_fails if {
	inp := json.patch(green, [{"op": "replace", "path": "/nginx/files/file_modes", "value": {"/etc/nginx/nginx.conf": "666"}}])
	v := pkg.violations with input as inp
	_id_in(v, "2.3.2")
}

test_unattested_judgement_fails if {
	inp := json.patch(green, [{"op": "remove", "path": "/nginx/attest/dynamic_modules_reviewed"}])
	v := pkg.violations with input as inp
	_id_in(v, "2.1.1")
}
