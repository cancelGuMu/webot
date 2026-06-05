"""
Desktop application entry point.

Uses Edge WebView2 (built into Windows 10/11) for a native window.
Falls back to browser if WebView2 is unavailable.

Usage:
    python desktop.py
    webot.exe  (packaged version)
"""
import os
import sys
import threading
import time
import webbrowser
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def _write_crash_log(exc_info: str) -> None:
    """Write crash details to a file for windowed-mode debugging."""
    try:
        crash_dir = PROJECT_ROOT / "data"
        crash_dir.mkdir(parents=True, exist_ok=True)
        crash_path = crash_dir / "crash.log"
        with open(crash_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"Crash at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(exc_info)
            f.write(f"\n{'='*60}\n\n")
    except Exception:
        pass  # last resort — can't even write crash log


def start_bot():
    """Start bot in background thread (signal-safe)."""
    sys.path.insert(0, str(PROJECT_ROOT))

    from src.web.server import (
        start_web_server, update_status,
        register_bot, _bot_exited,
    )
    web_thread = start_web_server()

    try:
        from src.config import load_config
        config = load_config()
        update_status(
            wechat_backend=config.wechat_backend,
            ai_backend=config.ai_backend,
        )
        from src.bot import Bot
        bot = Bot(config)
        # Bot.run() calls _register_backend() during init — no patch needed
        register_bot(thread=threading.current_thread(), backend=None)
        bot.run()
        # Bot exited normally (e.g., no groups found)
        update_status(running=False)
    except SystemExit:
        update_status(running=False)
    except Exception as e:
        update_status(running=False, error=str(e))
        exc_info = traceback.format_exc()
        _write_crash_log(exc_info)
    finally:
        # Always reset bot control state so the user can restart
        # via the web UI (or auto-restart will work next launch)
        _bot_exited()


def main():
    # Check if onboarding is needed
    from src.config import is_onboarding_done
    onboarding_needed = not is_onboarding_done()

    # Always start web server (needed for both onboarding and dashboard)
    from src.web.server import start_web_server
    web_thread = start_web_server()

    # Bot starts STOPPED — user must click "启动机器人" in the UI.
    # This prevents auto-startup races with WeChat login / key availability.

    # Wait for web server
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
        _write_crash_log("Web server startup timeout (30 attempts)")
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "Web 服务器启动超时，请检查端口 7327 是否被占用。\n\n"
                "详情见 data/crash.log",
                "webot — 启动失败",
                0x10,
            )
        except Exception:
            pass
        return

    title = "webot — 初始设置" if onboarding_needed else "webot — Dashboard"

    # Try native WebView2, fall back to browser
    try:
        import webview
        window = webview.create_window(
            title=title,
            url="http://127.0.0.1:7327",
            width=1200,
            height=800,
            min_size=(900, 600),
        )
        webview.start(gui="edgechromium")
    except Exception as e:
        logger_available = False
        try:
            from src.web.server import logger
            logger.warning("WebView2 不可用，正在使用浏览器: %s", e)
            logger_available = True
        except Exception:
            pass
        if not logger_available:
            _write_crash_log(f"WebView2 unavailable: {e}\nFalling back to browser.")
        webbrowser.open("http://127.0.0.1:7327")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
