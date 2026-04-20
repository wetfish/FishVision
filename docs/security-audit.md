# FishVision Security Audit

**Date:** 2026-04-01
**Scope:** All configuration files, Kubernetes manifests, Docker Compose, and application configs
**Branch:** apm-features

---

## Summary

| Severity | Count | Primary Issues |
|----------|-------|----------------|
| CRITICAL | 7 | Hardcoded credentials, unauthenticated endpoints, disabled auth |
| HIGH | 14 | No network policies, exposed APIs, missing container security contexts |
| MEDIUM | 9 | No inter-service TLS, retention gaps, image pinning |
| LOW | 4 | PDB, HPA, cleanup |
| **Total** | **34** | |

---

## CRITICAL Findings

### C-01: Hardcoded IRC NickServ Password

- **Files:** `irc-deamon/config.yml:9`, `k8s/base/irc-relay.yaml:15`
- **Issue:** NickServ password stored in plaintext in config and Kubernetes ConfigMap
  ```yaml
  irc_nickname_password: myNickServPassword
  ```
- **Impact:** Anyone with repo or ConfigMap access can steal IRC credentials and impersonate the relay bot
- **Remediation:**
  - Move password to a Kubernetes Secret with `valueFrom.secretKeyRef`
  - Inject via environment variable at runtime
  - Rotate the IRC password immediately

---

### C-02: Default Grafana Admin Credentials

- **File:** `docker-compose.yml:65-66`
- **Issue:** Default admin credentials hardcoded in compose file
  ```yaml
  GF_SECURITY_ADMIN_USER: admin
  GF_SECURITY_ADMIN_PASSWORD: admin
  ```
- **Impact:** Anyone with network access to port 3000 can log in as admin
- **Remediation:**
  - Use environment variables or Docker secrets
  - The K8s deployment references a Secret (`k8s/base/grafana.yaml:72-74`) but the Secret resource is not defined in the manifests — ensure it exists with a strong password

---

### C-03: Unauthenticated OTLP Trace Ingestion

- **Files:** `tempo/tempo-config.yaml:11-13`, `k8s/base/tempo.yaml:14-19`
- **Issue:** OTLP gRPC (4318) and HTTP (4319) endpoints bind to `0.0.0.0` with no authentication
  ```yaml
  protocols:
    grpc:
      endpoint: "0.0.0.0:4318"
    http:
      endpoint: "0.0.0.0:4319"
  ```
- **Impact:** Any external actor can push arbitrary traces/spans to Tempo — enables trace poisoning, topology mapping, and denial of service
- **Remediation:**
  - Bind receivers to `127.0.0.1` or pod network only
  - Enable `auth_enabled: true` in Tempo config
  - Add NetworkPolicy restricting ingress to trusted sources
  - For external ingestion, use a reverse proxy with mTLS or API key auth

---

### C-04: Unauthenticated IRC Relay Webhook

- **Files:** `irc-deamon/config.yml:1`, `docker-compose.yml:160-161`, `k8s/base/irc-relay.yaml:8`
- **Issue:** HTTP webhook endpoint on `0.0.0.0:8010` accepts requests without authentication
  ```yaml
  http_host: 0.0.0.0
  http_port: 8010
  ```
- **Impact:** Anyone can send arbitrary messages to the `#ops` IRC channel — fake alerts, noise injection, alert masking
- **Remediation:**
  - Bind to `127.0.0.1` (Docker) or ClusterIP-only Service (K8s)
  - Add NetworkPolicy restricting ingress to Alertmanager pod only
  - Implement HMAC signature verification or authentication token

---

### C-05: IRC TLS Certificate Validation Disabled

- **File:** `irc-deamon/config.yml:7`
- **Issue:** TLS is enabled but certificate verification is explicitly disabled
  ```yaml
  use_tls: true
  irc_verify_ssl: no
  ```
- **Impact:** Vulnerable to man-in-the-middle attacks — attacker can intercept IRC credentials and all alert messages
- **Remediation:**
  - Set `irc_verify_ssl: yes`
  - If using a self-signed certificate, add CA certificate to the container trust store
  - Verify connectivity after enabling

