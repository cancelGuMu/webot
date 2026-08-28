"""DeepSeek summarization backend.

DeepSeek API is OpenAI-compatible, so all logic lives in
``OpenAISummarizer``.  This subclass only adds DeepSeek-specific defaults:
- model IDs (deepseek-v4-pro / deepseek-v4-flash)
- a 900K token budget (safe margin below DeepSeek's 1M context)
- ``thinking: disabled`` extra_body (DeepSeek's thinking mode toggle)

Base URL: https://api.deepseek.com
Docs: https://platform.deepseek.com/api-docs
"""

from .openai_backend import OpenAISummarizer


class DeepSeekSummarizer(OpenAISummarizer):
    """Summarization via DeepSeek API (OpenAI-compatible)."""

    # DeepSeek API base URL
    DEEPSEEK_BASE_URL = "https://api.deepseek.com"

    # DeepSeek model IDs
    MODEL_PRO = "deepseek-v4-pro"      # V4 Pro (flagship, 1M context)
    MODEL_FLASH = "deepseek-v4-flash"  # V4 Flash (fast/cheap, 1M context)
    MODEL_DEFAULT = MODEL_PRO

    # 1M context window → 900K safe budget
    token_budget = 900_000

    # DeepSeek requires thinking mode to be explicitly disabled.
    disable_thinking = True

    def __init__(self, api_key: str,
                 model: str = MODEL_DEFAULT,
                 base_url: str = DEEPSEEK_BASE_URL,
                 chunk_size: int = 400,
                 max_retries: int = 3):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            chunk_size=chunk_size,
            max_retries=max_retries,
        )
