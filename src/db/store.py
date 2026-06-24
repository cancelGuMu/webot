"""MessageStore — all database read/write operations.

Thread-safe: all public methods are serialized through a lock because
the underlying SQLite connection (check_same_thread=False) is not
safe for concurrent use from multiple threads.
"""

import sqlite3
import threading
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MessageStore:
    """Wraps all database operations for message persistence and querying."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._lock = threading.Lock()
        self._trigger_count = 0

    # ── Write operations ──────────────────────────────────────────

    def insert_message(self, msg: dict) -> bool:
        """Insert a message and update the user's last-message cursor.

        Returns True if inserted, False if duplicate (silently skipped).
        """
        with self._lock:
            try:
                # Coerce all fields to SQLite-safe types (defensive).
                message_id = str(msg["message_id"])
                chat_id = str(msg["chat_id"])
                sender_id = str(msg["sender_id"])
                sender_name = str(msg["sender_name"])
                content = str(msg.get("content", ""))
                msg_type = int(msg.get("msg_type", 1))
                timestamp = int(msg.get("timestamp", 0))

                with self.conn:
                    self.conn.execute(
                        """INSERT INTO messages
                           (message_id, chat_id, sender_id, sender_name,
                            content, msg_type, timestamp)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (message_id, chat_id, sender_id, sender_name,
                         content, msg_type, timestamp),
                    )
                    self.conn.execute(
                        """INSERT INTO user_last_message
                           (chat_id, sender_id, sender_name, last_timestamp)
                           VALUES (?, ?, ?, ?)
                           ON CONFLICT(chat_id, sender_id) DO UPDATE SET
                           sender_name = excluded.sender_name,
                           last_timestamp = excluded.last_timestamp""",
                        (chat_id, sender_id, sender_name, timestamp),
                    )
                return True
            except sqlite3.IntegrityError:
                return False
            except sqlite3.InterfaceError:
                logger.warning(
                    "DB insert skipped (connection closed): msg_id=%s, chat=%s",
                    msg.get("message_id", "?")[:20], msg.get("chat_id", "?"),
                )
                return False
            except Exception:
                logger.exception(
                    "Failed to insert message (msg_id=%s, chat=%s, sender=%s)",
                    msg.get("message_id", "?"), msg.get("chat_id", "?"),
                    msg.get("sender_id", "?"),
                )
                return False

    def log_trigger(self, chat_id: str, requester_id: str,
                    trigger_msg_id: str) -> None:
        """Record a trigger event for deduplication.

        Periodically cleans old entries (every 100th trigger) and
        reclaims disk space (every 1000th trigger).
        """
        with self._lock:
            with self.conn:
                self.conn.execute(
                    """INSERT INTO trigger_log
                       (chat_id, requester_id, trigger_message_id)
                       VALUES (?, ?, ?)""",
                    (chat_id, requester_id, trigger_msg_id),
                )
            self._trigger_count += 1
            if self._trigger_count % 100 == 0:
                self._cleanup_old_triggers_locked()
            if self._trigger_count % 1000 == 0:
                self._vacuum_locked()

    def _cleanup_old_triggers_locked(self) -> int:
        """Delete trigger_log entries older than 7 days (caller must hold lock)."""
        cutoff = int(time.time()) - 7 * 86400
        with self.conn:
            cursor = self.conn.execute(
                "DELETE FROM trigger_log WHERE processed_at < ?",
                (cutoff,),
            )
            deleted = cursor.rowcount
        if deleted:
            logger.info("Cleaned up %d old trigger_log entries.", deleted)
        return deleted

    def cleanup_old_triggers(self) -> int:
        """Delete trigger_log entries older than 7 days. Thread-safe."""
        with self._lock:
            return self._cleanup_old_triggers_locked()

    def _vacuum_locked(self) -> None:
        """Reclaim disk space from deleted trigger_log rows (caller must hold lock)."""
        logger.info("Running VACUUM to reclaim disk space.")
        with self.conn:
            self.conn.execute("PRAGMA optimize")

    # ── Query operations ───────────────────────────────────────────

    def get_sender_display_name(self, sender_id: str) -> Optional[str]:
        """Return a previously seen display name for a wxid, or None."""
        with self._lock:
            row = self.conn.execute(
                """SELECT sender_name FROM messages
                   WHERE sender_id = ? AND sender_name != sender_id
                   ORDER BY id DESC LIMIT 1""",
                (sender_id,),
            ).fetchone()
            return row["sender_name"] if row else None

    def get_user_last_timestamp(self, chat_id: str,
                                sender_id: str) -> Optional[int]:
        """Get the Unix timestamp of a user's most recent message in a chat."""
        with self._lock:
            row = self.conn.execute(
                """SELECT last_timestamp FROM user_last_message
                   WHERE chat_id = ? AND sender_id = ?""",
                (chat_id, sender_id),
            ).fetchone()
            return row["last_timestamp"] if row else None

    def get_user_previous_timestamp(self, chat_id: str,
                                    sender_id: str,
                                    before_ts: int) -> Optional[int]:
        """Get the timestamp of a user's last message BEFORE the given time."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT timestamp FROM messages
                   WHERE chat_id = ? AND sender_id = ? AND timestamp < ?
                   ORDER BY timestamp DESC
                   LIMIT 30""",
                (chat_id, sender_id, before_ts),
            ).fetchall()

            if not rows:
                return None

            prev_ts = before_ts
            skipped = 0
            for row in rows:
                gap = prev_ts - row["timestamp"]
                if gap > 30:
                    if skipped > 0:
                        logger.info(
                            "Skipped %d close prior messages from sender_id=%s "
                            "(final gap=%ds). Using earlier message as boundary.",
                            skipped, sender_id, gap,
                        )
                    return row["timestamp"]
                skipped += 1
                prev_ts = row["timestamp"]

            logger.info(
                "All %d prior messages from sender_id=%s are within close chain. "
                "Using oldest as boundary.",
                len(rows), sender_id,
            )
            return rows[-1]["timestamp"]

    def get_messages_since(self, chat_id: str, since_ts: int,
                           until_ts: Optional[int] = None,
                           limit: int = 500) -> list[dict]:
        """Fetch messages from a chat in a time window."""
        with self._lock:
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
        """Check if a trigger was processed for this chat recently."""
        with self._lock:
            cutoff = int(time.time()) - window_sec
            row = self.conn.execute(
                """SELECT COUNT(*) as cnt FROM trigger_log
                   WHERE chat_id = ? AND processed_at > ?""",
                (chat_id, cutoff),
            ).fetchone()
            return row["cnt"] > 0 if row else False

    # ── Group memory operations ────────────────────────────────────

    def get_group_memory(self, chat_id: str) -> dict | None:
        """Retrieve the memory record for a group."""
        with self._lock:
            row = self.conn.execute(
                """SELECT chat_id, memory_text, message_count,
                          last_message_id, last_consolidated,
                          created_at, updated_at
                   FROM group_memory
                   WHERE chat_id = ?""",
                (chat_id,),
            ).fetchone()
            return dict(row) if row else None

    def upsert_group_memory(self, chat_id: str, memory_text: str,
                            message_count: int, last_message_id: str) -> None:
        """Insert or update a group's memory record."""
        with self._lock:
            now = time.time()
            with self.conn:
                self.conn.execute(
                    """INSERT INTO group_memory
                       (chat_id, memory_text, message_count, last_message_id,
                        last_consolidated, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(chat_id) DO UPDATE SET
                       memory_text = excluded.memory_text,
                       message_count = excluded.message_count,
                       last_message_id = excluded.last_message_id,
                       last_consolidated = excluded.last_consolidated,
                       updated_at = excluded.updated_at""",
                    (chat_id, memory_text, message_count, last_message_id,
                     now, now, now),
                )

    def get_new_message_count(self, chat_id: str,
                              since_message_id: str | None) -> int:
        """Count new messages in a chat since a given message ID."""
        with self._lock:
            if since_message_id is None:
                row = self.conn.execute(
                    "SELECT COUNT(*) as cnt FROM messages WHERE chat_id = ?",
                    (chat_id,),
                ).fetchone()
            else:
                row = self.conn.execute(
                    """SELECT COUNT(*) as cnt FROM messages
                       WHERE chat_id = ? AND id > (
                           SELECT COALESCE(
                               (SELECT id FROM messages WHERE message_id = ?), 0
                           )
                       )""",
                    (chat_id, since_message_id),
                ).fetchone()
            return row["cnt"] if row else 0

    def get_messages_since_id(self, chat_id: str,
                              since_message_id: str | None,
                              limit: int = 200) -> list[dict]:
        """Fetch messages since a given message ID."""
        with self._lock:
            if since_message_id is None:
                rows = self.conn.execute(
                    """SELECT message_id, chat_id, sender_id, sender_name,
                              content, msg_type, timestamp
                       FROM messages
                       WHERE chat_id = ?
                       ORDER BY timestamp ASC
                       LIMIT ?""",
                    (chat_id, limit),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    """SELECT message_id, chat_id, sender_id, sender_name,
                              content, msg_type, timestamp
                       FROM messages
                       WHERE chat_id = ? AND id > (
                           SELECT COALESCE(
                               (SELECT id FROM messages WHERE message_id = ?), 0
                           )
                       )
                       ORDER BY timestamp ASC
                       LIMIT ?""",
                    (chat_id, since_message_id, limit),
                ).fetchall()
            return [dict(row) for row in rows]
