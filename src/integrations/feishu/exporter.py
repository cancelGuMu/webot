"""Export WeChat summaries to Feishu/Lark documents or tables."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .client import FeishuClient


@dataclass
class FeishuExportResult:
    ok: bool
    reply_text: str
    response: dict | None = None


class FeishuExportService:
    """Coordinates message lookup, AI summarization, and Feishu writes."""

    def __init__(self, config, store, summarizer, client: FeishuClient | None = None):
        self._config = config
        self._store = store
        self._summarizer = summarizer
        self._client = client

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
        messages = self._store.get_messages_since(
            trigger_msg["chat_id"],
            since_ts,
            until_ts=trigger_ts,
            limit=self._config.max_messages_for_summary,
        )
        messages = [
            m for m in messages
            if m.get("message_id") != trigger_msg.get("message_id")
            and str(m.get("content", "")).strip()
        ]
        if not messages:
            return FeishuExportResult(
                ok=False,
                reply_text=f"@{requester} 最近没有可同步的群聊内容。",
            )

        summary = self._summarizer.summarize(messages, requester)
        client = self._get_client()
        mode = self._config.feishu_export_mode
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
