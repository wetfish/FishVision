# 🐟 FishVision  
Prometheus → Alertmanager → IRC alerting pipeline using [alertmanager-irc-relay](https://github.com/google/alertmanager-irc-relay).  
This project provides an **end-to-end monitoring and alerting stack** where Prometheus alerts are routed to IRC in real time.  

---

## 📌 Audience  
- DevOps  
- SRE  
- Infrastructure Engineers  
- Incident Response Teams  

---

## 🎯 Objective  
Deliver **critical Prometheus alerts** (e.g., high CPU, disk full) to a designated IRC channel to improve visibility and reduce mean time to response.  

---

## 🗂️ Project Structure  
```text
FishVision/
├── alertmanager/
│   └── alertmanager.yml        # Alertmanager config with webhook receiver
├── alertmanager-irc-relay.yaml # IRC relay deployment config
├── docker-compose.yml          # Compose stack for Prometheus, Alertmanager, Grafana, IRC
├── grafana/                    # Grafana dashboards (extendable)
├── irc-deamon/
│   ├── Dockerfile.irc          # IRC server container
│   └── config.yml              # IRC server configuration
├── prometheus/
│   ├── alert.rules.yml         # Prometheus alerting rules
│   └── prometheus.yml          # Prometheus scrape + rule config
└── utils/
    └── node-exporter-installer.sh # Helper script to install Node Exporter
```

---

## 🧱 Architecture  
| Component           | Description |
|---------------------|-------------|
| **Node Exporter**   | Exposes host-level metrics from Linux systems |
| **Prometheus**      | Scrapes metrics and evaluates alert rules |
| **Alertmanager**    | Routes alerts and sends notifications |
| **IRC Relay Bot**   | Receives webhooks and relays alerts to IRC |
| **IRC Server**      | Hosts the target IRC channel (e.g., `#alerts`) |
| **Grafana**         | Visualizes Prometheus data and alerting context |

---

## 🔧 Prerequisites  
- Docker & Docker Compose installed  
- Outbound IRC traffic allowed from relay host  
- Working IRC server (local or external)  

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
| Test alert delivery | Monthly | Simulate CPU load & verify IRC |
| Update IRC relay container | Quarterly | `docker pull ghcr.io/google/alertmanager-irc-relay` |
| Rotate bot nick/channel | As needed | Update relay flags in config |
| Update alert rules | As needed | Edit `prometheus/alert.rules.yml` + restart Prometheus |

---

## 🔒 Security Notes  
- Run relay on a private network or behind a reverse proxy (NGINX, Caddy)  
- Enable logging for relay HTTP traffic  
- Restrict IRC server access as appropriate  


