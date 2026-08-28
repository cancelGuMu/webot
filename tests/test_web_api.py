"""
Tests for webot: config loading, trigger detection, and web API endpoints.

Uses Python's built-in unittest framework with unittest.mock for mocking.
No real DB or network -- all tests are fast and deterministic.
"""

import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch


# ======================================================================
#  TestConfig -- configuration loading, validation, helpers
# ======================================================================


class TestConfig(unittest.TestCase):
    """Tests for src.config: load_config, _validate_config, find_env_file,
    is_onboarding_done, _sanitize_display_name, _decode_wechat_groups."""

    # -- import-time resilience ----------------------------------------

    def test_config_module_can_be_imported(self):
        """Importing config module should not raise NameError even when no
        .env file exists (regression test for dotenv fallback bug)."""
        try:
            from src import config as cfg
            self.assertTrue(hasattr(cfg, "load_config"))
            self.assertTrue(hasattr(cfg, "BotConfig"))
            self.assertTrue(hasattr(cfg, "find_env_file"))
            self.assertTrue(hasattr(cfg, "is_onboarding_done"))
        except NameError as e:
            self.fail(f"Import of src.config raised NameError: {e}")

    # -- load_config ---------------------------------------------------

    def test_load_config_deepseek_backend(self):
        """load_config should build BotConfig from DeepSeek environment variables."""
        from src.config import load_config, BotConfig
        env = {
            "AI_BACKEND": "deepseek",
            "DEEPSEEK_API_KEY": "sk-test-deepseek-key",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "WECHAT_BACKEND": "wcdb",
            "WECHAT_GROUPS": "*",
            "BOT_DISPLAY_NAME": "test-bot",
            "TRIGGER_KEYWORDS": "summary,help,info",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = load_config()
            self.assertIsInstance(cfg, BotConfig)
            self.assertEqual(cfg.ai_backend, "deepseek")
            self.assertEqual(cfg.deepseek_api_key, "sk-test-deepseek-key")
            self.assertEqual(cfg.deepseek_model, "deepseek-v4-flash")
            self.assertEqual(cfg.bot_display_name, "test-bot")
            self.assertEqual(cfg.trigger_keywords, ["summary", "help", "info"])
            self.assertEqual(cfg.wechat_groups, "*")

    def test_load_config_claude_backend(self):
        """load_config should build BotConfig from Claude env vars."""
        from src.config import load_config, BotConfig
        env = {
            "AI_BACKEND": "claude",
            "ANTHROPIC_API_KEY": "sk-ant-test-key",
            "SUMMARIZE_MODEL": "claude-sonnet-4-5-20250901",
            "WECHAT_BACKEND": "wcdb",
            "BOT_DISPLAY_NAME": "claude-bot",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = load_config()
            self.assertEqual(cfg.ai_backend, "claude")
            self.assertEqual(cfg.anthropic_api_key, "sk-ant-test-key")
            self.assertEqual(cfg.summarize_model, "claude-sonnet-4-5-20250901")
            self.assertEqual(cfg.bot_display_name, "claude-bot")

    def test_load_config_missing_deepseek_api_key_raises(self):
        """load_config with deepseek backend but empty key should raise RuntimeError."""
        from src.config import load_config
        env = {"AI_BACKEND": "deepseek", "DEEPSEEK_API_KEY": ""}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                load_config()
            self.assertIn("DEEPSEEK_API_KEY", str(ctx.exception))

    def test_load_config_missing_anthropic_api_key_raises(self):
        """load_config with claude backend but empty key should raise RuntimeError."""
        from src.config import load_config
        env = {"AI_BACKEND": "claude", "ANTHROPIC_API_KEY": ""}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                load_config()
            self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))

    def test_load_config_defaults_when_vars_missing(self):
        """load_config should apply dataclass defaults for optional env vars."""
        from src.config import load_config
        env = {"AI_BACKEND": "deepseek", "DEEPSEEK_API_KEY": "sk-test-key"}
        with patch.dict(os.environ, env, clear=True):
            cfg = load_config()
            self.assertEqual(cfg.poll_interval_sec, 1.0)
            self.assertEqual(cfg.chunk_size, 400)
            self.assertEqual(cfg.max_messages_for_summary, 5000)
            self.assertEqual(cfg.fallback_window_hours, 8)
            self.assertEqual(cfg.dedup_window_sec, 60)
            self.assertTrue(cfg.fun_enabled)
            self.assertFalse(cfg.proactive_enabled)
            self.assertEqual(cfg.log_level, "INFO")

    def test_load_config_empty_trigger_keywords_uses_default(self):
        """When TRIGGER_KEYWORDS is unset, the dataclass defaults apply."""
        from src.config import load_config
        env = {"AI_BACKEND": "deepseek", "DEEPSEEK_API_KEY": "sk-test-key",
               "TRIGGER_KEYWORDS": ""}
        with patch.dict(os.environ, env, clear=True):
            cfg = load_config()
            self.assertIn("summarize", cfg.trigger_keywords)
            self.assertIn("总结一下", cfg.trigger_keywords)

    # -- _validate_config ----------------------------------------------

    def _call_validate(self, **overrides):
        from src.config import _validate_config
        defaults = {
            "ai_backend": "deepseek",
            "anthropic_api_key": "k",
            "deepseek_api_key": "k",
        }
        defaults.update(overrides)
        _validate_config(defaults)

    def test_validate_config_poll_interval_too_low(self):
        """POLL_INTERVAL_SEC < 0.1 must raise RuntimeError."""
        with self.assertRaises(RuntimeError) as ctx:
            self._call_validate(poll_interval_sec=0.05)
        self.assertIn("POLL_INTERVAL_SEC", str(ctx.exception))

    def test_validate_config_chunk_size_below_range(self):
        """CHUNK_SIZE < 10 must raise RuntimeError."""
        with self.assertRaises(RuntimeError) as ctx:
            self._call_validate(chunk_size=5)
        self.assertIn("CHUNK_SIZE", str(ctx.exception))

    def test_validate_config_chunk_size_above_range(self):
        """CHUNK_SIZE > 1000 must raise RuntimeError."""
        with self.assertRaises(RuntimeError) as ctx:
            self._call_validate(chunk_size=9999)
        self.assertIn("CHUNK_SIZE", str(ctx.exception))

    def test_validate_config_chunk_size_at_boundaries_passes(self):
        """CHUNK_SIZE at 10 and 1000 should pass."""
        self._call_validate(chunk_size=10)
        self._call_validate(chunk_size=1000)

    def test_validate_config_max_messages_too_low(self):
        """MAX_MESSAGES_FOR_SUMMARY < 10 must raise RuntimeError."""
        with self.assertRaises(RuntimeError) as ctx:
            self._call_validate(max_messages_for_summary=1)
        self.assertIn("MAX_MESSAGES_FOR_SUMMARY", str(ctx.exception))

    def test_validate_config_fallback_window_hours_too_low(self):
        """FALLBACK_WINDOW_HOURS < 1 must raise RuntimeError."""
        with self.assertRaises(RuntimeError) as ctx:
            self._call_validate(fallback_window_hours=0)
        self.assertIn("FALLBACK_WINDOW_HOURS", str(ctx.exception))

    def test_validate_config_dedup_window_too_low(self):
        """DEDUP_WINDOW_SEC < 10 must raise RuntimeError."""
        with self.assertRaises(RuntimeError) as ctx:
            self._call_validate(dedup_window_sec=5)
        self.assertIn("DEDUP_WINDOW_SEC", str(ctx.exception))

    def test_validate_config_proactive_rates_not_ascending(self):
        """PROACTIVE_RATE_* values must be strictly ascending."""
        with self.assertRaises(RuntimeError) as ctx:
            self._call_validate(
                proactive_rate_quiet=5.0,
                proactive_rate_casual=3.0,   # smaller than quiet
                proactive_rate_lively=6.5,
                proactive_rate_burst=8.5,
            )
        self.assertIn("ascending", str(ctx.exception))

    def test_validate_config_proactive_rates_negative(self):
        """All PROACTIVE_RATE_* values must be > 0."""
        with self.assertRaises(RuntimeError) as ctx:
            self._call_validate(
                proactive_rate_quiet=-1.0,
                proactive_rate_casual=4.0,
                proactive_rate_lively=6.5,
                proactive_rate_burst=8.5,
            )
        self.assertIn("PROACTIVE_RATE", str(ctx.exception))

    def test_validate_config_sticky_mention_ttl_out_of_range(self):
        """STICKY_MENTION_TTL_SEC must be between 10 and 300."""
        with self.assertRaises(RuntimeError):
            self._call_validate(sticky_mention_ttl_sec=500)
        with self.assertRaises(RuntimeError):
            self._call_validate(sticky_mention_ttl_sec=5)

    def test_validate_config_proactive_rate_window_too_low(self):
        """PROACTIVE_RATE_WINDOW_SEC must be >= 30."""
        with self.assertRaises(RuntimeError) as ctx:
            self._call_validate(proactive_rate_window_sec=10)
        self.assertIn("PROACTIVE_RATE_WINDOW_SEC", str(ctx.exception))

    def test_validate_config_max_retries_out_of_range(self):
        """MAX_RETRIES must be between 1 and 10 if provided."""
        with self.assertRaises(RuntimeError):
            self._call_validate(max_retries=0)
        with self.assertRaises(RuntimeError):
            self._call_validate(max_retries=99)

    def test_validate_config_max_retries_not_set_passes(self):
        """max_retries=None (not in config) should pass validation."""
        self._call_validate()  # no max_retries key at all

    def test_validate_config_multiple_errors_reported(self):
        """Multiple invalid values should all appear in the error message."""
        with self.assertRaises(RuntimeError) as ctx:
            self._call_validate(chunk_size=0, poll_interval_sec=0)
        msg = str(ctx.exception)
        self.assertIn("CHUNK_SIZE", msg)
        self.assertIn("POLL_INTERVAL_SEC", msg)

    # -- find_env_file ------------------------------------------------

    def test_find_env_file_found_in_project_root(self):
        """find_env_file should return project-root .env if it exists."""
        from src.config import find_env_file, PROJECT_ROOT

        with (
            patch.object(sys, "frozen", False, create=True),
            patch.object(Path, "exists", return_value=True),
        ):
            result = find_env_file()
            self.assertIsNotNone(result)
            self.assertEqual(result, PROJECT_ROOT / ".env")

    def test_find_env_file_found_in_cwd(self):
        """find_env_file returns non-None when at least one .env exists."""
        from src.config import find_env_file

        with (
            patch.object(sys, "frozen", False, create=True),
            patch.object(Path, "exists", return_value=True),
        ):
            result = find_env_file()
            self.assertIsNotNone(result)

    def test_find_env_file_not_found(self):
        """find_env_file should return None when no .env exists anywhere."""
        from src.config import find_env_file
        with (
            patch.object(sys, "frozen", False, create=True),
            patch.object(Path, "exists", return_value=False),
        ):
            self.assertIsNone(find_env_file())

    def test_find_env_file_frozen_mode(self):
        """In frozen mode, EXE directory is searched first and returned
        when .env is present there."""
        from src.config import find_env_file

        exe_dir = Path(sys.executable).resolve().parent

        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(Path, "exists", return_value=True),
        ):
            result = find_env_file()
            self.assertIsNotNone(result)
            # In frozen mode, EXE dir is checked first — it wins
            self.assertEqual(result, exe_dir / ".env")

    # -- is_onboarding_done --------------------------------------------

    def test_is_onboarding_done_true(self):
        """Returns True when .env has ONBOARDING_DONE=true."""
        from src.config import is_onboarding_done

        fake_env = Path("/fake/.env")
        fake_content = "ONBOARDING_DONE=true\nWECHAT_BACKEND=wcdb\n"
        with (
            patch("src.config.find_env_file", return_value=fake_env),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value=fake_content),
        ):
            self.assertTrue(is_onboarding_done())

    def test_is_onboarding_done_false_explicit(self):
        """Returns False when ONBOARDING_DONE=false."""
        from src.config import is_onboarding_done

        fake_env = Path("/fake/.env")
        fake_content = "ONBOARDING_DONE=false\n"
        with (
            patch("src.config.find_env_file", return_value=fake_env),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value=fake_content),
        ):
            self.assertFalse(is_onboarding_done())

    def test_is_onboarding_done_no_env_file(self):
        """Returns False when no .env exists."""
        from src.config import is_onboarding_done
        with patch("src.config.find_env_file", return_value=None):
            self.assertFalse(is_onboarding_done())

    def test_is_onboarding_done_missing_key(self):
        """Returns False when .env exists but ONBOARDING_DONE key is missing."""
        from src.config import is_onboarding_done

        fake_env = Path("/fake/.env")
        fake_content = "AI_BACKEND=deepseek\nWECHAT_BACKEND=wcdb\n"
        with (
            patch("src.config.find_env_file", return_value=fake_env),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value=fake_content),
        ):
            self.assertFalse(is_onboarding_done())

    def test_is_onboarding_done_case_insensitive_value(self):
        """'TRUE' / 'True' variants pass because .lower() == 'true'."""
        from src.config import is_onboarding_done

        fake_env = Path("/fake/.env")
        fake_content = "ONBOARDING_DONE=TRUE\n"
        with (
            patch("src.config.find_env_file", return_value=fake_env),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value=fake_content),
        ):
            self.assertTrue(is_onboarding_done())

    # -- _sanitize_display_name ----------------------------------------

    def test_sanitize_display_name_empty_returns_default(self):
        """Empty string returns the default display name."""
        from src.config import _sanitize_display_name
        self.assertEqual(_sanitize_display_name(""), "群聊小助手")

    def test_sanitize_display_name_none_returns_default(self):
        """None (falsy) returns the default display name."""
        from src.config import _sanitize_display_name
        self.assertEqual(_sanitize_display_name(None), "群聊小助手")

    def test_sanitize_display_name_strips_control_chars(self):
        """CR, LF, and other control chars are removed."""
        from src.config import _sanitize_display_name
        result = _sanitize_display_name("hello\nworld\r\n\x00test\x1b")
        self.assertNotIn("\n", result)
        self.assertNotIn("\r", result)
        self.assertNotIn("\x00", result)
        self.assertNotIn("\x1b", result)
        self.assertIn("hello", result)
        self.assertIn("test", result)

    def test_sanitize_display_name_too_long_truncated(self):
        """Names longer than 128 chars are truncated."""
        from src.config import _sanitize_display_name
        long_name = "A" * 200
        result = _sanitize_display_name(long_name)
        self.assertLessEqual(len(result), 128)
        self.assertEqual(result, "A" * 128)

    def test_sanitize_display_name_whitespace_only_returns_default(self):
        """Whitespace-only names fall back to default."""
        from src.config import _sanitize_display_name
        self.assertEqual(_sanitize_display_name("   \t  \n  "), "群聊小助手")

    def test_sanitize_display_name_preserves_unicode(self):
        """Chinese characters are preserved."""
        from src.config import _sanitize_display_name
        result = _sanitize_display_name("你好世界")
        self.assertEqual(result, "你好世界")

    def test_sanitize_display_name_collapses_whitespace(self):
        """Multiple spaces collapse to a single space."""
        from src.config import _sanitize_display_name
        result = _sanitize_display_name("hello   world")
        self.assertEqual(result, "hello world")

    def test_sanitize_display_name_strips_leading_trailing(self):
        """Leading and trailing whitespace are stripped."""
        from src.config import _sanitize_display_name
        result = _sanitize_display_name("  hello  ")
        self.assertEqual(result, "hello")

    def test_sanitize_display_name_exactly_128_chars_passes(self):
        """A name exactly 128 chars is not truncated."""
        from src.config import _sanitize_display_name
        name = "A" * 128
        self.assertEqual(len(_sanitize_display_name(name)), 128)

    # -- _decode_wechat_groups ----------------------------------------

    def test_decode_wechat_groups_wildcard(self):
        """'*' stays '*'."""
        from src.config import _decode_wechat_groups
        self.assertEqual(_decode_wechat_groups("*"), "*")

    def test_decode_wechat_groups_empty_returns_wildcard(self):
        """Empty string returns '*'."""
        from src.config import _decode_wechat_groups
        self.assertEqual(_decode_wechat_groups(""), "*")

    def test_decode_wechat_groups_whitespace_only_returns_wildcard(self):
        """Whitespace-only returns '*'."""
        from src.config import _decode_wechat_groups
        self.assertEqual(_decode_wechat_groups("   "), "*")

    def test_decode_wechat_groups_single_url_encoded(self):
        """URL-encoded group name is decoded."""
        from src.config import _decode_wechat_groups
        result = _decode_wechat_groups("%E6%B5%8B%E8%AF%95%E7%BE%A4")
        self.assertEqual(result, "测试群")

    def test_decode_wechat_groups_multiple_encoded(self):
        """Multiple comma-separated encoded groups all decode."""
        from src.config import _decode_wechat_groups
        result = _decode_wechat_groups(
            "%E6%B5%8B%E8%AF%95%E7%BE%A4,%E5%B7%A5%E4%BD%9C%E7%BE%A4"
        )
        self.assertEqual(result, "测试群,工作群")

    def test_decode_wechat_groups_mixed_encoded_and_plain(self):
        """Mixed URL-encoded and plain names coexist."""
        from src.config import _decode_wechat_groups
        result = _decode_wechat_groups("plain_group,%E6%B5%8B%E8%AF%95%E7%BE%A4")
        self.assertEqual(result, "plain_group,测试群")

    def test_messages_table_exists_handles_empty_runtime_db(self):
        """Nickname APIs should treat an initialized-empty sqlite file as no groups."""
        from src.web.server import _messages_table_exists

        conn = sqlite3.connect(":memory:")
        self.assertFalse(_messages_table_exists(conn))

        conn.execute("CREATE TABLE messages (chat_id TEXT, sender_id TEXT)")
        self.assertTrue(_messages_table_exists(conn))


