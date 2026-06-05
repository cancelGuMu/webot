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


def _find_or_create_env() -> Path:
    """Find .env file, using the canonical search order from config.py.

    If .env is not found but .env.example is, copy it to create a new .env.
    """
    import sys

    # 1. Use the canonical search from config.py (consistent across the app)
    from src.config import find_env_file
    existing = find_env_file()
    if existing:
        return existing

    # 2. Not found — try to create from .env.example
    project_root = Path(__file__).resolve().parent.parent.parent
    env_example = project_root / ".env.example"
    if not env_example.exists():
        env_example = Path.cwd() / ".env.example"
        if not env_example.exists():
            # Also search in EXE dir (frozen mode)
            if getattr(sys, "frozen", False):
                exe_candidate = Path(sys.executable).resolve().parent / ".env.example"
                if exe_candidate.exists():
                    env_example = exe_candidate

    if env_example.exists():
        # Create .env in CWD (most accessible to user)
        env_path = Path.cwd() / ".env"
        env_path.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
        logger.info("Created .env from .env.example at %s", env_path)
        return env_path

    # 3. Last resort: create minimal .env in CWD
    env_path = Path.cwd() / ".env"
    env_path.write_text(
        "AI_BACKEND=deepseek\n"
        "DEEPSEEK_API_KEY=\n"
        "WECHAT_BACKEND=wcdb\n"
        "BOT_DISPLAY_NAME=\n"
        "WECHAT_GROUPS=\n",
        encoding="utf-8",
    )
    logger.info("Created minimal .env at %s", env_path)
    return env_path


def _detect_wxid_and_db_path():
    """Auto-detect WeChat wxid and database path from common locations."""
    import os as _os
    candidates = [
        Path(_os.environ.get("USERPROFILE", "")) / "Documents" / "xwechat_files",
        Path(_os.environ.get("USERPROFILE", "")) / "Documents" / "WeChat Files",
    ]
    for base in candidates:
        if not base.exists():
            continue
        wxid_dirs = sorted(
            [d for d in base.iterdir() if d.is_dir() and d.name.startswith("wxid_")],
            key=lambda d: d.stat().st_mtime, reverse=True,
        )
        for wxid_dir in wxid_dirs:
            session_db = wxid_dir / "db_storage" / "session" / "session.db"
            if session_db.exists():
                return wxid_dir.name, str(session_db)
            # Older WeChat versions
            msg_dir = wxid_dir / "Msg"
            if msg_dir.exists():
                db_files = sorted(msg_dir.glob("MSG*.db"), key=lambda f: f.stat().st_mtime, reverse=True)
                if db_files:
                    return wxid_dir.name, str(db_files[0])
    return None, None


def _set_env_key(env_path: Path, key: str, value: str) -> None:
    """Set or update one key=value in a .env file atomically."""
    if not env_path.exists():
        env_path.write_text(f"{key}={value}\n", encoding="utf-8")
        return
    lines = env_path.read_text(encoding="utf-8").splitlines()
    new_lines, found = [], False
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k == key:
                new_lines.append(f"{key}={value}")
                found = True
                continue
        new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    tmp = env_path.with_suffix(".tmp")
    tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    os.replace(tmp, env_path)


