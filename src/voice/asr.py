"""ASR (Automatic Speech Recognition) — two backends.

- LocalWhisperASR:  faster-whisper, free, offline, ~1 GB RAM (default)
- OpenAiWhisperASR: OpenAI Whisper API, $0.006/min, zero local memory
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class TranscribeResult:
    text: str            # Recognised text
    confidence: float    # 0.0 ~ 1.0
    duration_sec: float  # Audio length in seconds


class ASRError(Exception):
    """Raised when transcription fails."""


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class AbstractASR(ABC):
    """Voice → text interface."""

    @abstractmethod
    def transcribe(self, audio_path: Path,
                   language: str = "zh") -> TranscribeResult:
        """Transcribe an audio file (.wav) to text."""
        ...


# ---------------------------------------------------------------------------
# Local Whisper (faster-whisper)
# ---------------------------------------------------------------------------

class LocalWhisperASR(AbstractASR):
    """Local Whisper model via faster-whisper.

    The model is downloaded on first use to ``data/models/`` and kept in
    memory thereafter, so subsequent calls are fast and offline.
    """

    def __init__(self, model_size: str = "small",
                 model_dir: str = "data/models") -> None:
        """
        Args:
            model_size: tiny / base / small / medium (small ≈ 1 GB RAM).
            model_dir:  Directory to cache downloaded models.
        """
        self._model_size = model_size
        self._model_dir = model_dir
        self._model = None  # lazy-init

    # -- Public API --------------------------------------------------------

    def transcribe(self, audio_path: Path,
                   language: str = "zh") -> TranscribeResult:
        model = self._get_model()

        try:
            segments, info = model.transcribe(
                str(audio_path),
                language=language,
                beam_size=5,
                vad_filter=False,
            )
        except Exception as exc:
            raise ASRError(f"LocalWhisper transcribe failed: {exc}") from exc

        # Collect text from all segments
        text_parts = []
        total_confidence = 0.0
        seg_count = 0
        for seg in segments:
            if seg.text:
                text_parts.append(seg.text.strip())
            total_confidence += getattr(seg, "avg_logprob", -1.0)
            seg_count += 1

        text = " ".join(text_parts)
        # Convert avg_logprob → confidence estimate (heuristic)
        if seg_count > 0:
            avg_logprob = total_confidence / seg_count
            # Map logprob [-2, 0] roughly to [0, 1]
            confidence = min(1.0, max(0.0, (avg_logprob + 2.0) / 2.0))
        else:
            confidence = 0.0

        logger.info(
            "LocalWhisper: %.1fs audio → %d chars (confidence=%.2f)",
            info.duration, len(text), confidence,
        )
        return TranscribeResult(
            text=text,
            confidence=confidence,
            duration_sec=info.duration,
        )

    # -- Internal ----------------------------------------------------------

    def _get_model(self):
        if self._model is not None:
            return self._model

        from faster_whisper import WhisperModel

        logger.info(
            "Loading local Whisper model '%s' (first use downloads ~500 MB) ...",
            self._model_size,
        )
        # Compute type: auto-select best for current hardware
        self._model = WhisperModel(
            self._model_size,
            device="cpu",
            compute_type="int8",
            download_root=self._model_dir,
        )
        logger.info("LocalWhisper model loaded (size=%s)", self._model_size)
        return self._model


# ---------------------------------------------------------------------------
# OpenAI Whisper API
# ---------------------------------------------------------------------------

class OpenAiWhisperASR(AbstractASR):
    """OpenAI Whisper API — cloud-based transcription.

    Uses the same ``openai`` client the project already depends on.
    Cost: $0.006 / minute (no free tier).
    """

    def __init__(self, api_key: str = "",
                 base_url: str = "") -> None:
        """
        Args:
            api_key:  OpenAI API key (falls back to OPENAI_API_KEY env var).
            base_url: Custom API endpoint (e.g. proxy).
        """
        self._api_key = api_key
        self._base_url = base_url
        self._client = None  # lazy-init

    # -- Public API --------------------------------------------------------

    def transcribe(self, audio_path: Path,
                   language: str = "zh") -> TranscribeResult:
        client = self._get_client()

        try:
            with open(audio_path, "rb") as fh:
                result = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=fh,
                    language=language,
                    response_format="verbose_json",
                )
        except Exception as exc:
            raise ASRError(f"OpenAI Whisper API call failed: {exc}") from exc

        text = result.text.strip() if result.text else ""
        # Whisper API returns logprob-based segments; extract avg confidence
        confidence = 0.8  # default when no detailed info
        duration = 0.0
        if hasattr(result, "segments") and result.segments:
            logprobs = []
            for seg in result.segments:
                if hasattr(seg, "avg_logprob") and seg.avg_logprob is not None:
                    logprobs.append(seg.avg_logprob)
            if logprobs:
                avg = sum(logprobs) / len(logprobs)
                confidence = min(1.0, max(0.0, (avg + 2.0) / 2.0))
        if hasattr(result, "duration") and result.duration:
            duration = float(result.duration)

        logger.info(
            "OpenAIWhisper: %.1fs audio → %d chars (confidence=%.2f)",
            duration, len(text), confidence,
        )
        return TranscribeResult(
            text=text,
            confidence=float(confidence),
            duration_sec=duration,
        )

    # -- Internal ----------------------------------------------------------

    def _get_client(self):
        if self._client is not None:
            return self._client

        import os as _os
        from openai import OpenAI

        kwargs = {}
        api_key = self._api_key or _os.getenv("OPENAI_API_KEY", "")
        if api_key:
            kwargs["api_key"] = api_key
        if self._base_url:
            kwargs["base_url"] = self._base_url

        self._client = OpenAI(**kwargs)
        return self._client


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_asr(config) -> AbstractASR:
    """Build the ASR backend specified in *config*.

    Args:
        config: A BotConfig instance (or any object with the voice_* fields).

    Returns:
        An AbstractASR implementation.
    """
    backend = getattr(config, "voice_asr_backend", "local_whisper")

    if backend == "openai_whisper":
        logger.info("ASR backend: OpenAI Whisper API (cloud)")
        return OpenAiWhisperASR(
            api_key=getattr(config, "voice_openai_api_key", ""),
            base_url=getattr(config, "voice_openai_base_url", ""),
        )
    else:
        logger.info("ASR backend: Local Whisper (faster-whisper, offline)")
        return LocalWhisperASR(
            model_size=getattr(config, "voice_local_model", "small"),
        )