# ======================================================================
#  TestTriggerDetector -- keyword + @mention detection
# ======================================================================


class TestTriggerDetector(unittest.TestCase):
    """Tests for TriggerDetector: keyword matching, @mention detection,
    empty content, edge cases."""

    def setUp(self):
        from src.trigger.detector import TriggerDetector
        self.TriggerDetector = TriggerDetector

    def test_exact_keyword_match(self):
        """An exact match on a keyword triggers."""
        detector = self.TriggerDetector(
            keywords=["总结一下", "summarize"],
            bot_display_name="小助手",
        )
        self.assertTrue(
            detector.is_trigger("总结一下", is_at_mentioned=False,
                               sender_name="user")
        )

    def test_substring_keyword_match(self):
        """Keyword found as substring triggers (uses 'in' check)."""
        detector = self.TriggerDetector(
            keywords=["总结"],
            bot_display_name="小助手",
        )
        self.assertTrue(
            detector.is_trigger("请帮我总结一下今天的内容",
                               is_at_mentioned=False, sender_name="user")
        )

    def test_case_insensitive_match(self):
        """Keyword matching is case-insensitive."""
        detector = self.TriggerDetector(
            keywords=["Summarize", "What Did I Miss"],
            bot_display_name="小助手",
        )
        self.assertTrue(
            detector.is_trigger("summarize this for me",
                               is_at_mentioned=False, sender_name="user")
        )
        self.assertTrue(
            detector.is_trigger("WHAT DID I MISS?",
                               is_at_mentioned=False, sender_name="user")
        )

    def test_at_mention_always_triggers(self):
        """is_at_mentioned=True always triggers regardless of content."""
        detector = self.TriggerDetector(
            keywords=["总结"],
            bot_display_name="小助手",
        )
        self.assertTrue(
            detector.is_trigger("random chat message",
                               is_at_mentioned=True, sender_name="user")
        )

    def test_at_mention_even_with_empty_content(self):
        """is_at_mentioned=True with empty content still triggers."""
        detector = self.TriggerDetector(
            keywords=["总结"],
            bot_display_name="小助手",
        )
        self.assertTrue(
            detector.is_trigger("", is_at_mentioned=True, sender_name="user")
        )

    def test_no_match_when_no_keyword_and_no_mention(self):
        """A message without keyword or @mention does not trigger."""
        detector = self.TriggerDetector(
            keywords=["总结", "summarize"],
            bot_display_name="小助手",
        )
        self.assertFalse(
            detector.is_trigger("今天天气不错",
                               is_at_mentioned=False, sender_name="user")
        )

    def test_empty_content_no_mention_does_not_trigger(self):
        """Empty content without @mention does not trigger."""
        detector = self.TriggerDetector(
            keywords=["总结"],
            bot_display_name="小助手",
        )
        self.assertFalse(
            detector.is_trigger("", is_at_mentioned=False, sender_name="user")
        )

    def test_empty_keyword_list_no_false_positive(self):
        """An empty keyword list never causes a false trigger."""
        detector = self.TriggerDetector(
            keywords=[],
            bot_display_name="小助手",
        )
        self.assertFalse(
            detector.is_trigger("总结一下",
                               is_at_mentioned=False, sender_name="user")
        )

    def test_whitespace_only_keyword_not_added(self):
        """Keywords that are whitespace-only after stripping are excluded."""
        detector = self.TriggerDetector(
            keywords=["总结", "   ", "\t"],
            bot_display_name="小助手",
        )
        self.assertEqual(len(detector.keywords), 1)
        self.assertIn("总结", detector.keywords)

    def test_keyword_with_leading_trailing_spaces_trimmed(self):
        """Keywords with surrounding whitespace are trimmed."""
        detector = self.TriggerDetector(
            keywords=["  总结  "],
            bot_display_name="小助手",
        )
        self.assertIn("总结", detector.keywords)
        self.assertTrue(
            detector.is_trigger("总结", is_at_mentioned=False,
                               sender_name="user")
        )

    def test_chinese_keyword_match(self):
        """Chinese keywords match correctly."""
        detector = self.TriggerDetector(
            keywords=["说了啥", "发生了什么", "聊天总结"],
            bot_display_name="小助手",
        )
        self.assertTrue(
            detector.is_trigger("前面说了啥",
                               is_at_mentioned=False, sender_name="user")
        )
        self.assertTrue(
            detector.is_trigger("发生了什么我不知道的事",
                               is_at_mentioned=False, sender_name="user")
        )

    def test_partial_word_boundary_match(self):
        """Keyword matches inside a longer word (substring match)."""
        detector = self.TriggerDetector(
            keywords=["help"],
            bot_display_name="小助手",
        )
        self.assertTrue(
            detector.is_trigger("helpless situation",
                               is_at_mentioned=False, sender_name="user")
        )

    def test_special_characters_in_keyword(self):
        """Keywords with special characters still match."""
        detector = self.TriggerDetector(
            keywords=["@bot", "what's up"],
            bot_display_name="小助手",
        )
        self.assertTrue(
            detector.is_trigger("hey @bot come here",
                               is_at_mentioned=False, sender_name="user")
        )

    def test_bot_name_as_keyword_is_just_string_match(self):
        """Having the bot name as a keyword is just a string match,
        not @-semantics."""
        detector = self.TriggerDetector(
            keywords=["小助手"],
            bot_display_name="小助手",
        )
        self.assertTrue(
            detector.is_trigger("小助手在不",
                               is_at_mentioned=False, sender_name="user")
        )


