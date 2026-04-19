# Investigation Scripts

Scripts for forensics, diagnostics, and monitoring health checks.

## Scripts

### `traefik-traffic-analysis.py`
Analyses Traefik JSON access logs for traffic patterns: top IPs, countries, status distribution, hourly breakdown, user agents, subnets.

```bash
# Analyse a specific router in a rotated log
zcat /opt/web-services/prod/traefik/logs/access.log.2.gz \
  | python3 traefik-traffic-analysis.py online@file

# Analyse all routers in the live log
cat /opt/web-services/prod/traefik/logs/access.log \
  | python3 traefik-traffic-analysis.py
```

---

### `traefik-exploit-scan.py`
Scans Traefik JSON access logs for exploitation attempts: SQLi, XSS, LFI, RCE patterns, WordPress probes, webshell probes, env/git recon, and unusual HTTP methods. Highlights any hits that returned HTTP 200.

```bash
zcat /opt/web-services/prod/traefik/logs/access.log.2.gz \
  | python3 traefik-exploit-scan.py
```

> **Note:** SMF uses semicolons as URL parameter separators (`;topic=`, `;id=`, `;msg=`). Review any RCE hits manually — they are often false positives in SMF context.

---

### `server-diag.sh`
Quick server health snapshot: Docker services, disk, memory, load, top processes, open ports.

```bash
# Local
bash server-diag.sh

# Remote
ssh vultr-prod 'bash -s' < server-diag.sh
ssh dedi-prod  'bash -s' < server-diag.sh
ssh stage      'bash -s' < server-diag.sh
```

---

### `prometheus-target-check.sh`
Checks all Prometheus scrape targets and reports which are up/down with last error.

```bash
# Run on dedi-prod
ssh dedi-prod 'bash -s' < prometheus-target-check.sh

# Or with custom URL
bash prometheus-target-check.sh http://localhost:9090
```

---

### `active-alerts.sh`
Lists currently firing alerts from Alertmanager.

```bash
# Run on dedi-prod
ssh dedi-prod 'bash -s' < active-alerts.sh

# Or with custom URL
bash active-alerts.sh http://localhost:9093
```

---

## Related Docs

- `docs/forensics-2026-04-17-bot-attack.md` — ByteDance scraping event
- `docs/forensics-2026-04-17-exploitation-attempts.md` — exploitation attempt analysis
- `docs/incident-2026-04-17-online-forum-outages.md` — incident report and mitigations
