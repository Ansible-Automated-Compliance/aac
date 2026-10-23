#!/usr/bin/env bash
# Smoke-test the AAC Compliance-State API. Override HOST/PORT for your environment.
set -euo pipefail

BASE="http://${HOST:-AAP_HOST}:${PORT:-8090}"
HOSTKEY="${1:-web-01.lab.local}"

echo "== health (200 healthy / 503 DB unreachable) =="
curl -sS -w '\n[%{http_code}]\n' "${BASE}/health"

echo "== all assessed hosts =="
curl -sS "${BASE}/v1/compliance/hosts" | python3 -m json.tool

echo "== authorization context for ${HOSTKEY} (hostname OR ip) =="
curl -sS "${BASE}/v1/compliance/hosts/${HOSTKEY}" | python3 -m json.tool

echo "== OPA bundle -> load into a local OPA and query =="
curl -sS "${BASE}/v1/bundle.tar.gz" -o /tmp/aac_compliance_bundle.tar.gz
opa eval -b /tmp/aac_compliance_bundle.tar.gz \
  "data.aac.compliance.hosts[\"${HOSTKEY}\"]" --format pretty || true

echo "== end-to-end authorization decision (bundle mode) =="
opa eval -b /tmp/aac_compliance_bundle.tar.gz \
  -d "$(dirname "$0")/../policy/enforceauth_authz_bundle.rego" \
  --input <(echo "{\"host\":\"${HOSTKEY}\"}") \
  'data.enforceauth.aac_compliance_bundle.decision' --format pretty || true