---

### C-06: Loki Authentication Disabled

- **Files:** `loki/loki-config.yaml:1`, `k8s/base/loki.yaml:8`
- **Issue:** Authentication explicitly disabled
  ```yaml
  auth_enabled: false
  ```
- **Impact:** Anyone with network access can read, write, or delete logs — logs may contain sensitive data (API keys, session tokens, PII)
- **Remediation:**
  - Enable `auth_enabled: true`
  - Configure tenant isolation for multi-tenancy
  - Add API key or OAuth2 authentication for Promtail and Grafana

---

### C-07: Loki Lifecycle Address Exposed

- **File:** `loki/loki-config.yaml:13`
- **Issue:** Memberlist/lifecycle address binds to all interfaces
  ```yaml
  address: 0.0.0.0
  ```
- **Impact:** Unauthorized services can interfere with Loki cluster coordination
- **Remediation:**
  - Bind to `127.0.0.1` or specific pod IP
  - Restrict with NetworkPolicy

---

## HIGH Findings

### H-01: No Kubernetes NetworkPolicies

- **File:** `k8s/base/namespace.yaml`
- **Issue:** Monitoring namespace has no NetworkPolicy — all pods communicate freely, no ingress/egress restrictions
- **Impact:** Lateral movement between compromised pods; no east-west traffic control
- **Remediation:**
  - Create a default-deny NetworkPolicy for the namespace
  - Whitelist required connections:
    - Prometheus → node exporters (9100), MySQL exporter (9104), Redis exporter (9121), Nginx exporter (9113)
    - Promtail → Loki (3100)
    - Alertmanager → IRC relay (8010)
    - Grafana → Prometheus (9090), Loki (3100), Tempo (3200)
    - Ingress → Grafana (3000), Prometheus (9090)

---

### H-02: Prometheus Lifecycle API Enabled

- **Files:** `docker-compose.yml:18`, `k8s/base/prometheus.yaml:58`
- **Issue:** `--web.enable-lifecycle` flag allows unauthenticated remote config reload
  ```yaml
  - --web.enable-lifecycle
  ```
- **Impact:** `POST /-/reload` can change scrape configs, disable alerts, or inject malicious rules without authentication
- **Remediation:**
  - Remove the flag if hot-reload is not required
  - If needed, place Prometheus behind an auth proxy

---

### H-03: No Authentication on Prometheus API

- **Files:** `k8s/base/prometheus.yaml:59-60`, `docker-compose.yml:11`
- **Issue:** Port 9090 exposed with no authentication
- **Impact:** Unauthenticated PromQL queries expose infrastructure topology; expensive queries can cause DoS
- **Remediation:**
  - Deploy an auth proxy (OAuth2 Proxy, nginx with basic auth)
  - Restrict access via NetworkPolicy to Grafana only

---

### H-04: No Authentication on Alertmanager API

- **Files:** `k8s/base/alertmanager.yaml:46`, `docker-compose.yml:40`
- **Issue:** Port 9093 exposed with no authentication
- **Impact:** Can silence alerts to mask incidents, create/delete alerts, modify routing rules
- **Remediation:**
  - Deploy auth proxy
  - Restrict network access to Prometheus only

---

### H-05: Unauthenticated Grafana Datasource Connections

- **File:** `k8s/base/grafana.yaml:13-25`
- **Issue:** Datasources (Prometheus, Loki, Tempo) accessed without credentials or mTLS
- **Impact:** Proxied access from Grafana to backends is unauthenticated
- **Remediation:**
  - Add basic auth or API key credentials to datasource provisioning
  - Enable mTLS between Grafana and backends

---

### H-06: Ingress Missing Security Headers

