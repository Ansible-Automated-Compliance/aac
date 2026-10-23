> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx9, HOST:8181x7, AAP-2.5/2.6x3.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Accessing OPA Through AAP 2.6 API
## Complete API Integration Guide for AAP_HOST

This guide shows how to trigger OPA compliance validation through the AAP 2.6 REST API.

---

## 📋 Table of Contents

1. [Authentication](#authentication)
2. [API Workflow Overview](#api-workflow-overview)
3. [Method 1: Launch Job with Callback Plugin](#method-1-launch-job-with-callback-plugin)
4. [Method 2: Custom Workflow Job](#method-2-custom-workflow-job)
5. [Method 3: Ad-Hoc Commands](#method-3-ad-hoc-commands)
6. [Method 4: Workflow Templates](#method-4-workflow-templates)
7. [Retrieving OPA Results](#retrieving-opa-results)
8. [Complete Examples](#complete-examples)

---

## Authentication

### Get API Token

**Option A: Via AAP Web UI**
```
1. Login to: https://AAP_HOST
2. Click: Your username (top right)
3. Go to: Tokens
4. Click: Add
5. Application: Leave empty (personal token)
6. Scope: Write
7. Click: Save
8. Copy the token (shown only once!)
```

**Option B: Via API (username/password)**
```bash
# Get token
curl -X POST https://AAP_HOST/api/controller/v2/tokens/ \
  -H "Content-Type: application/json" \
  -u "admin:password" \
  --insecure \
  -d '{
    "description": "API Token for OPA Integration",
    "application": null,
    "scope": "write"
  }'

# Response includes:
{
  "id": 1,
  "token": "your-token-here",
  ...
}
```

### Test Authentication

```bash
# Set variables
export AAP_HOST="AAP_HOST"
export AAP_TOKEN=$AAP_TOKEN

# Test connection
curl -X GET "https://${AAP_HOST}/api/controller/v2/me/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  --insecure | jq '.'
```

---

## API Workflow Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     AAP 2.6 REST API                             │
│  https://AAP_HOST/api/controller/v2/                        │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: Launch Job Template                                    │
│  POST /api/controller/v2/job_templates/{id}/launch/             │
│  • Triggers playbook execution                                   │
│  • Returns job_id                                                │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 2: Playbook Runs (with OPA callback plugin)               │
│  • Gathers facts from target hosts                               │
│  • Callback plugin sends facts to OPA (localhost:8181)          │
│  • OPA validates against policies                                │
│  • Results appear in job stdout                                  │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 3: Retrieve Job Output                                     │
│  GET /api/controller/v2/jobs/{job_id}/stdout/                   │
│  • Contains OPA validation results                               │
│  • Shows violations and compliance status                        │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 4: Parse Results                                           │
│  • Extract OPA compliance data from stdout                       │
│  • Process violations                                            │
│  • Generate reports                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Method 1: Launch Job with Callback Plugin

This is the **recommended** method - the OPA callback plugin automatically validates during playbook execution.

### Step 1: Find Your Job Template

```bash
# List all job templates
curl -X GET "https://${AAP_HOST}/api/controller/v2/job_templates/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  --insecure | jq '.results[] | {id: .id, name: .name}'

# Search for specific template
curl -X GET "https://${AAP_HOST}/api/controller/v2/job_templates/?name__icontains=compliance" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  --insecure | jq '.results[] | {id: .id, name: .name}'
```

### Step 2: Launch the Job

```bash
# Basic launch
curl -X POST "https://${AAP_HOST}/api/controller/v2/job_templates/TEMPLATE_ID/launch/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  -H "Content-Type: application/json" \
  --insecure \
  -d '{}'

# Launch with extra variables (to override OPA settings)
curl -X POST "https://${AAP_HOST}/api/controller/v2/job_templates/TEMPLATE_ID/launch/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  -H "Content-Type: application/json" \
  --insecure \
  -d '{
    "extra_vars": {
      "OPA_SERVER_URL": "http://localhost:8181",
      "OPA_FAIL_ON_VIOLATIONS": false,
      "OPA_COMPLIANCE_FRAMEWORKS": "cis/linux/rhel9"
    }
  }'

# Launch with specific inventory and limit
curl -X POST "https://${AAP_HOST}/api/controller/v2/job_templates/TEMPLATE_ID/launch/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  -H "Content-Type: application/json" \
  --insecure \
  -d '{
    "inventory": 2,
    "limit": "webserver-01"
  }'

# Response:
{
  "job": 123,
  "ignored_fields": {},
  "id": 123,
  "type": "job",
  "url": "/api/controller/v2/jobs/123/",
  ...
}
```

### Step 3: Monitor Job Status

```bash
# Get job status
JOB_ID=123

curl -X GET "https://${AAP_HOST}/api/controller/v2/jobs/${JOB_ID}/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  --insecure | jq '{status: .status, failed: .failed}'

# Poll until complete
while true; do
  STATUS=$(curl -s -X GET "https://${AAP_HOST}/api/controller/v2/jobs/${JOB_ID}/" \
    -H "Authorization: Bearer ${AAP_TOKEN}" \
    --insecure | jq -r '.status')

  echo "Job status: $STATUS"

  if [[ "$STATUS" == "successful" ]] || [[ "$STATUS" == "failed" ]]; then
    break
  fi

  sleep 5
done
```

### Step 4: Retrieve OPA Results from Job Output

```bash
# Get full stdout (includes OPA validation output)
curl -X GET "https://${AAP_HOST}/api/controller/v2/jobs/${JOB_ID}/stdout/?format=txt" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  --insecure

# Get just OPA compliance sections
curl -X GET "https://${AAP_HOST}/api/controller/v2/jobs/${JOB_ID}/stdout/?format=txt" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  --insecure | grep -A 20 "\[OPA COMPLIANCE\]"

# Get JSON output (if available)
curl -X GET "https://${AAP_HOST}/api/controller/v2/jobs/${JOB_ID}/stdout/?format=json" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  --insecure | jq '.event_data.res.msg' 2>/dev/null || echo "JSON not available"
```

---

## Method 2: Custom Workflow Job

Create a workflow that:
1. Collects facts
2. Calls OPA via uri module
3. Stores results

### Step 1: Create Workflow Template

```bash
# Create workflow template
curl -X POST "https://${AAP_HOST}/api/controller/v2/workflow_job_templates/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  -H "Content-Type: application/json" \
  --insecure \
  -d '{
    "name": "OPA Compliance Workflow",
    "description": "Collect facts and validate with OPA",
    "organization": 1,
    "inventory": 1
  }'

# Response includes workflow ID
```

### Step 2: Add Workflow Nodes

```bash
WORKFLOW_ID=5

# Node 1: Collect facts
curl -X POST "https://${AAP_HOST}/api/controller/v2/workflow_job_templates/${WORKFLOW_ID}/workflow_nodes/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  -H "Content-Type: application/json" \
  --insecure \
  -d '{
    "unified_job_template": JOB_TEMPLATE_ID,
    "identifier": "collect_facts"
  }'

# Node 2: Validate with OPA (runs after Node 1)
curl -X POST "https://${AAP_HOST}/api/controller/v2/workflow_job_templates/${WORKFLOW_ID}/workflow_nodes/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  -H "Content-Type: application/json" \
  --insecure \
  -d '{
    "unified_job_template": VALIDATION_JOB_TEMPLATE_ID,
    "identifier": "validate_opa",
    "success_nodes": ["collect_facts"]
  }'
```

### Step 3: Launch Workflow

```bash
curl -X POST "https://${AAP_HOST}/api/controller/v2/workflow_job_templates/${WORKFLOW_ID}/launch/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  -H "Content-Type: application/json" \
  --insecure \
  -d '{}'
```

---

## Method 3: Ad-Hoc Commands

Run ad-hoc Ansible commands that query OPA directly.

### Create Ad-Hoc Command to Query OPA

```bash
# Launch ad-hoc command
curl -X POST "https://${AAP_HOST}/api/controller/v2/inventories/INVENTORY_ID/ad_hoc_commands/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  -H "Content-Type: application/json" \
  --insecure \
  -d '{
    "module_name": "uri",
    "module_args": "url=http://localhost:8181/health method=GET return_content=yes",
    "limit": "localhost",
    "credential": CREDENTIAL_ID
  }'

# Query OPA with collected facts
curl -X POST "https://${AAP_HOST}/api/controller/v2/inventories/INVENTORY_ID/ad_hoc_commands/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  -H "Content-Type: application/json" \
  --insecure \
  -d '{
    "module_name": "uri",
    "module_args": "url=http://localhost:8181/v1/data/cis_rhel9/report method=POST body_format=json body=\"{\\\"input\\\":{}}\" return_content=yes",
    "limit": "localhost",
    "credential": CREDENTIAL_ID
  }'
```

---

## Method 4: Workflow Templates

Create a comprehensive workflow that integrates OPA validation.

### Example Workflow Job Template

```bash
# Create workflow that:
# 1. Gathers facts
# 2. Validates with OPA (automatic via callback)
# 3. Generates report
# 4. Sends notification

cat > workflow_definition.json <<'EOF'
{
  "name": "Complete OPA Compliance Validation",
  "description": "Full compliance validation workflow with OPA",
  "organization": 1,
  "inventory": 1,
  "extra_vars": {
    "opa_server_url": "http://localhost:8181",
    "generate_report": true,
    "send_notifications": true
  }
}
EOF

curl -X POST "https://${AAP_HOST}/api/controller/v2/workflow_job_templates/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  -H "Content-Type: application/json" \
  --insecure \
  -d @workflow_definition.json
```

---

## Retrieving OPA Results

### Parse Job Output for OPA Data

```bash
# Function to extract OPA results from job output
extract_opa_results() {
  JOB_ID=$1

  # Get stdout
  OUTPUT=$(curl -s -X GET "https://${AAP_HOST}/api/controller/v2/jobs/${JOB_ID}/stdout/?format=txt" \
    -H "Authorization: Bearer ${AAP_TOKEN}" \
    --insecure)

  # Extract OPA compliance banner
  echo "$OUTPUT" | sed -n '/\[OPA COMPLIANCE\]/,/^$/p'

  # Extract violation count
  VIOLATIONS=$(echo "$OUTPUT" | grep "Total Violations:" | awk '{print $NF}')
  echo "Total Violations: $VIOLATIONS"

  # Extract status
  if echo "$OUTPUT" | grep -q "✓ COMPLIANT"; then
    echo "Status: COMPLIANT"
  else
    echo "Status: NON-COMPLIANT"
  fi
}

# Use it
extract_opa_results 123
```

### Extract Results to JSON

```bash
# Extract OPA results and format as JSON
get_opa_results_json() {
  JOB_ID=$1

  OUTPUT=$(curl -s -X GET "https://${AAP_HOST}/api/controller/v2/jobs/${JOB_ID}/stdout/?format=txt" \
    -H "Authorization: Bearer ${AAP_TOKEN}" \
    --insecure)

  # Parse and create JSON
  COMPLIANT=$(echo "$OUTPUT" | grep -q "✓ COMPLIANT" && echo "true" || echo "false")
  VIOLATIONS=$(echo "$OUTPUT" | grep "Total Violations:" | awk '{print $NF}')

  cat <<EOF
{
  "job_id": ${JOB_ID},
  "compliant": ${COMPLIANT},
  "total_violations": ${VIOLATIONS},
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
}

# Use it
get_opa_results_json 123 | jq '.'
```

---

## Complete Examples

### Example 1: Simple Compliance Check

```bash
#!/bin/bash
# Simple compliance check via AAP API

set -e

AAP_HOST="AAP_HOST"
AAP_TOKEN=$AAP_TOKEN
TEMPLATE_ID=5

echo "=== Launching Compliance Check ==="

# Launch job
RESPONSE=$(curl -s -X POST "https://${AAP_HOST}/api/controller/v2/job_templates/${TEMPLATE_ID}/launch/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  -H "Content-Type: application/json" \
  --insecure \
  -d '{}')

JOB_ID=$(echo "$RESPONSE" | jq -r '.job')
echo "Job ID: $JOB_ID"

echo "=== Waiting for job to complete ==="

# Wait for completion
while true; do
  STATUS=$(curl -s -X GET "https://${AAP_HOST}/api/controller/v2/jobs/${JOB_ID}/" \
    -H "Authorization: Bearer ${AAP_TOKEN}" \
    --insecure | jq -r '.status')

  echo "Status: $STATUS"

  if [[ "$STATUS" == "successful" ]] || [[ "$STATUS" == "failed" ]]; then
    break
  fi

  sleep 5
done

echo "=== Retrieving OPA Results ==="

# Get OPA output
curl -s -X GET "https://${AAP_HOST}/api/controller/v2/jobs/${JOB_ID}/stdout/?format=txt" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  --insecure | grep -A 20 "\[OPA COMPLIANCE\]"

echo "=== Complete ==="
```

### Example 2: Compliance Check with Result Processing

```bash
#!/bin/bash
# Advanced compliance check with result processing

AAP_HOST="AAP_HOST"
AAP_TOKEN=$AAP_TOKEN
TEMPLATE_ID=5

# Launch job
launch_compliance_check() {
  curl -s -X POST "https://${AAP_HOST}/api/controller/v2/job_templates/${TEMPLATE_ID}/launch/" \
    -H "Authorization: Bearer ${AAP_TOKEN}" \
    -H "Content-Type: application/json" \
    --insecure \
    -d '{
      "extra_vars": {
        "OPA_SERVER_URL": "http://localhost:8181",
        "OPA_FAIL_ON_VIOLATIONS": false
      }
    }' | jq -r '.job'
}

# Wait for job
wait_for_job() {
  JOB_ID=$1

  while true; do
    STATUS=$(curl -s -X GET "https://${AAP_HOST}/api/controller/v2/jobs/${JOB_ID}/" \
      -H "Authorization: Bearer ${AAP_TOKEN}" \
      --insecure | jq -r '.status')

    if [[ "$STATUS" == "successful" ]] || [[ "$STATUS" == "failed" ]]; then
      echo "$STATUS"
      return
    fi

    sleep 5
  done
}

# Extract OPA results
extract_results() {
  JOB_ID=$1

  OUTPUT=$(curl -s -X GET "https://${AAP_HOST}/api/controller/v2/jobs/${JOB_ID}/stdout/?format=txt" \
    -H "Authorization: Bearer ${AAP_TOKEN}" \
    --insecure)

  # Parse results
  if echo "$OUTPUT" | grep -q "✓ COMPLIANT"; then
    COMPLIANT="true"
  else
    COMPLIANT="false"
  fi

  VIOLATIONS=$(echo "$OUTPUT" | grep "Total Violations:" | awk '{print $NF}')

  # Create result JSON
  cat <<EOF
{
  "job_id": ${JOB_ID},
  "compliant": ${COMPLIANT},
  "total_violations": ${VIOLATIONS},
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "details": {
    "filesystem": $(echo "$OUTPUT" | grep "filesystem:" | awk '{print $NF}' | sed 's/violations//'),
    "logging": $(echo "$OUTPUT" | grep "logging:" | awk '{print $NF}' | sed 's/violations//'),
    "file_permissions": $(echo "$OUTPUT" | grep "file_permissions:" | awk '{print $NF}' | sed 's/violations//'),
    "services": $(echo "$OUTPUT" | grep "services:" | awk '{print $NF}' | sed 's/violations//'),
    "network": $(echo "$OUTPUT" | grep "network:" | awk '{print $NF}' | sed 's/violations//')
  }
}
EOF
}

# Main execution
echo "Launching compliance check..."
JOB_ID=$(launch_compliance_check)
echo "Job ID: $JOB_ID"

echo "Waiting for completion..."
STATUS=$(wait_for_job $JOB_ID)
echo "Job completed with status: $STATUS"

echo "Extracting results..."
RESULTS=$(extract_results $JOB_ID)

echo "Results:"
echo "$RESULTS" | jq '.'

# Save results
echo "$RESULTS" > "compliance_results_${JOB_ID}.json"
echo "Results saved to: compliance_results_${JOB_ID}.json"

# Check compliance
if echo "$RESULTS" | jq -e '.compliant == true' > /dev/null; then
  echo "✓ SYSTEM IS COMPLIANT"
  exit 0
else
  echo "✗ SYSTEM IS NON-COMPLIANT"
  echo "Violations:"
  echo "$RESULTS" | jq '.details'
  exit 1
fi
```

### Example 3: Python Script

```python
#!/usr/bin/env python3
"""
OPA Compliance Check via AAP API
"""

import requests
import time
import json
import sys
from urllib3.exceptions import InsecureRequestWarning

# Disable SSL warnings for self-signed certs
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class AAPOPAClient:
    def __init__(self, host, token):
        self.host = host
        self.token = token
        self.base_url = f"https://{host}/api/controller/v2"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def launch_job(self, template_id, extra_vars=None):
        """Launch a job template"""
        url = f"{self.base_url}/job_templates/{template_id}/launch/"
        data = {}

        if extra_vars:
            data['extra_vars'] = extra_vars

        response = requests.post(
            url,
            headers=self.headers,
            json=data,
            verify=False
        )
        response.raise_for_status()

        return response.json()['job']

    def wait_for_job(self, job_id, poll_interval=5):
        """Wait for job to complete"""
        url = f"{self.base_url}/jobs/{job_id}/"

        while True:
            response = requests.get(url, headers=self.headers, verify=False)
            response.raise_for_status()

            status = response.json()['status']
            print(f"Job {job_id} status: {status}")

            if status in ['successful', 'failed']:
                return status

            time.sleep(poll_interval)

    def get_job_output(self, job_id):
        """Get job output"""
        url = f"{self.base_url}/jobs/{job_id}/stdout/?format=txt"
        response = requests.get(url, headers=self.headers, verify=False)
        response.raise_for_status()

        return response.text

    def parse_opa_results(self, output):
        """Parse OPA results from job output"""
        results = {
            'compliant': False,
            'total_violations': 0,
            'sections': {}
        }

        # Check compliance
        if '✓ COMPLIANT' in output:
            results['compliant'] = True

        # Extract violation count
        for line in output.split('\n'):
            if 'Total Violations:' in line:
                results['total_violations'] = int(line.split()[-1])

            # Extract section results
            for section in ['filesystem', 'logging', 'file_permissions', 'services', 'network']:
                if f'{section}:' in line:
                    violations = line.split()[-2]
                    results['sections'][section] = int(violations)

        return results

def main():
    # Configuration
    AAP_HOST = "AAP_HOST"
    AAP_TOKEN = os.environ["AAP_TOKEN"]
    TEMPLATE_ID = 5

    # Create client
    client = AAPOPAClient(AAP_HOST, AAP_TOKEN)

    print("=== Launching Compliance Check ===")

    # Launch job
    job_id = client.launch_job(
        TEMPLATE_ID,
        extra_vars={
            'OPA_SERVER_URL': 'http://localhost:8181',
            'OPA_FAIL_ON_VIOLATIONS': False
        }
    )
    print(f"Job ID: {job_id}")

    # Wait for completion
    print("\n=== Waiting for Job Completion ===")
    status = client.wait_for_job(job_id)
    print(f"Job completed with status: {status}")

    # Get output
    print("\n=== Retrieving OPA Results ===")
    output = client.get_job_output(job_id)

    # Parse results
    results = client.parse_opa_results(output)

    print("\n=== Results ===")
    print(json.dumps(results, indent=2))

    # Save results
    filename = f"compliance_results_{job_id}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {filename}")

    # Exit code based on compliance
    if results['compliant']:
        print("\n✓ SYSTEM IS COMPLIANT")
        sys.exit(0)
    else:
        print("\n✗ SYSTEM IS NON-COMPLIANT")
        print(f"Total Violations: {results['total_violations']}")
        sys.exit(1)

if __name__ == '__main__':
    main()
```

---

## API Reference Summary

### Key AAP API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/controller/v2/job_templates/` | GET | List job templates |
| `/api/controller/v2/job_templates/{id}/` | GET | Get template details |
| `/api/controller/v2/job_templates/{id}/launch/` | POST | Launch job |
| `/api/controller/v2/jobs/{id}/` | GET | Get job status |
| `/api/controller/v2/jobs/{id}/stdout/` | GET | Get job output |
| `/api/controller/v2/jobs/{id}/cancel/` | POST | Cancel running job |
| `/api/controller/v2/workflow_job_templates/` | GET/POST | Workflow templates |
| `/api/controller/v2/inventories/{id}/ad_hoc_commands/` | POST | Ad-hoc commands |

### Common Query Parameters

```bash
# Pagination
?page=1&page_size=20

# Filtering
?name__icontains=compliance
?status=successful

# Ordering
?order_by=-created

# Format
?format=json
?format=txt
```

---

## Troubleshooting

### Issue: Token Authentication Failed

```bash
# Verify token is valid
curl -X GET "https://${AAP_HOST}/api/controller/v2/me/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  --insecure

# If failed, create new token
curl -X POST "https://${AAP_HOST}/api/controller/v2/tokens/" \
  -u "admin:password" \
  --insecure \
  -d '{"description": "New token", "scope": "write"}'
```

### Issue: Job Template Not Found

```bash
# List all templates to find correct ID
curl -X GET "https://${AAP_HOST}/api/controller/v2/job_templates/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  --insecure | jq '.results[] | {id: .id, name: .name}'
```

### Issue: OPA Results Not in Output

```bash
# Check if callback plugin is enabled
curl -X GET "https://${AAP_HOST}/api/controller/v2/settings/jobs/" \
  -H "Authorization: Bearer ${AAP_TOKEN}" \
  --insecure | jq '.DEFAULT_CALLBACK_WHITELIST'

# Should include: "opa_compliance"
```

---

## Best Practices

1. **Use OAuth2 Tokens** instead of username/password
2. **Set reasonable timeouts** when polling job status
3. **Implement retry logic** for API calls
4. **Parse job output** for OPA-specific markers
5. **Store results** in database for historical tracking
6. **Use workflow templates** for complex validation scenarios
7. **Monitor API rate limits** and implement backoff

---

## Next Steps

1. ✅ Set up AAP API authentication
2. ✅ Create compliance check job template
3. ✅ Test launching jobs via API
4. ✅ Parse OPA results from job output
5. ⬜ Build automated compliance monitoring
6. ⬜ Integrate with CI/CD pipelines
7. ⬜ Create compliance dashboard

---

**Your AAP API Endpoint**: `https://AAP_HOST/api/controller/v2/`

**OPA runs automatically** via callback plugin when jobs execute!
