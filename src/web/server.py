"""
Zero-dependency web UI server for the bot dashboard.

Uses only Python stdlib (http.server for HTTP + WebSocket).
Serves the React UI from ui/dist/ and provides bot status via WebSocket.

Runs in a daemon thread — no impact on the main bot loop.
"""
import json
import logging
import os
import struct
import threading
import time
from hashlib import sha1
from base64 import b64encode
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

logger = logging.getLogger(__name__)

UI_DIR = (Path(__file__).resolve().parent.parent.parent / "ui" / "dist").resolve()
WEBSOCKET_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# ── Shared state ──────────────────────────────────────────────────────

_status = {
    "running": False,
    "uptime_sec": 0,
    "messages_processed": 0,
    "wechat_backend": "",
    "ai_backend": "",
    "db_ok": False,
    "last_api_call_sec_ago": -1,
    "timestamp": "",
    "error": "",
}

_clients: list = []
_clients_lock = threading.Lock()


def update_status(**kwargs):
    """Push status update to all WebSocket clients (thread-safe)."""
    _status.update(kwargs)
    _status["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    payload = json.dumps(_status, ensure_ascii=False)
    dead = []
    with _clients_lock:
        for sock in _clients:
            try:
                _send_ws_frame(sock, payload)
            except Exception:
                dead.append(sock)
        for s in dead:
            if s in _clients:
                _clients.remove(s)


def _recv_exactly(sock, n):
    """Receive exactly n bytes from a socket (handles TCP fragmentation)."""
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def _send_ws_frame(sock, text):
    """Send a WebSocket text frame."""
    data = text.encode("utf-8")
    frame = bytearray()
    frame.append(0x81)  # FIN + text opcode
    if len(data) < 126:
        frame.append(len(data))
    elif len(data) < 65536:
        frame.append(126)
        frame.extend(struct.pack(">H", len(data)))
    else:
        frame.append(127)
        frame.extend(struct.pack(">Q", len(data)))
    frame.extend(data)
    sock.sendall(bytes(frame))


def _read_ws_frame(sock):
    """Read a WebSocket frame (handles TCP fragmentation)."""
    header = _recv_exactly(sock, 2)
    if header is None:
        return None
    opcode = header[0] & 0x0F
    if opcode == 0x8:  # close
        return None
    if opcode == 0x9:  # ping
        # Send pong
        pong = bytearray([0x8A, 0x00])  # FIN + pong opcode, no payload
        sock.sendall(bytes(pong))
        return b""  # return empty to keep reading
    length = header[1] & 0x7F
    if length == 126:
        ext = _recv_exactly(sock, 2)
        if ext is None:
            return None
        length = struct.unpack(">H", ext)[0]
    elif length == 127:
        ext = _recv_exactly(sock, 8)
        if ext is None:
            return None
        length = struct.unpack(">Q", ext)[0]
    mask = _recv_exactly(sock, 4)
    if mask is None:
        return None
    payload = _recv_exactly(sock, length)
    if payload is None:
        return None
    payload = bytearray(payload)
    for i in range(len(payload)):
        payload[i] ^= mask[i % 4]
    return bytes(payload)


def _parse_http_headers(data):
    """Parse HTTP request headers from raw bytes."""
    headers = {}
    lines = data.decode(errors="replace").split("\r\n")
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return headers


def _handle_ws_upgrade(data, conn):
    """Perform WebSocket handshake. Returns True on success, False on failure."""
    try:
        headers = _parse_http_headers(data)

        # Validate WebSocket upgrade
        if headers.get("upgrade", "").lower() != "websocket":
            return False
        if headers.get("sec-websocket-version") != "13":
            return False

        key = headers.get("sec-websocket-key", "")
        if not key:
            return False

        accept = b64encode(sha1((key + WEBSOCKET_GUID.decode()).encode()).digest()).decode()

        conn.sendall(
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n".encode()
        )
        return True
    except Exception:
        logger.exception("WebSocket upgrade failed")
        return False


class _UIHandler(SimpleHTTPRequestHandler):
    """HTTP handler: static files + WebSocket upgrade + API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_POST(self):
        # Only delegate specific API paths; return 405 for unknown POST paths
        if self.path in ("/api/config", "/api/start", "/api/stop"):
            self.do_GET()
        else:
            self.send_response(405)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": "Method not allowed"}).encode())

    def do_GET(self):
        self._handle_request()

    def _handle_request(self):
        # ── WebSocket upgrade ─────────────────────────────────────────
        if self.path == "/ws":
            connection_header = self.headers.get("Connection", "").lower()
            upgrade_header = self.headers.get("Upgrade", "").lower()
            if "upgrade" in connection_header and upgrade_header == "websocket":
                raw_request = (
                    self.raw_requestline
                    + b"\r\n"
                    + self.headers.as_bytes()
                )
                if _handle_ws_upgrade(raw_request, self.request):
                    with _clients_lock:
                        _clients.append(self.request)
                    # Send initial status
                    try:
                        _send_ws_frame(self.request, json.dumps(_status, ensure_ascii=False))
                    except Exception:
                        with _clients_lock:
                            if self.request in _clients:
                                _clients.remove(self.request)
                        return
                    # Read loop (ping/pong handled in _read_ws_frame)
                    while True:
                        try:
                            frame = _read_ws_frame(self.request)
                            if frame is None:
                                break
                        except Exception:
                            break
                    with _clients_lock:
                        if self.request in _clients:
                            _clients.remove(self.request)
                    return
                else:
                    self.send_response(400)
                    self.end_headers()
                    return

        # ── API: Start bot ────────────────────────────────────────────
        if self.path == "/api/start":
            update_status(running=True)
            self.send_json({"ok": True})
            return

        # ── API: Stop bot ─────────────────────────────────────────────
        if self.path == "/api/stop":
            update_status(running=False)
            self.send_json({"ok": True})
            return

        # ── API: Save config ──────────────────────────────────────────
        if self.path == "/api/config":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len else b"{}"
            try:
                config = json.loads(body)
                env_path = Path(__file__).resolve().parent.parent.parent / ".env"
                # Also check CWD for .env (packaged EXE scenario)
                if not env_path.exists():
                    env_path = Path.cwd() / ".env"
                if env_path.exists():
                    lines = env_path.read_text(encoding="utf-8").splitlines()
                    new_lines = []
                    updates = {
                        "DEEPSEEK_API_KEY": config.get("deepseek_api_key"),
                        "DEEPSEEK_MODEL": config.get("deepseek_model"),
                        "ANTHROPIC_API_KEY": config.get("anthropic_api_key"),
                        "SUMMARIZE_MODEL": config.get("summarize_model"),
                        "AI_BACKEND": config.get("ai_backend"),
                        "BOT_DISPLAY_NAME": config.get("bot_display_name"),
                        "WECHAT_BACKEND": config.get("wechat_backend"),
                        "WECHAT_GROUPS": config.get("wechat_groups"),
                        "PROACTIVE_ENABLED": str(config.get("proactive_enabled", False)).lower(),
                        "VULGAR_GUARD_ENABLED": str(config.get("vulgar_guard_enabled", True)).lower(),
                        "ENABLE_WEB_SEARCH": str(config.get("enable_web_search", True)).lower(),
                        "STICKY_MENTION_ENABLED": str(config.get("sticky_mention_enabled", True)).lower(),
                        "LOG_LEVEL": config.get("log_level"),
                    }
                    seen = set()
                    for line in lines:
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#") and "=" in stripped:
                            key = stripped.split("=", 1)[0].strip()
                            if key in updates and updates[key] is not None:
                                new_lines.append(f"{key}={updates[key]}")
                                seen.add(key)
                                continue
                        new_lines.append(line)
                    for key, val in updates.items():
                        if key not in seen and val is not None:
                            new_lines.append(f"{key}={val}")
                    # Atomic write: temp file then os.replace
                    tmp_path = env_path.with_suffix(".tmp")
                    tmp_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                    os.replace(tmp_path, env_path)
                    self.send_json({
                        "ok": True,
                        "saved": list(seen),
                        "requires_restart": True,
                    })
                else:
                    self.send_json({"ok": False, "error": ".env not found"})
            except Exception as e:
                logger.exception("Failed to save config")
                self.send_json({"ok": False, "error": str(e)})
            return

        # ── API: Get status ───────────────────────────────────────────
        if self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(_status, ensure_ascii=False).encode())
            return

        # ── SPA fallback: serve index.html for unknown paths ──────────
        if self.command != "GET" and self.command != "HEAD":
            self.send_response(405)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": "Method not allowed"}).encode())
            return

        path = self.translate_path(self.path)
        if not Path(path).exists():
            self.path = "/index.html"

        super().do_GET()

    def log_message(self, format, *args):
        """Log HTTP errors but suppress normal access logs."""
        if args and any(
            code in str(args).lower()
            for code in ["error", "exception", "400", "401", "403", "404", "405", "500"]
        ):
            logger.warning("HTTP %s", format % args)

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())


_server_started = False


def _run_server(host, port):
    """Run the HTTP server (blocking, called in daemon thread)."""
    server = ThreadingHTTPServer((host, port), _UIHandler)
    logger.info("Web UI: http://%s:%s", host, port)
    server.serve_forever()


def start_web_server(host="127.0.0.1", port=8765):
    """Start the web UI in a daemon thread (idempotent)."""
    global _server_started
    if _server_started:
        logger.debug("Web server already running, skipping duplicate start")
        return None

    if not UI_DIR.exists():
        logger.warning("UI not built. Run: cd ui && npm run build")
        return None

    thread = threading.Thread(
        target=_run_server, args=(host, port),
        daemon=True, name="web-ui-server",
    )
    thread.start()
    _server_started = True
    return thread
