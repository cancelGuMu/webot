"""Tests for macOS adaptation without changing the Windows wcdb path."""

import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path

from src.bot import Bot
from src.config import BotConfig
from src.wechat.mac_ui_backend import MacUIAutomation, MacUIBackend


class FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeRunner:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def __call__(self, cmd, input_text=None, timeout=5):
        self.calls.append({
            "cmd": cmd,
            "input_text": input_text,
            "timeout": timeout,
        })
        if self.responses:
            return self.responses.pop(0)
        return FakeCompletedProcess()


class FakeMacAutomation:
    def __init__(self, snapshots=None):
        self.snapshots = list(snapshots or [])
        self.sent = []
        self.opened = []
        self.activated = 0

    def activate_wechat(self):
        self.activated += 1
        return True

    def open_chat(self, chat_name):
        self.opened.append(chat_name)
        return True

    def read_visible_texts(self):
        if self.snapshots:
            return self.snapshots.pop(0)
        return []

    def send_text(self, content):
        self.sent.append(content)
        return True


class FakeChatlogClient:
    def __init__(self, batches=None):
        self.batches = list(batches or [])
        self.calls = []

    def get_new_messages(self, state=None, limit=200):
        self.calls.append({"state": dict(state or {}), "limit": limit})
        if self.batches:
            return self.batches.pop(0)
        return {"count": 0, "messages": [], "new_state": state or {}}


