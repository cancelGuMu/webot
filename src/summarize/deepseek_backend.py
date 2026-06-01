"""DeepSeek summarization backend.

DeepSeek API is OpenAI-compatible. Uses the openai Python SDK with
tool calling for structured output.

Base URL: https://api.deepseek.com
Docs: https://platform.deepseek.com/api-docs
"""

import json
import logging

from openai import OpenAI, RateLimitError, APIConnectionError, APIStatusError

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

# DeepSeek API base URL
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# Tool schema for structured output — matches SummaryResult Pydantic model
STORE_SUMMARY_TOOL = {
    "type": "function",
    "function": {
        "name": "store_summary",
        "description": "Store a structured summary of a group chat conversation",
        "parameters": {
            "type": "object",
            "properties": {
                "summary_text": {
                    "type": "string",
                    "description": "A 2-4 sentence overview of what was discussed",
                },
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Main topics discussed in the conversation",
                },
                "participants": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "contributions": {"type": "string"},
                        },
                        "required": ["name", "contributions"],
                        "additionalProperties": False,
                    },
                    "description": "Key participants and what they contributed",
                },
            },
            "required": ["summary_text", "topics", "participants"],
            "additionalProperties": False,
        },
    },
}


def _parse_summary_from_tool_call(response) -> SummaryResult:
    """Extract SummaryResult from DeepSeek response.

    Tries in order:
    1. Tool call → parse arguments JSON
    2. Content is valid JSON → parse as SummaryResult
    3. Plain text content → wrap in basic SummaryResult
    """
    choice = response.choices[0]
    msg = choice.message

    # Strategy 1: tool call with structured data
    if msg.tool_calls:
        args_json = msg.tool_calls[0].function.arguments
        data = json.loads(args_json)

        participants = []
        for p in data.get("participants", []):
            if isinstance(p, dict):
                participants.append(p)
            elif isinstance(p, str):
                participants.append({"name": p, "contributions": ""})

        return SummaryResult(
            summary_text=data.get("summary_text", ""),
            topics=data.get("topics", []),
            participants=participants,
        )

    # Strategy 2: JSON in message content
    content = msg.content or ""
    if isinstance(content, str) and content.strip():
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "summary_text" in data:
                return SummaryResult(**{
                    k: v for k, v in data.items()
                    if k in ("summary_text", "topics", "participants")
                })
        except (json.JSONDecodeError, Exception):
            pass

    # Strategy 3: plain text — wrap in minimal SummaryResult
    content = (content or "").strip()
    if content:
        logger.info("DeepSeek returned plain text (no tool call), wrapping as summary")
        return SummaryResult(
            summary_text=content[:2000],
            topics=[],
            participants=[],
        )

    raise RuntimeError("DeepSeek returned empty response")


class DeepSeekSummarizer(AbstractSummarizer):
    """Summarization via DeepSeek API (OpenAI-compatible).

    Uses tool calling for structured output since DeepSeek doesn't have
    native Pydantic parsing like Claude.

    Features:
    - OpenAI-compatible tool calling for structured output
    - Token budget: 100K (safe margin below 128K context window)
    - Map-Reduce chunking for large conversations
    """

    # DeepSeek model IDs
    MODEL_PRO = "deepseek-v4-pro"      # V4 Pro (flagship, 1M context)
    MODEL_FLASH = "deepseek-v4-flash"  # V4 Flash (fast/cheap, 1M context)

    # 1M context window → 900K safe budget
    token_budget = 900_000

    retry_exceptions = (RateLimitError, APIConnectionError)

    def __init__(self, api_key: str,
                 model: str = MODEL_PRO,
                 base_url: str = DEEPSEEK_BASE_URL,
                 chunk_size: int = 400,
                 max_retries: int = 3,
                 enable_web_search: bool = True):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.enable_web_search = enable_web_search

    # ── Conversational chat API call (called by base class) ─────

    def _call_chat_api(self, system_prompt: str,
                        messages: list[dict]) -> str:
        """DeepSeek-specific: uses chat.completions.create() with system role."""
        api_messages = [{"role": "system", "content": system_prompt}] + messages
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=400,
            messages=api_messages,
            extra_body={"thinking": {"type": "disabled"}},
        )
        return response.choices[0].message.content or "..."

    # ── Direct summarization ──────────────────────────────────────

    def _summarize_direct(self, messages: list[dict],
                           requester_name: str) -> SummaryResult:
        """All messages in one call — uses tool calling for structured output."""
        user_prompt = build_summary_prompt(messages, requester_name)

        def call():
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                tools=[STORE_SUMMARY_TOOL],
                tool_choice="auto",  # V4 Flash doesn't support forced tool_choice with thinking
                extra_body={"thinking": {"type": "disabled"}},
            )
            return _parse_summary_from_tool_call(response)

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
        """Extract key facts from a single chunk (plain text, no structured output)."""
        user_prompt = build_chunk_summary_prompt(
            chunk, chunk_num, total, requester_name
        )

        def call():
            response = self.client.chat.completions.create(
                model=self.MODEL_FLASH,  # Flash for chunk extraction (fast/cheap)
                max_tokens=1024,
                messages=[
                    {"role": "system", "content": CHUNK_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content or ""

        return self._retry_with_backoff(call, f"chunk {chunk_num}/{total}")

    def _merge_chunk_summaries(self, chunk_summaries: list[str],
                                requester_name: str) -> SummaryResult:
        """Merge chunk summaries into final structured result via tool calling."""
        user_prompt = build_merge_prompt(chunk_summaries, requester_name)

        def call():
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": MERGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                tools=[STORE_SUMMARY_TOOL],
                tool_choice="auto",
                extra_body={"thinking": {"type": "disabled"}},
            )
            return _parse_summary_from_tool_call(response)

        return self._retry_with_backoff(call, "merge chunk summaries")
