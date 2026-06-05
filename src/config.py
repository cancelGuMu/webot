"""Configuration loading from .env file."""

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _sanitize_display_name(name: str) -> str:
    """Remove only truly dangerous characters from a display name.

    This preserves the user's actual name (including quotes, braces, etc.)
    and relies on *usage-point escaping* (``repr()`` in logs, ``_esc()``
    in ``str.format()`` calls) to prevent injection at each call site.

    Only stripped:
    - Control characters (CR/LF → log-line injection)
    - Leading/trailing whitespace + quotes (almost certainly accidental)
    - Excessive length (> 128 chars)
    """
    if not name:
        return "群聊小助手"

    # 1. Strip control chars (except space) — prevents log-line injection
    name = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", name)

    # 2. Collapse whitespace and strip
    name = re.sub(r"\s+", " ", name).strip()

    # 3. Truncate to reasonable length
    if len(name) > 128:
        name = name[:128]

    # 4. Fallback
    if not name:
        return "群聊小助手"

    return name

# Load .env from the project root directory.
# In a PyInstaller EXE, __file__ resolves inside the temp extraction dir.
# We search multiple locations so the EXE finds .env placed next to it.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def find_env_file() -> Path | None:
    """Find the .env file using a consistent search order.

    Order: EXE directory (frozen) → project root → current working directory.
    Returns the Path if found, or None if no .env exists anywhere.
    """
    locations = [
        PROJECT_ROOT / ".env",
        Path.cwd() / ".env",
    ]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        locations.insert(0, exe_dir / ".env")

    for loc in locations:
        if loc.exists():
            return loc
    return None


_env_path = find_env_file()

if _env_path:
    load_dotenv(_env_path)
else:
    load_dotenv()

# Log which .env was loaded (helpful for debugging EXE packaging issues)
import logging as _logging
_log = _logging.getLogger(__name__)
if _env_path:
    _log.info("Loaded .env from: %s", _env_path)
else:
    _log.warning(
        ".env not found in any search path (%s). Using defaults.",
        ", ".join(str(p) for p in _locations),
    )


@dataclass
class BotConfig:
    """All configuration for the WeChat summarizer bot."""

    # === AI Backend ===
    # "claude" or "deepseek"
    ai_backend: str = "claude"

    # === Claude (Anthropic) ===
    anthropic_api_key: str = ""
    summarize_model: str = "claude-haiku-4-5-20251001"

    # === DeepSeek ===
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"

    # === WeChat Backend ===
    wechat_backend: str = "wcdb"
    # Comma-separated group names to monitor. "*" = auto-discover all groups.
    wechat_groups: str = "*"

    # === Bot Identity ===
    bot_display_name: str = "群聊小助手"
    # Admin wxid (can manage nicknames and bot settings)
    admin_wxid: str = ""

    # === Trigger Keywords ===
    trigger_keywords: list[str] = field(default_factory=lambda: [
        "总结一下", "之前发了什么", "错过了什么", "summarize",
        "what did i miss", "聊天总结", "帮我总结", "前面说了什么",
        "说了啥", "发生了什么",
    ])

    # === Database ===
    db_path: str = "data/messages.db"

    # === Features ===
    # Enable web search before AI chat replies (duckduckgo, free)
    enable_web_search: bool = True

    # === Proactive Participation ===
    # Master switch — enable autonomous chat participation without @mention
    proactive_enabled: bool = False
    # Rate thresholds for each mode (msgs/min).  When the message rate
    # exceeds a threshold, the bot enters that mode.  Calibrate these
    # by running:  python tools/analyze_chat_rhythm.py
    proactive_rate_window_sec: int = 120  # rate calculation window
    proactive_rate_quiet: float = 1.5     # SLEEP → QUIET  boundary
    proactive_rate_casual: float = 4.0    # QUIET → CASUAL boundary
    proactive_rate_lively: float = 6.5    # CASUAL → LIVELY boundary
    proactive_rate_burst: float = 8.5     # LIVELY → BURST  boundary

    # === Vulgar Content Guard ===
    # When enabled, the bot detects vulgar/low-brow memes in incoming
    # messages and issues a firm verbal warning (no profanity) instead
    # of engaging.  Also filters the AI's own output as a safety net.
    vulgar_guard_enabled: bool = True

    # === Sticky Mention ===
    # When a user sends @bot with no message text, enter sticky listening
    # mode.  The user's next message in the same group is treated as if it
    # were @mentioned (one-shot).  Set enabled=false to disable entirely.
    sticky_mention_enabled: bool = True
    sticky_mention_ttl_sec: int = 60  # max wait for follow-up message

    # === Tuning ===
    poll_interval_sec: float = 1.0
    dedup_window_sec: int = 60
    max_messages_for_summary: int = 5000
    chunk_size: int = 400
    fallback_window_hours: int = 8

    # === Logging ===
    log_level: str = "INFO"
    log_file: str = "data/bot.log"


