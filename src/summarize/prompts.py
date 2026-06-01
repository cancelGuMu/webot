"""Prompt templates for Claude chat summarization.

Two strategies:
1. Direct: for conversations that fit within the context window (~150K tokens).
   All messages are sent in one call with XML formatting.
2. Map-Reduce: for very large conversations (5000+ messages).
   Messages are split into chunks, each chunk gets a concise summary,
   then the chunk summaries are merged into the final structured output.
"""

import time as _time


# ── System prompts ────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a helpful assistant that summarizes WeChat group chat conversations \
for someone who missed messages.

Guidelines:
- Write in Chinese.
- CRITICAL: Every event you mention MUST be on its own numbered line: 1. 2. 3. — one topic per number. Do NOT use bullet points or plain paragraphs.
- Each topic: one sentence. Say who said what in the sentence itself.
- Example:
  1. 马牛逼吐槽火鸡面抽烟，说给她买了两个电子烟。
  2. 小金鱼被催找工作，回复说"看我状态"。
  3. 蘑菇倒计时拉人打王者，苏苏的小号说四缺一。
- NO introductions, NO participant tables, NO section headers.
- Absolutely NEVER output wxid_xxx — always use the sender's name from the messages.
- If the conversation is purely casual chat, just say so in one sentence.
- Total output under 300 characters when possible."""


CHUNK_SYSTEM_PROMPT = """\
You are a helpful assistant that extracts key information from a segment \
of a WeChat group chat conversation. This segment is part of a longer \
conversation — you only see a portion of it.

Guidelines:
- Write in Chinese if the messages are in Chinese.
- Extract: main topics in this segment, key things people said, \
  any decisions or action items mentioned.
- For each person, note what they contributed in this segment.
- Be concise. Your output will be merged with summaries from other segments.
- Do NOT produce a final summary — just extract the key facts from this segment."""


MERGE_SYSTEM_PROMPT = """\
You are a helpful assistant that synthesizes partial chat summaries \
into one coherent final summary for someone who missed the entire conversation.

Guidelines:
- Write in Chinese if the segment summaries are in Chinese.
- Combine overlapping topics from different segments — do not duplicate.
- Track each participant's contributions across all segments.
- Identify the overall narrative arc of the conversation.
- CRITICAL: Every event MUST be on its own numbered line: 1. 2. 3. — one topic per number. Do NOT use bullet points or plain paragraphs.
- Be neutral and factual."""


# ── Direct summarization prompt ───────────────────────────────────

def build_summary_prompt(messages: list[dict], requester_name: str) -> str:
    """Build a structured XML prompt for direct summarization.

    Used when the entire conversation fits within the model's context window.

    Args:
        messages: List of message dicts (sender_name, content, timestamp, msg_type).
        requester_name: The display name of the person asking for a summary.

    Returns:
        A formatted prompt string with XML-tagged messages.
    """
    messages_xml = _format_messages_xml(messages)

    prompt = f"""\
{requester_name} just asked what they missed in this group chat since their \
last message. Please provide a summary of the conversation they missed.

<messages>
{messages_xml}
</messages>

The messages above are in chronological order ({len(messages)} total).
Provide a structured summary covering: topics discussed, and who contributed what."""

    return prompt


# ── Map-Reduce prompts ────────────────────────────────────────────

def build_chunk_summary_prompt(messages: list[dict], chunk_num: int,
                                total_chunks: int,
                                requester_name: str) -> str:
    """Build a prompt for summarizing one chunk of a large conversation.

    Args:
        messages: The messages in this chunk.
        chunk_num: Which chunk this is (1-indexed).
        total_chunks: Total number of chunks.
        requester_name: The person asking for the summary.

    Returns:
        A prompt string for per-chunk extraction.
    """
    messages_xml = _format_messages_xml(messages)

    first_time = _format_time(messages[0]["timestamp"]) if messages else "?"
    last_time = _format_time(messages[-1]["timestamp"]) if messages else "?"

    prompt = f"""\
{requester_name} missed a long group chat conversation. This is segment \
{chunk_num} of {total_chunks} (chronologically, from {first_time} to {last_time}).

Extract the key information from this segment:

<messages>
{messages_xml}
</messages>

Extract: topics discussed, who said what important, any decisions or action items."""

    return prompt


def build_merge_prompt(chunk_summaries: list[str],
                        requester_name: str) -> str:
    """Build a prompt for merging chunk summaries into a final summary.

    Args:
        chunk_summaries: List of text summaries, one per chunk.
        requester_name: The person asking for the summary.

    Returns:
        A prompt string for the merge step.
    """
    segments = "\n\n".join(
        f"<segment index='{i+1}'>\n{summary}\n</segment>"
        for i, summary in enumerate(chunk_summaries)
    )

    prompt = f"""\
{requester_name} missed a long group chat conversation that has been \
split into {len(chunk_summaries)} chronological segments. Each segment \
below is a summary of part of the conversation.

Synthesize these into one coherent final summary:

{segments}

Provide a comprehensive final summary covering all topics discussed and \
who contributed what across the entire conversation."""

    return prompt


# ── Internal helpers ──────────────────────────────────────────────

def _format_messages_xml(messages: list[dict]) -> str:
    """Format a list of message dicts into XML blocks."""
    msg_blocks = []
    for msg in messages:
        sender = msg.get("sender_name", "unknown")
        ts = msg.get("timestamp", 0)
        time_str = _format_time(ts)
        content = msg.get("content", "")
        msg_type = msg.get("msg_type", 1)

        if msg_type == 1:
            content_escaped = _escape_xml(content)
            msg_blocks.append(
                f'<msg sender="{sender}" time="{time_str}">\n'
                f"  {content_escaped}\n"
                f"</msg>"
            )
        elif content:
            msg_blocks.append(
                f'<msg sender="{sender}" time="{time_str}">\n'
                f"  {_escape_xml(content)}\n"
                f"</msg>"
            )

    return "\n".join(msg_blocks)


def _format_time(timestamp: int) -> str:
    """Convert Unix timestamp to HH:MM string."""
    return _time.strftime("%H:%M", _time.localtime(timestamp))


def _escape_xml(text: str) -> str:
    """Escape special XML characters in text content."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    return text
