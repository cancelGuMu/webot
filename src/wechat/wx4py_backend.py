"""wx4py backend — WeChat 4.x via UI Automation.

wx4py is a modern replacement for wxauto, targeting WeChat 4.1.x.
It uses UIAutomation under the hood with a cleaner, callback-based API.

Requirements:
    - Windows OS
    - WeChat Desktop 4.1.x logged in, window NOT minimized
    - pip install wx4py

Docs: https://wx4py.biglongxia.com
"""

import logging
import time
from typing import Optional

from wx4py import (
    WeChatClient,
    CallbackHandler,
    MessageEvent,
    ReplyAction,
    __version__ as wx4py_version,
)

# wx4py supported WeChat versions (from docs)
wx4py_wechat_versions = "4.1.7.59, 4.1.8.29"

from .base import AbstractWeChatBackend, MessageCallback
from .helpers import DedupSet, generate_message_id

logger = logging.getLogger(__name__)


class Wx4pyBackend(AbstractWeChatBackend):
    """WeChat backend using wx4py (WeChat 4.1.x UI Automation)."""

    def __init__(self,
                 bot_display_name: str = "",
                 groups: list[str] | None = None,
                 poll_interval_sec: float = 0.1):
        """
        Args:
            bot_display_name: The bot's WeChat display name.
            groups: List of group chat names to monitor. Required.
            poll_interval_sec: Internal poll interval (wx4py default: 0.1).
        """
        self._bot_name = bot_display_name
        self._groups = groups or []
        self._poll_interval = poll_interval_sec
        self._running = False
        self._client: Optional[WeChatClient] = None
        self._processor = None
        self._known_ids = DedupSet(max_size=10000)

    # ── Public API ────────────────────────────────────────────────

    def start(self, callback: MessageCallback) -> None:
        """Start listening for group messages. Blocks until stop() is called."""
        if not self._groups:
            logger.error(
                "No groups configured. Set WECHAT_GROUPS in .env "
                "(comma-separated group names)."
            )
            return

        self._running = True
        self._client = WeChatClient()

        try:
            connected = self._client.connect()
        except Exception as e:
            logger.error(
                f"Failed to connect to WeChat: {e}\n"
                f"wx4py {wx4py_version} supports WeChat {wx4py_wechat_versions}.\n"
                f"Please check:\n"
                f"  1. WeChat Desktop is running and fully logged in\n"
                f"  2. WeChat version matches one of the supported versions\n"
                f"  3. WeChat window is NOT minimized to tray\n"
                f"  4. Try restarting WeChat and run again"
            )
            return

        if not connected:
            logger.error(
                "Failed to connect to WeChat. "
                "Make sure WeChat Desktop is running and logged in."
            )
            return

        # Auto-detect bot name if not provided
        if not self._bot_name:
            try:
                # wx4py may expose self-info via window
                self._bot_name = getattr(
                    self._client.window, "nickname", ""
                ) or ""
                if self._bot_name:
                    logger.info(f"Auto-detected bot name: {self._bot_name}")
            except Exception:
                pass

        logger.info(
            f"Wx4pyBackend started "
            f"(groups={self._groups}, bot_name='{self._bot_name}')"
        )

        # Build the message handler
        def wx4py_handler(event: MessageEvent):
            return self._handle_message(event, callback)

        handler = CallbackHandler(
            callback=wx4py_handler,
            auto_reply=False,  # We control replies via ReplyAction returns
        )

        # Run with retry on UIA errors (window covered, etc.)
        retry_wait = 5
        while self._running:
            try:
                self._processor = self._client.process_groups(
                    groups=self._groups,
                    handlers=[handler],
                    ignore_client_sent=True,
                    block=True,
                    tick=self._poll_interval,
                )
            except KeyboardInterrupt:
                break
            except Exception as e:
                if not self._running:
                    break
                logger.warning(
                    f"UIA error (window may be covered or WeChat busy). "
                    f"Retrying in {retry_wait}s... ({e})"
                )
                time.sleep(retry_wait)
                # Try reconnecting
                try:
                    if not self._client.is_connected:
                        self._client.connect()
                except Exception:
                    pass
                continue
            break

        self.stop()
        logger.info("Wx4pyBackend stopped.")

    def send_text(self, chat_id: str, content: str) -> bool:
        """Send a text message to a chat.

        Note: In wx4py, sending is primarily handled by returning ReplyAction
        from the handler. This method is a fallback for external sends.
        """
        if not self._client or not self._client.is_connected:
            logger.warning("Cannot send: WeChat not connected")
            return False

        try:
            # Use chat_window to send directly
            sent = self._client.chat_window.send_to(
                chat_id, content, target_type="group"
            )
            return sent
        except Exception as e:
            logger.error(f"Failed to send to {chat_id}: {e}")
            return False

    def stop(self) -> None:
        """Signal the listener loop to stop."""
        self._running = False
        if self._processor:
            try:
                self._processor.stop()
            except Exception:
                pass
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass

    # ── Internal ──────────────────────────────────────────────────

    def _handle_message(self, event: MessageEvent,
                         callback: MessageCallback):
        """Convert a wx4py MessageEvent to our standard format and dispatch."""
        try:
            msg = self._standardize(event)
            if msg is None:
                return None

            # Call the main callback — it returns reply text or None
            reply_text = callback(msg)

            if reply_text:
                return ReplyAction(group=event.group, content=reply_text)
            return None

        except Exception:
            logger.exception("Error handling message")
            return None

    def _standardize(self, event: MessageEvent) -> Optional[dict]:
        """Convert a wx4py MessageEvent to our standard message dict.

        Returns None if the message should be skipped.
        """
        content = (event.content or "").strip()
        if not content:
            return None

        timestamp = int(event.timestamp) if event.timestamp else int(time.time())
        group = event.group or ""

        # Extract sender info from raw data if available
        sender_name = "群成员"
        sender_id = ""
        if hasattr(event, 'raw') and event.raw is not None:
            raw = event.raw
            if hasattr(raw, 'sender'):
                sender_name = str(raw.sender or sender_name)
            elif hasattr(raw, 'sender_name'):
                sender_name = str(raw.sender_name or sender_name)
            if hasattr(raw, 'sender_id'):
                sender_id = str(raw.sender_id or "")

        if not sender_id:
            sender_id = sender_name

        # Generate a stable message ID
        msg_id = generate_message_id(group, content, timestamp)

        # Dedup
        if msg_id in self._known_ids:
            return None
        self._known_ids.add(msg_id)

        return {
            "message_id": msg_id,
            "chat_id": group,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "content": content,
            "msg_type": 1,  # wx4py delivers text
            "timestamp": timestamp,
            "is_at_mentioned": event.is_at_me if hasattr(event, 'is_at_me') else False,
            "is_group": True,
        }
