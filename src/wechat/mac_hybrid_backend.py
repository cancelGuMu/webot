"""macOS hybrid WeChat backend.

Read path: local chatlog HTTP service backed by decrypted macOS WeChat DBs.
Write path: existing macOS Accessibility automation from ``mac_ui_backend``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .base import AbstractWeChatBackend, MessageCallback
from .mac_ui_backend import MacUIAutomation

logger = logging.getLogger(__name__)

DEFAULT_CHATLOG_BASE_URL = "http://127.0.0.1:5030"
DEFAULT_POLL_SEC = 1.0
DEFAULT_LIMIT = 200


class ChatlogClient:
    """Small HTTP client for chatlog-style local APIs."""

    def __init__(self, base_url: str | None = None, timeout: float = 5.0):
        self.base_url = (base_url or os.getenv("CHATLOG_BASE_URL") or DEFAULT_CHATLOG_BASE_URL).rstrip("/")
        self.timeout = timeout

    def get_new_messages(self, state: dict[str, int] | None = None,
                         limit: int = DEFAULT_LIMIT) -> dict:
        params = {
            "format": "json",
            "limit": str(limit),
        }
        if state:
            params["state"] = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        return self._get_json("/api/v1/new_messages", params)

    def _get_json(self, path: str, params: dict[str, str]) -> dict:
        url = f"{self.base_url}{path}?{urlencode(params)}"
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw or "{}")
        if not isinstance(data, dict):
            raise ValueError(f"chatlog returned non-object JSON from {path}")
        return data


class MacHybridBackend(AbstractWeChatBackend):
    """Read macOS WeChat messages from chatlog and send with Accessibility."""

    def __init__(
        self,
        bot_display_name: str = "",
        groups: list[str] | None = None,
        poll_sec: float = DEFAULT_POLL_SEC,
        store=None,
        client: Optional[ChatlogClient] = None,
        automation: Optional[MacUIAutomation] = None,
        limit: int = DEFAULT_LIMIT,
    ):
        self._bot_name = bot_display_name
        self._groups = groups or []
        self._poll_sec = poll_sec
        self._store = store
        self._client = client or ChatlogClient()
        self._automation = automation or MacUIAutomation()
        self._limit = limit
        self._state: dict[str, int] = {}
        self._running = False
        self._seen_ids: set[str] = set()
        self._chat_titles: dict[str, str] = {}

    def start(self, callback: MessageCallback) -> None:
        self._running = True
        logger.info(
            "MacHybridBackend starting (groups=%s, poll=%ss, bot=%r)",
            self._groups, self._poll_sec, self._bot_name,
        )
        self._automation.activate_wechat()
        while self._running:
            self.poll_once(callback)
            time.sleep(self._poll_sec)

    def send_text(self, chat_id: str, content: str) -> bool:
        if not content:
            return False
        target = self._chat_titles.get(chat_id, chat_id)
        if target and not self._automation.open_chat(target):
            logger.warning("Failed to open macOS WeChat chat for send: %s", target)
            return False
        return self._automation.send_text(content)

    def stop(self) -> None:
        self._running = False

    def poll_once(self, callback: MessageCallback) -> None:
        try:
            payload = self._client.get_new_messages(self._state, limit=self._limit)
        except Exception as exc:
            logger.warning("Failed to poll chatlog messages: %s", exc)
            return

        new_state = payload.get("new_state")
        if isinstance(new_state, dict):
            self._state = {
                str(k): int(v)
                for k, v in new_state.items()
                if _can_int(v)
            }

        messages = payload.get("messages") or []
        if not isinstance(messages, list):
            return

        for raw in messages:
            if not isinstance(raw, dict):
                continue
            msg = self._message_from_chatlog(raw)
            if not msg or not self._should_monitor(msg):
                continue
            msg_id = msg["message_id"]
            if msg_id in self._seen_ids:
                continue
            self._seen_ids.add(msg_id)

            if self._bot_name and self._bot_name in msg["sender_name"]:
                continue

            reply = callback(msg)
            if reply:
                self.send_text(msg["chat_id"], reply)

    def _message_from_chatlog(self, raw: dict) -> dict | None:
        content = str(raw.get("content") or "").strip()
        if not content:
            return None

        username = str(raw.get("username") or raw.get("chat_id") or raw.get("chat") or "").strip()
        group_name = str(raw.get("chat") or username or "当前聊天").strip()
        if not username:
            username = group_name
        self._chat_titles[username] = group_name

        sender_name = str(raw.get("sender") or raw.get("sender_name") or "unknown").strip() or "unknown"
        timestamp = _to_int(raw.get("timestamp"), default=int(time.time()))
        local_id = str(raw.get("local_id") or raw.get("message_id") or "").strip()
        if local_id:
            msg_id = f"mac-chatlog-{username}-{local_id}"
        else:
            digest = hashlib.sha1(
                f"{username}\0{sender_name}\0{content}\0{timestamp}".encode("utf-8")
            ).hexdigest()
            msg_id = f"mac-chatlog-{digest}"

        return {
            "message_id": msg_id,
            "chat_id": username,
            "group_name": group_name,
            "sender_id": sender_name,
            "sender_name": sender_name,
            "content": content,
            "msg_type": _chatlog_type_to_msg_type(raw.get("type")),
            "timestamp": timestamp,
            "is_at_mentioned": bool(
                self._bot_name
                and (f"@{self._bot_name}" in content or self._bot_name in content)
            ),
            "is_group": _to_bool(raw.get("is_group")) or str(username).endswith("@chatroom"),
        }

    def _should_monitor(self, msg: dict) -> bool:
        if not msg.get("is_group"):
            return False
        groups = [g for g in self._groups if g and g != "*"]
        if not groups:
            return True
        chat_id = str(msg.get("chat_id") or "")
        group_name = str(msg.get("group_name") or "")
        return any(g == chat_id or g == group_name for g in groups)


def _can_int(value) -> bool:
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _chatlog_type_to_msg_type(value) -> int:
    label = str(value or "").strip().lower()
    if not label or label in {"text", "文本"}:
        return 1
    if label in {"image", "img", "图片"}:
        return 3
    if label in {"voice", "语音"}:
        return 34
    if label in {"emoji", "表情"}:
        return 47
    if label in {"link", "file", "app", "引用", "文件"}:
        return 49
    return 1
