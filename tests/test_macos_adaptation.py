"""Tests for macOS adaptation without changing the Windows wcdb path."""

import subprocess
import unittest
import tempfile
import plistlib
import os
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
        self.open_options = []
        self.activated = 0

    def activate_wechat(self):
        self.activated += 1
        return True

    def open_chat(
        self,
        chat_name,
        prefer_group=False,
        sidebar_index=None,
        expected_title=None,
        expected_is_group=False,
        require_group_marker=False,
    ):
        self.opened.append(chat_name)
        self.open_options.append({
            "chat_name": chat_name,
            "prefer_group": prefer_group,
            "sidebar_index": sidebar_index,
            "expected_title": expected_title,
            "expected_is_group": expected_is_group,
            "require_group_marker": require_group_marker,
        })
        return True

    def read_visible_texts(self):
        if self.snapshots:
            return self.snapshots.pop(0)
        return []

    def send_text(self, content):
        self.sent.append(content)
        return True


class FakeMacDiagnosticAutomation:
    def __init__(self, report=None):
        self.calls = 0
        self.report = report or {"ok": True, "accessibility_ok": True}

    def diagnose_access(self):
        self.calls += 1
        return self.report


class FakeChatlogClient:
    def __init__(self, batches=None, sessions=None):
        self.batches = list(batches or [])
        self.sessions = sessions or {"sessions": []}
        self.calls = []

    def get_new_messages(self, state=None, limit=200):
        self.calls.append({"state": dict(state or {}), "limit": limit})
        if self.batches:
            return self.batches.pop(0)
        return {"count": 0, "messages": [], "new_state": state or {}}

    def get_sessions(self, limit=500):
        return self.sessions

    def health(self):
        return True


class FakeHealthClient:
    def __init__(self, health_results):
        self.health_results = list(health_results)
        self.health_calls = 0

    def health(self):
        self.health_calls += 1
        if self.health_results:
            return self.health_results.pop(0)
        return False


class FakeChatlogProcess:
    pid = 4321

    def poll(self):
        return None


class FakeChatlogServiceManager:
    def __init__(self):
        self.calls = 0

    def ensure_running(self):
        self.calls += 1
        return False


class FakeClicker:
    def __init__(self):
        self.points = []

    def __call__(self, x, y):
        self.points.append((x, y))
        return True


class FakeWebview:
    def __init__(self):
        self.created = []
        self.started = []

    def create_window(self, **kwargs):
        self.created.append(kwargs)
        return object()

    def start(self, **kwargs):
        self.started.append(kwargs)


