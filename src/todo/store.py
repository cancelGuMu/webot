"""SQLite-backed todo storage.

Each todo belongs to a chat_id (group).  display_order is a per-group
monotonic sequence that never changes - when items are completed or
deleted their display_order is preserved so user-facing numbers stay stable.
"""

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS todos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         TEXT    NOT NULL,
    content         TEXT    NOT NULL,
    display_order   INTEGER NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'active',
    creator_id      TEXT    NOT NULL DEFAULT '',
    creator_name    TEXT    NOT NULL DEFAULT '',
    created_at      REAL    NOT NULL,
    completed_by_id   TEXT    DEFAULT '',
    completed_by_name TEXT    DEFAULT '',
    completed_at      REAL    DEFAULT 0,
    deleted_by_id     TEXT    DEFAULT '',
    deleted_by_name   TEXT    DEFAULT '',
    deleted_at        REAL    DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_todos_chat_status ON todos(chat_id, status);
CREATE INDEX IF NOT EXISTS idx_todos_chat_order  ON todos(chat_id, display_order);
"""


@dataclass
class TodoItem:
    id: int
    chat_id: str
    content: str
    display_order: int
    status: str  # "active" | "completed" | "deleted"
    creator_id: str
    creator_name: str
    created_at: float
    completed_by_id: str = ""
    completed_by_name: str = ""
    completed_at: float = 0.0
    deleted_by_id: str = ""
    deleted_by_name: str = ""
    deleted_at: float = 0.0

    @staticmethod
    def from_row(row: tuple) -> "TodoItem":
        return TodoItem(
            id=row[0], chat_id=row[1], content=row[2],
            display_order=row[3], status=row[4],
            creator_id=row[5], creator_name=row[6], created_at=row[7],
            completed_by_id=row[8] or "", completed_by_name=row[9] or "",
            completed_at=row[10] or 0.0,
            deleted_by_id=row[11] or "", deleted_by_name=row[12] or "",
            deleted_at=row[13] or 0.0,
        )


@dataclass
class TodoResult:
    """Return value for todo operations."""
    ok: bool
    reply: str = ""
    items: list[TodoItem] = field(default_factory=list)
    total: int = 0


class TodoStore:
    """Persist todos in the bot's SQLite database."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(CREATE_TABLE)
            conn.commit()

    # helpers

    def _get_active_count(self, chat_id: str) -> int:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM todos WHERE chat_id=? AND status='active'",
                (chat_id,),
            ).fetchone()
        return row[0] if row else 0

    # add

    def add(self, chat_id: str, content: str,
            creator_id: str = "", creator_name: str = "",
            max_per_group: int = 50) -> TodoResult:
        """Add a new todo.  Returns error if duplicate or over limit."""
        content = content.strip()
        if not content:
            return TodoResult(ok=False, reply="待办内容不能为空。")

        with sqlite3.connect(self._db_path) as conn:
            # Dedup: same content, same group, still active
            dup = conn.execute(
                "SELECT id, display_order FROM todos "
                "WHERE chat_id=? AND content=? AND status='active'",
                (chat_id, content),
            ).fetchone()
            if dup:
                return TodoResult(
                    ok=False,
                    reply=f"待办“{content}”已存在（第 {dup[1]} 项），无需重复添加。",
                )

            # Limit check
            active_count = conn.execute(
                "SELECT COUNT(*) FROM todos WHERE chat_id=? AND status='active'",
                (chat_id,),
            ).fetchone()[0]
            if active_count >= max_per_group:
                return TodoResult(
                    ok=False,
                    reply=f"当前待办已达上限（{max_per_group} 项），请先完成或删除一些再添加。",
                )

            # Next display_order
            max_order = conn.execute(
                "SELECT COALESCE(MAX(display_order), 0) FROM todos WHERE chat_id=?",
                (chat_id,),
            ).fetchone()[0]

            now = time.time()
            conn.execute(
                "INSERT INTO todos (chat_id, content, display_order, status, "
                "creator_id, creator_name, created_at) VALUES (?,?,?,?,?,?,?)",
                (chat_id, content, max_order + 1, "active",
                 creator_id, creator_name, now),
            )
            conn.commit()

        items, total = self._list_active(chat_id)
        return TodoResult(
            ok=True,
            reply=f"已添加待办：{content}",
            items=items, total=total,
        )

    # complete

    def complete(self, chat_id: str, target: str,
                 operator_id: str = "", operator_name: str = "",
                 ) -> TodoResult:
        """Mark a todo as completed by display_order or content match."""
        item = self._resolve_target(chat_id, target, status="active")
        if item is None:
            return TodoResult(ok=False, reply=f"未找到匹配的待办：{target}")

        now = time.time()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE todos SET status='completed', "
                "completed_by_id=?, completed_by_name=?, completed_at=? "
                "WHERE id=?",
                (operator_id, operator_name, now, item.id),
            )
            conn.commit()

        items, total = self._list_active(chat_id)
        return TodoResult(
            ok=True,
            reply=f"已将第 {item.display_order} 项标记为已完成：{item.content}",
            items=items, total=total,
        )

    # delete (soft)

    def delete(self, chat_id: str, target: str,
               operator_id: str = "", operator_name: str = "",
               ) -> TodoResult:
        """Soft-delete a todo (move to deleted list)."""
        item = self._resolve_target(chat_id, target, status="active")
        if item is None:
            return TodoResult(ok=False, reply=f"未找到匹配的待办：{target}")

        now = time.time()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE todos SET status='deleted', "
                "deleted_by_id=?, deleted_by_name=?, deleted_at=? "
                "WHERE id=?",
                (operator_id, operator_name, now, item.id),
            )
            conn.commit()

        items, total = self._list_active(chat_id)
        return TodoResult(
            ok=True,
            reply=f"已将第 {item.display_order} 项移至已删除：{item.content}",
            items=items, total=total,
        )

    # restore

    def restore(self, chat_id: str, target: str) -> TodoResult:
        """Restore a deleted todo back to active."""
        item = self._resolve_target(chat_id, target, status="deleted")
        if item is None:
            return TodoResult(ok=False, reply=f"未在已删除中找到：{target}")

        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE todos SET status='active', "
                "deleted_by_id='', deleted_by_name='', deleted_at=0 "
                "WHERE id=?",
                (item.id,),
            )
            conn.commit()

        items, total = self._list_active(chat_id)
        return TodoResult(
            ok=True,
            reply=f"已将第 {item.display_order} 项恢复：{item.content}",
            items=items, total=total,
        )

    # list

    def _list_active(self, chat_id: str) -> tuple[list[TodoItem], int]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM todos WHERE chat_id=? AND status='active' "
                "ORDER BY display_order",
                (chat_id,),
            ).fetchall()
        items = [TodoItem.from_row(r) for r in rows]
        return items, len(items)

    def list_active(self, chat_id: str) -> TodoResult:
        items, total = self._list_active(chat_id)
        return TodoResult(ok=True, items=items, total=total)

    def list_completed(self, chat_id: str) -> TodoResult:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM todos WHERE chat_id=? AND status='completed' "
                "ORDER BY completed_at DESC",
                (chat_id,),
            ).fetchall()
        items = [TodoItem.from_row(r) for r in rows]
        return TodoResult(ok=True, items=items, total=len(items))

    def list_deleted(self, chat_id: str) -> TodoResult:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM todos WHERE chat_id=? AND status='deleted' "
                "ORDER BY deleted_at DESC",
                (chat_id,),
            ).fetchall()
        items = [TodoItem.from_row(r) for r in rows]
        return TodoResult(ok=True, items=items, total=len(items))

    # clear

    def clear_completed(self, chat_id: str) -> TodoResult:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM todos WHERE chat_id=? AND status='completed'",
                (chat_id,),
            )
            conn.commit()
        return TodoResult(ok=True, reply="已清空已完成事项。")

    def clear_deleted(self, chat_id: str) -> TodoResult:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM todos WHERE chat_id=? AND status='deleted'",
                (chat_id,),
            )
            conn.commit()
        return TodoResult(ok=True, reply="已彻底清空已删除事项。")

    # auto-cleanup

    def cleanup(self, chat_id: str,
                completed_retention_days: int = 30,
                deleted_retention_days: int = 30) -> None:
        """Remove expired completed/deleted todos. 0 = keep forever."""
        now = time.time()
        with sqlite3.connect(self._db_path) as conn:
            if completed_retention_days > 0:
                cutoff = now - completed_retention_days * 86400
                conn.execute(
                    "DELETE FROM todos WHERE chat_id=? AND status='completed' "
                    "AND completed_at > 0 AND completed_at < ?",
                    (chat_id, cutoff),
                )
            if deleted_retention_days > 0:
                cutoff = now - deleted_retention_days * 86400
                conn.execute(
                    "DELETE FROM todos WHERE chat_id=? AND status='deleted' "
                    "AND deleted_at > 0 AND deleted_at < ?",
                    (chat_id, cutoff),
                )
            conn.commit()

    # target resolution

    def _resolve_target(self, chat_id: str, target: str,
                        status: str) -> Optional[TodoItem]:
        """Resolve a user-supplied target (number, Chinese number, or
        content keyword) to a single TodoItem with the given status.
        Returns None if not found or ambiguous.
        """
        target = target.strip()
        if not target:
            return None

        # 1. Try as display_order
        order = _parse_order(target)
        if order is not None:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT * FROM todos WHERE chat_id=? AND status=? "
                    "AND display_order=?",
                    (chat_id, status, order),
                ).fetchone()
            if row:
                return TodoItem.from_row(row)
            return None

        # 2. Fuzzy match by content keyword
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM todos WHERE chat_id=? AND status=? "
                "AND content LIKE ? ORDER BY display_order",
                (chat_id, status, f"%{target}%"),
            ).fetchall()
        if len(rows) == 1:
            return TodoItem.from_row(rows[0])
        return None

    # admin: get all todos across groups

    def get_all(self, status: str = "active",
                chat_id: str = "") -> list[TodoItem]:
        """Get todos for admin UI.  If chat_id is empty, return all groups."""
        with sqlite3.connect(self._db_path) as conn:
            if chat_id:
                rows = conn.execute(
                    "SELECT * FROM todos WHERE status=? AND chat_id=? "
                    "ORDER BY chat_id, display_order",
                    (status, chat_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM todos WHERE status=? "
                    "ORDER BY chat_id, display_order",
                    (status,),
                ).fetchall()
        return [TodoItem.from_row(r) for r in rows]

    def get_active_groups(self) -> list[str]:
        """Return distinct chat_ids that have at least one todo."""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT chat_id FROM todos ORDER BY chat_id",
            ).fetchall()
        return [r[0] for r in rows]


# number parsing

import re as _re

_CHINESE_NUMBERS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "第一": 1, "第二": 2, "第三": 3, "第四": 4, "第五": 5,
    "第六": 6, "第七": 7, "第八": 8, "第九": 9, "第十": 10,
}
_ORDER_RE = _re.compile(r"第?\s*(\d+|[一二三四五六七八九十]+)\s*项?")


def _parse_order(text: str) -> Optional[int]:
    """Parse display_order from user input like '3', '第三', '第3项'."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    if text in _CHINESE_NUMBERS:
        return _CHINESE_NUMBERS[text]
    m = _ORDER_RE.match(text)
    if m:
        num_str = m.group(1)
        if num_str.isdigit():
            return int(num_str)
        if num_str in _CHINESE_NUMBERS:
            return _CHINESE_NUMBERS[num_str]
    return None