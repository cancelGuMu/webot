"""In-memory sliding-window message rate tracker.

Tracks message arrival timestamps per chat_id to compute instant
message rate (msgs/min) without hitting the database on every poll.
Lost on restart — the bot simply takes a few minutes to wake up again.
"""

import time
from collections import defaultdict


class RateTracker:
    """Tracks per-group message rate using an in-memory sliding window.

    Thread-safe for single-threaded use (the bot's polling loop).
    """

    def __init__(self, window_sec: int = 120):
        """
        Args:
            window_sec: Width of the sliding window in seconds.
                        Timestamps older than (now - window_sec) are pruned
                        on each access.
        """
        self._window = window_sec
        # chat_id → list of Unix timestamps (float)
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def record(self, chat_id: str) -> None:
        """Record a message arrival for the given chat."""
        self._buckets[chat_id].append(time.time())

    def rate(self, chat_id: str) -> float:
        """Return the current message rate in msgs/minute.

        Automatically prunes expired timestamps before computing.
        Returns 0.0 if the group has no recorded messages.
        """
        if chat_id not in self._buckets:
            return 0.0

        now = time.time()
        cutoff = now - self._window
        timestamps = self._buckets[chat_id]

        # Prune expired entries in-place
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

        if not timestamps:
            return 0.0

        count = len(timestamps)
        # Rate = count / window in minutes
        return count / (self._window / 60)

    def count(self, chat_id: str) -> int:
        """Return the number of messages in the current window."""
        self.rate(chat_id)  # triggers pruning
        return len(self._buckets.get(chat_id, []))

    def clear(self, chat_id: str) -> None:
        """Remove all tracking data for a group."""
        self._buckets.pop(chat_id, None)
