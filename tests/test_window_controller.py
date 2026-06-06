import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only HWND controller tests", allow_module_level=True)

from src.wechat.window_controller import WeChatWindowController, WindowCandidate


class WeChatWindowControllerTests(unittest.TestCase):
    def test_navigate_to_chat_uses_keyboard_only(self):
        """Navigation should use only keyboard (Ctrl+F, paste, Enter, Tab),
        no mouse clicks."""
        controller = WeChatWindowController()

        with (
            patch.object(controller, "_validate_hwnd", return_value=True),
            patch.object(controller, "_foreground_matches", return_value=True),
            patch("src.wechat.window_controller.press_key") as press_key,
            patch("src.wechat.window_controller.send_combo") as send_combo,
            patch.object(controller, "_set_clipboard"),
            patch.object(controller, "_verify_chat_title", return_value=False),
            patch.object(controller, "_current_wechat_foreground_hwnd", return_value=None),
            patch.object(
                controller,
                "get_foreground_info",
                return_value="FG_HWND=12345 title='微信' class='Qt51514QWindowIcon' proc=wechat.exe",
            ),
        ):
            self.assertTrue(controller.navigate_to_chat(12345, "target group"))

            # Verify keyboard keys were pressed (not mouse clicks)
            pressed_keys = [
                call[0][0] for call in press_key.call_args_list
            ]
            # Only Enter (no Esc, no Tab)
            self.assertIn(0x0D, pressed_keys)  # Enter
            self.assertNotIn(0x1B, pressed_keys)  # Esc must NOT be pressed
            self.assertNotIn(0x09, pressed_keys)  # Tab must NOT be pressed

            # Verify Ctrl+F and Ctrl+V combos
            combo_keys = [
                (call[0][0], call[0][1]) for call in send_combo.call_args_list
            ]
            self.assertIn((0x11, 0x46), combo_keys)  # Ctrl+F
            self.assertIn((0x11, 0x56), combo_keys)  # Ctrl+V

    def test_navigate_to_chat_fails_when_wechat_is_not_foreground(self):
        controller = WeChatWindowController()

        with (
            patch.object(controller, "_validate_hwnd", return_value=True),
            patch.object(controller, "_foreground_matches", return_value=False),
            patch("src.wechat.window_controller.press_key"),
            patch("src.wechat.window_controller.send_combo"),
            patch.object(controller, "_set_clipboard"),
            patch.object(controller, "_verify_chat_title", return_value=False),
            patch.object(
                controller,
                "get_foreground_info",
                return_value="FG_HWND=1 title='Explorer' class='CabinetWClass' proc=explorer.exe",
            ),
        ):
            self.assertFalse(controller.navigate_to_chat(12345, "target group"))

    def test_send_message_fails_when_wechat_is_not_foreground(self):
        controller = WeChatWindowController()

        with (
            patch.object(controller, "_validate_hwnd", return_value=True),
            patch.object(controller, "_foreground_matches", return_value=False),
            patch.object(controller, "_set_clipboard") as set_clipboard,
            patch("src.wechat.window_controller.send_combo") as send_combo,
            patch("src.wechat.window_controller.press_key") as press_key,
        ):
            self.assertFalse(controller.send_message(12345, "hello"))
            set_clipboard.assert_not_called()
            send_combo.assert_not_called()
            press_key.assert_not_called()

    def test_send_message_uses_keyboard_only(self):
        """Send should use Ctrl+V paste + Enter, no mouse clicks."""
        controller = WeChatWindowController()

        with (
            patch.object(controller, "_validate_hwnd", return_value=True),
            patch.object(controller, "_foreground_matches", return_value=True),
            patch.object(controller, "_set_clipboard"),
            patch("src.wechat.window_controller.send_combo") as send_combo,
            patch("src.wechat.window_controller.press_key") as press_key,
            patch.object(controller, "_current_wechat_foreground_hwnd", return_value=None),
        ):
            self.assertTrue(controller.send_message(12345, "hello"))

            # Should use Ctrl+V for paste
            send_combo.assert_called_once_with(0x11, 0x56)

            # Should use Enter to send (not click send button)
            enter_calls = [
                c for c in press_key.call_args_list if c[0][0] == 0x0D
            ]
            self.assertTrue(len(enter_calls) > 0, "Enter key should be pressed to send")

    def test_find_hwnd_rejects_small_wechat_login_prompt(self):
        controller = WeChatWindowController()
        small_prompt = WindowCandidate(
            hwnd=200,
            title="微信",
            class_name="Qt51514QWindowIcon",
            pid=1,
            process_name="weixin.exe",
            rect=(0, 0, 180, 150),   # below 200×200 minimum
            visible=True,
            iconic=False,
            score=150,
            reason="wechat_process+qt_class+visible+too_small(180x150)",
        )

        def enum_windows(callback, ctx):
            callback(200, ctx)

        with (
            patch("src.wechat.window_controller.win32gui.EnumWindows", side_effect=enum_windows),
            patch("src.wechat.window_controller._score_window", return_value=small_prompt),
        ):
            self.assertIsNone(controller.find_hwnd(force=True))

    def test_send_to_chat_adopts_new_wechat_foreground_hwnd_after_navigation(self):
        controller = WeChatWindowController()
        states = {"hwnd": 100}

        def navigate(hwnd, _group_name):
            states["hwnd"] = 200
            return 200

        def send_message(hwnd, _text):
            self.assertEqual(hwnd, 200)
            return True

        with (
            patch.object(controller, "find_hwnd", return_value=100),
            patch.object(controller, "activate", return_value=True),
            patch.object(controller, "navigate_to_chat", side_effect=navigate),
            patch.object(controller, "send_message", side_effect=send_message),
            patch.object(controller, "_current_wechat_foreground_hwnd", side_effect=lambda: states["hwnd"]),
            patch.object(controller, "_log_failure"),
        ):
            self.assertTrue(controller.send_to_chat("target group", "hello", max_retries=1))

    def test_send_to_chat_refuses_blank_wechat_window(self):
        controller = WeChatWindowController()

        with (
            patch.object(controller, "find_hwnd", return_value=100),
            patch.object(controller, "activate", return_value=True),
            patch.object(controller, "_looks_like_blank_window", return_value=True),
            patch.object(controller, "navigate_to_chat") as navigate,
            patch.object(controller, "send_message") as send_message,
            patch.object(controller, "_log_failure") as log_failure,
        ):
            self.assertFalse(controller.send_to_chat("target group", "hello", max_retries=1))
            navigate.assert_not_called()
            send_message.assert_not_called()
            log_failure.assert_called_with(
                "target group", "hello", "WeChat window is blank/white", 100
            )



if __name__ == "__main__":
    unittest.main()
