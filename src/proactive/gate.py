"""ProactiveGate — decides whether the bot should evaluate speaking.

Combines message rate tracking, mode lookup, per-mode evaluation
intervals, and probabilistic gating.  Pure heuristic — zero AI cost
for the 99% of messages that get filtered out before reaching the AI.
"""

import logging
import random
import time
from typing import TYPE_CHECKING

from .modes import lookup_mode, ProactiveMode
from .rate_tracker import RateTracker

if TYPE_CHECKING:
    from ..config import BotConfig
    from ..db.store import MessageStore

logger = logging.getLogger(__name__)


class ProactiveGate:
    """Multi-level gate for proactive chat participation.

    On every message (without @mention), the gate:
    1. Records the message for rate tracking
    2. Computes current message rate
    3. Looks up the corresponding mode
    4. Checks if the evaluation interval has elapsed
    5. Rolls the dice against the mode's reply probability

    Only when ALL gates pass does it return a mode for the handler
    to call the AI with.  No daily limit, no hard cooldown — the
    per-mode interval + probability provides natural pacing.
    """

    def __init__(self, config: "BotConfig"):
        self._config = config
        self._tracker = RateTracker(config.proactive_rate_window_sec)
        # Per-group: last time we evaluated (to enforce eval_interval)
        self._last_eval: dict[str, float] = {}

    def should_speak(self, msg: dict) -> tuple[bool, ProactiveMode | None, str]:
        """Record a message and decide whether to trigger AI evaluation.

        Args:
            msg: Standardized message dict (must have 'chat_id').

        Returns:
            (should_evaluate, mode, reason) — if should_evaluate is False,
            mode is None and reason explains which gate blocked.
        """
        chat_id = msg.get("chat_id", "")
        if not chat_id:
            return False, None, "no chat_id"

        # ── Always record for rate tracking ───────────────────────
        self._tracker.record(chat_id)

        # ── Gate 1: master switch ─────────────────────────────────
        if not self._config.proactive_enabled:
            return False, None, "disabled"

        # ── Gate 2: message rate ──────────────────────────────────
        rate = self._tracker.rate(chat_id)
        mode = lookup_mode(rate, self._config)

        if mode.name == "SLEEP":
            logger.debug(
                "Proactive: rate=%.1f/min → SLEEP (chat=%s)",
                rate, chat_id[:20],
            )
            return False, None, f"rate {rate:.1f}/min → SLEEP"

        # ── Gate 3: evaluation interval ───────────────────────────
        now = time.time()
        last = self._last_eval.get(chat_id, 0)
        elapsed = now - last
        if elapsed < mode.eval_interval_sec:
            logger.debug(
                "Proactive: eval interval not met (%.0fs < %ds, mode=%s)",
                elapsed, mode.eval_interval_sec, mode.name,
            )
            return False, None, f"eval interval ({elapsed:.0f}s < {mode.eval_interval_sec}s)"

        # ── Gate 4: reply probability ─────────────────────────────
        roll = random.random()
        if roll > mode.reply_probability:
            logger.debug(
                "Proactive: probability miss (%.2f > %.2f, mode=%s)",
                roll, mode.reply_probability, mode.name,
            )
            # Update last_eval so we don't hammer the probability gate
            self._last_eval[chat_id] = now
            return False, None, f"probability miss ({roll:.2f} > {mode.reply_probability})"

        # ── All gates passed ──────────────────────────────────────
        self._last_eval[chat_id] = now
        logger.info(
            "Proactive: GATE PASSED mode=%s rate=%.1f/min "
            "interval=%ds prob=%.0f%% (chat=%s)",
            mode.name, rate, mode.eval_interval_sec,
            mode.reply_probability * 100, chat_id[:20],
        )
        return True, mode, f"mode={mode.name} rate={rate:.1f}/min"

    def record_eval(self, chat_id: str) -> None:
        """Manually update last evaluation time (e.g., after AI returned blank)."""
        self._last_eval[chat_id] = time.time()
