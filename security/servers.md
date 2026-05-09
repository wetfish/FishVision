# Server Inventory

Last updated: 2026-05-09  
Sources: prometheus.yml scrape targets, ~/.ssh/config, shell history (90-day audit)

---

## Observability Host

| Alias | IP | User | Key | Role |
|---|---|---|---|---|
| `dedi-prod` / `matrix` | `144.48.106.242` | root | `cyba_wetish` | FishVision observability stack (Prometheus, Grafana, Loki, Tempo, Alertmanager) |

---

## Web Services

| Alias | IP | User | Key | Role |
|---|---|---|---|---|
| `stage` | `107.191.43.166` | root | `cyba_wetish` | Web services staging |
| `prod` / `vultr-prod` | `149.28.239.165` | root | `cyba_wetish` | Web services production |
| `old-prod` | `134.195.89.60` | root | `cyba_wetish` | Legacy production |
| `future-prod` | `164.92.229.176` | root | `cyba_wetish` | Future production node (IRC) |

---

## Factory (k8s / RKE2)

| Alias | IP | User | Key | Role |
|---|---|---|---|---|
| `andon-alert-stage` | `155.138.225.13` | root | `cyba_wetish` | Factory k8s staging node |
| *(factory staging)* | `45.76.235.77` | root | `jfc-deploy` | Factory k8s staging — node exporter, MySQL, Nginx, Redis exporters (NodePorts 30104/30113/30121) |
| *(factory prod)* | `104.156.237.105` | root | `jfc-deploy` | Factory k8s production — node exporter, MySQL, Nginx, Redis exporters (direct ports 9104/9113/9121) |

---

## Testforums / Mini-stage

| Alias | IP | User | Key | Role |
|---|---|---|---|---|
| *(testforums)* | `144.202.63.236` | root | `cyba_wetish` / `mini-stage` | Testforums / mini-stage node |

---

## Other / Historical Access

| Alias | IP / Host | User | Key | Notes |
|---|---|---|---|---|
| *(IRC server)* | `us-chicago-01.wetfish.chat` | root | `cyba_wetish` | wetfish IRC server |
| *(unnamed)* | `216.128.155.242` | root | `jfc-deploy` | Active server — needs alias added to ~/.ssh/config |
| *(local LAN)* | `192.168.1.x` range | various | — | Local dev/LAN hosts (rachel, testdev, etc.) — not production |
| *(AWS EC2)* | `54.187.211.44` | `debug-labs` | — | One-off access (DoorDash interview lab) — not infra |

---

## CVE Patch Scope — CVE-2026-31431 (Copy Fail)

All Linux servers above require kernel patching. Priority order:

1. `149.28.239.165` — vultr-prod (web services production)
2. `104.156.237.105` — factory prod
3. `144.48.106.242` — dedi-prod (observability)
4. `107.191.43.166` — stage (web services staging)
5. `45.76.235.77` — factory staging
6. `155.138.225.13` — andon-alert-stage
7. `144.202.63.236` — testforums/mini-stage
8. `164.92.229.176` — future-prod
9. `134.195.89.60` — old-prod
10. `216.128.155.242` — unnamed server (jfc-deploy key)

---

## Notes

- `216.128.155.242` has no SSH alias — add one to `~/.ssh/config`.
- SSH keys in use: `cyba_wetish` (primary), `jfc-deploy` (factory + 216.128.155.242), `mini-stage` (testforums).