def _write_onboarding_to_env(env_path):
    """Write accumulated onboarding data to .env file atomically."""
    env_map = {
        "AI_BACKEND": _onboarding_data.get("ai_backend", "deepseek"),
        "DEEPSEEK_API_KEY": _onboarding_data.get("deepseek_api_key", ""),
        "DEEPSEEK_MODEL": _onboarding_data.get("deepseek_model", "deepseek-v4-flash"),
        "ANTHROPIC_API_KEY": _onboarding_data.get("anthropic_api_key", ""),
        "SUMMARIZE_MODEL": _onboarding_data.get("summarize_model", "claude-haiku-4-5-20251001"),
        "WECHAT_BACKEND": _onboarding_data.get("wechat_backend", "wcdb"),
        "WECHAT_GROUPS": _onboarding_data.get("wechat_groups", "*"),
        "BOT_DISPLAY_NAME": _onboarding_data.get("bot_display_name", "群聊小助手"),
        "PROACTIVE_ENABLED": str(_onboarding_data.get("proactive_enabled", False)).lower(),
        "VULGAR_GUARD_ENABLED": str(_onboarding_data.get("vulgar_guard_enabled", True)).lower(),
        "ENABLE_WEB_SEARCH": str(_onboarding_data.get("enable_web_search", True)).lower(),
        "STICKY_MENTION_ENABLED": str(_onboarding_data.get("sticky_mention_enabled", True)).lower(),
        "WCDB_KEY": _onboarding_data.get("key", ""),
        "ONBOARDING_DONE": "true",
    }
    # Preserve existing keys not managed by onboarding
    if env_path.exists():
        lines = []
        seen = set()
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in env_map and env_map[key] is not None:
                    lines.append(f"{key}={env_map[key]}")
                    seen.add(key)
                    continue
            lines.append(line)
        for key, val in env_map.items():
            if key not in seen and val is not None:
                lines.append(f"{key}={val}")
        content = "\n".join(lines) + "\n"
    else:
        content = "\n".join(f"{k}={v}" for k, v in env_map.items() if v is not None) + "\n"

    tmp_path = env_path.with_suffix(".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, env_path)
    logger.info("Onboarding complete — wrote .env")


def _run_step1_extraction():
    """Background thread: wait for WeChat exit → restart → hook → capture.

    Uses extract_wcdb_key's on_progress callback to push real-time phase
    updates to the frontend so the user sees exactly what's happening.
    """
    from src.wechat.extract_key import extract_wcdb_key

    def _on_progress(phase, message):
        """Push progress updates to the frontend via _step1_state."""
        with _step1_lock:
            _step1_state["phase"] = phase
            _step1_state["message"] = message

    try:
        # extract_wcdb_key(require_restart=True) handles the full flow.
        # on_progress pushes phase changes so the frontend can display
        # real-time instructions (hooking → waiting_exit → waiting_login
        # → hooking_restart).
        key = extract_wcdb_key(require_restart=True,
                               on_progress=_on_progress)

        if key:
            wxid, db_path = _detect_wxid_and_db_path()
            with _onboarding_lock:
                _onboarding_data["step1_done"] = True
                _onboarding_data["key"] = key
                _onboarding_data["wxid"] = wxid or ""
                _onboarding_data["db_path"] = db_path or ""

            # Persist the key to .env immediately so the bot can use it
            # on restart without needing to complete the full onboarding flow.
            env_path = _find_or_create_env()
            _set_env_key(env_path, "WCDB_KEY", key)
            # Also set in the current process for load_dotenv in this session
            import os as _os
            _os.environ["WCDB_KEY"] = key
            # Clear the KEY_MISSING error so it doesn't reappear on page refresh
            update_status(error="")

            with _step1_lock:
                _step1_state["phase"] = "done"
                _step1_state["message"] = "密钥获取成功"
                _step1_state["result"] = {"key": key, "wxid": wxid or "", "db_path": db_path or ""}
                _step1_state["running"] = False
        else:
            with _step1_lock:
                _step1_state["phase"] = "timeout"
                _step1_state["message"] = "密钥提取超时，请确保微信已登录并重试"
                _step1_state["running"] = False

    except Exception as e:
        logger.exception("Step1 extraction failed")
        with _step1_lock:
            _step1_state["phase"] = "error"
            _step1_state["message"] = str(e)
            _step1_state["running"] = False


def _read_recent_logs():
    """Read the last 500 lines from the bot log file. Returns JSON-serializable list.

    Log format: ``YYYY-MM-DD HH:MM:SS [LEVEL] module: message``
    (configured in src/utils/logging_config.py).
    """
    import re
    project_root = Path(__file__).resolve().parent.parent.parent
    log_path = project_root / "data" / "bot.log"
    if not log_path.exists():
        return {"ok": True, "logs": [], "message": "日志文件尚未创建"}
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        # Return last 500 lines
        recent = lines[-500:]
        # Regex: timestamp [LEVEL] module: message
        pattern = re.compile(
            r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+'
            r'\[(DEBUG|INFO|WARNING|ERROR)\]\s+'
            r'([^:]+):\s+'
            r'(.*)$'
        )
        entries = []
        for line in recent:
            entry = {"raw": line}
            m = pattern.match(line.strip())
            if m:
                entry["ts"] = m.group(1)
                entry["level"] = m.group(2)
                entry["module"] = m.group(3)
                entry["msg"] = m.group(4)
            else:
                # Fallback for lines that don't match (tracebacks, multi-line, etc.)
                entry["ts"] = ""
                entry["level"] = "INFO"
                entry["module"] = ""
                entry["msg"] = line
            entries.append(entry)
        return {"ok": True, "logs": entries}
    except Exception as e:
        return {"ok": False, "logs": [], "error": str(e)}


# ── Thread-safe server state classes ────────────────────────────────────


class _ServerStatus:
    """Thread-safe bot status with WebSocket broadcast.

    All writes are serialized through an internal lock so concurrent
    update_status() calls from different threads never produce inconsistent
    status snapshots.
    """

    _FIELDS = (
        "running", "uptime_sec", "messages_processed",
        "wechat_backend", "ai_backend", "db_ok",
        "last_api_call_sec_ago", "last_api_call_time",
        "timestamp", "error",
    )

    def __init__(self):
        self._lock = threading.Lock()
        self.running = False
        self.uptime_sec = 0
        self.messages_processed = 0
        self.wechat_backend = ""
        self.ai_backend = ""
        self.db_ok = False
        self.last_api_call_sec_ago = -1
        self.last_api_call_time = 0.0
        self.timestamp = ""
        self.error = ""
        self._clients: list = []
        self._clients_lock = threading.Lock()

    def update(self, **kwargs):
        """Update status fields and broadcast to all WebSocket clients."""
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k):
                    setattr(self, k, v)
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            snapshot = self._snapshot_locked()
        self._broadcast(snapshot)

    def snapshot(self):
        """Return a consistent dict snapshot (thread-safe)."""
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self):
        """Build a dict from fields (caller must hold _lock)."""
        return {k: getattr(self, k) for k in self._FIELDS}

    def add_client(self, sock):
        with self._clients_lock:
            self._clients.append(sock)

    def remove_client(self, sock):
        with self._clients_lock:
            if sock in self._clients:
                self._clients.remove(sock)

    def _broadcast(self, snapshot):
        """Push snapshot to all connected WebSocket clients."""
        payload = json.dumps(snapshot, ensure_ascii=False)
        dead = []
        with self._clients_lock:
            for sock in self._clients:
                try:
                    _send_ws_frame(sock, payload)
                except Exception:
                    dead.append(sock)
            for s in dead:
                if s in self._clients:
                    self._clients.remove(s)


