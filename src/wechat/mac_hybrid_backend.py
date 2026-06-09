"""macOS hybrid WeChat backend.

Read path: WeFlow-style local WCDB access keyed by stable ``@chatroom`` ids.
Write path: existing macOS Accessibility automation from ``mac_ui_backend``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from .base import AbstractWeChatBackend, MessageCallback
from .mac_ui_backend import MacUIAutomation
from .mac_weflow_client import MacWeFlowClient

logger = logging.getLogger(__name__)

DEFAULT_POLL_SEC = 1.0
DEFAULT_LIMIT = 200
SENT_TITLE_RE = re.compile(r"Sent macOS WeChat reply to (?P<username>\S+) via '(?P<title>[^']+)'")


class MacHybridBackend(AbstractWeChatBackend):
    """Read macOS WeChat messages from WeFlow WCDB and send with Accessibility."""

    def __init__(
        self,
        bot_display_name: str = "",
        groups: list[str] | None = None,
        poll_sec: float = DEFAULT_POLL_SEC,
        store=None,
        client: Any = None,
        automation: MacUIAutomation | None = None,
        limit: int = DEFAULT_LIMIT,
        config=None,
    ):
        self._bot_name = bot_display_name
        self._groups = groups or []
        self._poll_sec = poll_sec
        self._store = store
        self._client = client or MacWeFlowClient(config=config)
        self._automation = automation or MacUIAutomation()
        self._limit = limit
        self._service_error = ""
        self._state: dict[str, int] = {}
        self._running = False
        self._seen_ids: set[str] = set()
        self._chat_titles: dict[str, str] = {}
        self._chat_is_group: dict[str, bool] = {}
        self._title_entries: dict[str, dict[str, bool]] = {}
        self._last_messages: dict[str, dict] = {}
        self._chat_titles_loaded = False
        self._manual_chat_titles = _parse_chat_title_map(os.getenv("MAC_CHAT_TITLE_MAP", ""))
        self._load_cached_chat_titles()
        for username, title in self._manual_chat_titles.items():
            self._remember_chat_session(
                username,
                title,
                str(username).endswith("@chatroom"),
                force=True,
            )

    def start(self, callback: MessageCallback) -> None:
        self._running = True
        logger.info(
            "MacHybridBackend starting in WeFlow target mode (groups=%s, poll=%ss, bot=%r)",
            self._groups, self._poll_sec, self._bot_name,
        )
        self._automation.activate_wechat()
        self._prime_message_state()
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
        last_msg = self._last_messages.get(chat_id, {})
        configured_target = self._configured_group_title_for(chat_id, target or "")
        if configured_target:
            target = configured_target
        elif self._is_unreliable_group_title(chat_id, target or "", last_msg):
            learned = self._learn_current_visible_group_title(chat_id, last_msg, target or "")
            if learned:
                target = learned
            else:
                logger.warning(
                    "Refusing to search macOS WeChat group with unreliable title: "
                    "chat_id=%s title=%r sender=%r",
                    chat_id,
                    target,
                    last_msg.get("sender_name") or last_msg.get("sender_id") or "",
                )
                return False
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
            self._persist_chat_title(chat_id, target, is_group)
            logger.info("Sent macOS WeChat reply to %s via %r", chat_id[:20], target)
        else:
            logger.warning("Failed to send macOS WeChat reply to %s", chat_id[:20])
        return sent

    def stop(self) -> None:
        self._running = False

    def health_status(self) -> str:
        if self._service_error:
            return "weflow_down"
        return "weflow_ok" if self._client.health() else "weflow_down"

    def poll_once(self, callback: MessageCallback) -> None:
        try:
            payload = self._client.get_new_messages(self._state, limit=self._limit)
        except Exception as exc:
            logger.warning("Failed to poll macOS WeFlow messages: %s", exc)
            return

        self._apply_new_state(payload.get("new_state"))

        messages = payload.get("messages") or []
        if not isinstance(messages, list):
            return

        for raw in messages:
            if not isinstance(raw, dict):
                continue
            msg = self._message_from_source(raw)
            if not msg or not self._should_monitor(msg):
                continue
            msg_id = msg["message_id"]
            if msg_id in self._seen_ids:
                continue
            self._seen_ids.add(msg_id)

            if self._bot_name and self._bot_name in msg["sender_name"]:
                continue

            self._last_messages[msg["chat_id"]] = msg
            reply = callback(msg)
            if reply:
                self.send_text(msg["chat_id"], reply)

    def _prime_message_state(self) -> None:
        try:
            payload = self._client.get_new_messages(self._state, limit=self._limit)
        except Exception as exc:
            logger.warning("Failed to prime macOS WeFlow state: %s", exc)
            return

        self._apply_new_state(payload.get("new_state"))

        messages = payload.get("messages") or []
        if not isinstance(messages, list):
            return

        primed = 0
        for raw in messages:
            if not isinstance(raw, dict):
                continue
            msg = self._message_from_source(raw)
            if not msg:
                continue
            self._seen_ids.add(msg["message_id"])
            primed += 1
        logger.info("Primed macOS WeFlow state (%s historical messages skipped)", primed)

    def _apply_new_state(self, new_state) -> None:
        if isinstance(new_state, dict):
            self._state = {
                str(k): int(v)
                for k, v in new_state.items()
                if _can_int(v)
            }

    def _message_from_source(self, raw: dict) -> dict | None:
        content = str(raw.get("content") or "").strip()
        if not content:
            return None

        # ── System message handling ───────────────────────────────
        # Detect "xxx joined the group" events for welcome feature.
        _JOIN_PATTERN = re.compile(r'"(.+?)"(?:通过.+?)?加入了群聊')
        join_match = _JOIN_PATTERN.search(content)
        new_member_id: str = ""
        is_system_join: bool = False
        if join_match:
            new_member_id = join_match.group(1)
            is_system_join = True
            logger.info(
                "Join event detected: new_member=%s group=%s",
                new_member_id, str(raw.get("chat") or raw.get("username", ""))[:20],
            )

        # Filter other system messages
        if not is_system_join:
            _FILTER_KEYWORDS = (
                "修改群名", "退出了群聊",
                "撤回了一条消息", "被移除", "开启了朋友验证",
                "邀请", "移出了群聊",
            )
            if any(kw in content for kw in _FILTER_KEYWORDS):
                return None

        username = str(raw.get("username") or raw.get("chat_id") or raw.get("chat") or "").strip()
        group_name = str(raw.get("chat") or username or "当前聊天").strip()
        if not username:
            username = group_name
        is_group = _to_bool(raw.get("is_group")) or str(username).endswith("@chatroom")
        sender_name = str(raw.get("sender") or raw.get("sender_name") or "unknown").strip() or "unknown"
        configured_title = self._configured_group_title_for(username, group_name) if is_group else None
        if configured_title:
            group_name = configured_title
        elif _looks_internal_chat_id(group_name):
            group_name = self._resolve_chat_title(username) or group_name
        weak_group_title = _is_unreliable_group_title_value(username, group_name, sender_name, is_group)
        if weak_group_title:
            resolved = self._resolve_chat_title(username)
            if resolved and not self._is_unreliable_group_title(
                username,
                resolved,
                {"sender_name": sender_name, "is_group": is_group},
            ):
                group_name = resolved
        if not weak_group_title or configured_title:
            self._remember_chat_session(username, group_name, is_group)

        timestamp = _to_int(raw.get("timestamp"), default=int(time.time()))
        local_id = str(raw.get("local_id") or raw.get("message_id") or "").strip()
        if local_id:
            msg_id = f"mac-weflow-{username}-{local_id}"
        else:
            digest = hashlib.sha1(
                f"{username}\0{sender_name}\0{content}\0{timestamp}".encode("utf-8")
            ).hexdigest()
            msg_id = f"mac-weflow-{digest}"

        return {
            "message_id": msg_id,
            "chat_id": username,
            "group_name": group_name,
            "sender_id": sender_name,
            "sender_name": sender_name,
            "content": content,
            "msg_type": _source_type_to_msg_type(raw.get("type")),
            "timestamp": timestamp,
            "is_at_mentioned": bool(
                self._bot_name
                and (f"@{self._bot_name}" in content or self._bot_name in content)
            ),
            "is_group": is_group,
            "is_system_join": is_system_join,
            "new_member_id": new_member_id,
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
        if callable(get_sessions):
            try:
                payload = get_sessions()
            except Exception as exc:
                logger.warning("Failed to load macOS WeFlow sessions for title map: %s", exc)
            else:
                sessions = payload.get("sessions") if isinstance(payload, dict) else None
                self._remember_chat_title_items(
                    sessions,
                    username_keys=("username", "name"),
                    title_keys=("chat", "display", "remark", "nickname"),
                    default_is_group=False,
                )

        get_chatrooms = getattr(self._client, "get_chatrooms", None)
        if callable(get_chatrooms):
            try:
                payload = get_chatrooms()
            except Exception as exc:
                logger.debug("Failed to load macOS WeFlow chatrooms for title map: %s", exc)
            else:
                chatrooms = payload.get("chatrooms") if isinstance(payload, dict) else None
                self._remember_chat_title_items(
                    chatrooms,
                    username_keys=("name", "username"),
                    title_keys=("display", "remark", "nickname"),
                    default_is_group=True,
                )

        get_contacts = getattr(self._client, "get_contacts", None)
        if callable(get_contacts):
            try:
                payload = get_contacts()
            except Exception as exc:
                logger.debug("Failed to load macOS WeFlow contacts for title map: %s", exc)
            else:
                contacts = payload.get("contacts") if isinstance(payload, dict) else None
                self._remember_chat_title_items(
                    contacts,
                    username_keys=("username", "name"),
                    title_keys=("display", "remark", "nickname"),
                    default_is_group=False,
                )

        self._chat_titles_loaded = True

    def _remember_chat_title_items(
        self,
        items,
        *,
        username_keys: tuple[str, ...],
        title_keys: tuple[str, ...],
        default_is_group: bool,
    ) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            username = _first_present_text(item, username_keys)
            title = _first_present_text(item, title_keys)
            if not username or not title or _looks_internal_chat_id(title):
                continue
            if username in self._manual_chat_titles:
                continue
            self._remember_chat_session(
                username,
                title,
                default_is_group or _session_is_group(item, username),
            )

    def _remember_chat_session(
        self,
        username: str,
        title: str,
        is_group: bool,
        force: bool = False,
    ) -> None:
        if not username:
            return
        if title:
            existing = self._chat_titles.get(username, "")
            if force or _should_replace_chat_title(existing, title):
                self._chat_titles[username] = title
        self._chat_is_group[username] = bool(is_group)
        remembered = self._chat_titles.get(username, title)
        if remembered and not _looks_internal_chat_id(remembered):
            self._title_entries.setdefault(remembered, {})[username] = bool(is_group)

    def _load_cached_chat_titles(self) -> None:
        for path in _chat_title_cache_paths():
            try:
                if not path.exists():
                    continue
                data = json.loads(path.read_text(encoding="utf-8") or "{}")
            except (OSError, json.JSONDecodeError) as exc:
                logger.debug("Failed to load cached macOS chat titles from %s: %s", path, exc)
                continue
            if not isinstance(data, dict):
                continue
            for username, title in data.items():
                username = str(username).strip()
                title = str(title).strip()
                if username and title and not _looks_internal_chat_id(title):
                    self._remember_chat_session(
                        username,
                        title,
                        str(username).endswith("@chatroom"),
                        force=True,
                    )

        for path in _chat_title_log_paths():
            try:
                if not path.exists():
                    continue
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError as exc:
                logger.debug("Failed to scan macOS chat title log %s: %s", path, exc)
                continue
            for line in lines:
                match = SENT_TITLE_RE.search(line)
                if not match:
                    continue
                username = match.group("username").strip()
                title = match.group("title").strip()
                if username and title and not _looks_internal_chat_id(title):
                    self._remember_chat_session(
                        username,
                        title,
                        str(username).endswith("@chatroom"),
                        force=True,
                    )

    def _persist_chat_title(self, username: str, title: str, is_group: bool) -> None:
        if not is_group or not username or not title or _looks_internal_chat_id(title):
            return
        path = _preferred_chat_title_cache_path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if path.exists():
                loaded = json.loads(path.read_text(encoding="utf-8") or "{}")
                if isinstance(loaded, dict):
                    data = {str(k): str(v) for k, v in loaded.items()}
            data[str(username)] = str(title)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            tmp.replace(path)
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("Failed to persist macOS chat title cache: %s", exc)

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

    def _is_unreliable_group_title(self, username: str, title: str, msg: dict | None) -> bool:
        msg = msg or {}
        is_group = bool(msg.get("is_group")) or self._chat_is_group.get(
            username,
            str(username).endswith("@chatroom"),
        )
        sender = str(msg.get("sender_name") or msg.get("sender_id") or "").strip()
        return _is_unreliable_group_title_value(username, title, sender, is_group)

    def _learn_current_visible_group_title(
        self,
        username: str,
        msg: dict | None,
        weak_title: str,
    ) -> str | None:
        if not str(username or "").endswith("@chatroom") or not msg:
            return None
        title_reader = getattr(self._automation, "read_current_chat_title_candidates", None)
        visible_reader = getattr(self._automation, "read_visible_texts", None)
        if not callable(title_reader) or not callable(visible_reader):
            return None
        try:
            titles = title_reader()
        except Exception as exc:
            logger.debug("Failed to read current macOS WeChat title candidates: %s", exc)
            return None
        title = _best_visible_group_title(
            titles,
            weak_title=weak_title,
            sender=str(msg.get("sender_name") or msg.get("sender_id") or ""),
            bot_name=self._bot_name,
        )
        if not title:
            return None
        try:
            visible_texts = visible_reader()
        except Exception as exc:
            logger.debug("Failed to read current macOS WeChat visible texts: %s", exc)
            return None
        if not _visible_texts_include_message(visible_texts, str(msg.get("content") or "")):
            logger.info(
                "Not learning macOS WeChat group title %r for %s; trigger message is not visible",
                title,
                username,
            )
            return None
        self._remember_chat_session(username, title, True, force=True)
        self._persist_chat_title(username, title, True)
        logger.info("Learned macOS WeChat group title for %s: %r", username, title)
        return title


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


def _first_present_text(item: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def _is_unreliable_group_title_value(
    username: str,
    title: str,
    sender: str,
    is_group: bool,
) -> bool:
    if not is_group and not str(username or "").endswith("@chatroom"):
        return False
    title = str(title or "").strip()
    sender = str(sender or "").strip()
    if not title or _looks_internal_chat_id(title):
        return False
    if sender and _normalize_chat_title(title) == _normalize_chat_title(sender):
        return True
    return False


def _best_visible_group_title(
    titles,
    *,
    weak_title: str = "",
    sender: str = "",
    bot_name: str = "",
) -> str | None:
    reject = {
        _normalize_chat_title(weak_title),
        _normalize_chat_title(sender),
        _normalize_chat_title(bot_name),
    }
    for raw in titles or []:
        title = _clean_wechat_group_title(str(raw or ""))
        normalized = _normalize_chat_title(title)
        if not title or not normalized:
            continue
        if normalized in reject:
            continue
        if _looks_internal_chat_id(title):
            continue
        if _looks_non_title_text(title):
            continue
        return title
    return None


def _clean_wechat_group_title(value: str) -> str:
    title = str(value or "").strip()
    title = re.sub(r"\s*[（(]\d+[）)]\s*$", "", title).strip()
    return title


def _looks_non_title_text(value: str) -> bool:
    normalized = _normalize_chat_title(value)
    if not normalized:
        return True
    if normalized in {"微信", "wechat", "搜一搜", "搜索", "聊天", "通讯录"}:
        return True
    if normalized.startswith("微信号:") or normalized.startswith("微信号："):
        return True
    if normalized.startswith("@"):
        return True
    return False


def _visible_texts_include_message(texts, content: str) -> bool:
    expected = _normalize_chat_title(content)
    if len(expected) < 4:
        return False
    combined = _normalize_chat_title("".join(str(item or "") for item in texts or []))
    return expected in combined


def _should_replace_chat_title(existing: str, incoming: str) -> bool:
    incoming = str(incoming or "").strip()
    existing = str(existing or "").strip()
    if not incoming or _looks_internal_chat_id(incoming):
        return False
    if not existing or _looks_internal_chat_id(existing):
        return True
    old = _normalize_chat_title(existing)
    new = _normalize_chat_title(incoming)
    if not old:
        return True
    if not new:
        return False
    if old in new and len(new) > len(old):
        return True
    if new in old:
        return False
    return False


def _chat_title_cache_paths() -> list[Path]:
    paths: list[Path] = []
    explicit = os.getenv("MAC_CHAT_TITLE_CACHE_FILE", "").strip()
    if explicit:
        paths.append(Path(explicit))
    app_home = os.getenv("WEBOT_APP_HOME", "").strip()
    if app_home:
        paths.append(Path(app_home) / "data" / "group_names.json")
    else:
        paths.append(Path("data") / "group_names.json")
    return _unique_paths(paths)


def _chat_title_log_paths() -> list[Path]:
    paths: list[Path] = []
    app_home = os.getenv("WEBOT_APP_HOME", "").strip()
    if app_home:
        paths.append(Path(app_home) / "data" / "bot.log")
    else:
        paths.append(Path("data") / "bot.log")
    return _unique_paths(paths)


def _preferred_chat_title_cache_path() -> Path | None:
    explicit = os.getenv("MAC_CHAT_TITLE_CACHE_FILE", "").strip()
    if explicit:
        return Path(explicit)
    app_home = os.getenv("WEBOT_APP_HOME", "").strip()
    if app_home:
        return Path(app_home) / "data" / "group_names.json"
    return None


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen = set()
    unique = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


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


def _source_type_to_msg_type(value) -> int:
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
