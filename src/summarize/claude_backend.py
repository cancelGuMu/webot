"""Claude (Anthropic) summarization backend.

Uses the Anthropic Python SDK with native structured output (Pydantic parse).
"""

import logging

import anthropic

from .base import AbstractSummarizer
from .models import SummaryResult
from .prompts import (
    SYSTEM_PROMPT,
    CHUNK_SYSTEM_PROMPT,
    MERGE_SYSTEM_PROMPT,
    build_summary_prompt,
    build_chunk_summary_prompt,
    build_merge_prompt,
)

logger = logging.getLogger(__name__)


class ClaudeSummarizer(AbstractSummarizer):
    """Summarization via Anthropic Claude API.

    Features:
    - Native structured output via client.messages.parse() + Pydantic
    - Token budget: 150K (safe margin below 200K context window)
    - Map-Reduce chunking for large conversations
    """

    # Claude-specific constants
    MODEL_HAIKU = "claude-haiku-4-5-20251001"
    MODEL_SONNET = "claude-sonnet-4-5-20250929"

    # 200K context window → 150K safe budget
    token_budget = 150_000

    retry_exceptions = (
        anthropic.RateLimitError,
        anthropic.APIConnectionError,
    )

    def __init__(self, api_key: str,
                 model: str = MODEL_HAIKU,
                 chunk_size: int = 400,
                 max_retries: int = 3,
                 enable_web_search: bool = True):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.enable_web_search = enable_web_search

    # ── Conversational chat API call (called by base class) ─────

    def _call_chat_api(self, system_prompt: str,
                        messages: list[dict]) -> str:
        """Claude-specific: uses client.messages.create() with system param."""
        response = self.client.messages.create(
            model=self.MODEL_HAIKU,
            max_tokens=400,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text or "..."

    # ── Direct summarization ──────────────────────────────────────

    def _summarize_direct(self, messages: list[dict],
                           requester_name: str) -> SummaryResult:
        """All messages in one call — uses Pydantic parse for structured output."""
        user_prompt = build_summary_prompt(messages, requester_name)

        def call():
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                output_format=SummaryResult,
            )
            return response.parsed_output

        return self._retry_with_backoff(call, "direct summarization")

    # ── Map-Reduce ────────────────────────────────────────────────

    def _summarize_map_reduce(self, chunks: list[list[dict]],
                               requester_name: str) -> SummaryResult:
        """Map: summarize each chunk. Reduce: merge into structured result."""
        total = len(chunks)

        chunk_summaries: list[str] = []
        for i, chunk in enumerate(chunks, 1):
            logger.info(
                f"Map phase: chunk {i}/{total} ({len(chunk)} messages)"
            )
            summary = self._summarize_chunk(chunk, i, total, requester_name)
            chunk_summaries.append(summary)

        if not chunk_summaries:
            return SummaryResult(
                summary_text="无法生成总结。",
                topics=[],
                participants=[],
            )

        logger.info(f"Reduce phase: merging {len(chunk_summaries)} summaries")
        return self._merge_chunk_summaries(chunk_summaries, requester_name)

    def _summarize_chunk(self, chunk: list[dict], chunk_num: int,
                          total: int, requester_name: str) -> str:
        """Extract key facts from a single chunk (plain text output)."""
        user_prompt = build_chunk_summary_prompt(
            chunk, chunk_num, total, requester_name
        )

        def call():
            response = self.client.messages.create(
                model=self.MODEL_HAIKU,
                max_tokens=1024,
                system=CHUNK_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text

        return self._retry_with_backoff(call, f"chunk {chunk_num}/{total}")

    def _merge_chunk_summaries(self, chunk_summaries: list[str],
                                requester_name: str) -> SummaryResult:
        """Merge chunk summaries into final structured result."""
        user_prompt = build_merge_prompt(chunk_summaries, requester_name)

        def call():
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=4096,
                system=MERGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                output_format=SummaryResult,
            )
            return response.parsed_output

        return self._retry_with_backoff(call, "merge chunk summaries")
