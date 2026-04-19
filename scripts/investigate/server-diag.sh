#!/usr/bin/env bash
# Server quick-diagnostics — run on any prod/stage node via SSH.
# Prints: docker services, prometheus targets, disk, memory, load.
#
# Usage (local):  bash server-diag.sh
# Usage (remote): ssh <host> 'bash -s' < server-diag.sh

set -euo pipefail

echo "=== DOCKER SERVICES ==="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || echo "docker not available"

echo ""
echo "=== DISK ==="
df -h /

echo ""
echo "=== MEMORY ==="
free -h

echo ""
echo "=== LOAD ==="
uptime

echo ""
echo "=== TOP PROCESSES BY CPU ==="
ps aux --sort=-%cpu | head -10

echo ""
echo "=== OPEN PORTS ==="
ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null || echo "ss/netstat not available"
