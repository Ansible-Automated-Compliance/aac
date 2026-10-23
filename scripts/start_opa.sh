#!/bin/bash

# Start OPA server with the CIS policy
echo "Starting OPA server with CIS compliance policy..."

# Load the policy into OPA
opa run --server --addr localhost:8181 cis_policy.rego &

OPA_PID=$!
echo "OPA server started with PID: $OPA_PID"

# Wait a moment for OPA to start
sleep 3

# Test the policy with sample data
echo "Testing OPA policy..."
curl -X POST http://localhost:8181/v1/data/cis/allow \
  -H 'Content-Type: application/json' \
  -d '{
    "input": {
      "os_family": "RedHat",
      "distribution": "CentOS",
      "distribution_version": "9.0",
      "selinux_status": "enforcing",
      "firewall_enabled": true,
      "ssh_port": 22
    }
  }' | jq

echo ""
echo "OPA server is running on http://localhost:8181"
echo "Policy endpoint: http://localhost:8181/v1/data/cis/allow"
echo "To stop OPA: kill $OPA_PID"