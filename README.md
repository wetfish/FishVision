# 🐟 FishVision  
Prometheus → Alertmanager → IRC alerting pipeline using [alertmanager-irc-relay](https://github.com/google/alertmanager-irc-relay).  
This project provides an **end-to-end monitoring and alerting stack** where Prometheus alerts are routed to IRC in real time.  

---

## Audience
- DevOps
- SRE
- Infrastructure Engineers
- Incident Response Teams

---

## Objective
Deliver **critical Prometheus alerts** (e.g., high CPU, disk full) to a designated IRC channel to improve visibility and reduce mean time to response. Provide centralized logging (Loki), distributed tracing (Tempo), and LLM-assisted alert triage (Ollama + IRC Bot).

---

## 🗂️ Project Structure  
```text
FishVision/
├── alertmanager/
│   └── alertmanager.yml              # Alertmanager config with webhook receiver
├── alertmanager-irc-relay.yaml       # IRC relay deployment config
├── docker-compose.yml                # Compose stack for all services
├── docs/
│   ├── planned-implementation.md     # Adaptation/rollout plan
│   └── security-audit.md            # Security audit notes
├── grafana/
│   ├── dashboards/
│   │   ├── andon-alert-observability.json
│   │   └── factory.json
│   └── provisioning/
│       ├── dashboards/dashboards.yml
│       └── datasources/datasources.yml
├── irc-bot/
│   ├── Dockerfile                    # IRC bot container
│   ├── bot.py                        # LLM-powered alert analysis bot
│   ├── tools.py                      # Bot tool functions
│   └── requirements.txt
├── irc-deamon/
│   ├── Dockerfile.irc                # IRC server container
│   └── config.yml                    # IRC server configuration
├── k8s/
│   ├── base/                         # Kustomize base manifests
│   │   ├── kustomization.yaml
│   │   ├── namespace.yaml
│   │   ├── prometheus.yaml
│   │   ├── alertmanager.yaml
│   │   ├── grafana.yaml
│   │   ├── loki.yaml
│   │   ├── tempo.yaml
│   │   ├── irc-relay.yaml
│   │   └── ingress.yaml
│   └── overlays/
│       ├── dev/kustomization.yaml
│       ├── staging/kustomization.yaml
│       └── prod/kustomization.yaml
├── loki/
│   └── loki-config.yaml              # Loki log aggregation config
├── prometheus/
│   ├── alert.rules.yml               # Prometheus alerting rules
│   └── prometheus.yml                # Prometheus scrape + rule config
├── promtail/
│   └── promtail-config.yaml          # Promtail log collection config
├── tempo/
│   └── tempo-config.yaml             # Tempo tracing config
└── utils/
    └── node-exporter-installer.sh    # Helper script to install Node Exporter
```

---

## 🧱 Architecture  
| Component           | Description |
|---------------------|-------------|
| **Node Exporter**   | Exposes host-level metrics from Linux systems |
| **Prometheus**      | Scrapes metrics and evaluates alert rules |
| **Alertmanager**    | Routes alerts and sends notifications |
| **IRC Relay**       | Receives webhooks and relays alerts to IRC |
| **IRC Server**      | Hosts the target IRC channel (e.g., `#alerts`) |
| **Grafana**         | Visualizes metrics, logs, and traces |
| **Loki**            | Log aggregation and querying |
| **Promtail**        | Collects and ships container/host logs to Loki |
| **Tempo**           | Distributed tracing backend |
| **Ollama**          | Local LLM inference for alert analysis |
| **IRC Bot**         | LLM-powered bot that analyzes alerts in IRC |

---

## Prerequisites
- Docker & Docker Compose installed
- Outbound IRC traffic allowed from relay host
- Working IRC server (local or external)
- Ollama (included in stack) for LLM-powered alert analysis

Optional: Node Exporter installed on monitored hosts (script provided in `utils/`).

---

## ⚙️ Quick Start  
1. **Install Node Exporter (optional)**  
   ```bash
   ./utils/node-exporter-installer.sh
   ```
2. **Start the stack**  
   ```bash
   docker-compose up -d
   ```
3. **Access services**  
   - Prometheus → [http://localhost:9090](http://localhost:9090)  
   - Alertmanager → [http://localhost:9093](http://localhost:9093)  
   - Grafana → [http://localhost:3000](http://localhost:3000)  
   - IRC server → configured from `irc-deamon/`  
4. **Trigger a test alert**  
   ```bash
   stress-ng --cpu 4 --timeout 180s
   ```
   Expected message in `#alerts`:
   ```
   [FIRING] HighCPUUsage: server1.example.com has high CPU
   ```

---

## 🛠️ Maintenance  
| Task | Frequency | Notes |
|------|-----------|-------|
| Test alert delivery | Monthly | Simulate CPU load and verify IRC |
| Update container images | Quarterly | Check for new versions in `docker-compose.yml` |
| Rotate bot nick/channel | As needed | Update relay flags in config |
| Update alert rules | As needed | Edit `prometheus/alert.rules.yml` + restart Prometheus |

---

## Security Notes
- Run relay on a private network or behind a reverse proxy (NGINX, Caddy)
- Enable logging for relay HTTP traffic
- Restrict IRC server access as appropriate
- See [docs/security-audit.md](docs/security-audit.md) for a detailed security audit


