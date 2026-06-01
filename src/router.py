"""Message router — receives standardized messages and dispatches to handlers.

Routes messages to four response modes:
1. Admin commands: @bot mention + admin wxid → AdminCommandHandler
2. Summary requests: keyword trigger → summarizer.summarize()
3. AI chat: @bot mention (non-summary) → summarizer.chat()
4. Proactive chat: ambient participation via rate-based gating → summarizer.proactive_chat()
"""

import logging
import re
import time
from typing import Optional

from .proactive.gate import ProactiveGate

logger = logging.getLogger(__name__)

# Markdown patterns to strip before sending to WeChat
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_MD_STRIKE = re.compile(r"~~(.+?)~~")
_MD_CODE = re.compile(r"`(.+?)`")


class MessageRouter:
    """Routes incoming WeChat messages to the correct handler.

    Usage:
        router = MessageRouter(
            store=message_store,
            detector=trigger_detector,
            summarizer=summarizer,
            admin_handler=admin_handler,
            nickname_service=nickname_service,
            config=bot_config,
        )

        def on_message(msg: dict) -> str | None:
            return router.handle(msg)
    """

    def __init__(self, store, detector, summarizer, admin_handler,
                 nickname_service, config):
        """
        Args:
            store: MessageStore instance for persistence and queries.
            detector: TriggerDetector instance for keyword matching.
            summarizer: AbstractSummarizer instance for AI responses.
            admin_handler: AdminCommandHandler instance.
            nickname_service: NicknameService instance.
            config: BotConfig instance.
        """
        self._store = store
        self._detector = detector
        self._summarizer = summarizer
        self._admin = admin_handler
        self._nicks = nickname_service
        self._config = config
        self._proactive = ProactiveGate(config)

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Remove markdown formatting characters that WeChat can't render."""
        text = _MD_BOLD.sub(r"\1", text)
        text = _MD_ITALIC.sub(r"\1", text)
        text = _MD_STRIKE.sub(r"\1", text)
        text = _MD_CODE.sub(r"\1", text)
        return text

    def handle(self, msg: dict) -> Optional[str]:
        """Process an incoming group chat message.

        Returns reply text if a reply should be sent, or None.
        """
        # Skip messages from the bot itself (prevent infinite loops)
        if msg["sender_name"] == self._config.bot_display_name:
            return None

        # Always persist the message
        stored = self._store.insert_message(msg)
        if not stored:
            return None  # Duplicate — nothing more to do

        # ── Route: @mention vs proactive ─────────────────────────
        is_at = msg["is_at_mentioned"]

        if is_at:
            # ── @mention path (existing logic) ───────────────────
            logger.info(
                "Trigger in %s by '%s': %s",
                msg["chat_id"], msg["sender_name"], msg["content"][:80],
            )

            clean_content = msg["content"]
            if self._config.bot_display_name:
                at_pattern = f"@{self._config.bot_display_name}"
                clean_content = clean_content.replace(at_pattern, "").strip()
                clean_content = clean_content.replace(
                    f"@{self._config.bot_display_name} ", "",
                ).strip()

            reply: Optional[str] = None

            if clean_content.strip() in ("帮助", "help", "命令"):
                reply = self._admin.handle(clean_content, msg["sender_name"])

            elif clean_content.strip() == "抽签":
                from .fun import draw_lots
                reply = draw_lots(msg["sender_name"])

            if reply is None and (
                self._config.admin_wxid
                and msg["sender_id"] == self._config.admin_wxid
            ):
                reply = self._admin.handle(clean_content, msg["sender_name"])

            if reply is None and self._detector.is_trigger(
                content=clean_content,
                is_at_mentioned=False,
                sender_name=msg["sender_name"],
            ):
                self._store.log_trigger(
                    msg["chat_id"], msg["sender_id"], msg["message_id"],
                )
                reply = self._handle_summary(msg)

            if reply is None and clean_content:
                reply = self._handle_chat(msg, clean_content)

        else:
            # ── Proactive path (rate-based ambient participation) ─
            should_speak, mode, reason = self._proactive.should_speak(msg)
            if should_speak and mode is not None:
                reply = self._handle_proactive_chat(msg, mode)
            else:
                return None

        # ── Strip markdown — WeChat can't render it ──────────────
        return self._strip_markdown(reply) if reply else None

    # ── Summary handler ──────────────────────────────────────────

    def _handle_summary(self, msg: dict) -> str | None:
        """Generate a chat summary for the requester.

        Summary range: from requester's last message to @bot trigger message.
        Requester's own messages are excluded from the summary."""
        trigger_ts = msg.get("timestamp", int(time.time()))
        sender_id = msg["sender_id"]
        sender_name = msg["sender_name"]
        chat_id = msg["chat_id"]

        # Find the requester's last message BEFORE this trigger.
        # Uses the messages table directly so the current @bot trigger
        # is excluded. If the most recent prior message is very close
        # (≤30s) it is skipped in favour of an earlier boundary.
        since_ts = self._store.get_user_previous_timestamp(
            chat_id, sender_id, trigger_ts,
        )
        min_window_sec = self._config.fallback_window_hours * 3600

        if since_ts is None:
            since_ts = int(time.time()) - min_window_sec
            logger.info(
                "No prior message from '%s'. Using fallback: last %dh.",
                sender_name, self._config.fallback_window_hours,
            )
        else:
            # Start AFTER the boundary message (exclude the message itself)
            since_ts += 1

        # Safety net: if the resulting window is smaller than min_window,
        # expand it to guarantee a minimum amount of context for the summary.
        actual_window = trigger_ts - since_ts
        if actual_window < min_window_sec:
            expanded_since = trigger_ts - min_window_sec
            logger.info(
                "Summary window too small (%dmin), expanding to %dh minimum.",
                actual_window // 60, self._config.fallback_window_hours,
            )
            since_ts = expanded_since

        raw_messages = self._store.get_messages_since(
            chat_id, since_ts, until_ts=trigger_ts,
            limit=self._config.max_messages_for_summary,
        )

        if len(raw_messages) == 0:
            logger.info("No messages to summarize for %s", chat_id)
            return f"@{sender_name} 这段时间没有新消息。"

        # Exclude requester's own messages from summary content
        messages = [m for m in raw_messages if m["sender_id"] != sender_id]

        if len(messages) == 0:
            logger.info("Only requester's own messages in window for %s", chat_id)
            return f"@{sender_name} 你上条消息之后还没有人说话～"

        msg_count = len(messages)
        time_span_min = (trigger_ts - since_ts) // 60
        logger.info(
            "Summarizing %d messages (excl. requester) over %dmin for '%s' in %s",
            msg_count, time_span_min, sender_name, chat_id,
        )

        try:
            # Pre-resolve wxids and trim long messages
            for m in messages:
                # Resolve custom nickname from file using sender_id (raw wxid).
                # Using sender_name here is wrong: the WeFlow backend may have
                # already resolved it to a WeChat default name like "暴富蘑菇",
                # and NicknameService can only look up wxid keys, not display names.
                custom = self._nicks.resolve_name(m["sender_id"])
                if custom != m["sender_id"]:
                    m["sender_name"] = custom
                content = self._nicks.resolve_wxids(m.get("content", ""))
                # Trim single messages over 300 chars to save tokens
                if len(content) > 300:
                    content = content[:297] + "..."
                m["content"] = content

            result = self._summarizer.summarize(messages, sender_name)
            reply = self._summarizer.format_summary_for_reply(result, sender_name)
            reply = self._nicks.resolve_wxids(reply)

            logger.info("Summary sent to %s (%d chars)", chat_id, len(reply))
            return reply
        except RuntimeError as e:
            logger.error("Summarization failed: %s", e)
            return (
                f"@{sender_name} "
                f"抱歉，生成总结时出错了，请稍后再试。"
            )

    # ── AI Chat handler ──────────────────────────────────────────

    def _handle_chat(self, msg: dict, clean_content: str) -> str | None:
        """Handle a conversational @bot mention."""
        # Resolve custom nickname from file (via sender_id=wxid),
        # not sender_name which may already be a WeFlow default.
        display_name = self._nicks.resolve_name(msg["sender_id"])
        if display_name == msg["sender_id"]:
            display_name = msg["sender_name"]

        logger.info(
            "AI chat: '%s' asks '%s'",
            display_name, clean_content[:60],
        )

        # Always fetch recent chat context for @mentions.
        # The bot is @mentioned inside a group conversation — the surrounding
        # chat is almost always relevant.  Keyword-based gating (e.g. "刚才",
        # "之前") is too brittle: natural language has countless ways to
        # reference prior chat without those specific words ("挑一件事评价一下",
        # "怎么看", "那件事", etc.).
        since = int(time.time()) - 600  # last 10 minutes
        context = self._store.get_messages_since(
            msg["chat_id"], since, limit=20,
        )
        if context:
            for m in context:
                custom = self._nicks.resolve_name(m["sender_id"])
                if custom != m["sender_id"]:
                    m["sender_name"] = custom
            logger.info(
                "Chat context: %d messages for '%s'",
                len(context), display_name,
            )

        try:
            ai_reply = self._summarizer.chat(
                message=clean_content,
                context_messages=context,
                requester_name=display_name,
                bot_name=self._config.bot_display_name,
                group_name=msg.get("group_name", msg.get("chat_id", "群聊")),
            )
            ai_reply = self._nicks.resolve_wxids(ai_reply)
            return f"@{display_name} {ai_reply}"
        except RuntimeError as e:
            logger.error("AI chat failed: %s", e)
            return f"@{display_name} 大脑短路了，稍等再试～"

    # ── Proactive chat handler ────────────────────────────────────

    def _handle_proactive_chat(self, msg: dict, mode) -> str | None:
        """Generate a spontaneous reply based on recent chat context.

        The mode (ProactiveMode) determines:
          - context_count: how many recent messages to fetch
          - max_chars: hard cap on reply length
          - label/description/instruction: injected into AI prompt

        The AI may return an empty string if it judges the conversation
        inappropriate for interjection — no message is sent in that case.
        """
        now = int(time.time())

        # Fetch recent messages — limit to mode's context window
        window_start = now - self._config.proactive_rate_window_sec
        context = self._store.get_messages_since(
            msg["chat_id"], window_start, limit=mode.context_count,
        )

        if not context:
            logger.debug("Proactive: no context available for %s", msg["chat_id"])
            return None

        # Resolve nicknames
        for m in context:
            custom = self._nicks.resolve_name(m["sender_id"])
            if custom != m["sender_id"]:
                m["sender_name"] = custom

        logger.info(
            "Proactive chat: mode=%s context=%d msgs chat=%s",
            mode.name, len(context), msg.get("group_name", msg["chat_id"][:20]),
        )

        try:
            ai_reply = self._summarizer.proactive_chat(
                mode=mode,
                context_messages=context,
                bot_name=self._config.bot_display_name,
                group_name=msg.get("group_name", msg.get("chat_id", "群聊")),
            )
        except RuntimeError as e:
            logger.error("Proactive chat API failed: %s", e)
            return None

        if not ai_reply:
            logger.info(
                "Proactive: AI chose silence (mode=%s)", mode.name,
            )
            return None

        ai_reply = self._nicks.resolve_wxids(ai_reply)
        logger.info(
            "Proactive reply: mode=%s len=%d → '%s'",
            mode.name, len(ai_reply), ai_reply[:40],
        )
        # No @prefix — bot speaks as a natural group member
        return ai_reply
