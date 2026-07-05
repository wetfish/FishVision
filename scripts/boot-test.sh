#!/bin/sh
# FishVision Boot Test Framework
# Runs automatically on stack startup via test-runner service.
# Verifies: API endpoints, scrape targets, alert rules, alert pipeline, log pipeline.
# Exits with number of failures. Sends result to IRC via Alertmanager.

PROM="http://prometheus:9090"
AM="http://alertmanager:9093"
LOKI="http://loki:3100"
TEMPO="http://tempo:3200"
GRAFANA="http://grafana:3000"
IRC="http://irc-relay:8010"
PUSHGW="http://pushgateway:9091"

PASS=0
FAIL=0
FAILURES=""
TMPDIR="${TMPDIR:-/tmp}"

# ── Helpers ─────────────────────────────────────

check() {
    desc="$1"; shift
    if "$@" >/dev/null 2>&1; then
        PASS=$((PASS + 1))
        echo "  ✅ $desc"
    else
        FAIL=$((FAIL + 1))
        echo "  ❌ $desc"
        if [ -n "$FAILURES" ]; then
            FAILURES="$FAILURES, $desc"
        else
            FAILURES="$desc"
        fi
    fi
}

add_fail() {
    FAIL=$((FAIL + 1))
    if [ -n "$FAILURES" ]; then FAILURES="$FAILURES, $1"; else FAILURES="$1"; fi
}

# ── Header ──────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     FishVision Boot Test Framework       ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 0. Wait for Prometheus ─────────────────────

echo "─── Waiting for Prometheus ───"
for i in $(seq 1 30); do
    if curl -sf "$PROM/-/ready" >/dev/null 2>&1; then
        echo "  ✅ Prometheus ready (${i}s)"
        PASS=$((PASS + 1))
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  ❌ Prometheus not ready after 30s"
        FAIL=$((FAIL + 1))
        add_fail "Prometheus readiness"
    fi
    sleep 1
done

# ── 1. API Endpoints ───────────────────────────

echo ""
echo "─── API Endpoints ───"
check "Alertmanager /api/v2/status"  curl -sf "$AM/api/v2/status"
check "Loki /ready"                  curl -sf "$LOKI/ready"
check "Tempo /ready"                 curl -sf "$TEMPO/ready"
check "Grafana /api/health"          curl -sf "$GRAFANA/api/health"
check "IRC relay /metrics"           curl -sf "$IRC/metrics"
check "Pushgateway /metrics"         curl -sf "$PUSHGW/metrics"

# ── 2. Scrape Targets ──────────────────────────

echo ""
echo "─── Scrape Targets ───"
TARGETS=$(curl -sf "$PROM/api/v1/targets")
echo "$TARGETS" | jq -r '
    .data.activeTargets[]
    | if .health == "up" then "PASS|\(.labels.job)|\(.scrapeUrl)"
      else "FAIL|\(.labels.job)|\(.scrapeUrl)" end
' > "$TMPDIR/targets.tmp"

while IFS='|' read -r status job url; do
    if [ "$status" = "PASS" ]; then
        echo "  ✅ $job"
        PASS=$((PASS + 1))
    else
        echo "  ❌ $job → $url"
        add_fail "target:$job"
    fi
done < "$TMPDIR/targets.tmp"
rm -f "$TMPDIR/targets.tmp"

# ── 3. Alert Rules ─────────────────────────────

echo ""
echo "─── Alert Rules ───"
RULES=$(curl -sf "$PROM/api/v1/rules?type=alert")
echo "$RULES" | jq -r '
    .data.groups[] | .name as $group | .rules[]
    | if .health == "ok" and (.lastError == null or .lastError == "")
      then "PASS|\(.name)|\($group)"
      else "FAIL|\(.name)|\(.health)|\(.lastError // "unknown error")|\($group)" end
' > "$TMPDIR/rules.tmp"

while IFS='|' read -r status name detail group; do
    if [ "$status" = "PASS" ]; then
        echo "  ✅ $name"
        PASS=$((PASS + 1))
    else
        echo "  ❌ $name [$detail] ($group)"
        add_fail "rule:$name"
    fi
done < "$TMPDIR/rules.tmp"
rm -f "$TMPDIR/rules.tmp"

# ── 4. Alert Pipeline ──────────────────────────

echo ""
echo "─── Alert Pipeline ───"

# Record Alertmanager webhook notification count before
AM_BEFORE=$(curl -sf "$PROM/api/v1/query" \
    --data-urlencode 'query=alertmanager_notifications_total{integration="webhook"}' \
    | jq -r '.data.result[0].value[1] // "0"')