# ======================================================================
#  Web API endpoint handler tests
# ======================================================================


class MockSocket:
    """Minimal mock socket for testing _UIHandler.

    Provides enough of the socket interface for BaseHTTPRequestHandler to
    parse an HTTP request and write a response.

    IMPORTANT: BaseHTTPRequestHandler / StreamRequestHandler sets ``wfile``
    to a ``socketserver._SocketWriter`` instance (not a file object from
    ``makefile``).  _SocketWriter accumulates writes and flushes them via
    ``self._sock.sendall()``.  We therefore capture **sendall** calls to
    reconstruct the HTTP response text.
    """

    def __init__(self, request_bytes: bytes = b""):
        self._rbuf = io.BytesIO(request_bytes)
        self._wbuf = io.BytesIO()                # returned for makefile('rb') compat
        self._sent_chunks: list[bytes] = []       # captured via sendall()

    def makefile(self, mode: str, *args, **kwargs):
        if mode == "rb":
            return self._rbuf
        # _SocketWriter bypasses makefile entirely.  Return self._wbuf
        # anyway for any code path that might still use it.
        return self._wbuf

    def sendall(self, data: bytes):
        """Captured by _SocketWriter when it flushes the HTTP response."""
        self._sent_chunks.append(data)

    def get_response_text(self) -> str:
        """Reconstruct the full HTTP response text from captured chunks."""
        return b"".join(self._sent_chunks).decode("utf-8", errors="replace")


def _build_handler(path: str, method: str = "GET", body: bytes = b"",
                   headers: dict | None = None):
    """Construct a _UIHandler with a pre-built HTTP request.

    Returns (handler, sock) where ``sock`` is the MockSocket that captured
    the response.  Call ``sock.get_response_text()`` to read the HTTP
    response, then split on ``\\r\\n\\r\\n`` to separate headers and body.
    """
    from src.web.server import _UIHandler

    if headers is None:
        headers = {}
    header_lines = "\r\n".join(
        f"{k}: {v}" for k, v in headers.items()
    )
    content_length = f"Content-Length: {len(body)}\r\n" if body else ""
    raw = (
        f"{method} {path} HTTP/1.1\r\n"
        f"Host: localhost\r\n"
        f"{content_length}"
        f"{header_lines}\r\n"
        f"\r\n"
    ).encode() + body

    sock = MockSocket(raw)
    handler = _UIHandler(sock, ("127.0.0.1", 9999), MagicMock())
    return handler, sock


# ---------------------------------------------------------------------------
# _ServerStatus tests
# ---------------------------------------------------------------------------