class MacOSAdaptationTests(unittest.TestCase):
    def test_find_env_file_honors_explicit_env_file_override(self):
        from src.config import find_env_file

        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env.macos"
            env_path.write_text("WECHAT_BACKEND=mac_ui\n", encoding="utf-8")
            with patch.dict("os.environ", {"WEBOT_ENV_FILE": str(env_path)}):
                self.assertEqual(find_env_file(), env_path)

    def test_bot_selects_mac_ui_backend_without_importing_wcdb(self):
        cfg = BotConfig(
            ai_backend="deepseek",
            deepseek_api_key="sk-test",
            wechat_backend="mac_ui",
            wechat_groups="*",
            bot_display_name="群聊小助手",
        )

        backend = Bot(cfg)._create_wechat_backend(store=None)

        self.assertEqual(backend.__class__.__name__, "MacUIBackend")

    def test_bot_selects_mac_hybrid_backend_without_importing_wcdb(self):
        cfg = BotConfig(
            ai_backend="deepseek",
            deepseek_api_key="sk-test",
            wechat_backend="mac_hybrid",
            wechat_groups="*",
            bot_display_name="群聊小助手",
        )

        backend = Bot(cfg)._create_wechat_backend(store=None)

        self.assertEqual(backend.__class__.__name__, "MacHybridBackend")

    def test_requirements_macos_omits_windows_only_packages(self):
        text = Path("requirements-macos.txt").read_text(encoding="utf-8")
        lowered = text.lower()

        self.assertNotIn("pywin32", lowered)
        self.assertNotIn("uiautomation", lowered)
        self.assertNotIn("comtypes", lowered)

    def test_frontend_exposes_mac_ui_backend_label(self):
        config_panel = Path("ui/src/components/ConfigPanel.jsx").read_text(encoding="utf-8")
        dashboard = Path("ui/src/components/Dashboard.jsx").read_text(encoding="utf-8")

        self.assertIn("value: 'mac_ui'", config_panel)
        self.assertIn("value: 'mac_hybrid'", config_panel)
        self.assertIn("mac_ui", dashboard)
        self.assertIn("mac_hybrid", dashboard)
        self.assertIn("macOS", config_panel)

    def test_readme_documents_macos_experimental_start(self):
        text = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("requirements-macos.txt", text)
        self.assertIn("desktop_mac.py", text)
        self.assertIn("WECHAT_BACKEND=mac_ui", text)
        self.assertIn("WECHAT_BACKEND=mac_hybrid", text)
        self.assertIn("all_keys.json", text)
        self.assertIn("tools/macos_chatlog_setup.py extract-keys", text)
        self.assertIn("tools/macos_chatlog_setup.py diagnose", text)
        self.assertIn("tools/macos_chatlog_setup.py build-chatlog", text)
        self.assertIn("tools/macos_chatlog_setup.py start-chatlog", text)
        self.assertIn("tools/macos_chatlog_setup.py verify-read", text)

    def test_platform_dependency_report_for_macos_excludes_windows_deps(self):
        from src.web.server import _platform_dependency_report

        report = _platform_dependency_report(
            system_name="Darwin",
            import_checker=lambda module_name: True,
            command_checker=lambda command_name: True,
        )

        self.assertTrue(report["ok"])
        self.assertNotIn("pywin32", report["value"])
        self.assertNotIn("uiautomation", report["value"])
        self.assertNotIn("comtypes", report["value"])

    def test_desktop_mac_imports_without_windows_modules(self):
        import desktop_mac

        self.assertTrue(hasattr(desktop_mac, "main"))

    def test_mac_ui_poll_once_emits_standardized_messages_once(self):
        automation = FakeMacAutomation([
            ["Alice: 你好", "Bob: @群聊小助手 总结一下"],
            ["Alice: 你好", "Bob: @群聊小助手 总结一下"],
        ])
        backend = MacUIBackend(
            bot_display_name="群聊小助手",
            groups=["摸鱼群"],
            poll_sec=0.01,
            automation=automation,
        )
        seen = []

        backend.poll_once(lambda msg: seen.append(msg))
        backend.poll_once(lambda msg: seen.append(msg))

        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0]["group_name"], "摸鱼群")
        self.assertEqual(seen[0]["sender_name"], "Alice")
        self.assertEqual(seen[0]["content"], "你好")
        self.assertFalse(seen[0]["is_at_mentioned"])
        self.assertEqual(seen[1]["sender_name"], "Bob")
        self.assertEqual(seen[1]["content"], "@群聊小助手 总结一下")
        self.assertTrue(seen[1]["is_at_mentioned"])

    def test_mac_ui_poll_once_sends_callback_reply(self):
        automation = FakeMacAutomation([["Alice: ping"]])
        backend = MacUIBackend(
            bot_display_name="群聊小助手",
            groups=["摸鱼群"],
            poll_sec=0.01,
            automation=automation,
        )

        backend.poll_once(lambda msg: "pong")

        self.assertEqual(automation.sent, ["pong"])

    def test_mac_ui_automation_send_text_uses_clipboard_and_osascript(self):
        runner = FakeRunner()
        automation = MacUIAutomation(app_name="WeChat", runner=runner)

        self.assertTrue(automation.send_text("hello"))

        self.assertEqual(runner.calls[0]["cmd"], ["pbcopy"])
        self.assertEqual(runner.calls[0]["input_text"], "hello")
        self.assertIn("osascript", runner.calls[1]["cmd"][0])
        self.assertIn("keystroke \"v\"", runner.calls[1]["cmd"][-1])
        self.assertIn("key code 36", runner.calls[1]["cmd"][-1])

    def test_mac_ui_automation_read_visible_texts_parses_json(self):
        runner = FakeRunner([
            FakeCompletedProcess(stdout='["Alice: hi", "", "Bob: ok"]')
        ])
        automation = MacUIAutomation(app_name="WeChat", runner=runner)

        self.assertEqual(
            automation.read_visible_texts(),
            ["Alice: hi", "Bob: ok"],
        )

    def test_mac_hybrid_poll_once_reads_chatlog_messages_and_sends_reply(self):
        from src.wechat.mac_hybrid_backend import MacHybridBackend

        client = FakeChatlogClient([
            {
                "count": 1,
                "new_state": {"room1@chatroom": 1780727000},
                "messages": [
                    {
                        "timestamp": 1780726999,
                        "time": "06-06 14:30",
                        "sender": "Alice",
                        "type": "text",
                        "content": "@群聊小助手 总结一下",
                        "local_id": 42,
                        "chat": "摸鱼群",
                        "username": "room1@chatroom",
                        "is_group": True,
                        "chat_type": "group",
                    }
                ],
            },
            {
                "count": 1,
                "new_state": {"room1@chatroom": 1780727000},
                "messages": [
                    {
                        "timestamp": 1780726999,
                        "sender": "Alice",
                        "type": "text",
                        "content": "@群聊小助手 总结一下",
                        "local_id": 42,
                        "chat": "摸鱼群",
                        "username": "room1@chatroom",
                        "is_group": True,
                    }
                ],
            },
        ])
        automation = FakeMacAutomation()
        backend = MacHybridBackend(
            bot_display_name="群聊小助手",
            groups=["摸鱼群"],
            poll_sec=0.01,
            client=client,
            automation=automation,
        )
        seen = []

        backend.poll_once(lambda msg: seen.append(msg) or "收到")
        backend.poll_once(lambda msg: seen.append(msg) or "不应发送")

        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["message_id"], "mac-chatlog-room1@chatroom-42")
        self.assertEqual(seen[0]["chat_id"], "room1@chatroom")
        self.assertEqual(seen[0]["group_name"], "摸鱼群")
        self.assertEqual(seen[0]["sender_name"], "Alice")
        self.assertEqual(seen[0]["content"], "@群聊小助手 总结一下")
        self.assertTrue(seen[0]["is_at_mentioned"])
        self.assertEqual(automation.opened, ["摸鱼群"])
        self.assertEqual(automation.sent, ["收到"])


if __name__ == "__main__":
    unittest.main()
