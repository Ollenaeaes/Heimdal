#!/bin/bash
# =============================================================================
# Deploy Heimdal to Oracle VM
# =============================================================================
# Syncs code, copies .env, builds and starts services.
# Called by: make oci-deploy
# =============================================================================

set -euo pipefail

STATE_FILE=".oci-state.json"
ENV_FILE=".env"

if [ ! -f "$STATE_FILE" ]; then
    echo "ERROR: No .oci-state.json found. Run 'make oci-provision' first."
    exit 1
fi

PUBLIC_IP=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('public_ip',''))")
if [ -z "$PUBLIC_IP" ]; then
    echo "ERROR: No public_ip in state file. Run 'make oci-provision' first."
    exit 1
fi

# Detect SSH user (Ubuntu = ubuntu, Oracle Linux = opc)
SSH_USER="${OCI_SSH_USER:-ubuntu}"
SSH_CMD="ssh -o StrictHostKeyChecking=no ${SSH_USER}@${PUBLIC_IP}"

echo "=== Deploying Heimdal to $PUBLIC_IP ==="

# 1. Sync code
echo "Pulling latest code on server..."
$SSH_CMD "cd ~/Heimdal && git pull origin main"

# 2. Copy .env if it exists locally
if [ -f "$ENV_FILE" ]; then
    echo "Syncing .env to server..."
    scp -o StrictHostKeyChecking=no "$ENV_FILE" "${SSH_USER}@${PUBLIC_IP}:~/Heimdal/.env"
else
    echo "WARNING: No local .env file. Make sure .env exists on the server."
fi

# 3. Build and start always-on services (ais-fetcher first priority)
echo "Building and starting services..."
$SSH_CMD "cd ~/Heimdal && docker compose up -d --build ais-fetcher"

echo ""
echo "=== AIS Fetcher Deployed ==="
echo ""
echo "  Check logs:  make oci-logs"
echo "  SSH in:      make oci-ssh"
echo ""
echo "To also start DB + API server:"
echo "  make oci-deploy-full"
echo ""
