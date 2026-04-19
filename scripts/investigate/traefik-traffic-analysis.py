#!/usr/bin/env python3
"""
Traefik access log traffic analyser.
Analyses request patterns, status distribution, top IPs, countries,
user agents, and hourly breakdown for a given router.

Usage:
    zcat access.log.gz | python3 traefik-traffic-analysis.py [router]
    cat access.log     | python3 traefik-traffic-analysis.py [router]

    router: optional RouterName filter (default: all routers)

Example:
    zcat /opt/web-services/prod/traefik/logs/access.log.2.gz | python3 traefik-traffic-analysis.py online@file
"""

import json, re, sys
from collections import Counter, defaultdict

router_filter = sys.argv[1] if len(sys.argv) > 1 else None

ips = Counter()
status_counter = Counter()
ip_status = defaultdict(Counter)
hourly = defaultdict(Counter)
ip_sessions = defaultdict(set)
ua_counter = Counter()
ip_first = {}
ip_last = {}
subnet_counter = Counter()
country_counter = Counter()
ip_country = {}
dur_2xx = []
dur_5xx = []

for line in sys.stdin:
    try:
        r = json.loads(line.strip())
        if router_filter and r.get('RouterName') != router_filter:
            continue
        ip = r.get('ClientHost', '')
        status = r.get('DownstreamStatus', 0)
        ts = r.get('time', '')
        duration = r.get('Duration', 0)
        ua = r.get('request_User-Agent', '')
        country = r.get('request_Cf-Ipcountry', '')
        path = r.get('RequestPath', '')

        ips[ip] += 1
        status_counter[status] += 1
        ip_status[ip][status] += 1
        ua_counter[ua[:100]] += 1
        country_counter[country] += 1
        if country:
            ip_country[ip] = country

        parts = ip.split('.')
        if len(parts) == 4:
            subnet_counter['.'.join(parts[:3]) + '.0/24'] += 1

        if duration:
            if status >= 500:
                dur_5xx.append(duration / 1e9)
            elif status == 200:
                dur_2xx.append(duration / 1e9)

        if ts:
            h = ts[11:13]
            hourly[h][status] += 1
            if ip not in ip_first:
                ip_first[ip] = ts
            ip_last[ip] = ts

        m = re.search(r'PHPSESSID=([a-z0-9]+)', path)
        if m:
            ip_sessions[ip].add(m.group(1))
    except:
        pass

print(f'=== TOP 30 IPs ===')
for ip, count in ips.most_common(30):
    statuses = dict(ip_status[ip].most_common(3))
    sessions = len(ip_sessions.get(ip, []))
    country = ip_country.get(ip, '??')
    first = ip_first.get(ip, '')[:19]
    last = ip_last.get(ip, '')[:19]
    print(f'{ip} [{country}]: {count:5d} reqs | {statuses} | sessions={sessions} | {first} -> {last}')

print()
print('=== STATUS DISTRIBUTION ===')
total = sum(status_counter.values())
for s, c in sorted(status_counter.items()):
    print(f'  HTTP {s}: {c:7d} ({c / total * 100:.2f}%)')

print()
print('=== HOURLY BREAKDOWN ===')
for h in sorted(hourly.keys()):
    fives = sum(v for k, v in hourly[h].items() if k >= 500)
    twos = hourly[h].get(200, 0)
    tot = sum(hourly[h].values())
    bar = '#' * min(50, fives // 300)
    print(f'  {h}:00  total={tot:6d}  200={twos:6d}  5xx={fives:6d}  {bar}')

print()
print('=== TOP COUNTRIES ===')
for c, n in country_counter.most_common(15):
    print(f'  {c}: {n}')

print()
print('=== TOP SUBNETS ===')
for s, c in subnet_counter.most_common(20):
    print(f'  {s}: {c}')

print()
print('=== TOP 10 USER AGENTS ===')
for ua, c in ua_counter.most_common(10):
    print(f'  [{c:6d}] {ua}')

print()
total_5xx = sum(v for k, v in status_counter.items() if k >= 500)
avg2 = sum(dur_2xx) / len(dur_2xx) if dur_2xx else 0
avg5 = sum(dur_5xx) / len(dur_5xx) if dur_5xx else 0
print('=== SUMMARY ===')
print(f'Total requests:      {total:,}')
print(f'Total 5xx:           {total_5xx:,} ({total_5xx / total * 100:.1f}%)')
print(f'Total unique IPs:    {len(ips):,}')
print(f'Avg 200 resp time:   {avg2:.3f}s')
print(f'Avg 5xx resp time:   {avg5:.3f}s')
