"""Voice → text pipeline — locator + decoder + ASR + cache.

Entry point is ``VoicePipeline.process(msg)`` which takes a WCDB raw
message dict and returns the recognised text (or None on failure).
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from .file_locator import VoiceFileLocator, _extract_msg_svr_id
from .decoder import SilkDecoder, DecodeError
from .asr import AbstractASR, ASRError, create_asr

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE_MAX_ENTRIES = 10_000
_CACHE_TTL_SEC = 7 * 86400  # 7 days (roughly matches WeChat cleanup window)


class VoiceCache:
    """Persistent JSON cache to avoid re-transcribing the same voice message.

    Key = msg_svr_id (WeChat server message ID, globally unique).
    """

    def __init__(self, cache_path: Path) -> None:
        self._path = cache_path
        self._data: dict[str, dict] = {}
        self._dirty = False
        self._load()

    # -- Public ------------------------------------------------------------

    def get(self, msg_svr_id: str) -> Optional[str]:
        """Return cached text, or None."""
        entry = self._data.get(msg_svr_id)
        if entry is None:
            return None
        # TTL check
        if time.time() - entry.get("ts", 0) > _CACHE_TTL_SEC:
            del self._data[msg_svr_id]
            self._dirty = True
            return None
        logger.debug("VoiceCache hit: %s", msg_svr_id[:16])
        return entry.get("text")

    def set(self, msg_svr_id: str, text: str, confidence: float) -> None:
        """Store a transcription result."""
        self._data[msg_svr_id] = {
            "text": text,
            "confidence": confidence,
            "ts": int(time.time()),
        }
        self._dirty = True
        # Prune if over limit
        if len(self._data) > _CACHE_MAX_ENTRIES:
            self._prune()

    def flush(self) -> None:
        """Persist to disk."""
        if not self._dirty:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._dirty = False
        logger.debug("VoiceCache flushed (%d entries)", len(self._data))

    # -- Internal ----------------------------------------------------------

    def _load(self) -> None:
        try:
            if self._path.exists():
                self._data = json.loads(
                    self._path.read_text(encoding="utf-8")
                )
                logger.debug("VoiceCache loaded (%d entries)", len(self._data))
        except Exception:
            logger.warning("VoiceCache load failed, starting fresh")
            self._data = {}

    def _prune(self) -> None:
        """Remove expired entries."""
        now = time.time()
        stale = [
            k for k, v in self._data.items()
            if now - v.get("ts", 0) > _CACHE_TTL_SEC
        ]
        for k in stale:
            del self._data[k]
        logger.debug("VoiceCache pruned %d expired entries", len(stale))


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class VoiceStats:
    """Lightweight counters for monitoring."""

    def __init__(self) -> None:
        self.total = 0
        self.success = 0
        self.cache_hit = 0
        self.file_not_found = 0
        self.decode_failed = 0
        self.asr_failed = 0

    def snapshot(self) -> dict:
        return {
            "total": self.total,
            "success": self.success,
            "cache_hit": self.cache_hit,
            "file_not_found": self.file_not_found,
            "decode_failed": self.decode_failed,
            "asr_failed": self.asr_failed,
        }

    def log_summary(self) -> None:
        s = self.snapshot()
        logger.info(
            "VoiceStats: total=%d success=%d cache=%d miss_file=%d "
            "decode_err=%d asr_err=%d",
            s["total"], s["success"], s["cache_hit"],
            s["file_not_found"], s["decode_failed"], s["asr_failed"],
        )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

# Confidence threshold below which we add a "[可能不准确]" prefix.
_LOW_CONFIDENCE_THRESHOLD = 0.6


class VoicePipeline:
    """End-to-end voice → text pipeline.

    Usage::

        pipeline = VoicePipeline(config)
        text = pipeline.process(voice_msg)
        # → "今天晚上吃什么"
    """

    def __init__(self, config) -> None:
        """
        Args:
            config: BotConfig instance.
        """
        self._enabled = getattr(config, "voice_asr_enabled", False)
        if not self._enabled:
            logger.info("VoicePipeline disabled (VOICE_ASR_ENABLED=false)")
            return

        data_dir = getattr(config, "wechat_data_dir", "")
        if not data_dir:
            logger.warning(
                "VoicePipeline: wechat_data_dir not configured — "
                "file locator will probably fail"
            )

        self._locator = VoiceFileLocator(data_dir)
        self._decoder = SilkDecoder()
        self._asr = create_asr(config)
        self._cache = VoiceCache(Path("data/voice_cache.json"))
        self._stats = VoiceStats()
        logger.info("VoicePipeline initialised (backend=%s)",
                     getattr(config, "voice_asr_backend", "?"))

    # -- Public ------------------------------------------------------------

    def process(self, msg: dict) -> Optional[str]:
        """Transcribe a voice message.

        Args:
            msg: WCDB raw message dict (must have localType=34).

        Returns:
            Recognised text, e.g. "今天晚上吃什么", or None on failure.
            On failure the caller should fall back to "[语音]".
        """
        if not self._enabled:
            return None

        self._stats.total += 1
        msg_svr_id = _extract_msg_svr_id(msg)

        # ── Cache lookup ────────────────────────────────────────────
        if msg_svr_id:
            cached = self._cache.get(msg_svr_id)
            if cached is not None:
                self._stats.cache_hit += 1
                return cached

        # ── Locate file ─────────────────────────────────────────────
        audio_path = self._locator.find_voice_file(msg)
        if not audio_path:
            self._stats.file_not_found += 1
            return None

        # ── Decode → WAV ────────────────────────────────────────────
        try:
            wav_path = self._decoder.decode(audio_path)
        except DecodeError:
            logger.exception("SILK decode failed for msg_svr_id=%s", msg_svr_id)
            self._stats.decode_failed += 1
            return None

        # ── ASR ─────────────────────────────────────────────────────
        try:
            language = "zh"  # Could read from config later
            result = self._asr.transcribe(wav_path, language=language)
        except ASRError:
            logger.exception("ASR failed for msg_svr_id=%s", msg_svr_id)
            self._stats.asr_failed += 1
            return None
        finally:
            # Clean up temp WAV immediately
            self._cleanup_temp(wav_path)

        # ── Cache + stats ───────────────────────────────────────────
        text = result.text
        if not text:
            self._stats.asr_failed += 1
            return None

        if msg_svr_id:
            self._cache.set(msg_svr_id, text, result.confidence)

        self._stats.success += 1

        # ── Low-confidence flag ─────────────────────────────────────
        if result.confidence < _LOW_CONFIDENCE_THRESHOLD:
            logger.info(
                "Low-confidence result (%.2f): '%s'...",
                result.confidence, text[:40],
            )
            return f"[可能不准确] {text}"

        return text

    def flush(self) -> None:
        """Persist cache to disk (call before shutdown)."""
        if self._enabled:
            self._cache.flush()
            self._stats.log_summary()

    @staticmethod
    def _cleanup_temp(wav_path: Path) -> None:
        try:
            wav_path.unlink(missing_ok=True)
        except Exception:
            pass
