#!/bin/sh
# loki-init.sh
# Ensure all mounted volumes have correct ownership before starting Loki

LOKI_UID=10001
LOKI_GID=10001

echo "Fixing permissions for Loki volumes..."
# Recursively chown mounted paths
chown -R $LOKI_UID:$LOKI_GID /loki/index /loki/chunks /loki/cache || true

echo "Starting Loki..."
# Execute original Loki command
exec /usr/bin/loki "$@"
