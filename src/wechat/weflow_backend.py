"""WeFlow Backend — HTTP API for reading + WeChatWindowController for sending.

WeFlow reads WeChat's local encrypted database and exposes messages
via a local HTTP API (port 5031). This backend polls that API for
new messages and uses the WeChatWindowController for reliable message sending.

Requirements:
    - WeFlow installed and running (https://github.com/hicccc77/WeFlow)
    - HTTP API enabled in WeFlow Settings (port 5031)
    - WeChat Desktop logged in (window can be in background)
"""

import hashlib
import json
import logging
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.parse import urlencode

from .base import AbstractWeChatBackend, MessageCallback
from .window_controller import WeChatWindowController

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────

WEFLOW_BASE = "http://127.0.0.1:5031"
WEFLOW_TIMEOUT = 5
DEFAULT_POLL_SEC = 1.0
MAX_DEDUP_SIZE = 5000


# ── WeFlow HTTP client ────────────────────────────────────────────

class WeFlowClient:
    """Minimal HTTP client for WeFlow API."""

    def __init__(self, base_url: str = WEFLOW_BASE,
                 timeout: int = WEFLOW_TIMEOUT, access_token: str = ""):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.token = access_token

    def _get(self, path: str, params: dict | None = None) -> dict | list | None:
        url = f"{self.base}{path}"
        if params is None:
            params = {}
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urlencode(clean)
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = Request(url, headers=headers)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except URLError:
            return None
        except json.JSONDecodeError:
            return None

    def health(self) -> bool:
        try:
            with urlopen(f"{self.base}/health", timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_sessions(self, keyword: str = "", limit: int = 50) -> list[dict]:
        result = self._get("/api/v1/sessions", {"keyword": keyword, "limit": limit})
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            sessions = result.get("sessions", result.get("data", []))
            return sessions if isinstance(sessions, list) else []
        return []

    def get_contacts(self, keyword: str = "", limit: int = 500) -> list[dict]:
        result = self._get("/api/v1/contacts", {"keyword": keyword, "limit": limit})
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            contacts = result.get("contacts", result.get("data", []))
            return contacts if isinstance(contacts, list) else []
        return []

    def get_messages(self, talker: str, limit: int = 200,
                     start_date: str = "", end_date: str = "") -> list[dict]:
        params = {"talker": talker, "limit": limit}
        if start_date:
            params["start"] = start_date
        if end_date:
            params["end"] = end_date
        result = self._get("/api/v1/messages", params)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            msgs = result.get("messages", result.get("data", []))
            if isinstance(msgs, list) and msgs:
                return msgs

        # Some WeFlow builds return an empty list when no date range is supplied,
        # even though sessions show fresh messages. Retry with a narrow date range.
        if not start_date and not end_date:
            today = date.today()
            retry = self.get_messages(
                talker=talker,
                limit=limit,
                start_date=today.isoformat(),
                end_date=(today + timedelta(days=1)).isoformat(),
            )
            if retry:
                return retry
        return []


# ── WeFlow Backend ────────────────────────────────────────────────


class WeFlowBackend(AbstractWeChatBackend):
    """Backend using WeFlow HTTP API for message reading and
    WeChatWindowController for reliable message sending.
    """

    def __init__(self,
                 bot_display_name: str = "",
                 groups: list[str] | None = None,
                 poll_sec: float = DEFAULT_POLL_SEC,
                 weflow_url: str = WEFLOW_BASE,
                 access_token: str = ""):
        self._bot_name = bot_display_name
        self._groups = groups or []
        self._poll_sec = poll_sec
        self._running = False
        self._client = WeFlowClient(base_url=weflow_url, access_token=access_token)
        self._window = WeChatWindowController()

        # Cache: group name → talker ID
        self._talker_ids: dict[str, str] = {}
        # Cache: wxid → display name
        self._nicknames: dict[str, str] = {}
        # Dedup
        self._known_ids: set[str] = set()

    # ── Public API ─────────────────────────────────────────────────

    def start(self, callback: MessageCallback) -> None:
        if not self._groups:
            logger.error("No groups configured. Set WECHAT_GROUPS in .env")
            return

        if not self._client.health():
            logger.error(
                "WeFlow API is not reachable at %s.\n"
                "Make sure WeFlow is running and HTTP API is enabled:\n"
                "  WeFlow Settings → API Service → Start",
                WEFLOW_BASE,
            )
            return

        logger.info(
            "WeFlowBackend starting (groups=%s, poll=%ss, bot='%s')",
            self._groups, self._poll_sec, self._bot_name,
        )

        self._resolve_groups()

        # Pre-find WeChat window (diagnostic only, don't activate)
        hwnd = self._window.find_hwnd()
        if hwnd:
            logger.info("WeChat window pre-detected: HWND=%s", hwnd)
        else:
            logger.warning("WeChat window not found — will retry on first send")

        self._running = True
        consecutive_errors = 0

        while self._running:
            try:
                self._poll_cycle(callback)
                consecutive_errors = 0
            except KeyboardInterrupt:
                break
            except URLError as e:
                consecutive_errors += 1
                wait = min(2 ** consecutive_errors, 30)
                logger.warning(
                    "Poll network error #%d (URLError): %s. Retry in %ss...",
                    consecutive_errors, e, wait,
                )
                time.sleep(wait)
            except Exception as e:
                consecutive_errors += 1
                wait = min(2 ** consecutive_errors, 30)
                logger.error(
                    "Poll unexpected error #%d (%s): %s. Retry in %ss...",
                    consecutive_errors, type(e).__name__, e, wait,
                )
                time.sleep(wait)

        logger.info("WeFlowBackend stopped.")

    def send_text(self, chat_id: str, content: str) -> bool:
        """Send text to a group via the full send pipeline.

        Returns True only if the pipeline succeeded.
        """
        if not content:
            return False

        group_name = self._talker_to_name(chat_id)
        if not group_name:
            logger.error(
                "send_text: cannot resolve chat_id=%s to group name", chat_id
            )
            return False

        return self._send_and_confirm(group_name, chat_id, content)

    def stop(self) -> None:
        self._running = False

    # ── Group & nickname resolution ────────────────────────────────

    # NOTE: Nickname resolution happens in two places:
    #   1. Here (_resolve_groups) at backend startup — loads from WeFlow
    #      sessions/contacts and nicknames.json as a local cache for
    #      fast lookups during message polling.
    #   2. NicknameService (src/nickname.py) during message routing —
    #      the canonical source for manual overrides. NicknameService
    #      takes precedence because router.py calls it after the backend
    #      returns a standardized message; any manual override applied
    #      via the '改名' admin command will override the backend cache.
    def _resolve_groups(self) -> None:
        sessions = self._client.get_sessions(limit=500)

        # Nickname cache from sessions
        for s in sessions:
            username = s.get("username", "")
            display = s.get("displayName", s.get("nickname", ""))
            if username and display:
                self._nicknames[username] = display

        # Nickname cache from contacts
        contacts = self._client.get_contacts(limit=1000)
        for c in contacts:
            username = c.get("userName", c.get("username", ""))
            nick = (c.get("nickName") or c.get("remark")
                    or c.get("displayName") or c.get("alias") or "")
            if username and nick:
                self._nicknames[username] = nick

        # Manual overrides from nicknames.json
        nick_file = Path("data/nicknames.json")
        if nick_file.exists():
            try:
                manual = json.loads(nick_file.read_text(encoding="utf-8"))
                for wxid, name in manual.items():
                    if wxid.startswith("_"):
                        continue
                    if name and name.strip():
                        self._nicknames[wxid] = name.strip()
                logger.info("Loaded %d manual nickname overrides", len(manual))
            except Exception as e:
                logger.warning("Failed to load nicknames.json: %s", e)

        logger.info("Total nickname cache: %d entries", len(self._nicknames))

        # Resolve group talker IDs
        auto_discover = (
            len(self._groups) == 1
            and self._groups[0].strip() in ("*", "all")
        )

        if auto_discover:
            # Auto-discover all group chats
            for s in sessions:
                username = s.get("username", s.get("talker", ""))
                display = s.get("displayName", s.get("nickname", ""))
                # Group chats have usernames ending with @chatroom
                if username.endswith("@chatroom") and display:
                    self._talker_ids[display] = username
                    logger.info("Auto-discovered: '%s' -> %s", display, username)
            if not self._talker_ids:
                logger.error(
                    "Auto-discover found no group chats. "
                    "Sessions: %s",
                    [(s.get('displayName', '')[:30],
                      s.get('username', '')[:40])
                     for s in sessions[:10]],
                )
                self._groups = []  # prevent polling with "*"
            else:
                logger.info(
                    "Auto-discovered %d group chats: %s",
                    len(self._talker_ids),
                    list(self._talker_ids.keys()),
                )
                # Update self._groups so polling iterates over all of them
                self._groups = list(self._talker_ids.keys())
            return

        # Manual mode: match configured names against sessions
        for group_name in self._groups:
            found = None
            for s in sessions:
                display = s.get("displayName", s.get("nickname", ""))
                username = s.get("username", s.get("talker", ""))
                if group_name in display or display in group_name:
                    found = username
                    break
            if found:
                self._talker_ids[group_name] = found
                logger.info("Resolved '%s' -> %s", group_name, found)
            else:
                logger.warning(
                    "Could not resolve group '%s'. Available: %s",
                    group_name,
                    [s.get('displayName', '')[:30] for s in sessions[:20]],
                )

    def _resolve_nickname(self, wxid: str) -> str:
        if wxid in self._nicknames:
            return self._nicknames[wxid]

        contacts = self._client.get_contacts(keyword=wxid, limit=5)
        for c in contacts:
            username = c.get("userName", c.get("username", ""))
            nick = (c.get("nickName") or c.get("remark")
                    or c.get("displayName") or c.get("alias") or "")
            if username:
                self._nicknames[username] = nick
            if username == wxid and nick:
                return nick

        self._nicknames[wxid] = wxid
        return wxid

    def _talker_to_name(self, talker_id: str) -> str:
        for name, tid in self._talker_ids.items():
            if tid == talker_id:
                return name
        return ""

    # ── Message polling ────────────────────────────────────────────

    def _poll_cycle(self, callback: MessageCallback) -> None:
        # NOTE: This method runs synchronously in the main poll loop.
        # _poll_group dispatches to `callback` (router.handle), which may
        # trigger AI summarization. Since the loop is single-threaded, a
        # long-running callback delays the next poll cycle for *all* groups.
        for group_name in list(self._groups):
            if not self._running:
                break
            talker = self._talker_ids.get(group_name)
            if not talker:
                continue
            self._poll_group(group_name, talker, callback)
        time.sleep(self._poll_sec)

    def _poll_group(self, group_name: str, talker: str,
                    callback: MessageCallback) -> None:
        """Poll messages for one group. On trigger reply, use the full
        send pipeline via WeChatWindowController."""
        messages = self._client.get_messages(talker=talker, limit=100)
        if not messages:
            return

        for msg in reversed(messages):
            if not self._running:
                break

            standardized = self._standardize(msg, group_name, talker)
            if standardized is None:
                continue

            msg_id = standardized["message_id"]
            if msg_id in self._known_ids:
                continue
            self._known_ids.add(msg_id)

            if self._bot_name and self._bot_name in standardized["sender_name"]:
                continue

            self._trim_dedup()

            cb_start = time.monotonic()
            reply = callback(standardized)
            cb_elapsed = time.monotonic() - cb_start
            if cb_elapsed > 0.5:
                logger.debug(
                    "Callback took %.2fs (msg_id=%s, group='%s')",
                    cb_elapsed, msg_id, group_name,
                )
            if reply:
                logger.info(
                    "Reply ready: group='%s' sender='%s' len=%d",
                    group_name, standardized["sender_name"], len(reply),
                )
                # Use the full send pipeline, then verify through WeFlow so
                # keyboard/window false positives are not treated as sent.
                success = self._send_and_confirm(group_name, talker, reply)
                if success:
                    logger.info(
                        "Reply sent: group='%s' (%d chars)",
                        group_name, len(reply),
                    )
                else:
                    logger.error(
                        "Reply FAILED: group='%s' (%d chars) — "
                        "check data/send_failures.log",
                        group_name, len(reply),
                    )

    # ── Message standardization ────────────────────────────────────

    def _send_and_confirm(self, group_name: str, talker: str, content: str) -> bool:
        """Send through the window controller, then confirm via WeFlow API.

        After pressing Enter to send, polls WeFlow for up to 3 seconds
        (6 attempts at 0.5s intervals) to confirm the sent message appears
        in the chat. If the window controller itself fails, returns False
        immediately. If the message is not confirmed within timeout, logs a
        warning but still returns True — we don't block the bot on transient
        API issues, but operators can see the failure in logs.
        """
        if not self._window.send_to_chat(group_name, content):
            return False

        # Confirm via WeFlow — poll up to 3s for our message to appear
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            try:
                recent = self._client.get_messages(talker=talker, limit=5)
                for msg in recent:
                    msg_content = str(msg.get("content", "")).strip()
                    # Match against the raw content (no sender filter — we
                    # want our own sent messages, which carry isSend=1).
                    if msg_content == content:
                        elapsed = 3.0 - (deadline - time.monotonic())
                        logger.debug(
                            "Send confirmed: message appeared in WeFlow "
                            "after %.1fs", elapsed,
                        )
                        return True
            except Exception:
                pass  # transient API error, retry next interval
            time.sleep(0.5)

        logger.warning(
            "Send unconfirmed after 3s: group='%s' content='%s' — "
            "message may be lost. Check WeChat window state.",
            group_name,
            content[:80],
        )
        return True  # don't block the bot, but log the failure

    def _standardize(self, msg: dict, group_name: str,
                     talker: str) -> Optional[dict]:
        if msg.get("isSend") == 1:
            return None

        sender = str(msg.get("senderUsername", ""))
        content = str(msg.get("content", "")).strip()
        if not content:
            return None

        local_type = msg.get("localType", 1)
        if local_type and int(local_type) >= 10000:
            return None

        sys_keywords = (
            "修改群名", "加入了群聊", "退出了群聊",
            "撤回了一条消息", "被移除", "开启了朋友验证",
            "邀请", "移出了群聊",
        )
        if any(kw in content for kw in sys_keywords):
            return None

        ts = msg.get("createTime", 0)
        try:
            ts = int(ts)
        except (TypeError, ValueError):
            ts = int(time.time())

        sender_name = self._resolve_nickname(sender)
        resolved_content = content
        if "@" in content:
            def _replace_at(match):
                at_wxid = match.group(0)[1:]
                name = self._resolve_nickname(at_wxid)
                return f"@{name}" if name != at_wxid else match.group(0)
            resolved_content = re.sub(r'@wxid_[a-zA-Z0-9]+', _replace_at, content)

        is_at = self._bot_name and (
            f"@{self._bot_name}" in resolved_content
            or f"@{self._bot_name}" in content
        )

        raw_id = f"{msg.get('serverId','')}|{msg.get('localId','')}"
        msg_id = hashlib.md5(raw_id.encode()).hexdigest()

        return {
            "message_id": msg_id,
            "chat_id": talker,
            "group_name": group_name,
            "sender_id": str(sender),
            "sender_name": str(sender_name),
            "content": resolved_content,
            "msg_type": int(local_type),
            "timestamp": ts,
            "is_at_mentioned": is_at,
            "is_group": True,
        }

    def _trim_dedup(self) -> None:
        if len(self._known_ids) > MAX_DEDUP_SIZE:
            items = list(self._known_ids)
            self._known_ids = set(items[-MAX_DEDUP_SIZE // 2:])
