"""Configuration loading from .env file."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


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
    # "weflow" (4.1.x+, recommended) / "uia" / "wx4py"
    wechat_backend: str = "weflow"
    # Comma-separated group names to monitor
    wechat_groups: str = ""
    # WeFlow API base URL (only for weflow backend)
    weflow_url: str = "http://127.0.0.1:5031"
    weflow_token: str = ""

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

    # === Tuning ===
    poll_interval_sec: float = 1.0
    dedup_window_sec: int = 60
    max_messages_for_summary: int = 5000
    chunk_size: int = 400
    fallback_window_hours: int = 8

    # === Logging ===
    log_level: str = "INFO"
    log_file: str = "data/bot.log"


def load_config() -> BotConfig:
    """Load configuration from environment variables.

    Returns a validated BotConfig instance.
    Raises SystemExit if required configuration is missing.
    """
    ai_backend = os.getenv("AI_BACKEND", "claude").strip().lower()

    # Validate required API keys based on selected backend
    if ai_backend == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            print("ERROR: DEEPSEEK_API_KEY is required when AI_BACKEND=deepseek.")
            print("       Set it in your .env file.")
            raise SystemExit(1)
    else:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            print("ERROR: ANTHROPIC_API_KEY is required when AI_BACKEND=claude.")
            print("       Set it in your .env file.")
            raise SystemExit(1)

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
        "deepseek_model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro").strip(),
        "wechat_backend": os.getenv("WECHAT_BACKEND", "weflow").strip(),
        "wechat_groups": os.getenv("WECHAT_GROUPS", "").strip(),
        "weflow_url": os.getenv("WEFLOW_URL", "http://127.0.0.1:5031").strip(),
        "weflow_token": os.getenv("WEFLOW_TOKEN", "").strip(),
        "bot_display_name": os.getenv("BOT_DISPLAY_NAME", "群聊小助手").strip(),
        "admin_wxid": os.getenv("ADMIN_WXID", "").strip(),
        "db_path": os.getenv("DB_PATH", "data/messages.db").strip(),
        "poll_interval_sec": float(os.getenv("POLL_INTERVAL_SEC", "1.0")),
        "dedup_window_sec": int(os.getenv("DEDUP_WINDOW_SEC", "60")),
        "max_messages_for_summary": int(os.getenv("MAX_MESSAGES_FOR_SUMMARY", "5000")),
        "chunk_size": int(os.getenv("CHUNK_SIZE", "400")),
        "fallback_window_hours": int(os.getenv("FALLBACK_WINDOW_HOURS", "8")),
        "enable_web_search": os.getenv("ENABLE_WEB_SEARCH", "true").strip().lower() == "true",
        "log_level": os.getenv("LOG_LEVEL", "INFO").strip(),
        "log_file": os.getenv("LOG_FILE", "data/bot.log").strip(),
    }

    if trigger_keywords is not None:
        kwargs["trigger_keywords"] = trigger_keywords

    return BotConfig(**kwargs)
