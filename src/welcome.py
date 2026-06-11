"""Welcome template manager — load/save templates and per-group mappings.

Templates are stored in data/welcome_templates.json.  Each template has a
unique id, a display name, and a message body with ``{new_member}`` as the
placeholder for the new member's identifier.

Group mappings associate a chat_id with either a template_id or the
special sentinel ``"__disabled__"`` (no welcome for that group).

Thread-safe: all disk writes are serialised through a module-level lock.
"""

import json
import logging
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

from src.config import PROJECT_ROOT

# Default path relative to project root
DEFAULT_WELCOME_CONFIG_PATH = PROJECT_ROOT / "data/welcome_templates.json"

DISABLED_SENTINEL = "__disabled__"

DEFAULT_TEMPLATES: list[dict] = [
    {
        "id": "tpl_default",
        "name": "默认",
        "message": "欢迎 @{new_member} 加入群聊！🎉",
    },
    {
        "id": "tpl_warm",
        "name": "热情版",
        "message": "欢迎 @{new_member} 加入！大家出来接客了！🔥",
    },
    {
        "id": "tpl_serious",
        "name": "正经版",
        "message": "欢迎 @{new_member} 加入本群，有问题随时讨论。",
    },
]


def _default_config() -> dict:
    return {
        "templates": DEFAULT_TEMPLATES,
        "group_mapping": {},
        "default_template": "tpl_default",
    }


class WelcomeManager:
    """Thread-safe welcome template manager.

    Usage::

        wm = WelcomeManager()
        text = wm.resolve_message("123@chatroom", "wxid_abc")
        if text:
            send_to_group(text)
    """

    def __init__(self, path: Path | str = DEFAULT_WELCOME_CONFIG_PATH) -> None:
        self._path = Path(path)
        self._lock = Lock()

    # ── Load / Save ──────────────────────────────────────────────

    def load(self) -> dict:
        """Load the full config dict from disk, falling back to defaults."""
        if not self._path.exists():
            return _default_config()
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Sanity: ensure required keys exist
            if "templates" not in data:
                data["templates"] = DEFAULT_TEMPLATES
            if "group_mapping" not in data:
                data["group_mapping"] = {}
            if "default_template" not in data:
                data["default_template"] = "tpl_default"
            # Ensure the default_template actually exists
            template_ids = {t["id"] for t in data["templates"]}
            if data["default_template"] not in template_ids and data["templates"]:
                data["default_template"] = data["templates"][0]["id"]
            return data
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to load welcome templates, using defaults")
            return _default_config()

    def save(self, data: dict) -> None:
        """Atomically write the full config dict to disk."""
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp.replace(self._path)
            logger.info("Welcome templates saved (%d templates, %d group mappings)",
                        len(data.get("templates", [])),
                        len(data.get("group_mapping", {})))

    # ── Resolve ──────────────────────────────────────────────────

    def resolve_message(self, chat_id: str, new_member_id: str) -> str | None:
        """Return the resolved welcome message for *chat_id*, or None.

        Resolution order:
        1. If ``group_mapping[chat_id] == "__disabled__"`` → return None.
        2. If ``group_mapping[chat_id]`` points to a template → use it.
        3. Otherwise use ``default_template``.
        """
        data = self.load()
        mapping: dict[str, str] = data.get("group_mapping", {})

        # 1. Explicitly disabled for this group
        if mapping.get(chat_id) == DISABLED_SENTINEL:
            logger.debug("Welcome: disabled for chat=%s", chat_id[:20])
            return None

        # 2. Find the right template
        templates: dict[str, dict] = {t["id"]: t for t in data.get("templates", [])}
        template_id = mapping.get(chat_id, data.get("default_template", "tpl_default"))
        template = templates.get(template_id)

        if not template:
            # Fallback to first available template
            if templates:
                template = next(iter(templates.values()))
                logger.warning(
                    "Welcome: template '%s' not found, falling back to '%s'",
                    template_id, template["id"],
                )
            else:
                logger.warning("Welcome: no templates defined")
                return None

        # 3. Replace variable
        message = template.get("message", "")
        if not message:
            return None

        return message.replace("{new_member}", f"@{new_member_id}")


# ── Module-level singleton ───────────────────────────────────────

_manager_lock = Lock()
_manager: WelcomeManager | None = None


def get_welcome_manager() -> WelcomeManager:
    """Return the module-level WelcomeManager singleton."""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = WelcomeManager()
    return _manager