class ServerStatusTests(unittest.TestCase):
    """Tests for _ServerStatus -- thread-safe status tracking."""

    def setUp(self):
        from src.web.server import _ServerStatus
        self.status = _ServerStatus()

    def test_snapshot_returns_all_expected_fields(self):
        """snapshot() returns all documented _FIELDS."""
        snap = self.status.snapshot()
        expected_fields = {
            "running", "uptime_sec", "messages_processed",
            "wechat_backend", "ai_backend", "db_ok",
            "last_api_call_sec_ago", "last_api_call_time",
            "timestamp", "error",
        }
        self.assertEqual(set(snap.keys()), expected_fields)

    def test_default_snapshot_values(self):
        """Fresh instance has sensible defaults."""
        snap = self.status.snapshot()
        self.assertFalse(snap["running"])
        self.assertEqual(snap["uptime_sec"], 0)
        self.assertEqual(snap["messages_processed"], 0)
        self.assertEqual(snap["wechat_backend"], "")
        self.assertEqual(snap["ai_backend"], "")
        self.assertFalse(snap["db_ok"])
        self.assertEqual(snap["last_api_call_sec_ago"], -1)

    def test_update_changes_fields(self):
        """update() sets fields and updates timestamp."""
        self.status.update(
            running=True, wechat_backend="wcdb", messages_processed=42,
        )
        snap = self.status.snapshot()
        self.assertTrue(snap["running"])
        self.assertEqual(snap["wechat_backend"], "wcdb")
        self.assertEqual(snap["messages_processed"], 42)
        self.assertTrue(snap["timestamp"])
        self.assertIn("T", snap["timestamp"])

    def test_update_ignores_unknown_fields(self):
        """update() silently ignores keys that are not real attributes."""
        self.status.update(nonexistent_field="value")
        snap = self.status.snapshot()
        self.assertNotIn("nonexistent_field", snap)

    def test_snapshot_is_a_copy(self):
        """Modifying the returned snapshot dict does not affect internal state."""
        snap = self.status.snapshot()
        snap["running"] = True
        snap["error"] = "hacked"
        snap2 = self.status.snapshot()
        self.assertFalse(snap2["running"])
        self.assertEqual(snap2["error"], "")

    def test_update_preserves_unchanged_fields(self):
        """Fields not passed to update() keep their values."""
        self.status.update(running=True)
        snap = self.status.snapshot()
        self.assertTrue(snap["running"])
        self.assertEqual(snap["ai_backend"], "")

    def test_update_broadcasts_to_websocket_clients(self):
        """update() broadcasts to all connected WebSocket clients."""
        mock_sock = MagicMock()
        self.status.add_client(mock_sock)
        with patch("src.web.server._send_ws_frame") as mock_send:
            self.status.update(running=True, messages_processed=5)
        mock_send.assert_called_once()
        payload = json.loads(mock_send.call_args[0][1])
        self.assertTrue(payload["running"])
        self.assertEqual(payload["messages_processed"], 5)

    def test_remove_client_removes_disconnected(self):
        """remove_client removes a socket from the client list."""
        mock_sock = MagicMock()
        self.status.add_client(mock_sock)
        self.status.remove_client(mock_sock)
        with patch("src.web.server._send_ws_frame") as mock_send:
            self.status.update(running=True)
        mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# _BotControl tests
# ---------------------------------------------------------------------------


class BotControlTests(unittest.TestCase):
    """Tests for _BotControl -- bot lifecycle management."""

    def setUp(self):
        from src.web.server import _BotControl
        self.control = _BotControl()

    def test_initial_state_not_running(self):
        """Fresh _BotControl is not running."""
        self.assertFalse(self.control.is_running())

    def test_set_running_makes_it_running(self):
        """set_running() -> is_running() returns True."""
        self.control.set_running()
        self.assertTrue(self.control.is_running())

    def test_register_sets_running_and_thread(self):
        """register() sets thread, backend, and running flag."""
        fake_thread = MagicMock()
        fake_backend = MagicMock()
        self.control.register(thread=fake_thread, backend=fake_backend)
        self.assertTrue(self.control.is_running())
        self.assertIs(self.control.thread, fake_thread)
        self.assertIs(self.control.backend, fake_backend)

    def test_mark_stopped_resets_state(self):
        """mark_stopped() resets running, backend, and thread."""
        self.control.set_running()
        fake_backend = MagicMock()
        fake_thread = MagicMock()
        self.control.register(backend=fake_backend, thread=fake_thread)
        self.control.mark_stopped()
        self.assertFalse(self.control.is_running())
        self.assertIsNone(self.control.backend)
        self.assertIsNone(self.control.thread)

    def test_mark_stopped_does_not_call_backend_stop(self):
        """mark_stopped() just resets state -- does NOT stop backend."""
        fake_backend = MagicMock()
        self.control.register(backend=fake_backend)
        self.control.mark_stopped()
        fake_backend.stop.assert_not_called()

    def test_stop_calls_backend_stop_and_joins_thread(self):
        """stop() calls backend.stop() and thread.join()."""
        fake_backend = MagicMock()
        fake_thread = MagicMock()
        fake_thread.is_alive.return_value = True
        self.control.register(backend=fake_backend, thread=fake_thread)
        self.control.stop()
        fake_backend.stop.assert_called_once()
        fake_thread.join.assert_called_once_with(timeout=30)
        self.assertFalse(self.control.is_running())

    def test_stop_handles_backend_without_stop_method(self):
        """stop() does not crash if backend has no stop() method."""
        self.control.stop()
        self.assertFalse(self.control.is_running())

    def test_stop_handles_none_thread(self):
        """stop() does not crash if thread is None."""
        self.control.set_running()
        self.control.stop()
        self.assertFalse(self.control.is_running())

    def test_register_backend_stores_reference(self):
        """register_backend() stores the backend without setting running."""
        fake_backend = MagicMock()
        self.control.register_backend(fake_backend)
        self.assertIs(self.control.backend, fake_backend)


# ---------------------------------------------------------------------------
# _ServerStartGuard tests
# ---------------------------------------------------------------------------


class ServerStartGuardTests(unittest.TestCase):
    """Tests for _ServerStartGuard -- idempotent server start."""

    def test_first_try_start_returns_true(self):
        """First call to try_start() returns True."""
        from src.web.server import _ServerStartGuard
        guard = _ServerStartGuard()
        self.assertTrue(guard.try_start())

    def test_second_try_start_returns_false(self):
        """Second call to try_start() returns False (already started)."""
        from src.web.server import _ServerStartGuard
        guard = _ServerStartGuard()
        guard.try_start()
        self.assertFalse(guard.try_start())

    def test_multiple_try_start_always_false_after_first(self):
        """All calls after the first return False."""
        from src.web.server import _ServerStartGuard
        guard = _ServerStartGuard()
        self.assertTrue(guard.try_start())
        for _ in range(10):
            self.assertFalse(guard.try_start())


# ---------------------------------------------------------------------------
# Public API tests
# ---------------------------------------------------------------------------


class PublicApiTests(unittest.TestCase):
    """Tests for the public API wrapper functions."""

    def test_update_status_calls_status_update(self):
        """update_status() delegates to _status.update()."""
        from src.web.server import update_status, _status
        with patch.object(_status, "update") as mock_update:
            update_status(running=True, error="test")
            mock_update.assert_called_once_with(running=True, error="test")

    def test_stop_bot_returns_false_when_not_running(self):
        """_stop_bot() handles the case where nothing is running."""
        from src.web.server import _stop_bot, _bot_control
        _bot_control.mark_stopped()
        result = _stop_bot()
        self.assertFalse(result)

    def test_start_bot_in_thread_returns_error_when_already_running(self):
        """_start_bot_in_thread() refuses if bot is already running."""
        from src.web.server import _start_bot_in_thread, _bot_control
        _bot_control.set_running()
        result = _start_bot_in_thread()
        self.assertFalse(result["ok"])
        self.assertIn("already running", result["error"])
        _bot_control.mark_stopped()  # cleanup


# ---------------------------------------------------------------------------
# /api/status endpoint tests
# ---------------------------------------------------------------------------


class ApiStatusEndpointTests(unittest.TestCase):
    """Tests for GET /api/status."""

    def test_status_returns_json_with_expected_fields(self):
        """GET /api/status returns 200 with JSON containing key fields."""
        from src.web.server import _status
        _status.update(running=False, ai_backend="claude")
        handler, sock = _build_handler("/api/status")
        response = sock.get_response_text()
        self.assertIn("200", response.splitlines()[0])
        parts = response.split("\r\n\r\n", 1)
        self.assertEqual(len(parts), 2,
                         "Response should have headers and body")
        body = json.loads(parts[1])
        self.assertIn("running", body)
        self.assertIn("messages_processed", body)
        self.assertIn("ai_backend", body)
        self.assertIn("error", body)

    def test_status_when_bot_stopped(self):
        """Status reflects bot stopped state with error info."""
        from src.web.server import _status
        _status.update(running=False, error="KEY_MISSING")
        handler, sock = _build_handler("/api/status")
        parts = sock.get_response_text().split("\r\n\r\n", 1)
        body = json.loads(parts[1])
        self.assertFalse(body["running"])
        self.assertEqual(body["error"], "KEY_MISSING")

    def test_status_has_cors_headers(self):
        """Status response includes CORS headers."""
        handler, sock = _build_handler("/api/status")
        response = sock.get_response_text()
        self.assertIn("Access-Control-Allow-Origin: *", response)


# ---------------------------------------------------------------------------
# /api/start and /api/stop endpoint tests
# ---------------------------------------------------------------------------


class ApiStartStopEndpointTests(unittest.TestCase):
    """Tests for /api/start and /api/stop."""

    def tearDown(self):
        from src.web.server import _bot_control
        _bot_control.mark_stopped()

    def test_start_when_already_running_returns_already_running(self):
        """POST /api/start when bot is running -> already_running=True."""
        from src.web.server import _bot_control
        _bot_control.set_running()
        handler, sock = _build_handler("/api/start", method="POST")
        parts = sock.get_response_text().split("\r\n\r\n", 1)
        body = json.loads(parts[1])
        self.assertTrue(body["ok"])
        self.assertTrue(body.get("already_running"))

    def test_start_when_not_running_starts_bot(self):
        """POST /api/start when bot is not running -> starts bot thread."""
        from src.web.server import _bot_control
        _bot_control.mark_stopped()
        with patch("src.web.server._start_bot_in_thread",
                   return_value={"ok": True}):
            handler, sock = _build_handler("/api/start", method="POST")
            parts = sock.get_response_text().split("\r\n\r\n", 1)
            body = json.loads(parts[1])
            self.assertTrue(body["ok"])

    def test_stop_returns_ok(self):
        """POST /api/stop returns ok=True."""
        handler, sock = _build_handler("/api/stop", method="POST")
        parts = sock.get_response_text().split("\r\n\r\n", 1)
        body = json.loads(parts[1])
        self.assertTrue(body["ok"])

    def test_stop_when_bot_not_running_returns_ok(self):
        """POST /api/stop succeeds even when nothing is running."""
        from src.web.server import _bot_control
        _bot_control.mark_stopped()
        handler, sock = _build_handler("/api/stop", method="POST")
        parts = sock.get_response_text().split("\r\n\r\n", 1)
        body = json.loads(parts[1])
        self.assertTrue(body["ok"])