class _BotControl:
    """Thread-safe bot lifecycle control.

    Serializes start/stop transitions so concurrent API requests cannot
    create duplicate bot instances or leave the state inconsistent.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.thread = None
        self.backend = None
        self.running = False

    def register(self, thread=None, backend=None):
        with self._lock:
            if thread is not None:
                self.thread = thread
            if backend is not None:
                self.backend = backend
            self.running = True

    def register_backend(self, backend):
        """Called by Bot.run() during initialization."""
        with self._lock:
            self.backend = backend

    def stop(self):
        """Stop the bot backend and wait for the thread to exit."""
        # Read refs under lock, then call stop + join outside the lock
        # to avoid deadlock if stop() needs the lock.
        with self._lock:
            backend = self.backend
            thread = self.thread

        if backend is not None and hasattr(backend, "stop"):
            backend.stop()

        if thread is not None and thread.is_alive():
            thread.join(timeout=30)

        with self._lock:
            self.running = False
            self.backend = None
            self.thread = None
        return backend is not None

    def is_running(self):
        with self._lock:
            return self.running

    def set_running(self):
        with self._lock:
            self.running = True

    def mark_stopped(self):
        """Reset running state when the bot thread exits on its own.

        Does NOT stop the backend or join the thread — use stop() for
        external shutdown requests.  This is called from within the bot
        thread's ``finally`` block so the next /api/start can proceed.
        """
        with self._lock:
            self.running = False
            self.backend = None
            self.thread = None

    def set_thread(self, thread):
        with self._lock:
            self.thread = thread


class _ServerStartGuard:
    """Thread-safe idempotent server start guard."""

    def __init__(self):
        self._lock = threading.Lock()
        self._started = False

    def try_start(self):
        """Return True if server should start, False if already started."""
        with self._lock:
            if self._started:
                return False
            self._started = True
            return True


# ── Module-level instances ────────────────────────────────────────────

_status = _ServerStatus()
_bot_control = _BotControl()
_server_guard = _ServerStartGuard()
_shutdown_event = threading.Event()


def signal_shutdown():
    """Signal all components to stop (called on app exit)."""
    _shutdown_event.set()


def is_shutting_down():
    """Check if shutdown has been signaled."""
    return _shutdown_event.is_set()

# ── Onboarding state ──────────────────────────────────────────────────

_onboarding_data = {
    "step1_done": False, "step2_done": False, "step3_done": False, "step4_done": False,
    "key": "", "wxid": "", "db_path": "",
    "bot_display_name": "", "wechat_groups": "*", "wechat_backend": "wcdb",
    "ai_backend": "deepseek", "deepseek_api_key": "", "deepseek_model": "deepseek-v4-flash",
    "anthropic_api_key": "", "summarize_model": "claude-haiku-4-5-20251001",
    "proactive_enabled": False, "vulgar_guard_enabled": True,
    "enable_web_search": True, "sticky_mention_enabled": True,
}
_onboarding_lock = threading.Lock()

# Async step1 state
_step1_state = {
    "running": False,
    "phase": "idle",   # idle | waiting_exit | waiting_login | hooking | done | error
    "message": "",
    "result": None,    # {"key": ..., "wxid": ..., "db_path": ...}
}
_step1_thread = None
_step1_lock = threading.Lock()


# ── Public API wrappers (delegate to thread-safe classes) ─────────────


def update_status(**kwargs):
    """Push status update to all WebSocket clients (thread-safe)."""
    _status.update(**kwargs)


def register_bot(thread=None, backend=None):
    """Register bot thread/backend so the web API can control it."""
    _bot_control.register(thread=thread, backend=backend)
    update_status(running=True)


def _bot_exited():
    """Notify that the bot thread has exited (any path — normal/error).

    Resets the control lock so the next /api/start can proceed.
    Called from desktop.py's start_bot() and _start_bot_in_thread().
    """
    _bot_control.mark_stopped()


def _register_backend(backend):
    """Register backend from Bot.run() — explicit API, no monkey-patching."""
    _bot_control.register_backend(backend)


def _stop_bot():
    """Stop the running bot backend. Returns True if anything was stopped."""
    stopped = _bot_control.stop()
    update_status(running=False)
    if stopped:
        logger.info("Bot stopped via web API")
    return stopped
    return False


def _start_bot_in_thread():
    """Start the bot in a new daemon thread. Call from API handler."""
    if _bot_control.is_running():
        return {"ok": False, "error": "Bot is already running"}

    import sys
    from pathlib import Path as _Path

    project_root = _Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    def _run():
        try:
            from src.config import load_config
            config = load_config()
            update_status(
                wechat_backend=config.wechat_backend,
                ai_backend=config.ai_backend,
                error="",
            )
            from src.bot import Bot
            bot = Bot(config)
            # Bot.run() calls _register_backend() during init — no patch needed
            bot.run()
        except SystemExit:
            update_status(running=False)
        except Exception as e:
            update_status(running=False, error=str(e))
            logger.exception("Bot crashed during startup")
        finally:
            # Always clear the running flag so the user can restart
            # (bot.run() exits gracefully on errors like KEY_MISSING)
            _bot_control.mark_stopped()

    thread = threading.Thread(target=_run, daemon=True, name="bot-main")
    thread.start()
    _bot_control.set_thread(thread)
    _bot_control.set_running()
    update_status(running=True)
    return {"ok": True}


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


def _handle_ws_upgrade(headers, conn):
    """Perform WebSocket handshake using already-parsed headers.

    Uses the ``http.client.HTTPMessage`` object directly — avoids re-parsing
    raw bytes, which broke on Python 3.13 where ``headers.as_bytes()`` no
    longer round-trips faithfully.
    """
    key = headers.get("Sec-WebSocket-Key", "")
    if not key:
        logger.warning("WS upgrade rejected: missing Sec-WebSocket-Key")
        return False

    accept = b64encode(sha1((key + WEBSOCKET_GUID.decode()).encode()).digest()).decode()

    conn.sendall(
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n\r\n".encode()
    )
    logger.info("WS upgrade accepted")
    return True


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
        if self.path in ("/api/config", "/api/start", "/api/stop",
                         "/api/onboarding/reset",
                         "/api/onboarding/step1", "/api/onboarding/step2",
                         "/api/onboarding/step3", "/api/onboarding/step4"):
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
                if _handle_ws_upgrade(self.headers, self.request):
                    _status.add_client(self.request)
                    # Send initial status
                    try:
                        _send_ws_frame(
                            self.request,
                            json.dumps(_status.snapshot(), ensure_ascii=False),
                        )
                    except Exception:
                        _status.remove_client(self.request)
                        return
                    # Read loop (ping/pong handled in _read_ws_frame)
                    while True:
                        try:
                            frame = _read_ws_frame(self.request)
                            if frame is None:
                                break
                        except Exception:
                            break
                    _status.remove_client(self.request)
                    return
                else:
                    self.send_response(400)
                    self.end_headers()
                    return

        # ── API: Start bot ────────────────────────────────────────────
        if self.path == "/api/start":
            if _bot_control.is_running():
                self.send_json({"ok": True, "already_running": True})
            else:
                result = _start_bot_in_thread()
                self.send_json(result)
            return

        # ── API: Stop bot ─────────────────────────────────────────────
        if self.path == "/api/stop":
            _stop_bot()
            self.send_json({"ok": True})
            return

        # ── API: Load config ───────────────────────────────────────────
        if self.path == "/api/load-config":
            env_path = _find_or_create_env()
            raw = {}
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        raw[k.strip()] = v.strip()
            self.send_json({
                "ok": True,
                "config": {
                    "ai_backend": raw.get("AI_BACKEND", "deepseek"),
                    "deepseek_api_key": raw.get("DEEPSEEK_API_KEY", ""),
                    "deepseek_model": raw.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                    "anthropic_api_key": raw.get("ANTHROPIC_API_KEY", ""),
                    "summarize_model": raw.get("SUMMARIZE_MODEL", "claude-haiku-4-5-20251001"),
                    "bot_display_name": raw.get("BOT_DISPLAY_NAME", ""),
                    "wechat_backend": raw.get("WECHAT_BACKEND", "wcdb"),
                    "wechat_groups": raw.get("WECHAT_GROUPS", "*"),
                    "proactive_enabled": raw.get("PROACTIVE_ENABLED", "false").lower() == "true",
                    "vulgar_guard_enabled": raw.get("VULGAR_GUARD_ENABLED", "true").lower() == "true",
                    "enable_web_search": raw.get("ENABLE_WEB_SEARCH", "true").lower() == "true",
                    "sticky_mention_enabled": raw.get("STICKY_MENTION_ENABLED", "true").lower() == "true",
                    "log_level": raw.get("LOG_LEVEL", "INFO"),
                },
            })
            return

        # ── API: Save config ──────────────────────────────────────────
        if self.path == "/api/config":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len else b"{}"
            try:
                config = json.loads(body)
                env_path = _find_or_create_env()
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
                        "WECHAT_GROUPS": config.get("wechat_groups") or "*",
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
            self.wfile.write(json.dumps(_status.snapshot(), ensure_ascii=False).encode())
            return

        # ── API: Get logs ────────────────────────────────────────────
        if self.path == "/api/logs":
            self.send_json(_read_recent_logs())
            return

        # ── API: Onboarding status ────────────────────────────────────
        if self.path == "/api/onboarding/status":
            from src.config import is_onboarding_done
            done = is_onboarding_done()
            with _onboarding_lock:
                steps = {
                    "step1": _onboarding_data["step1_done"],
                    "step2": _onboarding_data["step2_done"],
                    "step3": _onboarding_data["step3_done"],
                    "step4": _onboarding_data["step4_done"],
                }
            self.send_json({"ok": True, "onboarding_done": done, "steps": steps})
            return

        # ── API: Onboarding step 1 - start extraction (async) ─────────
        if self.path == "/api/onboarding/step1":
            with _step1_lock:
                if _step1_state["running"]:
                    self.send_json({"ok": False, "phase": "busy", "message": "正在提取中..."})
                    return
                _step1_state["running"] = True
                _step1_state["phase"] = "idle"
                _step1_state["message"] = ""
                _step1_state["result"] = None

            # Start background thread
            t = threading.Thread(target=_run_step1_extraction, daemon=True)
            t.start()
            with _step1_lock:
                _step1_thread = t

            self.send_json({"ok": True, "phase": "started", "message": "提取已启动"})
            return

        # ── API: Onboarding step 1 - poll status ──────────────────────
        if self.path == "/api/onboarding/step1-status":
            with _step1_lock:
                s = dict(_step1_state)
            self.send_json(s)
            return

        # ── API: Onboarding step 2 - WeChat identity ──────────────────
        if self.path == "/api/onboarding/step2":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len else b"{}"
            try:
                data = json.loads(body)
                with _onboarding_lock:
                    _onboarding_data["step2_done"] = True
                    from src.config import _sanitize_display_name
                    _onboarding_data["bot_display_name"] = _sanitize_display_name(
                        data.get("bot_display_name", "群聊小助手")
                    )
                    _onboarding_data["wechat_groups"] = data.get("wechat_groups", "*")
                    _onboarding_data["wechat_backend"] = data.get("wechat_backend", "wcdb")
                    if data.get("wxid"):
                        _onboarding_data["wxid"] = data["wxid"]
                    if data.get("db_path"):
                        _onboarding_data["db_path"] = data["db_path"]
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)})
            return

        # ── API: Onboarding step 3 - AI backend ───────────────────────
        if self.path == "/api/onboarding/step3":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len else b"{}"
            try:
                data = json.loads(body)
                ai = data.get("ai_backend", "deepseek")
                with _onboarding_lock:
                    _onboarding_data["step3_done"] = True
                    _onboarding_data["ai_backend"] = ai
                    _onboarding_data["deepseek_api_key"] = data.get("deepseek_api_key", "")
                    _onboarding_data["deepseek_model"] = data.get("deepseek_model", "deepseek-v4-flash")
                    _onboarding_data["anthropic_api_key"] = data.get("anthropic_api_key", "")
                    _onboarding_data["summarize_model"] = data.get("summarize_model", "claude-haiku-4-5-20251001")
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)})
            return

        # ── API: Onboarding step 4 - features + write .env ────────────
        if self.path == "/api/onboarding/step4":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len else b"{}"
            try:
                data = json.loads(body)
                with _onboarding_lock:
                    _onboarding_data["step4_done"] = True
                    _onboarding_data["proactive_enabled"] = data.get("proactive_enabled", False)
                    _onboarding_data["vulgar_guard_enabled"] = data.get("vulgar_guard_enabled", True)
                    _onboarding_data["enable_web_search"] = data.get("enable_web_search", True)
                    _onboarding_data["sticky_mention_enabled"] = data.get("sticky_mention_enabled", True)

                # Write all accumulated data to .env
                env_path = _find_or_create_env()
                _write_onboarding_to_env(env_path)
                self.send_json({"ok": True})
            except Exception as e:
                logger.exception("Onboarding step4 failed")
                self.send_json({"ok": False, "error": str(e)})
            return

        # ── API: Reset onboarding → allow re-extraction ─────────────
        if self.path == "/api/onboarding/reset":
            # 1. Reset file-based state
            env_path = _find_or_create_env()
            _set_env_key(env_path, "ONBOARDING_DONE", "false")
            _set_env_key(env_path, "WCDB_KEY", "")
            # 2. Reset in-memory state so a fresh extraction can start
            with _onboarding_lock:
                for k in _onboarding_data:
                    if isinstance(_onboarding_data[k], bool):
                        _onboarding_data[k] = False
                    elif isinstance(_onboarding_data[k], str):
                        _onboarding_data[k] = ""
            with _step1_lock:
                _step1_state["running"] = False
                _step1_state["phase"] = "idle"
                _step1_state["message"] = ""
                _step1_state["result"] = None
            self.send_json({"ok": True, "message": "请退出微信，然后点击「重新获取密钥」"})
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


def _run_server(host, port):
    """Run the HTTP server (blocking, called in daemon thread)."""
    server = ThreadingHTTPServer((host, port), _UIHandler)
    server.daemon_threads = True  # WebSocket handlers won't block exit
    logger.info("Web UI: http://%s:%s", host, port)
    server.serve_forever()


def start_web_server(host="127.0.0.1", port=7327):
    """Start the web UI in a daemon thread (idempotent)."""
    if not _server_guard.try_start():
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
    return thread
