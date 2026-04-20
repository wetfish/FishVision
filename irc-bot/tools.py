"""MCP-style tool definitions for querying the monitoring stack."""

import requests
import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger("irc-bot.tools")

PROMETHEUS_URL = "http://prometheus:9090"
LOKI_URL = "http://loki:3100"
TEMPO_URL = "http://tempo:3200"


TOOL_DEFINITIONS = [
    {
        "name": "query_prometheus",
        "description": "Run a PromQL instant query against Prometheus. Use this to check current metric values like CPU, memory, error rates, connection counts, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "PromQL expression to evaluate, e.g. 'up{job=\"factory-mysql\"}' or 'rate(traces_spanmetrics_calls_total{service=\"andon-alert\",status_code=\"STATUS_CODE_ERROR\"}[5m])'"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "query_prometheus_range",
        "description": "Run a PromQL range query over the last N minutes. Returns time series data to identify trends.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "PromQL expression"
                },
                "minutes": {
                    "type": "integer",
                    "description": "How many minutes of history to query (default 15)",
                    "default": 15
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "query_loki",
        "description": "Query Loki for recent log lines matching a LogQL expression. Use this to find error logs, stack traces, or application output.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "LogQL expression, e.g. '{container=\"laravel-app\"} |= \"ERROR\"'"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of log lines to return (default 20)",
                    "default": 20
                },
                "minutes": {
                    "type": "integer",
                    "description": "How many minutes of history to search (default 15)",
                    "default": 15
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_tempo_traces",
        "description": "Search Tempo for recent traces by service name. Returns trace IDs, durations, and root span info.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Service name to search for, e.g. 'andon-alert'"
                },
                "min_duration": {
                    "type": "string",
                    "description": "Minimum trace duration filter, e.g. '500ms', '1s' (optional)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of traces to return (default 10)",
                    "default": 10
                }
            },
            "required": ["service_name"]
        }
    },
    {
        "name": "get_prometheus_alerts",
        "description": "Get all currently firing alerts from Prometheus. Use this to see the full alert state.",
        "input_schema": {
            "type": "object",
            "properties": {},
        }
    },
]


def query_prometheus(query: str) -> str:
    try:
        r = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query}, timeout=10)
        data = r.json()
        if data["status"] != "success":
            return f"Error: {data.get('error', 'unknown')}"
        results = data["data"]["result"]
        if not results:
            return "No results returned."
        lines = []
        for res in results[:20]:
            metric = res["metric"]
            val = res["value"][1] if "value" in res else "N/A"
            label_str = ", ".join(f'{k}="{v}"' for k, v in metric.items() if k != "__name__")
            name = metric.get("__name__", "")
            lines.append(f"{name}{{{label_str}}} = {val}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error querying Prometheus: {e}"


def query_prometheus_range(query: str, minutes: int = 15) -> str:
    try:
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=minutes)
        r = requests.get(f"{PROMETHEUS_URL}/api/v1/query_range", params={
            "query": query,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "step": "60s"
        }, timeout=10)
        data = r.json()
        if data["status"] != "success":
            return f"Error: {data.get('error', 'unknown')}"
        results = data["data"]["result"]
        if not results:
            return "No results returned."
        lines = []
        for res in results[:5]:
            metric = res["metric"]
            label_str = ", ".join(f'{k}="{v}"' for k, v in metric.items() if k != "__name__")
            name = metric.get("__name__", "")
            values = res["values"]
            latest = values[-1][1] if values else "N/A"
            oldest = values[0][1] if values else "N/A"
            lines.append(f"{name}{{{label_str}}}: {oldest} -> {latest} ({len(values)} samples over {minutes}m)")
        return "\n".join(lines)
    except Exception as e:
        return f"Error querying Prometheus range: {e}"


def query_loki(query: str, limit: int = 20, minutes: int = 15) -> str:
    try:
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=minutes)
        r = requests.get(f"{LOKI_URL}/loki/api/v1/query_range", params={
            "query": query,
            "start": int(start.timestamp() * 1e9),
            "end": int(end.timestamp() * 1e9),
            "limit": limit,
            "direction": "backward"
        }, timeout=10)
        data = r.json()
        if data["status"] != "success":
            return f"Error: {data.get('error', 'unknown')}"
        streams = data["data"]["result"]
        if not streams:
            return "No log lines found."
        lines = []
        for stream in streams:
            for ts, line in stream["values"][:limit]:
                dt = datetime.fromtimestamp(int(ts) / 1e9, tz=timezone.utc).strftime("%H:%M:%S")
                lines.append(f"[{dt}] {line[:300]}")
        return "\n".join(lines[:limit])
    except Exception as e:
        return f"Error querying Loki: {e}"


def search_tempo_traces(service_name: str, min_duration: str = None, limit: int = 10) -> str:
    try:
        params = {"tags": f"service.name={service_name}", "limit": limit}
        if min_duration:
            params["minDuration"] = min_duration
        r = requests.get(f"{TEMPO_URL}/api/search", params=params, timeout=10)
        data = r.json()
        traces = data.get("traces", [])
        if not traces:
            return "No traces found."
        lines = []
        for t in traces[:limit]:
            tid = t.get("traceID", "?")
            root = t.get("rootServiceName", "?")
            root_span = t.get("rootTraceName", "?")
            dur_ms = t.get("durationMs", 0)
            lines.append(f"TraceID: {tid[:16]}... | {root}/{root_span} | {dur_ms}ms")
        return "\n".join(lines)
    except Exception as e:
        return f"Error searching Tempo: {e}"


def get_prometheus_alerts() -> str:
    try:
        r = requests.get(f"{PROMETHEUS_URL}/api/v1/alerts", timeout=10)
        data = r.json()
        if data["status"] != "success":
            return f"Error: {data.get('error', 'unknown')}"
        alerts = data["data"]["alerts"]
        if not alerts:
            return "No alerts currently firing."
        firing = [a for a in alerts if a["state"] == "firing"]
        if not firing:
            return "No alerts currently firing (some may be pending)."
        lines = []
        for a in firing:
            name = a["labels"].get("alertname", "?")
            sev = a["labels"].get("severity", "?")
            inst = a["labels"].get("instance", "?")
            summary = a["annotations"].get("summary", "")
            lines.append(f"[{sev}] {name} on {inst}: {summary}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching alerts: {e}"


TOOL_HANDLERS = {
    "query_prometheus": lambda args: query_prometheus(args.get("query", "up")),
    "query_prometheus_range": lambda args: query_prometheus_range(args.get("query", "up"), args.get("minutes", 15)),
    "query_loki": lambda args: query_loki(args.get("query", '{job=~".+"}'), args.get("limit", 20), args.get("minutes", 15)),
    "search_tempo_traces": lambda args: search_tempo_traces(args.get("service_name", args.get("query", "unknown")), args.get("min_duration"), args.get("limit", 10)),
    "get_prometheus_alerts": lambda args: get_prometheus_alerts(),
}
