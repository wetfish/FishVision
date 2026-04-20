# Forensics Report: Bot Scraping Attack on wetfishonline.com

**Date of attack:** 2026-04-17 (UTC)
**Log analysed:** `/opt/web-services/prod/traefik/logs/access.log.2.gz` (2026-04-17T00:00:08Z – 2026-04-18T00:00:08Z)
**Total requests analysed:** 435,607 (online@file router only)
**Analyst:** Claude / cyba
**Status:** Mitigated

---

## Executive Summary

On 2026-04-17, wetfishonline.com sustained a large-scale coordinated scraping attack from a botnet of approximately **1,908 unique IPs** across the `43.172.x.x` and `43.173.x.x` address space (attributed to ByteDance/Lemon8 infrastructure, routed through Singapore). The attack ran continuously for the full 24-hour period and caused **four distinct outage windows** between 08:00–12:00 UTC, during which 31% of all requests (134,865) returned 5xx errors. At peak, over 90% of requests were failing.

The attack exploited two pre-existing weaknesses: an undersized PHP-FPM worker pool (`pm.max_children = 5`) and the absence of any rate limiting. Both have since been remediated.

---

## Attack Timeline

| Hour (UTC) | Total Reqs | 200 OK | 5xx Errors | Notes |
|---|---|---|---|---|
| 00:00 | 4,206 | 4,147 | 0 | Bot traffic present, workers coping |
| 01:00 | 4,387 | 4,282 | 0 | |
| 02:00 | 4,140 | 4,045 | 0 | |
| 03:00 | 4,319 | 4,252 | 0 | |
| 04:00 | 2,085 | 1,931 | 0 | Traffic dip |
| 05:00 | 20,948 | 20,852 | 0 | **Bot wave 1 begins** — traffic 5× spike |
| 06:00 | 22,175 | 22,129 | 0 | Still absorbing |
| 07:00 | 21,625 | 21,493 | 0 | |
| **08:00** | **29,983** | **17,606** | **11,055** | **Outage begins** — workers saturated |
| **09:00** | **46,155** | **6,073** | **37,804** | **Peak degradation** — 82% error rate |
| **10:00** | **48,956** | **3,045** | **42,269** | **86% error rate** |
| **11:00** | **51,105** | **2,993** | **43,730** | **86% error rate — peak request volume** |
| 12:00 | 16,527 | 16,424 | 0 | **Recovery** — bot wave subsides |
| 13:00–19:00 | ~9,000–14,000/hr | ~99% 200 | 0 | Normal operation |
| 20:00 | 18,351 | 18,249 | 7 | Minor blip |
| 21:00–23:00 | ~21,000–23,000/hr | ~99% 200 | 0 | Elevated but stable |

**Outage window:** 08:00–12:00 UTC (~4 hours)
**Peak request rate:** ~51,000 req/hr (14.2 req/s) at 11:00 UTC

---

## Attacker Infrastructure

### Primary Botnet — `43.172.x.x` / `43.173.x.x`

**Attribution:** ByteDance / Lemon8 cloud infrastructure (confirmed via Cloudflare `Cf-Ipcountry: SG`, ASN 138915 — Kaopu Cloud HK Limited, known ByteDance CDN/scraping network)

| Subnet | Requests |
|---|---|
| `43.173.181.0/24` | 31,940 |
| `43.173.179.0/24` | 30,474 |
| `43.173.180.0/24` | 29,478 |
| `43.173.182.0/24` | 28,925 |
| `43.172.197.0/24` | 28,315 |
| `43.172.194.0/24` | 26,613 |
| `43.172.196.0/24` | 24,555 |
| `43.172.198.0/24` | 23,846 |
| `43.172.195.0/24` | 23,807 |
| `43.173.176–178.0/24` | ~60,000 combined |

**Total unique IPs in this netblock:** 1,908
**Total requests from `43.172/173.x.x`:** ~375,000 (~86% of all traffic)

