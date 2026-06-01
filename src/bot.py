"""Bot orchestrator — wires all components and manages the bot lifecycle.

This is the central class that initializes, starts, and gracefully shuts down
the WeChat summarizer bot. It replaces the inline wiring previously in main.py.
"""

import logging
import signal

from .config import BotConfig
from .db import initialize_db, MessageStore
from .summarize import create_summarizer
from .trigger import TriggerDetector
from .nickname import NicknameService
from .admin import AdminCommandHandler
from .router import MessageRouter
from .utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class Bot:
    """Orchestrates the WeChat summarizer bot.

    Usage:
        config = load_config()
        bot = Bot(config)
        bot.run()
    """

    def __init__(self, config: BotConfig):
        self._config = config
        self._conn = None
        self._backend = None

    def run(self) -> None:
        """Initialize all components and start the bot. Blocks until stopped."""
        config = self._config

        # ── 1. Logging ──────────────────────────────────────────
        setup_logging(level=config.log_level, log_file=config.log_file)
        self._log_banner()

        # ── 2. Database ─────────────────────────────────────────
        self._conn = initialize_db(config.db_path)
        store = MessageStore(self._conn)

        # ── 3. Components ───────────────────────────────────────
        detector = TriggerDetector(
            keywords=config.trigger_keywords,
            bot_display_name=config.bot_display_name,
        )
        summarizer = create_summarizer(config)
        nickname_service = NicknameService()
        admin_handler = AdminCommandHandler(nickname_service)

        router = MessageRouter(
            store=store,
            detector=detector,
            summarizer=summarizer,
            admin_handler=admin_handler,
            nickname_service=nickname_service,
            config=config,
        )

        # ── 4. WeChat backend ───────────────────────────────────
        backend = self._create_wechat_backend()
        self._backend = backend

        # ── 5. Signal handling ──────────────────────────────────
        def shutdown(signum, frame):
            logger.info("Received signal %d. Shutting down...", signum)
            backend.stop()

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        # ── 6. Start listening (blocks) ─────────────────────────
        try:
            logger.info("Bot is running. Press Ctrl+C to stop.")
            backend.start(router.handle)
        except KeyboardInterrupt:
            pass
        finally:
            self._conn.close()
            logger.info("Bot shut down gracefully.")

    # ── Helpers ──────────────────────────────────────────────────

    def _log_banner(self) -> None:
        """Log the startup banner with configuration details."""
        config = self._config
        logger.info("=" * 50)
        logger.info("WeChat Summarizer Bot starting...")
        logger.info("WeChat backend: %s", config.wechat_backend)
        logger.info("AI backend: %s", config.ai_backend)
        if config.ai_backend == "deepseek":
            logger.info("Model: %s", config.deepseek_model)
        else:
            logger.info("Model: %s", config.summarize_model)
        logger.info("Bot name: %s", config.bot_display_name)
        if config.wechat_groups:
            logger.info("Groups: %s", config.wechat_groups)
        logger.info("DB path: %s", config.db_path)
        logger.info("=" * 50)

    def _create_wechat_backend(self):
        """Create the appropriate WeChat backend based on config.

        Returns an AbstractWeChatBackend instance.
        """
        config = self._config
        groups = [
            g.strip() for g in config.wechat_groups.split(",") if g.strip()
        ]

        if config.wechat_backend == "weflow":
            from .wechat.weflow_backend import WeFlowBackend
            return WeFlowBackend(
                bot_display_name=config.bot_display_name,
                groups=groups,
                poll_sec=config.poll_interval_sec,
                weflow_url=config.weflow_url,
                access_token=config.weflow_token,
            )

        elif config.wechat_backend == "uia":
            from .wechat.uia_backend import UiaBackend
            return UiaBackend(
                bot_display_name=config.bot_display_name,
                groups=groups,
                poll_sec=config.poll_interval_sec,
            )

        elif config.wechat_backend == "wx4py":
            from .wechat.wx4py_backend import Wx4pyBackend
            return Wx4pyBackend(
                bot_display_name=config.bot_display_name,
                groups=groups,
                poll_interval_sec=config.poll_interval_sec,
            )

        else:
            raise ValueError(
                f"Unknown WECHAT_BACKEND: '{config.wechat_backend}'. "
                f"Supported: weflow, uia, wx4py."
            )
