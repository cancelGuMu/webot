"""WeChat Group Chat Summarizer Bot — Entry Point.

Usage:
    python -m src.main
    python -m src.main --dry-run
"""

import sys

from .config import load_config, BotConfig


def _mask(s: str, keep: int = 6) -> str:
    """Mask a secret string, showing only the first and last few characters."""
    if not s:
        return "(not set)"
    if len(s) <= keep * 2:
        return "*" * len(s)
    return s[:keep] + "***" + s[-keep:]


def _print_config_summary(config: BotConfig) -> None:
    """Print a human-readable summary of the loaded configuration (secrets masked)."""
    print()
    print("Configuration Summary")
    print("─" * 50)
    print(f"  AI Backend:              {config.ai_backend}")
    print(f"  Summarize Model:         {config.summarize_model}")
    print(f"  Anthropic API Key:       {_mask(config.anthropic_api_key)}")
    if config.ai_backend == "deepseek":
        print(f"  DeepSeek API Key:        {_mask(config.deepseek_api_key)}")
        print(f"  DeepSeek Model:          {config.deepseek_model}")
    print(f"  WeChat Backend:          {config.wechat_backend}")
    print(f"  WeChat Groups:           {config.wechat_groups or '(all)'}")
    if config.wechat_backend == "weflow":
        print(f"  WeFlow URL:              {config.weflow_url}")
        print(f"  WeFlow Token:            {_mask(config.weflow_token)}")
    print(f"  Bot Display Name:        {config.bot_display_name}")
    print(f"  Admin wxid:              {config.admin_wxid or '(not set)'}")
    print(f"  Trigger Keywords:        {config.trigger_keywords}")
    print(f"  DB Path:                 {config.db_path}")
    print(f"  Poll Interval (sec):     {config.poll_interval_sec}")
    print(f"  Dedup Window (sec):      {config.dedup_window_sec}")
    print(f"  Max Msgs per Summary:    {config.max_messages_for_summary}")
    print(f"  Chunk Size:              {config.chunk_size}")
    print(f"  Fallback Window (hrs):   {config.fallback_window_hours}")
    print(f"  Web Search Enabled:      {config.enable_web_search}")
    print(f"  Proactive Enabled:       {config.proactive_enabled}")
    if config.proactive_enabled:
        print(f"    Rate Window (sec):     {config.proactive_rate_window_sec}")
        print(f"    Rate Quiet:            {config.proactive_rate_quiet}")
        print(f"    Rate Casual:           {config.proactive_rate_casual}")
        print(f"    Rate Lively:           {config.proactive_rate_lively}")
        print(f"    Rate Burst:            {config.proactive_rate_burst}")
    print(f"  Log Level:               {config.log_level}")
    print(f"  Log File:                {config.log_file}")
    print("─" * 50)
    print()


def main() -> None:
    """Load configuration and start the bot.

    With --dry-run: validate .env config and print a summary, then exit.
    """
    dry_run = "--dry-run" in sys.argv

    config = load_config()

    if dry_run:
        _print_config_summary(config)
        print("Dry-run mode: config loaded successfully. Bot would start polling now.")
        return

    from .bot import Bot
    bot = Bot(config)
    bot.run()


if __name__ == "__main__":
    main()
