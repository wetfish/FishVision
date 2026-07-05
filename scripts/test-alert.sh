#!/bin/bash
# Fire a test alert with 🟡 yellow dot in IRC — auto-resolves after 2 minutes.
# Usage: ./test-alert.sh "Alert Name" "Summary of test"
# Without args, uses defaults: TestAlert / Manual test alert

NAME="${1:-TestAlert}"
SUMMARY="${2:-Manual test alert}"
STARTS_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ENDS_AT=$(date -u -d "+2 minutes" +"%Y-%m-%dT%H:%M:%SZ")

RESPONSE=$(curl -s -X POST http://localhost:9093/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d @- <<JSONEOF
[{
  "labels": {
    "alertname": "${NAME}",
    "severity": "test",
    "test": "true"
  },
  "annotations": {
    "summary": "${SUMMARY}",
    "description": "Test alert — auto-resolves in 2 minutes"
  },
  "startsAt": "${STARTS_AT}",
  "endsAt": "${ENDS_AT}",
  "generatorURL": "http://localhost:9090/graph"
}]
JSONEOF
)

echo "🟡 Test alert \"${NAME}\" fired — resolves at ${ENDS_AT}"
echo "   ${RESPONSE}"