def _validate_config(kwargs: dict) -> None:
    """Validate numeric config values.  Prints clear errors and exits on bad values."""
    errors: list[str] = []

    # poll_interval_sec
    poll_interval_sec = kwargs.get("poll_interval_sec", 1.0)
    if poll_interval_sec < 0.1:
        errors.append(
            f"POLL_INTERVAL_SEC must be >= 0.1, got {poll_interval_sec}"
        )

    # chunk_size
    chunk_size = kwargs.get("chunk_size", 400)
    if not (10 <= chunk_size <= 1000):
        errors.append(
            f"CHUNK_SIZE must be between 10 and 1000, got {chunk_size}"
        )

    # max_messages_for_summary
    max_messages_for_summary = kwargs.get("max_messages_for_summary", 5000)
    if max_messages_for_summary < 10:
        errors.append(
            f"MAX_MESSAGES_FOR_SUMMARY must be >= 10, got {max_messages_for_summary}"
        )

    # fallback_window_hours
    fallback_window_hours = kwargs.get("fallback_window_hours", 8)
    if fallback_window_hours < 1:
        errors.append(
            f"FALLBACK_WINDOW_HOURS must be >= 1, got {fallback_window_hours}"
        )

    # dedup_window_sec
    dedup_window_sec = kwargs.get("dedup_window_sec", 60)
    if dedup_window_sec < 10:
        errors.append(
            f"DEDUP_WINDOW_SEC must be >= 10, got {dedup_window_sec}"
        )

    # sticky_mention_ttl_sec
    sticky_mention_ttl_sec = kwargs.get("sticky_mention_ttl_sec", 60)
    if not (10 <= sticky_mention_ttl_sec <= 300):
        errors.append(
            f"STICKY_MENTION_TTL_SEC must be between 10 and 300, "
            f"got {sticky_mention_ttl_sec}"
        )

    # proactive_rate_window_sec
    proactive_rate_window_sec = kwargs.get("proactive_rate_window_sec", 120)
    if proactive_rate_window_sec < 30:
        errors.append(
            f"PROACTIVE_RATE_WINDOW_SEC must be >= 30, got {proactive_rate_window_sec}"
        )

    # proactive_rate thresholds: all > 0 and in strict ascending order
    quiet = kwargs.get("proactive_rate_quiet", 1.5)
    casual = kwargs.get("proactive_rate_casual", 4.0)
    lively = kwargs.get("proactive_rate_lively", 6.5)
    burst = kwargs.get("proactive_rate_burst", 8.5)

    rate_names = ("quiet", "casual", "lively", "burst")
    rate_values = (quiet, casual, lively, burst)

    if any(v <= 0 for v in rate_values):
        errors.append(
            "All PROACTIVE_RATE_* values must be > 0, got: "
            + ", ".join(f"{n}={v}" for n, v in zip(rate_names, rate_values))
        )

    if not (quiet < casual < lively < burst):
        errors.append(
            "PROACTIVE_RATE_* values must be in strict ascending order "
            "(quiet < casual < lively < burst), got: "
            + ", ".join(f"{n}={v}" for n, v in zip(rate_names, rate_values))
        )

    # max_retries (if present in config)
    max_retries = kwargs.get("max_retries")
    if max_retries is not None:
        if not (1 <= max_retries <= 10):
            errors.append(
                f"MAX_RETRIES must be between 1 and 10, got {max_retries}"
            )

    if errors:
        msg = "配置值无效:\n" + "\n".join(f"  - {err}" for err in errors)
        raise RuntimeError(msg)


