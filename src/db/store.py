"""MessageStore — all database read/write operations."""

import sqlite3
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MessageStore:
    """Wraps all database operations for message persistence and querying."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ── Write operations ──────────────────────────────────────────

    def insert_message(self, msg: dict) -> bool:
        """Insert a message and update the user's last-message cursor.

        Args:
            msg: Standardized message dict with keys:
                message_id, chat_id, sender_id, sender_name,
                content, msg_type, timestamp

        Returns:
            True if inserted, False if duplicate (silently skipped).
        """
        try:
            with self.conn:
                self.conn.execute(
                    """INSERT INTO messages
                       (message_id, chat_id, sender_id, sender_name,
                        content, msg_type, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        msg["message_id"], msg["chat_id"], msg["sender_id"],
                        msg["sender_name"], msg["content"], msg["msg_type"],
                        msg["timestamp"],
                    ),
                )
                # Upsert the last-message cursor
                self.conn.execute(
                    """INSERT INTO user_last_message
                       (chat_id, sender_id, sender_name, last_timestamp)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(chat_id, sender_id) DO UPDATE SET
                       sender_name = excluded.sender_name,
                       last_timestamp = excluded.last_timestamp""",
                    (
                        msg["chat_id"], msg["sender_id"],
                        msg["sender_name"], msg["timestamp"],
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            # Duplicate message_id — silently skip
            return False

    def log_trigger(self, chat_id: str, requester_id: str,
                    trigger_msg_id: str) -> None:
        """Record a trigger event for deduplication."""
        with self.conn:
            self.conn.execute(
                """INSERT INTO trigger_log
                   (chat_id, requester_id, trigger_message_id)
                   VALUES (?, ?, ?)""",
                (chat_id, requester_id, trigger_msg_id),
            )

    # ── Query operations ───────────────────────────────────────────

    def get_user_last_timestamp(self, chat_id: str,
                                sender_id: str) -> Optional[int]:
        """Get the Unix timestamp of a user's most recent message in a chat.

        Args:
            chat_id: The chatroom ID.
            sender_id: The user's WeChat ID.

        Returns:
            Unix timestamp (int), or None if the user has never posted.
        """
        row = self.conn.execute(
            """SELECT last_timestamp FROM user_last_message
               WHERE chat_id = ? AND sender_id = ?""",
            (chat_id, sender_id),
        ).fetchone()
        return row["last_timestamp"] if row else None

    def get_user_previous_timestamp(self, chat_id: str,
                                    sender_id: str,
                                    before_ts: int) -> Optional[int]:
        """Get the timestamp of a user's last message BEFORE the given time.

        Queries the messages table directly (not user_last_message cursor)
        so we can exclude the current @bot trigger message.  If the most
        recent prior message is within 30 seconds of before_ts (i.e. the
        user sent a message and immediately @mentioned the bot), that
        adjacent message is skipped and the one before it is used instead.

        Args:
            chat_id: The chatroom ID.
            sender_id: The user's WeChat ID.
            before_ts: Upper bound (exclusive) — find messages before this.

        Returns:
            Unix timestamp of the user's last meaningful message before
            the trigger, or None if no prior message exists.
        """
        # Fetch the user's most recent messages before the trigger
        rows = self.conn.execute(
            """SELECT timestamp FROM messages
               WHERE chat_id = ? AND sender_id = ? AND timestamp < ?
               ORDER BY timestamp DESC
               LIMIT 5""",
            (chat_id, sender_id, before_ts),
        ).fetchall()

        if not rows:
            return None

        # If only one prior message exists, use it regardless of gap
        if len(rows) == 1:
            return rows[0]["timestamp"]

        # Skip the most recent prior message if it's too close to the
        # trigger (≤30 seconds) — it's likely a setup line right before
        # the @bot mention, not a meaningful conversation boundary.
        most_recent = rows[0]["timestamp"]
        if before_ts - most_recent <= 30:
            logger.info(
                "Skipping close prior message from sender_id=%s "
                "(gap=%ds). Using earlier message.",
                sender_id, before_ts - most_recent,
            )
            return rows[1]["timestamp"]

        return most_recent

    def get_messages_since(self, chat_id: str, since_ts: int,
                           until_ts: Optional[int] = None,
                           limit: int = 500) -> list[dict]:
        """Fetch messages from a chat in a time window.

        Args:
            chat_id: The chatroom ID.
            since_ts: Start of window (inclusive), Unix seconds.
            until_ts: End of window (inclusive). Defaults to now.
            limit: Maximum number of messages to return.

        Returns:
            List of message dicts, ordered by timestamp ascending.
        """
        if until_ts is None:
            until_ts = int(time.time())

        rows = self.conn.execute(
            """SELECT message_id, chat_id, sender_id, sender_name,
                      content, msg_type, timestamp
               FROM messages
               WHERE chat_id = ? AND timestamp BETWEEN ? AND ?
               ORDER BY timestamp ASC
               LIMIT ?""",
            (chat_id, since_ts, until_ts, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def was_recently_triggered(self, chat_id: str,
                                window_sec: int) -> bool:
        """Check if a trigger was processed for this chat recently.

        Args:
            chat_id: The chatroom ID.
            window_sec: Lookback window in seconds.

        Returns:
            True if a trigger was processed within the window.
        """
        cutoff = int(time.time()) - window_sec
        row = self.conn.execute(
            """SELECT COUNT(*) as cnt FROM trigger_log
               WHERE chat_id = ? AND processed_at > ?""",
            (chat_id, cutoff),
        ).fetchone()
        return row["cnt"] > 0 if row else False
