# FishVision Adaptation Plan

## Context

FishVision is a standalone Docker Compose monitoring stack (Prometheus, Grafana, Loki, Tempo, Alertmanager + IRC relay). It currently monitors 3 bare-metal nodes via node_exporter but has no awareness of the actual services running on them (factory Laravel app, web-services, etc.).

**Goal**: Adapt FishVision to be the central observability hub for all Wetfish projects, with factory as the top priority. Additionally, create Kubernetes manifests so FishVision can be deployed into K8s clusters.

**Key constraint**: Factory's RKE2 cluster has only ~365m CPU headroom on 2-vCPU nodes — too tight to run a full monitoring stack in-cluster. FishVision will monitor factory externally.

---

## Phase 1: Factory Monitoring (Priority)

### 1.1 Add Factory Scrape Targets
**File**: `prometheus/prometheus.yml`
- Add factory staging node (45.76.235.77:9100) and prod node (104.156.237.105:9100) as scrape targets
- Add MySQL exporter targets (requires exporter deployment — see 1.2)
- Add Redis exporter targets
- Add nginx/PHP-FPM status endpoints if exposed

### 1.2 Factory Exporter Sidecars (changes in factory repo)
Add lightweight metric exporters as sidecars in factory's K8s base manifests:

- **mysql-exporter** sidecar in `k8s/services/factory/k8s/base/mysql.yaml` (~10m CPU, 32Mi RAM)
- **redis-exporter** sidecar in `k8s/services/factory/k8s/base/redis.yaml` (~10m CPU, 32Mi RAM)
- **nginx stub_status** + php-fpm status in `k8s/services/factory/k8s/base/web.yaml` (already has nginx, just enable status endpoint)
- Update network policies in `k8s/infrastructure/network-policies/factory-allow.yaml` to allow external scraping on exporter ports

Total additional resource cost: ~30m CPU, ~96Mi RAM (well within headroom)

### 1.3 Factory-Specific Alert Rules
**File**: `prometheus/alert.rules.yml`
- Add `FactoryMySQLDown` — MySQL exporter unreachable
- Add `FactoryRedisDown` — Redis exporter unreachable
- Add `FactoryAppDown` — web pod unreachable
- Add `FactoryHighMySQLConnections` — connection count threshold
- Add `FactoryHighRedisMemory` — Redis memory threshold
- Add `FactoryPodRestarts` — Kubernetes pod restart count (via kube-state-metrics or custom)

### 1.4 Grafana Datasource Provisioning -- COMPLETED
**Files**: `grafana/provisioning/datasources/datasources.yml` and `grafana/provisioning/dashboards/dashboards.yml`
- Auto-provision Prometheus, Loki, Tempo datasources
- Factory dashboard JSON created (`grafana/dashboards/factory.json`)
- Andon alert observability dashboard added (`grafana/dashboards/andon-alert-observability.json`)

---

## Phase 2: Web-Services & Web-Services-K8s Monitoring

### 2.1 Web-Services (Docker Compose) Scrape Targets
**File**: `prometheus/prometheus.yml`
- The prod-node target (149.28.239.165:9100) already covers web-services infrastructure
- Add Traefik metrics endpoint if exposed

### 2.2 Web-Services-K8s Integration
- web-services-k8s already has its own kube-prometheus-stack in-cluster
- Add Prometheus federation or remote_write from web-services-k8s Prometheus → FishVision Prometheus for centralized view
- Add scrape config for web-services-k8s Prometheus federation endpoint

### 2.3 Service-Specific Alert Rules
**File**: `prometheus/alert.rules.yml`
- Add alert group for web-services targets

---

## Phase 3: FishVision Kubernetes Manifests

Create K8s manifests following factory's Kustomize pattern so FishVision can be deployed in K8s when resources allow.

### 3.1 Base Manifests -- COMPLETED
**Directory**: `k8s/base/`
- `namespace.yaml` — `monitoring` namespace
- `prometheus.yaml` — Deployment + ConfigMap + PVC + Service
- `alertmanager.yaml` — Deployment + ConfigMap + PVC + Service
- `grafana.yaml` — Deployment + PVC + Service + provisioning ConfigMaps
- `loki.yaml` — Deployment + ConfigMap + PVC + Service
- `tempo.yaml` — Deployment + ConfigMap + PVC + Service
- `irc-relay.yaml` — Deployment + ConfigMap + Service
- `ingress.yaml` — Ingress for Grafana/Prometheus UIs
- `kustomization.yaml`

### 3.2 Overlays -- COMPLETED
**Directories**: `k8s/overlays/{dev,staging,prod}/`
- Environment-specific hostnames, storage classes, resource limits
- Image tag overrides

---

## Phase 4: Cleanup & Improvements

### 4.1 Fix Existing Issues
- Fix alert rule description mismatches (says "70%" but threshold is 80%/90%)
- Pin image versions (currently `prom/prometheus:latest`)
- Add Grafana provisioning instead of default admin/admin with no datasources

### 4.2 Add Promtail/Log Collection -- COMPLETED
- Promtail added to `docker-compose.yml` collecting container and host logs to Loki
- Configuration at `promtail/promtail-config.yaml`

---

## Files Modified (FishVision)

| File | Action |
|------|--------|
| `prometheus/prometheus.yml` | Edit — add factory + web-services scrape targets |
| `prometheus/alert.rules.yml` | Edit — add factory-specific + web-services alert rules, fix descriptions |
| `docker-compose.yml` | Edit — pin image versions, add Promtail service |
| `grafana/provisioning/datasources/datasources.yml` | Create — auto-provision datasources |
| `grafana/provisioning/dashboards/dashboards.yml` | Create — dashboard provider config |
| `grafana/dashboards/factory.json` | Create — factory dashboard |
| `k8s/base/*.yaml` | Create — Kubernetes base manifests |
| `k8s/overlays/{dev,staging,prod}/` | Create — environment overlays |

## Files Modified (Factory — separate repo)

| File | Action |
|------|--------|
| `k8s/services/factory/k8s/base/mysql.yaml` | Edit — add mysql-exporter sidecar |
| `k8s/services/factory/k8s/base/redis.yaml` | Edit — add redis-exporter sidecar |
| `k8s/services/factory/k8s/base/web.yaml` | Edit — enable nginx stub_status |
| `k8s/infrastructure/network-policies/factory-allow.yaml` | Edit — allow metrics scraping |

---

## Verification

1. `docker compose up -d` — all services healthy
2. Prometheus targets page (localhost:9090/targets) — all targets UP
3. Grafana (localhost:3000) — datasources auto-provisioned, factory dashboard loads
4. Trigger test alert — verify IRC relay receives it
5. For factory changes: apply to staging cluster, verify exporters respond on metrics ports
6. `kubectl apply -k k8s/overlays/dev/` — verify K8s manifests are valid

---

## Implementation Order

1. Phase 1.1 + 1.3 + 1.4 (FishVision configs — no cross-repo deps)
2. Phase 4.1 (fix existing issues while we're in the configs)
3. Phase 1.2 (factory repo changes — can be a separate PR)
4. Phase 2 (web-services monitoring)
5. Phase 3 (K8s manifests)
6. Phase 4.2 (Promtail)
