"""Voice recognition module — SILK/AMR decode + ASR transcription.

Converts WeChat voice messages (localType=34) to text via either
local Whisper (faster-whisper, free & offline) or OpenAI Whisper API.

Usage:
    from src.voice import VoicePipeline
    pipeline = VoicePipeline(config)
    text = pipeline.process(voice_msg)  # "今天晚上吃什么"
"""

from .pipeline import VoicePipeline, VoiceCache, VoiceStats

__all__ = ["VoicePipeline", "VoiceCache", "VoiceStats"]
