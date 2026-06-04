"""
Desktop application entry point.

Provides a native Windows window with the React dashboard embedded.
Also serves the web UI on localhost for browser/remote access.

Usage:
    python desktop.py           # GUI mode (native window)
    python desktop.py --web     # Web-only mode (no window, server only)
    python desktop.py --tray    # Start minimized to system tray
"""
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def start_bot():
    """Start the WeChat bot in a background thread."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from src.config import load_config
    from src.bot import Bot

    config = load_config()

    # Start web UI server first
    from src.web.server import start_web_server, update_status
    start_web_server()
    update_status(
        wechat_backend=config.wechat_backend,
        ai_backend=config.ai_backend,
    )

    # Start bot
    bot = Bot(config)
    bot.run()


def run_gui():
    """Launch native desktop window with embedded React UI."""
    import webview

    def on_loaded():
        """Called when the webview finishes loading."""
        pass

    # Start bot in background
    bot_thread = threading.Thread(target=start_bot, daemon=True, name="bot-main")
    bot_thread.start()

    # Wait for server to be ready
    time.sleep(2)

    # Create native window
    window = webview.create_window(
        title="WeChat Bot — Dashboard",
        url="http://127.0.0.1:8765",
        width=1200,
        height=800,
        min_size=(900, 600),
        text_select=True,
        confirm_close=True,
    )

    webview.start(on_loaded, window, gui="edgechromium")


def run_web_only():
    """Web-only mode: serve UI, open browser."""
    start_bot()


def run_tray():
    """Start minimized to system tray."""
    import webview
    import pystray
    from PIL import Image, ImageDraw

    # Create a simple tray icon (green circle)
    def create_icon():
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((4, 4, 28, 28), fill=(52, 211, 153))
        draw.ellipse((10, 10, 22, 22), fill=(16, 185, 129))
        return img

    def on_open(_icon, _item):
        webbrowser.open("http://127.0.0.1:8765")

    def on_quit(_icon, _item):
        _icon.stop()
        os._exit(0)

    # Start bot
    bot_thread = threading.Thread(target=start_bot, daemon=True, name="bot-main")
    bot_thread.start()
    time.sleep(2)

    # System tray
    icon = pystray.Icon(
        "wechat_bot",
        create_icon(),
        "WeChat Bot",
        menu=pystray.Menu(
            pystray.MenuItem("Open Dashboard", on_open, default=True),
            pystray.MenuItem("Quit", on_quit),
        ),
    )
    icon.run()


def main():
    if "--web" in sys.argv:
        run_web_only()
    elif "--tray" in sys.argv:
        run_tray()
    else:
        run_gui()


if __name__ == "__main__":
    main()
