#!/bin/bash
# Deploy Python-based AAP MCP Server to OpenShift
# Usage: ./deploy.sh <AAP_TOKEN>

set -e

AAP_TOKEN="${1:-}"
NAMESPACE="aap-mcp"
AAP_URL="https://aap-aap.apps.cluster-9d56n-2.dynamic.redhatworkshops.io"
IMAGE_NAME="aap-mcp-server-python"

echo "=============================================="
echo "AAP MCP Server (Python) - OpenShift Deployment"
echo "=============================================="

# Check if logged in to OpenShift
if ! oc whoami &>/dev/null; then
    echo "Error: Not logged in to OpenShift"
    echo ""
    echo "To login, run:"
    echo "  oc login https://api.cluster-9d56n-2.dynamic.redhatworkshops.io:6443"
    echo ""
    exit 1
fi

CLUSTER=$(oc whoami --show-server)
echo "Cluster: $CLUSTER"
echo "User: $(oc whoami)"

# Get token if not provided
if [ -z "$AAP_TOKEN" ]; then
    echo ""
    echo "AAP Token required for authentication."
    echo "To get a token: Log into AAP > Users > Tokens > Add"
    echo ""
    read -sp "Enter your AAP API token: " AAP_TOKEN
    echo ""
fi

if [ -z "$AAP_TOKEN" ]; then
    echo "Error: AAP token is required"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "Step 1: Creating namespace..."
oc create namespace $NAMESPACE --dry-run=client -o yaml | oc apply -f -

echo ""
echo "Step 2: Creating secret..."
oc create secret generic aap-mcp-credentials \
    --from-literal=AAP_TOKEN="$AAP_TOKEN" \
    --namespace=$NAMESPACE \
    --dry-run=client -o yaml | oc apply -f -

echo ""
echo "Step 3: Creating ImageStream..."
oc apply -n $NAMESPACE -f - <<EOF
apiVersion: image.openshift.io/v1
kind: ImageStream
metadata:
  name: $IMAGE_NAME
spec:
  lookupPolicy:
    local: true
EOF

echo ""
echo "Step 4: Creating BuildConfig..."
oc apply -n $NAMESPACE -f - <<EOF
apiVersion: build.openshift.io/v1
kind: BuildConfig
metadata:
  name: $IMAGE_NAME
spec:
  source:
    type: Binary
  strategy:
    type: Docker
    dockerStrategy:
      dockerfilePath: Dockerfile
  output:
    to:
      kind: ImageStreamTag
      name: $IMAGE_NAME:latest
EOF

echo ""
echo "Step 5: Starting binary build..."
cd "$SCRIPT_DIR"
oc start-build $IMAGE_NAME --from-dir=. -n $NAMESPACE --follow

echo ""
echo "Step 6: Creating Deployment..."
oc apply -n $NAMESPACE -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aap-mcp-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app: aap-mcp-server
  template:
    metadata:
      labels:
        app: aap-mcp-server
    spec:
      containers:
        - name: aap-mcp-server
          image: image-registry.openshift-image-registry.svc:5000/$NAMESPACE/$IMAGE_NAME:latest
          ports:
            - containerPort: 3000
          env:
            - name: AAP_URL
              value: "$AAP_URL"
            - name: AAP_TOKEN
              valueFrom:
                secretKeyRef:
                  name: aap-mcp-credentials
                  key: AAP_TOKEN
            - name: AAP_VERIFY_SSL
              value: "false"
            - name: MCP_PORT
              value: "3000"
          resources:
            requests:
              memory: "128Mi"
              cpu: "50m"
            limits:
              memory: "256Mi"
              cpu: "200m"
          livenessProbe:
            httpGet:
              path: /health
              port: 3000
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /health
              port: 3000
            initialDelaySeconds: 5
            periodSeconds: 10
EOF

echo ""
echo "Step 7: Creating Service..."
oc apply -n $NAMESPACE -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: aap-mcp-server
spec:
  selector:
    app: aap-mcp-server
  ports:
    - port: 8004
      targetPort: 3000
      name: http
EOF

echo ""
echo "Step 8: Creating Route..."
oc apply -n $NAMESPACE -f - <<EOF
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: aap-mcp-server
spec:
  port:
    targetPort: http
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
  to:
    kind: Service
    name: aap-mcp-server
EOF

echo ""
echo "Step 9: Waiting for deployment..."
oc rollout status deployment/aap-mcp-server -n $NAMESPACE --timeout=180s

echo ""
echo "=============================================="
echo "Deployment Complete!"
echo "=============================================="
echo ""

ROUTE_URL=$(oc get route aap-mcp-server -n $NAMESPACE -o jsonpath='{.spec.host}')
echo "MCP Server URL: https://$ROUTE_URL"
echo ""
echo "Health Check:"
curl -sk "https://$ROUTE_URL/health" | python3 -m json.tool 2>/dev/null || echo "(waiting for pod to be ready)"
echo ""
echo "=============================================="
echo "Configure Claude Code"
echo "=============================================="
echo ""
echo "Add to ~/.claude.json under your project's mcpServers:"
echo ""
cat <<JSONEOF
{
  "aap": {
    "type": "sse",
    "url": "https://$ROUTE_URL/sse",
    "headers": {
      "Authorization": "Bearer $AAP_TOKEN"
    }
  }
}
JSONEOF
echo ""
