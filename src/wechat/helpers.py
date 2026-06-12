"""Shared utilities for WeChat backends.

These reduce duplication across WeChat backend implementations.
"""

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Message type mapping ──────────────────────────────────────────

# WeChat localType -> standard integer codes
MSG_TYPE_MAP: dict[str | int, int] = {
    "text": 1,
    "friend": 1,      # wxauto uses 'friend' for some text messages
    "image": 3,
    "voice": 34,
    "emoji": 47,
    "app_share": 49,   # links, mini-programs
    "file": 49,
    "video": 43,
    "system": 10000,
    # Also support integer keys for lookup
    1: 1,
    3: 3,
    34: 34,
    47: 47,
    49: 49,
    43: 43,
    10000: 10000,
}

# Non-text → human-readable placeholder
_NONTEXT_PLACEHOLDERS: dict[str, str] = {
    "image": "[图片]",
    "voice": "[语音]",
    "emoji": "[表情]",
    "video": "[视频]",
    "file": "[文件]",
    "app_share": "[链接]",
}

# 硬编码反向映射（避免每次调用时重建，且消除 str→int 多对一的歧义）
_REVERSE_MSG_TYPE: dict[int, str] = {
    1: "text", 3: "image", 34: "voice", 47: "emoji",
    43: "video", 49: "file", 10000: "system",
}


def normalize_msg_type(raw_type: Any) -> int:
    """Convert a backend-specific message type to our standard integer code.

    Handles both string keys ("text", "image", ...) and raw integer codes.
    Unknown types default to 1 (text).
    """
    if raw_type is None:
        return 1
    if isinstance(raw_type, int):
        return MSG_TYPE_MAP.get(raw_type, raw_type)
    if isinstance(raw_type, str):
        return MSG_TYPE_MAP.get(raw_type, 1)
    return 1


def format_nontext_content(raw_type: Any) -> str:
    """Return a human-readable placeholder for non-text message types.

    Examples: image → "[图片]", voice → "[语音]", video → "[视频]"
    """
    if isinstance(raw_type, str):
        return _NONTEXT_PLACEHOLDERS.get(raw_type, f"[{raw_type}]")
    if isinstance(raw_type, int):
        key = _REVERSE_MSG_TYPE.get(raw_type, "")
        return _NONTEXT_PLACEHOLDERS.get(key, f"[消息类型:{raw_type}]")
    return "[未知消息]"


def generate_message_id(*fields: Any) -> str:
    """Generate a stable, deterministic message ID from one or more fields.

    Each field's string representation is joined with '|' and hashed via MD5.
    """
    raw = "|".join(str(f) for f in fields)
    return hashlib.md5(raw.encode()).hexdigest()


# ── Dedup set ─────────────────────────────────────────────────────

class DedupSet:
    """A size-bounded set for message deduplication.

    Automatically trims to keep the most recent entries when the set
    grows beyond *max_size*. This prevents unbounded memory growth
    in long-running bots.

    Usage:
        seen = DedupSet(max_size=5000)
        if msg_id in seen:
            continue
        seen.add(msg_id)
    """

    def __init__(self, max_size: int = 5000):
        self._max_size = max_size
        self._data: set[str] = set()
        self._insertion_order: list[str] = []

    def __contains__(self, item: str) -> bool:
        return item in self._data

    def add(self, item: str) -> None:
        """Add an item to the set, trimming if necessary."""
        self._data.add(item)
        self._insertion_order.append(item)
        self._trim()

    def _trim(self) -> None:
        """If the set exceeds max_size, keep only the most recent half."""
        if len(self._data) > self._max_size:
            keep = self._max_size // 2
            discard = self._insertion_order[:-keep]
            self._insertion_order = self._insertion_order[-keep:]
            for item in discard:
                self._data.discard(item)
            logger.debug(
                "DedupSet trimmed: %d → %d items",
                len(self._data) + len(discard), len(self._data),
            )

    def __len__(self) -> int:
        return len(self._data)
