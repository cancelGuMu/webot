"""Export WeChat summaries to Feishu/Lark documents or tables."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .client import FeishuClient
from .knowledge import (
    DAILY_TABLE_KEY,
    KNOWLEDGE_TABLES,
    PROJECT_TABLE_KEY,
    REQUIREMENT_TABLE_KEY,
    SUMMARY_TABLE_KEY,
    TODO_TABLE_KEY,
    FeishuResourceStore,
    KnowledgeClassifier,
    strip_feishu_sync_command,
)


@dataclass
class FeishuExportResult:
    ok: bool
    reply_text: str
    response: dict | None = None


class FeishuExportService:
    """Coordinates message lookup, AI summarization, and Feishu writes."""

    def __init__(
        self,
        config,
        store,
        summarizer,
        client: FeishuClient | None = None,
        resource_store: FeishuResourceStore | None = None,
        classifier: KnowledgeClassifier | None = None,
    ):
        self._config = config
        self._store = store
        self._summarizer = summarizer
        self._client = client
        self._resource_store = resource_store or FeishuResourceStore()
        self._classifier = classifier or KnowledgeClassifier()
        self._last_auto_export_ts_by_chat: dict[str, int] = {}

    def is_export_command(self, content: str) -> bool:
        """Return True when a cleaned @mention asks to sync to Feishu."""
        normalized = (content or "").strip().lower()
        if not normalized:
            return False
        return any(
            keyword.strip().lower() in normalized
            for keyword in self._config.feishu_export_trigger_keywords
            if keyword.strip()
        )

    def export_recent_chat(self, trigger_msg: dict) -> FeishuExportResult:
        """Summarize recent chat and export it to the configured Feishu target."""
        requester = trigger_msg.get("sender_name", "群友")
        if not self._config.feishu_export_enabled:
            return FeishuExportResult(
                ok=False,
                reply_text=f"@{requester} 飞书同步还没开启，先去系统配置里打开飞书导出。",
            )

        target_error = self._validate_target()
        if target_error:
            return FeishuExportResult(
                ok=False,
                reply_text=f"@{requester} {target_error}",
            )

        trigger_ts = int(trigger_msg.get("timestamp") or time.time())
        since_ts = trigger_ts - self._config.feishu_export_window_hours * 3600
        messages = self._recent_messages(trigger_msg, since_ts, trigger_ts)
        if not messages:
            return FeishuExportResult(
                ok=False,
                reply_text=f"@{requester} 最近没有可同步的群聊内容。",
            )

        summary = self._summarizer.summarize(messages, requester)
        client = self._get_client()
        mode = self._config.feishu_export_mode
        if mode == "knowledge":
            response = self._export_knowledge(client, trigger_msg, messages, summary)
            return FeishuExportResult(
                ok=True,
                reply_text=f"@{requester} 已沉淀到飞书知识库，共 {len(messages)} 条消息。",
                response=response,
            )

        if mode == "spreadsheet":
            response = client.append_spreadsheet_rows(
                spreadsheet_token=self._config.feishu_spreadsheet_token,
                range_name=self._config.feishu_spreadsheet_range,
                rows=[self._spreadsheet_row(trigger_msg, messages, summary)],
            )
            return FeishuExportResult(
                ok=True,
                reply_text=f"@{requester} 已同步到飞书电子表格，共 {len(messages)} 条消息。",
                response=response,
            )

        if mode == "bitable":
            response = client.create_bitable_record(
                app_token=self._config.feishu_bitable_app_token,
                table_id=self._config.feishu_bitable_table_id,
                fields=self._bitable_fields(trigger_msg, messages, summary),
            )
            return FeishuExportResult(
                ok=True,
                reply_text=f"@{requester} 已同步到飞书多维表格，共 {len(messages)} 条消息。",
                response=response,
            )

        response = client.create_docx_with_markdown(
            title=self._doc_title(trigger_msg),
            markdown=self._doc_markdown(trigger_msg, messages, summary),
            folder_token=self._config.feishu_doc_folder_token,
        )
        return FeishuExportResult(
            ok=True,
            reply_text=f"@{requester} 已创建飞书文档，共 {len(messages)} 条消息。",
            response=response,
        )

    def maybe_auto_export(self, msg: dict) -> FeishuExportResult | None:
        """Silently export recent chat when auto knowledge sync is enabled."""
        if (
            not self._config.feishu_export_enabled
            or not self._config.feishu_auto_sync_enabled
            or self._config.feishu_export_mode != "knowledge"
        ):
            return None
        if self._validate_target():
            return None

        trigger_ts = int(msg.get("timestamp") or time.time())
        chat_id = str(msg.get("chat_id", ""))
        last_export_ts = self._last_auto_export_ts_by_chat.get(chat_id, 0)
        if trigger_ts - last_export_ts < self._config.feishu_auto_sync_cooldown_sec:
            return None

        since_ts = trigger_ts - self._config.feishu_export_window_hours * 3600
        messages = self._recent_messages(msg, since_ts, trigger_ts, include_trigger=True)
        if len(messages) < self._config.feishu_auto_sync_min_messages:
            return None

        summary = self._summarizer.summarize(messages, msg.get("sender_name", "群友"))
        response = self._export_knowledge(self._get_client(), msg, messages, summary)
        self._last_auto_export_ts_by_chat[chat_id] = trigger_ts
        return FeishuExportResult(ok=True, reply_text="", response=response)

    def _get_client(self) -> FeishuClient:
        if self._client is None:
            self._client = FeishuClient(
                self._config.feishu_app_id,
                self._config.feishu_app_secret,
            )
        return self._client

    def _validate_target(self) -> str:
        if (
            self._client is None
            and (not self._config.feishu_app_id or not self._config.feishu_app_secret)
        ):
            return "飞书应用 App ID / App Secret 还没配置。"

        mode = self._config.feishu_export_mode
        if mode == "knowledge":
            return ""
        if mode == "spreadsheet":
            if not self._config.feishu_spreadsheet_token:
                return "飞书电子表格 token 还没配置。"
            if not self._config.feishu_spreadsheet_range:
                return "飞书电子表格写入范围还没配置。"
        elif mode == "bitable":
            if not self._config.feishu_bitable_app_token:
                return "飞书多维表格 app_token 还没配置。"
            if not self._config.feishu_bitable_table_id:
                return "飞书多维表格 table_id 还没配置。"
        return ""

    def _recent_messages(
        self,
        trigger_msg: dict,
        since_ts: int,
        trigger_ts: int,
        *,
        include_trigger: bool = False,
    ) -> list[dict]:
        messages = self._store.get_messages_since(
            trigger_msg["chat_id"],
            since_ts,
            until_ts=trigger_ts,
            limit=self._config.max_messages_for_summary,
        )
        group_name = trigger_msg.get("group_name") or trigger_msg.get("chat_id", "")
        normalized = []
        for msg in messages:
            if (
                not include_trigger
                and msg.get("message_id") == trigger_msg.get("message_id")
            ):
                copied = self._clean_trigger_message(msg, group_name)
                if copied is not None:
                    normalized.append(copied)
                continue
            if not str(msg.get("content", "")).strip():
                continue
            copied = dict(msg)
            copied.setdefault("group_name", group_name)
            normalized.append(copied)
        return normalized

    def _clean_trigger_message(self, msg: dict, group_name: str) -> dict | None:
        content = strip_feishu_sync_command(
            str(msg.get("content", "")),
            bot_display_name=getattr(self._config, "bot_display_name", ""),
        )
        if not content:
            return None
        copied = dict(msg)
        copied["content"] = content
        copied.setdefault("group_name", group_name)
        return copied

    def _export_knowledge(self, client, trigger_msg: dict, messages: list[dict], summary) -> dict:
        resources = self._ensure_knowledge_resources(client)
        app_token = resources["app_token"]
        tables = resources["tables"]
        classified = self._classifier.classify(messages)
        summary_fields = self._bitable_fields(trigger_msg, messages, summary)
        structured_summary = self._knowledge_summary_text(classified)
        if structured_summary:
            summary_fields["摘要"] = structured_summary
            summary_fields["主题"] = self._knowledge_topics(classified)
        responses = {
            SUMMARY_TABLE_KEY: client.create_bitable_record(
                app_token=app_token,
                table_id=tables[SUMMARY_TABLE_KEY],
                fields=summary_fields,
            )
        }
        for table_key in (TODO_TABLE_KEY, REQUIREMENT_TABLE_KEY, DAILY_TABLE_KEY, PROJECT_TABLE_KEY):
            table_id = tables.get(table_key)
            if not table_id:
                continue
            created = []
            for fields in classified.get(table_key, []):
                created.append(client.create_bitable_record(
                    app_token=app_token,
                    table_id=table_id,
                    fields=fields,
                ))
            responses[table_key] = created
        return {"resources": resources, "records": responses}

    def _knowledge_summary_text(self, classified: dict[str, list[dict]]) -> str:
        parts = []
        projects = classified.get(PROJECT_TABLE_KEY, [])
        if projects:
            stage_counts: dict[str, int] = {}
            for project in projects:
                stage = str(project.get("阶段", "")).strip() or "未定"
                stage_counts[stage] = stage_counts.get(stage, 0) + 1
            count_text = "；".join(f"{stage} {count} 个" for stage, count in stage_counts.items())
            project_texts = []
            for project in projects[:8]:
                meta = []
                if project.get("负责人"):
                    meta.append(f"负责人：{project['负责人']}")
                if project.get("协作人"):
                    meta.append(f"协作人：{project['协作人']}")
                suffix = f"，{'，'.join(meta)}" if meta else ""
                project_texts.append(f"{project.get('项目', '')}（{project.get('阶段', '未定')}{suffix}）")
            parts.append(f"项目台账更新：{count_text}。项目：{'；'.join(project_texts)}。")

        requirements = classified.get(REQUIREMENT_TABLE_KEY, [])
        if requirements:
            req_text = "；".join(
                f"{item.get('需求', '')}（{item.get('状态', '待评估')}）"
                for item in requirements[:8]
            )
            parts.append(f"需求沉淀：{req_text}。")

        todos = classified.get(TODO_TABLE_KEY, [])
        if todos:
            todo_text = "；".join(
                f"{item.get('事项', '')}"
                + (f" -> {item.get('负责人')}" if item.get("负责人") else "")
                for item in todos[:8]
            )
            parts.append(f"待办提取：{todo_text}。")

        daily = classified.get(DAILY_TABLE_KEY, [])
        non_project_daily = [
            item for item in daily
            if item.get("分类") != "项目进展"
        ]
        if non_project_daily:
            daily_text = "；".join(str(item.get("记录", "")) for item in non_project_daily[:5])
            parts.append(f"日常记录：{daily_text}。")

        return "\n".join(part for part in parts if part).strip()

    @staticmethod
    def _knowledge_topics(classified: dict[str, list[dict]]) -> str:
        topics = []
        if classified.get(PROJECT_TABLE_KEY):
            topics.append("项目台账")
        if classified.get(REQUIREMENT_TABLE_KEY):
            topics.append("需求")
        if classified.get(TODO_TABLE_KEY):
            topics.append("待办")
        if classified.get(DAILY_TABLE_KEY):
            topics.append("日常记录")
        return ", ".join(topics)

    def _ensure_knowledge_resources(self, client) -> dict:
        resources = self._resource_store.load()
        app_token = str(resources.get("app_token", "")).strip()
        tables = dict(resources.get("tables", {}))
        missing_tables = [table for table in KNOWLEDGE_TABLES if not tables.get(table.key)]
        if app_token and not missing_tables:
            return {"app_token": app_token, "tables": tables}

        if not app_token:
            created = client.create_bitable_app(
                name=self._config.feishu_knowledge_base_name or "webot 群聊沉淀",
                folder_token=self._config.feishu_knowledge_folder_token,
            )
            app_token = self._extract_app_token(created)

        for table in KNOWLEDGE_TABLES:
            if tables.get(table.key):
                continue
            created_table = client.create_bitable_table(
                app_token=app_token,
                table_name=table.name,
                fields=table.fields,
            )
            tables[table.key] = self._extract_table_id(created_table)

        resources = {"app_token": app_token, "tables": tables}
        self._resource_store.save(resources)
        return resources

    @staticmethod
    def _extract_app_token(response: dict) -> str:
        data = response.get("data", {})
        candidates = [
            data.get("app_token"),
            data.get("app", {}).get("app_token") if isinstance(data.get("app"), dict) else "",
            data.get("bitable", {}).get("app_token") if isinstance(data.get("bitable"), dict) else "",
        ]
        for candidate in candidates:
            token = str(candidate or "").strip()
            if token:
                return token
        raise RuntimeError("飞书创建多维表格成功但没有返回 app_token")

    @staticmethod
    def _extract_table_id(response: dict) -> str:
        data = response.get("data", {})
        candidates = [
            data.get("table_id"),
            data.get("table", {}).get("table_id") if isinstance(data.get("table"), dict) else "",
        ]
        for candidate in candidates:
            table_id = str(candidate or "").strip()
            if table_id:
                return table_id
        raise RuntimeError("飞书创建数据表成功但没有返回 table_id")

    def _spreadsheet_row(self, trigger_msg: dict, messages: list[dict], summary) -> list[object]:
        start_ts = int(messages[0]["timestamp"])
        end_ts = int(messages[-1]["timestamp"])
        return [
            self._format_time(int(time.time())),
            trigger_msg.get("group_name") or trigger_msg.get("chat_id", ""),
            trigger_msg.get("sender_name", ""),
            self._format_time(start_ts),
            len(messages),
            summary.summary_text,
            ", ".join(summary.topics),
            self._format_time(end_ts),
        ]

    def _bitable_fields(self, trigger_msg: dict, messages: list[dict], summary) -> dict[str, object]:
        return {
            "同步时间": int(time.time() * 1000),
            "群聊": trigger_msg.get("group_name") or trigger_msg.get("chat_id", ""),
            "请求人": trigger_msg.get("sender_name", ""),
            "消息数": len(messages),
            "开始时间": int(messages[0]["timestamp"] * 1000),
            "结束时间": int(messages[-1]["timestamp"] * 1000),
            "主题": ", ".join(summary.topics),
            "摘要": summary.summary_text,
        }

    def _doc_title(self, trigger_msg: dict) -> str:
        group = trigger_msg.get("group_name") or trigger_msg.get("chat_id", "群聊")
        return f"{group} 群聊摘要 {self._format_time(int(time.time()), '%Y-%m-%d %H:%M')}"

    def _doc_markdown(self, trigger_msg: dict, messages: list[dict], summary) -> str:
        topics = ", ".join(summary.topics) if summary.topics else "无"
        group = trigger_msg.get("group_name") or trigger_msg.get("chat_id", "群聊")
        return "\n".join([
            f"# {group} 群聊摘要",
            f"- 同步时间：{self._format_time(int(time.time()), '%Y-%m-%d %H:%M:%S')}",
            f"- 请求人：{trigger_msg.get('sender_name', '')}",
            f"- 消息数：{len(messages)}",
            f"- 时间范围：{self._format_time(int(messages[0]['timestamp']))} - {self._format_time(int(messages[-1]['timestamp']))}",
            f"- 主题：{topics}",
            "",
            "## 摘要",
            summary.summary_text,
        ])

    @staticmethod
    def _format_time(timestamp: int, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
        return time.strftime(fmt, time.localtime(timestamp))
