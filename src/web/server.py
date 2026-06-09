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
from urllib.parse import unquote

# Re-exported from config.py for use in API handlers.
# NOTE: _decode_wechat_groups is also imported inside _handle_request()
# conditional blocks, but for Python's scoping those later imports still
# make the name a local — so it must be imported at module level too,
# otherwise the first branch that references it raises UnboundLocalError.
from src.config import _decode_wechat_groups

logger = logging.getLogger(__name__)

import sys as _sys
if getattr(_sys, "frozen", False):
    UI_DIR = (Path(_sys._MEIPASS) / "ui" / "dist").resolve()
else:
    UI_DIR = (Path(__file__).resolve().parent.parent.parent / "ui" / "dist").resolve()
WEBSOCKET_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _messages_table_exists(conn) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='messages'"
    ).fetchone()
    return row is not None


def _find_or_create_env() -> Path:
    """Find .env file, using the canonical search order from config.py.

    If .env is not found but .env.example is, copy it to create a new .env.
    """
    import sys

    # 1. Use the canonical search from config.py (consistent across the app)
    from src.config import find_env_file, _decode_wechat_groups
    existing = find_env_file()
    if existing:
        return existing

    # 2. Not found — try to create from .env.example
    # .env.example is bundled into _MEIPASS in frozen mode.
    if getattr(sys, "frozen", False):
        env_example = Path(sys._MEIPASS) / ".env.example"
    else:
        env_example = Path(__file__).resolve().parent.parent.parent / ".env.example"

    if env_example.exists():
        # Create .env in app home (CWD already set to EXE dir / project root)
        env_path = Path(".env")
        env_path.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
        logger.info("Created .env from .env.example at %s", env_path.resolve())
        return env_path

    # 3. Last resort: create minimal .env in app home
    env_path = Path(".env")
    env_path.write_text(
        "AI_BACKEND=deepseek\n"
        "DEEPSEEK_API_KEY=\n"
        "WECHAT_BACKEND=wcdb\n"
        "BOT_DISPLAY_NAME=\n"
        "WECHAT_GROUPS=\n",
        encoding="utf-8",
    )
    logger.info("Created minimal .env at %s", env_path.resolve())
    return env_path


def _detect_default_data_dir() -> str:
    """Auto-detect the default WeChat data directory (parent of wxid_*).

    Returns the base directory path string, or empty string if not found.
    Used by the UI to show what auto-detection would use.
    """
    import os as _os
    candidates = [
        Path(_os.environ.get("USERPROFILE", "")) / "Documents" / "xwechat_files",
        Path(_os.environ.get("USERPROFILE", "")) / "Documents" / "WeChat Files",
    ]
    for base in candidates:
        if not base.exists():
            continue
        try:
            wxid_dirs = [d for d in base.iterdir() if d.is_dir() and d.name.startswith("wxid_")]
            for wxid_dir in wxid_dirs:
                session_db = wxid_dir / "db_storage" / "session" / "session.db"
                if session_db.exists():
                    return str(base)
        except PermissionError:
            continue
    return ""


_DEFAULT_FEISHU_TRIGGER_KEYWORDS = "同步到飞书,导出到飞书,写到飞书,沉淀到飞书"


def _split_csv(raw: str) -> list[str]:
    """Split a comma-separated env value into trimmed non-empty items."""
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def _bool_env(raw: str, default: bool = False) -> bool:
    if raw == "":
        return default
    return raw.strip().lower() == "true"


