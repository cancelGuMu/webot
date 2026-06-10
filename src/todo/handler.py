"""Todo command parsing and dispatch.

Receives a clean @mention message (bot name already stripped), matches it
against the configured trigger keywords by priority, and returns a TodoResult.
"""

import logging
from typing import Optional

from .store import TodoStore, TodoResult

logger = logging.getLogger(__name__)

# Fixed trigger keywords (not user-customizable)
_VIEW_KEYWORDS = ["查看待办", "待办列表", "还有什么没做", "还有啥没做"]
_COMPLETED_LIST_KEYWORDS = ["已完成列表", "看看做完了什么", "完成了哪些"]
_DELETED_LIST_KEYWORDS = ["已删除列表", "看看删了什么", "删了哪些"]
_CLEAR_KEYWORDS = ["清空已完成", "清空已删除"]
_RESTORE_KEYWORDS = ["恢复待办", "还原", "恢复"]


class TodoHandler:
    """Parse a clean @mention message and dispatch to TodoStore."""

    def __init__(self, store: TodoStore, config):
        self._store = store
        self._config = config

    def handle(self, clean_content: str, chat_id: str,
               sender_id: str, sender_name: str,
               is_admin: bool) -> Optional[TodoResult]:
        """Try to handle a todo command.  Returns None if not a todo command.

        Priority order (first match wins):
          1. View active todos   (contains match)
          2. View completed list (contains match)
          3. View deleted list   (contains match)
          4. Clear lists         (contains match, admin only)
          5. Add todo            (prefix match + content)
          6. Complete todo       (prefix match + number)
          7. Delete todo         (prefix match + number)
          8. Restore todo        (prefix match + number, admin only)
        """
        content = clean_content.strip()

        # Priority 1: View active
        if self._contains_any(content, _VIEW_KEYWORDS):
            return self._store.list_active(chat_id)

        # Priority 2: View completed
        if self._contains_any(content, _COMPLETED_LIST_KEYWORDS):
            return self._store.list_completed(chat_id)

        # Priority 3: View deleted
        if self._contains_any(content, _DELETED_LIST_KEYWORDS):
            return self._store.list_deleted(chat_id)

        # Priority 4: Clear (admin only)
        if self._contains_any(content, _CLEAR_KEYWORDS):
            if not is_admin:
                return TodoResult(ok=False, reply="仅群管理员可以执行清空操作。")
            if "清空已完成" in content:
                return self._store.clear_completed(chat_id)
            if "清空已删除" in content:
                return self._store.clear_deleted(chat_id)

        # Priority 5: Add (prefix match)
        kw, arg = self._match_prefix(content, self._config.todo_add_keywords)
        if kw:
            if not arg:
                return TodoResult(
                    ok=False,
                    reply="请说明要记录什么待办事项，例如：记一下 周五聚餐",
                )
            return self._store.add(
                chat_id, arg, sender_id, sender_name,
                max_per_group=self._config.todo_max_per_group,
            )

        # Priority 6: Complete (prefix match)
        kw, arg = self._match_prefix(content, self._config.todo_complete_keywords)
        if kw:
            if not arg:
                return TodoResult(
                    ok=False,
                    reply="请指定要完成的待办编号，例如：搞定 3",
                )
            return self._store.complete(chat_id, arg, sender_id, sender_name)

        # Priority 7: Delete (prefix match)
        kw, arg = self._match_prefix(content, self._config.todo_delete_keywords)
        if kw:
            if not arg:
                return TodoResult(
                    ok=False,
                    reply="请指定要删除的待办编号，例如：删掉 2",
                )
            return self._store.delete(chat_id, arg, sender_id, sender_name)

        # Priority 8: Restore (prefix match, admin only)
        kw, arg = self._match_prefix(content, _RESTORE_KEYWORDS)
        if kw:
            if not is_admin:
                return TodoResult(
                    ok=False,
                    reply="仅群管理员可以恢复已删除的待办事项。",
                )
            if not arg:
                return TodoResult(
                    ok=False,
                    reply="请指定要恢复的待办编号，例如：恢复待办 2",
                )
            return self._store.restore(chat_id, arg)

        return None  # Not a todo command

    @staticmethod
    def _contains_any(text: str, keywords: list[str]) -> bool:
        """True if text contains any of the keywords as a substring."""
        for kw in keywords:
            if kw in text:
                return True
        return False

    @staticmethod
    def _match_prefix(text: str, keywords: list[str]) -> tuple[Optional[str], str]:
        """Try to match a keyword at the start of text.

        Returns (matched_keyword, remaining_text) or (None, "").
        Longer keywords (e.g. "添加待办") match before shorter ones (e.g. "待办").
        """
        sorted_kw = sorted(keywords, key=len, reverse=True)
        for kw in sorted_kw:
            if text.startswith(kw):
                arg = text[len(kw):].strip()
                return kw, arg
        return None, ""


def format_todo_reply(result: TodoResult, sender_name: str = "") -> str:
    """Format a TodoResult into a human-readable WeChat reply."""
    if not result.ok:
        return result.reply

    if result.items is not None and len(result.items) >= 0:
        return _format_list(result, sender_name)

    return result.reply


def _format_list(result: TodoResult, sender_name: str) -> str:
    """Format a todo list for display."""
    if result.total == 0:
        return '当前没有待办事项。\n@机器人说"记一下 xxx"即可添加。'

    lines = []
    is_completed = any(
        item.status == "completed" for item in result.items
    ) if result.items else False
    is_deleted = any(
        item.status == "deleted" for item in result.items
    ) if result.items else False

    if is_completed:
        lines.append("已完成事项：")
        lines.append("")
        for item in result.items:
            who = f" @{item.completed_by_name}" if item.completed_by_name else ""
            lines.append(f"{item.display_order}. {item.content} - 由{who} 完成")
    elif is_deleted:
        lines.append("已删除事项：")
        lines.append("")
        for item in result.items:
            who = f" @{item.deleted_by_name}" if item.deleted_by_name else ""
            lines.append(f"{item.display_order}. {item.content} - 由{who} 删除")
    else:
        lines.append("当前群待办内容有：")
        lines.append("")
        for item in result.items:
            lines.append(f"{item.display_order}. {item.content}")

    lines.append("")
    label = "待办" if not is_completed and not is_deleted else ""
    lines.append(f"共 {result.total} 项{label}。")

    if not is_completed and not is_deleted and result.total > 0:
        lines.append('回复"完成 N"或"删除 N"可操作指定事项。')
    elif is_deleted and result.total > 0:
        lines.append('管理员可回复"恢复待办 N"恢复指定事项。')

    return "\n".join(lines)