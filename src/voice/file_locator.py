"""Locate WeChat voice files (.silk/.amr) on the filesystem.

WeChat stores voice messages outside the WCDB database, under:
  {wechat_data_dir}/{wxid}/msg/voice/{msg_svr_id}/*.silk
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _extract_msg_svr_id(msg: dict) -> Optional[str]:
    """Extract the server message ID from a WCDB raw message dict.

    Tries multiple field name variants used across WeChat versions.
    """
    for key in ("msgSvrId", "msg_svr_id", "server_id", "serverId", "newMsgId"):
        val = msg.get(key)
        if val:
            return str(val)
    return None


class VoiceFileLocator:
    """Locate .silk/.amr voice files from WCDB message metadata."""

    def __init__(self, wechat_data_dir: str) -> None:
        """Args:
            wechat_data_dir: Path to WeChat data directory
                (the parent of wxid_* folders).
        """
        self._data_dir = Path(wechat_data_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_voice_file(self, msg: dict) -> Optional[Path]:
        """Given a WCDB raw message, return the path to its voice file.

        Lookup order:
          1. {data_dir}/{wxid}/msg/voice/{msg_svr_id}/*.silk
          2. {data_dir}/{wxid}/msg/voice/{msg_svr_id}/*.amr
          3. {data_dir}/{wxid}/msg/attach/{msg_svr_id}/*.silk
          4. {data_dir}/{wxid}/msg/attach/{msg_svr_id}/*.amr

        Returns None if no file is found (e.g. WeChat auto-cleaned it).
        """
        msg_svr_id = _extract_msg_svr_id(msg)
        if not msg_svr_id:
            logger.debug("Voice message missing msg_svr_id, cannot locate file")
            return None

        # Find the wxid_* subdirectory
        wxid_dir = self._find_wxid_dir()
        if not wxid_dir:
            logger.debug("Cannot find wxid_* directory under %s", self._data_dir)
            return None

        # Priority-ordered search
        for subdir in ("voice", "attach"):
            base = wxid_dir / "msg" / subdir / msg_svr_id
            for ext in (".silk", ".amr"):
                candidate = base / f"{msg_svr_id}{ext}"
                if candidate.exists():
                    logger.debug(
                        "Found voice file: %s (%.1f KB)",
                        candidate, candidate.stat().st_size / 1024,
                    )
                    return candidate

        logger.debug(
            "Voice file not found for msg_svr_id=%s (may have been cleaned up)",
            msg_svr_id,
        )
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_wxid_dir(self) -> Optional[Path]:
        """Find the wxid_* directory under the WeChat data directory."""
        if not self._data_dir.exists():
            return None
        for child in self._data_dir.iterdir():
            if child.is_dir() and child.name.startswith("wxid_"):
                return child
        return None