def load_config() -> BotConfig:
    """Load configuration from environment variables.

    Returns a validated BotConfig instance.
    Raises RuntimeError if required configuration is missing.
    """
    ai_backend = os.getenv("AI_BACKEND", "claude").strip().lower()

    # Validate required API keys based on selected backend
    if ai_backend == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            msg = "DEEPSEEK_API_KEY 未设置，请在 .env 文件中配置或通过引导页完成设置"
            raise RuntimeError(msg)
    else:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            msg = "ANTHROPIC_API_KEY 未设置，请在 .env 文件中配置或通过引导页完成设置"
            raise RuntimeError(msg)

    # Parse trigger keywords from comma-separated string
    keywords_str = os.getenv("TRIGGER_KEYWORDS", "").strip()
    trigger_keywords = (
        [kw.strip() for kw in keywords_str.split(",") if kw.strip()]
        if keywords_str
        else None  # let the dataclass default apply
    )

    kwargs: dict = {
        "ai_backend": ai_backend,
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", "").strip(),
        "summarize_model": os.getenv("SUMMARIZE_MODEL", "claude-haiku-4-5-20251001").strip(),
        "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY", "").strip(),
        # deepseek_model handled conditionally below (dataclass default)
        "wechat_backend": os.getenv("WECHAT_BACKEND", "wcdb").strip(),
        "wechat_groups": os.getenv("WECHAT_GROUPS", "*").strip(),
        "bot_display_name": _sanitize_display_name(os.getenv("BOT_DISPLAY_NAME", "群聊小助手")),
        "admin_wxid": os.getenv("ADMIN_WXID", "").strip(),
        "db_path": os.getenv("DB_PATH", "data/messages.db").strip(),
        "poll_interval_sec": float(os.getenv("POLL_INTERVAL_SEC", "1.0")),
        "dedup_window_sec": int(os.getenv("DEDUP_WINDOW_SEC", "60")),
        "max_messages_for_summary": int(os.getenv("MAX_MESSAGES_FOR_SUMMARY", "5000")),
        "chunk_size": int(os.getenv("CHUNK_SIZE", "400")),
        "fallback_window_hours": int(os.getenv("FALLBACK_WINDOW_HOURS", "8")),
        "enable_web_search": os.getenv("ENABLE_WEB_SEARCH", "true").strip().lower() == "true",
        "proactive_enabled": os.getenv("PROACTIVE_ENABLED", "false").strip().lower() == "true",
        # proactive_rate_window_sec handled conditionally below (dataclass default)
        "proactive_rate_quiet": float(os.getenv("PROACTIVE_RATE_QUIET", "1.5")),
        "proactive_rate_casual": float(os.getenv("PROACTIVE_RATE_CASUAL", "4.0")),
        "proactive_rate_lively": float(os.getenv("PROACTIVE_RATE_LIVELY", "6.5")),
        "proactive_rate_burst": float(os.getenv("PROACTIVE_RATE_BURST", "8.5")),
        "vulgar_guard_enabled": os.getenv("VULGAR_GUARD_ENABLED", "true").strip().lower() == "true",
        "sticky_mention_enabled": os.getenv("STICKY_MENTION_ENABLED", "true").strip().lower() == "true",
        "sticky_mention_ttl_sec": int(os.getenv("STICKY_MENTION_TTL_SEC", "60")),
        "log_level": os.getenv("LOG_LEVEL", "INFO").strip(),
        "log_file": os.getenv("LOG_FILE", "data/bot.log").strip(),
    }

    deepseek_model = os.getenv("DEEPSEEK_MODEL")
    if deepseek_model is not None:
        kwargs["deepseek_model"] = deepseek_model.strip()

    proactive_rate_window_sec = os.getenv("PROACTIVE_RATE_WINDOW_SEC")
    if proactive_rate_window_sec is not None:
        kwargs["proactive_rate_window_sec"] = int(proactive_rate_window_sec)

    if trigger_keywords is not None:
        kwargs["trigger_keywords"] = trigger_keywords

    _validate_config(kwargs)

    return BotConfig(**kwargs)


def is_onboarding_done() -> bool:
    """Check if onboarding has been completed without loading full config.

    Uses find_env_file() for consistent .env resolution.
    """
    env_path = find_env_file()
    if env_path and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ONBOARDING_DONE="):
                return line.split("=", 1)[1].strip().lower() == "true"
        return False  # .env exists but no ONBOARDING_DONE key
    return False  # No .env found
