"""Tests for TriggerDetector: keyword matching, @mention detection, edge cases."""

import unittest

from src.trigger.detector import TriggerDetector


class TriggerDetectorInitTests(unittest.TestCase):
    """Test TriggerDetector initialization and keyword normalization."""

    def test_init_normalizes_keywords_to_lowercase(self):
        """Keywords should be lowercased and stripped during init."""
        detector = TriggerDetector(
            keywords=["总结一下", "SUMMARIZE", "  What Did I Miss  "],
            bot_display_name="群聊小助手",
        )
        self.assertEqual(detector.keywords, ["总结一下", "summarize", "what did i miss"])

    def test_init_filters_empty_and_whitespace_only_keywords(self):
        """Empty or whitespace-only keywords should be dropped."""
        detector = TriggerDetector(
            keywords=["", "   ", "valid", "\n\t"],
            bot_display_name="bot",
        )
        self.assertEqual(detector.keywords, ["valid"])

    def test_init_accepts_empty_keyword_list(self):
        """An empty keyword list is valid — only @mentions will trigger."""
        detector = TriggerDetector(keywords=[], bot_display_name="bot")
        self.assertEqual(detector.keywords, [])

    def test_init_stores_bot_name(self):
        """bot_name is stored as-is (no mutation)."""
        detector = TriggerDetector(keywords=["hi"], bot_display_name="MyBot  ")
        self.assertEqual(detector.bot_name, "MyBot  ")

    def test_init_with_empty_bot_name(self):
        """Empty bot_display_name is stored as empty string."""
        detector = TriggerDetector(keywords=["hi"], bot_display_name="")
        self.assertEqual(detector.bot_name, "")


