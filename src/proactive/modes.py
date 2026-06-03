"""Proactive chat modes — rate-based atmosphere detection.

5 modes based on message frequency, each with distinct reply behavior.
Thresholds are loaded from BotConfig and can be calibrated via .env
or by running:  python tools/analyze_chat_rhythm.py
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import BotConfig


@dataclass(frozen=True)
class ProactiveMode:
    """A single proactive participation mode.

    Attributes:
        name: Short key (e.g. "SLEEP", "QUIET", "BURST").
        label: Chinese label for logging/prompts.
        description: Human-readable description of the group atmosphere.
        instruction: How the AI should behave in this mode (injected into prompt).
        min_rate: Lower bound message rate (msgs/min) for this mode.
        eval_interval_sec: Minimum seconds between AI evaluation attempts.
        reply_probability: Chance (0.0-1.0) of actually calling the AI
                           when the evaluation interval has elapsed.
        max_chars: Hard cap on AI reply length (characters).
        context_count: How many recent messages to include as context.
    """

    name: str
    label: str
    description: str
    instruction: str
    min_rate: float
    eval_interval_sec: int
    reply_probability: float
    max_chars: int
    context_count: int


# ── Mode behavior definitions ─────────────────────────────────────────
#
# The min_rate thresholds are injected from BotConfig at runtime.
# Everything else (eval_interval, probability, max_chars, etc.) is
# defined here as the sensible default behavior per mode.

_MODE_BEHAVIOR: list[dict] = [
    {
        "name": "SLEEP",
        "label": "沉睡",
        "description": "群里没人说话，或者很久才有一条消息",
        "instruction": "群里很安静，如果没有什么特别值得说的，就保持沉默。",
        "eval_interval_sec": 9999,
        "reply_probability": 0.0,
        "max_chars": 0,
        "context_count": 0,
    },
    {
        "name": "QUIET",
        "label": "冷清",
        "description": "偶尔有人冒泡，节奏很慢",
        "instruction": "群里比较安静，偶尔才有人说话。看最近聊了什么，如果话题你能接上就自然地回一句。保持克制，不要说无关的话。如果群里出现重大打击、情绪崩溃、吵架、裁员离婚等严重话题，必须保持沉默。",
        "eval_interval_sec": 300,
        "reply_probability": 0.10,
        "max_chars": 30,
        "context_count": 30,
    },
    {
        "name": "CASUAL",
        "label": "闲聊",
        "description": "正常聊天节奏，几个人在聊",
        "instruction": "群里在正常聊天。仔细看最近大家在聊什么话题，确保你的回复是接着前面话题的。可以自然地插话、吐槽、接梗，但不要突然跳到无关话题。如果群里出现重大打击、情绪崩溃、吵架等严重话题，保持沉默，不要接话。",
        "eval_interval_sec": 120,
        "reply_probability": 0.25,
        "max_chars": 50,
        "context_count": 50,
    },
    {
        "name": "LIVELY",
        "label": "热闹",
        "description": "多人同时在讨论，节奏较快",
        "instruction": "群里聊得很嗨。快速扫一眼最近的话题，接短句、吐槽、起哄都可以。但要确保你接的是正在聊的事，不要答非所问。注意：如果话题转向严重负面事件（事故、重病、情绪崩溃等），停止插话。",
        "eval_interval_sec": 60,
        "reply_probability": 0.50,
        "max_chars": 35,
        "context_count": 60,
    },
    {
        "name": "BURST",
        "label": "炸了",
        "description": "刷屏级别，瓜来了或者大事件",
        "instruction": "群聊爆炸了！极短的感叹、吐槽、表情反应为主。快速扫上下文确保你没接错话题。但如果是负面大事件刷屏（事故、重病等），不要跟风发言。",
        "eval_interval_sec": 30,
        "reply_probability": 0.70,
        "max_chars": 20,
        "context_count": 80,
    },
]


def build_modes(config: "BotConfig") -> list[ProactiveMode]:
    """Build the mode list from config rate thresholds + default behavior.

    Rate thresholds come from config (calibratable via .env or
    analyze_chat_rhythm.py).  Everything else uses the defined behavior above.
    """
    rate_keys = ["quiet", "casual", "lively", "burst"]
    rates: dict[str, float] = {
        key: getattr(config, f"proactive_rate_{key}")
        for key in rate_keys
    }

    modes: list[ProactiveMode] = []
    for b in _MODE_BEHAVIOR:
        name = b["name"]
        min_rate: float
        if name == "SLEEP":
            min_rate = 0.0
        elif name == "QUIET":
            min_rate = rates["quiet"]
        elif name == "CASUAL":
            min_rate = rates["casual"]
        elif name == "LIVELY":
            min_rate = rates["lively"]
        else:  # BURST
            min_rate = rates["burst"]

        modes.append(ProactiveMode(
            name=name,
            label=b["label"],
            description=b["description"],
            instruction=b["instruction"],
            min_rate=min_rate,
            eval_interval_sec=b["eval_interval_sec"],
            reply_probability=b["reply_probability"],
            max_chars=b["max_chars"],
            context_count=b["context_count"],
        ))

    modes.sort(key=lambda m: m.min_rate)
    return modes


# Module-level cache — built once on first access
_MODES: list[ProactiveMode] | None = None


def get_modes(config: "BotConfig") -> list[ProactiveMode]:
    """Return the mode list, building from config on first call."""
    global _MODES
    if _MODES is None:
        _MODES = build_modes(config)
    return _MODES


def reset_modes() -> None:
    """Reset the module-level mode cache so modes are rebuilt on next access.

    Call this after config changes to force re-evaluation of rate thresholds.
    """
    global _MODES
    _MODES = None


def lookup_mode(rate: float, config: "BotConfig") -> ProactiveMode:
    """Return the mode whose min_rate is the largest ≤ rate.

    Modes are sorted by min_rate ascending, so this finds the
    highest mode whose threshold is met.  SLEEP (min_rate=0) is
    always the fallback.
    """
    modes = get_modes(config)
    current = modes[0]  # SLEEP
    for mode in modes:
        if rate >= mode.min_rate:
            current = mode
    return current