class MacOSAdaptationTests(unittest.TestCase):
    def test_mac_ui_default_runner_converts_timeout_to_failed_process(self):
        with patch(
            "src.wechat.mac_ui_backend.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["osascript"], 3),
        ):
            result = MacUIAutomation._default_runner(["osascript"], timeout=3)

        self.assertEqual(result.returncode, 124)
        self.assertIn("timed out", result.stderr)

    def test_mac_ui_falls_back_to_external_osascript_when_in_process_access_denied(self):
        runner = FakeRunner([
            FakeCompletedProcess(
                stdout="window|210|201|880|640|closed|0"
            )
        ])
        automation = MacUIAutomation(runner=runner)

        with patch.object(
            MacUIAutomation,
            "_run_applescript_in_process",
            return_value={
                "ok": False,
                "stdout": "",
                "stderr": "“Python”不允许辅助访问。",
            },
        ):
            geometry = automation._get_wechat_geometry_applescript()

        self.assertEqual(geometry["window"]["w"], 880)
        self.assertEqual(runner.calls[0]["cmd"][:2], ["osascript", "-e"])

    def test_mac_ui_reads_title_texts_from_accessibility_when_screen_capture_fails(self):
        runner = FakeRunner([
            FakeCompletedProcess(
                stdout='{"window":{"x":210,"y":201,"w":880,"h":640},"closed_aux_windows":0}'
            ),
            FakeCompletedProcess(returncode=1, stderr="could not create image from rect"),
            FakeCompletedProcess(stdout='["ai群聊测试", "honker", "文件传输助手"]'),
        ])
        automation = MacUIAutomation(runner=runner)

        texts = automation._read_current_header_texts()

        self.assertIn("ai群聊测试", texts)
        self.assertEqual(runner.calls[1]["cmd"][0], "screencapture")
        self.assertEqual(runner.calls[2]["cmd"][:3], ["osascript", "-l", "JavaScript"])

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

    def test_macos_entitlements_allow_bundled_python_framework(self):
        with Path("macos-entitlements.plist").open("rb") as f:
            entitlements = plistlib.load(f)

        self.assertTrue(entitlements["com.apple.security.automation.apple-events"])
        self.assertTrue(entitlements["com.apple.security.cs.disable-library-validation"])

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
        self.assertIn("tools/macos_chatlog_setup.py import-keys", text)
        self.assertIn("tools/macos_chatlog_setup.py diagnose", text)
        self.assertIn("tools/macos_chatlog_setup.py extract-keys-restart-hook", text)
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

    def test_macos_wechat_diagnostics_skips_non_macos(self):
        from src.web.server import _macos_wechat_diagnostics

        automation = FakeMacDiagnosticAutomation()

        report = _macos_wechat_diagnostics(
            system_name="Windows",
            automation=automation,
        )

        self.assertFalse(report["ok"])
        self.assertTrue(report["skipped"])
        self.assertEqual(automation.calls, 0)

    def test_macos_wechat_diagnostics_uses_injected_automation(self):
        from src.web.server import _macos_wechat_diagnostics

        automation = FakeMacDiagnosticAutomation({
            "ok": True,
            "activated": True,
            "accessibility_ok": True,
            "screen_capture_ok": True,
        })

        report = _macos_wechat_diagnostics(
            system_name="Darwin",
            automation=automation,
        )

        self.assertTrue(report["ok"])
        self.assertEqual(automation.calls, 1)

    def test_desktop_mac_imports_without_windows_modules(self):
        import desktop_mac

        self.assertTrue(hasattr(desktop_mac, "main"))

    def test_desktop_mac_uses_application_support_when_frozen(self):
        import desktop_mac

        with (
            patch.object(desktop_mac.sys, "frozen", True, create=True),
            patch.object(desktop_mac.Path, "home", return_value=Path("/Users/tester")),
            patch.dict("os.environ", {}, clear=True),
        ):
            self.assertEqual(
                desktop_mac._resolve_app_home(),
                Path("/Users/tester/Library/Application Support/webot"),
            )

    def test_desktop_mac_env_file_creates_application_support_dir(self):
        import desktop_mac

        with tempfile.TemporaryDirectory() as tmp:
            app_home = Path(tmp) / "Library" / "Application Support" / "webot"
            env_path = app_home / ".env.macos"
            with (
                patch.object(desktop_mac, "APP_HOME", app_home),
                patch.object(desktop_mac, "MAC_ENV_PATH", env_path),
                patch.dict("os.environ", {}, clear=True),
            ):
                written = desktop_mac.ensure_macos_env_file()
                self.assertEqual(os.environ["WEBOT_APP_HOME"], str(app_home))
                self.assertEqual(os.environ["WEBOT_ENV_FILE"], str(env_path))

            self.assertEqual(written, env_path)
            self.assertTrue(env_path.exists())

    def test_desktop_mac_opens_native_webview_window(self):
        import desktop_mac

        webview = FakeWebview()

        desktop_mac.open_dashboard(
            "http://127.0.0.1:7327",
            webview_module=webview,
            browser_opener=lambda url: self.fail(f"unexpected browser fallback: {url}"),
            sleep_func=lambda seconds: None,
        )

        self.assertEqual(webview.created[0]["title"], "webot — Dashboard")
        self.assertEqual(webview.created[0]["url"], "http://127.0.0.1:7327")
        self.assertEqual(webview.created[0]["min_size"], (900, 600))
        self.assertEqual(webview.started[0]["gui"], "cocoa")

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

    def test_mac_ui_automation_send_text_uses_core_graphics_click_before_paste(self):
        runner = FakeRunner([
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout='{"front":"WeChat"}'),
            FakeCompletedProcess(stdout='{"window":{"x":100,"y":200,"w":800,"h":600}}'),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
        ])
        clicker = FakeClicker()
        automation = MacUIAutomation(app_name="WeChat", runner=runner, clicker=clicker)

        self.assertTrue(automation.send_text("hello"))

        self.assertEqual(runner.calls[0]["cmd"], ["open", "-a", "WeChat"])
        self.assertIn("frontmost", runner.calls[1]["cmd"][-1])
        self.assertEqual(clicker.points, [(644, 756)])
        self.assertIn("osascript", runner.calls[3]["cmd"][0])
        self.assertIn('keystroke "a" using command down', runner.calls[3]["cmd"][-1])
        self.assertEqual(runner.calls[4]["cmd"], ["pbcopy"])
        self.assertEqual(runner.calls[4]["input_text"], "hello")
        self.assertIn("osascript", runner.calls[5]["cmd"][0])
        self.assertIn('tell process "WeChat"', runner.calls[5]["cmd"][-1])
        self.assertNotIn("click at", runner.calls[5]["cmd"][-1])
        self.assertIn("keystroke \"v\"", runner.calls[5]["cmd"][-1])
        self.assertIn("key code 36", runner.calls[5]["cmd"][-1])
        self.assertNotIn("key code 36 using command down", runner.calls[5]["cmd"][-1])

    def test_mac_ui_automation_send_text_can_use_cmd_enter_when_configured(self):
        runner = FakeRunner([
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout='{"front":"WeChat"}'),
            FakeCompletedProcess(stdout='{"window":{"x":100,"y":200,"w":800,"h":600}}'),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
        ])
        automation = MacUIAutomation(app_name="WeChat", runner=runner, clicker=FakeClicker())

        with patch.dict("os.environ", {"MAC_WECHAT_SEND_SHORTCUT": "cmd_enter"}):
            self.assertTrue(automation.send_text("hello"))

        self.assertIn("key code 36 using command down", runner.calls[5]["cmd"][-1])

    def test_mac_ui_automation_open_chat_uses_existing_chat_search_not_start_chat_sheet(self):
        runner = FakeRunner([
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout='{"front":"WeChat"}'),
            FakeCompletedProcess(stdout='{"window":{"x":100,"y":200,"w":800,"h":600}}'),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
        ])
        clicker = FakeClicker()
        titles = iter([["别的群（2）"], ["honker（2）"]])
        automation = MacUIAutomation(
            app_name="WeChat",
            runner=runner,
            clicker=clicker,
            title_reader=lambda: next(titles, []),
            screen_text_reader=lambda rect: [],
        )

        self.assertTrue(automation.open_chat(
            "honker",
            expected_title="honker",
            expected_is_group=True,
        ))

        self.assertEqual(runner.calls[0]["cmd"], ["open", "-a", "WeChat"])
        self.assertIn("key code 19 using command down", runner.calls[3]["cmd"][-1])
        self.assertEqual(runner.calls[4]["cmd"], ["pbcopy"])
        self.assertEqual(runner.calls[4]["input_text"], "honker")
        scripts = "\n".join(call["cmd"][-1] for call in runner.calls if call["cmd"][0] == "osascript")
        self.assertNotIn("click at", scripts)
        self.assertNotIn('keystroke "f"', scripts)
        self.assertNotIn("发起会话", scripts)
        self.assertNotIn("发起群聊", scripts)
        self.assertIn('keystroke "v"', scripts)
        self.assertEqual(clicker.points, [(260, 228), (340, 228), (260, 308)])

    def test_mac_ui_automation_open_chat_switches_to_chats_tab_before_search(self):
        runner = FakeRunner([
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout='{"front":"WeChat"}'),
            FakeCompletedProcess(stdout='{"window":{"x":100,"y":200,"w":800,"h":600}}'),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
        ])
        automation = MacUIAutomation(
            app_name="WeChat",
            runner=runner,
            clicker=FakeClicker(),
            screen_text_reader=lambda rect: [],
        )

        self.assertTrue(automation.open_chat("honker"))

        tab_switch_indexes = [
            index for index, call in enumerate(runner.calls)
            if call["cmd"][0] == "osascript"
            and "key code 19 using command down" in call["cmd"][-1]
        ]
        pbcopy_index = next(
            index for index, call in enumerate(runner.calls)
            if call["cmd"] == ["pbcopy"]
        )
        self.assertEqual(tab_switch_indexes, [3])
        self.assertLess(tab_switch_indexes[0], pbcopy_index)

    def test_mac_ui_automation_open_chat_returns_when_current_title_already_matches(self):
        runner = FakeRunner([
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout='{"front":"WeChat"}'),
        ])
        clicker = FakeClicker()
        automation = MacUIAutomation(
            app_name="WeChat",
            runner=runner,
            clicker=clicker,
            title_reader=lambda: ["ai群聊测试（2）"],
        )

        self.assertTrue(automation.open_chat(
            "ai群聊测试",
            expected_title="ai群聊测试",
            expected_is_group=True,
        ))

        self.assertFalse(any(call["cmd"] == ["pbcopy"] for call in runner.calls))
        scripts = "\n".join(call["cmd"][-1] for call in runner.calls if call["cmd"][0] == "osascript")
        self.assertNotIn("发起会话", scripts)
        self.assertNotIn("发起群聊", scripts)
        self.assertEqual(clicker.points, [])

    def test_mac_ui_automation_open_chat_rejects_internal_chat_ids(self):
        runner = FakeRunner()
        clicker = FakeClicker()
        automation = MacUIAutomation(app_name="WeChat", runner=runner, clicker=clicker)

        self.assertFalse(automation.open_chat("52859259744@chatroom"))
        self.assertFalse(automation.open_chat("wxid_jfs04ffdka4u21"))

        self.assertEqual(runner.calls, [])
        self.assertEqual(clicker.points, [])

    def test_mac_ui_automation_open_chat_can_prefer_second_group_result(self):
        runner = FakeRunner([
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout='{"front":"WeChat"}'),
            FakeCompletedProcess(stdout='{"window":{"x":100,"y":200,"w":800,"h":600}}'),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
        ])
        clicker = FakeClicker()
        automation = MacUIAutomation(app_name="WeChat", runner=runner, clicker=clicker)

        automation._screen_text_reader = lambda rect: []

        self.assertTrue(automation.open_chat("honker", prefer_group=True))

        self.assertEqual(clicker.points, [(260, 228), (340, 228), (260, 510)])

    def test_mac_ui_search_result_picker_prefers_group_section(self):
        entries = [
            {"text": "搜索网络结果", "x": 200, "y": 300, "w": 160, "h": 24},
            {"text": "honker233粉丝微信纯享版", "x": 220, "y": 370, "w": 260, "h": 28},
            {"text": "群聊", "x": 180, "y": 430, "w": 80, "h": 24},
            {"text": "honker233粉丝微信纯享版", "x": 250, "y": 520, "w": 280, "h": 34},
        ]

        point = MacUIAutomation._search_result_click_point(
            entries,
            "honker233粉丝微信纯享版",
            expected_is_group=True,
        )

        self.assertEqual(point, {"x": 390.0, "y": 537.0})

    def test_mac_ui_search_result_picker_treats_souyisou_as_network_section(self):
        entries = [
            {"text": "搜一搜", "x": 200, "y": 300, "w": 100, "h": 24},
            {"text": "honker233粉丝微信纯享版", "x": 220, "y": 370, "w": 260, "h": 28},
            {"text": "群聊", "x": 180, "y": 430, "w": 80, "h": 24},
            {"text": "honker233粉丝微信纯享版", "x": 250, "y": 520, "w": 280, "h": 34},
        ]

        point = MacUIAutomation._search_result_click_point(
            entries,
            "honker233粉丝微信纯享版",
            expected_is_group=True,
        )

        self.assertEqual(point, {"x": 390.0, "y": 537.0})

    def test_mac_ui_search_result_picker_refuses_network_only_result(self):
        entries = [
            {"text": "搜索网络结果", "x": 200, "y": 300, "w": 160, "h": 24},
            {"text": "honker233粉丝微信纯享版", "x": 220, "y": 370, "w": 260, "h": 28},
        ]

        point = MacUIAutomation._search_result_click_point(
            entries,
            "honker233粉丝微信纯享版",
            expected_is_group=True,
        )

        self.assertIsNone(point)

    def test_mac_ui_search_result_picker_refuses_souyisou_only_result(self):
        entries = [
            {"text": "搜一搜", "x": 200, "y": 300, "w": 100, "h": 24},
            {"text": "honker233粉丝微信纯享版", "x": 220, "y": 370, "w": 260, "h": 28},
        ]

        point = MacUIAutomation._search_result_click_point(
            entries,
            "honker233粉丝微信纯享版",
            expected_is_group=True,
        )

        self.assertIsNone(point)

    def test_mac_ui_automation_open_chat_retries_group_result_after_top_mismatch(self):
        runner = FakeRunner([
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout='{"front":"WeChat"}'),
            FakeCompletedProcess(stdout='{"window":{"x":100,"y":200,"w":800,"h":600}}'),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout='{"window":{"x":100,"y":200,"w":800,"h":600}}'),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
        ])
        clicker = FakeClicker()
        titles = iter([["别的群（2）"], ["错的会话"], ["honker（2）"]])
        automation = MacUIAutomation(
            app_name="WeChat",
            runner=runner,
            clicker=clicker,
            title_reader=lambda: next(titles, []),
            screen_text_reader=lambda rect: [],
        )

        self.assertTrue(automation.open_chat(
            "honker",
            expected_title="honker",
            expected_is_group=True,
        ))

        self.assertEqual(clicker.points, [
            (260, 228), (340, 228), (260, 308),
            (260, 228), (340, 228), (260, 510),
        ])

    def test_mac_ui_automation_open_chat_can_click_sidebar_session_index(self):
        runner = FakeRunner([
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout='{"front":"WeChat"}'),
            FakeCompletedProcess(stdout='{"window":{"x":100,"y":200,"w":800,"h":600}}'),
        ])
        clicker = FakeClicker()
        automation = MacUIAutomation(app_name="WeChat", runner=runner, clicker=clicker)

        self.assertTrue(automation.open_chat("honker", sidebar_index=1))

        self.assertEqual(clicker.points, [(327, 378)])
        self.assertFalse(any(call["cmd"] == ["pbcopy"] for call in runner.calls))

    def test_mac_ui_automation_open_chat_rejects_mismatched_ocr_title(self):
        runner = FakeRunner([
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout='{"front":"WeChat"}'),
            FakeCompletedProcess(stdout='{"window":{"x":100,"y":200,"w":800,"h":600}}'),
        ])
        clicker = FakeClicker()
        automation = MacUIAutomation(
            app_name="WeChat",
            runner=runner,
            clicker=clicker,
            title_reader=lambda: ["honker233粉丝微信纯享版（31）"],
        )

        self.assertFalse(automation.open_chat(
            "honker",
            sidebar_index=0,
            expected_title="honker",
            expected_is_group=True,
            require_group_marker=True,
        ))

        self.assertEqual(clicker.points, [(327, 310)])

    def test_mac_ui_automation_open_chat_accepts_group_title_marker(self):
        runner = FakeRunner([
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout='{"front":"WeChat"}'),
            FakeCompletedProcess(stdout='{"window":{"x":100,"y":200,"w":800,"h":600}}'),
        ])
        automation = MacUIAutomation(
            app_name="WeChat",
            runner=runner,
            clicker=FakeClicker(),
            title_reader=lambda: ["honker (2)"],
        )

        self.assertTrue(automation.open_chat(
            "honker",
            sidebar_index=1,
            expected_title="honker",
            expected_is_group=True,
            require_group_marker=True,
        ))

    def test_mac_ui_automation_title_ocr_crops_right_chat_header_only(self):
        runner = FakeRunner([
            FakeCompletedProcess(stdout='{"window":{"x":100,"y":200,"w":1000,"h":600}}'),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout='["目标群（2）"]'),
        ])
        automation = MacUIAutomation(app_name="WeChat", runner=runner)

        self.assertEqual(automation._read_current_header_texts(), ["目标群（2）"])

        capture_cmd = runner.calls[1]["cmd"]
        self.assertEqual(capture_cmd[0], "screencapture")
        self.assertEqual(capture_cmd[2], "-R440,200,660,140")

    def test_mac_ui_automation_read_visible_texts_parses_json(self):
        runner = FakeRunner([
            FakeCompletedProcess(stdout='["Alice: hi", "", "Bob: ok"]')
        ])
        automation = MacUIAutomation(app_name="WeChat", runner=runner)

        self.assertEqual(
            automation.read_visible_texts(),
            ["Alice: hi", "Bob: ok"],
        )

    def test_mac_ui_automation_parses_native_applescript_geometry(self):
        parsed = MacUIAutomation._parse_wechat_geometry_applescript(
            "window|100|200|800|600|closed|1|sheet|120|230|300|180"
        )

        self.assertEqual(parsed["window"], {"x": 100.0, "y": 200.0, "w": 800.0, "h": 600.0})
        self.assertEqual(parsed["closed_aux_windows"], 1)
        self.assertEqual(parsed["sheet"], {"x": 120.0, "y": 230.0, "w": 300.0, "h": 180.0})

    def test_mac_ui_automation_parses_native_applescript_geometry_without_sheet(self):
        parsed = MacUIAutomation._parse_wechat_geometry_applescript(
            "window|100|200|800|600|closed|0"
        )

        self.assertEqual(parsed["window"], {"x": 100.0, "y": 200.0, "w": 800.0, "h": 600.0})
        self.assertEqual(parsed["closed_aux_windows"], 0)
        self.assertNotIn("sheet", parsed)

    def test_mac_ui_automation_parses_native_applescript_error(self):
        parsed = MacUIAutomation._parse_wechat_geometry_applescript(
            "error|osascript is not allowed assistive access"
        )

        self.assertEqual(parsed, {"error": "osascript is not allowed assistive access"})

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

    def test_mac_hybrid_resolves_internal_chatroom_id_before_send(self):
        from src.wechat.mac_hybrid_backend import MacHybridBackend

        client = FakeChatlogClient(
            batches=[{
                "count": 1,
                "new_state": {"52859259744@chatroom": 1780740773},
                "messages": [{
                    "timestamp": 1780740773,
                    "sender": "honker",
                    "type": "text",
                    "content": "@群聊小助手 你好",
                    "local_id": 10,
                    "chat": "52859259744@chatroom",
                    "username": "52859259744@chatroom",
                    "is_group": True,
                }],
            }],
            sessions={
                "sessions": [{
                    "username": "52859259744@chatroom",
                    "chat": "honker",
                    "is_group": True,
                }],
            },
        )
        automation = FakeMacAutomation()
        with patch.dict("os.environ", {"MAC_CHAT_TITLE_MAP": ""}):
            backend = MacHybridBackend(
                bot_display_name="群聊小助手",
                groups=["*"],
                client=client,
                automation=automation,
            )

        backend.poll_once(lambda msg: "收到")

        self.assertEqual(automation.opened, ["honker"])
        self.assertEqual(automation.sent, ["收到"])

    def test_mac_hybrid_refuses_to_search_internal_chatroom_id_without_resolved_title(self):
        from src.wechat.mac_hybrid_backend import MacHybridBackend

        client = FakeChatlogClient(
            batches=[{
                "count": 1,
                "new_state": {"52859259744@chatroom": 1780740773},
                "messages": [{
                    "timestamp": 1780740773,
                    "sender": "honker",
                    "type": "text",
                    "content": "@群聊小助手 你好",
                    "local_id": 10,
                    "chat": "52859259744@chatroom",
                    "username": "52859259744@chatroom",
                    "is_group": True,
                }],
            }],
            sessions={"sessions": []},
        )
        automation = FakeMacAutomation()
        with patch.dict("os.environ", {"MAC_CHAT_TITLE_MAP": ""}):
            backend = MacHybridBackend(
                bot_display_name="群聊小助手",
                groups=["*"],
                client=client,
                automation=automation,
            )

        backend.poll_once(lambda msg: "收到")

        self.assertEqual(automation.opened, [])
        self.assertEqual(automation.sent, [])

    def test_mac_hybrid_manual_chat_title_map_overrides_unreliable_session_title(self):
        from src.wechat.mac_hybrid_backend import MacHybridBackend

        client = FakeChatlogClient(
            batches=[{
                "count": 1,
                "new_state": {"52859259744@chatroom": 1780747572},
                "messages": [{
                    "timestamp": 1780747572,
                    "sender": "honker",
                    "type": "text",
                    "content": "@群聊小助手 还在吗",
                    "local_id": 12,
                    "chat": "52859259744@chatroom",
                    "username": "52859259744@chatroom",
                    "is_group": True,
                }],
            }],
            sessions={
                "sessions": [{
                    "username": "52859259744@chatroom",
                    "chat": "honker",
                    "is_group": True,
                }],
            },
        )
        automation = FakeMacAutomation()
        with patch.dict(
            "os.environ",
            {"MAC_CHAT_TITLE_MAP": '{"52859259744@chatroom":"ai群聊测试"}'},
        ):
            backend = MacHybridBackend(
                bot_display_name="群聊小助手",
                groups=["*"],
                client=client,
                automation=automation,
            )

        backend.poll_once(lambda msg: "收到")

        self.assertEqual(automation.open_options, [{
            "chat_name": "ai群聊测试",
            "prefer_group": False,
            "sidebar_index": None,
            "expected_title": "ai群聊测试",
            "expected_is_group": True,
            "require_group_marker": False,
        }])
        self.assertEqual(automation.sent, ["收到"])

    def test_mac_hybrid_prefers_group_result_when_title_collides_with_private_chat(self):
        from src.wechat.mac_hybrid_backend import MacHybridBackend

        client = FakeChatlogClient(
            batches=[{
                "count": 1,
                "new_state": {"52859259744@chatroom": 1780743227},
                "messages": [{
                    "timestamp": 1780743227,
                    "sender": "honker",
                    "type": "text",
                    "content": "@群聊小助手 你好",
                    "local_id": 11,
                    "chat": "honker",
                    "username": "52859259744@chatroom",
                    "is_group": True,
                }],
            }],
            sessions={
                "sessions": [
                    {
                        "username": "wxid_jfs04ffdka4u21",
                        "chat": "honker",
                        "chat_type": "private",
                        "is_group": False,
                    },
                    {
                        "username": "52859259744@chatroom",
                        "chat": "honker",
                        "chat_type": "group",
                        "is_group": True,
                    },
                ],
            },
        )
        automation = FakeMacAutomation()
        with patch.dict("os.environ", {"MAC_CHAT_TITLE_MAP": ""}):
            backend = MacHybridBackend(
                bot_display_name="群聊小助手",
                groups=["*"],
                client=client,
                automation=automation,
            )

        backend.poll_once(lambda msg: "收到")

        self.assertEqual(automation.open_options, [{
            "chat_name": "honker",
            "prefer_group": True,
            "sidebar_index": None,
            "expected_title": "honker",
            "expected_is_group": True,
            "require_group_marker": True,
        }])
        self.assertEqual(automation.sent, ["收到"])

    def test_mac_hybrid_start_primes_chatlog_state_without_replying_to_history(self):
        from src.wechat.mac_hybrid_backend import MacHybridBackend

        client = FakeChatlogClient([
            {
                "count": 1,
                "new_state": {"room1@chatroom": 100},
                "messages": [{
                    "timestamp": 99,
                    "sender": "Alice",
                    "type": "text",
                    "content": "@群聊小助手 旧消息",
                    "local_id": 1,
                    "chat": "摸鱼群",
                    "username": "room1@chatroom",
                    "is_group": True,
                }],
            },
            {
                "count": 1,
                "new_state": {"room1@chatroom": 101},
                "messages": [{
                    "timestamp": 101,
                    "sender": "Alice",
                    "type": "text",
                    "content": "@群聊小助手 新消息",
                    "local_id": 2,
                    "chat": "摸鱼群",
                    "username": "room1@chatroom",
                    "is_group": True,
                }],
            },
        ])
        automation = FakeMacAutomation()
        backend = MacHybridBackend(
            bot_display_name="群聊小助手",
            groups=["*"],
            poll_sec=0,
            client=client,
            automation=automation,
        )
        seen = []

        def callback(msg):
            seen.append(msg)
            backend.stop()
            return "收到新消息"

        backend.start(callback)

        self.assertEqual([msg["content"] for msg in seen], ["@群聊小助手 新消息"])
        self.assertEqual(automation.sent, ["收到新消息"])

    def test_mac_hybrid_start_ensures_chatlog_service_before_priming(self):
        from src.wechat.mac_hybrid_backend import MacHybridBackend

        client = FakeChatlogClient([
            {"count": 0, "new_state": {"room1@chatroom": 10}, "messages": []},
            {
                "count": 1,
                "new_state": {"room1@chatroom": 11},
                "messages": [{
                    "timestamp": 11,
                    "sender": "Alice",
                    "type": "text",
                    "content": "@群聊小助手 新消息",
                    "local_id": 2,
                    "chat": "摸鱼群",
                    "username": "room1@chatroom",
                    "is_group": True,
                }],
            },
        ])
        service_manager = FakeChatlogServiceManager()
        backend = MacHybridBackend(
            bot_display_name="群聊小助手",
            groups=["*"],
            poll_sec=0,
            client=client,
            automation=FakeMacAutomation(),
            service_manager=service_manager,
        )

        backend.start(lambda msg: backend.stop() or "收到")

        self.assertEqual(service_manager.calls, 1)
        self.assertEqual(client.calls[0], {"state": {}, "limit": 200})

    def test_chatlog_service_manager_noops_when_service_is_healthy(self):
        from src.wechat.mac_chatlog_service import MacChatlogServiceManager

        launches = []
        manager = MacChatlogServiceManager(
            client=FakeHealthClient([True]),
            popen_factory=lambda *args, **kwargs: launches.append((args, kwargs)),
        )

        self.assertFalse(manager.ensure_running())
        self.assertEqual(launches, [])

    def test_chatlog_service_manager_starts_bundled_binary_with_runtime_env(self):
        from src.wechat.mac_chatlog_service import MacChatlogServiceManager

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "tools" / "macos_chatlog" / "chatlog-alpha"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            binary.chmod(0o755)
            app_home = root / "home"
            data_dir = root / "wechat-data"
            data_dir.mkdir()
            launches = []

            def fake_popen(cmd, **kwargs):
                launches.append({"cmd": cmd, **kwargs})
                return FakeChatlogProcess()

            manager = MacChatlogServiceManager(
                client=FakeHealthClient([False, False, True]),
                base_url="http://127.0.0.1:5039",
                app_home=app_home,
                resource_root=root,
                data_dir_resolver=lambda: str(data_dir),
                popen_factory=fake_popen,
                sleep_func=lambda _: None,
            )

            self.assertTrue(manager.ensure_running(timeout=1))

            self.assertEqual(launches[0]["cmd"], [str(binary.resolve())])
            self.assertEqual(launches[0]["cwd"], str(app_home.resolve()))
            self.assertEqual(launches[0]["env"]["CHATLOG_DATA_DIR"], str(data_dir))
            self.assertEqual(launches[0]["env"]["CHATLOG_HTTP_ADDR"], "127.0.0.1:5039")
            self.assertTrue((app_home / "data" / "chatlog_alpha.log").exists())

    def test_chatlog_service_manager_raises_clear_error_when_binary_missing(self):
        from src.wechat.mac_chatlog_service import ChatlogServiceError, MacChatlogServiceManager

        with tempfile.TemporaryDirectory() as tmp:
            manager = MacChatlogServiceManager(
                client=FakeHealthClient([False]),
                app_home=Path(tmp) / "home",
                resource_root=Path(tmp) / "missing",
                data_dir_resolver=lambda: str(Path(tmp) / "wechat-data"),
            )

            with self.assertRaisesRegex(ChatlogServiceError, "chatlog-alpha binary not found"):
                manager.ensure_running(timeout=1)

    def test_health_monitor_uses_mac_backend_health_status_without_window(self):
        from src.bot import HealthMonitor
        from src.wechat.mac_hybrid_backend import MacHybridBackend

        cfg = BotConfig(
            ai_backend="deepseek",
            deepseek_api_key="sk-test",
            wechat_backend="mac_hybrid",
        )
        backend = MacHybridBackend(client=FakeChatlogClient(), automation=FakeMacAutomation())
        monitor = HealthMonitor(
            summarizer=type("S", (), {"last_api_call_time": 0})(),
            router=type("R", (), {"messages_processed": 0})(),
            conn=type("C", (), {"execute": lambda self, sql: None})(),
            backend=backend,
            config=cfg,
        )

        self.assertEqual(monitor._check_wechat_hwnd(), "chatlog_ok")


if __name__ == "__main__":
    unittest.main()