# Fire test alert with 2min TTL (epoch arithmetic for Alpine/BusyBox compat)
# Unique name per run to avoid group_interval suppression
TEST_ID="PipelineTest-$(date +%s)"
STARTS_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ENDS_AT=$(date -u -d @$(( $(date -u +%s) + 120 )) +"%Y-%m-%dT%H:%M:%SZ")

curl -sf -X POST "$AM/api/v2/alerts" \
    -H 'Content-Type: application/json' \
    -d "{
        \"labels\": {
            \"alertname\": \"${TEST_ID}\",
            \"severity\": \"test\",
            \"test\": \"true\"
        },
        \"annotations\": {
            \"summary\": \"Boot test pipeline check\",
            \"description\": \"Synthetic alert to verify Alertmanager → webhook delivery\"
        },
        \"startsAt\": \"${STARTS_AT}\",
        \"endsAt\": \"${ENDS_AT}\",
        \"generatorURL\": \"http://localhost:9090/graph\"
    }" >/dev/null 2>&1

echo "  📤 Test alert posted, waiting for delivery..."

# Wait for group_wait (30s) + Prometheus scrape (15s) + buffer (5s)
sleep 50

AM_AFTER=$(curl -sf "$PROM/api/v1/query" \
    --data-urlencode 'query=alertmanager_notifications_total{integration="webhook"}' \
    | jq -r '.data.result[0].value[1] // "0"')

if [ "$AM_AFTER" -gt "$AM_BEFORE" ] 2>/dev/null; then
    echo "  ✅ Alert pipeline ($AM_BEFORE → $AM_AFTER webhooks sent)"
    PASS=$((PASS + 1))
else
    echo "  ❌ Alert pipeline ($AM_BEFORE → $AM_AFTER, no webhooks sent)"
    add_fail "Alert pipeline"
fi

# ── 5. Log Pipeline ────────────────────────────

echo ""
echo "─── Log Pipeline ───"
ENTRIES=$(curl -sf "$PROM/api/v1/query" --data-urlencode 'query=promtail_sent_entries_total' \
    | jq -r '.data.result[0].value[1] // "0"')

if [ "$ENTRIES" -gt 0 ] 2>/dev/null; then
    HUMAN=$(echo "$ENTRIES" | awk '{ sum=$1; unit=""; if(sum>=1e9){sum=sum/1e9; unit="B"} else if(sum>=1e6){sum=sum/1e6; unit="M"} else if(sum>=1e3){sum=sum/1e3; unit="K"}; printf "%.1f%s", sum, unit}')
    echo "  ✅ Log ingestion active (${HUMAN} entries)"
    PASS=$((PASS + 1))
else
    echo "  ❌ Log ingestion ($ENTRIES entries)"
    add_fail "Log pipeline"
fi

# ── Summary ────────────────────────────────────

TOTAL=$((PASS + FAIL))
echo ""
echo "═══════════════════════════════════════════"
if [ "$FAIL" -eq 0 ]; then
    echo "  🎉 ALL $TOTAL CHECKS PASSED"
    SEVERITY="info"
    SUMMARY="Boot test: ${TOTAL}/${TOTAL} passed"
    DESC="All API endpoints, scrape targets, alert rules, alert pipeline, and log pipeline verified."
else
    echo "  ⚠️  $PASS/$TOTAL passed, $FAIL FAILED"
    SEVERITY="warning"
    SUMMARY="Boot test: ${PASS}/${TOTAL} passed ($FAIL failures)"
    DESC="Failures: ${FAILURES}"
fi
echo "═══════════════════════════════════════════"
echo ""

# ── Report to IRC ──────────────────────────────

STARTS_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ENDS_AT=$(date -u -d @$(( $(date -u +%s) + 120 )) +"%Y-%m-%dT%H:%M:%SZ")

curl -sf -X POST "$AM/api/v2/alerts" \
    -H 'Content-Type: application/json' \
    -d "{
        \"labels\": {
            \"alertname\": \"BootTestComplete-$(date +%s)\",
            \"severity\": \"${SEVERITY}\",
            \"test\": \"true\"
        },
        \"annotations\": {
            \"summary\": \"${SUMMARY}\",
            \"description\": \"${DESC}\"
        },
        \"startsAt\": \"${STARTS_AT}\",
        \"endsAt\": \"${ENDS_AT}\",
        \"generatorURL\": \"http://localhost:9090/graph\"
    }" >/dev/null 2>&1

echo "📤 Boot test result sent to IRC — check #alerts"
echo ""

exit "$FAIL"
