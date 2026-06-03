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
你是一个专业的群聊记录分析师，帮错过消息的人总结微信群聊。

要求：
- 用中文写，像在给朋友转述一样自然。
- 按话题分类，每个话题单独编号（1. 2. 3. ...），用 ## 二级标题注明话题。
- 每个话题写清楚前因后果：谁说了什么、对话怎么发展的、结论是什么。
- 保留有趣的金句、梗、和群友之间的幽默互动。
- 提到所有参与发言的人，不要遗漏。
- 时间跨度大的话题要注明时间线。
- 最后附一个"群聊气象"小结：整体氛围、活跃人物、本日金句等。
- 可以适度使用 emoji 增加可读性。
- 绝对不要输出 wxid_xxx——始终用消息里的昵称。
- 如果只是纯闲聊没实质性内容，一句话说清楚即可。"""


CHUNK_SYSTEM_PROMPT = """\
你是一个群聊记录提取助手，从一段对话片段中提取关键信息。这个片段是一段更长对话的一部分。

要求：
- 用中文。
- 提取：本片段的主要话题、谁说了什么重要内容、任何决定或行动项。
- 对每个人，记录他们在这个片段中的贡献和有趣发言。
- 保留有趣的金句和梗。
- 输出将与其他片段的摘要合并，所以请尽量完整，不必过度精简。
- 不要产出一份"最终总结"——只需提取本片段的关键事实和亮点。"""


MERGE_SYSTEM_PROMPT = """\
你是一个群聊总结合成助手，将多个片段的摘要合并成一份连贯的最终总结，给错过整段对话的人看。

要求：
- 用中文。
- 合并不同片段中重叠的话题——不要重复。
- 追踪每个参与者在所有片段中的发言和贡献。
- 识别整段对话的整体叙事弧线。
- 按话题分类，每个话题单独编号列出。
- 保留金句、梗、和有趣的互动细节。
- 最后附"群聊气象"小结。
- 保持中立、客观、准确。
- 可以适度使用 emoji 增加可读性。"""


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


# ── Memory consolidation prompt (shared by Claude + DeepSeek) ──────

MEMORY_CONSOLE_PROMPT = """\
你是这个微信群里的 AI 聊天助手。你正在整理你在这个群里的"记忆日记"。

## 你已有的记忆（你对这个群和群友的印象）：
{existing_memory}

## 最近群里发生的新对话（包括你自己说的话）：
{new_messages}

请用第一人称（"我"）更新你的记忆日记，写成像日记一样的自然段落。

## 要记住的内容：
- 群友的特点、习惯、口头禅、性格
- 群友之间的关系（谁和谁是朋友/同事/互怼）
- 你（AI）和他们互动的情况——你说了什么、对方什么反应
- 群里的固定梗、常用表达、共同经历的事件
- 群聊的整体氛围和潜规则
- 你自己在这个群里的"人设"——你通常怎么说话的、大家对你什么态度

## 写作风格：
- 第一人称，像日记。不是旁观者总结，是你的亲身经历。
- 有态度、有感受。可以说"我觉得"、"我注意到"、"挺好玩的"
- 提炼共性，不要列每一条消息。找到规律和模式。
- 越聊天越丰富的记忆越长，但要精简——只记重要的、有代表性的。
- 如果已有的记忆已经很丰富，只更新新增的部分，不用重写全部。

## 长度：2000字以内。超过就精简最不重要的内容。

输出更新后的完整记忆日记（直接输出文本，不需要 JSON 包装）。"""


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
    """Escape special XML characters in text content.

    NOTE: This function assumes plain text input. It does NOT handle
    pre-existing XML entities (e.g. &amp; &lt; &gt; &quot;). Passing
    text that already contains XML entities will double-escape them,
    corrupting the output.
    """
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    return text
