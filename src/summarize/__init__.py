"""Summarization module — factory for AI backends.

Usage:
    from .summarize import create_summarizer

    summarizer = create_summarizer(config)
    result = summarizer.summarize(messages, requester_name)
"""

import logging

from .base import AbstractSummarizer
from .claude_backend import ClaudeSummarizer
from .deepseek_backend import DeepSeekSummarizer
from .models import ParticipantContribution, SummaryResult

logger = logging.getLogger(__name__)

__all__ = [
    "AbstractSummarizer",
    "ClaudeSummarizer",
    "DeepSeekSummarizer",
    "SummaryResult",
    "ParticipantContribution",
    "create_summarizer",
]


def create_summarizer(config) -> AbstractSummarizer:
    """Create the appropriate summarizer based on config.ai_backend.

    Args:
        config: BotConfig instance with ai_backend, api keys, model, etc.

    Returns:
        An AbstractSummarizer implementation (Claude or DeepSeek).

    Raises:
        ValueError: If the configured backend is unknown.
    """
    backend = config.ai_backend.lower()

    if backend == "deepseek":
        logger.info("Creating DeepSeekSummarizer (model=%s)", config.deepseek_model)
        return DeepSeekSummarizer(
            api_key=config.deepseek_api_key,
            model=config.deepseek_model,
            chunk_size=config.chunk_size,
            enable_web_search=config.enable_web_search,
        )

    elif backend == "claude":
        logger.info("Creating ClaudeSummarizer (model=%s)", config.summarize_model)
        return ClaudeSummarizer(
            api_key=config.anthropic_api_key,
            model=config.summarize_model,
            chunk_size=config.chunk_size,
            enable_web_search=config.enable_web_search,
        )

    else:
        raise ValueError(
            f"Unknown AI_BACKEND: '{config.ai_backend}'. "
            f"Supported: 'claude', 'deepseek'."
        )