class TriggerDetectorAtMentionTests(unittest.TestCase):
    """Test @mention trigger condition (condition 1 — always triggers)."""

    def test_at_mention_triggers_regardless_of_content(self):
        """@mention should return True even with empty content."""
        detector = TriggerDetector(keywords=[], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(
            content="", is_at_mentioned=True, sender_name="Alice",
        ))

    def test_at_mention_triggers_with_irrelevant_content(self):
        """@mention should trigger even if content has no keywords."""
        detector = TriggerDetector(keywords=["总结"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(
            content="hello world", is_at_mentioned=True, sender_name="Bob",
        ))

    def test_at_mention_does_not_require_keywords(self):
        """@mention triggers even when keyword list is empty."""
        detector = TriggerDetector(keywords=[], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(
            content="anything", is_at_mentioned=True,
        ))

    def test_at_mention_takes_priority_over_keyword(self):
        """If @mentioned, return True immediately without checking keywords."""
        # Use a keyword that would NOT match — but @mention returns early
        detector = TriggerDetector(keywords=["nomatch"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(
            content="unrelated text", is_at_mentioned=True, sender_name="Eve",
        ))


class TriggerDetectorKeywordMatchTests(unittest.TestCase):
    """Test keyword-based trigger condition (condition 2)."""

    def test_exact_keyword_match(self):
        """Exact match on a keyword triggers."""
        detector = TriggerDetector(keywords=["总结一下"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(content="总结一下"))

    def test_substring_keyword_match(self):
        """Keyword appearing as substring within a longer message triggers."""
        detector = TriggerDetector(keywords=["总结一下"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(
            content="大家 总结一下 今天的讨论",
        ))

    def test_case_insensitive_match(self):
        """Keyword matching is case-insensitive."""
        detector = TriggerDetector(keywords=["summarize"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(content="SUMMARIZE"))
        self.assertTrue(detector.is_trigger(content="Summarize"))
        self.assertTrue(detector.is_trigger(content="SuMmArIzE"))

    def test_chinese_keyword_case_insensitive_noop(self):
        """Chinese keyword matching works (case insensitivity is a no-op for CJK)."""
        detector = TriggerDetector(keywords=["之前发了什么"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(content="之前发了什么"))
        self.assertTrue(detector.is_trigger(content="请帮我回顾之前发了什么内容"))

    def test_keyword_match_with_trailing_whitespace(self):
        """Content with leading/trailing whitespace still matches keywords."""
        detector = TriggerDetector(keywords=["hello"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(content="   hello   "))

    def test_keyword_partial_word_match(self):
        """Substring match: keyword inside a larger word still triggers."""
        detector = TriggerDetector(keywords=["sum"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(content="summary"))

    def test_no_keyword_match_returns_false(self):
        """Content without any keyword returns False."""
        detector = TriggerDetector(keywords=["总结一下"], bot_display_name="bot")
        self.assertFalse(detector.is_trigger(content="今天天气不错"))

    def test_no_keyword_match_when_similar_but_different(self):
        """Similar but not matching content should not trigger."""
        detector = TriggerDetector(keywords=["总结一下"], bot_display_name="bot")
        self.assertFalse(detector.is_trigger(content="总结"))
        self.assertFalse(detector.is_trigger(content="一下"))

    def test_first_matching_keyword_triggers(self):
        """As soon as one keyword matches, return True (no need to check rest)."""
        detector = TriggerDetector(
            keywords=["first", "second", "third"],
            bot_display_name="bot",
        )
        self.assertTrue(detector.is_trigger(content="first keyword wins"))

    def test_later_keyword_matches_when_earlier_ones_dont(self):
        """If the first keyword doesn't match, later ones are still checked."""
        detector = TriggerDetector(
            keywords=["aaa", "bbb", "ccc"],
            bot_display_name="bot",
        )
        self.assertTrue(detector.is_trigger(content="contains ccc only"))

    def test_no_false_positive_when_content_contains_keyword_characters_reversed(self):
        """Keyword characters in different order should not match."""
        detector = TriggerDetector(keywords=["abc"], bot_display_name="bot")
        self.assertFalse(detector.is_trigger(content="cba"))


class TriggerDetectorEdgeCaseTests(unittest.TestCase):
    """Test edge cases for TriggerDetector.is_trigger()."""

    def test_empty_content_without_at_mention_returns_false(self):
        """Empty content with no @mention should return False."""
        detector = TriggerDetector(keywords=["hello"], bot_display_name="bot")
        self.assertFalse(detector.is_trigger(content=""))

    def test_empty_content_with_empty_keywords_returns_false(self):
        """Empty content + empty keywords + no @mention = False."""
        detector = TriggerDetector(keywords=[], bot_display_name="bot")
        self.assertFalse(detector.is_trigger(content=""))

    def test_whitespace_only_content_returns_false(self):
        """Whitespace-only content doesn't match any keyword."""
        detector = TriggerDetector(keywords=["hello"], bot_display_name="bot")
        self.assertFalse(detector.is_trigger(content="   \t\n   "))

    def test_none_like_sender_name(self):
        """Sender name defaults to empty string and doesn't affect matching."""
        detector = TriggerDetector(keywords=["hi"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(content="hi"))

    def test_is_at_mentioned_false_by_default(self):
        """is_at_mentioned defaults to False when not provided."""
        detector = TriggerDetector(keywords=["test"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(content="test"))
        self.assertFalse(detector.is_trigger(content="no match"))

    def test_special_characters_in_keyword(self):
        """Keywords with special characters are matched literally."""
        detector = TriggerDetector(keywords=["@bot", "!help"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(content="@bot please"))
        self.assertTrue(detector.is_trigger(content="!help me"))
        self.assertFalse(detector.is_trigger(content="bot please"))  # no @ prefix

    def test_multiline_content_keyword_match(self):
        """Multi-line content with keyword on any line triggers."""
        detector = TriggerDetector(keywords=["总结"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(content="line1\nline2\n请总结"))

    def test_numeric_keyword(self):
        """Purely numeric keywords work."""
        detector = TriggerDetector(keywords=["123"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(content="code 123 here"))
        self.assertFalse(detector.is_trigger(content="code 12 here"))

    def test_long_content_with_many_newlines(self):
        """Large content with many newlines should still match."""
        detector = TriggerDetector(keywords=["urgent"], bot_display_name="bot")
        content = "\n".join(["filler line"] * 500) + "\nthis is urgent"
        self.assertTrue(detector.is_trigger(content=content))

    def test_keyword_is_entire_content(self):
        """Content that is exactly one keyword (no extra chars) triggers."""
        detector = TriggerDetector(keywords=["hello"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(content="hello"))

    def test_duplicate_keywords_are_not_deduplicated(self):
        """Duplicate keywords are kept as-is (matching still works correctly)."""
        detector = TriggerDetector(
            keywords=["hi", "hi", "hi"],
            bot_display_name="bot",
        )
        self.assertEqual(len(detector.keywords), 3)
        self.assertTrue(detector.is_trigger(content="hi there"))

    def test_very_long_keyword(self):
        """Very long keywords are supported."""
        long_keyword = "a" * 1000
        detector = TriggerDetector(keywords=[long_keyword], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(content=f"prefix {long_keyword} suffix"))

    def test_very_short_keyword(self):
        """Single-character keywords work."""
        detector = TriggerDetector(keywords=["!"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(content="hello!"))


class TriggerDetectorCombinedTests(unittest.TestCase):
    """Test combinations of both trigger conditions."""

    def test_no_trigger_without_at_mention_or_keyword(self):
        """Neither condition met => no trigger."""
        detector = TriggerDetector(keywords=["总结"], bot_display_name="bot")
        self.assertFalse(detector.is_trigger(
            content="hello", is_at_mentioned=False,
        ))

    def test_trigger_with_both_conditions(self):
        """Both @mention and keyword match => still triggers (once)."""
        detector = TriggerDetector(keywords=["hello"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(
            content="hello", is_at_mentioned=True,
        ))

    def test_keyword_trigger_with_explicit_false_at_mention(self):
        """Explicit is_at_mentioned=False still allows keyword trigger."""
        detector = TriggerDetector(keywords=["总结"], bot_display_name="bot")
        self.assertTrue(detector.is_trigger(
            content="总结一下", is_at_mentioned=False,
        ))

    def test_no_keyword_trigger_when_not_mentioned_and_no_keyword(self):
        """False for both conditions."""
        detector = TriggerDetector(keywords=["xyz"], bot_display_name="bot")
        self.assertFalse(detector.is_trigger(
            content="abc", is_at_mentioned=False,
        ))


if __name__ == "__main__":
    unittest.main()
