"""Tests for macOS chatlog setup helpers."""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_setup_module():
    path = Path(__file__).resolve().parent.parent / "tools" / "macos_chatlog_setup.py"
    spec = importlib.util.spec_from_file_location("macos_chatlog_setup", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MacOSChatlogSetupTests(unittest.TestCase):
    def test_parse_data_dir_from_lsof_output(self):
        setup = _load_setup_module()
        output = """
WeChat 17947 user 100r REG 1,16 114688 /Users/me/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_abc/db_storage/session/session.db
WeChat 17947 user 101r REG 1,16 565248 /Users/me/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_abc/db_storage/message/message_0.db
"""

        self.assertEqual(
            setup.parse_data_dir_from_lsof(output),
            "/Users/me/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_abc",
        )

    def test_count_valid_keys_accepts_dict_and_string_formats(self):
        setup = _load_setup_module()
        key = "a" * 64
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "all_keys.json"
            path.write_text(
                json.dumps({
                    "message/message_0.db": {"enc_key": key},
                    "session/session.db": key,
                    "__salts__": ["ignored"],
                    "bad.db": {"enc_key": "not-a-key"},
                }),
                encoding="utf-8",
            )

            self.assertEqual(setup.count_valid_keys(path), 2)

    def test_parse_sip_status(self):
        setup = _load_setup_module()

        self.assertEqual(
            setup.parse_sip_status("System Integrity Protection status: disabled."),
            "disabled",
        )
        self.assertEqual(
            setup.parse_sip_status("System Integrity Protection status: enabled."),
            "enabled",
        )
        self.assertEqual(setup.parse_sip_status("unexpected"), "unknown")

    def test_normalize_key_entries_converts_supported_formats(self):
        setup = _load_setup_module()
        key = "A" * 64

        entries = setup.normalize_key_entries({
            "message/message_0.db": key,
            "session/session.db": {"enc_key": key.lower()},
            "__salts__": ["ignored"],
            "bad.db": {"enc_key": "not-a-key"},
        })

        self.assertEqual(entries, {
            "message/message_0.db": {"enc_key": key.lower()},
            "session/session.db": {"enc_key": key.lower()},
        })

    def test_write_all_keys_uses_chatlog_alpha_format(self):
        setup = _load_setup_module()
        key = "a" * 64
        with tempfile.TemporaryDirectory() as tmp:
            path = setup.write_all_keys(tmp, {"message/message_0.db": {"enc_key": key}})
            saved = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(saved, {"message/message_0.db": {"enc_key": key}})
            self.assertEqual(setup.count_valid_keys(path), 1)

    def test_detect_data_dir_from_filesystem_uses_latest_session_db(self):
        setup = _load_setup_module()

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            old_db = (
                home
                / "Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
                / "wxid_old/db_storage/session/session.db"
            )
            new_db = (
                home
                / "Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
                / "wxid_new/db_storage/session/session.db"
            )
            old_db.parent.mkdir(parents=True)
            new_db.parent.mkdir(parents=True)
            old_db.write_bytes(b"old")
            new_db.write_bytes(b"new")
            os.utime(old_db, (1000, 1000))
            os.utime(new_db, (2000, 2000))

            with patch.object(setup.Path, "home", return_value=home):
                self.assertEqual(
                    setup.detect_data_dir_from_filesystem(),
                    str(new_db.parent.parent.parent),
                )

    def test_count_open_db_files_counts_db_storage_handles(self):
        setup = _load_setup_module()
        data_dir = "/Users/me/xwechat_files/wxid_abc"
        lsof = f"""
WeChat 123 me 77r REG 1,16 1 {data_dir}/db_storage/session/session.db
WeChat 123 me 78u REG 1,16 1 {data_dir}/db_storage/session/session.db-wal
WeChat 123 me 79u REG 1,16 1 {data_dir}/db_storage/message/message_0.kvdb
WeChat 123 me 80r REG 1,16 1 /tmp/other.db
"""

        with patch.object(setup, "run_text", return_value=lsof):
            self.assertEqual(setup.count_open_db_files(123, data_dir), 3)

    def test_build_extract_command_uses_sudo_and_never_embeds_key_material(self):
        setup = _load_setup_module()

        cmd = setup.build_extract_command(
            scanner="/tmp/macscan",
            pid=123,
            data_dir="/Users/me/xwechat_files/wxid_abc",
        )

        self.assertEqual(cmd[:2], ["sudo", "/tmp/macscan"])
        self.assertIn("--pid", cmd)
        self.assertIn("123", cmd)
        self.assertIn("--data-dir", cmd)
        self.assertIn("/Users/me/xwechat_files/wxid_abc", cmd)
        self.assertNotIn("enc_key", " ".join(cmd))

    def test_build_lldb_extract_command_uses_sudo_env_and_never_embeds_key_material(self):
        setup = _load_setup_module()

        cmd = setup.build_lldb_extract_command(
            script=Path("/tmp/macos_lldb_keyscan.py"),
            python_bin="/usr/bin/python3",
            pid=123,
            data_dir="/Users/me/xwechat_files/wxid_abc",
            lldb_python_path="/Applications/Xcode.app/LLDB/Python",
        )

        self.assertEqual(cmd[:3], ["sudo", "env", "PYTHONPATH=/Applications/Xcode.app/LLDB/Python"])
        self.assertEqual(cmd[3], "/usr/bin/python3")
        self.assertIn("/tmp/macos_lldb_keyscan.py", cmd)
        self.assertIn("--pid", cmd)
        self.assertIn("123", cmd)
        self.assertIn("--data-dir", cmd)
        self.assertIn("/Users/me/xwechat_files/wxid_abc", cmd)
        self.assertNotIn("enc_key", " ".join(cmd))

    def test_build_lldb_env_prepends_lldb_python_path(self):
        setup = _load_setup_module()

        env = setup.build_lldb_env(
            lldb_python_path="/Applications/Xcode.app/LLDB/Python",
            base_env={"PYTHONPATH": "/existing"},
        )

        self.assertEqual(
            env["PYTHONPATH"],
            "/Applications/Xcode.app/LLDB/Python:/existing",
        )

    def test_run_lldb_keyscan_invokes_sudo_env_pythonpath(self):
        setup = _load_setup_module()

        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "macos_lldb_keyscan.py"
            script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            with (
                patch.object(setup, "LLDB_SCANNER_SCRIPT", script),
                patch.object(setup, "detect_wechat_pid", return_value=123),
                patch.object(setup, "detect_data_dir", return_value="/Users/me/xwechat_files/wxid_abc"),
                patch.object(setup, "detect_lldb_python_path", return_value="/Applications/Xcode.app/LLDB/Python"),
                patch.object(setup, "resolve_lldb_python_bin", return_value="/usr/bin/python3"),
                patch.object(setup, "count_valid_keys", return_value=0),
                patch.object(setup.subprocess, "run") as run,
            ):
                run.return_value.returncode = 0

                self.assertEqual(setup.run_lldb_keyscan(mode="aes-hook", duration=120), 0)

        cmd = run.call_args.args[0]
        self.assertEqual(cmd[:3], ["sudo", "env", "PYTHONPATH=/Applications/Xcode.app/LLDB/Python"])
        self.assertIn("--mode", cmd)
        self.assertIn("aes-hook", cmd)
        self.assertIn("--duration", cmd)
        self.assertIn("120", cmd)

    def test_extract_keys_falls_back_to_lldb_when_mach_scanner_finds_no_keys(self):
        setup = _load_setup_module()

        with (
            patch.object(setup, "detect_wechat_pid", return_value=123),
            patch.object(setup, "detect_data_dir", return_value="/Users/me/xwechat_files/wxid_abc"),
            patch.object(setup, "build_scanner", return_value=Path("/tmp/macscan")),
            patch.object(setup, "count_valid_keys", return_value=0),
            patch.object(setup, "run_lldb_keyscan", return_value=0) as lldb_scan,
            patch.object(setup.subprocess, "run") as run,
        ):
            run.return_value.returncode = 1

            self.assertEqual(setup.extract_keys(), 0)

        lldb_scan.assert_called_once_with(123, "/Users/me/xwechat_files/wxid_abc")

    def test_extract_keys_lldb_command_is_exposed(self):
        setup = _load_setup_module()

        with patch.object(setup, "run_lldb_keyscan", return_value=0) as lldb_scan:
            self.assertEqual(setup.main(["extract-keys-lldb"]), 0)

        lldb_scan.assert_called_once()

    def test_extract_keys_hook_command_is_exposed(self):
        setup = _load_setup_module()

        with patch.object(setup, "run_lldb_keyscan", return_value=0) as lldb_scan:
            self.assertEqual(setup.main(["extract-keys-hook"]), 0)

        lldb_scan.assert_called_once_with(mode="aes-hook")

    def test_extract_keys_hook_honors_duration_option(self):
        setup = _load_setup_module()

        with patch.object(setup, "run_lldb_keyscan", return_value=0) as lldb_scan:
            self.assertEqual(setup.main(["extract-keys-hook", "--duration", "120"]), 0)

        lldb_scan.assert_called_once_with(mode="aes-hook", duration=120)

    def test_extract_keys_restart_hook_command_is_exposed(self):
        setup = _load_setup_module()

        with patch.object(setup, "restart_wechat_and_hook", return_value=0) as restart_hook:
            rc = setup.main([
                "extract-keys-restart-hook",
                "--yes",
                "--duration",
                "120",
                "--open-chat",
                "文件传输助手",
                "--skip-verify-read",
            ])

        self.assertEqual(rc, 0)
        restart_hook.assert_called_once_with(
            duration=120,
            open_chats=["文件传输助手"],
            assume_yes=True,
            force=False,
            verify_after=False,
            base_url=setup.DEFAULT_CHATLOG_BASE_URL,
        )

    def test_restart_wechat_and_hook_refuses_without_confirmation(self):
        setup = _load_setup_module()

        with (
            patch.object(setup, "confirm_restart_wechat", return_value=False),
            patch.object(setup, "ensure_sudo_ticket") as sudo_ticket,
            patch.object(setup, "quit_wechat_gracefully") as quit_wechat,
        ):
            rc = setup.restart_wechat_and_hook(assume_yes=False)

        self.assertEqual(rc, 1)
        sudo_ticket.assert_not_called()
        quit_wechat.assert_not_called()

    def test_restart_wechat_and_hook_orchestrates_early_hook_and_verify(self):
        setup = _load_setup_module()

        with (
            patch.object(setup, "confirm_restart_wechat", return_value=True),
            patch.object(setup, "detect_wechat_pid", return_value=111),
            patch.object(setup, "detect_data_dir", return_value="/Users/me/xwechat_files/wxid_abc"),
            patch.object(setup, "ensure_sudo_ticket", return_value=True),
            patch.object(setup, "quit_wechat_gracefully", return_value=True) as quit_wechat,
            patch.object(setup, "wait_for_wechat_exit", return_value=True),
            patch.object(setup, "launch_wechat", return_value=True) as launch_wechat,
            patch.object(setup, "wait_for_new_wechat_pid", return_value=222),
            patch.object(setup, "start_chat_warmup") as warmup,
            patch.object(setup, "run_lldb_keyscan", return_value=0) as lldb_scan,
            patch.object(setup, "restart_chatlog", return_value=0) as chatlog_restart,
            patch.object(setup, "verify_read", return_value=0) as verify_read,
        ):
            rc = setup.restart_wechat_and_hook(
                duration=90,
                open_chats=["文件传输助手"],
                assume_yes=True,
                verify_after=True,
                base_url="http://127.0.0.1:5030",
            )

        self.assertEqual(rc, 0)
        quit_wechat.assert_called_once_with(force=False)
        launch_wechat.assert_called_once()
        warmup.assert_called_once_with(["文件传输助手"], duration=90)
        lldb_scan.assert_called_once_with(
            222,
            "/Users/me/xwechat_files/wxid_abc",
            mode="aes-hook",
            duration=90,
        )
        chatlog_restart.assert_called_once_with("http://127.0.0.1:5030")
        verify_read.assert_called_once_with("http://127.0.0.1:5030", limit=5)

    def test_chatlog_build_command_targets_cmd_chatlog(self):
        setup = _load_setup_module()

        cmd = setup.build_chatlog_build_command(
            source_dir=Path("/tmp/chatlog_alpha"),
            output=Path("/tmp/chatlog-alpha"),
        )

        self.assertEqual(cmd, ["go", "build", "-o", "/tmp/chatlog-alpha", "./cmd/chatlog_server"])

    def test_find_chatlog_binary_honors_env_override(self):
        setup = _load_setup_module()

        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "chatlog"
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            binary.chmod(0o755)

            with patch.dict(os.environ, {"CHATLOG_BIN": str(binary)}):
                self.assertEqual(setup.find_chatlog_binary(), binary)

    def test_chatlog_addr_from_base_url(self):
        setup = _load_setup_module()

        self.assertEqual(
            setup.chatlog_addr_from_base_url("http://127.0.0.1:5030"),
            "127.0.0.1:5030",
        )
        self.assertEqual(
            setup.chatlog_addr_from_base_url("127.0.0.1:5030"),
            "127.0.0.1:5030",
        )

    def test_chatlog_port_from_base_url(self):
        setup = _load_setup_module()

        self.assertEqual(setup.chatlog_port_from_base_url("http://127.0.0.1:5030"), 5030)
        self.assertEqual(setup.chatlog_port_from_base_url("127.0.0.1:5031"), 5031)
        self.assertEqual(setup.chatlog_port_from_base_url("http://127.0.0.1"), 5030)

    def test_find_chatlog_binary_rejects_go_archive(self):
        setup = _load_setup_module()

        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "chatlog"
            binary.write_bytes(b"!<arch>\n")
            binary.chmod(0o755)

            with patch.dict(os.environ, {"CHATLOG_BIN": str(binary)}):
                with patch.object(setup, "CHATLOG_BINARY", Path(tmp) / "missing"):
                    self.assertIsNone(setup.find_chatlog_binary())

    def test_summarize_new_messages_payload_redacts_private_values(self):
        setup = _load_setup_module()

        lines = setup.summarize_new_messages_payload({
            "new_state": {"room1@chatroom": 1780727000},
            "messages": [
                {
                    "timestamp": 1780726999,
                    "sender": "Alice",
                    "content": "secret message",
                    "chat": "摸鱼群",
                    "username": "room1@chatroom",
                    "type": "text",
                    "local_id": 42,
                    "is_group": True,
                }
            ],
        })
        output = "\n".join(lines)

        self.assertIn("message_count=1", output)
        self.assertIn("new_state_entries=1", output)
        self.assertIn("sample_fields=is_group,local_id,timestamp,type", output)
        self.assertNotIn("Alice", output)
        self.assertNotIn("secret message", output)
        self.assertNotIn("摸鱼群", output)


if __name__ == "__main__":
    unittest.main()