Each IP made approximately **280–300 requests** over the full 24-hour period — a deliberate rate (~12 req/hr per IP) designed to stay under naive per-IP rate limits while achieving high aggregate throughput across the botnet.

### Secondary Actors

| IP | Country | Requests | Behaviour |
|---|---|---|---|
| `2001:41d0:602:2e48::1` | PL (OVH) | 565 | Mixed 200/404, no PHPSESSID — crawler |
| `144.76.32.241` | DE (Hetzner) | 394 | Mixed 200/404, no PHPSESSID — crawler |
| `74.248.99.34` | PL | 336 | 100% 404 — vulnerability/path scanner |
| `43.130.91.95` | US | ~60 | Different ByteDance subnet |

---

## Attack Characteristics

### Bot Fingerprints

**Session spoofing:** Every request included a unique `PHPSESSID` in the URL query string. Each IP used a near-unique session per request (e.g. `43.172.197.229`: 298 requests, 287 unique PHPSESSIDs). This causes SMF to treat each request as a new visitor, bypassing session-based throttling and multiplying PHP/DB load.

**User-Agent rotation:** The botnet rotated across ~15+ Chrome user-agent strings, with Windows 10/Chrome and macOS/Chrome being most common. Versions ranged from Chrome/103 to Chrome/142 — some versions (e.g. 142) do not exist, indicating synthetic UA strings.

Top UAs (each ~19,000–40,000 requests):
```
Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/133.0.0.0  [39,617]
Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/131.0.0.0  [39,377]
Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/116.0.0.0  [39,074]
Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ... Chrome/140.0  [26,544]
Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/142.0.0.0  [22,276]  ← non-existent
```

**Accept-Language:** Predominantly `zh-CN,zh;q=0.9` — consistent with mainland China origin despite Singapore egress IPs.

**Scraping pattern:** Systematic enumeration of forum topics and message IDs via `?topic=N.msgM` and `?topic=N.X` parameters. No CSS, JS, or image requests — pure content extraction.

**HTTP method:** 99.9% GET. No POST/login attempts observed.

### Traffic Origin by Country (Cloudflare headers)

| Country | Requests | % |
|---|---|---|
| SG (Singapore / ByteDance egress) | 387,677 | 89.0% |
| CN (China) | 29,455 | 6.8% |
| US | 3,751 | 0.9% |
| DE | 1,875 | 0.4% |
| Others | ~13,000 | 3.0% |

---

## Impact

### Error breakdown

| Status | Count | % | Meaning |
|---|---|---|---|
| 200 OK | 287,086 | 65.9% | Served successfully |
| 499 | 10,599 | 2.4% | Client closed connection (Cloudflare timeout) |
| 502 Bad Gateway | 62,957 | 14.5% | PHP-FPM crashed/unreachable |
| 504 Gateway Timeout | 71,560 | 16.4% | Traefik timed out waiting for PHP-FPM |
| **Total 5xx** | **134,865** | **31.0%** | |

### Response time degradation

| Condition | Avg response time |
|---|---|
| Normal (200) | 1.133s |
| Error (5xx) | 31.999s |

5xx responses took **28× longer** than successful ones, indicating PHP-FPM workers were hanging at the connection limit rather than fast-failing.

### Service availability

- **08:00–12:00 UTC**: effectively down for most users (82–86% error rate)
- **Legitimate users during outage**: received 504 Gateway Timeout or Cloudflare error pages

---

## Root Cause Chain

```
1,908 bot IPs × ~12 req/hr each
        ↓
~14 concurrent requests/sec at peak
        ↓
SMF creates new PHP session per request (unique PHPSESSID in URL)
        ↓
SMF shells out to `host` for reverse DNS on each request
  → `host` not installed → process spawns and fails (extra latency)
        ↓
PHP-FPM saturates at pm.max_children = 5
        ↓
Traefik request queue fills → 504/502 for all new requests
        ↓
CPU hits 100% → HighCPUUsage alert fires
Latency spikes → WebServicesHighLatency fires
5xx rate >5% → WebServicesHighErrorRate fires (critical)
```

