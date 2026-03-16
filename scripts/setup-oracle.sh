#!/bin/bash
# =============================================================================
# Initial Oracle Free Tier Instance Setup
# =============================================================================
# Run this once on a fresh Oracle ARM instance to set up Heimdal.
# Called by: make oci-setup (runs over SSH automatically)
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
    echo "Docker installed."
fi

# 2. Install Docker Compose plugin
if ! docker compose version &> /dev/null; then
    echo "Installing Docker Compose plugin..."
    sudo apt-get update && sudo apt-get install -y docker-compose-plugin 2>/dev/null || {
        # Oracle Linux / RHEL fallback
        sudo yum install -y docker-compose-plugin 2>/dev/null || true
    }
fi

# 3. Install git if missing
if ! command -v git &> /dev/null; then
    echo "Installing git..."
    sudo apt-get update && sudo apt-get install -y git 2>/dev/null || {
        sudo yum install -y git 2>/dev/null || true
    }
fi

# 4. Create data directories
echo "Creating data directories..."
sudo mkdir -p /data/raw/ais /data/raw/cold /data/raw/meta
sudo chown -R "$USER:$USER" /data

# 5. Clone the repo (if not already present)
if [ ! -d ~/Heimdal ]; then
    echo "Cloning Heimdal..."
    git clone https://github.com/Ollenaeaes/Heimdal.git ~/Heimdal
fi

# 6. Set up cron jobs for batch-pipeline and cold-archiver
echo "Setting up cron jobs..."
CRON_BATCH="0 */2 * * * cd \$HOME/Heimdal && docker compose --profile batch run --rm batch-pipeline >> /var/log/heimdal-batch.log 2>&1"
CRON_COLD="0 3 * * * cd \$HOME/Heimdal && docker compose --profile batch run --rm cold-archiver >> /var/log/heimdal-cold.log 2>&1"

(crontab -l 2>/dev/null || true) | grep -v "batch-pipeline" | grep -v "cold-archiver" > /tmp/crontab.tmp
echo "$CRON_BATCH" >> /tmp/crontab.tmp
echo "$CRON_COLD" >> /tmp/crontab.tmp
crontab /tmp/crontab.tmp
rm /tmp/crontab.tmp

echo "Cron jobs installed:"
echo "  - batch-pipeline: every 2 hours"
echo "  - cold-archiver: daily at 3am"

# 7. Create log rotation
sudo tee /etc/logrotate.d/heimdal > /dev/null <<'LOGROTATE'
/var/log/heimdal-*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
LOGROTATE

# 8. Open firewall ports (iptables — Oracle Linux uses this by default)
echo "Configuring firewall..."
for PORT in 22 80 443 8000; do
    sudo iptables -I INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || true
done
# Persist iptables rules
sudo sh -c 'iptables-save > /etc/iptables/rules.v4' 2>/dev/null || {
    sudo sh -c 'iptables-save > /etc/sysconfig/iptables' 2>/dev/null || true
}

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next: make oci-deploy"
echo ""
