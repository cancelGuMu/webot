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
from urllib.error import URLError
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

    def get_sessions(self, limit: int = 500) -> dict:
        return self._get_json("/api/v1/sessions", {
            "format": "json",
            "limit": str(limit),
        })

    def health(self) -> bool:
        req = Request(self.base_url + "/health", headers={"Accept": "application/json"})
        try:
            with urlopen(req, timeout=min(self.timeout, 2.0)) as resp:
                body = resp.read(512).decode("utf-8", errors="replace")
            return resp.status < 400 and ("ok" in body.lower() or bool(body.strip()))
        except (OSError, URLError):
            return False

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
        service_manager=None,
    ):
        self._bot_name = bot_display_name
        self._groups = groups or []
        self._poll_sec = poll_sec
        self._store = store
        self._client = client or ChatlogClient()
        self._automation = automation or MacUIAutomation()
        self._limit = limit
        self._service_manager = service_manager
        self._service_error = ""
        self._state: dict[str, int] = {}
        self._running = False
        self._seen_ids: set[str] = set()
        self._chat_titles: dict[str, str] = {}
        self._chat_is_group: dict[str, bool] = {}
        self._title_entries: dict[str, dict[str, bool]] = {}
        self._chat_titles_loaded = False
        self._manual_chat_titles = _parse_chat_title_map(os.getenv("MAC_CHAT_TITLE_MAP", ""))
        for username, title in self._manual_chat_titles.items():
            self._remember_chat_session(username, title, str(username).endswith("@chatroom"))

    def start(self, callback: MessageCallback) -> None:
        self._running = True
        logger.info(
            "MacHybridBackend starting (groups=%s, poll=%ss, bot=%r)",
            self._groups, self._poll_sec, self._bot_name,
        )
        self._automation.activate_wechat()
        self._ensure_chatlog_service()
        self._prime_chatlog_state()
        while self._running:
            self.poll_once(callback)
            time.sleep(self._poll_sec)

    def send_text(self, chat_id: str, content: str) -> bool:
        if not content:
            return False
        if not self._chat_titles_loaded:
            self._load_chat_titles()
        if _looks_internal_chat_id(chat_id):
            target = self._resolve_chat_title(chat_id)
        else:
            target = self._chat_titles.get(chat_id, chat_id)
        if not target:
            logger.warning("Refusing to send macOS WeChat reply without a resolved chat target: %s", chat_id)
            return False
        if _looks_internal_chat_id(target or ""):
            logger.warning(
                "Refusing to open macOS WeChat chat with unresolved internal id: chat_id=%s target=%s",
                chat_id,
                target,
            )
            return False
        is_group = self._chat_is_group.get(chat_id, str(chat_id).endswith("@chatroom"))
        prefer_group = self._should_prefer_group_result(chat_id, target)
        if target and not self._automation.open_chat(
            target,
            prefer_group=prefer_group,
            sidebar_index=None,
            expected_title=target,
            expected_is_group=is_group,
            require_group_marker=prefer_group,
        ):
            logger.warning("Failed to open macOS WeChat chat for send: %s", target)
            return False
        sent = self._automation.send_text(content)
        if sent:
            logger.info("Sent macOS WeChat reply to %s via %r", chat_id[:20], target)
        else:
            logger.warning("Failed to send macOS WeChat reply to %s", chat_id[:20])
        return sent

    def stop(self) -> None:
        self._running = False

    def health_status(self) -> str:
        if self._service_error:
            return "chatlog_down"
        return "chatlog_ok" if self._client.health() else "chatlog_down"

    def _ensure_chatlog_service(self) -> None:
        if self._service_manager is None:
            from .mac_chatlog_service import MacChatlogServiceManager

            self._service_manager = MacChatlogServiceManager(client=self._client)
        try:
            started = self._service_manager.ensure_running()
            self._service_error = ""
            if started:
                logger.info("Started managed macOS chatlog service")
        except Exception as exc:
            self._service_error = str(exc)
            logger.warning("Managed macOS chatlog service unavailable: %s", exc)

    def poll_once(self, callback: MessageCallback) -> None:
        try:
            payload = self._client.get_new_messages(self._state, limit=self._limit)
        except Exception as exc:
            logger.warning("Failed to poll chatlog messages: %s", exc)
            return

        self._apply_new_state(payload.get("new_state"))

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

    def _prime_chatlog_state(self) -> None:
        try:
            payload = self._client.get_new_messages(self._state, limit=self._limit)
        except Exception as exc:
            logger.warning("Failed to prime chatlog state: %s", exc)
            return

        self._apply_new_state(payload.get("new_state"))

        messages = payload.get("messages") or []
        if not isinstance(messages, list):
            return

        primed = 0
        for raw in messages:
            if not isinstance(raw, dict):
                continue
            msg = self._message_from_chatlog(raw)
            if not msg:
                continue
            self._seen_ids.add(msg["message_id"])
            primed += 1
        logger.info("Primed macOS chatlog state (%s historical messages skipped)", primed)

    def _apply_new_state(self, new_state) -> None:
        if isinstance(new_state, dict):
            self._state = {
                str(k): int(v)
                for k, v in new_state.items()
                if _can_int(v)
            }

    def _message_from_chatlog(self, raw: dict) -> dict | None:
        content = str(raw.get("content") or "").strip()
        if not content:
            return None

        username = str(raw.get("username") or raw.get("chat_id") or raw.get("chat") or "").strip()
        group_name = str(raw.get("chat") or username or "当前聊天").strip()
        if not username:
            username = group_name
        is_group = _to_bool(raw.get("is_group")) or str(username).endswith("@chatroom")
        configured_title = self._configured_group_title_for(username, group_name) if is_group else None
        if configured_title:
            group_name = configured_title
        elif _looks_internal_chat_id(group_name):
            group_name = self._resolve_chat_title(username) or group_name
        self._remember_chat_session(username, group_name, is_group)

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
            "is_group": is_group,
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

    def _resolve_chat_title(self, username: str) -> str | None:
        manual = self._manual_chat_titles.get(username, "")
        if manual and not _looks_internal_chat_id(manual):
            return manual
        title = self._chat_titles.get(username, "")
        configured = self._configured_group_title_for(username, title)
        if configured:
            return configured
        if title and not _looks_internal_chat_id(title):
            return title
        if not self._chat_titles_loaded:
            self._load_chat_titles()
        title = self._chat_titles.get(username, "")
        configured = self._configured_group_title_for(username, title)
        if configured:
            return configured
        if title and not _looks_internal_chat_id(title):
            return title
        return None

    def _configured_group_title_for(self, username: str, title: str) -> str | None:
        groups = [
            str(group).strip()
            for group in self._groups
            if str(group).strip() and str(group).strip().lower() not in {"*", "all"}
        ]
        groups = [group for group in groups if not _looks_internal_chat_id(group)]
        if not groups:
            return None

        username = str(username or "").strip()
        if username:
            direct = [group for group in groups if group == username]
            if len(direct) == 1:
                return direct[0]

        normalized_title = _normalize_chat_title(title)
        if normalized_title and not _looks_internal_chat_id(title):
            matches = [
                group for group in groups
                if normalized_title in _normalize_chat_title(group)
                or _normalize_chat_title(group) in normalized_title
            ]
            if len(matches) == 1:
                return matches[0]

        if len(groups) == 1:
            return groups[0]
        return None

    def _load_chat_titles(self) -> None:
        get_sessions = getattr(self._client, "get_sessions", None)
        if not callable(get_sessions):
            return
        try:
            payload = get_sessions()
        except Exception as exc:
            logger.warning("Failed to load chatlog sessions for title map: %s", exc)
            return
        sessions = payload.get("sessions") if isinstance(payload, dict) else None
        if not isinstance(sessions, list):
            return
        for index, item in enumerate(sessions):
            if not isinstance(item, dict):
                continue
            username = str(item.get("username") or "").strip()
            title = str(
                item.get("chat")
                or item.get("display")
                or item.get("nickname")
                or "",
            ).strip()
            if username and title and not _looks_internal_chat_id(title):
                if username in self._manual_chat_titles:
                    continue
                self._remember_chat_session(username, title, _session_is_group(item, username))
        self._chat_titles_loaded = True

    def _remember_chat_session(self, username: str, title: str, is_group: bool) -> None:
        if not username:
            return
        if title:
            self._chat_titles[username] = title
        self._chat_is_group[username] = bool(is_group)
        if title and not _looks_internal_chat_id(title):
            self._title_entries.setdefault(title, {})[username] = bool(is_group)

    def _should_prefer_group_result(self, username: str, title: str) -> bool:
        if not title or _looks_internal_chat_id(title):
            return False
        is_group = self._chat_is_group.get(username, str(username).endswith("@chatroom"))
        if not is_group:
            return False
        entries = self._title_entries.get(title, {})
        has_group = any(entries.values())
        has_private = any(not value for value in entries.values())
        return has_group and has_private


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


def _looks_internal_chat_id(value: str) -> bool:
    value = str(value or "").strip()
    return value.endswith("@chatroom") or value.startswith("wxid_")


def _normalize_chat_title(value: str) -> str:
    return "".join(str(value or "").strip().split()).lower()


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _parse_chat_title_map(raw: str) -> dict[str, str]:
    raw = str(raw or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        return {
            str(key).strip(): str(value).strip()
            for key, value in data.items()
            if str(key).strip() and str(value).strip()
        }

    result: dict[str, str] = {}
    for item in raw.replace("\n", ",").split(","):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            key, value = item.split("=", 1)
        elif ":" in item:
            key, value = item.split(":", 1)
        else:
            continue
        key = key.strip()
        value = value.strip()
        if key and value:
            result[key] = value
    return result


def _session_is_group(item: dict, username: str) -> bool:
    chat_type = str(item.get("chat_type") or item.get("type") or "").strip().lower()
    return (
        _to_bool(item.get("is_group"))
        or str(username).endswith("@chatroom")
        or chat_type in {"group", "chatroom", "群聊"}
    )


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
