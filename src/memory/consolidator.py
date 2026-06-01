"""MemoryConsolidator — triggers and orchestrates group memory updates.

Core logic:
- After every N new messages (default 30), or
- After T hours since last consolidation (default 2h),
  consolidate the new messages into the group's memory diary.

Uses the DeepSeek Flash API for low-cost, low-latency consolidation.
"""

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..db.store import MessageStore
    from ..summarize.deepseek_backend import DeepSeekSummarizer

logger = logging.getLogger(__name__)

# ── Tuning constants ─────────────────────────────────────────────────

# Trigger consolidation after this many NEW messages
CONSOLIDATE_MSG_THRESHOLD = 30
# Or after this many seconds since last consolidation (with new messages)
CONSOLIDATE_TIME_THRESHOLD_SEC = 2 * 3600  # 2 hours
# Maximum new messages to send per consolidation (limits prompt size)
MAX_NEW_MSGS_PER_CONSOLIDATION = 200


class MemoryConsolidator:
    """Checks consolidation triggers and orchestrates memory updates.

    Usage:
        consolidator = MemoryConsolidator(store, summarizer)

        # In router.handle(), after persisting each message:
        consolidator.check_and_consolidate(chat_id)
    """

    def __init__(self, store: "MessageStore",
                 summarizer: "DeepSeekSummarizer"):
        self._store = store
        self._summarizer = summarizer

    def check_and_consolidate(self, chat_id: str) -> bool:
        """Check if consolidation is needed and run it if so.

        Returns True if consolidation was performed, False if skipped.
        Never raises — all errors are caught and logged internally.
        """
        try:
            return self._check_and_consolidate_impl(chat_id)
        except Exception as e:
            logger.error(
                "Memory consolidation error for chat %s: %s",
                chat_id[:30], e,
            )
            return False

    # ── Internal ───────────────────────────────────────────────────

    def _check_and_consolidate_impl(self, chat_id: str) -> bool:
        """Internal: check triggers and run consolidation."""
        memory = self._store.get_group_memory(chat_id)
        last_id = memory["last_message_id"] if memory else None
        last_consolidated = memory["last_consolidated"] if memory else None

        # Count new messages since last consolidation
        new_count = self._store.get_new_message_count(chat_id, last_id)

        # Trigger check
        time_ok = (
            last_consolidated is not None
            and (time.time() - last_consolidated) >= CONSOLIDATE_TIME_THRESHOLD_SEC
        )
        msg_ok = new_count >= CONSOLIDATE_MSG_THRESHOLD

        if not time_ok and not msg_ok:
            return False  # nothing to do

        if new_count == 0:
            return False  # no new messages to incorporate

        # Fetch new messages
        new_messages = self._store.get_messages_since_id(
            chat_id, last_id, limit=MAX_NEW_MSGS_PER_CONSOLIDATION,
        )
        if not new_messages:
            return False

        existing_memory = memory["memory_text"] if memory else ""

        logger.info(
            "Consolidating memory for %s (%d new msgs, existing memory=%d chars)...",
            chat_id[:30], len(new_messages), len(existing_memory),
        )

        # Call AI consolidation
        updated = self._summarizer.consolidate_memory(
            existing_memory=existing_memory,
            new_messages=new_messages,
        )

        if not updated or updated == existing_memory:
            logger.info(
                "Memory consolidation returned unchanged text for %s — skipping write",
                chat_id[:30],
            )
            return False

        # Persist
        total_count = (memory["message_count"] if memory else 0) + len(new_messages)
        last_msg_id = new_messages[-1]["message_id"]

        self._store.upsert_group_memory(
            chat_id=chat_id,
            memory_text=updated,
            message_count=total_count,
            last_message_id=last_msg_id,
        )

        logger.info(
            "Memory consolidated for %s: %d msgs → %d chars (total %d msgs processed)",
            chat_id[:30], len(new_messages), len(updated), total_count,
        )
        return True
