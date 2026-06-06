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
import time
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

    def __init__(self, app_name: str | None = None, runner=None):
        self._app_name = app_name or os.getenv("MAC_WECHAT_APP_NAME", "WeChat")
        self._runner = runner or self._default_runner

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
        script = f'tell application "{self._escape_applescript(self._app_name)}" to activate'
        return self._run_osascript(script)

    def open_chat(self, chat_name: str) -> bool:
        if not chat_name:
            return False
        copied = self._run(["pbcopy"], input_text=chat_name)
        if not copied:
            return False
        app = self._escape_applescript(self._app_name)
        script = f'''
tell application "{app}" to activate
delay 0.2
tell application "System Events"
  keystroke "f" using command down
  delay 0.2
  keystroke "v" using command down
  delay 0.3
  key code 36
end tell
'''
        return self._run_osascript(script, timeout=8)

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
        copied = self._run(["pbcopy"], input_text=content)
        if not copied:
            return False
        app = self._escape_applescript(self._app_name)
        script = f'''
tell application "{app}" to activate
delay 0.1
tell application "System Events"
  keystroke "v" using command down
  delay 0.1
  key code 36
end tell
'''
        return self._run_osascript(script, timeout=8)

    def _run(self, cmd, input_text=None, timeout=5) -> bool:
        result = self._runner(cmd, input_text=input_text, timeout=timeout)
        if result.returncode != 0:
            logger.warning("macOS command failed (%s): %s", cmd, result.stderr)
            return False
        return True

    def _run_osascript(self, script: str, timeout=5) -> bool:
        return self._run(["osascript", "-e", script], timeout=timeout)

    @staticmethod
    def _escape_applescript(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _escape_jxa(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')


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
