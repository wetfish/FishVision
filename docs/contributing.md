# Contributing to FishVision

## Branching Strategy

```
feature/* → main → release
```

| Branch | Purpose |
|---|---|
| `feature/*` | All development work |
| `main` | Integration — validated, stable, not yet deployed |
| `release` | Production — triggers deploy to dedi-prod on merge |

**Rules:**
- Never push directly to `main` or `release`
- All changes enter via PR
- PRs to `main` require CI to pass
- PRs to `release` must come from `main` and require CI to pass

---

## Workflow

### Starting work

```bash
git checkout main && git pull
git checkout -b feature/my-change
```

### Opening a PR

Push your branch and open a PR targeting `main`. CI will run automatically — all checks must pass before merge.

### Deploying to production

Once changes are merged to `main` and validated in integration, open a PR from `main` → `release`. Merging triggers the deploy workflow automatically.

---

## CI Checks

Every PR runs the following (`.github/workflows/validate.yml`):

| Check | What it validates |
|---|---|
| `promtool check rules` | Alert rule syntax and expression validity |
| `amtool check-config` | Alertmanager routing config |
| `promtool check config` | Prometheus scrape config |
| `kustomize build` | All overlays in `k8s/overlays/` and `k8s/factory/overlays/` |
| `:latest` tag check | No upstream images pinned to `:latest` |
| `docker compose config` | Compose file syntax |
| Grafana dashboard JSON | All dashboards in `grafana/dashboards/` are valid JSON |

If any check fails the PR cannot be merged.

---

## Deployment

Merging to `release` triggers `.github/workflows/deploy.yml`, which:

1. Runs all CI checks (via `workflow_call`)
2. Detects which paths changed
3. Rsyncs files to dedi-prod (`/opt/FishVision/`)
4. Reloads only the affected services (Prometheus, Alertmanager, Grafana) or restarts them if config requires it (Loki, Tempo)
5. Runs a health check against all five services

### Smart reload vs restart

| Changed path | Action |
|---|---|
| `prometheus/` | Hot reload (`/-/reload`) — no downtime |
| `alertmanager/` | Hot reload (`/-/reload`) — no downtime |
| `grafana/` | Dashboard provisioning reload — no downtime |
| `loki/` | Container restart |
| `tempo/` | Container restart |
| `docker-compose.yml` | `docker compose up -d --remove-orphans` |

### Factory Kubernetes manifests

Changes to `k8s/factory/` are **not** applied automatically — the deploy job emits a warning with the commands to run manually:

```bash
kubectl apply -k k8s/factory/overlays/staging/ --context=<staging>
kubectl apply -k k8s/factory/overlays/prod/ --context=<prod>
```

The OTLP patches (`k8s/factory/overlays/*/otlp-patch.yaml`) are reference files — they need to be applied in the factory repo's own kustomize overlays, not here.

---

## Required GitHub Secrets

| Secret | Description |
|---|---|
| `DEPLOY_KEY` | Private SSH key authorized on dedi-prod |
| `DEPLOY_HOST_KEY` | dedi-prod SSH host key (`ssh-keyscan 144.48.106.242`) |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin password for provisioning reload |

---

## Running Validation Locally

```bash
# Alert rules
promtool check rules prometheus/alert.rules.yml

# Alertmanager config
amtool check-config alertmanager/alertmanager.yml

# Prometheus config (rules file must be accessible)
ln -sf "$PWD/prometheus/alert.rules.yml" /tmp/alert.rules.yml
sed 's|/etc/prometheus/alert.rules.yml|/tmp/alert.rules.yml|' prometheus/prometheus.yml > /tmp/prom-check.yml
promtool check config /tmp/prom-check.yml

# Kustomize overlays
for overlay in k8s/overlays/*/ k8s/factory/overlays/*/; do
  kustomize build "$overlay" > /dev/null && echo "OK: $overlay"
done

# No :latest upstream images
grep -rn ':latest' k8s/ docker-compose.yml | grep -v 'fishvision/'

# Docker Compose syntax
GF_SECURITY_ADMIN_PASSWORD=placeholder docker compose config --quiet

# Grafana dashboard JSON
for f in grafana/dashboards/*.json; do
  python3 -c "import json; json.load(open('$f'))" && echo "OK: $f"
done
```

---

## Project Structure

```
FishVision/
├── alertmanager/          # Alertmanager routing config
├── grafana/
│   ├── dashboards/        # Dashboard JSON (auto-provisioned)
│   └── provisioning/      # Datasource + dashboard provider config
├── irc-bot/               # LLM-powered IRC alert analysis bot
├── irc-deamon/            # IRC server container
├── k8s/
│   ├── base/              # FishVision stack Kubernetes base manifests
│   ├── overlays/          # dev / staging / prod overlays for FishVision
│   └── factory/
│       ├── base/          # Exporters + Promtail for factory cluster
│       └── overlays/      # staging / prod — namespace + env overrides
├── loki/                  # Loki config
├── prometheus/            # Prometheus scrape config + alert rules
├── promtail/              # Promtail config (Docker Compose)
└── tempo/                 # Tempo config
```

---

## Monitored Services

| Project | Targets |
|---|---|
| factory (staging) | Node exporter, MySQL exporter, Redis exporter, Nginx exporter |
| factory (prod) | Node exporter, MySQL exporter, Redis exporter, Nginx exporter |
| web-services | Node exporter (staging + prod), Traefik metrics (staging + prod) |
| observability stack | Prometheus, Alertmanager, Loki, Tempo (self-monitoring) |

Traces from the factory app (andon-alert) are received via OTLP HTTP on port 4319 (staging) and 4318 (prod).
