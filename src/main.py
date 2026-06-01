"""WeChat Group Chat Summarizer Bot — Entry Point.

Usage:
    python -m src.main
"""

from .config import load_config
from .bot import Bot


def main() -> None:
    """Load configuration and start the bot."""
    config = load_config()
    bot = Bot(config)
    bot.run()


if __name__ == "__main__":
    main()
