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
    MEMORY_CONSOLE_PROMPT,
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
                 base_url: str = "https://api.anthropic.com",
                 chunk_size: int = 400,
                 max_retries: int = 3):
        self.client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
        self.model = model
        self.chunk_size = chunk_size
        self.max_retries = max_retries

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
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                output_format=SummaryResult,
            )
            return response.parsed_output

        return self._retry_with_backoff(call, "direct summarization")

    # ── Map-Reduce ────────────────────────────────────────────────

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
                max_tokens=8192,
                system=MERGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                output_format=SummaryResult,
            )
            return response.parsed_output

        return self._retry_with_backoff(call, "merge chunk summaries")

    # ── Memory consolidation (Claude backend) ───────────────────────

    def consolidate_memory(self, existing_memory: str,
                           new_messages: list[dict]) -> str:
        """Update group memory by incorporating new messages.

        Uses Claude Haiku for low cost and latency.  Returns the updated
        first-person diary-style memory text (≤2000 chars).

        Args:
            existing_memory: Current memory text (empty string if first time).
            new_messages: List of new message dicts to incorporate.

        Returns:
            Updated memory text, or existing_memory unchanged on failure.
        """
        if not new_messages:
            return existing_memory

        # Format new messages for the prompt
        msg_lines = []
        for m in new_messages[-200:]:  # cap at 200 messages per consolidation
            sender = m.get("sender_name", "?")
            content = m.get("content", "")
            if content:
                msg_lines.append(f"{sender}: {content}")

        if not msg_lines:
            return existing_memory

        existing_display = (
            existing_memory if existing_memory
            else "（暂无，这是第一次整理记忆）"
        )

        system_prompt = MEMORY_CONSOLE_PROMPT.format(
            existing_memory=existing_display,
            new_messages="\n".join(msg_lines),
        )

        def call():
            response = self.client.messages.create(
                model=self.MODEL_HAIKU,
                max_tokens=2048,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": "请输出更新后的完整记忆日记。",
                }],
            )
            text = response.content[0].text or ""
            # Enforce 2000-char soft cap
            if len(text) > 2000:
                text = text[:2000]
            return text.strip()

        try:
            return self._retry_with_backoff(call, "memory consolidation")
        except RuntimeError as e:
            logger.warning("Memory consolidation failed: %s", e)
            return existing_memory  # don't lose existing memory on failure
