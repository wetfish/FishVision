# Incident Report: wetfishonline.com 91% Error Rate
**Date:** 2026-04-20
**Duration:** ~02:29 UTC – 03:25 UTC (~56 minutes)
**Severity:** Critical
**Service:** wetfishonline.com (online@file router, vultr-prod)
**Status:** Resolved

---

## Summary

wetfishonline.com experienced a near-total outage with a sustained 91–95% HTTP 5xx error rate. All 15 PHP-FPM workers became permanently saturated — each blocked for 60+ seconds per request — due to `gethostbyaddr()` reverse DNS lookups timing out on bot traffic IPs with no rDNS records. The bot flood (same 43.172.0.0/14 ByteDance ASN as the April 17 incident) overwhelmed capacity once workers were stuck. Recovery involved patching the PHP container at runtime, which introduced two additional complications.

---

## Timeline (UTC)

| Time | Event |
|------|-------|
| 02:29 | PHP-FPM workers begin saturating. All 15 workers enter sustained `R` state. |
| ~02:35 | 5xx error rate reaches 91%. Traefik starts returning 502/504 at scale. |
| 02:49 | Incident detected. `ps aux` shows all workers running since 02:29 with 88% CPU. |
| 02:50 | PHP-FPM logs confirm `host: not found` errors per request. Root cause identified: `gethostbyaddr()` fallback in `host_from_ip()`. |
| 02:52 | Fake `/usr/local/bin/host` binary deployed in PHP container. `resolv.conf` set to `timeout:1 attempts:1`. |
| 02:54 | First kill attempt uses `awk "{print $1}"` (user field, not PID) — no workers killed. |
| 03:00 | `nsswitch.conf` changed to `hosts: files` (removed `dns`) to bypass gethostbyaddr DNS. |
| 03:01 | Error type shifts to 500: `Settings.php` discovered to be 0 bytes in PHP container. |
| 03:05 | Workers correctly killed by explicit PID list. Fresh workers spawn but fail with 500 due to missing Settings.php. |
| 03:09 | Error type shifts to 503: database connection fails because Docker container name resolution (`online-db`) broke when `dns` was removed from nsswitch.conf. |
| 03:21 | Settings.php restored from Docker image via `docker cp`. nsswitch.conf restored to `hosts: files dns`. resolv.conf restored to `127.0.0.11` with `timeout:1 attempts:1`. |
| 03:22 | Workers killed again with correct PID extraction. Fresh workers spawn. |
| 03:25 | 0% 5xx error rate. Requests returning 200 at 28ms average. |

---

## Root Cause

SMF's `host_from_ip()` function in `Sources/Subs.php` performs reverse DNS lookups on every visitor IP:

```php
// Try the Linux host command (50% of requests via mt_rand)
if (!isset($modSettings['host_to_dis']))
    $test = @shell_exec('host -W 1 ' . @escapeshellarg($ip));

// ...if host unavailable or not called, fallback:
if (!isset($host) || $host === false)
    $host = @gethostbyaddr($ip);
```

`host` was not installed in the PHP container, so the `shell_exec` path returned `sh: host: not found` — which SMF correctly interprets as "not found" and sets `$host = ''`. However, the `mt_rand(0, 1) == 1` condition means only 50% of requests take this path. The other 50% fall through directly to `gethostbyaddr()`.

`gethostbyaddr()` uses the system resolver with no PHP-level timeout. The bot IPs (43.172.0.0/14) have no rDNS records, so each lookup blocked for the full resolver timeout (default: 5 seconds × 3 attempts = 15 seconds). Under the bot flood (~35 req/s), the 15 PHP-FPM workers saturated within seconds — each stuck in a gethostbyaddr call. New requests queued, then timed out (60s Traefik timeout → 504) or were rejected immediately (502).

---

## Complications During Mitigation

### 1. Settings.php truncated to 0 bytes
At some point during the incident, `/var/www/forum/Settings.php` inside `online-php` was found to be 0 bytes. The forum files are baked into the Docker image (`ghcr.io/wetfish/online:prod-php`) and Settings.php should be 2,244 bytes. The truncation cause is unknown — possibly a `cat >` redirect with an incorrect path during remediation. This caused 500 errors ("Undefined variable: boarddir") when fresh workers were spawned with the correct nsswitch.conf.

