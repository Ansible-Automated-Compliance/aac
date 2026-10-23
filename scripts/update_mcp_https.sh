#!/bin/bash
# Update Claude Code MCP configuration to use HTTPS
#
# Usage:
#   ./scripts/update_mcp_https.sh [AAP_HOST] [HTTPS_PORT]
#
# Example:
#   ./scripts/update_mcp_https.sh ${AAC_HOST:?set AAC_HOST} 8443

set -e

AAP_HOST="${1:-${AAC_HOST:?set AAC_HOST}}"
HTTPS_PORT="${2:-8443}"
CLAUDE_CONFIG="$HOME/.claude.json"

echo "========================================"
echo "Update MCP Configuration for HTTPS"
echo "========================================"
echo "AAP Host: $AAP_HOST"
echo "HTTPS Port: $HTTPS_PORT"
echo "Config File: $CLAUDE_CONFIG"
echo ""

# Check if jq is available
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed."
    echo "Install with: brew install jq"
    exit 1
fi

# Backup current config
if [ -f "$CLAUDE_CONFIG" ]; then
    cp "$CLAUDE_CONFIG" "$CLAUDE_CONFIG.backup.$(date +%Y%m%d_%H%M%S)"
    echo "Backed up current config"
fi

# New HTTPS URL
NEW_URL="https://${AAP_HOST}:${HTTPS_PORT}/sse"

echo ""
echo "New MCP URL: $NEW_URL"
echo ""

# Update the configuration using jq
# This updates the aap MCP server URL for the specific project
PROJECT_PATH="${AAC_PROJECT_PATH:-$(cd "$(dirname "$0")/.." && pwd)}"

if [ -f "$CLAUDE_CONFIG" ]; then
    # Check current URL
    CURRENT_URL=$(jq -r ".projects[\"$PROJECT_PATH\"].mcpServers.aap.url // \"not set\"" "$CLAUDE_CONFIG")
    echo "Current URL: $CURRENT_URL"

    # Update URL
    jq ".projects[\"$PROJECT_PATH\"].mcpServers.aap.url = \"$NEW_URL\"" "$CLAUDE_CONFIG" > "$CLAUDE_CONFIG.tmp"
    mv "$CLAUDE_CONFIG.tmp" "$CLAUDE_CONFIG"

    echo "Updated URL to: $NEW_URL"
else
    echo "Error: Claude config file not found at $CLAUDE_CONFIG"
    exit 1
fi

echo ""
echo "========================================"
echo "Configuration Updated"
echo "========================================"
echo ""
echo "IMPORTANT: If using a self-signed certificate, you may need to:"
echo ""
echo "1. Trust the certificate on macOS:"
echo "   scp aapuser1@${AAP_HOST}:/opt/mcp/certs/mcp-server.crt /tmp/"
echo "   sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain /tmp/mcp-server.crt"
echo ""
echo "2. Restart Claude Code to apply changes"
echo ""
echo "3. Test the connection:"
echo "   curl -sk https://${AAP_HOST}:${HTTPS_PORT}/health"
echo ""
