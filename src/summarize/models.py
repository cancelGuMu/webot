"""Pydantic models for structured chat summarization output.

Shared across all AI backends (Claude, DeepSeek, etc.).
"""

from pydantic import BaseModel, ConfigDict


class ParticipantContribution(BaseModel):
    """A participant's contribution to the conversation."""
    model_config = ConfigDict(extra='ignore')
    name: str
    contributions: str


class SummaryResult(BaseModel):
    """Structured summary of a group chat conversation."""
    model_config = ConfigDict(extra='ignore')
    summary_text: str
    topics: list[str]
    participants: list[ParticipantContribution]