# ---------------------------------------------------------------------------
# /api/config and /api/load-config endpoint tests
# ---------------------------------------------------------------------------


class ApiConfigEndpointTests(unittest.TestCase):
    """Tests for /api/config and /api/load-config."""

    def test_load_config_returns_defaults_when_no_env(self):
        """GET /api/load-config returns defaults when no .env exists."""
        with patch("src.web.server._find_or_create_env") as mock_find:
            fake_env = MagicMock()
            fake_env.exists.return_value = False
            mock_find.return_value = fake_env
            handler, sock = _build_handler("/api/load-config")
            parts = sock.get_response_text().split("\r\n\r\n", 1)
            body = json.loads(parts[1])
            self.assertTrue(body["ok"])
            config = body["config"]
            self.assertEqual(config["ai_backend"], "deepseek")
            self.assertEqual(config["wechat_backend"], "wcdb")

    def test_load_config_reads_env_values(self):
        """GET /api/load-config reads values from .env file."""
        with patch("src.web.server._find_or_create_env") as mock_find:
            fake_env = MagicMock()
            fake_env.exists.return_value = True
            fake_env.read_text.return_value = (
                "AI_BACKEND=claude\n"
                "DEEPSEEK_BASE_URL=https://proxy.example.com/v1\n"
                "ANTHROPIC_BASE_URL=https://claude-proxy.example.com\n"
                "BOT_DISPLAY_NAME=MyBot\n"
                "FUN_ENABLED=false\n"
            )
            mock_find.return_value = fake_env
            handler, sock = _build_handler("/api/load-config")
            parts = sock.get_response_text().split("\r\n\r\n", 1)
            body = json.loads(parts[1])
            config = body["config"]
            self.assertEqual(config["ai_backend"], "claude")
            self.assertEqual(config["deepseek_base_url"], "https://proxy.example.com/v1")
            self.assertEqual(config["anthropic_base_url"], "https://claude-proxy.example.com")
            self.assertEqual(config["bot_display_name"], "MyBot")
            self.assertFalse(config["fun_enabled"])

    def test_load_config_reads_openai_values(self):
        """GET /api/load-config returns openai fields (masked key + base_url/model)."""
        with patch("src.web.server._find_or_create_env") as mock_find:
            fake_env = MagicMock()
            fake_env.exists.return_value = True
            fake_env.read_text.return_value = (
                "AI_BACKEND=openai\n"
                "OPENAI_API_KEY=sk-glm-test-key\n"
                "OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4/\n"
                "OPENAI_MODEL=glm-4-flash\n"
            )
            mock_find.return_value = fake_env
            handler, sock = _build_handler("/api/load-config")
            parts = sock.get_response_text().split("\r\n\r\n", 1)
            body = json.loads(parts[1])
            config = body["config"]
            self.assertEqual(config["ai_backend"], "openai")
            self.assertNotIn("sk-glm-test-key", config["openai_api_key"])
            self.assertEqual(config["openai_base_url"], "https://open.bigmodel.cn/api/paas/v4/")
            self.assertEqual(config["openai_model"], "glm-4-flash")

    def test_load_config_reads_feishu_export_values(self):
        """GET /api/load-config reads Feishu export settings from .env."""
        with patch("src.web.server._find_or_create_env") as mock_find:
            fake_env = MagicMock()
            fake_env.exists.return_value = True
            fake_env.read_text.return_value = (
                "FEISHU_EXPORT_ENABLED=true\n"
                "FEISHU_APP_ID=cli_test\n"
                "FEISHU_APP_SECRET=secret_test\n"
                "FEISHU_EXPORT_MODE=knowledge\n"
                "FEISHU_EXPORT_WINDOW_HOURS=6\n"
                "FEISHU_AUTO_SYNC_ENABLED=true\n"
                "FEISHU_AUTO_SYNC_MIN_MESSAGES=7\n"
                "FEISHU_AUTO_SYNC_COOLDOWN_SEC=900\n"
                "FEISHU_KNOWLEDGE_BASE_NAME=webot 自动知识库\n"
                "FEISHU_KNOWLEDGE_FOLDER_TOKEN=fld_knowledge\n"
                "FEISHU_EXPORT_TRIGGER_KEYWORDS=同步到飞书,导出到飞书\n"
                "FEISHU_SPREADSHEET_TOKEN=sht_test\n"
                "FEISHU_SPREADSHEET_RANGE=Sheet1!A:H\n"
                "FEISHU_BITABLE_APP_TOKEN=base_test\n"
                "FEISHU_BITABLE_TABLE_ID=tbl_test\n"
                "FEISHU_DOC_FOLDER_TOKEN=fld_test\n"
            )
            mock_find.return_value = fake_env

            handler, sock = _build_handler("/api/load-config")
            parts = sock.get_response_text().split("\r\n\r\n", 1)
            body = json.loads(parts[1])

        config = body["config"]
        self.assertTrue(config["feishu_export_enabled"])
        self.assertEqual(config["feishu_app_id"], "cli_test")
        self.assertEqual(config["feishu_app_secret"], "secret_test")
        self.assertEqual(config["feishu_export_mode"], "knowledge")
        self.assertEqual(config["feishu_export_window_hours"], 6)
        self.assertTrue(config["feishu_auto_sync_enabled"])
        self.assertEqual(config["feishu_auto_sync_min_messages"], 7)
        self.assertEqual(config["feishu_auto_sync_cooldown_sec"], 900)
        self.assertEqual(config["feishu_knowledge_base_name"], "webot 自动知识库")
        self.assertEqual(config["feishu_knowledge_folder_token"], "fld_knowledge")
        self.assertEqual(config["feishu_export_trigger_keywords"], ["同步到飞书", "导出到飞书"])
        self.assertEqual(config["feishu_spreadsheet_token"], "sht_test")
        self.assertEqual(config["feishu_spreadsheet_range"], "Sheet1!A:H")
        self.assertEqual(config["feishu_bitable_app_token"], "base_test")
        self.assertEqual(config["feishu_bitable_table_id"], "tbl_test")
        self.assertEqual(config["feishu_doc_folder_token"], "fld_test")

    def test_load_config_empty_env_returns_defaults(self):
        """GET /api/load-config with empty env returns defaults."""
        with patch("src.web.server._find_or_create_env") as mock_find:
            fake_env = MagicMock()
            fake_env.exists.return_value = True
            fake_env.read_text.return_value = ""
            mock_find.return_value = fake_env
            handler, sock = _build_handler("/api/load-config")
            parts = sock.get_response_text().split("\r\n\r\n", 1)
            body = json.loads(parts[1])
            self.assertTrue(body["ok"])
            self.assertIsInstance(body["config"], dict)

    def test_save_config_returns_ok_and_saved_keys(self):
        """POST /api/config saves settings and returns saved keys."""
        with patch("src.web.server._find_or_create_env") as mock_find:
            fake_env = MagicMock()
            fake_env.exists.return_value = True
            fake_env.read_text.return_value = (
                "AI_BACKEND=deepseek\n"
                "BOT_DISPLAY_NAME=oldname\n"
            )
            fake_env.with_suffix.return_value = fake_env
            mock_find.return_value = fake_env
            with patch("os.replace") as mock_replace:
                body = json.dumps({
                    "bot_display_name": "newname",
                    "ai_backend": "claude",
                })
                handler, sock = _build_handler(
                    "/api/config", method="POST",
                    body=body.encode(),
                    headers={"Content-Type": "application/json"},
                )
                parts = sock.get_response_text().split("\r\n\r\n", 1)
                result = json.loads(parts[1])
                self.assertTrue(result["ok"])
                self.assertIn("BOT_DISPLAY_NAME", result["saved"])
                self.assertIn("AI_BACKEND", result["saved"])
                self.assertTrue(result["requires_restart"])

    def test_save_config_adds_new_keys(self):
        """POST /api/config adds new keys not present in existing .env."""
        with patch("src.web.server._find_or_create_env") as mock_find:
            fake_env = MagicMock()
            fake_env.exists.return_value = True
            fake_env.read_text.return_value = "AI_BACKEND=deepseek\n"
            fake_env.with_suffix.return_value = fake_env
            mock_find.return_value = fake_env
            with patch("os.replace") as mock_replace:
                body = json.dumps({"bot_display_name": "MyBot"})
                handler, sock = _build_handler(
                    "/api/config", method="POST",
                    body=body.encode(),
                    headers={"Content-Type": "application/json"},
                )
                parts = sock.get_response_text().split("\r\n\r\n", 1)
                result = json.loads(parts[1])
                self.assertTrue(result["ok"])

    def test_save_config_roundtrip(self):
        """POST /api/config saves, and load-config reads it back correctly."""
        tmp_dir = Path(tempfile.mkdtemp())
        tmp_env = tmp_dir / ".env"
        tmp_env.write_text(
            "AI_BACKEND=deepseek\nDEEPSEEK_API_KEY=old-key\n"
            "BOT_DISPLAY_NAME=old-name\n",
            encoding="utf-8",
        )
        try:
            # -- Save --
            save_body = json.dumps({
                "deepseek_api_key": "new-key",
                "deepseek_base_url": "https://proxy.example.com/v1",
                "anthropic_base_url": "https://claude-proxy.example.com",
                "bot_display_name": "new-name",
                "fun_enabled": False,
            }).encode()
            with patch("src.web.server._find_or_create_env",
                       return_value=tmp_env):
                handler, sock = _build_handler(
                    "/api/config", method="POST",
                    body=save_body,
                    headers={"Content-Type": "application/json",
                             "Content-Length": str(len(save_body))},
                )
                parts = sock.get_response_text().split("\r\n\r\n", 1)
                result = json.loads(parts[1])
                self.assertTrue(result["ok"])

            # -- Read back --
            saved_content = tmp_env.read_text(encoding="utf-8")
            self.assertIn("DEEPSEEK_API_KEY=new-key", saved_content)
            self.assertIn("DEEPSEEK_BASE_URL=https://proxy.example.com/v1", saved_content)
            self.assertIn("ANTHROPIC_BASE_URL=https://claude-proxy.example.com", saved_content)
            self.assertIn("BOT_DISPLAY_NAME=new-name", saved_content)
            self.assertIn("FUN_ENABLED=false", saved_content)
            self.assertIn("AI_BACKEND=deepseek", saved_content)
        finally:
            tmp_env.unlink(missing_ok=True)
            for f in tmp_dir.glob("*"):
                f.unlink(missing_ok=True)
            tmp_dir.rmdir()

    def test_save_config_roundtrip_openai(self):
        """POST /api/config persists OPENAI_* values and load-config reads them."""
        tmp_dir = Path(tempfile.mkdtemp())
        tmp_env = tmp_dir / ".env"
        tmp_env.write_text("AI_BACKEND=deepseek\n", encoding="utf-8")
        try:
            save_body = json.dumps({
                "ai_backend": "openai",
                "openai_api_key": "sk-glm-new-key",
                "openai_base_url": "https://open.bigmodel.cn/api/paas/v4/",
                "openai_model": "glm-4-flash",
            }).encode()
            with patch("src.web.server._find_or_create_env",
                       return_value=tmp_env):
                handler, sock = _build_handler(
                    "/api/config", method="POST",
                    body=save_body,
                    headers={"Content-Type": "application/json",
                             "Content-Length": str(len(save_body))},
                )
                parts = sock.get_response_text().split("\r\n\r\n", 1)
                result = json.loads(parts[1])
                self.assertTrue(result["ok"])

            saved_content = tmp_env.read_text(encoding="utf-8")
            self.assertIn("AI_BACKEND=openai", saved_content)
            self.assertIn("OPENAI_API_KEY=sk-glm-new-key", saved_content)
            self.assertIn("OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4/", saved_content)
            self.assertIn("OPENAI_MODEL=glm-4-flash", saved_content)
        finally:
            tmp_env.unlink(missing_ok=True)
            for f in tmp_dir.glob("*"):
                f.unlink(missing_ok=True)
            tmp_dir.rmdir()

    def test_save_config_does_not_overwrite_masked_openai_key(self):
        """Saving a masked OPENAI_API_KEY must not clobber the real secret."""
        tmp_dir = Path(tempfile.mkdtemp())
        tmp_env = tmp_dir / ".env"
        tmp_env.write_text(
            "AI_BACKEND=openai\nOPENAI_API_KEY=sk-real-secret-key\n",
            encoding="utf-8",
        )
        try:
            save_body = json.dumps({
                "ai_backend": "openai",
                "openai_api_key": "sk-r***t-key",
                "openai_model": "glm-4-flash",
            }).encode()
            with patch("src.web.server._find_or_create_env",
                       return_value=tmp_env):
                handler, sock = _build_handler(
                    "/api/config", method="POST",
                    body=save_body,
                    headers={"Content-Type": "application/json",
                             "Content-Length": str(len(save_body))},
                )
                parts = sock.get_response_text().split("\r\n\r\n", 1)
                result = json.loads(parts[1])
                self.assertTrue(result["ok"])

            saved_content = tmp_env.read_text(encoding="utf-8")
            self.assertIn("OPENAI_API_KEY=sk-real-secret-key", saved_content)
            self.assertNotIn("sk-r***t-key", saved_content)
        finally:
            tmp_env.unlink(missing_ok=True)
            for f in tmp_dir.glob("*"):
                f.unlink(missing_ok=True)
            tmp_dir.rmdir()

    def test_save_config_roundtrip_feishu_export_values(self):
        """POST /api/config persists Feishu settings and load-config reads them."""
        tmp_dir = Path(tempfile.mkdtemp())
        tmp_env = tmp_dir / ".env"
        tmp_env.write_text("AI_BACKEND=deepseek\n", encoding="utf-8")
        try:
            save_body = json.dumps({
                "feishu_export_enabled": True,
                "feishu_app_id": "cli_test",
                "feishu_app_secret": "secret_test",
                "feishu_export_mode": "knowledge",
                "feishu_export_window_hours": 12,
                "feishu_auto_sync_enabled": True,
                "feishu_auto_sync_min_messages": 9,
                "feishu_auto_sync_cooldown_sec": 1200,
                "feishu_knowledge_base_name": "webot 群聊沉淀",
                "feishu_knowledge_folder_token": "fld_knowledge",
                "feishu_export_trigger_keywords": ["同步到飞书", "飞书沉淀"],
                "feishu_spreadsheet_token": "sht_test",
                "feishu_spreadsheet_range": "Sheet1!A:H",
                "feishu_bitable_app_token": "base_test",
                "feishu_bitable_table_id": "tbl_test",
                "feishu_doc_folder_token": "fld_test",
            }).encode()
            with patch("src.web.server._find_or_create_env", return_value=tmp_env):
                handler, sock = _build_handler(
                    "/api/config", method="POST",
                    body=save_body,
                    headers={"Content-Type": "application/json",
                             "Content-Length": str(len(save_body))},
                )
                parts = sock.get_response_text().split("\r\n\r\n", 1)
                result = json.loads(parts[1])
                self.assertTrue(result["ok"])

            saved = tmp_env.read_text(encoding="utf-8")
            self.assertIn("FEISHU_EXPORT_ENABLED=true", saved)
            self.assertIn("FEISHU_APP_ID=cli_test", saved)
            self.assertIn("FEISHU_APP_SECRET=secret_test", saved)
            self.assertIn("FEISHU_EXPORT_MODE=knowledge", saved)
            self.assertIn("FEISHU_EXPORT_WINDOW_HOURS=12", saved)
            self.assertIn("FEISHU_AUTO_SYNC_ENABLED=true", saved)
            self.assertIn("FEISHU_AUTO_SYNC_MIN_MESSAGES=9", saved)
            self.assertIn("FEISHU_AUTO_SYNC_COOLDOWN_SEC=1200", saved)
            self.assertIn("FEISHU_KNOWLEDGE_BASE_NAME=webot 群聊沉淀", saved)
            self.assertIn("FEISHU_KNOWLEDGE_FOLDER_TOKEN=fld_knowledge", saved)
            self.assertIn("FEISHU_EXPORT_TRIGGER_KEYWORDS=同步到飞书,飞书沉淀", saved)
            self.assertIn("FEISHU_SPREADSHEET_TOKEN=sht_test", saved)
            self.assertIn("FEISHU_SPREADSHEET_RANGE=Sheet1!A:H", saved)
            self.assertIn("FEISHU_BITABLE_APP_TOKEN=base_test", saved)
            self.assertIn("FEISHU_BITABLE_TABLE_ID=tbl_test", saved)
            self.assertIn("FEISHU_DOC_FOLDER_TOKEN=fld_test", saved)

            with patch("src.web.server._find_or_create_env", return_value=tmp_env):
                handler, sock = _build_handler("/api/load-config")
                parts = sock.get_response_text().split("\r\n\r\n", 1)
                body = json.loads(parts[1])

            config = body["config"]
            self.assertTrue(config["feishu_export_enabled"])
            self.assertEqual(config["feishu_export_mode"], "knowledge")
            self.assertTrue(config["feishu_auto_sync_enabled"])
            self.assertEqual(config["feishu_auto_sync_min_messages"], 9)
            self.assertEqual(config["feishu_auto_sync_cooldown_sec"], 1200)
            self.assertEqual(config["feishu_knowledge_base_name"], "webot 群聊沉淀")
            self.assertEqual(config["feishu_knowledge_folder_token"], "fld_knowledge")
            self.assertEqual(config["feishu_export_trigger_keywords"], ["同步到飞书", "飞书沉淀"])
        finally:
            tmp_env.unlink(missing_ok=True)
            for f in tmp_dir.glob("*"):
                f.unlink(missing_ok=True)
            tmp_dir.rmdir()

    def test_save_config_updates_process_environment(self):
        """Saved config is available to bot threads started in this process."""
        tmp_dir = Path(tempfile.mkdtemp())
        tmp_env = tmp_dir / ".env"
        tmp_env.write_text(
            "AI_BACKEND=deepseek\n"
            "DEEPSEEK_API_KEY=old-key\n"
            "DEEPSEEK_BASE_URL=https://api.deepseek.com\n"
            "DEEPSEEK_MODEL=old-model\n",
            encoding="utf-8",
        )
        save_body = json.dumps({
            "ai_backend": "deepseek",
            "deepseek_api_key": "new-key",
            "deepseek_base_url": "https://proxy.example.com/v1",
            "deepseek_model": "new-model",
        }).encode()
        try:
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("src.web.server._find_or_create_env",
                      return_value=tmp_env),
            ):
                handler, sock = _build_handler(
                    "/api/config", method="POST",
                    body=save_body,
                    headers={"Content-Type": "application/json",
                             "Content-Length": str(len(save_body))},
                )
                parts = sock.get_response_text().split("\r\n\r\n", 1)
                result = json.loads(parts[1])
                self.assertTrue(result["ok"])
                self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "new-key")
                self.assertEqual(
                    os.environ["DEEPSEEK_BASE_URL"],
                    "https://proxy.example.com/v1",
                )
                self.assertEqual(os.environ["DEEPSEEK_MODEL"], "new-model")
        finally:
            tmp_env.unlink(missing_ok=True)
            for f in tmp_dir.glob("*"):
                f.unlink(missing_ok=True)
            tmp_dir.rmdir()

    def test_save_config_invalid_json_returns_error(self):
        """POST /api/config with malformed JSON returns error."""
        handler, sock = _build_handler(
            "/api/config", method="POST",
            body=b"not-json{{{",
            headers={"Content-Type": "application/json"},
        )
        parts = sock.get_response_text().split("\r\n\r\n", 1)
        body = json.loads(parts[1])
        self.assertFalse(body["ok"])
        self.assertIn("error", body)

    def test_save_config_empty_body_handled(self):
        """POST /api/config with empty body should not crash."""
        with patch("src.web.server._find_or_create_env") as mock_find:
            fake_env = MagicMock()
            fake_env.exists.return_value = True
            fake_env.read_text.return_value = "AI_BACKEND=deepseek\n"
            fake_env.with_suffix.return_value = fake_env
            mock_find.return_value = fake_env
            with patch("os.replace"):
                handler, sock = _build_handler(
                    "/api/config", method="POST",
                    body=b"",
                )
                parts = sock.get_response_text().split("\r\n\r\n", 1)
                result = json.loads(parts[1])
                self.assertIsNotNone(result)

    def test_save_config_creates_env_if_missing(self):
        """POST /api/config creates .env when none exists."""
        tmp_dir = Path(tempfile.mkdtemp())
        tmp_env = tmp_dir / ".env"
        save_body = json.dumps({
            "ai_backend": "claude",
            "anthropic_api_key": "sk-ant-key",
        }).encode()
        try:
            tmp_env.write_text("", encoding="utf-8")
            with patch("src.web.server._find_or_create_env",
                       return_value=tmp_env):
                handler, sock = _build_handler(
                    "/api/config", method="POST",
                    body=save_body,
                    headers={"Content-Type": "application/json",
                             "Content-Length": str(len(save_body))},
                )
                parts = sock.get_response_text().split("\r\n\r\n", 1)
                result = json.loads(parts[1])
                self.assertTrue(result["ok"])
            saved = tmp_env.read_text(encoding="utf-8")
            self.assertIn("AI_BACKEND=claude", saved)
            self.assertIn("ANTHROPIC_API_KEY=sk-ant-key", saved)
        finally:
            tmp_env.unlink(missing_ok=True)
            for f in tmp_dir.glob("*"):
                f.unlink(missing_ok=True)
            tmp_dir.rmdir()


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class ApiErrorHandlingTests(unittest.TestCase):
    """Tests for error handling across API endpoints."""

    def test_unknown_post_path_returns_405(self):
        """POST to an unknown path returns 405 Method Not Allowed."""
        handler, sock = _build_handler("/api/nonexistent", method="POST")
        response = sock.get_response_text()
        self.assertIn("405", response.splitlines()[0])

    def test_unknown_post_path_has_json_error(self):
        """405 response includes a JSON error body."""
        handler, sock = _build_handler("/api/nonexistent", method="POST")
        parts = sock.get_response_text().split("\r\n\r\n", 1)
        body = json.loads(parts[1])
        self.assertFalse(body["ok"])
        self.assertIn("error", body)

    def test_options_returns_204_with_cors(self):
        """OPTIONS request returns 204 with CORS headers."""
        handler, sock = _build_handler("/api/status", method="OPTIONS")
        response = sock.get_response_text()
        self.assertIn("204", response.splitlines()[0])
        self.assertIn("Access-Control-Allow-Origin: *", response)


