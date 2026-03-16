#!/bin/bash
# =============================================================================
# Sync raw AIS data from production (Oracle) to local development
# =============================================================================
# Usage:
#   ./scripts/sync-data.sh [days]
#
# Arguments:
#   days   Number of days of recent data to sync (default: 3)
#
# Environment:
#   ORACLE_HOST   Production server hostname/IP
#   ORACLE_USER   SSH user (default: opc)
#   REMOTE_PATH   Remote raw data path (default: /data/raw/ais)
#   LOCAL_PATH    Local raw data path (default: ./data/raw/ais)
# =============================================================================

set -euo pipefail

DAYS=${1:-3}
ORACLE_HOST="${ORACLE_HOST:-76.13.248.226}"
ORACLE_USER="${ORACLE_USER:-root}"
REMOTE_PATH="${REMOTE_PATH:-/data/raw/ais}"
LOCAL_PATH="${LOCAL_PATH:-./data/raw/ais}"

echo "Syncing last ${DAYS} days of AIS data from ${ORACLE_USER}@${ORACLE_HOST}:${REMOTE_PATH}"

# Create local directory
mkdir -p "${LOCAL_PATH}"

# Build list of date directories to sync
for i in $(seq 0 $((DAYS - 1))); do
    DATE=$(date -d "-${i} days" +%Y/%m/%d 2>/dev/null || date -v-${i}d +%Y/%m/%d)
    YEAR=$(echo "$DATE" | cut -d/ -f1)
    MONTH=$(echo "$DATE" | cut -d/ -f2)
    DAY=$(echo "$DATE" | cut -d/ -f3)

    REMOTE_DIR="${REMOTE_PATH}/${YEAR}/${MONTH}/${DAY}"
    LOCAL_DIR="${LOCAL_PATH}/${YEAR}/${MONTH}/${DAY}"

    echo "Syncing ${REMOTE_DIR} -> ${LOCAL_DIR}"
    mkdir -p "${LOCAL_DIR}"

    rsync -avz --progress \
        "${ORACLE_USER}@${ORACLE_HOST}:${REMOTE_DIR}/" \
        "${LOCAL_DIR}/" \
        2>/dev/null || echo "  (no data for ${DATE})"
done

# Also sync the meta directory
echo "Syncing metadata..."
mkdir -p "$(dirname "${LOCAL_PATH}")/meta"
rsync -avz \
    "${ORACLE_USER}@${ORACLE_HOST}:$(dirname "${REMOTE_PATH}")/meta/" \
    "$(dirname "${LOCAL_PATH}")/meta/" \
    2>/dev/null || echo "  (no metadata found)"

echo "Sync complete. Run 'docker compose -f docker-compose.dev.yml --profile batch run batch-pipeline' to process."
