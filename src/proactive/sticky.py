"""In-memory one-shot sticky mention tracker.

When a user sends @bot with no message text, registers a sticky entry
for (chat_id, sender_id).  The user's very next message in that group
is treated as if it were @mentioned — then the entry is consumed (deleted).

Composite key (chat_id, sender_id) ensures different users' stickies
never cross-contaminate, even in the same group.

Lost on restart — acceptable for a 30-60s TTL window.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)


class StickyMentionTracker:
    """One-shot sticky mention bridge.

    Thread-safe: all public methods hold self._lock so concurrent calls
    from ThreadPoolExecutor workers don't corrupt internal dicts.
    """

    def __init__(self, ttl_sec: int = 60):
        """
        Args:
            ttl_sec: Seconds before an unconsumed sticky entry expires.
        """
        self._ttl = ttl_sec
        self._lock = threading.Lock()
        # (chat_id, sender_id) → expiry_timestamp (float)
        self._entries: dict[tuple[str, str], float] = {}
        # Per-entry re-registration count to prevent infinite whitespace loop
        self._re_reg_count: dict[tuple[str, str], int] = {}
        self._call_count: int = 0

    # ── Public API ──────────────────────────────────────────────────

    def register(self, chat_id: str, sender_id: str) -> None:
        """Record a sticky mention for (chat_id, sender_id).

        Overwrites any existing entry for the same key, extending the TTL.
        Tracks re-registration count; after 3 consecutive re-registrations
        without a consume, further re-registrations are logged at WARNING
        and the count is stopped to prevent an infinite loop from a
        malfunctioning client.
        """
        with self._lock:
            self._maybe_cleanup()

            key = (chat_id, sender_id)
            existed = key in self._entries

            # Re-registration cap: prevent infinite whitespace→register loop
            if existed:
                self._re_reg_count[key] = self._re_reg_count.get(key, 0) + 1
                if self._re_reg_count[key] >= 3:
                    logger.warning(
                        "Sticky: %d re-registrations without consume for "
                        "chat=%s sender=%s — capping, entry will expire naturally",
                        self._re_reg_count[key], chat_id[:20], sender_id[:20],
                    )
                    return  # Don't refresh TTL — let the original expiry stand
            else:
                self._re_reg_count.pop(key, None)

            expiry = time.time() + self._ttl
            self._entries[key] = expiry
            logger.debug(
                "Sticky mention %s: chat=%s sender=%s (expires in %ds)",
                "extended" if existed else "registered",
                chat_id[:20], sender_id[:20], self._ttl,
            )

    def consume(self, chat_id: str, sender_id: str) -> bool:
        """Check and consume a sticky mention atomically.

        Returns True if a non-expired sticky entry existed for this
        (chat_id, sender_id) — and clears it.  Returns False if no
        entry existed or it had already expired.
        """
        with self._lock:
            self._maybe_cleanup()

            key = (chat_id, sender_id)
            expiry = self._entries.get(key)
        if expiry is None:
            return False

        remaining = expiry - time.time()
        if remaining <= 0:
            # Expired — clean up and return False
            del self._entries[key]
            self._re_reg_count.pop(key, None)
            return False

        # Warn if the sticky was nearly starved by poll latency
        if remaining < 5:
            logger.warning(
                "Sticky: consumed with only %.1fs remaining — "
                "nearly expired due to poll latency (chat=%s sender=%s)",
                remaining, chat_id[:20], sender_id[:20],
            )

        # Hit — consume (delete) and return True
        del self._entries[key]
        self._re_reg_count.pop(key, None)
        logger.info(
            "Sticky mention consumed: chat=%s sender=%s (%.1fs before expiry)",
            chat_id[:20], sender_id[:20], remaining,
        )
        return True

    def clear(self, chat_id: str, sender_id: str) -> None:
        """Explicitly remove a sticky entry (e.g., user explicitly re-@mentions)."""
        key = (chat_id, sender_id)
        self._entries.pop(key, None)
        self._re_reg_count.pop(key, None)

    # ── Internals ───────────────────────────────────────────────────

    def _maybe_cleanup(self) -> None:
        """Trigger periodic cleanup every 200 calls."""
        self._call_count += 1
        if self._call_count % 200 == 0:
            self._cleanup()

    def _cleanup(self) -> None:
        """Remove all expired entries."""
        now = time.time()
        stale = [k for k, v in self._entries.items() if v < now]
        if stale:
            logger.debug("Sticky cleanup: removing %d expired entries", len(stale))
            for k in stale:
                del self._entries[k]
                self._re_reg_count.pop(k, None)

    def __len__(self) -> int:
        """Number of active sticky entries (useful for monitoring)."""
        return len(self._entries)

    def __repr__(self) -> str:
        return f"StickyMentionTracker(active={len(self)}, ttl={self._ttl}s)"