def _int_env(raw: str, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _feishu_config_from_raw(raw: dict[str, str]) -> dict:
    """Return UI-facing Feishu export config from env key/value pairs."""
    return {
        "feishu_export_enabled": _bool_env(
            raw.get("FEISHU_EXPORT_ENABLED", "false"),
            False,
        ),
        "feishu_app_id": raw.get("FEISHU_APP_ID", ""),
        "feishu_app_secret": raw.get("FEISHU_APP_SECRET", ""),
        "feishu_export_mode": raw.get("FEISHU_EXPORT_MODE", "knowledge"),
        "feishu_export_window_hours": _int_env(
            raw.get("FEISHU_EXPORT_WINDOW_HOURS", "8"),
            8,
        ),
        "feishu_auto_sync_enabled": _bool_env(
            raw.get("FEISHU_AUTO_SYNC_ENABLED", "false"),
            False,
        ),
        "feishu_auto_sync_min_messages": _int_env(
            raw.get("FEISHU_AUTO_SYNC_MIN_MESSAGES", "20"),
            20,
        ),
        "feishu_auto_sync_cooldown_sec": _int_env(
            raw.get("FEISHU_AUTO_SYNC_COOLDOWN_SEC", "1800"),
            1800,
        ),
        "feishu_knowledge_base_name": raw.get("FEISHU_KNOWLEDGE_BASE_NAME", "webot 群聊沉淀"),
        "feishu_knowledge_folder_token": raw.get("FEISHU_KNOWLEDGE_FOLDER_TOKEN", ""),
        "feishu_export_trigger_keywords": _split_csv(
            raw.get("FEISHU_EXPORT_TRIGGER_KEYWORDS", _DEFAULT_FEISHU_TRIGGER_KEYWORDS)
        ),
        "feishu_spreadsheet_token": raw.get("FEISHU_SPREADSHEET_TOKEN", ""),
        "feishu_spreadsheet_range": raw.get("FEISHU_SPREADSHEET_RANGE", "Sheet1!A:H"),
        "feishu_bitable_app_token": raw.get("FEISHU_BITABLE_APP_TOKEN", ""),
        "feishu_bitable_table_id": raw.get("FEISHU_BITABLE_TABLE_ID", ""),
        "feishu_doc_folder_token": raw.get("FEISHU_DOC_FOLDER_TOKEN", ""),
    }


def _feishu_updates_from_config(config: dict) -> dict[str, str | None]:
    """Return env updates for Feishu export settings from UI payload."""
    keywords = config.get("feishu_export_trigger_keywords")
    if isinstance(keywords, list):
        keywords_value = ",".join(str(k).strip() for k in keywords if str(k).strip())
    else:
        keywords_value = str(keywords).strip() if keywords is not None else None

    updates: dict[str, str | None] = {}
    field_map = {
        "feishu_export_enabled": "FEISHU_EXPORT_ENABLED",
        "feishu_app_id": "FEISHU_APP_ID",
        "feishu_app_secret": "FEISHU_APP_SECRET",
        "feishu_export_mode": "FEISHU_EXPORT_MODE",
        "feishu_export_window_hours": "FEISHU_EXPORT_WINDOW_HOURS",
        "feishu_auto_sync_enabled": "FEISHU_AUTO_SYNC_ENABLED",
        "feishu_auto_sync_min_messages": "FEISHU_AUTO_SYNC_MIN_MESSAGES",
        "feishu_auto_sync_cooldown_sec": "FEISHU_AUTO_SYNC_COOLDOWN_SEC",
        "feishu_knowledge_base_name": "FEISHU_KNOWLEDGE_BASE_NAME",
        "feishu_knowledge_folder_token": "FEISHU_KNOWLEDGE_FOLDER_TOKEN",
        "feishu_export_trigger_keywords": "FEISHU_EXPORT_TRIGGER_KEYWORDS",
        "feishu_spreadsheet_token": "FEISHU_SPREADSHEET_TOKEN",
        "feishu_spreadsheet_range": "FEISHU_SPREADSHEET_RANGE",
        "feishu_bitable_app_token": "FEISHU_BITABLE_APP_TOKEN",
        "feishu_bitable_table_id": "FEISHU_BITABLE_TABLE_ID",
        "feishu_doc_folder_token": "FEISHU_DOC_FOLDER_TOKEN",
    }
    for field, env_key in field_map.items():
        if field not in config:
            continue
        if field in ("feishu_export_enabled", "feishu_auto_sync_enabled"):
            updates[env_key] = str(config.get(field, False)).lower()
        elif field in (
            "feishu_export_window_hours",
            "feishu_auto_sync_min_messages",
            "feishu_auto_sync_cooldown_sec",
        ):
            default = {
                "feishu_export_window_hours": 8,
                "feishu_auto_sync_min_messages": 20,
                "feishu_auto_sync_cooldown_sec": 1800,
            }[field]
            updates[env_key] = str(config.get(field, default))
        elif field == "feishu_export_trigger_keywords":
            updates[env_key] = keywords_value
        else:
            updates[env_key] = config.get(field)
    return updates


def _detect_wxid_and_db_path():
    """Auto-detect WeChat wxid and database path from common locations.

    Respects WECHAT_DATA_DIR env var as a custom base dir (scanned first).
    """
    import os as _os

    candidates: list[Path] = []

    # 1. Custom path from env (highest priority)
    custom_dir = _os.environ.get("WECHAT_DATA_DIR", "").strip()
    if custom_dir:
        custom = Path(custom_dir)
        if custom.exists() and custom.is_dir():
            candidates.append(custom)

    # 2. Default locations
    candidates += [
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
        "DEEPSEEK_BASE_URL": _onboarding_data.get("deepseek_base_url", "https://api.deepseek.com"),
        "DEEPSEEK_MODEL": _onboarding_data.get("deepseek_model", "deepseek-v4-flash"),
        "ANTHROPIC_API_KEY": _onboarding_data.get("anthropic_api_key", ""),
        "ANTHROPIC_BASE_URL": _onboarding_data.get("anthropic_base_url", "https://api.anthropic.com"),
        "SUMMARIZE_MODEL": _onboarding_data.get("summarize_model", "claude-haiku-4-5-20251001"),
        "WECHAT_BACKEND": _onboarding_data.get("wechat_backend", "wcdb"),
        "WECHAT_GROUPS": _onboarding_data.get("wechat_groups", "*"),
        "BOT_DISPLAY_NAME": _onboarding_data.get("bot_display_name", "群聊小助手"),
        "PROACTIVE_ENABLED": str(_onboarding_data.get("proactive_enabled", False)).lower(),
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


def _list_dir_entries(target: Path) -> list[dict]:
    """List directory entries for the filesystem browser API.

    Returns only directories (the user is browsing for parent dir of wxid_*).
    Sorted: directories first, then alphabetically.
    """
    entries = []
    try:
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if child.name.startswith(".") or child.name.startswith("$"):
                continue  # skip hidden/system entries
            entries.append({
                "name": child.name,
                "path": str(child),
                "is_dir": child.is_dir(),
            })
    except PermissionError:
        pass
    return entries


def _read_recent_logs():
    """Read the last 500 lines from the bot log file. Returns JSON-serializable list.

    Log format: ``YYYY-MM-DD HH:MM:SS [LEVEL] module: message``
    (configured in src/utils/logging_config.py).
    """
    import re
    # CWD is set to app home by desktop.py; relative path works for both
    # frozen (EXE dir) and dev (project root) modes.
    log_path = Path("data/bot.log")
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


def _can_import(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


def _platform_dependency_report(system_name=None, import_checker=None, command_checker=None):
    """Return platform-aware dependency diagnostics for onboarding."""
    import platform
    import shutil

    system = system_name or platform.system()
    import_checker = import_checker or _can_import
    command_checker = command_checker or shutil.which

    req_mapping = {
        "dotenv": "python-dotenv",
        "anthropic": "anthropic",
        "openai": "openai",
        "pydantic": "pydantic",
        "webview": "pywebview",
        "PIL": "Pillow",
        "psutil": "psutil",
        "pyperclip": "pyperclip",
    }
    if system == "Windows":
        req_mapping.update({
            "uiautomation": "uiautomation",
            "win32api": "pywin32",
            "comtypes": "comtypes",
        })

    missing_reqs = []
    ddgs_ok = import_checker("ddgs") or import_checker("duckduckgo_search")
    if not ddgs_ok:
        missing_reqs.append("ddgs")

    for mod, pkg in req_mapping.items():
        if not import_checker(mod):
            missing_reqs.append(pkg)

    if system == "Darwin":
        for command in ("osascript", "pbcopy"):
            if not command_checker(command):
                missing_reqs.append(command)

    ok = len(missing_reqs) == 0
    value = "所有依赖已安装" if ok else f"缺少依赖: {', '.join(missing_reqs)}"
    return {"ok": ok, "value": value, "missing": missing_reqs}


def _platform_wechat_report(system_name=None):
    """Return a platform-aware WeChat process status."""
    import os as _os
    import platform
    import subprocess

    system = system_name or platform.system()
    if system == "Darwin":
        app_name = _os.getenv("MAC_WECHAT_APP_NAME", "WeChat")
        try:
            result = subprocess.run(
                ["pgrep", "-x", app_name],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                pid = result.stdout.strip().splitlines()[0]
                return {"ok": True, "value": f"微信运行中 (PID {pid})", "error": None}
            return {"ok": False, "value": "微信未运行", "error": "请启动 macOS 微信并授权辅助功能权限"}
        except Exception as e:
            return {"ok": False, "value": f"微信检测出错: {e}", "error": str(e)}

    try:
        from src.wechat.native.injector import _find_wechat_pid
        wx_pid, wx_name = _find_wechat_pid()
        wx_ok = wx_pid is not None
        wx_val = f"微信运行中 (PID {wx_pid})" if wx_ok else "微信未运行"
        return {"ok": wx_ok, "value": wx_val, "error": None if wx_ok else "请登录微信电脑端"}
    except Exception as e:
        return {"ok": False, "value": f"微信检测出错: {e}", "error": str(e)}


def _macos_wechat_diagnostics(system_name=None, automation=None):
    """Run macOS WeChat permission diagnostics from this process identity."""
    import platform

    system = system_name or platform.system()
    if system != "Darwin":
        return {
            "ok": False,
            "skipped": True,
            "error": "macOS diagnostics are only available on Darwin",
        }

    try:
        if automation is None:
            from src.wechat.mac_ui_backend import MacUIAutomation

            automation = MacUIAutomation()
        return automation.diagnose_access()
    except Exception as exc:
        logger.exception("macOS WeChat diagnostics failed")
        return {
            "ok": False,
            "skipped": False,
            "error": str(exc),
        }


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
_voice_downloads: dict[str, dict] = {}  # model → {active, msg}


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
    "proactive_enabled": False,
    "sticky_mention_enabled": True,
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
    from src.config import PROJECT_ROOT

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

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
        if self.path in ("/api/config", "/api/config/import", "/api/start", "/api/stop",
                         "/api/nicknames",
                         "/api/welcome/templates",
                         "/api/onboarding/reset",
                         "/api/onboarding/step1", "/api/onboarding/step2",
                         "/api/onboarding/step3", "/api/onboarding/step4",
                         "/api/sandbox/test",
                         "/api/lots",
                         "/api/voice/download-model"):
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
            from src.config import _decode_wechat_groups  # noqa: F811 - needed before use (scoping)
            env_path = _find_or_create_env()
            raw = {}
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        raw[k.strip()] = v.strip()
            config_data = {
                "ai_backend": raw.get("AI_BACKEND", "deepseek"),
                "deepseek_api_key": raw.get("DEEPSEEK_API_KEY", ""),
                "deepseek_base_url": raw.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                "deepseek_model": raw.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                "anthropic_api_key": raw.get("ANTHROPIC_API_KEY", ""),
                "anthropic_base_url": raw.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
                "summarize_model": raw.get("SUMMARIZE_MODEL", "claude-haiku-4-5-20251001"),
                "bot_display_name": raw.get("BOT_DISPLAY_NAME", ""),
                "wechat_backend": raw.get("WECHAT_BACKEND", "wcdb"),
                "wechat_groups": _decode_wechat_groups(raw.get("WECHAT_GROUPS", "*")),
                "fun_enabled": raw.get("FUN_ENABLED", "true").lower() == "true",
                "proactive_enabled": raw.get("PROACTIVE_ENABLED", "false").lower() == "true",
                "proactive_rate_window_sec": int(raw.get("PROACTIVE_RATE_WINDOW_SEC", "120")),
                "proactive_rate_quiet": float(raw.get("PROACTIVE_RATE_QUIET", "1.5")),
                "proactive_rate_casual": float(raw.get("PROACTIVE_RATE_CASUAL", "4.0")),
                "proactive_rate_lively": float(raw.get("PROACTIVE_RATE_LIVELY", "6.5")),
                "proactive_rate_burst": float(raw.get("PROACTIVE_RATE_BURST", "8.5")),
                "welcome_enabled": raw.get("WELCOME_ENABLED", "false").lower() == "true",
                "sticky_mention_enabled": raw.get("STICKY_MENTION_ENABLED", "true").lower() == "true",
                "sticky_mention_ttl_sec": int(raw.get("STICKY_MENTION_TTL_SEC", "60")),
                "summarize_enabled": raw.get("SUMMARIZE_ENABLED", "true").lower() == "true",
                "fallback_window_hours": int(raw.get("FALLBACK_WINDOW_HOURS", "8")),
                "trigger_keywords": [
                    kw.strip() for kw in raw.get("TRIGGER_KEYWORDS", "").split(",")
                    if kw.strip()
                ],
                "log_level": raw.get("LOG_LEVEL", "INFO"),
                "wechat_data_dir": raw.get("WECHAT_DATA_DIR", ""),
                "voice_asr_enabled": raw.get("VOICE_ASR_ENABLED", "false").lower() == "true",
                "voice_asr_backend": raw.get("VOICE_ASR_BACKEND", "local_whisper"),
                "voice_asr_language": raw.get("VOICE_ASR_LANGUAGE", "zh"),
                "voice_openai_api_key": raw.get("VOICE_OPENAI_API_KEY", ""),
                "voice_openai_base_url": raw.get("VOICE_OPENAI_BASE_URL", ""),
                "voice_local_model": raw.get("VOICE_LOCAL_MODEL", "small"),
            }
            config_data.update(_feishu_config_from_raw(raw))
            self.send_json({
                "ok": True,
                "config": config_data,
                "detected_data_dir": _detect_default_data_dir(),
            })
            return

        # ── API: Export config ───────────────────────────────────────
        if self.path == "/api/config/export":
            from datetime import date as _dt_date
            try:
                env_path = _find_or_create_env()
                raw = {}
                if env_path.exists():
                    for line in env_path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            raw[k.strip()] = v.strip()
                export_data = {
                    "ai_backend": raw.get("AI_BACKEND", "deepseek"),
                    "deepseek_api_key": raw.get("DEEPSEEK_API_KEY", ""),
                    "deepseek_base_url": raw.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                    "deepseek_model": raw.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                    "anthropic_api_key": raw.get("ANTHROPIC_API_KEY", ""),
                    "anthropic_base_url": raw.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
                    "summarize_model": raw.get("SUMMARIZE_MODEL", "claude-haiku-4-5-20251001"),
                    "bot_display_name": raw.get("BOT_DISPLAY_NAME", ""),
                    "wechat_backend": raw.get("WECHAT_BACKEND", "wcdb"),
                    "wechat_groups": raw.get("WECHAT_GROUPS", "*"),
                    "fun_enabled": raw.get("FUN_ENABLED", "true").lower() == "true",
                    "proactive_enabled": raw.get("PROACTIVE_ENABLED", "false").lower() == "true",
                    "proactive_rate_window_sec": int(raw.get("PROACTIVE_RATE_WINDOW_SEC", "120")),
                    "proactive_rate_quiet": float(raw.get("PROACTIVE_RATE_QUIET", "1.5")),
                    "proactive_rate_casual": float(raw.get("PROACTIVE_RATE_CASUAL", "4.0")),
                    "proactive_rate_lively": float(raw.get("PROACTIVE_RATE_LIVELY", "6.5")),
                    "proactive_rate_burst": float(raw.get("PROACTIVE_RATE_BURST", "8.5")),
                    "welcome_enabled": raw.get("WELCOME_ENABLED", "false").lower() == "true",
                    "sticky_mention_enabled": raw.get("STICKY_MENTION_ENABLED", "true").lower() == "true",
                    "sticky_mention_ttl_sec": int(raw.get("STICKY_MENTION_TTL_SEC", "60")),
                    "summarize_enabled": raw.get("SUMMARIZE_ENABLED", "true").lower() == "true",
                    "fallback_window_hours": int(raw.get("FALLBACK_WINDOW_HOURS", "8")),
                    "trigger_keywords": [
                        kw.strip() for kw in raw.get("TRIGGER_KEYWORDS", "").split(",")
                        if kw.strip()
                    ],
                    "log_level": raw.get("LOG_LEVEL", "INFO"),
                    "wechat_data_dir": raw.get("WECHAT_DATA_DIR", ""),
                }
                export_data.update(_feishu_config_from_raw(raw))
                filename = f"webot-config-{_dt_date.today().isoformat()}.json"
                body = json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                logger.exception("Failed to export config")
                self.send_json({"ok": False, "error": str(e)})
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
                else:
                    lines = []
                new_lines = []
                updates = {
                    "DEEPSEEK_API_KEY": config.get("deepseek_api_key"),
                    "DEEPSEEK_BASE_URL": config.get("deepseek_base_url"),
                    "DEEPSEEK_MODEL": config.get("deepseek_model"),
                    "ANTHROPIC_API_KEY": config.get("anthropic_api_key"),
                    "ANTHROPIC_BASE_URL": config.get("anthropic_base_url"),
                    "SUMMARIZE_MODEL": config.get("summarize_model"),
                    "AI_BACKEND": config.get("ai_backend"),
                    "BOT_DISPLAY_NAME": config.get("bot_display_name"),
                    "WECHAT_BACKEND": config.get("wechat_backend"),
                    "WECHAT_GROUPS": config.get("wechat_groups") or "*",
                    "FUN_ENABLED": str(config.get("fun_enabled", True)).lower(),
                    "PROACTIVE_ENABLED": str(config.get("proactive_enabled", False)).lower(),
                    "PROACTIVE_RATE_WINDOW_SEC": str(config.get("proactive_rate_window_sec", 120)),
                    "PROACTIVE_RATE_QUIET": str(config.get("proactive_rate_quiet", 1.5)),
                    "PROACTIVE_RATE_CASUAL": str(config.get("proactive_rate_casual", 4.0)),
                    "PROACTIVE_RATE_LIVELY": str(config.get("proactive_rate_lively", 6.5)),
                    "PROACTIVE_RATE_BURST": str(config.get("proactive_rate_burst", 8.5)),
                    "WELCOME_ENABLED": str(config.get("welcome_enabled", False)).lower(),
                    "STICKY_MENTION_ENABLED": str(config.get("sticky_mention_enabled", True)).lower(),
                    "STICKY_MENTION_TTL_SEC": str(config.get("sticky_mention_ttl_sec", 60)),
                    "SUMMARIZE_ENABLED": str(config.get("summarize_enabled", True)).lower(),
                    "FALLBACK_WINDOW_HOURS": str(config.get("fallback_window_hours", 8)),
                    "TRIGGER_KEYWORDS": ",".join(config.get("trigger_keywords", [])) if config.get("trigger_keywords") else None,
                    "LOG_LEVEL": config.get("log_level"),
                    "WECHAT_DATA_DIR": config.get("wechat_data_dir"),
                    "VOICE_ASR_ENABLED": str(config.get("voice_asr_enabled", False)).lower(),
                    "VOICE_ASR_BACKEND": config.get("voice_asr_backend", "local_whisper"),
                    "VOICE_ASR_LANGUAGE": config.get("voice_asr_language", "zh"),
                    "VOICE_OPENAI_API_KEY": config.get("voice_openai_api_key", ""),
                    "VOICE_OPENAI_BASE_URL": config.get("voice_openai_base_url", ""),
                    "VOICE_LOCAL_MODEL": config.get("voice_local_model", "small"),
                }
                updates.update(_feishu_updates_from_config(config))
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
                for key, val in updates.items():
                    if val is not None:
                        os.environ[key] = str(val)
                self.send_json({
                    "ok": True,
                    "saved": list(seen),
                    "requires_restart": True,
                })
            except Exception as e:
                logger.exception("Failed to save config")
                self.send_json({"ok": False, "error": str(e)})
            return

        # ── API: Import config ─────────────────────────────────────────
        if self.path == "/api/config/import":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len else b"{}"
            try:
                config = json.loads(body)
                # Basic validation: must look like a webot config export
                expected_keys = ['ai_backend', 'deepseek_model', 'wechat_backend']
                has_keys = any(k in config for k in expected_keys)
                if not has_keys:
                    raise ValueError("无效的配置文件格式：缺少必需字段")
                env_path = _find_or_create_env()
                if env_path.exists():
                    lines = env_path.read_text(encoding="utf-8").splitlines()
                else:
                    lines = []
                updates = {
                    "DEEPSEEK_API_KEY": config.get("deepseek_api_key"),
                    "DEEPSEEK_BASE_URL": config.get("deepseek_base_url"),
                    "DEEPSEEK_MODEL": config.get("deepseek_model"),
                    "ANTHROPIC_API_KEY": config.get("anthropic_api_key"),
                    "ANTHROPIC_BASE_URL": config.get("anthropic_base_url"),
                    "SUMMARIZE_MODEL": config.get("summarize_model"),
                    "AI_BACKEND": config.get("ai_backend"),
                    "BOT_DISPLAY_NAME": config.get("bot_display_name"),
                    "WECHAT_BACKEND": config.get("wechat_backend"),
                    "WECHAT_GROUPS": config.get("wechat_groups") or "*",
                    "FUN_ENABLED": str(config.get("fun_enabled", True)).lower(),
                    "PROACTIVE_ENABLED": str(config.get("proactive_enabled", False)).lower(),
                    "PROACTIVE_RATE_WINDOW_SEC": str(config.get("proactive_rate_window_sec", 120)),
                    "PROACTIVE_RATE_QUIET": str(config.get("proactive_rate_quiet", 1.5)),
                    "PROACTIVE_RATE_CASUAL": str(config.get("proactive_rate_casual", 4.0)),
                    "PROACTIVE_RATE_LIVELY": str(config.get("proactive_rate_lively", 6.5)),
                    "PROACTIVE_RATE_BURST": str(config.get("proactive_rate_burst", 8.5)),
                    "WELCOME_ENABLED": str(config.get("welcome_enabled", False)).lower(),
                    "STICKY_MENTION_ENABLED": str(config.get("sticky_mention_enabled", True)).lower(),
                    "STICKY_MENTION_TTL_SEC": str(config.get("sticky_mention_ttl_sec", 60)),
                    "SUMMARIZE_ENABLED": str(config.get("summarize_enabled", True)).lower(),
                    "FALLBACK_WINDOW_HOURS": str(config.get("fallback_window_hours", 8)),
                    "TRIGGER_KEYWORDS": ",".join(config.get("trigger_keywords", [])) if config.get("trigger_keywords") else None,
                    "LOG_LEVEL": config.get("log_level"),
                    "WECHAT_DATA_DIR": config.get("wechat_data_dir"),
                    "VOICE_ASR_ENABLED": str(config.get("voice_asr_enabled", False)).lower(),
                    "VOICE_ASR_BACKEND": config.get("voice_asr_backend", "local_whisper"),
                    "VOICE_ASR_LANGUAGE": config.get("voice_asr_language", "zh"),
                    "VOICE_OPENAI_API_KEY": config.get("voice_openai_api_key", ""),
                    "VOICE_OPENAI_BASE_URL": config.get("voice_openai_base_url", ""),
                    "VOICE_LOCAL_MODEL": config.get("voice_local_model", "small"),
                }
                updates.update(_feishu_updates_from_config(config))
                new_lines = []
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
                # Atomic write
                tmp_path = env_path.with_suffix(".tmp")
                tmp_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                os.replace(tmp_path, env_path)
                # Update in-process environment
                for key, val in updates.items():
                    if val is not None:
                        os.environ[key] = str(val)
                self.send_json({
                    "ok": True,
                    "imported": list(seen),
                    "requires_restart": True,
                })
            except ValueError as e:
                self.send_json({"ok": False, "error": str(e)})
            except Exception as e:
                logger.exception("Failed to import config")
                self.send_json({"ok": False, "error": str(e)})
            return

        # ── API: Get nickname groups ─────────────────────────────────────
        if self.path == "/api/nicknames/groups":
            try:
                from src.config import find_env_file, _decode_wechat_groups
                env_path = find_env_file()
                import sqlite3

                # Resolve group names same way as wcdb_backend: read env, match sessions
                groups_raw = "*"
                if env_path and env_path.exists():
                    for line in env_path.read_text(encoding="utf-8").splitlines():
                        if line.strip().startswith("WECHAT_GROUPS="):
                            groups_raw = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                            break
                groups_raw = _decode_wechat_groups(groups_raw)

                db_path = "data/messages.db"
                if env_path and env_path.exists():
                    for line in env_path.read_text(encoding="utf-8").splitlines():
                        if line.strip().startswith("DB_PATH="):
                            db_path = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                            break

                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row

                # ── Load persisted chat_id -> group display names ────────
                # Written by WcdbBackend._save_group_names() when the bot
                # resolves group names from WeChat's session DB via WCDB DLL.
                group_names_path = Path("data/group_names.json")
                group_names: dict[str, str] = {}
                if group_names_path.exists():
                    try:
                        group_names = json.loads(
                            group_names_path.read_text(encoding="utf-8")
                        )
                    except (json.JSONDecodeError, OSError):
                        pass
                # ──────────────────────────────────────────────────────────

                groups = []
                if not _messages_table_exists(conn):
                    conn.close()
                    self.send_json({"ok": True, "groups": groups})
                    return
                if groups_raw == "*" or not groups_raw:
                    # All groups: distinct chat_ids from messages
                    rows = conn.execute(
                        "SELECT DISTINCT chat_id FROM messages WHERE chat_id LIKE '%@chatroom%' ORDER BY chat_id"
                    ).fetchall()
                    for row in rows:
                        chat_id = row["chat_id"]
                        cnt_row = conn.execute(
                            "SELECT COUNT(DISTINCT sender_id) as cnt FROM messages WHERE chat_id=?",
                            (chat_id,),
                        ).fetchone()
                        groups.append({
                            "chat_id": chat_id,
                            "group_name": group_names.get(chat_id, chat_id),
                            "member_count": cnt_row["cnt"] if cnt_row else 0,
                        })
                else:
                    # Specific group names — match against known chat_ids
                    wanted = [g.strip() for g in groups_raw.split(",") if g.strip()]
                    # Get all chatroom IDs from messages
                    all_chats = conn.execute(
                        "SELECT DISTINCT chat_id FROM messages WHERE chat_id LIKE '%@chatroom%'"
                    ).fetchall()
                    all_ids = [r["chat_id"] for r in all_chats]
                    for name in wanted:
                        # Try exact match first, then substring
                        chat_id = name
                        for cid in all_ids:
                            if name.lower() in cid.lower():
                                chat_id = cid
                                break
                        cnt_row = conn.execute(
                            "SELECT COUNT(DISTINCT sender_id) as cnt FROM messages WHERE chat_id=?",
                            (chat_id,),
                        ).fetchone()
                        # Resolve display name from persisted mapping, fallback to configured name
                        display_name = group_names.get(chat_id) or name
                        groups.append({
                            "chat_id": chat_id,
                            "group_name": display_name,
                            "member_count": cnt_row["cnt"] if cnt_row else 0,
                        })

                conn.close()
                self.send_json({"ok": True, "groups": groups})
            except Exception as e:
                logger.exception("Failed to list nickname groups")
                self.send_json({"ok": False, "error": str(e)})
            return

        # ── API: Get nicknames for a group ────────────────────────────────
        if self.path.startswith("/api/nicknames") and self.command == "GET":
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if not parsed.path.startswith("/api/nicknames") or parsed.path != "/api/nicknames":
                self.send_json({"ok": False, "error": "not found"})
                return
            try:
                chat_id = params.get("chat_id", [""])[0]
                if not chat_id:
                    self.send_json({"ok": False, "error": "missing chat_id"})
                    return

                from src.nickname import NicknameService
                nicks = NicknameService()
                overrides = nicks.load()

                import sqlite3
                from src.config import load_config
                config = load_config()
                conn = sqlite3.connect(config.db_path)
                conn.row_factory = sqlite3.Row
                if not _messages_table_exists(conn):
                    conn.close()
                    self.send_json({"ok": True, "members": []})
                    return
                rows = conn.execute(
                    "SELECT DISTINCT sender_id, sender_name FROM messages WHERE chat_id=? ORDER BY sender_name",
                    (chat_id,),
                ).fetchall()
                conn.close()

                members = []
                for row in rows:
                    wxid = row["sender_id"]
                    display = row["sender_name"] or wxid
                    members.append({
                        "wxid": wxid,
                        "display_name": display,
                        "nickname": overrides.get(wxid, ""),
                    })

                self.send_json({"ok": True, "members": members})
            except Exception as e:
                logger.exception("Failed to get nicknames")
                self.send_json({"ok": False, "error": str(e)})
            return

        # ── API: Save nickname ────────────────────────────────────────────
        if self.path == "/api/nicknames" and self.command != "GET":
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len else b"{}"
                data = json.loads(body)
                wxid = (data.get("wxid") or "").strip()
                nickname = (data.get("nickname") or "").strip()

                if not wxid:
                    self.send_json({"ok": False, "error": "missing wxid"})
                    return

                from src.nickname import NicknameService
                nicks = NicknameService()
                if nickname:
                    nicks.update(wxid, nickname)
                else:
                    nicks.remove(wxid)

                self.send_json({"ok": True})
            except Exception as e:
                logger.exception("Failed to save nickname")
                self.send_json({"ok": False, "error": str(e)})
            return

        # ── API: Get / Save lots config ───────────────────────────────
        if self.path == "/api/lots":
            if self.command == "GET":
                try:
                    from src.fun import load_lots_config
                    config = load_lots_config()
                    self.send_json({"ok": True, "config": config})
                except Exception as e:
                    logger.exception("Failed to load lots config")
                    self.send_json({"ok": False, "error": str(e)})
            else:
                # POST — save custom lots config
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len else b"{}"
                try:
                    data = json.loads(body)
                    from src.fun import save_lots_config
                    save_lots_config(data)
                    self.send_json({"ok": True})
                except ValueError as e:
                    self.send_json({"ok": False, "error": str(e)})
                except Exception as e:
                    logger.exception("Failed to save lots config")
                    self.send_json({"ok": False, "error": str(e)})
            return

        # ── API: Get / Save welcome templates ─────────────────────────
        if self.path == "/api/welcome/templates":
            if self.command == "GET":
                try:
                    from src.welcome import get_welcome_manager
                    wm = get_welcome_manager()
                    data = wm.load()
                    self.send_json({"ok": True, "data": data})
                except Exception as e:
                    logger.exception("Failed to load welcome templates")
                    self.send_json({"ok": False, "error": str(e)})
            else:
                # POST — save welcome templates + group mappings
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len else b"{}"
                try:
                    data = json.loads(body)
                    from src.welcome import get_welcome_manager
                    wm = get_welcome_manager()
                    wm.save(data)
                    self.send_json({"ok": True})
                except Exception as e:
                    logger.exception("Failed to save welcome templates")
                    self.send_json({"ok": False, "error": str(e)})
            return

        # ── API: Test AI prompt sandbox ──────────────────────────────
        if self.path == "/api/sandbox/test":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len else b"{}"
            try:
                data = json.loads(body)
                message = data.get("message", "").strip()
                sender_name = data.get("sender_name", "张三").strip()
                group_name = data.get("group_name", "技术交流群").strip()
                group_memory = data.get("group_memory", "").strip()
                context_messages = data.get("context_messages", [])

                # Load config
                from dotenv import load_dotenv
                from src.config import find_env_file, load_config
                from src.summarize import create_summarizer

                env_path = find_env_file()
                if env_path:
                    load_dotenv(env_path, override=True)
                else:
                    load_dotenv(override=True)

                config = load_config()

                # Allow overrides from frontend sandbox inputs
                if data.get("ai_backend"):
                    config.ai_backend = data["ai_backend"]
                if data.get("deepseek_api_key"):
                    config.deepseek_api_key = data["deepseek_api_key"]
                if data.get("deepseek_model"):
                    config.deepseek_model = data["deepseek_model"]
                if data.get("anthropic_api_key"):
                    config.anthropic_api_key = data["anthropic_api_key"]
                if data.get("summarize_model"):
                    config.summarize_model = data["summarize_model"]

                # Create summarizer
                summarizer = create_summarizer(config)

                # Call chat
                reply = summarizer.chat(
                    message=message,
                    context_messages=context_messages,
                    requester_name=sender_name,
                    bot_name=config.bot_display_name or "群聊小助手",
                    group_name=group_name,
                    group_memory=group_memory,
                )

                self.send_json({
                    "ok": True,
                    "reply": reply,
                })
            except Exception as e:
                logger.exception("Failed to run sandbox test")
                self.send_json({
                    "ok": False,
                    "error": str(e),
                })
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

        # ── API: macOS WeChat automation diagnostics ─────────────────
        if self.path == "/api/macos/diagnose":
            self.send_json({
                "ok": True,
                "diagnostics": _macos_wechat_diagnostics(),
            })
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

        # ── API: Onboarding diagnostics check ─────────────────────────
        if self.path == "/api/onboarding/diagnose":
            import sys

            # 1. Python check
            python_ok = sys.version_info >= (3, 10)
            python_val = f"Python {sys.version.split()[0]}"

            # 2. Requirements check
            req_report = _platform_dependency_report()

            # 3. WeChat PID check
            wx_report = _platform_wechat_report()

            # 4. .env check
            # In frozen mode, __file__ is inside the read-only _MEIPASS
            # extraction directory. Use PROJECT_ROOT from config.py which
            # correctly resolves to the EXE directory when frozen.
            from src.config import PROJECT_ROOT, find_env_file
            project_root = PROJECT_ROOT
            env_path = find_env_file() or (project_root / ".env")
            env_ok = env_path.exists()
            env_val = "配置文件已存在" if env_ok else "配置文件尚未创建"

            # 5. DB permissions check
            data_dir = project_root / "data"
            db_perm_ok = True
            db_perm_err = None
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
                test_file = data_dir / ".write_test"
                test_file.write_text("test", encoding="utf-8")
                test_file.unlink()
            except Exception as e:
                db_perm_ok = False
                db_perm_err = str(e)

            # Check read permission to WeChat db path if it's set/detected
            db_path = None
            with _onboarding_lock:
                db_path = _onboarding_data.get("db_path")
            if not db_path:
                _, detected_db = _detect_wxid_and_db_path()
                if detected_db:
                    db_path = detected_db

            if db_path:
                db_path_obj = Path(db_path)
                if db_path_obj.exists():
                    try:
                        with open(db_path_obj, "rb") as f:
                            f.read(100)
                    except Exception as e:
                        db_perm_ok = False
                        db_perm_err = f"微信数据库读取失败: {e}"

            db_perm_val = "数据库读写权限正常" if db_perm_ok else f"数据库权限错误: {db_perm_err}"

            self.send_json({
                "ok": True,
                "diagnostics": {
                    "python": {"ok": python_ok, "value": python_val, "error": None},
                    "requirements": req_report,
                    "wechat": wx_report,
                    "env": {"ok": env_ok, "value": env_val, "error": None},
                    "db": {"ok": db_perm_ok, "value": db_perm_val, "error": db_perm_err}
                }
            })
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
                    _onboarding_data["deepseek_base_url"] = data.get("deepseek_base_url", "https://api.deepseek.com")
                    _onboarding_data["deepseek_model"] = data.get("deepseek_model", "deepseek-v4-flash")
                    _onboarding_data["anthropic_api_key"] = data.get("anthropic_api_key", "")
                    _onboarding_data["anthropic_base_url"] = data.get("anthropic_base_url", "https://api.anthropic.com")
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
                    _onboarding_data["fun_enabled"] = data.get("fun_enabled", True)
                    _onboarding_data["proactive_enabled"] = data.get("proactive_enabled", False)
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

        # ── API: Browse filesystem directories ──────────────────────
        if self.path.startswith("/api/browse"):
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            dir_path = params.get("path", [""])[0].strip()
            if not dir_path:
                # No path given — list drives on Windows, home on others
                import platform
                if platform.system() == "Windows":
                    import string
                    drives = []
                    for letter in string.ascii_uppercase:
                        p = Path(f"{letter}:\\")
                        if p.exists():
                            drives.append({"name": f"{letter}:", "path": f"{letter}:\\", "is_dir": True})
                    self.send_json({"ok": True, "entries": drives, "current_path": ""})
                else:
                    home = Path.home()
                    entries = _list_dir_entries(home)
                    self.send_json({"ok": True, "entries": entries, "current_path": str(home)})
                return

            target = Path(dir_path)
            if not target.exists():
                self.send_json({"ok": False, "error": f"路径不存在: {dir_path}"})
                return
            if not target.is_dir():
                self.send_json({"ok": False, "error": "请选择一个目录"})
                return

            try:
                entries = _list_dir_entries(target)
                self.send_json({"ok": True, "entries": entries, "current_path": str(target)})
            except PermissionError:
                self.send_json({"ok": False, "error": "没有权限访问该目录"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)})
            return

        # ── API: Detect WeChat data in a custom directory ──────────
        if self.path == "/api/wechat-data-dir/detect":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len else b"{}"
            try:
                data = json.loads(body)
                dir_path = (data.get("path") or "").strip()
                if not dir_path:
                    self.send_json({"ok": False, "error": "请提供目录路径"})
                    return
                target = Path(dir_path)
                if not target.exists() or not target.is_dir():
                    self.send_json({"ok": False, "error": f"目录不存在: {dir_path}"})
                    return

                # Scan for wxid_* directories
                wxid_dirs = sorted(
                    [d for d in target.iterdir() if d.is_dir() and d.name.startswith("wxid_")],
                    key=lambda d: d.stat().st_mtime, reverse=True,
                )
                accounts = []
                for wxid_dir in wxid_dirs:
                    session_db = wxid_dir / "db_storage" / "session" / "session.db"
                    accounts.append({
                        "wxid": wxid_dir.name,
                        "has_session_db": session_db.exists(),
                        "db_path": str(session_db) if session_db.exists() else "",
                    })

                if accounts:
                    self.send_json({
                        "ok": True,
                        "found": True,
                        "accounts": accounts,
                        "message": f"找到 {len(accounts)} 个微信账号",
                    })
                else:
                    self.send_json({
                        "ok": True,
                        "found": False,
                        "accounts": [],
                        "message": f"在 {dir_path} 中未找到 wxid_* 目录。请确认路径正确。",
                    })
            except Exception as e:
                logger.exception("Failed to detect WeChat data dir")
                self.send_json({"ok": False, "error": str(e)})
            return

        # ── API: Voice model status ────────────────────────────────────
        if self.path.startswith("/api/voice/model-status"):
            try:
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                model = qs.get("model", ["small"])[0]

                # Check HuggingFace cache
                cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
                model_dir = cache_dir / f"models--Systran--faster-whisper-{model}"
                downloaded = False
                if model_dir.exists():
                    snapshots = model_dir / "snapshots"
                    if snapshots.exists() and any(snapshots.iterdir()):
                        downloaded = True
                    else:
                        blobs = model_dir / "blobs"
                        if blobs.exists() and any(blobs.iterdir()):
                            downloaded = True

                dl = _voice_downloads.get(model)
                self.send_json({
                    "ok": True,
                    "downloaded": downloaded,
                    "phase": dl.get("phase", "") if dl else "",  # "downloading" | "installing"
                    "pct": dl.get("pct", 0) if dl else 0,
                    "error": dl.get("error", "") if dl else "",
                    "model": model,
                })
            except Exception as e:
                logger.exception("Voice model-status failed")
                self.send_json({"ok": False, "error": str(e)})
            return

        # ── API: Trigger voice model download ──────────────────────────
        if self.path == "/api/voice/download-model":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len else b"{}"
            try:
                data = json.loads(body)
                model = data.get("model", "small")

                _voice_downloads[model] = {"phase": "downloading", "pct": 0, "error": ""}

                def _run():
                    state = _voice_downloads.setdefault(model, {})
                    try:
                        # ── Phase 1: download via huggingface_hub ──
                        state["phase"] = "downloading"
                        state["pct"] = 0

                        from huggingface_hub import snapshot_download
                        cache = str(Path.home() / ".cache" / "huggingface")
                        repo_id = f"Systran/faster-whisper-{model}"

                        snapshot_download(
                            repo_id=repo_id,
                            cache_dir=cache,
                        )
                        state["pct"] = 90

                        # ── Phase 2: load model into memory ──────
                        state["phase"] = "installing"
                        state["pct"] = 95
                        from faster_whisper import WhisperModel
                        WhisperModel(
                            model, device="cpu", compute_type="int8",
                            download_root=cache,
                        )
                        state["phase"] = "done"
                        state["pct"] = 100
                        state["error"] = ""
                        logger.info("Voice model '%s' ready", model)
                    except Exception as exc:
                        state["phase"] = "error"
                        state["error"] = str(exc).split("\n")[0][:300]
                        logger.exception("Voice model download/install failed")

                import threading
                t = threading.Thread(target=_run, daemon=True)
                t.start()
                self.send_json({"ok": True, "model": model, "message": "下载已在后台启动"})
            except Exception as e:
                _voice_downloads.pop(model, None)
                logger.exception("Voice download-model failed")
                self.send_json({"ok": False, "error": str(e)})
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