---

## Mitigations Applied (2026-04-17)

| Fix | Detail | Status |
|---|---|---|
| PHP-FPM workers | `pm.max_children` 5 → 15, `pm.max_spare_servers` 3 → 5 | ✅ Applied, container restarted |
| Traefik rate limit | 20 req/s avg, burst 50, per real client IP on `online` router | ✅ Applied, live immediately |
| Alert retuning | `HighCPUUsage` 80%→90% / 5m→15m; `WebServicesHighLatency` exclude ACME router / 5m→10m; `AndonAlertHighErrorRate` description fix | ✅ Deployed |

**Effect:** Today's log (2026-04-18 00:00–03:36 UTC) shows 45,728 requests with **zero 5xx errors**. The `43.173.x.x` bots are still scraping but at throttled rate (~42 req per IP over 3.5 hrs = 12 req/hr), no longer causing saturation.

---

## Recommendations

### High priority

1. **Cloudflare WAF rate limiting** — add a rate limit rule at the Cloudflare level targeting `/forum/index.php` with a per-IP limit (e.g. 60 req/min). This stops bot traffic before it reaches the origin entirely, saving bandwidth and PHP-FPM load.

2. **Cloudflare Bot Fight Mode** — enable for `wetfishonline.com` in the Cloudflare dashboard. ByteDance/Kaopu IPs are well-known to Cloudflare's bot database.

3. **Block `43.172.0.0/14` at Cloudflare** — this entire /14 block (43.172.0.0–43.175.255.255) is ByteDance/Kaopu infrastructure. If no legitimate users are expected from this range, a Cloudflare firewall rule to challenge or block it would eliminate ~86% of yesterday's attack traffic with a single rule.

4. **SMF hostname lookup — disable** (pending manual action):
   > Admin → Server Settings → Security and Moderation → Enable hostname lookup → **Disabled**

   Eliminates per-request shell execution and reduces CPU overhead immediately.

### Medium priority

5. **PHPSESSID in URL** — SMF passes session IDs in URLs when cookies are unavailable (a sign the client isn't accepting cookies). Consider disabling URL-based sessions in SMF settings to prevent bots from bypassing session tracking. This may break some crawlers but not real users.

6. **SMF caching** — enable file-based or memcached caching in SMF admin to reduce DB hits per page view under load.

7. **PHP-FPM monitoring** — add a metric for active workers vs. `pm.max_children` to get early warning before saturation. `pm.max_children = 15` is better but not infinite — monitor actual worker utilisation.

8. **robots.txt enforcement** — the bots ignore `robots.txt` but it provides a documented baseline. Consider adding Cloudflare rules to block crawlers that ignore `robots.txt` (identifiable by absence of a prior fetch of `/robots.txt`).

---

## Indicators of Compromise

For blocklisting or Cloudflare firewall rules:

**IP ranges (primary botnet):**
```
43.172.194.0/24
43.172.195.0/24
43.172.196.0/24
43.172.197.0/24
43.172.198.0/24
43.173.173.0/24
43.173.174.0/24
43.173.175.0/24
43.173.176.0/24
43.173.177.0/24
43.173.178.0/24
43.173.179.0/24
43.173.180.0/24
43.173.181.0/24
43.173.182.0/24
```
Or as a single supernet: `43.172.0.0/14` (covers all observed ranges and broader ByteDance/Kaopu space)

**Bot UA pattern (regex):**
```
Chrome/(103|104|105|106|107|108|109|110|111|112|116|117|120|124|131|133|142)\.0
```
Note: Chrome/142 does not exist as of this writing and is a definitive bot indicator.

**Request pattern:**
- `PHPSESSID` in URL query string (not cookie)
- `Accept-Language: zh-CN`
- No `Referer` header
- No requests for static assets (CSS/JS/images) in same session
