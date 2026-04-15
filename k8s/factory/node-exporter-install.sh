#!/usr/bin/env bash
# Install and enable node_exporter as a systemd service on factory k8s nodes.
# Run as root on each node (staging: 45.76.235.77, prod: 104.156.237.105).
#
# node_exporter runs on the host directly (not in k8s) because it needs
# access to host-level metrics (CPU, disk, memory, network).

set -euo pipefail

VERSION="1.8.2"
ARCH="linux-amd64"
URL="https://github.com/prometheus/node_exporter/releases/download/v${VERSION}/node_exporter-${VERSION}.${ARCH}.tar.gz"

cd /tmp
curl -sL "$URL" | tar xz
mv "node_exporter-${VERSION}.${ARCH}/node_exporter" /usr/local/bin/
rm -rf "node_exporter-${VERSION}.${ARCH}"

cat > /etc/systemd/system/node_exporter.service << 'EOF'
[Unit]
Description=Prometheus Node Exporter
After=network.target

[Service]
User=root
ExecStart=/usr/local/bin/node_exporter
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now node_exporter
echo "node_exporter running on :9100"
