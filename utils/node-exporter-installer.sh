#!/usr/bin/env bash

echo '[*] /GET latest node exporter release'
wget https://github.com/prometheus/node_exporter/releases/download/v1.9.1/node_exporter-1.9.1.linux-amd64.tar.gz

echo '[*] Install node exporter'
tar -xvf node_exporter-1.9.1.linux-amd64.tar.gz
cd node_exporter-1.9.1.linuxamd64
./node_exporter &

echo '[*] Punch hole in host firewall with ufw'
ufw allow 9100/tcp