# ---------------------------------------------------------------------------
# /api/logs endpoint tests
# ---------------------------------------------------------------------------


class ApiLogsEndpointTests(unittest.TestCase):
    """Tests for GET /api/logs."""

    def test_logs_file_not_found_returns_empty(self):
        """GET /api/logs returns an empty list when log file missing."""
        with patch("src.web.server._read_recent_logs",
                   return_value={"ok": True, "logs": [],
                                 "message": "日志文件尚未创建"}):
            handler, sock = _build_handler("/api/logs")
            parts = sock.get_response_text().split("\r\n\r\n", 1)
            body = json.loads(parts[1])
            self.assertTrue(body["ok"])
            self.assertEqual(body["logs"], [])

    def test_logs_with_entries(self):
        """GET /api/logs returns parsed log entries."""
        mock_logs = {
            "ok": True,
            "logs": [
                {"raw": "2024-06-01 12:00:00 [INFO] bot: Bot started",
                 "ts": "2024-06-01 12:00:00", "level": "INFO",
                 "module": "bot", "msg": "Bot started"},
                {"raw": "2024-06-01 12:01:00 [ERROR] bot: Crash",
                 "ts": "2024-06-01 12:01:00", "level": "ERROR",
                 "module": "bot", "msg": "Crash"},
            ],
        }
        with patch("src.web.server._read_recent_logs",
                   return_value=mock_logs):
            handler, sock = _build_handler("/api/logs")
            parts = sock.get_response_text().split("\r\n\r\n", 1)
            body = json.loads(parts[1])
            self.assertTrue(body["ok"])
            self.assertEqual(len(body["logs"]), 2)
            self.assertEqual(body["logs"][0]["level"], "INFO")
            self.assertEqual(body["logs"][1]["level"], "ERROR")

    def test_logs_error_handling(self):
        """GET /api/logs returns error info on failure."""
        with patch("src.web.server._read_recent_logs",
                   return_value={"ok": False, "logs": [],
                                 "error": "Permission denied"}):
            handler, sock = _build_handler("/api/logs")
            parts = sock.get_response_text().split("\r\n\r\n", 1)
            body = json.loads(parts[1])
            self.assertFalse(body["ok"])
            self.assertEqual(body["error"], "Permission denied")


