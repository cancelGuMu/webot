"""Feishu knowledge-base resource schema and local persistence."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.config import PROJECT_ROOT


SUMMARY_TABLE_KEY = "summary"
TODO_TABLE_KEY = "todo"
REQUIREMENT_TABLE_KEY = "requirement"
DAILY_TABLE_KEY = "daily"


@dataclass(frozen=True)
class KnowledgeTable:
    key: str
    name: str
    fields: list[dict]


KNOWLEDGE_TABLES: tuple[KnowledgeTable, ...] = (
    KnowledgeTable(
        key=SUMMARY_TABLE_KEY,
        name="群聊摘要",
        fields=[
            {"field_name": "同步时间", "type": 5},
            {"field_name": "群聊", "type": 1},
            {"field_name": "请求人", "type": 1},
            {"field_name": "消息数", "type": 2},
            {"field_name": "开始时间", "type": 5},
            {"field_name": "结束时间", "type": 5},
            {"field_name": "主题", "type": 1},
            {"field_name": "摘要", "type": 1},
        ],
    ),
    KnowledgeTable(
        key=TODO_TABLE_KEY,
        name="待办",
        fields=[
            {"field_name": "创建时间", "type": 5},
            {"field_name": "群聊", "type": 1},
            {"field_name": "事项", "type": 1},
            {"field_name": "负责人", "type": 1},
            {"field_name": "截止时间", "type": 1},
            {"field_name": "状态", "type": 1},
            {"field_name": "来源", "type": 1},
        ],
    ),
    KnowledgeTable(
        key=REQUIREMENT_TABLE_KEY,
        name="需求",
        fields=[
            {"field_name": "创建时间", "type": 5},
            {"field_name": "群聊", "type": 1},
            {"field_name": "需求", "type": 1},
            {"field_name": "提出人", "type": 1},
            {"field_name": "优先级", "type": 1},
            {"field_name": "状态", "type": 1},
            {"field_name": "来源", "type": 1},
        ],
    ),
    KnowledgeTable(
        key=DAILY_TABLE_KEY,
        name="日常记录",
        fields=[
            {"field_name": "记录时间", "type": 5},
            {"field_name": "群聊", "type": 1},
            {"field_name": "记录", "type": 1},
            {"field_name": "分类", "type": 1},
            {"field_name": "参与人", "type": 1},
            {"field_name": "来源", "type": 1},
        ],
    ),
)


class FeishuResourceStore:
    """Persist generated Feishu Bitable resource ids under data/."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else PROJECT_ROOT / "data" / "feishu_resources.json"

    def load(self) -> dict:
        if not self.path.exists():
            return {"app_token": "", "tables": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"app_token": "", "tables": {}}
        tables = data.get("tables")
        if not isinstance(tables, dict):
            tables = {}
        return {
            "app_token": str(data.get("app_token", "")).strip(),
            "tables": {str(k): str(v) for k, v in tables.items()},
        }

    def save(self, resources: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        normalized = {
            "app_token": str(resources.get("app_token", "")).strip(),
            "tables": {
                str(k): str(v)
                for k, v in dict(resources.get("tables", {})).items()
                if str(v).strip()
            },
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)


class KnowledgeClassifier:
    """Small deterministic extractor for the first auto-knowledge pass."""

    TODO_RE = re.compile(r"(待办|todo|TODO|负责|截止|下周|明天|今天.*做|我来|你来)")
    REQUIREMENT_RE = re.compile(r"(需求|希望|需要|要支持|功能|PRD|用户故事|验收)")
    DAILY_RE = re.compile(r"(日常|记录|今天|日报|同步|进展|结论|决定|确认)")

    def classify(self, messages: Iterable[dict]) -> dict[str, list[dict]]:
        items = {
            TODO_TABLE_KEY: [],
            REQUIREMENT_TABLE_KEY: [],
            DAILY_TABLE_KEY: [],
        }
        for msg in messages:
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            source = self._source(msg, content)
            sender = str(msg.get("sender_name", "")).strip()
            group = str(msg.get("group_name") or msg.get("chat_id") or "").strip()
            ts_ms = int(msg.get("timestamp", 0) or 0) * 1000

            if self.TODO_RE.search(content):
                items[TODO_TABLE_KEY].append({
                    "创建时间": ts_ms,
                    "群聊": group,
                    "事项": content,
                    "负责人": self._owner_hint(content, sender),
                    "截止时间": self._deadline_hint(content),
                    "状态": "待处理",
                    "来源": source,
                })
            if self.REQUIREMENT_RE.search(content):
                items[REQUIREMENT_TABLE_KEY].append({
                    "创建时间": ts_ms,
                    "群聊": group,
                    "需求": content,
                    "提出人": sender,
                    "优先级": "未定",
                    "状态": "待评估",
                    "来源": source,
                })
            if self.DAILY_RE.search(content):
                items[DAILY_TABLE_KEY].append({
                    "记录时间": ts_ms,
                    "群聊": group,
                    "记录": content,
                    "分类": "日常",
                    "参与人": sender,
                    "来源": source,
                })
        return items

    @staticmethod
    def _source(msg: dict, content: str) -> str:
        sender = str(msg.get("sender_name", "")).strip() or "未知"
        return f"{sender}: {content[:240]}"

    @staticmethod
    def _owner_hint(content: str, sender: str) -> str:
        if "我来" in content:
            return sender
        return ""

    @staticmethod
    def _deadline_hint(content: str) -> str:
        for keyword in ("今天", "明天", "下周", "本周", "月底"):
            if keyword in content:
                return keyword
        return ""