- **File:** `k8s/base/ingress.yaml`
- **Issue:** Only `ssl-redirect: true` annotation present; missing rate limiting, CSP, X-Frame-Options, X-Content-Type-Options, HSTS
- **Impact:** Clickjacking, MIME sniffing, brute force attacks, session fixation
- **Remediation:**
  ```yaml
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
    nginx.ingress.kubernetes.io/limit-rps: "10"
    nginx.ingress.kubernetes.io/limit-connections: "5"
    nginx.ingress.kubernetes.io/configuration-snippet: |
      more_set_headers "X-Frame-Options: SAMEORIGIN";
      more_set_headers "X-Content-Type-Options: nosniff";
      more_set_headers "X-XSS-Protection: 1; mode=block";
      more_set_headers "Strict-Transport-Security: max-age=31536000; includeSubDomains";
  ```

---

### H-07: No TLS on Dev/Staging Ingress

- **Files:** `k8s/overlays/dev/kustomization.yaml`, `k8s/overlays/staging/kustomization.yaml`
- **Issue:** TLS configured only in prod overlay; dev and staging transmit credentials in plaintext
- **Impact:** Credential interception in non-prod environments; misaligned security posture
- **Remediation:**
  - Add TLS blocks to dev and staging overlays
  - Use cert-manager with self-signed issuers for non-prod

---

### H-08: Prometheus Scrapes Public IPs Over HTTP

- **File:** `prometheus/prometheus.yml:20-82`
- **Issue:** Metrics scraped from public IPs without TLS
  ```yaml
  - targets: ["107.191.43.166:9100"]   # stage-node
  - targets: ["149.28.239.165:9100"]   # prod-node
  - targets: ["45.76.235.77:9100"]     # factory-staging
  - targets: ["104.156.237.105:9100"]  # factory-prod
  ```
- **Impact:** Node exporter metrics (CPU, memory, disk, network) exposed on public internet; MITM risk
- **Remediation:**
  - Firewall exporter ports (9100, 9104, 9121, 9113) to allow only the Prometheus server IP
  - Add TLS to scrape configs with `scheme: https`
  - Use a VPN or private network where possible
  - Enable authentication on node exporters

---

### H-09: No Read-Only Root Filesystem

- **Files:** All K8s deployments in `k8s/base/`
- **Issue:** No containers use `readOnlyRootFilesystem: true`
- **Impact:** Compromised containers can write malware, backdoors, or persistence mechanisms to the filesystem
- **Remediation:**
  ```yaml
  securityContext:
    readOnlyRootFilesystem: true
  volumeMounts:
    - name: tmp
      mountPath: /tmp
  volumes:
    - name: tmp
      emptyDir: {}
  ```

---

### H-10: Missing runAsNonRoot on Most Containers

- **Files:** `k8s/base/prometheus.yaml`, `k8s/base/alertmanager.yaml`, `k8s/base/grafana.yaml`, `k8s/base/irc-relay.yaml`
- **Issue:** Only Loki and Tempo run as non-root (UID 10001); Prometheus, Alertmanager, Grafana, and IRC relay have no securityContext
- **Impact:** Root-level access if containers are compromised
- **Remediation:**
  ```yaml
  securityContext:
    runAsNonRoot: true
    runAsUser: 65534
    runAsGroup: 65534
  ```

---

### H-11: Missing Privilege Escalation Prevention

- **Files:** All K8s deployments in `k8s/base/`
- **Issue:** No container sets `allowPrivilegeEscalation: false` or drops capabilities
- **Impact:** Containers can escalate to root via Linux capabilities
- **Remediation:**
  ```yaml
  securityContext:
    allowPrivilegeEscalation: false
    capabilities:
      drop:
        - ALL
  ```

---

### H-12: IRC Relay Container Has No Security Context

- **File:** `k8s/base/irc-relay.yaml:41-58`
- **Issue:** No securityContext defined; runs as root in Debian container
- **Impact:** Full system access if compromised
- **Remediation:**
  - Add securityContext (runAsNonRoot, readOnlyRootFilesystem, drop all capabilities)
  - Update Dockerfile to create and use a non-root user

---

### H-13: No Pod Security Standards Enforcement

- **File:** `k8s/base/namespace.yaml`
- **Issue:** No Pod Security Standards labels on the monitoring namespace
- **Impact:** Insecure pods can be deployed without restriction
- **Remediation:**
  ```yaml
  metadata:
    name: monitoring
    labels:
      pod-security.kubernetes.io/enforce: restricted
      pod-security.kubernetes.io/audit: restricted
      pod-security.kubernetes.io/warn: restricted
  ```

