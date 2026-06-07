"""macOS dashboard launcher for the experimental mac_hybrid backend.

This entry point is intentionally separate from desktop.py so the Windows
WebView2 + wcdb flow remains unchanged.
"""

import os
import platform
import sys
import time
import webbrowser
import traceback
from pathlib import Path


def _resolve_resource_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parent


def _resolve_app_home() -> Path:
    explicit_home = os.getenv("WEBOT_APP_HOME", "").strip()
    if explicit_home:
        return Path(explicit_home).expanduser().resolve()

    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent

    return Path.home() / "Library" / "Application Support" / "webot"


RESOURCE_ROOT = _resolve_resource_root()
APP_HOME = _resolve_app_home()
MAC_ENV_PATH = APP_HOME / ".env.macos"
DASHBOARD_URL = "http://127.0.0.1:7327"


def _write_crash_log(exc_info: str) -> None:
    try:
        crash_dir = APP_HOME / "data"
        crash_dir.mkdir(parents=True, exist_ok=True)
        with open(crash_dir / "crash.log", "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"Crash at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(exc_info)
            f.write(f"\n{'='*60}\n\n")
    except Exception:
        pass


def ensure_macos_env_file() -> Path:
    """Create a macOS-specific env file and point config loading at it."""
    APP_HOME.mkdir(parents=True, exist_ok=True)
    if not MAC_ENV_PATH.exists():
        MAC_ENV_PATH.write_text(
            "AI_BACKEND=deepseek\n"
            "DEEPSEEK_API_KEY=\n"
            "WECHAT_BACKEND=mac_hybrid\n"
            "MAC_WECHAT_SEND_SHORTCUT=enter\n"
            "BOT_DISPLAY_NAME=群聊小助手\n"
            "WECHAT_GROUPS=*\n"
            "ONBOARDING_DONE=true\n"
            "LOG_LEVEL=INFO\n"
            "LOG_FILE=data/bot.log\n",
            encoding="utf-8",
        )
    os.environ.setdefault("WEBOT_APP_HOME", str(APP_HOME))
    os.environ.setdefault("WEBOT_ENV_FILE", str(MAC_ENV_PATH))
    return MAC_ENV_PATH


def open_dashboard(
    url: str = DASHBOARD_URL,
    *,
    webview_module=None,
    browser_opener=webbrowser.open,
    sleep_func=time.sleep,
) -> None:
    try:
        if webview_module is None:
            import webview as webview_module

        webview_module.create_window(
            title="webot — Dashboard",
            url=url,
            width=1200,
            height=800,
            min_size=(900, 600),
        )
        webview_module.start(gui="cocoa")
    except Exception:
        _write_crash_log(
            "macOS WebView unavailable; falling back to browser.\n"
            + traceback.format_exc()
        )
        browser_opener(url)
        while True:
            sleep_func(1)


def main() -> None:
    if platform.system() != "Darwin":
        print("desktop_mac.py is intended for macOS. Use desktop.py on Windows.")

    ensure_macos_env_file()
    os.chdir(str(APP_HOME))

    if str(RESOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(RESOURCE_ROOT))

    try:
        from src.web.server import start_web_server

        start_web_server()

        ready = False
        for _ in range(30):
            try:
                from urllib.request import urlopen
                urlopen(DASHBOARD_URL, timeout=1)
                ready = True
                break
            except Exception:
                time.sleep(0.5)

        if not ready:
            _write_crash_log("Web server startup timeout (30 attempts)")
            print("Web server startup timeout. Check whether port 7327 is occupied.")
            return

        open_dashboard(DASHBOARD_URL)
    except KeyboardInterrupt:
        pass
    except Exception:
        _write_crash_log(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
