"""Admin command handler — parses and executes admin-only commands.

Commands are only accepted from the configured admin wxid (checked in router).
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AdminCommandHandler:
    """Parse and execute admin commands from the bot's admin user.

    Commands (admin only):
      改名 wxid_xxx = 新昵称    → add/update nickname mapping
      删除昵称 wxid_xxx         → remove nickname mapping
      刷新昵称                   → reload from JSON

    Usage:
        handler = AdminCommandHandler(nickname_service)
        reply = handler.handle("改名 wxid_abc = 张三", "AdminName")
    """

    def __init__(self, nickname_service):
        """
        Args:
            nickname_service: NicknameService instance for persistence.
        """
        self._nicks = nickname_service

    def handle(self, content: str, requester_name: str) -> str | None:
        """Parse and execute an admin command. Returns reply text or None.

        Args:
            content: Cleaned message content (no @bot prefix).
            requester_name: Display name of the admin user.

        Returns:
            Reply text if the content was a recognized command, else None.
        """
        content = content.strip()

        # ── 改名 command ────────────────────────────────────────
        if content.startswith("改名 "):
            return self._cmd_rename(content, requester_name)

        # ── 删除昵称 command ────────────────────────────────────
        if content.startswith("删除昵称 "):
            return self._cmd_delete_nickname(content, requester_name)

        # ── 刷新昵称 command ────────────────────────────────────
        if content.strip() == "刷新昵称":
            return (
                f"@{requester_name} 昵称缓存将在下次重启时刷新，"
                f"或使用「改名」命令手动添加"
            )

        return None

    # ── Command implementations ────────────────────────────────────

    def _cmd_rename(self, content: str, requester_name: str) -> str | None:
        """Handle the '改名' command."""
        rest = content[3:].strip()

        # Parse: "wxid_xxx = 新昵称"  or  "wxid_xxx 新昵称"
        if "=" in rest:
            parts = rest.split("=", 1)
        else:
            parts = rest.split(None, 1)  # split on first whitespace

        if len(parts) != 2:
            return None

        wxid = parts[0].strip()
        nickname = parts[1].strip()

        if not wxid or not nickname:
            return None

        self._nicks.update(wxid, nickname)
        return f"@{requester_name} 已更新：{wxid} → {nickname}"

    def _cmd_delete_nickname(self, content: str,
                             requester_name: str) -> str | None:
        """Handle the '删除昵称' command."""
        wxid = content[5:].strip()
        if not wxid:
            return None

        self._nicks.remove(wxid)
        return f"@{requester_name} 已删除：{wxid} 的昵称"