---

### H-14: Docker Compose Binds All Ports to 0.0.0.0

- **File:** `docker-compose.yml`
- **Issue:** All service ports bound to all interfaces by default
  ```yaml
  ports:
    - "9090:9090"   # Prometheus
    - "9093:9093"   # Alertmanager
    - "3000:3000"   # Grafana
    - "3100:3100"   # Loki
    - "3200:3200"   # Tempo
    - "4318:4318"   # OTLP gRPC
    - "4319:4319"   # OTLP HTTP
    - "8010:8010"   # IRC relay
  ```
- **Impact:** Every service accessible from any network interface on the host
- **Remediation:**
  - Bind internal-only services to localhost: `"127.0.0.1:9090:9090"`
  - Expose only Grafana externally (behind a reverse proxy with auth)

---

## MEDIUM Findings

### M-01: Loki Data Retention Disabled

- **File:** `loki/loki-config.yaml:50-51`
- **Issue:** Retention is disabled; logs never auto-delete
  ```yaml
  retention_deletes_enabled: false
  retention_period: 0s
  ```
- **Impact:** Disk exhaustion (DoS), PII retained indefinitely (GDPR risk), escalating storage costs
- **Remediation:**
  ```yaml
  retention_deletes_enabled: true
  retention_period: 168h
  ```

---

### M-02: No TLS Between Prometheus and Alertmanager

- **File:** `prometheus/prometheus.yml:8-9`
- **Issue:** Alertmanager communication over plaintext HTTP
- **Impact:** Alerts can be intercepted and modified in transit
- **Remediation:** Configure TLS in the alerting section of `prometheus.yml`

---

### M-03: No TLS Between Promtail and Loki

- **File:** `promtail/promtail-config.yaml:9`
- **Issue:** Logs shipped over plaintext HTTP
  ```yaml
  - url: http://loki:3100/loki/api/v1/push
  ```
- **Impact:** Logs (potentially containing secrets) transmitted in cleartext
- **Remediation:** Use `https://` with TLS verification

---

### M-04: No TLS Between Alertmanager and IRC Relay

- **File:** `alertmanager/alertmanager.yml:24`
- **Issue:** Webhook delivered over plaintext HTTP
  ```yaml
  - url: "http://irc-relay:8010/ops"
  ```
- **Impact:** Alert content can be intercepted or modified
- **Remediation:** Use HTTPS with mTLS or API token

---

### M-05: Go Base Image Not Pinned to Patch Version

- **File:** `irc-deamon/Dockerfile.irc:1`
- **Issue:** Uses `golang:1.23` without patch version
- **Impact:** Non-reproducible builds; potential supply chain compromise
- **Remediation:**
  - Pin to specific digest: `golang:1.23.8-bookworm@sha256:...`
  - Pin runtime image: `debian:12.5-slim@sha256:...`

---

### M-06: No Image Pull Policy or Registry Restrictions

- **Files:** All K8s deployments in `k8s/base/`
- **Issue:** Public images pulled with default pull policy; no registry allowlist
- **Impact:** Supply chain attack vector; images could be replaced at source
- **Remediation:**
  - Set `imagePullPolicy: Always`
  - Use a private registry mirror
  - Implement image signing verification (Cosign/Kyverno)

---

### M-07: No Resource Limits in Docker Compose

- **File:** `docker-compose.yml`
- **Issue:** No CPU or memory limits on any service
- **Impact:** One service can starve others; no DoS protection; can crash the host
- **Remediation:**
  ```yaml
  deploy:
    resources:
      limits:
        cpus: '1'
        memory: 1G
  ```

---

### M-08: Prometheus 30-Day Retention May Be Excessive

- **File:** `k8s/base/prometheus.yaml:57`
- **Issue:** `--storage.tsdb.retention.time=30d` retains metrics longer than operationally necessary
- **Impact:** Storage bloat; retained forensic data from past incidents
- **Remediation:** Align retention with operational needs (7-15 days for most use cases)

