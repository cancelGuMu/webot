"""Trigger detection: keyword matching + @mention detection."""

import logging


logger = logging.getLogger(__name__)


class TriggerDetector:
    """Detects whether a message should trigger summarization.

    Two trigger conditions:
    1. The bot is @mentioned (always triggers).
    2. The message content matches a keyword from the configurable list.
    """

    def __init__(self, keywords: list[str], bot_display_name: str = ""):
        """
        Args:
            keywords: List of trigger keywords (lowercased for matching).
            bot_display_name: The bot's display name for @mention detection.
        """
        self.keywords = [kw.lower().strip() for kw in keywords if kw.strip()]
        self.bot_name = bot_display_name

    def is_trigger(self, content: str, is_at_mentioned: bool = False,
                   sender_name: str = "") -> bool:
        """Check if this message should trigger summarization.

        Args:
            content: The message text content.
            is_at_mentioned: Whether the bot was @mentioned.
            sender_name: The sender's display name (for logging).

        Returns:
            True if this is a trigger message.
        """
        # Condition 1: @mention always triggers
        if is_at_mentioned:
            logger.debug(f"Trigger: @mention by '{sender_name}'")
            return True

        # Condition 2: Keyword match
        normalized = content.lower().strip()
        for kw in self.keywords:
            if kw in normalized:
                logger.debug(
                    f"Trigger: keyword '{kw}' matched in message "
                    f"from '{sender_name}'"
                )
                return True

        return False
