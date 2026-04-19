#!/usr/bin/env bash
# Check Prometheus scrape target health.
# Queries the local Prometheus API and prints all targets with their
# health status, last error, and last scrape time.
#
# Usage: bash prometheus-target-check.sh [prometheus_url]
#
# Default prometheus URL: http://localhost:9090
# Run via SSH tunnel or on dedi-prod directly.

PROM="${1:-http://localhost:9090}"

echo "=== PROMETHEUS TARGETS ==="
echo "Source: $PROM"
echo ""

curl -sf "${PROM}/api/v1/targets" | python3 -c "
import sys, json, datetime

data = json.load(sys.stdin)
targets = data['data']['activeTargets']

down = [t for t in targets if t['health'] == 'down']
up   = [t for t in targets if t['health'] == 'up']

print(f'UP:   {len(up)}')
print(f'DOWN: {len(down)}')
print()

if down:
    print('=== DOWN TARGETS ===')
    for t in down:
        labels = t['labels']
        err = t.get('lastError', 'no error info')
        scrape = t.get('lastScrape', '')[:19]
        print(f\"  [{labels.get('job','?')}] {labels.get('instance','?')}\")
        print(f\"    Error: {err}\")
        print(f\"    Last scrape: {scrape}\")
    print()

print('=== ALL TARGETS ===')
for t in sorted(targets, key=lambda x: (x['health'], x['labels'].get('job',''))):
    labels = t['labels']
    health = t['health'].upper()
    marker = '✓' if health == 'UP' else '✗'
    print(f\"  {marker} [{health}] {labels.get('job','?'):30s} {labels.get('instance','?')}\")
"
