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
