"""
FishVision IRC Bot — LLM-powered alert analysis via Ollama + monitoring tool use.

Connects to IRC alongside alertmanager-irc-relay. When it sees an alert message
from the relay bot, it queries Prometheus/Loki/Tempo to build context, then uses
a local Ollama model to generate a concise action-item summary posted to the channel.

Fully open-source: Ollama for LLM, manual tool orchestration (no proprietary APIs).
"""

import os
import json
import time
import logging
import threading
import ssl
import irc.client
import irc.connection
import requests
from tools import TOOL_DEFINITIONS, TOOL_HANDLERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("irc-bot")

IRC_HOST = os.environ.get("IRC_HOST", "irc.wetfish.net")
IRC_PORT = int(os.environ.get("IRC_PORT", "6697"))
IRC_USE_TLS = os.environ.get("IRC_USE_TLS", "true").lower() == "true"
IRC_NICK = os.environ.get("IRC_NICK", "fishvision")
IRC_NICKSERV_PASS = os.environ.get("IRC_NICKSERV_PASS", "")
IRC_CHANNEL = os.environ.get("IRC_CHANNEL", "#alerts")
ALERT_BOT_NICK = os.environ.get("ALERT_BOT_NICK", "alertbot")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://localhost:3030")

ANALYSIS_COOLDOWN = 30
_last_analysis = 0
_model_pulled = False


def ensure_model():
    """Pull the model if it's not already available locally."""
    global _model_pulled
    if _model_pulled:
        return
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        if OLLAMA_MODEL in models:
            log.info(f"Model {OLLAMA_MODEL} already available")
            _model_pulled = True
            return
        log.info(f"Pulling model {OLLAMA_MODEL} (this may take a few minutes)...")
        r = requests.post(f"{OLLAMA_URL}/api/pull", json={"name": OLLAMA_MODEL, "stream": False}, timeout=600)
        r.raise_for_status()
        log.info(f"Model {OLLAMA_MODEL} pulled successfully")
        _model_pulled = True
    except Exception as e:
        log.error(f"Failed to pull model: {e}")


def ollama_chat(messages, tools=None):
    """Call Ollama chat API with optional tool definitions. Pulls model if needed."""
    ensure_model()
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": 4096},
    }
    if tools:
        payload["tools"] = tools
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=300)
    r.raise_for_status()
    return r.json()


def build_ollama_tools():
    """Convert our tool definitions to Ollama's tool format."""
    tools = []
    for t in TOOL_DEFINITIONS:
        tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            }
        })
    return tools


class FishVisionBot:
    def __init__(self):
        self.reactor = irc.client.Reactor()
        self.connection = None
        self._alert_buffer = []
        self._buffer_lock = threading.Lock()
        self._buffer_timer = None

    def connect(self):
        if IRC_USE_TLS:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            factory = irc.connection.Factory(wrapper=ssl_ctx.wrap_socket)
        else:
            factory = irc.connection.Factory()
        self.connection = self.reactor.server().connect(
            IRC_HOST, IRC_PORT, IRC_NICK, connect_factory=factory
        )
        self.connection.add_global_handler("welcome", self._on_connect)
        self.connection.add_global_handler("pubmsg", self._on_pubmsg)
        self.connection.add_global_handler("privmsg", self._on_pubmsg)
        self.connection.add_global_handler("disconnect", self._on_disconnect)
        self.connection.add_global_handler("nicknameinuse", self._on_nick_in_use)
        log.info(f"Connecting to {IRC_HOST}:{IRC_PORT} (TLS={IRC_USE_TLS})")

    def _on_connect(self, connection, event):
        log.info("Connected to IRC")
        if IRC_NICKSERV_PASS:
            connection.privmsg("NickServ", f"IDENTIFY {IRC_NICKSERV_PASS}")
            time.sleep(2)
        connection.join(IRC_CHANNEL)
        log.info(f"Joined {IRC_CHANNEL}")

    def _on_nick_in_use(self, connection, event):
        connection.nick(IRC_NICK + "_")

    def _on_disconnect(self, connection, event):
        log.warning("Disconnected, reconnecting in 30s...")
        time.sleep(30)
        self.connect()

    def _on_pubmsg(self, connection, event):
        sender = irc.client.NickMask(event.source).nick
        message = event.arguments[0]

        if sender.lower() != ALERT_BOT_NICK.lower():
            if IRC_NICK.lower() in message.lower() and "status" in message.lower():
                self._send(connection, "FishVision bot online. Monitoring alerts from alertbot.")
            return

        with self._buffer_lock:
            self._alert_buffer.append(message)
            if self._buffer_timer:
                self._buffer_timer.cancel()
            self._buffer_timer = threading.Timer(3.0, self._process_buffered_alert, args=[connection])
            self._buffer_timer.start()

    def _process_buffered_alert(self, connection):
        with self._buffer_lock:
            if not self._alert_buffer:
                return
            full_alert = "\n".join(self._alert_buffer)
            self._alert_buffer.clear()

        global _last_analysis
        now = time.time()
        if now - _last_analysis < ANALYSIS_COOLDOWN:
            log.info("Skipping analysis (cooldown)")
            return
        _last_analysis = now

        if "RESOLVED" in full_alert:
            log.info("Skipping resolved alert")
            return

        log.info(f"Processing alert:\n{full_alert}")
        threading.Thread(target=self._analyze_alert, args=(connection, full_alert), daemon=True).start()

    def _analyze_alert(self, connection, alert_text):
        system_msg = f"""You are FishVision, an SRE assistant bot in an IRC channel. An alert just fired.
Your job:
1. Use tools to investigate — check metrics, logs, traces.
2. Provide a SHORT (3-5 line) summary with concrete action items.
3. No markdown. Keep lines under 400 chars. Use | as separator.

Monitoring stack: Prometheus (metrics), Loki (logs), Tempo (traces), Grafana ({GRAFANA_URL})
Be concise — this goes to IRC."""

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"This alert just fired:\n\n{alert_text}\n\nInvestigate and provide action items."},
        ]
        tools = build_ollama_tools()

        try:
            for _ in range(2):
                resp = ollama_chat(messages, tools=tools)
                msg = resp.get("message", {})

                # Check for tool calls
                tool_calls = msg.get("tool_calls", [])
                if not tool_calls:
                    # Final text response
                    text = msg.get("content", "").strip()
                    if text:
                        for line in text.split("\n"):
                            line = line.strip()
                            if line:
                                self._send(connection, line)
                    return

                # Execute tool calls
                messages.append(msg)
                for tc in tool_calls:
                    fn = tc["function"]
                    handler = TOOL_HANDLERS.get(fn["name"])
                    if handler:
                        log.info(f"Calling tool: {fn['name']}({json.dumps(fn.get('arguments', {}))[:200]})")
                        result = handler(fn.get("arguments", {}))
                    else:
                        result = f"Unknown tool: {fn['name']}"
                    messages.append({
                        "role": "tool",
                        "content": result[:2000],
                    })

            self._send(connection, "Analysis incomplete — check Grafana directly.")

        except Exception as e:
            log.error(f"LLM analysis failed: {e}")
            self._send(connection, f"Analysis error: {e}")

    def _send(self, connection, message):
        log.info(f"Sending to IRC: {message[:200]}")
        for chunk in [message[i:i+400] for i in range(0, len(message), 400)]:
            connection.privmsg(IRC_CHANNEL, chunk)
            time.sleep(0.5)

    def run(self):
        self.connect()
        log.info("Bot running...")
        self.reactor.process_forever()


if __name__ == "__main__":
    bot = FishVisionBot()
    bot.run()
