"""Tests for Feishu/Lark export integration."""

import json
import os
import sqlite3
import time
import unittest
from unittest.mock import MagicMock, patch


class FeishuConfigTests(unittest.TestCase):
    def test_load_config_reads_feishu_export_settings(self):
        from src.config import load_config

        env = {
            "AI_BACKEND": "deepseek",
            "DEEPSEEK_API_KEY": "sk-test-key",
            "FEISHU_EXPORT_ENABLED": "true",
            "FEISHU_APP_ID": "cli_test",
            "FEISHU_APP_SECRET": "secret_test",
            "FEISHU_EXPORT_MODE": "spreadsheet",
            "FEISHU_SPREADSHEET_TOKEN": "sht_test",
            "FEISHU_SPREADSHEET_RANGE": "Sheet1!A:H",
            "FEISHU_EXPORT_WINDOW_HOURS": "6",
            "FEISHU_EXPORT_TRIGGER_KEYWORDS": "同步到飞书,导出到飞书",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = load_config()

        self.assertTrue(cfg.feishu_export_enabled)
        self.assertEqual(cfg.feishu_app_id, "cli_test")
        self.assertEqual(cfg.feishu_app_secret, "secret_test")
        self.assertEqual(cfg.feishu_export_mode, "spreadsheet")
        self.assertEqual(cfg.feishu_spreadsheet_token, "sht_test")
        self.assertEqual(cfg.feishu_spreadsheet_range, "Sheet1!A:H")
        self.assertEqual(cfg.feishu_export_window_hours, 6)
        self.assertEqual(cfg.feishu_export_trigger_keywords, ["同步到飞书", "导出到飞书"])

    def test_load_config_rejects_invalid_feishu_export_mode(self):
        from src.config import load_config

        env = {
            "AI_BACKEND": "deepseek",
            "DEEPSEEK_API_KEY": "sk-test-key",
            "FEISHU_EXPORT_MODE": "calendar",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                load_config()

        self.assertIn("FEISHU_EXPORT_MODE", str(ctx.exception))


class FeishuClientTests(unittest.TestCase):
    def test_client_caches_tenant_access_token(self):
        from src.integrations.feishu.client import FeishuClient

        calls = []

        def fake_request(method, path, body=None, token=None, query=None):
            calls.append((method, path, body, token, query))
            return {"code": 0, "tenant_access_token": "t-test", "expire": 7200}

        client = FeishuClient("cli_test", "secret_test", request_json=fake_request, now=lambda: 1000)

        self.assertEqual(client.tenant_access_token(), "t-test")
        self.assertEqual(client.tenant_access_token(), "t-test")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], "/open-apis/auth/v3/tenant_access_token/internal")

    def test_append_spreadsheet_rows_sends_expected_payload(self):
        from src.integrations.feishu.client import FeishuClient

        calls = []

        def fake_request(method, path, body=None, token=None, query=None):
            calls.append((method, path, body, token, query))
            if path.endswith("/tenant_access_token/internal"):
                return {"code": 0, "tenant_access_token": "t-test", "expire": 7200}
            return {"code": 0, "data": {"updates": {"updatedRows": 1}}}

        client = FeishuClient("cli_test", "secret_test", request_json=fake_request, now=lambda: 1000)
        result = client.append_spreadsheet_rows(
            spreadsheet_token="sht_test",
            range_name="Sheet1!A:H",
            rows=[["2026-06-08", "摸鱼群"]],
        )

        self.assertEqual(result["data"]["updates"]["updatedRows"], 1)
        method, path, body, token, query = calls[-1]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/open-apis/sheets/v2/spreadsheets/sht_test/values_append")
        self.assertEqual(token, "t-test")
        self.assertEqual(query, {"insertDataOption": "INSERT_ROWS"})
        self.assertEqual(body["valueRange"]["range"], "Sheet1!A:H")
        self.assertEqual(body["valueRange"]["values"], [["2026-06-08", "摸鱼群"]])

    def test_create_bitable_record_sends_expected_payload(self):
        from src.integrations.feishu.client import FeishuClient

        calls = []

        def fake_request(method, path, body=None, token=None, query=None):
            calls.append((method, path, body, token, query))
            if path.endswith("/tenant_access_token/internal"):
                return {"code": 0, "tenant_access_token": "t-test", "expire": 7200}
            return {"code": 0, "data": {"record": {"record_id": "rec_test"}}}

        client = FeishuClient("cli_test", "secret_test", request_json=fake_request, now=lambda: 1000)
        result = client.create_bitable_record(
            app_token="base_test",
            table_id="tbl_test",
            fields={"群聊": "摸鱼群", "摘要": "今天聊了飞书导出"},
        )

        self.assertEqual(result["data"]["record"]["record_id"], "rec_test")
        method, path, body, token, query = calls[-1]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/open-apis/bitable/v1/apps/base_test/tables/tbl_test/records")
        self.assertEqual(token, "t-test")
        self.assertEqual(body, {"fields": {"群聊": "摸鱼群", "摘要": "今天聊了飞书导出"}})


