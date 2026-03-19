#!/bin/bash
# Load .env and run the Hostinger MCP server
set -a
source "$(dirname "$0")/../.env" 2>/dev/null
set +a
export API_TOKEN="${HOSTINGER_API_TOKEN}"
exec /opt/homebrew/bin/hostinger-api-mcp
