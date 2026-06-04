"""
Zero-dependency web UI server for the bot dashboard.

Uses only Python stdlib (http.server + asyncio for WebSocket).
Serves the React UI from ui/dist/ and provides bot status via WebSocket.

Runs in a daemon thread — no impact on the main bot loop.
"""
import asyncio
import json
import logging
import struct
import threading
import time
from hashlib import sha1
from base64 import b64encode
from http.server import HTTPServer, SimpleHTTPRequestHandler
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
}

_clients: list = []


def update_status(**kwargs):
    """Push status update to all WebSocket clients."""
    _status.update(kwargs)
    _status["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    payload = json.dumps(_status, ensure_ascii=False)
    dead = []
    for sock in _clients:
        try:
            _send_ws_frame(sock, payload)
        except Exception:
            dead.append(sock)
    for s in dead:
        _clients.remove(s)


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
    frame.extend(data)
    sock.sendall(bytes(frame))


def _read_ws_frame(sock):
    """Read a WebSocket frame (simplified)."""
    header = sock.recv(2)
    if len(header) < 2:
        return None
    opcode = header[0] & 0x0F
    if opcode == 0x8:  # close
        return None
    length = header[1] & 0x7F
    if length == 126:
        length = struct.unpack(">H", sock.recv(2))[0]
    mask = sock.recv(4)
    payload = bytearray(sock.recv(length))
    for i in range(len(payload)):
        payload[i] ^= mask[i % 4]
    return bytes(payload)


def _handle_ws_upgrade(data, conn):
    """Perform WebSocket handshake."""
    headers = {}
    for line in data.decode().split("\r\n")[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    key = headers.get("sec-websocket-key", "")
    accept = b64encode(sha1((key + WEBSOCKET_GUID.decode()).encode()).digest()).decode()

    conn.sendall(
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n\r\n".encode()
    )
    return True


class _UIHandler(SimpleHTTPRequestHandler):
    """HTTP handler: static files + WebSocket upgrade + API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def do_GET(self):
        # WebSocket upgrade
        if self.path == "/ws":
            if "upgrade" in self.headers.get("Connection", "").lower():
                _handle_ws_upgrade(self.raw_requestline + "\r\n" + self.headers.as_string(), self.request)
                _clients.append(self.request)
                # Send initial status
                _send_ws_frame(self.request, json.dumps(_status, ensure_ascii=False))
                # Keep connection alive
                while True:
                    try:
                        frame = _read_ws_frame(self.request)
                        if frame is None:
                            break
                    except Exception:
                        break
                if self.request in _clients:
                    _clients.remove(self.request)
                return

        # API endpoint
        if self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(_status, ensure_ascii=False).encode())
            return

        # SPA fallback: serve index.html for unknown paths
        path = self.translate_path(self.path)
        if not Path(path).exists():
            self.path = "/index.html"

        super().do_GET()

    def log_message(self, format, *args):
        pass  # Silent


def _run_server(host, port):
    """Run the HTTP server (blocking, called in daemon thread)."""
    server = HTTPServer((host, port), _UIHandler)
    logger.info("Web UI: http://%s:%s", host, port)
    server.serve_forever()


def start_web_server(host="127.0.0.1", port=8765):
    """Start the web UI in a daemon thread."""
    if not UI_DIR.exists():
        logger.warning("UI not built. Run: cd ui && npm run build")
        return None

    thread = threading.Thread(
        target=_run_server, args=(host, port),
        daemon=True, name="web-ui-server",
    )
    thread.start()
    update_status(running=True)
    return thread
