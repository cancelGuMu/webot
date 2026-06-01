"""Manual probe for WeChat coordinate sending.

This script navigates to the configured group, replaces any draft text with a
marker, performs one send action, and checks WeFlow for the exact marker.
It is intentionally explicit so failures are easy to diagnose.
"""

from __future__ import annotations

import ctypes
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import win32gui

from src.config import load_config
from src.wechat.weflow_backend import WeFlowClient
from src.wechat.window_controller import WeChatWindowController


DEFAULT_GROUP_NAME = "honker233粉丝微信纯享版"


def click(x: int, y: int) -> None:
    ctypes.windll.user32.SetCursorPos(x, y)
    time.sleep(0.05)
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.04)
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)


def resolve_group(config, client: WeFlowClient) -> tuple[str, str]:
    group_name = (
        (config.wechat_groups.split(",")[0].strip() if config.wechat_groups else "")
        or DEFAULT_GROUP_NAME
    )
    for session in client.get_sessions(limit=500):
        display = session.get("displayName", session.get("nickname", ""))
        username = session.get("username", session.get("talker", ""))
        if username and (group_name in display or display in group_name):
            return group_name, username
    raise RuntimeError(f"Could not resolve talker for group: {group_name}")


def recent_hits(client: WeFlowClient, talker: str, marker: str) -> list[dict]:
    return [
        {
            key: msg.get(key)
            for key in ["localId", "createTime", "isSend", "senderUsername", "content"]
        }
        for msg in client.get_messages(talker, limit=100)
        if msg.get("content") == marker
    ]


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "button"
    marker = f"[wechatbot-test] {mode} {datetime.now().strftime('%H:%M:%S')}"

    config = load_config()
    client = WeFlowClient(config.weflow_url, access_token=config.weflow_token)
    group_name, talker = resolve_group(config, client)
    controller = WeChatWindowController()

    hwnd = controller.find_hwnd(force=True)
    if not hwnd:
        print("no hwnd")
        return 2

    print("marker", marker)
    print("group", group_name, "talker", talker)
    print("activate", controller.activate(hwnd), controller.get_foreground_info())
    nav_result = controller.navigate_to_chat(hwnd, group_name)
    if not nav_result:
        print("navigate failed", controller.get_foreground_info())
        return 3
    if type(nav_result) is int:
        hwnd = nav_result

    # Replace any stale draft text.
    controller._send_combo(0x11, 0x41)  # Ctrl+A
    time.sleep(0.1)
    controller._press_key(0x08)  # Backspace
    time.sleep(0.1)
    controller._set_clipboard(marker)
    controller._send_combo(0x11, 0x56)  # Ctrl+V
    time.sleep(0.5)
    print("after paste", controller.get_foreground_info())

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top

    if mode == "enter":
        controller._press_key(0x0D)
    elif mode == "ctrlenter":
        controller._send_combo(0x11, 0x0D)
    elif mode == "alts":
        controller._send_combo(0x12, 0x53)
    else:
        x = left + int(width * 0.925)
        y = top + int(height * 0.935)
        print("click send", x, y, "rect", (left, top, right, bottom))
        click(x, y)

    time.sleep(3)
    hits = recent_hits(client, talker, marker)
    print(json.dumps({"mode": mode, "hits": hits}, ensure_ascii=False, indent=2))
    return 0 if any(hit.get("isSend") == 1 for hit in hits) else 4


if __name__ == "__main__":
    raise SystemExit(main())