# ---------------------------------------------------------------------------
# _read_recent_logs helper tests
# ---------------------------------------------------------------------------


class ReadRecentLogsTests(unittest.TestCase):
    """Tests for _read_recent_logs."""

    def test_log_file_not_found_returns_empty(self):
        """Returns empty logs when log file doesn't exist."""
        from src.web.server import _read_recent_logs
        with patch.object(Path, "exists", return_value=False):
            result = _read_recent_logs()
            self.assertTrue(result["ok"])
            self.assertEqual(result["logs"], [])

    def test_parses_standard_log_entries(self):
        """Parses timestamp, level, module, msg from log lines."""
        from src.web.server import _read_recent_logs
        log_content = (
            "2024-06-01 12:00:00 [INFO] bot: Bot started\n"
            "2024-06-01 12:01:00 [ERROR] router: Something went wrong\n"
            "Traceback line without timestamp\n"
        )
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value=log_content),
        ):
            result = _read_recent_logs()
        self.assertTrue(result["ok"])
        entries = result["logs"]
        self.assertGreaterEqual(len(entries), 2)
        self.assertEqual(entries[0]["ts"], "2024-06-01 12:00:00")
        self.assertEqual(entries[0]["level"], "INFO")
        self.assertEqual(entries[0]["module"], "bot")
        self.assertEqual(entries[0]["msg"], "Bot started")
        # Traceback line preserves raw
        raw_texts = [e["raw"] for e in entries]
        self.assertIn("Traceback line without timestamp", raw_texts)


# ---------------------------------------------------------------------------
# _set_env_key helper tests
# ---------------------------------------------------------------------------


