"""macOS dashboard launcher for the experimental mac_hybrid backend.

This entry point is intentionally separate from desktop.py so the Windows
WebView2 + wcdb flow remains unchanged.
"""

import os
import platform
import sys
import time
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
MAC_ENV_PATH = PROJECT_ROOT / ".env.macos"


def ensure_macos_env_file() -> Path:
    """Create a macOS-specific env file and point config loading at it."""
    if not MAC_ENV_PATH.exists():
        MAC_ENV_PATH.write_text(
            "AI_BACKEND=deepseek\n"
            "DEEPSEEK_API_KEY=\n"
            "WECHAT_BACKEND=mac_hybrid\n"
            "CHATLOG_BASE_URL=http://127.0.0.1:5030\n"
            "MAC_WECHAT_SEND_SHORTCUT=enter\n"
            "BOT_DISPLAY_NAME=群聊小助手\n"
            "WECHAT_GROUPS=*\n"
            "ONBOARDING_DONE=true\n"
            "LOG_LEVEL=INFO\n"
            "LOG_FILE=data/bot.log\n",
            encoding="utf-8",
        )
    os.environ.setdefault("WEBOT_ENV_FILE", str(MAC_ENV_PATH))
    return MAC_ENV_PATH


def main() -> None:
    if platform.system() != "Darwin":
        print("desktop_mac.py is intended for macOS. Use desktop.py on Windows.")

    ensure_macos_env_file()

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from src.web.server import start_web_server

    start_web_server()

    ready = False
    for _ in range(30):
        try:
            from urllib.request import urlopen
            urlopen("http://127.0.0.1:7327", timeout=1)
            ready = True
            break
        except Exception:
            time.sleep(0.5)

    if not ready:
        print("Web server startup timeout. Run `cd ui && npm run build` first.")
        return

    webbrowser.open("http://127.0.0.1:7327")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
