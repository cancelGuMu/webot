"""Managed local chatlog service for macOS WeChat reads."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_CHATLOG_BASE_URL = "http://127.0.0.1:5030"
DEFAULT_CHATLOG_ADDR = "127.0.0.1:5030"


class ChatlogServiceError(RuntimeError):
    """Raised when the managed chatlog service cannot be started."""


class MacChatlogServiceManager:
    """Start the bundled chatlog service if the local HTTP API is down."""

    def __init__(
        self,
        *,
        client,
        base_url: str | None = None,
        app_home: Path | None = None,
        resource_root: Path | None = None,
        data_dir_resolver=None,
        popen_factory=subprocess.Popen,
        sleep_func=time.sleep,
        monotonic_func=time.monotonic,
    ):
        self.client = client
        self.base_url = (base_url or getattr(client, "base_url", "") or DEFAULT_CHATLOG_BASE_URL).rstrip("/")
        self.app_home = Path(app_home).expanduser().resolve() if app_home else _resolve_app_home()
        self.resource_root = Path(resource_root).expanduser().resolve() if resource_root else _resolve_resource_root()
        self.data_dir_resolver = data_dir_resolver or detect_active_data_dir
        self.popen_factory = popen_factory
        self.sleep_func = sleep_func
        self.monotonic_func = monotonic_func
        self._process = None

    def ensure_running(self, timeout: float = 15.0) -> bool:
        """Ensure chatlog is healthy.

        Returns True when this call launched a child process, False when an
        already-running service was reused.
        """
        if self.client.health():
            return False

        binary = find_chatlog_binary(self.resource_root)
        if not binary:
            raise ChatlogServiceError(
                "chatlog-alpha binary not found. Run: python3 tools/macos_chatlog_setup.py build-chatlog"
            )

        data_dir = str(self.data_dir_resolver() or "").strip()
        if not data_dir:
            raise ChatlogServiceError(
                "Could not detect macOS WeChat data dir. Open WeChat, then run diagnose/build-chatlog setup."
            )

        self.app_home.mkdir(parents=True, exist_ok=True)
        log_path = self.app_home / "data" / "chatlog_alpha.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fh = log_path.open("a", encoding="utf-8")

        env = os.environ.copy()
        env["CHATLOG_DATA_DIR"] = data_dir
        env["CHATLOG_HTTP_ADDR"] = chatlog_addr_from_base_url(self.base_url)

        self._process = self.popen_factory(
            [str(binary)],
            cwd=str(self.app_home),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )

        deadline = self.monotonic_func() + timeout
        while self.monotonic_func() < deadline:
            if self.client.health():
                return True
            poll = getattr(self._process, "poll", None)
            if callable(poll) and poll() is not None:
                raise ChatlogServiceError(f"chatlog-alpha exited during startup; see {log_path}")
            self.sleep_func(0.5)

        raise ChatlogServiceError(f"chatlog-alpha did not become healthy; see {log_path}")


def find_chatlog_binary(resource_root: Path | None = None) -> Path | None:
    env_bin = os.getenv("CHATLOG_BIN", "").strip()
    if env_bin:
        path = Path(env_bin).expanduser()
        if _is_executable_file(path):
            return path.resolve()

    root = Path(resource_root).expanduser().resolve() if resource_root else _resolve_resource_root()
    candidates = [root / "tools" / "macos_chatlog" / "chatlog-alpha"]
    for path in candidates:
        if _is_executable_file(path):
            return path.resolve()
    return None


def chatlog_addr_from_base_url(base_url: str) -> str:
    raw = str(base_url or "").strip()
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5030
    return f"{host}:{port}"


def detect_data_dir_from_filesystem() -> str:
    base = (
        Path.home()
        / "Library"
        / "Containers"
        / "com.tencent.xinWeChat"
        / "Data"
        / "Documents"
        / "xwechat_files"
    )
    candidates = []
    for session_db in base.glob("wxid_*/db_storage/session/session.db"):
        try:
            candidates.append((session_db.stat().st_mtime, session_db.parent.parent.parent))
        except OSError:
            continue
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return str(candidates[0][1])


def detect_active_data_dir() -> str:
    pid = detect_wechat_pid()
    if pid:
        output = run_text(["lsof", "-n", "-P", "-p", str(pid)], timeout=20)
        data_dir = parse_data_dir_from_lsof(output)
        if data_dir:
            return data_dir
    return detect_data_dir_from_filesystem()


def detect_wechat_pid() -> int:
    output = run_text(["pgrep", "-x", "WeChat"], timeout=5)
    first = output.strip().splitlines()[0] if output.strip() else ""
    return int(first) if first.isdigit() else 0


def parse_data_dir_from_lsof(output: str) -> str:
    marker = "/db_storage/session/session.db"
    for line in str(output or "").splitlines():
        if marker not in line:
            continue
        path = line.split()[-1]
        if path.endswith(marker):
            return path[: -len(marker)]
    return ""


def run_text(cmd: list[str], timeout: int = 10) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout or ""


def _resolve_resource_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return _project_root()


def _resolve_app_home() -> Path:
    explicit_home = os.getenv("WEBOT_APP_HOME", "").strip()
    if explicit_home:
        return Path(explicit_home).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path.home() / "Library" / "Application Support" / "webot"
    return _project_root()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_executable_file(path: Path) -> bool:
    try:
        return path.is_file() and os.access(path, os.X_OK)
    except OSError:
        return False