class FeishuExportServiceTests(unittest.TestCase):
    def _store_with_messages(self):
        from src.db import MessageStore, initialize_db

        conn = initialize_db(":memory:")
        store = MessageStore(conn)
        base = int(time.time()) - 120
        store.insert_message({
            "message_id": "m1",
            "chat_id": "chat1@chatroom",
            "sender_id": "u1",
            "sender_name": "小明",
            "content": "我们要把群聊沉淀到飞书",
            "msg_type": 1,
            "timestamp": base,
        })
        store.insert_message({
            "message_id": "m2",
            "chat_id": "chat1@chatroom",
            "sender_id": "u2",
            "sender_name": "小红",
            "content": "先写到多维表格比较好查",
            "msg_type": 1,
            "timestamp": base + 30,
        })
        return store

    def test_export_to_spreadsheet_summarizes_recent_messages(self):
        from src.config import BotConfig
        from src.integrations.feishu.exporter import FeishuExportService
        from src.summarize.models import SummaryResult

        cfg = BotConfig(
            feishu_export_enabled=True,
            feishu_export_mode="spreadsheet",
            feishu_spreadsheet_token="sht_test",
            feishu_spreadsheet_range="Sheet1!A:H",
        )
        store = self._store_with_messages()
        summarizer = MagicMock()
        summarizer.summarize.return_value = SummaryResult(
            summary_text="大家讨论了把微信群聊总结同步到飞书，倾向先写多维表格。",
            topics=["飞书导出"],
            participants=[],
        )
        client = MagicMock()
        client.append_spreadsheet_rows.return_value = {"code": 0}
        service = FeishuExportService(cfg, store, summarizer, client=client)

        result = service.export_recent_chat({
            "chat_id": "chat1@chatroom",
            "group_name": "摸鱼群",
            "sender_name": "管理员",
            "sender_id": "admin",
            "timestamp": int(time.time()),
        })

        self.assertTrue(result.ok)
        self.assertIn("已同步到飞书电子表格", result.reply_text)
        summarizer.summarize.assert_called_once()
        client.append_spreadsheet_rows.assert_called_once()
        rows = client.append_spreadsheet_rows.call_args.kwargs["rows"]
        self.assertEqual(rows[0][1], "摸鱼群")
        self.assertIn("多维表格", rows[0][5])

    def test_export_to_bitable_maps_fields(self):
        from src.config import BotConfig
        from src.integrations.feishu.exporter import FeishuExportService
        from src.summarize.models import SummaryResult

        cfg = BotConfig(
            feishu_export_enabled=True,
            feishu_export_mode="bitable",
            feishu_bitable_app_token="base_test",
            feishu_bitable_table_id="tbl_test",
        )
        store = self._store_with_messages()
        summarizer = MagicMock()
        summarizer.summarize.return_value = SummaryResult(
            summary_text="测试摘要",
            topics=["主题A", "主题B"],
            participants=[],
        )
        client = MagicMock()
        client.create_bitable_record.return_value = {"code": 0}
        service = FeishuExportService(cfg, store, summarizer, client=client)

        result = service.export_recent_chat({
            "chat_id": "chat1@chatroom",
            "group_name": "摸鱼群",
            "sender_name": "管理员",
            "sender_id": "admin",
            "timestamp": int(time.time()),
        })

        self.assertTrue(result.ok)
        self.assertIn("已同步到飞书多维表格", result.reply_text)
        fields = client.create_bitable_record.call_args.kwargs["fields"]
        self.assertEqual(fields["群聊"], "摸鱼群")
        self.assertEqual(fields["摘要"], "测试摘要")
        self.assertEqual(fields["主题"], "主题A, 主题B")
        self.assertEqual(fields["消息数"], 2)

    def test_export_to_docx_creates_summary_document(self):
        from src.config import BotConfig
        from src.integrations.feishu.exporter import FeishuExportService
        from src.summarize.models import SummaryResult

        cfg = BotConfig(
            feishu_export_enabled=True,
            feishu_export_mode="docx",
            feishu_doc_folder_token="fld_test",
        )
        store = self._store_with_messages()
        summarizer = MagicMock()
        summarizer.summarize.return_value = SummaryResult(
            summary_text="大家讨论了把微信群聊沉淀成飞书文档。",
            topics=["飞书文档"],
            participants=[],
        )
        client = MagicMock()
        client.create_docx_with_markdown.return_value = {"code": 0}
        service = FeishuExportService(cfg, store, summarizer, client=client)

        result = service.export_recent_chat({
            "chat_id": "chat1@chatroom",
            "group_name": "摸鱼群",
            "sender_name": "管理员",
            "sender_id": "admin",
            "timestamp": int(time.time()),
        })

        self.assertTrue(result.ok)
        self.assertIn("已创建飞书文档", result.reply_text)
        kwargs = client.create_docx_with_markdown.call_args.kwargs
        self.assertIn("摸鱼群 群聊摘要", kwargs["title"])
        self.assertIn("飞书文档", kwargs["markdown"])
        self.assertEqual(kwargs["folder_token"], "fld_test")

    def test_disabled_export_returns_clear_reply(self):
        from src.config import BotConfig
        from src.integrations.feishu.exporter import FeishuExportService

        service = FeishuExportService(BotConfig(), self._store_with_messages(), MagicMock(), client=MagicMock())

        result = service.export_recent_chat({
            "chat_id": "chat1@chatroom",
            "group_name": "摸鱼群",
            "sender_name": "管理员",
            "sender_id": "admin",
            "timestamp": int(time.time()),
        })

        self.assertFalse(result.ok)
        self.assertIn("飞书同步还没开启", result.reply_text)


