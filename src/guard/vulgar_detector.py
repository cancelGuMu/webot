"""Vulgar/low-brow content detector for Chinese group chat.

Detects common vulgar memes, sexual innuendos, crude jokes, and low-brow
internet slang. When triggered, returns a firm verbal warning — no profanity,
just direct language calling out the inappropriate content.
"""

import logging
import random
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ── Warning templates ──────────────────────────────────────────────
# These are firm but clean. No dirty words.  The goal is a direct,
# unambiguous call-out that doesn't escalate or match the vulgar tone.
#
# Selected randomly each time to avoid sounding like a broken record.

_WARNINGS = [
    "注意语言，这种梗别在群里说。",
    "说这种话不合适，注意点。",
    "群里聊天注意分寸，这种内容不要发。",
    "请保持文明交流，这种话不合适。",
    "别在群里发这种低俗内容。",
    "这种梗很低俗，请自重。",
    "低俗梗请适可而止，群里不是只有你一个人。",
    "注意言辞，这里不是可以随便乱说的地方。",
    "这种话很不得体，请撤回。",
    "请尊重群友，不要说这种低俗的话。",
    "语言注意一下，别把低俗当幽默。",
    "这种内容发出来不合适，请收敛。",
    "开这种低俗玩笑没什么意思，注意点。",
    "群里聊天请注意底线，这种话别说。",
    "别拿低俗当有趣，注意你的言辞。",
]


# ── Keyword patterns ───────────────────────────────────────────────
# Categories of vulgar/low-brow content to detect.
#
# Each entry is a (regex_pattern, category_label) pair.
# Patterns are case-insensitive and match against the full message text.
# We use regex rather than simple substring matching to catch common
# variants, spacing tricks, and homophones.

_PATTERNS: list[tuple[str, str]] = [
    # ── Sexual innuendo / crude jokes ─────────────────────────────
    (r"[艹操草][你尼拟泥][妈马吗玛嘛]", "粗俗用语"),
    (r"[日入][你尼拟]", "粗俗用语"),
    (r"[你他她它]妈[的滴]", "粗俗用语"),
    (r"[你他她它]他妈", "粗俗用语"),
    (r"[卧我]槽", "粗俗用语"),
    (r"[傻煞][逼比币弊]", "粗俗用语"),
    (r"鸡儿", "低俗性暗示"),  # exact match only — avoids false match on "几儿"
    (r"[牛妞纽][子仔崽]", "低俗性暗示"),
    (r"[搞弄][基鸡机]", "低俗梗"),
    (r"老[色涩瑟]批", "低俗梗"),
    (r"约[炮泡]", "低俗内容"),
    (r"[啪啪怕怕][啪啪怕怕]", "低俗内容"),
    (r"[撸噜鲁]一[发法]", "低俗内容"),
    (r"大[保宝]健", "低俗暗示"),
    (r"搞[黄簧皇]色", "低俗内容"),
    (r"[看看][黄簧皇]片", "低俗内容"),

    # ── Dirty wordplay / homophonic tricks ────────────────────────
    (r"[比比批逼币鼻][逼比币毕][你尼]", "低俗脏话变体"),
    (r"[尼拟][玛吗马码]", "低俗脏话变体"),
    (r"[煞沙杀傻][笔逼比币]", "低俗脏话变体"),
    (r"沙[雕吊]", "低俗脏话变体"),
    (r"[二贰]百[五伍舞]", "低俗脏话变体"),
    (r"弱[智志治]", "人身攻击"),
    (r"脑[残蚕惭]", "人身攻击"),
    (r"神[经精睛]病", "人身攻击"),

    # ── Crude body-part / bodily-function jokes ───────────────────
    (r"吃[屎始使]", "低俗内容"),
    (r"拉[屎始使]", "低俗内容"),
    (r"[尿鸟]一[裤库]", "低俗内容"),
    (r"放[屁皮匹]", "低俗内容"),

    # ── Sexual harassment / non-consensual implications ───────────
    (r"[摸摸磨][你妮拟][胸匈][部步不]", "低俗骚扰"),
    (r"[摸磨][大腿]", "低俗骚扰"),
    (r"[强抢][奸间坚]", "违法内容提及"),
    (r"[迷谜][奸间坚]", "违法内容提及"),

    # ── Gambling / fraud adjacent (common in low-brow contexts) ──
    (r"[赌堵睹][球求][输赢]", "赌博相关"),
    (r"下[注柱住]多[少小]", "赌博相关"),

    # ── Common low-brow internet trash talk ───────────────────────
    (r"你[算蒜][个各][什么]", "挑衅性低俗言论"),
    (r"[滚衮辊][蛋但旦]", "低俗辱骂"),
    (r"去[死屎使][吧把]", "低俗辱骂"),
    (r"[贱见建][人仁任]", "低俗辱骂"),
    (r"[婊表裱][子籽仔]", "低俗辱骂"),
    (r"臭[不]?[要]?[脸联怜]", "低俗辱骂"),
    (r"[烂滥蓝][货或祸]", "低俗辱骂"),

    # ── Sexual solicitation / escort content ──────────────────────
    (r"[陪赔培][睡水税]", "低俗色情"),
    (r"[包抱报][养氧仰]", "低俗色情"),
    (r"[约邀][吗嘛马][约邀]", "低俗色情"),
    (r"上[门们闷].*[服付复]", "低俗色情"),
    (r"[嫖飘漂][娼昌仓]", "违法内容提及"),
]


class VulgarDetector:
    """Detects vulgar/low-brow content and issues clean verbal warnings.

    Usage:
        detector = VulgarDetector()

        # Check incoming message
        hit, category = detector.scan("我操你妈的说啥呢")
        if hit:
            warning = detector.warning()  # random warning message

        # Check AI output
        hit, category = detector.scan(ai_reply)
        if hit:
            logger.warning("AI generated inappropriate content: %s", category)
            return detector.warning()
    """

    def __init__(self) -> None:
        """Compile regex patterns on init for fast repeated matching."""
        self._compiled: list[tuple[re.Pattern, str]] = [
            (re.compile(pattern, re.IGNORECASE), category)
            for pattern, category in _PATTERNS
        ]

    def scan(self, text: str) -> tuple[bool, Optional[str]]:
        """Scan a text string for vulgar/low-brow content.

        Args:
            text: The text to scan (incoming message, AI reply, etc.)

        Returns:
            (is_vulgar, category) — category is the matched category label
            if found, or None.
        """
        if not text or not text.strip():
            return False, None

        for regex, category in self._compiled:
            if regex.search(text):
                logger.debug(
                    "Vulgar content detected [%s]: %s",
                    category, text[:80],
                )
                return True, category

        return False, None

    def scan_messages(self, messages: list[dict]) -> tuple[bool, Optional[str]]:
        """Scan a list of message dicts for vulgar content.

        Checks the 'content' field of each message dict.

        Args:
            messages: List of message dicts with 'content' key.

        Returns:
            (is_vulgar, category) — True if any message matches.
        """
        for msg in messages:
            content = msg.get("content", "")
            if not content:
                continue
            is_vulgar, category = self.scan(content)
            if is_vulgar:
                return True, category
        return False, None

    @staticmethod
    def warning() -> str:
        """Return a random firm-but-clean warning message.

        The warnings are direct and unambiguous, but never use profanity
        themselves — the goal is to call out the behavior, not match it.
        """
        return random.choice(_WARNINGS)

    @staticmethod
    def warning_for(category: str) -> str:
        """Return a warning message appropriate for a specific category.

        Args:
            category: The category label from scan().

        Returns:
            A warning message string.
        """
        return random.choice(_WARNINGS)
