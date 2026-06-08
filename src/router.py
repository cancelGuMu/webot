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
from .proactive.sticky import StickyMentionTracker
from .memory.consolidator import MemoryConsolidator

logger = logging.getLogger(__name__)

# ── Tuning constants ──────────────────────────────────────────────
CHAT_CONTEXT_WINDOW_SEC = 600      # fetch last N seconds of chat as context for @mentions
MAX_CONTENT_LENGTH = 997           # max chars per message sent to AI (997 + "..." = 1000)
MAX_CONTENT_LINES = 20             # max context lines fed to AI chat prompt
AT_MENTION_MAX_AGE_SEC = 300       # ignore @mentions older than 5 minutes (startup safety)

# Markdown patterns to strip before sending to WeChat.
# These regexes may miss edge cases like nested formatting or asterisks at
# line boundaries.  AI output typically uses simple bold/italic/code/
# strikethrough — these patterns handle 99% of cases.
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
                 nickname_service, config, feishu_export_service=None):
        """
        Args:
            store: MessageStore instance for persistence and queries.
            detector: TriggerDetector instance for keyword matching.
            summarizer: AbstractSummarizer instance for AI responses.
            admin_handler: AdminCommandHandler instance.
            nickname_service: NicknameService instance.
            config: BotConfig instance.
            feishu_export_service: Optional FeishuExportService instance.
        """
        self._store = store
        self._detector = detector
        self._summarizer = summarizer
        self._admin = admin_handler
        self._nicks = nickname_service
        self._config = config
        self._feishu_export = feishu_export_service
        self._proactive = ProactiveGate(config)
        self._sticky = StickyMentionTracker(
            ttl_sec=config.sticky_mention_ttl_sec,
        ) if config.sticky_mention_enabled else None
        self._memory = MemoryConsolidator(store, summarizer)
        # Health monitoring: count unique messages processed (post-dedup)
        self.messages_processed: int = 0

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Remove markdown formatting characters that WeChat can't render."""
        text = _MD_BOLD.sub(r"\1", text)
        text = _MD_ITALIC.sub(r"\1", text)
        text = _MD_STRIKE.sub(r"\1", text)
        text = _MD_CODE.sub(r"\1", text)
        return text.strip()

    def handle(self, msg: dict) -> Optional[str]:
        """Process an incoming group chat message.

        Returns reply text if a reply should be sent, or None.
        """
        # Skip messages from the bot itself (prevent infinite loops).
        # Use a forgiving match — WeChat display names can vary slightly
        # (extra spaces, punctuation, emoji suffixes) from what's in .env.
        bot_name = self._config.bot_display_name.strip()
        if bot_name and (
            msg["sender_name"].strip() == bot_name
            or bot_name in msg["sender_name"]
        ):
            return None

        # Always persist the message
        stored = self._store.insert_message(msg)
        if not stored:
            return None  # Duplicate — nothing more to do
        self.messages_processed += 1

        # Check memory consolidation trigger (fast no-op unless threshold hit)
        self._memory.check_and_consolidate(msg["chat_id"])

        # ── Welcome new member ────────────────────────────────────
        if msg.get("is_system_join") and self._config.welcome_enabled:
            return self._handle_welcome(msg)

        # ── Route: @mention vs proactive ─────────────────────────
        # Sticky mention: if the user previously sent an empty @mention,
        # their next message is treated as if it were @mentioned (one-shot).
        is_at = msg["is_at_mentioned"] or (
            self._sticky is not None
            and self._sticky.consume(msg["chat_id"], msg["sender_id"])
        )

        if is_at:
            # ── @mention path (existing logic) ───────────────────

            # Guard: ignore stale @mentions, e.g. historical messages
            # replayed on startup when the dedup cache is cold.
            # WeChat message timestamps are Unix seconds.
            msg_age_sec = int(time.time()) - msg.get("timestamp", 0)
            if msg_age_sec > AT_MENTION_MAX_AGE_SEC:
                logger.info(
                    "Ignoring stale @mention from '%s' (age=%ds, max=%ds)",
                    msg["sender_name"], msg_age_sec, AT_MENTION_MAX_AGE_SEC,
                )
                return None

            logger.info(
                "Trigger in %s by '%s': %s",
                msg["chat_id"], msg["sender_name"], msg["content"][:80],
            )

            clean_content = msg["content"]
            if self._config.bot_display_name:
                # WeChat @mentions use @wxid<invisible_separator>text format.
                # The separator (U+2005, U+200B, U+FEFF, etc.) is not removed
                # by str.strip().  Use a regex to strip @bot_name + any
                # trailing non-word chars in one pass.
                clean_content = re.sub(
                    re.escape(f"@{self._config.bot_display_name}") + r"[^\w]*",
                    "", msg["content"]
                ).strip()

            # Strip WeChat reply-quote prefix: wxid_xxx:\n
            # When a user replies to a message then @mentions the bot,
            # WeChat prepends "wxid_<replied_user_id>:\n" to the content.
            clean_content = re.sub(
                r'^\s*wxid_[a-zA-Z0-9]+:\s*', '', clean_content,
            )

            reply: Optional[str] = None

            # ── Empty @mention → sticky listening mode ──────────────
            # User sent @bot but nothing else.  Register a sticky so
            # their next message (without @mention) still reaches the bot.
            if not clean_content.strip() and self._sticky is not None:
                self._sticky.register(msg["chat_id"], msg["sender_id"])
                logger.info(
                    "Empty @mention from '%s' in %s — sticky listening active for %ds",
                    msg["sender_name"], msg["chat_id"][:20],
                    self._config.sticky_mention_ttl_sec,
                )

            if (
                reply is None
                and self._feishu_export is not None
                and self._feishu_export.is_export_command(clean_content)
            ):
                result = self._feishu_export.export_recent_chat(msg)
                reply = result.reply_text

            if reply is None and clean_content.strip() in ("帮助", "help", "命令"):
                reply = self._admin.handle(clean_content, msg["sender_name"])

            elif self._config.fun_enabled and clean_content.strip() == "抽签":
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

    # ── Memory helper ────────────────────────────────────────────

    def _get_group_memory(self, chat_id: str) -> str:
        """Return the group's memory text, or empty string if none."""
        mem = self._store.get_group_memory(chat_id)
        return mem["memory_text"] if mem else ""

    # ── Summary handler ──────────────────────────────────────────

    def _handle_summary(self, msg: dict) -> str | None:
        """Generate a chat summary for the requester.

        Summary range: from requester's last message to @bot trigger message.
        Requester's own messages are excluded from the summary."""
        if not self._config.summarize_enabled:
            return None

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
                # Trim single messages over 1000 chars to save tokens.
                #
                # Python 3 string slicing operates on code points, not bytes,
                # so content[:997] will never split a multi-byte UTF-8
                # sequence.  However, surrogate escapes from the Windows
                # clipboard can leak lone surrogates (U+D800–U+DFFF) into
                # strings; slicing between a high/low surrogate pair would
                # produce an invalid lone surrogate at the cut point.
                # Pre-sanitise with surrogateescape→replace to squash any
                # lone surrogates into U+FFFD before slicing.
                if len(content) > 1000:
                    content = content.encode(
                        "utf-8", errors="surrogateescape",
                    ).decode("utf-8", errors="replace")
                    content = content[:MAX_CONTENT_LENGTH] + "..."
                m["content"] = content

            result = self._summarizer.summarize(messages, sender_name)
            reply = self._summarizer.format_summary_for_reply(result, sender_name)
            reply = self._nicks.resolve_wxids(reply)

            logger.info("Summary sent to %s (%d chars)", chat_id, len(reply))
            return reply
        except Exception as e:
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
        since = int(time.time()) - CHAT_CONTEXT_WINDOW_SEC
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
                group_memory=self._get_group_memory(msg["chat_id"]),
            )
            ai_reply = self._nicks.resolve_wxids(ai_reply)
            # Guard against empty AI reply — sending a bare @mention is confusing
            if not ai_reply or not ai_reply.strip():
                logger.warning(
                    "AI chat returned empty for '%s' in %s",
                    display_name, msg.get("group_name", msg["chat_id"][:20]),
                )
                return None
            return f"@{display_name} {ai_reply}"
        except Exception as e:
            logger.error("AI chat failed: %s", e)
            return f"@{display_name} 大脑短路了，稍等再试～"

    # ── Welcome handler ─────────────────────────────────────────

    def _handle_welcome(self, msg: dict) -> str | None:
        """Send a welcome message for a new group member.

        Resolves the appropriate welcome template for the group,
        replaces ``{new_member}`` with the new member's identifier,
        and returns the final text.  Returns None if the group has
        explicitly disabled welcome or no template matches.
        """
        from .welcome import get_welcome_manager

        new_member = msg.get("new_member_id", "")
        if not new_member:
            logger.warning("Welcome: missing new_member_id in join event")
            return None

        chat_id = msg["chat_id"]
        wm = get_welcome_manager()
        welcome_text = wm.resolve_message(chat_id, new_member)

        if not welcome_text:
            logger.info(
                "Welcome: skipped for '%s' in %s (disabled or no template)",
                new_member, msg.get("group_name", chat_id[:20]),
            )
            return None

        logger.info(
            "Welcome: new member '%s' in %s → '%s'",
            new_member, msg.get("group_name", chat_id[:20]), welcome_text[:40],
        )
        return welcome_text

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
                group_memory=self._get_group_memory(msg["chat_id"]),
            )
        except Exception as e:
            logger.error("Proactive chat API failed: %s", e)
            return None

        if not ai_reply:
            self._proactive.record_silence(msg["chat_id"])
            consecutive = self._proactive.get_consecutive_silence(msg["chat_id"])
            log_level = logging.WARNING if consecutive >= 3 else logging.INFO
            logger.log(
                log_level,
                "Proactive: AI chose silence (mode=%s consecutive=%d chat=%s)",
                mode.name, consecutive, msg["chat_id"][:20],
            )
            return None

        self._proactive.record_speech(msg["chat_id"])
        ai_reply = self._nicks.resolve_wxids(ai_reply)
        logger.info(
            "Proactive reply: mode=%s len=%d → '%s'",
            mode.name, len(ai_reply), ai_reply[:40],
        )
        # No @prefix — bot speaks as a natural group member
        return ai_reply
