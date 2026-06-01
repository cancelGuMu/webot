"""Nickname service — resolve wxid_xxx to display names and manage mappings.

Persists wxid → nickname mappings in data/nicknames.json for use by
AI summarization (which should output names, not internal IDs).
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default path relative to project root
DEFAULT_NICKNAME_PATH = Path("data/nicknames.json")


class NicknameService:
    """Loads, resolves, and persists wxid → nickname mappings.

    Usage:
        nicks = NicknameService()
        text = nicks.resolve_wxids("hello wxid_abc123 how are you")
        nicks.update("wxid_abc123", "张三")
        nicks.remove("wxid_abc123")
    """

    def __init__(self, path: Path | str = DEFAULT_NICKNAME_PATH):
        self._path = Path(path)
        self._cache: dict[str, str] | None = None
        self._cache_mtime: float = -1.0

    # ── Load / Reload ──────────────────────────────────────────────

    def load(self, force: bool = False) -> dict[str, str]:
        """Return all known wxid → nickname mappings.

        Results are cached; pass force=True to bypass the cache.
        """
        if not force and self._cache is not None:
            try:
                mtime = self._path.stat().st_mtime
                if mtime == self._cache_mtime:
                    return self._cache
            except OSError:
                pass

        if not self._path.exists():
            self._cache = {}
            self._cache_mtime = -1.0
            return self._cache

        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._cache = {
                k: v for k, v in data.items()
                if not k.startswith("_") and v and v.strip()
            }
            self._cache_mtime = self._path.stat().st_mtime
            logger.debug(
                "Loaded %d nickname mappings from %s",
                len(self._cache), self._path,
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load nicknames: %s", e)
            self._cache = {}
            self._cache_mtime = -1.0

        return self._cache

    # ── Resolve ────────────────────────────────────────────────────

    def resolve_wxids(self, text: str) -> str:
        """Replace all known wxid_xxx patterns in *text* with nicknames.

        Handles:
          wxid_xxx              → 昵称
          **wxid_xxx**          → **昵称**
          wxid_xxx（备注）       → 昵称（备注）
        """
        nicks = self.load()
        if not nicks:
            return text

        # Sort by length descending to avoid partial matches
        for wxid, name in sorted(nicks.items(), key=lambda x: -len(x[0])):
            text = text.replace(wxid, name)
        return text

    def resolve_name(self, wxid: str) -> str:
        """Resolve a single wxid to its nickname, falling back to the wxid itself."""
        nicks = self.load()
        return nicks.get(wxid, wxid)

    # ── Update / Remove ────────────────────────────────────────────

    def update(self, wxid: str, nickname: str) -> None:
        """Add or update a wxid → nickname mapping and persist."""
        data = self._read_raw()
        data[wxid] = nickname
        self._write_raw(data)
        self.load(force=True)
        logger.info("Nickname updated: %s → %s", wxid, nickname)

    def remove(self, wxid: str) -> None:
        """Remove a wxid mapping and persist."""
        data = self._read_raw()
        data.pop(wxid, None)
        self._write_raw(data)
        self.load(force=True)
        logger.info("Nickname removed: %s", wxid)

    def merge_manual(self, overrides: dict[str, str]) -> None:
        """Bulk-merge manual overrides into the nickname store.

        Only adds entries that are not already present.
        """
        data = self._read_raw()
        added = 0
        for wxid, name in overrides.items():
            if wxid.startswith("_"):
                continue
            if wxid not in data and name and name.strip():
                data[wxid] = name.strip()
                added += 1
        if added:
            self._write_raw(data)
            self.load(force=True)
            logger.info("Merged %d manual nickname overrides", added)

    # ── Internals ──────────────────────────────────────────────────

    def _read_raw(self) -> dict:
        """Read the raw JSON file, returning an empty dict on any error."""
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read nicknames file: %s", e)
            return {}

    def _write_raw(self, data: dict) -> None:
        """Write a cleaned dict to the JSON file."""
        # Strip private/comment keys
        out = {k: v for k, v in data.items() if not k.startswith("_")}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(out, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
