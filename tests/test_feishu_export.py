"""Tests for Feishu/Lark export integration."""

import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
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
            "FEISHU_AUTO_SYNC_ENABLED": "true",
            "FEISHU_AUTO_SYNC_MIN_MESSAGES": "5",
            "FEISHU_AUTO_SYNC_COOLDOWN_SEC": "600",
            "FEISHU_KNOWLEDGE_BASE_NAME": "webot 测试沉淀",
            "FEISHU_KNOWLEDGE_FOLDER_TOKEN": "fld_test",
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
        self.assertTrue(cfg.feishu_auto_sync_enabled)
        self.assertEqual(cfg.feishu_auto_sync_min_messages, 5)
        self.assertEqual(cfg.feishu_auto_sync_cooldown_sec, 600)
        self.assertEqual(cfg.feishu_knowledge_base_name, "webot 测试沉淀")
        self.assertEqual(cfg.feishu_knowledge_folder_token, "fld_test")

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

    def test_create_bitable_app_sends_expected_payload(self):
        from src.integrations.feishu.client import FeishuClient

        calls = []

        def fake_request(method, path, body=None, token=None, query=None):
            calls.append((method, path, body, token, query))
            if path.endswith("/tenant_access_token/internal"):
                return {"code": 0, "tenant_access_token": "t-test", "expire": 7200}
            return {"code": 0, "data": {"app": {"app_token": "base_new"}}}

        client = FeishuClient("cli_test", "secret_test", request_json=fake_request, now=lambda: 1000)
        result = client.create_bitable_app(name="webot 群聊沉淀", folder_token="fld_test")

        self.assertEqual(result["data"]["app"]["app_token"], "base_new")
        method, path, body, token, query = calls[-1]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/open-apis/bitable/v1/apps")
        self.assertEqual(token, "t-test")
        self.assertEqual(body, {"name": "webot 群聊沉淀", "folder_token": "fld_test"})

    def test_create_bitable_table_sends_fields(self):
        from src.integrations.feishu.client import FeishuClient

        calls = []

        def fake_request(method, path, body=None, token=None, query=None):
            calls.append((method, path, body, token, query))
            if path.endswith("/tenant_access_token/internal"):
                return {"code": 0, "tenant_access_token": "t-test", "expire": 7200}
            return {"code": 0, "data": {"table_id": "tbl_summary"}}

        client = FeishuClient("cli_test", "secret_test", request_json=fake_request, now=lambda: 1000)
        result = client.create_bitable_table(
            app_token="base_new",
            table_name="群聊摘要",
            fields=[
                {"field_name": "群聊", "type": 1},
                {"field_name": "消息数", "type": 2},
            ],
        )

        self.assertEqual(result["data"]["table_id"], "tbl_summary")
        method, path, body, token, query = calls[-1]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/open-apis/bitable/v1/apps/base_new/tables")
        self.assertEqual(token, "t-test")
        self.assertEqual(body["table"]["name"], "群聊摘要")
        self.assertEqual(body["table"]["default_view_name"], "默认视图")
        self.assertEqual(body["table"]["fields"][0]["field_name"], "群聊")
        self.assertNotIn("fields", body)


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
            "content": "我们要把群聊沉淀到飞书，下周前我来整理方案。",
            "msg_type": 1,
            "timestamp": base,
        })
        store.insert_message({
            "message_id": "m2",
            "chat_id": "chat1@chatroom",
            "sender_id": "u2",
            "sender_name": "小红",
            "content": "需求是自动识别待办和日常记录，先写到多维表格比较好查。",
            "msg_type": 1,
            "timestamp": base + 30,
        })
        store.insert_message({
            "message_id": "m3",
            "chat_id": "chat1@chatroom",
            "sender_id": "u3",
            "sender_name": "小王",
            "content": "今天日常记录：飞书后台权限需要确认。",
            "msg_type": 1,
            "timestamp": base + 60,
        })
        return store

    def _tmp_resource_store(self):
        from src.integrations.feishu.knowledge import FeishuResourceStore

        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "feishu_resources.json"
        store = FeishuResourceStore(path)
        self.addCleanup(tmp.cleanup)
        return store, path

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
        self.assertEqual(fields["消息数"], 3)

    def test_knowledge_base_auto_creates_resources_and_persists_ids(self):
        from src.config import BotConfig
        from src.integrations.feishu.exporter import FeishuExportService
        from src.summarize.models import SummaryResult

        cfg = BotConfig(
            feishu_export_enabled=True,
            feishu_export_mode="knowledge",
            feishu_knowledge_base_name="webot 测试沉淀",
            feishu_knowledge_folder_token="fld_test",
        )
        store = self._store_with_messages()
        resource_store, path = self._tmp_resource_store()
        summarizer = MagicMock()
        summarizer.summarize.return_value = SummaryResult(
            summary_text="讨论了飞书知识库、待办和需求沉淀。",
            topics=["飞书知识库", "自动沉淀"],
            participants=[],
        )
        client = MagicMock()
        client.create_bitable_app.return_value = {"data": {"app": {"app_token": "base_auto"}}}
        client.create_bitable_table.side_effect = [
            {"data": {"table_id": "tbl_summary"}},
            {"data": {"table_id": "tbl_todo"}},
            {"data": {"table_id": "tbl_requirement"}},
            {"data": {"table_id": "tbl_daily"}},
        ]
        client.create_bitable_record.return_value = {"code": 0}
        service = FeishuExportService(
            cfg,
            store,
            summarizer,
            client=client,
            resource_store=resource_store,
        )

        result = service.export_recent_chat({
            "chat_id": "chat1@chatroom",
            "group_name": "摸鱼群",
            "sender_name": "管理员",
            "sender_id": "admin",
            "timestamp": int(time.time()),
        })

        self.assertTrue(result.ok)
        self.assertIn("已沉淀到飞书知识库", result.reply_text)
        client.create_bitable_app.assert_called_once_with(
            name="webot 测试沉淀",
            folder_token="fld_test",
        )
        created_table_names = [
            call.kwargs["table_name"]
            for call in client.create_bitable_table.call_args_list
        ]
        self.assertEqual(created_table_names, ["群聊摘要", "待办", "需求", "日常记录"])
        persisted = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["app_token"], "base_auto")
        self.assertEqual(persisted["tables"]["summary"], "tbl_summary")
        self.assertEqual(persisted["tables"]["todo"], "tbl_todo")
        self.assertEqual(persisted["tables"]["requirement"], "tbl_requirement")
        self.assertEqual(persisted["tables"]["daily"], "tbl_daily")
        called_table_ids = {
            call.kwargs["table_id"]
            for call in client.create_bitable_record.call_args_list
        }
        self.assertIn("tbl_summary", called_table_ids)
        self.assertIn("tbl_todo", called_table_ids)
        self.assertIn("tbl_requirement", called_table_ids)
        self.assertIn("tbl_daily", called_table_ids)

    def test_knowledge_base_reuses_persisted_resources(self):
        from src.config import BotConfig
        from src.integrations.feishu.exporter import FeishuExportService
        from src.summarize.models import SummaryResult

        resource_store, path = self._tmp_resource_store()
        path.write_text(json.dumps({
            "app_token": "base_saved",
            "tables": {
                "summary": "tbl_summary",
                "todo": "tbl_todo",
                "requirement": "tbl_requirement",
                "daily": "tbl_daily",
            },
        }), encoding="utf-8")
        cfg = BotConfig(
            feishu_export_enabled=True,
            feishu_export_mode="knowledge",
        )
        summarizer = MagicMock()
        summarizer.summarize.return_value = SummaryResult(
            summary_text="摘要",
            topics=[],
            participants=[],
        )
        client = MagicMock()
        client.create_bitable_record.return_value = {"code": 0}
        service = FeishuExportService(
            cfg,
            self._store_with_messages(),
            summarizer,
            client=client,
            resource_store=resource_store,
        )

        result = service.export_recent_chat({
            "chat_id": "chat1@chatroom",
            "group_name": "摸鱼群",
            "sender_name": "管理员",
            "sender_id": "admin",
            "timestamp": int(time.time()),
        })

        self.assertTrue(result.ok)
        client.create_bitable_app.assert_not_called()
        client.create_bitable_table.assert_not_called()
        self.assertGreaterEqual(client.create_bitable_record.call_count, 1)

    def test_auto_export_uses_no_reply_and_respects_minimum_message_count(self):
        from src.config import BotConfig
        from src.integrations.feishu.exporter import FeishuExportService
        from src.summarize.models import SummaryResult

        cfg = BotConfig(
            feishu_export_enabled=True,
            feishu_export_mode="knowledge",
            feishu_auto_sync_enabled=True,
            feishu_auto_sync_min_messages=4,
        )
        summarizer = MagicMock()
        summarizer.summarize.return_value = SummaryResult(
            summary_text="摘要",
            topics=[],
            participants=[],
        )
        client = MagicMock()
        resource_store, _path = self._tmp_resource_store()
        service = FeishuExportService(
            cfg,
            self._store_with_messages(),
            summarizer,
            client=client,
            resource_store=resource_store,
        )

        result = service.maybe_auto_export({
            "message_id": "m3",
            "chat_id": "chat1@chatroom",
            "group_name": "摸鱼群",
            "sender_name": "小王",
            "sender_id": "u3",
            "timestamp": int(time.time()),
        })

        self.assertIsNone(result)
        client.create_bitable_record.assert_not_called()

        cfg.feishu_auto_sync_min_messages = 3
        client.create_bitable_app.return_value = {"data": {"app": {"app_token": "base_auto"}}}
        client.create_bitable_table.side_effect = [
            {"data": {"table_id": "tbl_summary"}},
            {"data": {"table_id": "tbl_todo"}},
            {"data": {"table_id": "tbl_requirement"}},
            {"data": {"table_id": "tbl_daily"}},
        ]
        client.create_bitable_record.return_value = {"code": 0}

        result = service.maybe_auto_export({
            "message_id": "m3",
            "chat_id": "chat1@chatroom",
            "group_name": "摸鱼群",
            "sender_name": "小王",
            "sender_id": "u3",
            "timestamp": int(time.time()),
        })

        self.assertTrue(result.ok)
        self.assertEqual(result.reply_text, "")
        client.create_bitable_record.assert_called()
        daily_calls = [
            call for call in client.create_bitable_record.call_args_list
            if call.kwargs["table_id"] == "tbl_daily"
        ]
        self.assertTrue(daily_calls)
        self.assertIn("权限需要确认", daily_calls[-1].kwargs["fields"]["记录"])

    def test_auto_export_silently_skips_when_feishu_credentials_missing(self):
        from src.config import BotConfig
        from src.integrations.feishu.exporter import FeishuExportService

        cfg = BotConfig(
            feishu_export_enabled=True,
            feishu_export_mode="knowledge",
            feishu_auto_sync_enabled=True,
            feishu_auto_sync_min_messages=1,
        )
        summarizer = MagicMock()
        service = FeishuExportService(
            cfg,
            self._store_with_messages(),
            summarizer,
            resource_store=self._tmp_resource_store()[0],
        )

        with patch("src.integrations.feishu.exporter.FeishuClient") as client_cls:
            result = service.maybe_auto_export({
                "message_id": "m3",
                "chat_id": "chat1@chatroom",
                "group_name": "摸鱼群",
                "sender_name": "小王",
                "sender_id": "u3",
                "timestamp": int(time.time()),
            })

        self.assertIsNone(result)
        summarizer.summarize.assert_not_called()
        client_cls.assert_not_called()

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

    def test_non_mention_message_can_trigger_silent_auto_export(self):
        from src.config import BotConfig
        from src.router import MessageRouter
        from src.trigger import TriggerDetector

        class Store:
            def insert_message(self, msg):
                return True

            def get_group_memory(self, chat_id):
                return None

        export_service = MagicMock()
        export_service.maybe_auto_export.return_value = MagicMock(ok=True, reply_text="")
        router = MessageRouter(
            store=Store(),
            detector=TriggerDetector(["总结一下"], "群聊小助手"),
            summarizer=MagicMock(),
            admin_handler=MagicMock(),
            nickname_service=MagicMock(),
            config=BotConfig(
                bot_display_name="群聊小助手",
                feishu_export_enabled=True,
                feishu_export_mode="knowledge",
                feishu_auto_sync_enabled=True,
                proactive_enabled=False,
            ),
            feishu_export_service=export_service,
        )

        reply = router.handle({
            "message_id": "normal-1",
            "chat_id": "chat1@chatroom",
            "group_name": "摸鱼群",
            "sender_id": "u1",
            "sender_name": "小明",
            "content": "今天日常记录一下，需求是自动沉淀待办。",
            "msg_type": 1,
            "timestamp": int(time.time()),
            "is_at_mentioned": False,
            "is_group": True,
        })

        self.assertIsNone(reply)
        export_service.maybe_auto_export.assert_called_once()


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
