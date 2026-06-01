"""Pydantic models for structured chat summarization output.

Shared across all AI backends (Claude, DeepSeek, etc.).
"""

from pydantic import BaseModel


class ParticipantContribution(BaseModel):
    """A participant's contribution to the conversation."""
    name: str
    contributions: str


class SummaryResult(BaseModel):
    """Structured summary of a group chat conversation."""
    summary_text: str
    topics: list[str]
    participants: list[ParticipantContribution]