---

### M-09: Commented Webhook URL in Alertmanager Config

- **File:** `alertmanager/alertmanager.yml:4-9`
- **Issue:** Commented-out webhook URL with UUID pointing to internal IP
  ```yaml
  # - url: "http://172.17.0.1:5678/webhook-test/36144696-..."
  ```
- **Impact:** Low — information leak of internal IP and endpoint UUID
- **Remediation:** Remove commented-out code from config files

---

## LOW Findings

### L-01: No Pod Disruption Budgets

- **Files:** No PDB resources in `k8s/base/`
- **Issue:** Monitoring stack has no disruption protection during cluster maintenance
- **Impact:** All monitoring pods can be evicted simultaneously
- **Remediation:** Add PDB with `minAvailable: 1` for critical services

---

### L-02: No Horizontal Pod Autoscaling

- **Files:** All K8s deployments use `replicas: 1`
- **Issue:** No auto-scaling for load spikes
- **Impact:** Monitoring degradation under high load
- **Remediation:** Add HPA for Prometheus and Loki based on CPU/memory thresholds

---

### L-03: Missing Resource Requests on Some Pods

- **Files:** K8s deployments in `k8s/base/`
- **Issue:** Some containers define limits but not requests
- **Impact:** Kubernetes scheduler cannot optimally place pods
- **Remediation:** Define both `requests` and `limits` for all containers

---

### L-04: No Liveness/Readiness Probes in K8s Deployments

- **Files:** K8s deployments in `k8s/base/`
- **Issue:** Docker Compose defines healthchecks but K8s manifests lack equivalent probes
- **Impact:** Unhealthy pods continue receiving traffic; slow failure detection
- **Remediation:** Add probes matching the Docker Compose healthchecks:
  ```yaml
  livenessProbe:
    httpGet:
      path: /-/healthy
      port: 9090
    initialDelaySeconds: 30
    periodSeconds: 15
  readinessProbe:
    httpGet:
      path: /-/ready
      port: 9090
    initialDelaySeconds: 5
    periodSeconds: 10
  ```

---

## Remediation Roadmap

### Week 1 — Critical

| ID | Action | Effort |
|----|--------|--------|
| C-01 | Rotate IRC password, move to K8s Secret | 1h |
| C-02 | Replace Grafana default credentials | 30m |
| C-03 | Bind OTLP receivers to localhost, enable Tempo auth | 1h |
| C-04 | Restrict IRC relay to Alertmanager only | 1h |
| C-05 | Enable IRC TLS certificate validation | 30m |
| C-06 | Enable Loki authentication | 2h |
| C-07 | Bind Loki lifecycle to localhost | 30m |

### Week 2-3 — High

| ID | Action | Effort |
|----|--------|--------|
| H-01 | Create NetworkPolicies for monitoring namespace | 4h |
| H-02 | Remove or protect Prometheus lifecycle API | 30m |
| H-03/04 | Deploy auth proxy for Prometheus and Alertmanager | 4h |
| H-06 | Add ingress security headers and rate limiting | 2h |
| H-07 | Add TLS to dev/staging ingress | 2h |
| H-08 | Firewall node exporter ports to Prometheus IP only | 2h |
| H-09/10/11/12 | Add securityContext to all pods | 3h |
| H-13 | Enable Pod Security Standards on namespace | 1h |
| H-14 | Bind Docker Compose ports to 127.0.0.1 | 1h |

### Month 1 — Medium

| ID | Action | Effort |
|----|--------|--------|
| M-01 | Enable Loki retention | 30m |
| M-02/03/04 | Add inter-service TLS | 8h |
| M-05/06 | Pin images, set pull policy, add scanning | 4h |
| M-07 | Add Docker Compose resource limits | 1h |

### Ongoing — Low

| ID | Action | Effort |
|----|--------|--------|
| L-01 | Add Pod Disruption Budgets | 1h |
| L-02 | Add HPA for Prometheus and Loki | 2h |
| L-03 | Align resource requests/limits | 1h |
| L-04 | Add liveness/readiness probes to K8s deployments | 2h |
