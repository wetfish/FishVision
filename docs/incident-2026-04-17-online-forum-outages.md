# Incident Report: wetfishonline.com Forum Outages & Alert Noise

**Date:** 2026-04-17
**Affected service:** wetfishonline.com (`online` stack on vultr-prod `149.28.239.165`)
**Severity:** Critical (repeated ~hourly outages, 90-97% 5xx error rate during events)

---

## Summary

Recurring hourly outages on the wetfishonline.com forum caused by bot traffic saturating an undersized PHP-FPM worker pool. High CPU and latency alerts were firing repeatedly as a side effect. Three fixes were applied: increased PHP-FPM worker count, added Traefik rate limiting, and retuned alert thresholds.

---

## Timeline (from alert log)

| Time (UTC) | Event |
|---|---|
| 05:11 | `HighCPUUsage` resolves (first visible) |
| 06:06 | `WebServicesHighLatency` fires on `online@file` |
| 06:08 | `HighCPUUsage` fires again (84%) |
| 08:32 | `WebServicesHighErrorRate` fires — **97.57% 5xx** |
| 09:14 | `WebServicesHighErrorRate` fires — **94.17% 5xx** |
| 10:10 | CPU hits 100%, 96.36% 5xx |
| 11:10 | CPU hits 100%, 93.82% 5xx |

Pattern: CPU spike → latency spike → total 5xx outage, repeating roughly every hour.

---

## Root Causes

### 1. Bot flood (primary cause)

Multiple bot networks were continuously scraping the SMF forum at high request rates, all proxied through Cloudflare:

| IP Range | Origin | Req count (in log) |
|---|---|---|
| `43.173.x.x` (×5 IPs) | ByteDance/scraper | ~1,240 combined |
| `144.76.32.241` | Hetzner (bot) | 392 |
| `74.248.99.34` | Unknown | 336 |
| `17.x.x.x` | Applebot | multiple |

All requests targeted `/forum/index.php` with rotating PHPSESSID values and spoofed Chrome user-agents, scraping through topic and message IDs systematically. No rate limiting was in place.

### 2. PHP-FPM worker pool too small

`pm.max_children = 5` — only 5 concurrent PHP workers for a forum under bot load. When bots saturated all 5 workers, legitimate requests queued, Traefik timed out, and returned 504s. **134,858 5xx errors** recorded in the Traefik access log.

### 3. SMF reverse DNS lookups on every request

SMF is configured to perform reverse DNS lookups on each connecting IP by shelling out to the `host` command. The `host` binary is not installed in the `online-php` container, causing every request to:
- Spawn a shell process
- Fail immediately with `sh: 1: host: not found`
- Add unnecessary latency and CPU overhead per request

---

## Fixes Applied

### Immediate (2026-04-17)

**PHP-FPM worker pool** (`/opt/web-services/prod/services/online/config/php-fpm-pool.conf`):
```
# Before
pm.max_children = 5
pm.max_spare_servers = 3

# After
pm.max_children = 15
pm.max_spare_servers = 5
```
Container restarted to apply.

**Traefik rate limiting** (`/opt/web-services/prod/traefik/conf/dynamic.yml`):

Added `online-ratelimit` middleware to the `online` router:
```yaml
middlewares:
  online-ratelimit:
    rateLimit:
      average: 20
      burst: 50
      period: 1s
```
Traefik reloaded automatically (file watch).

**Alert rule retuning** (`prometheus/alert.rules.yml`):

| Alert | Change |
|---|---|
| `HighCPUUsage` | Threshold 80% → 90%, `for` 5m → 15m |
| `WebServicesHighLatency` | Exclude `acme-http@internal` router, `for` 5m → 10m |
| `AndonAlertHighErrorRate` | Fixed description: `printf "%.1f"` → `humanizePercentage` (was showing 10% as "0.1%") |

Also re-enabled `WebServicesTraefikDown` alert (was disabled pending Vultr firewall fix — resolved by killing orphaned k3s on staging node).

### Pending (manual action required)

**SMF reverse DNS lookups** — disable in SMF admin panel:

> Admin → Server Settings → Security and Moderation → Enable hostname lookup → **Disabled**

This will eliminate the `sh: 1: host: not found` errors and reduce per-request CPU overhead. Alternatively, install `bind9-host` in the PHP container image if hostname lookup is needed.

---

## Side Investigation: Staging Node (107.191.43.166)

During investigation, discovered that the `web-services-traefik` Prometheus target on `107.191.43.166` (vultr-stage) had never successfully scraped since monitoring was added on 2026-04-15. Root cause: orphaned k3s (not RKE2 as initially suspected) with stale nftables rules intercepting port 8082 and DNATting it to dead k8s pod IPs. k3s systemd services were inactive but containerd shims had been running since Feb 19. Fixed by running `k3s-killall.sh` on the staging node, which cleared the NAT rules. Port 8082 is now reachable from dedi-prod.

---

## Recommendations

1. **Cloudflare rate limiting rules** — add a Cloudflare WAF rate limit rule for `/forum/index.php` (e.g. 60 req/min per IP) to block bots before they hit the origin. This is more effective than Traefik-level limiting since it stops traffic at the edge.
2. **Cloudflare Bot Fight Mode** — enable in the Cloudflare dashboard for wetfishonline.com to automatically challenge known bot IPs.
3. **PHP-FPM tuning** — monitor worker saturation with `online-php` container metrics; `pm.max_children = 15` may need further tuning depending on memory usage per worker.
4. **SMF caching** — enable SMF's built-in caching (file-based or memcached) to reduce PHP/DB load per page hit.
5. **Add `bind9-host` to container image** or disable SMF hostname lookups (see above).
