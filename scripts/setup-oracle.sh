#!/bin/bash
# =============================================================================
# Initial Oracle Free Tier Instance Setup
# =============================================================================
# Run this once on a fresh Oracle ARM instance to set up Heimdal.
#
# Prerequisites:
#   - Oracle free tier ARM instance (4 OCPUs, 24GB RAM)
#   - Ubuntu or Oracle Linux
#   - SSH access configured
#
# Usage:
#   ssh opc@<oracle-ip> 'bash -s' < scripts/setup-oracle.sh
# =============================================================================

set -euo pipefail

echo "=== Heimdal Oracle Free Tier Setup ==="

# 1. Install Docker
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    sudo systemctl enable docker
    sudo systemctl start docker
    echo "Docker installed. You may need to log out and back in for group changes."
fi

# 2. Install Docker Compose plugin
if ! docker compose version &> /dev/null; then
    echo "Installing Docker Compose plugin..."
    sudo apt-get update && sudo apt-get install -y docker-compose-plugin
fi

# 3. Create data directories
echo "Creating data directories..."
sudo mkdir -p /data/raw/ais /data/raw/cold /data/raw/meta
sudo chown -R "$USER:$USER" /data/raw

# 4. Clone the repo (if not already present)
if [ ! -d ~/Heimdal ]; then
    echo "Clone the Heimdal repository to ~/Heimdal"
    echo "  git clone <your-repo-url> ~/Heimdal"
    echo "  cd ~/Heimdal && cp .env.example .env"
    echo "  # Edit .env with your API keys"
fi

# 5. Set up cron jobs for batch-pipeline and cold-archiver
echo "Setting up cron jobs..."
CRON_BATCH="0 */2 * * * cd $HOME/Heimdal && docker compose --profile batch run --rm batch-pipeline >> /var/log/heimdal-batch.log 2>&1"
CRON_COLD="0 3 * * * cd $HOME/Heimdal && docker compose --profile batch run --rm cold-archiver >> /var/log/heimdal-cold.log 2>&1"

# Add cron jobs if not already present
(crontab -l 2>/dev/null || true) | grep -v "batch-pipeline" | grep -v "cold-archiver" > /tmp/crontab.tmp
echo "$CRON_BATCH" >> /tmp/crontab.tmp
echo "$CRON_COLD" >> /tmp/crontab.tmp
crontab /tmp/crontab.tmp
rm /tmp/crontab.tmp

echo "Cron jobs installed:"
echo "  - batch-pipeline: every 2 hours"
echo "  - cold-archiver: daily at 3am"

# 6. Create log rotation
sudo tee /etc/logrotate.d/heimdal > /dev/null <<'LOGROTATE'
/var/log/heimdal-*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
LOGROTATE

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. cd ~/Heimdal"
echo "  2. cp .env.example .env  # add your API keys"
echo "  3. docker compose up -d  # start always-on services"
echo "  4. docker compose --profile batch run --rm batch-pipeline  # initial data load"
echo ""
