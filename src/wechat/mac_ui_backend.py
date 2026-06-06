"""macOS WeChat UI automation backend.

This backend is intentionally separate from the Windows WCDB backend. It uses
macOS application automation as an experimental path for running the bot on
Darwin without importing Windows-only modules.
"""

import logging
import hashlib
import json
import os
import subprocess
import tempfile
import time
import ctypes
from ctypes import c_double, c_int64, c_void_p, Structure
from typing import Optional

from .base import AbstractWeChatBackend, MessageCallback

logger = logging.getLogger(__name__)

DEFAULT_POLL_SEC = 1.0


class MacUIAutomation:
    """Thin adapter for macOS UI automation commands.

    The concrete automation behavior is implemented incrementally. Keeping it
    behind this class lets tests inject a fake automation object and keeps the
    backend free of Windows imports.
    """

    def __init__(
        self,
        app_name: str | None = None,
        runner=None,
        clicker=None,
        title_reader=None,
    ):
        self._app_name = app_name or os.getenv("MAC_WECHAT_APP_NAME", "WeChat")
        self._runner = runner or self._default_runner
        self._clicker = clicker or self._core_graphics_click
        self._title_reader = title_reader or self._read_current_header_texts

    @staticmethod
    def _default_runner(cmd, input_text=None, timeout=5):
        return subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def activate_wechat(self) -> bool:
        return self._bring_wechat_frontmost()

    def open_chat(
        self,
        chat_name: str,
        prefer_group: bool = False,
        sidebar_index: int | None = None,
        expected_title: str | None = None,
        expected_is_group: bool = False,
        require_group_marker: bool = False,
    ) -> bool:
        if not chat_name:
            return False
        if _looks_internal_chat_id(chat_name):
            logger.warning("Refusing to search macOS WeChat with internal chat id: %s", chat_name)
            return False
        if not self._bring_wechat_frontmost():
            return False
        if expected_title and self._current_chat_title_matches(
            expected_title,
            expected_is_group=expected_is_group,
            require_group_marker=require_group_marker,
        ):
            return True
        if sidebar_index is not None:
            opened = self._open_sidebar_chat(sidebar_index)
            if opened and expected_title:
                return self._verify_current_chat_title(
                    expected_title,
                    expected_is_group=expected_is_group,
                    require_group_marker=require_group_marker,
                )
            return opened
        if not self._open_existing_chat_from_search(chat_name, prefer_group=prefer_group):
            return False
        if expected_title:
            return self._verify_current_chat_title(
                expected_title,
                expected_is_group=expected_is_group,
                require_group_marker=require_group_marker,
            )
        return True

    def _open_sidebar_chat(self, sidebar_index: int) -> bool:
        if sidebar_index < 0 or sidebar_index > 7:
            logger.warning("WeChat sidebar session index is not visible: %s", sidebar_index)
            return False
        geometry = self._get_wechat_geometry()
        window = self._window_rect(geometry)
        if not window:
            logger.warning("Could not locate WeChat main window for sidebar chat open")
            return False
        x = window["x"] + 227
        y = window["y"] + 110 + (sidebar_index * 68)
        if not self._click_screen(x, y):
            return False
        time.sleep(0.25)
        return True

    def _open_existing_chat_from_search(self, chat_name: str, prefer_group: bool = False) -> bool:
        geometry = self._get_wechat_geometry()
        if self._modal_sheet_rect(geometry):
            if not self._press_escape():
                return False
            time.sleep(0.2)
            geometry = self._get_wechat_geometry()
        window = self._window_rect(geometry)
        if not window:
            logger.warning("Could not locate WeChat main window for existing chat search")
            return False
        if not self._click_screen(window["x"] + 160, window["y"] + 56):
            return False
        time.sleep(0.1)
        if not self._run(["pbcopy"], input_text=chat_name):
            return False
        if not self._paste_clipboard(send=False):
            return False
        time.sleep(0.4)
        if not self._click_screen(window["x"] + 160, self._existing_search_result_y(window, prefer_group)):
            return False
        time.sleep(0.25)
        return True

    @staticmethod
    def _existing_search_result_y(window: dict, prefer_group: bool) -> float:
        return window["y"] + (244 if prefer_group else 176)

    def read_visible_texts(self) -> list[str]:
        app = self._escape_jxa(self._app_name)
        script = f'''
const appName = "{app}";
const se = Application("System Events");
const proc = se.processes.byName(appName);
const values = [];

function add(value) {{
  if (typeof value === "string") {{
    const trimmed = value.trim();
    if (trimmed) values.push(trimmed);
  }}
}}

function walk(node, depth) {{
  if (depth > 8) return;
  try {{ add(node.name()); }} catch (e) {{}}
  try {{ add(node.value()); }} catch (e) {{}}
  try {{
    const children = node.uiElements();
    for (let i = 0; i < children.length; i += 1) {{
      walk(children[i], depth + 1);
    }}
  }} catch (e) {{}}
}}

try {{
  const windows = proc.windows();
  for (let i = 0; i < windows.length; i += 1) {{
    walk(windows[i], 0);
  }}
}} catch (e) {{}}

JSON.stringify([...new Set(values)]);
'''
        result = self._runner(
            ["osascript", "-l", "JavaScript", "-e", script],
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning("macOS visible text read failed: %s", result.stderr)
            return []
        try:
            data = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            logger.warning("macOS visible text read returned non-JSON output")
            return []
        return [str(item).strip() for item in data if str(item).strip()]

    def send_text(self, content: str) -> bool:
        if not content:
            return False
        if not self._bring_wechat_frontmost():
            return False
        geometry = self._get_wechat_geometry()
        window = self._window_rect(geometry)
        if not window:
            logger.warning("Could not locate WeChat main window for send")
            return False
        if not self._click_screen(window["x"] + (window["w"] * 0.68), window["y"] + window["h"] - 44):
            return False
        time.sleep(0.1)
        if not self._run(["pbcopy"], input_text=content):
            return False
        return self._paste_clipboard(send=True)

    def _paste_clipboard(self, send: bool = False) -> bool:
        send_line = self._send_key_script_line() if send else ''
        script = f'''
tell application "System Events"
  keystroke "v" using command down
  delay 0.1
{send_line}
end tell
'''
        return self._run_osascript(script, timeout=8)

    @staticmethod
    def _send_key_script_line() -> str:
        shortcut = os.getenv("MAC_WECHAT_SEND_SHORTCUT", "cmd_enter").strip().lower()
        if shortcut in {"enter", "return"}:
            return "  key code 36"
        return "  key code 36 using command down"

    def _verify_current_chat_title(
        self,
        expected_title: str,
        expected_is_group: bool = False,
        require_group_marker: bool = False,
    ) -> bool:
        texts = self._title_reader()
        if self._texts_match_chat_title(
            texts,
            expected_title,
            expected_is_group=expected_is_group,
            require_group_marker=require_group_marker,
        ):
            return True
        logger.warning(
            "macOS WeChat title verification failed: expected=%r group=%s marker=%s texts=%s",
            expected_title,
            expected_is_group,
            require_group_marker,
            texts[:10],
        )
        return False

    def _current_chat_title_matches(
        self,
        expected_title: str,
        expected_is_group: bool = False,
        require_group_marker: bool = False,
    ) -> bool:
        return self._texts_match_chat_title(
            self._title_reader(),
            expected_title,
            expected_is_group=expected_is_group,
            require_group_marker=require_group_marker,
        )

    def _read_current_header_texts(self) -> list[str]:
        geometry = self._get_wechat_geometry()
        window = self._window_rect(geometry)
        if not window:
            return []

        header = self._chat_header_capture_rect(window)
        x = int(header["x"])
        y = int(header["y"])
        w = int(header["w"])
        h = int(header["h"])
        tmp = tempfile.NamedTemporaryFile(prefix="webot_wechat_header_", suffix=".png", delete=False)
        path = tmp.name
        tmp.close()
        try:
            if not self._run(["screencapture", "-x", f"-R{x},{y},{w},{h}", path], timeout=5):
                return []
            script = '''
import Foundation
import Vision
import AppKit

let path = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: path),
      let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    print("[]")
    exit(0)
}

var texts: [String] = []
let request = VNRecognizeTextRequest { request, error in
    let observations = request.results as? [VNRecognizedTextObservation] ?? []
    for obs in observations {
        guard let top = obs.topCandidates(1).first else { continue }
        let text = top.string.trimmingCharacters(in: .whitespacesAndNewlines)
        if !text.isEmpty {
            texts.append(text)
        }
    }
}
request.recognitionLanguages = ["zh-Hans", "en-US"]
request.recognitionLevel = .accurate
try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
let data = try! JSONSerialization.data(withJSONObject: texts, options: [])
print(String(data: data, encoding: .utf8)!)
'''
            result = self._runner(["swift", "-", path], input_text=script, timeout=20)
            if result.returncode != 0:
                logger.warning("macOS title OCR failed: %s", result.stderr)
                return []
            data = json.loads(result.stdout or "[]")
            return [str(item).strip() for item in data if str(item).strip()]
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("macOS title OCR failed: %s", exc)
            return []
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    @classmethod
    def _texts_match_chat_title(
        cls,
        texts: list[str],
        expected_title: str,
        expected_is_group: bool = False,
        require_group_marker: bool = False,
    ) -> bool:
        expected = cls._normalize_title(expected_title)
        if not expected:
            return False
        for text in texts:
            actual = cls._normalize_title(text)
            if not actual:
                continue
            if require_group_marker:
                if actual.startswith(expected + "(") or actual.startswith(expected + "（"):
                    return True
                continue
            if expected_is_group:
                if actual == expected or actual.startswith(expected + "(") or actual.startswith(expected + "（"):
                    return True
                continue
            if actual == expected:
                return True
        return False

    @staticmethod
    def _normalize_title(value: str) -> str:
        return "".join(str(value or "").strip().split())

    def _bring_wechat_frontmost(self) -> bool:
        if not self._run(["open", "-a", self._app_name], timeout=8):
            return False
        for _ in range(10):
            if self._is_wechat_frontmost():
                return True
            time.sleep(0.2)
        logger.warning("WeChat did not become frontmost after activation")
        return False

    def _is_wechat_frontmost(self) -> bool:
        script = '''
const se = Application("System Events");
const front = se.processes.whose({frontmost: true})();
const name = front.length ? front[0].name() : "";
JSON.stringify({front: name});
'''
        result = self._runner(
            ["osascript", "-l", "JavaScript", "-e", script],
            timeout=3,
        )
        if result.returncode != 0:
            logger.warning("macOS frontmost check failed: %s", result.stderr)
            return False
        try:
            data = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return False
        return data.get("front") in {self._app_name, "WeChat", "微信"}

    def _run(self, cmd, input_text=None, timeout=5) -> bool:
        result = self._runner(cmd, input_text=input_text, timeout=timeout)
        if result.returncode != 0:
            logger.warning("macOS command failed (%s): %s", cmd, result.stderr)
            return False
        return True

    def _run_osascript(self, script: str, timeout=5) -> bool:
        return self._run(["osascript", "-e", script], timeout=timeout)

    def _press_escape(self) -> bool:
        return self._run_osascript(
            '''
tell application "System Events"
  key code 53
end tell
''',
            timeout=3,
        )

    def _get_wechat_geometry(self) -> dict:
        app = self._escape_jxa(self._app_name)
        script = f'''
const appName = "{app}";
const se = Application("System Events");
const proc = se.processes.byName(appName);

function rect(node) {{
  const pos = node.position();
  const size = node.size();
  return {{
    x: Number(pos[0]),
    y: Number(pos[1]),
    w: Number(size[0]),
    h: Number(size[1]),
  }};
}}

let result = {{}};
try {{
  const windows = proc.windows();
  let mainWindow = null;
  for (let i = 0; i < windows.length; i += 1) {{
    try {{
      if (windows[i].name() === "微信") {{
        mainWindow = windows[i];
        break;
      }}
    }} catch (e) {{}}
  }}
  if (!mainWindow && windows.length > 0) mainWindow = windows[0];
  if (mainWindow) {{
    result.window = rect(mainWindow);
    try {{
      const sheets = mainWindow.sheets();
      if (sheets.length > 0) result.sheet = rect(sheets[0]);
    }} catch (e) {{}}
  }}
}} catch (e) {{}}

JSON.stringify(result);
'''
        result = self._runner(
            ["osascript", "-l", "JavaScript", "-e", script],
            timeout=5,
        )
        if result.returncode != 0:
            logger.warning("macOS WeChat geometry read failed: %s", result.stderr)
            return {}
        try:
            data = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            logger.warning("macOS WeChat geometry returned non-JSON output")
            return {}
        return data if isinstance(data, dict) else {}

    def _window_rect(self, geometry: dict) -> dict | None:
        return self._valid_rect(geometry.get("window") if isinstance(geometry, dict) else None)

    def _modal_sheet_rect(self, geometry: dict) -> dict | None:
        return self._valid_rect(geometry.get("sheet") if isinstance(geometry, dict) else None)

    @staticmethod
    def _chat_header_capture_rect(window: dict) -> dict:
        left_offset = min(max(window["w"] * 0.34, 260), 620)
        return {
            "x": window["x"] + left_offset,
            "y": window["y"],
            "w": max(window["w"] - left_offset, 1),
            "h": 140,
        }

    @staticmethod
    def _valid_rect(value) -> dict | None:
        if not isinstance(value, dict):
            return None
        try:
            rect = {
                "x": float(value["x"]),
                "y": float(value["y"]),
                "w": float(value["w"]),
                "h": float(value["h"]),
            }
        except (KeyError, TypeError, ValueError):
            return None
        if rect["w"] <= 0 or rect["h"] <= 0:
            return None
        return rect

    def _click_screen(self, x: float, y: float) -> bool:
        try:
            return bool(self._clicker(x, y))
        except Exception as exc:
            logger.warning("macOS CoreGraphics click failed: %s", exc)
            return False

    @staticmethod
    def _core_graphics_click(x: float, y: float) -> bool:
        class CGPoint(Structure):
            _fields_ = [("x", c_double), ("y", c_double)]

        cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cg.CGEventCreateMouseEvent.argtypes = [c_void_p, c_int64, CGPoint, c_int64]
        cg.CGEventCreateMouseEvent.restype = c_void_p
        cg.CGEventPost.argtypes = [c_int64, c_void_p]
        cg.CFRelease.argtypes = [c_void_p]

        point = CGPoint(float(x), float(y))
        for event_type in (1, 2):
            event = cg.CGEventCreateMouseEvent(None, event_type, point, 0)
            if not event:
                return False
            cg.CGEventPost(0, event)
            cg.CFRelease(event)
            time.sleep(0.05)
        return True

    @staticmethod
    def _escape_applescript(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _escape_jxa(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')


def _looks_internal_chat_id(value: str) -> bool:
    value = str(value or "").strip()
    return value.endswith("@chatroom") or value.startswith("wxid_")


class MacUIBackend(AbstractWeChatBackend):
    """Experimental macOS backend driven by visible WeChat UI text."""

    def __init__(
        self,
        bot_display_name: str = "",
        groups: list[str] | None = None,
        poll_sec: float = DEFAULT_POLL_SEC,
        store=None,
        automation: Optional[MacUIAutomation] = None,
    ):
        self._bot_name = bot_display_name
        self._groups = groups or []
        self._poll_sec = poll_sec
        self._store = store
        self._automation = automation or MacUIAutomation()
        self._running = False
        self._seen_ids: set[str] = set()
        self._current_group = self._default_group_name()

    def start(self, callback: MessageCallback) -> None:
        self._running = True
        logger.info(
            "MacUIBackend starting (groups=%s, poll=%ss, bot=%r)",
            self._groups, self._poll_sec, self._bot_name,
        )
        self._automation.activate_wechat()
        while self._running:
            self.poll_once(callback)
            time.sleep(self._poll_sec)

    def send_text(self, chat_id: str, content: str) -> bool:
        if not content:
            return False
        return self._automation.send_text(content)

    def stop(self) -> None:
        self._running = False

    def health_status(self) -> str:
        return "mac_ui_ok"

    def poll_once(self, callback: MessageCallback) -> None:
        """Poll visible WeChat UI text once and dispatch new lines.

        This testable single-cycle method keeps the long-running start loop
        simple and gives the macOS backend a deterministic unit-test surface.
        """
        for group_name in self._iter_groups():
            if group_name != self._current_group:
                if not self._automation.open_chat(group_name):
                    logger.warning("Failed to open macOS WeChat chat: %s", group_name)
                    continue
                self._current_group = group_name

            for line in self._automation.read_visible_texts():
                msg = self._message_from_line(group_name, line)
                if not msg or msg["message_id"] in self._seen_ids:
                    continue
                self._seen_ids.add(msg["message_id"])
                reply = callback(msg)
                if reply:
                    self.send_text(msg["chat_id"], reply)

    def _iter_groups(self) -> list[str]:
        groups = [g for g in self._groups if g and g != "*"]
        return groups or [self._default_group_name()]

    def _default_group_name(self) -> str:
        return "当前聊天"

    def _message_from_line(self, group_name: str, line: str) -> dict | None:
        text = (line or "").strip()
        if not text:
            return None

        sender_name = "unknown"
        content = text
        if ":" in text:
            sender_name, content = text.split(":", 1)
            sender_name = sender_name.strip() or "unknown"
            content = content.strip()
        if not content:
            return None

        digest = hashlib.sha1(
            f"{group_name}\0{sender_name}\0{content}".encode("utf-8")
        ).hexdigest()
        return {
            "message_id": f"mac-ui-{digest}",
            "chat_id": group_name,
            "group_name": group_name,
            "sender_id": sender_name,
            "sender_name": sender_name,
            "content": content,
            "msg_type": 1,
            "timestamp": int(time.time()),
            "is_at_mentioned": bool(self._bot_name and self._bot_name in content),
            "is_group": True,
        }