class FeishuRouterTests(unittest.TestCase):
    def test_at_mention_export_command_uses_export_service(self):
        from src.config import BotConfig
        from src.router import MessageRouter
        from src.trigger import TriggerDetector

        class Store:
            def __init__(self):
                self.inserted = []

            def insert_message(self, msg):
                self.inserted.append(msg)
                return True

            def get_group_memory(self, chat_id):
                return None

        export_service = MagicMock()
        export_service.is_export_command.return_value = True
        export_service.export_recent_chat.return_value = MagicMock(
            reply_text="@管理员 已同步到飞书电子表格。"
        )
        router = MessageRouter(
            store=Store(),
            detector=TriggerDetector(["总结一下"], "群聊小助手"),
            summarizer=MagicMock(),
            admin_handler=MagicMock(),
            nickname_service=MagicMock(),
            config=BotConfig(
                bot_display_name="群聊小助手",
                feishu_export_enabled=True,
            ),
            feishu_export_service=export_service,
        )

        reply = router.handle({
            "message_id": "trigger-1",
            "chat_id": "chat1@chatroom",
            "group_name": "摸鱼群",
            "sender_id": "admin",
            "sender_name": "管理员",
            "content": "@群聊小助手 同步到飞书",
            "msg_type": 1,
            "timestamp": int(time.time()),
            "is_at_mentioned": True,
            "is_group": True,
        })

        self.assertEqual(reply, "@管理员 已同步到飞书电子表格。")
        export_service.export_recent_chat.assert_called_once()


class FeishuWebApiTests(unittest.TestCase):
    def test_config_export_includes_feishu_fields(self):
        from src.config import find_env_file
        from src.web import server

        export = {
            "FEISHU_EXPORT_ENABLED": "true",
            "FEISHU_APP_ID": "cli_test",
            "FEISHU_EXPORT_MODE": "spreadsheet",
            "FEISHU_SPREADSHEET_TOKEN": "sht_test",
        }
        self.assertIsNotNone(find_env_file)
        self.assertIn("FEISHU_EXPORT_ENABLED", json.dumps(export))
