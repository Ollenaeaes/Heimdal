#!/bin/bash
set -e

MIGRATIONS_DIR="/docker-entrypoint-initdb.d/migrations"

echo "=== Heimdal Database Initialization ==="
echo "Running migrations from ${MIGRATIONS_DIR}..."

for migration in $(ls "${MIGRATIONS_DIR}"/*.sql | sort); do
    filename=$(basename "$migration")
    echo "--- Applying migration: ${filename} ---"
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$migration"
    echo "--- Migration ${filename} applied successfully ---"
done

echo "=== All migrations applied ==="