class SetEnvKeyTests(unittest.TestCase):
    """Tests for _set_env_key -- .env key management."""

    def test_creates_new_file(self):
        """Creates a .env with the key when file does not exist."""
        from src.web.server import _set_env_key
        tmp_env = Path(tempfile.mkdtemp()) / ".env"
        try:
            _set_env_key(tmp_env, "TEST_KEY", "test_value")
            content = tmp_env.read_text(encoding="utf-8")
            self.assertIn("TEST_KEY=test_value", content)
        finally:
            tmp_env.unlink(missing_ok=True)
            tmp_env.parent.rmdir()

    def test_updates_existing_key(self):
        """Updates an existing key, preserves other keys."""
        from src.web.server import _set_env_key
        tmp_dir = Path(tempfile.mkdtemp())
        tmp_env = tmp_dir / ".env"
        tmp_env.write_text("TEST_KEY=old_value\nOTHER_KEY=keep\n",
                           encoding="utf-8")
        try:
            _set_env_key(tmp_env, "TEST_KEY", "new_value")
            content = tmp_env.read_text(encoding="utf-8")
            self.assertIn("TEST_KEY=new_value", content)
            self.assertNotIn("old_value", content)
            self.assertIn("OTHER_KEY=keep", content)
        finally:
            tmp_env.unlink(missing_ok=True)
            tmp_dir.rmdir()

    def test_adds_new_key_to_existing_file(self):
        """Appends a key that does not already exist."""
        from src.web.server import _set_env_key
        tmp_dir = Path(tempfile.mkdtemp())
        tmp_env = tmp_dir / ".env"
        tmp_env.write_text("EXISTING_KEY=value\n", encoding="utf-8")
        try:
            _set_env_key(tmp_env, "NEW_KEY", "new_value")
            content = tmp_env.read_text(encoding="utf-8")
            self.assertIn("EXISTING_KEY=value", content)
            self.assertIn("NEW_KEY=new_value", content)
        finally:
            tmp_env.unlink(missing_ok=True)
            tmp_dir.rmdir()

    def test_ignores_comment_lines(self):
        """Does not match against commented-out lines."""
        from src.web.server import _set_env_key
        tmp_dir = Path(tempfile.mkdtemp())
        tmp_env = tmp_dir / ".env"
        tmp_env.write_text("# TEST_KEY=commented\nREAL_KEY=real\n",
                           encoding="utf-8")
        try:
            _set_env_key(tmp_env, "TEST_KEY", "uncommented")
            content = tmp_env.read_text(encoding="utf-8")
            self.assertIn("# TEST_KEY=commented", content)
            self.assertIn("TEST_KEY=uncommented", content)
        finally:
            tmp_env.unlink(missing_ok=True)
            tmp_dir.rmdir()


# ---------------------------------------------------------------------------
# Onboarding API tests
# ---------------------------------------------------------------------------


class OnboardingApiTests(unittest.TestCase):
    """Tests for /api/onboarding/* endpoints."""

    def test_onboarding_status_returns_steps(self):
        """GET /api/onboarding/status returns step completion info."""
        with patch("src.config.is_onboarding_done", return_value=False):
            handler, sock = _build_handler("/api/onboarding/status")
            parts = sock.get_response_text().split("\r\n\r\n", 1)
            body = json.loads(parts[1])
            self.assertTrue(body["ok"])
            self.assertFalse(body["onboarding_done"])
            self.assertIn("steps", body)
            self.assertIn("step1", body["steps"])

    def test_onboarding_status_when_done(self):
        """Returns onboarding_done=True when completed."""
        with patch("src.config.is_onboarding_done", return_value=True):
            handler, sock = _build_handler("/api/onboarding/status")
            parts = sock.get_response_text().split("\r\n\r\n", 1)
            body = json.loads(parts[1])
            self.assertTrue(body["onboarding_done"])

    def test_onboarding_reset_returns_ok(self):
        """POST /api/onboarding/reset returns ok=True."""
        with patch("src.web.server._find_or_create_env") as mock_find:
            fake_env = MagicMock()
            fake_env.exists.return_value = True
            fake_env.with_suffix.return_value = fake_env
            mock_find.return_value = fake_env
            with patch("os.replace"):
                handler, sock = _build_handler(
                    "/api/onboarding/reset", method="POST",
                )
                parts = sock.get_response_text().split("\r\n\r\n", 1)
                body = json.loads(parts[1])
                self.assertTrue(body["ok"])

    def test_onboarding_step2_posts_data(self):
        """POST /api/onboarding/step2 accepts WeChat identity data."""
        post_body = json.dumps({
            "bot_display_name": "TestBot",
            "wechat_groups": "*",
            "wechat_backend": "wcdb",
        })
        handler, sock = _build_handler(
            "/api/onboarding/step2", method="POST",
            body=post_body.encode(),
            headers={"Content-Type": "application/json"},
        )
        parts = sock.get_response_text().split("\r\n\r\n", 1)
        result = json.loads(parts[1])
        self.assertTrue(result["ok"])

    def test_onboarding_step3_posts_data(self):
        """POST /api/onboarding/step3 accepts AI backend config."""
        post_body = json.dumps({
            "ai_backend": "deepseek",
            "deepseek_api_key": "sk-test",
            "deepseek_model": "deepseek-v4-flash",
        })
        handler, sock = _build_handler(
            "/api/onboarding/step3", method="POST",
            body=post_body.encode(),
            headers={"Content-Type": "application/json"},
        )
        parts = sock.get_response_text().split("\r\n\r\n", 1)
        result = json.loads(parts[1])
        self.assertTrue(result["ok"])

    def test_onboarding_step4_posts_data(self):
        """POST /api/onboarding/step4 writes to .env and returns ok."""
        with patch("src.web.server._find_or_create_env") as mock_find:
            fake_env = MagicMock()
            fake_env.exists.return_value = True
            fake_env.with_suffix.return_value = fake_env
            mock_find.return_value = fake_env
            with (
                patch("os.replace") as mock_replace,
                patch("src.web.server._write_onboarding_to_env"),
            ):
                post_body = json.dumps({
                    "fun_enabled": True,
                    "proactive_enabled": False,
                    "sticky_mention_enabled": True,
                })
                handler, sock = _build_handler(
                    "/api/onboarding/step4", method="POST",
                    body=post_body.encode(),
                    headers={"Content-Type": "application/json"},
                )
                parts = sock.get_response_text().split("\r\n\r\n", 1)
                result = json.loads(parts[1])
                self.assertTrue(result["ok"])


# ---------------------------------------------------------------------------
# WebSocket helper tests
# ---------------------------------------------------------------------------


class WebSocketHelperTests(unittest.TestCase):
    """Tests for WebSocket frame encoding/decoding helpers."""

    def test_send_ws_frame_small_payload(self):
        """Encodes a short text payload correctly."""
        from src.web.server import _send_ws_frame
        mock_sock = MagicMock()
        _send_ws_frame(mock_sock, "hello")
        mock_sock.sendall.assert_called_once()
        frame = mock_sock.sendall.call_args[0][0]
        self.assertEqual(frame[0], 0x81)  # FIN + text
        self.assertEqual(frame[1], 5)      # length
        self.assertEqual(frame[2:].decode(), "hello")

    def test_send_ws_frame_medium_payload(self):
        """Uses 2-byte extended length for 200-byte payload."""
        from src.web.server import _send_ws_frame
        import struct
        payload = "A" * 200
        mock_sock = MagicMock()
        _send_ws_frame(mock_sock, payload)
        frame = mock_sock.sendall.call_args[0][0]
        self.assertEqual(frame[0], 0x81)
        self.assertEqual(frame[1], 126)  # extended 16-bit
        ext_len = struct.unpack(">H", frame[2:4])[0]
        self.assertEqual(ext_len, 200)

    def test_recv_exactly_fragmented(self):
        """Handles TCP fragmentation by looping."""
        from src.web.server import _recv_exactly
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"hel", b"lo"]
        result = _recv_exactly(mock_sock, 5)
        self.assertEqual(result, b"hello")
        self.assertEqual(mock_sock.recv.call_count, 2)

    def test_recv_exactly_connection_lost(self):
        """Returns None when connection drops."""
        from src.web.server import _recv_exactly
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"ab", b""]
        result = _recv_exactly(mock_sock, 5)
        self.assertIsNone(result)

    def test_read_ws_frame_ping_triggers_pong(self):
        """Responds to ping frames with a pong."""
        from src.web.server import _read_ws_frame
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"\x89\x00"]  # ping frame
        result = _read_ws_frame(mock_sock)
        self.assertEqual(result, b"")
        mock_sock.sendall.assert_called_once()
        pong_frame = mock_sock.sendall.call_args[0][0]
        self.assertEqual(pong_frame[0], 0x8A)  # FIN + pong

    def test_read_ws_frame_close_returns_none(self):
        """Returns None on close frame."""
        from src.web.server import _read_ws_frame
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"\x88\x00"]
        result = _read_ws_frame(mock_sock)
        self.assertIsNone(result)

    def test_read_ws_frame_small_text(self):
        """Unmasks a short text frame."""
        from src.web.server import _read_ws_frame
        payload = b"hello"
        mask = b"\x00\x00\x00\x00"  # zero mask for determinism
        header = b"\x81\x85"  # FIN + text, length 5, mask bit
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [header, mask, payload]
        result = _read_ws_frame(mock_sock)
        self.assertEqual(result, b"hello")


if __name__ == "__main__":
    unittest.main()
