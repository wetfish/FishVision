#!/usr/bin/env bash
# Query Alertmanager for currently firing alerts.
# Prints firing alerts with labels, state, and start time.
#
# Usage: bash active-alerts.sh [alertmanager_url]
#
# Default alertmanager URL: http://localhost:9093
# Run on dedi-prod or via SSH tunnel.

AM="${1:-http://localhost:9093}"

echo "=== ACTIVE ALERTS ==="
echo "Source: $AM"
echo ""

curl -sf "${AM}/api/v2/alerts" | python3 -c "
import sys, json

alerts = json.load(sys.stdin)
firing = [a for a in alerts if a['status']['state'] == 'active']
silenced = [a for a in alerts if a['status']['state'] == 'suppressed']

if not alerts:
    print('No active alerts.')
    sys.exit(0)

print(f'Firing:   {len(firing)}')
print(f'Silenced: {len(silenced)}')
print()

for a in sorted(firing, key=lambda x: x.get('startsAt','')):
    labels = a['labels']
    ann = a.get('annotations', {})
    name = labels.get('alertname', '?')
    sev = labels.get('severity', '?').upper()
    proj = labels.get('project', 'global')
    starts = a.get('startsAt','')[:19]
    summary = ann.get('summary', '')
    print(f'  [{sev}] {name} ({proj})')
    print(f'    Since:   {starts}')
    if summary:
        print(f'    Summary: {summary}')
    print()
"
