"""Bot orchestrator — wires all components and manages the bot lifecycle.

This is the central class that initializes, starts, and gracefully shuts down
the WeChat summarizer bot. It replaces the inline wiring previously in main.py.
"""

import json
import logging
import os
import signal
import threading
import time
from pathlib import Path

from .config import BotConfig, PROJECT_ROOT
from .db import initialize_db, MessageStore
from .summarize import create_summarizer
from .trigger import TriggerDetector
from .nickname import NicknameService
from .admin import AdminCommandHandler
from .router import MessageRouter
from .utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Background health heartbeat: periodic logging + JSON status file.

    Runs in a daemon thread so it never blocks shutdown.
    """

    def __init__(self, summarizer, router, conn, backend, config: BotConfig,
                 on_tick=None):
        self._summarizer = summarizer
        self._router = router
        self._conn = conn
        self._backend = backend
        self._config = config
        self._on_tick = on_tick or (lambda **kw: None)
        self._start_time = time.time()
        self._running = False
        self._thread: threading.Thread | None = None

    # ── Public API ──────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Health monitor started (interval=5m, daemon)")

    def stop(self) -> None:
        self._running = False

    # ── Internals ───────────────────────────────────────────────────

    def _run(self) -> None:
        while self._running:
            time.sleep(300)  # 5 minutes
            if not self._running:
                break
            try:
                self._tick()
            except Exception:
                logger.exception("Health monitor tick failed")

    def _tick(self) -> None:
        uptime_sec = int(time.time() - self._start_time)
        uptime_min = uptime_sec // 60
        msgs = self._router.messages_processed

        db_status = self._check_db()
        wechat_status = self._check_wechat_hwnd()
        last_api_str = self._last_api_ago()

        # Push to Web UI
        self._on_tick(
            uptime_sec=uptime_sec,
            messages_processed=msgs,
            db_ok=db_status == "OK",
            last_api_call_sec_ago=int(time.time() - self._summarizer.last_api_call_time)
                if self._summarizer.last_api_call_time > 0 else -1,
        )

        logger.info(
            "HEARTBEAT: uptime=%dm, msgs=%d, db=%s, wechat=%s, last_api=%s",
            uptime_min, msgs, db_status, wechat_status, last_api_str,
        )

        self._write_status_json()

    def _check_db(self) -> str:
        """Check database connection is alive."""
        try:
            self._conn.execute("SELECT 1")
            return "OK"
        except Exception as e:
            return f"ERR:{e}"

    def _check_wechat_hwnd(self) -> str:
        """Check WeChat window HWND."""
        try:
            wc = self._backend._window
            hwnd = wc._cached_hwnd
            if hwnd is not None:
                if wc._validate_hwnd(hwnd):
                    return f"HWND_{hwnd}"
            return "no_hwnd"
        except Exception as e:
            return f"ERR:{e}"

    def _last_api_ago(self) -> str:
        """Human-readable 'time since last successful API call'."""
        last = self._summarizer.last_api_call_time
        if last <= 0:
            return "never"
        ago = int(time.time() - last)
        if ago < 60:
            return f"{ago}s_ago"
        elif ago < 3600:
            return f"{ago // 60}m_ago"
        else:
            return f"{ago // 3600}h_ago"

    def _write_status_json(self) -> None:
        """Write a lightweight status file for external watchdogs."""
        status = {
            "uptime_sec": int(time.time() - self._start_time),
            "messages_processed": self._router.messages_processed,
            "db_ok": self._check_db() == "OK",
            "wechat_backend": self._config.wechat_backend,
            "last_api_call_sec_ago": (
                int(time.time() - self._summarizer.last_api_call_time)
                if self._summarizer.last_api_call_time > 0
                else -1
            ),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        out_dir = PROJECT_ROOT / "data"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "bot_status.json"
        tmp = path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(status, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)  # atomic write
        except Exception:
            logger.exception("Failed to write status JSON")


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
        self._health: HealthMonitor | None = None

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

        # ── 4. Web UI status ────────────────────────────────────
        # (web server already started by desktop.py)
        try:
            from .web.server import update_status
            update_status(
                wechat_backend=config.wechat_backend,
                ai_backend=config.ai_backend,
            )
            self._update_status = update_status
        except Exception as e:
            logger.debug("Web UI status: %s", e)
            self._update_status = lambda **kw: None

        # ── 5. WeChat backend ───────────────────────────────────
        backend = self._create_wechat_backend()
        self._backend = backend

        # ── 6. Health monitor ───────────────────────────────────
        self._health = HealthMonitor(
            summarizer=summarizer,
            router=router,
            conn=self._conn,
            backend=backend,
            config=config,
            on_tick=self._update_status,
        )
        self._health.start()

        # ── 6. Signal handling ──────────────────────────────────
        def shutdown(signum, frame):
            logger.info("Received signal %d. Shutting down...", signum)
            backend.stop()
            if self._health:
                self._health.stop()

        try:
            signal.signal(signal.SIGINT, shutdown)
            signal.signal(signal.SIGTERM, shutdown)
        except ValueError:
            # Running in a thread — signals not available
            pass

        # ── 7. Start listening (blocks) ─────────────────────────
        #
        # DESIGN NOTE — synchronous poll loop:
        #   backend.start() runs a tight while-loop: poll → callback → sleep.
        #   The callback (router.handle) may trigger summarization via the
        #   AI backend, which can take 5–30 seconds depending on model
        #   latency and message volume. Because the loop is single-threaded,
        #   a long-running callback *delays the next poll cycle*. Messages
        #   arriving during summarization are not picked up until the
        #   callback returns and the next iteration begins.
        #
        # Trade-offs:
        #   + Simple — no threads, no queues, no coordination
        #   + Predictable — one message at a time, no concurrent UIA
        #   - Poll latency — bursty summarization adds jitter
        #   - Head-of-line blocking — a slow reply blocks ALL groups
        #
        # Mitigations already in place:
        #   - poll_interval_sec controls idle cadence (default 1 s)
        #   - Reply sends happen inline; admin commands return instantly
        #   - Health monitor runs in its own daemon thread
        #
        # Future options (not implemented):
        #   - Fire-and-forget: queue the callback work and return immediately
        #   - Dedicated summarizer thread with a work queue
        #   - Async I/O (asyncio) for the poll loop
        try:
            logger.info("Bot is running. Press Ctrl+C to stop.")
            backend.start(router.handle)
        except KeyboardInterrupt:
            pass
        finally:
            if self._health:
                self._health.stop()
            if self._conn is not None:
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

        if config.wechat_backend == "wcdb":
            from .wechat.wcdb_backend import WcdbBackend
            return WcdbBackend(
                bot_display_name=config.bot_display_name,
                groups=groups,
                poll_sec=config.poll_interval_sec,
            )

        else:
            raise ValueError(
                f"Unknown WECHAT_BACKEND: '{config.wechat_backend}'. "
                f"Supported: wcdb."
            )