**Resolution:** Copied Settings.php from a temporary container spawned from the same image:
```bash
docker run --rm -d --name tmp-online ghcr.io/wetfish/online:prod-php sleep 30
docker cp tmp-online:/var/www/forum/Settings.php /tmp/Settings.php
docker cp /tmp/Settings.php online-php:/var/www/forum/Settings.php
docker stop tmp-online
```

### 2. nsswitch.conf change broke Docker DNS
Setting `hosts: files` (removing `dns`) in the PHP container's `/etc/nsswitch.conf` was intended to make `gethostbyaddr()` skip DNS entirely. Instead, it also broke Docker's internal service name resolution — `online-db` could not be resolved, causing all database connections to fail and returning 503.

**Resolution:** Restored `hosts: files dns` in nsswitch.conf. The resolver timeout (`timeout:1 attempts:1` in resolv.conf) is sufficient to limit gethostbyaddr blocking to ≤1 second.

---

## Fixes Applied (Temporary — Container Ephemeral)

All changes below are in-memory modifications to the running `online-php` container and **will be lost on container restart**.

| Fix | Effect |
|-----|--------|
| `/usr/local/bin/host` fake binary returning `"not found"` | Prevents 50% of requests from taking the `shell_exec` path, which was already working but making it consistent |
| `resolv.conf`: `timeout:1 attempts:1` | Limits gethostbyaddr blocking to ≤1 second instead of 15+ |
| `nsswitch.conf`: `hosts: files dns` (restored) | Allows Docker service name resolution to function |

With these in place: avg request duration dropped from 60+ seconds to 28ms.

---

## Permanent Fix Required

The ephemeral changes will not survive a container restart. The permanent fix is to **disable SMF's hostname lookup feature**:

**Via SMF Admin Panel:**
`Admin → Server Settings → Security & Moderation → Enable hostname lookup → Disabled`

This removes the `host_from_ip()` call entirely from request processing. SMF stores IPs numerically in the database and this feature only serves to display hostnames in the admin member list — it has no functional impact on normal forum operation.

**Alternatively**, install `bind-tools` (or `dnsutils`) in the PHP Docker image so the `host -W 1` path works correctly with a 1-second timeout, and the `gethostbyaddr` fallback is never reached.

---

## Contributing Factors

- **Same bot source as April 17 incident** (43.172.0.0/14, ByteDance/Kaopu ASN 138915) — rate limiting applied per IP is insufficient against a distributed flood of 1,908+ unique IPs.
- **SMF hostname lookup not disabled** after being identified as a problem on April 17. The action item from the previous incident was not completed.
- **PHP-FPM max_children = 15** — even with short gethostbyaddr timeouts, 35 req/s with 15 workers at 1s/request only handles 15 req/s capacity.

---

## Action Items

| Priority | Action | Owner |
|----------|--------|-------|
| **Critical** | Disable SMF hostname lookup in admin panel (survives container restarts) | Manual — requires SMF admin login |
| **High** | Rebuild `ghcr.io/wetfish/online:prod-php` image to include the resolv.conf timeout and fake `host` binary (or install real `bind-tools`) | wetfish/online repo |
| **High** | Add Cloudflare WAF rate rule to block/challenge 43.172.0.0/14 at the edge | Cloudflare dashboard |
| **Medium** | Increase PHP-FPM `pm.max_children` further or implement a request queue (pm.max_requests) to auto-recycle stuck workers | `config/php-fpm-pool.conf` |
| **Medium** | Add a Prometheus/Alertmanager alert for PHP-FPM worker saturation (monitor php-fpm pool accept queue depth or via blackbox) | FishVision alert rules |

---

## Metrics

| Metric | Value |
|--------|-------|
| Outage duration | ~56 minutes |
| Peak 5xx error rate | ~95% |
| Requests affected | ~35 req/s × 3360 seconds ≈ ~117,600 |
| PHP-FPM workers stuck | 15/15 (100%) |
| Avg request duration at peak | 60–90 seconds |
| Avg request duration at recovery | 28ms |
