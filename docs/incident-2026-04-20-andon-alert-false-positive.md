# Incident Report: AndonAlertHighErrorRate False Positive

**Date:** 2026-04-20
**Duration:** ~02:40 UTC – ongoing (not yet resolved)
**Severity:** Low (false positive — no real user impact)
**Service:** andon-alert (factory.andonalert.net)
**Status:** Root cause identified, fix pending

---

## Summary

`AndonAlertHighErrorRate` [CRITICAL] fired and sustained a ~5.8% error rate on the `andon-alert` Tempo service. Investigation confirmed this is a false positive: **staging traces are being shipped to production Tempo**, mixing with production spanmetrics. The error spans originate from the staging factory-web pod's nginx-prometheus-exporter scraping `/stub_status` — a path not handled by nginx in the staging config — causing requests to fall through to PHP-FPM, which returns 404 and the OTel extension emits `STATUS_CODE_ERROR` server spans. These staging spans increment production spanmetric counters, keeping the alert firing.

No production requests were failing. factory.andonalert.net was fully operational throughout.

---

## Timeline (UTC)

| Time | Event |
|------|-------|
| 02:40 | `AndonAlertHighErrorRate` fires. Alert shows 7.1% error rate on `andon-alert` spans. |
| ~03:00 | Investigation begins. Confirmed factory-prod cluster healthy: web pod responds 200, DB connected, scheduler running fine. |
| ~03:10 | Traced error spans to `SPAN_KIND_SERVER GET` with `user_agent: NGINX-Prometheus-Exporter/v1.5.0` hitting `/stub_status`. |
| ~03:20 | Found spans originate from `host.name: factory-web-75c55b4675-2gjs8` — a pod name not matching any running prod pod. |
| ~03:30 | Confirmed `factory-web-75c55b4675-2gjs8` is the **staging** factory-web pod on `45.76.235.77`. |
| ~03:40 | Root cause confirmed: staging OTel endpoint points to production Tempo (`144.48.106.242:4319`). Staging nginx lacks `stub_status` location → exporter requests reach PHP → 404 → error span → ships to prod Tempo. |

---

## Root Cause

Two misconfigurations combined to produce the false positive:

### 1. Staging ships traces to production Tempo

The staging factory-web pod has:

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://144.48.106.242:4319
OTEL_SERVICE_NAME=andon-alert
```

`144.48.106.242` is dedi-prod — the production Tempo instance. Staging traces are labelled `service=andon-alert` and are indistinguishable from production traces. Tempo's metrics generator processes them alongside prod spans, polluting `traces_spanmetrics_calls_total`.

### 2. Staging nginx config missing `stub_status` location

The staging nginx configmap (`factory-nginx-config` in `factory-staging`) does not have a `stub_status` location block. When the nginx-prometheus-exporter scrapes `http://10.43.183.229/stub_status` every 15 seconds:

1. Nginx has no matching location — falls through to `try_files` → `/index.php`
2. PHP-FPM receives the request and returns HTTP 404 (Laravel route not found)
3. The OTel PHP extension (`opentelemetry-php-instrumentation v1.2.1`) records a `SPAN_KIND_SERVER GET` span with `STATUS_CODE_ERROR` (OTel marks 4xx as errors for server spans)
4. The span is exported to production Tempo

This generates ~4 error spans per minute from staging alone, enough to sustain >5% error rate when real traffic to production is low (as it was overnight).

**Note:** The production nginx configmap is also missing the `stub_status` location. The production factory-web pod has the block in its running nginx config, but it appears to have been added manually to the pod rather than via the configmap. The production PHP-FPM pod does **not** have the OTel extension installed, so even if the same 404 occurred on prod, no error spans would be generated.

---

## Why No Real User Impact

- Production factory-web pod (`factory-web-648b49bb9f-4rb7g`) does not have the OTel PHP extension installed — no prod spans were generated for the `/stub_status` 404s.
- factory.andonalert.net was serving real user requests normally throughout the incident window.
- The alert threshold (>5% error rate) was crossed solely by staging noise during a low-traffic period.

---

## Fixes Required

| Priority | Action | Detail |
|----------|--------|--------|
| **Critical** | Change staging `OTEL_EXPORTER_OTLP_ENDPOINT` | Set to empty/disabled or a staging-only Tempo instance. Staging must not ship traces to prod Tempo. |
| **High** | Add `stub_status` to staging nginx configmap | Add the same `location /stub_status { stub_status; allow 10.42.0.0/16; deny all; }` block that prod uses to `factory-nginx-config` in `factory-staging`. |
| **High** | Add `stub_status` to prod nginx configmap | The prod running pod has it but the configmap does not. If the pod is redeployed, the location will be missing and the nginx-exporter will fail to scrape. |
| **Medium** | Add `environment` label filtering to `AndonAlertHighErrorRate` | Alert expression should filter to `environment="production"` to prevent staging noise from triggering critical alerts. |
| **Medium** | Deploy a staging Tempo instance | Proper environment isolation — staging traces should go to a staging observability stack. |

---

## Immediate Mitigation

The alert can be silenced in Alertmanager while the OTel endpoint is corrected. The fix to `OTEL_EXPORTER_OTLP_ENDPOINT` on staging will resolve the alert within 5 minutes (next Prometheus scrape interval).

---

## Contributing Factors

- **No environment isolation in Tempo**: All services write to a single Tempo instance with no tenant separation. A single misconfigured exporter endpoint can pollute all spanmetrics.
- **Alert expression lacks environment scoping**: `AndonAlertHighErrorRate` does not filter on an `environment` label, so staging traffic can trigger critical production alerts.
- **Staging OTel config pointing to prod**: Likely set up this way intentionally during initial observability rollout (staging has no own Tempo), but never corrected after prod Tempo was established.
- **nginx configmap drift**: The running prod nginx config diverges from the deployed configmap — the `stub_status` block was added manually to the pod, not to the configmap. This would be lost on pod restart.
