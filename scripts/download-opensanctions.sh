#!/bin/bash
# Download the OpenSanctions default dataset (NDJSON format).
# Schedule this weekly via cron or run manually before first use.
#
# Usage:
#   ./scripts/download-opensanctions.sh
#
# The download path defaults to ./data/opensanctions but can be
# overridden with the OPENSANCTIONS_DATA_PATH environment variable.

set -euo pipefail

DATA_DIR="${OPENSANCTIONS_DATA_PATH:-./data/opensanctions}"

mkdir -p "$DATA_DIR"

echo "Downloading OpenSanctions default dataset to ${DATA_DIR}/default.json ..."

curl -L --fail --retry 3 \
  https://data.opensanctions.org/datasets/latest/default/entities.ftm.json \
  -o "${DATA_DIR}/default.json"

echo "Download complete. $(wc -l < "${DATA_DIR}/default.json") entities."
