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
PROJECT_TABLE_KEY = "project"

FEISHU_COMMAND_KEYWORDS = ("同步到飞书", "导出到飞书", "写到飞书", "沉淀到飞书")
_INVISIBLE_SPACE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff\u2005]")


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
    KnowledgeTable(
        key=PROJECT_TABLE_KEY,
        name="项目",
        fields=[
            {"field_name": "创建时间", "type": 5},
            {"field_name": "群聊", "type": 1},
            {"field_name": "项目", "type": 1},
            {"field_name": "阶段", "type": 1},
            {"field_name": "负责人", "type": 1},
            {"field_name": "协作人", "type": 1},
            {"field_name": "角色分工", "type": 1},
            {"field_name": "提出人", "type": 1},
            {"field_name": "来源", "type": 1},
        ],
    ),
)


def strip_feishu_sync_command(content: str, bot_display_name: str = "") -> str:
    """Remove Feishu sync command fragments while preserving useful message text."""
    text = _INVISIBLE_SPACE_RE.sub(" ", str(content or "")).replace("\r\n", "\n")
    if bot_display_name:
        text = re.sub(
            re.escape(f"@{bot_display_name}") + r"[^\w\n]*",
            "",
            text,
        )

    cleaned_lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(keyword.lower() in line.lower() for keyword in FEISHU_COMMAND_KEYWORDS):
            for keyword in FEISHU_COMMAND_KEYWORDS:
                line = re.sub(re.escape(keyword), "", line, flags=re.IGNORECASE)
            line = re.sub(r"@\S+", "", line)
            line = line.strip(" \t,，.。;；:：")
        if line:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


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
        try:
            tmp.write_text(
                json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            tmp.replace(self.path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise


@dataclass(frozen=True)
class _ProjectItem:
    name: str
    stage: str
    owners: str
    collaborators: str
    role_text: str
    source_text: str


class KnowledgeClassifier:
    """Extract structured knowledge instead of dumping raw chat into tables."""

    TODO_RE = re.compile(r"(待办|todo|TODO|负责|截止|下周|明天|今天.*做|我来|你来)")
    REQUIREMENT_RE = re.compile(r"(需求|希望|需要|要支持|功能|PRD|用户故事|验收)")
    DAILY_RE = re.compile(r"(日常|记录|今天|日报|进展|结论|决定|确认)")
    BULLET_RE = re.compile(r"^\s*(?:[-*•]\s*|(?:\d+|[一二三四五六七八九十]+)[\.、)）]\s*)(.+?)\s*$")
    PROJECT_OWNER_ROLES = ("开发", "负责", "负责人", "产品", "主R", "owner", "Owner")
    TODO_ROLES = (
        "开发", "宣传", "设计", "测试", "运营", "产品", "文案", "调研",
        "对接", "跟进", "整理", "撰写", "落地", "负责",
    )

    def classify(self, messages: Iterable[dict]) -> dict[str, list[dict]]:
        items = {
            TODO_TABLE_KEY: [],
            REQUIREMENT_TABLE_KEY: [],
            DAILY_TABLE_KEY: [],
            PROJECT_TABLE_KEY: [],
        }
        for msg in messages:
            content = strip_feishu_sync_command(str(msg.get("content", "")).strip())
            if not content:
                continue
            source = self._source(msg, content)
            sender = str(msg.get("sender_name", "")).strip()
            group = str(msg.get("group_name") or msg.get("chat_id") or "").strip()
            ts_ms = int(msg.get("timestamp", 0) or 0) * 1000

            projects = self._extract_projects(content)
            if projects:
                self._append_project_records(items, projects, group, sender, ts_ms, source)
                continue

            section_items = self._extract_section_items(content)
            if section_items:
                self._append_section_records(items, section_items, group, sender, ts_ms, source)
                continue

            for chunk in self._semantic_chunks(content):
                chunk_source = self._source(msg, chunk)
                if self.TODO_RE.search(chunk):
                    items[TODO_TABLE_KEY].append({
                        "创建时间": ts_ms,
                        "群聊": group,
                        "事项": self._compact_text(chunk),
                        "负责人": self._owner_hint(chunk, sender),
                        "截止时间": self._deadline_hint(chunk),
                        "状态": "待处理",
                        "来源": chunk_source,
                    })
                if self.REQUIREMENT_RE.search(chunk):
                    items[REQUIREMENT_TABLE_KEY].append({
                        "创建时间": ts_ms,
                        "群聊": group,
                        "需求": self._compact_text(chunk),
                        "提出人": sender,
                        "优先级": "未定",
                        "状态": "待评估",
                        "来源": chunk_source,
                    })
                if self.DAILY_RE.search(chunk):
                    items[DAILY_TABLE_KEY].append({
                        "记录时间": ts_ms,
                        "群聊": group,
                        "记录": self._compact_text(chunk),
                        "分类": "日常",
                        "参与人": sender,
                        "来源": chunk_source,
                    })
        return items

    def _append_project_records(
        self,
        items: dict[str, list[dict]],
        projects: list[_ProjectItem],
        group: str,
        sender: str,
        ts_ms: int,
        source: str,
    ) -> None:
        stage_counts: dict[str, int] = {}
        for project in projects:
            stage_counts[project.stage] = stage_counts.get(project.stage, 0) + 1
            item_source = f"{sender}: {project.source_text[:240]}" if sender else project.source_text[:240]
            items[PROJECT_TABLE_KEY].append({
                "创建时间": ts_ms,
                "群聊": group,
                "项目": project.name,
                "阶段": project.stage,
                "负责人": project.owners,
                "协作人": project.collaborators,
                "角色分工": project.role_text,
                "提出人": sender,
                "来源": item_source,
            })
            items[REQUIREMENT_TABLE_KEY].append({
                "创建时间": ts_ms,
                "群聊": group,
                "需求": project.name,
                "提出人": sender,
                "优先级": "未定",
                "状态": project.stage,
                "来源": item_source,
            })
            for todo in self._project_todos(project):
                items[TODO_TABLE_KEY].append({
                    "创建时间": ts_ms,
                    "群聊": group,
                    "事项": todo["事项"],
                    "负责人": todo["负责人"],
                    "截止时间": "",
                    "状态": self._todo_status_for_stage(project.stage),
                    "来源": item_source,
                })

        count_text = "；".join(f"{stage} {count} 个" for stage, count in stage_counts.items())
        items[DAILY_TABLE_KEY].append({
            "记录时间": ts_ms,
            "群聊": group,
            "记录": f"项目台账更新：{count_text}。",
            "分类": "项目进展",
            "参与人": sender,
            "来源": source,
        })

    def _append_section_records(
        self,
        items: dict[str, list[dict]],
        section_items: list[tuple[str, str]],
        group: str,
        sender: str,
        ts_ms: int,
        source: str,
    ) -> None:
        for kind, text in section_items:
            source_text = f"{sender}: {text[:240]}" if sender else text[:240]
            if kind == TODO_TABLE_KEY:
                items[TODO_TABLE_KEY].append({
                    "创建时间": ts_ms,
                    "群聊": group,
                    "事项": self._compact_text(text),
                    "负责人": self._owner_hint(text, sender),
                    "截止时间": self._deadline_hint(text),
                    "状态": "待处理",
                    "来源": source_text,
                })
            elif kind == REQUIREMENT_TABLE_KEY:
                items[REQUIREMENT_TABLE_KEY].append({
                    "创建时间": ts_ms,
                    "群聊": group,
                    "需求": self._compact_text(text),
                    "提出人": sender,
                    "优先级": "未定",
                    "状态": "待评估",
                    "来源": source_text,
                })
            elif kind == DAILY_TABLE_KEY:
                items[DAILY_TABLE_KEY].append({
                    "记录时间": ts_ms,
                    "群聊": group,
                    "记录": self._compact_text(text),
                    "分类": "日常",
                    "参与人": sender,
                    "来源": source_text,
                })

    @staticmethod
    def _source(msg: dict, content: str) -> str:
        sender = str(msg.get("sender_name", "")).strip() or "未知"
        return f"{sender}: {content[:240]}"

    def _extract_projects(self, content: str) -> list[_ProjectItem]:
        projects: list[_ProjectItem] = []
        current_stage = ""
        for line in self._lines(content):
            stage = self._project_stage(line)
            if stage:
                current_stage = stage
                continue
            item_text = self._bullet_text(line)
            if not current_stage or not item_text:
                continue
            projects.append(self._parse_project_item(item_text, current_stage))
        return projects

    def _extract_section_items(self, content: str) -> list[tuple[str, str]]:
        section_items: list[tuple[str, str]] = []
        current_kind = ""
        for line in self._lines(content):
            kind = self._section_kind(line)
            if kind:
                current_kind = kind
                continue
            item_text = self._bullet_text(line)
            if current_kind and item_text:
                section_items.append((current_kind, item_text))
        return section_items

    @classmethod
    def _lines(cls, content: str) -> list[str]:
        return [line.strip() for line in content.splitlines() if line.strip()]

    @classmethod
    def _bullet_text(cls, line: str) -> str:
        match = cls.BULLET_RE.match(line)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _project_stage(line: str) -> str:
        normalized = line.strip().rstrip(":：")
        if "项目" not in normalized and "app" not in normalized.lower():
            return ""
        if any(keyword in normalized for keyword in ("待开发", "待做", "待启动")):
            return "待开发"
        if any(keyword in normalized for keyword in ("开发中", "进行中", "在做")):
            return "开发中"
        if any(keyword in normalized for keyword in ("已上线", "已发布", "已完成", "完成")):
            return "已完成"
        if any(keyword in normalized for keyword in ("待评估", "规划", "想法", "候选", "储备")):
            return "待评估"
        if any(keyword in normalized for keyword in ("暂停", "搁置")):
            return "搁置"
        return ""

    @staticmethod
    def _section_kind(line: str) -> str:
        normalized = line.strip().lower().rstrip(":：")
        if normalized in ("待办", "todo", "todos", "行动项", "待处理事项"):
            return TODO_TABLE_KEY
        if normalized in ("需求", "需求池", "待开发需求", "功能需求", "想法"):
            return REQUIREMENT_TABLE_KEY
        if normalized in ("日常", "日常记录", "今日进展", "进展", "结论", "决定"):
            return DAILY_TABLE_KEY
        return ""

    def _parse_project_item(self, item_text: str, stage: str) -> _ProjectItem:
        name, meta = self._split_project_meta(item_text)
        assignments = self._role_assignments(meta)
        collaborators = self._join_people([
            person
            for assignment in assignments
            for person in assignment["people"]
        ])
        owners = self._join_people([
            person
            for assignment in assignments
            if self._role_has_any(assignment["roles"], self.PROJECT_OWNER_ROLES)
            for person in assignment["people"]
        ])
        role_text = "；".join(
            f"{assignment['display_role']}：{self._join_people(assignment['people'])}"
            for assignment in assignments
            if assignment["people"]
        )
        return _ProjectItem(
            name=name,
            stage=stage,
            owners=owners,
            collaborators=collaborators,
            role_text=role_text,
            source_text=item_text,
        )

    @staticmethod
    def _split_project_meta(item_text: str) -> tuple[str, str]:
        text = item_text.strip()
        match = re.match(r"^(?P<name>.+?)[（(](?P<meta>[^（）()]+)[）)]\s*$", text)
        if not match:
            return text, ""
        return match.group("name").strip(), match.group("meta").strip()

    def _role_assignments(self, meta: str) -> list[dict]:
        assignments = []
        if not meta:
            return assignments
        for raw_part in re.split(r"[;；]", meta):
            part = raw_part.strip()
            if not part:
                continue
            if "：" in part:
                role_text, people_text = part.split("：", 1)
            elif ":" in part:
                role_text, people_text = part.split(":", 1)
            else:
                role_text, people_text = "参与", part
            display_role = role_text.strip() or "参与"
            roles = [role.strip() for role in re.split(r"[+＋/、,，和及与&]", display_role) if role.strip()]
            assignments.append({
                "display_role": display_role,
                "roles": roles or [display_role],
                "people": self._people(people_text),
            })
        return assignments

    @staticmethod
    def _people(text: str) -> list[str]:
        people = []
        for part in re.split(r"[+＋/、,，和及与&\s]+", text.strip()):
            name = part.strip("()（）[]【】 ")
            if name and name not in people:
                people.append(name)
        return people

    @classmethod
    def _join_people(cls, people: list[str]) -> str:
        unique = []
        for person in people:
            if person and person not in unique:
                unique.append(person)
        return "、".join(unique)

    @staticmethod
    def _role_has_any(roles: list[str], keywords: tuple[str, ...]) -> bool:
        return any(keyword in role for role in roles for keyword in keywords)

    def _project_todos(self, project: _ProjectItem) -> list[dict[str, str]]:
        todos = []
        for assignment in self._role_assignments(project.role_text):
            todo_role = self._todo_role(assignment["roles"])
            if not todo_role or not assignment["people"]:
                continue
            todos.append({
                "事项": f"{todo_role}：{project.name}",
                "负责人": self._join_people(assignment["people"]),
            })
        return todos

    def _todo_role(self, roles: list[str]) -> str:
        for role in roles:
            for keyword in self.TODO_ROLES:
                if keyword in role:
                    return keyword
        return ""

    @staticmethod
    def _todo_status_for_stage(stage: str) -> str:
        if stage == "开发中":
            return "进行中"
        if stage == "已完成":
            return "已完成"
        if stage == "搁置":
            return "已暂停"
        return "待处理"

    @staticmethod
    def _semantic_chunks(content: str) -> list[str]:
        chunks = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            pieces = [part.strip() for part in re.split(r"[。！？!?]\s*", line) if part.strip()]
            chunks.extend(pieces or [line])
        return chunks

    @staticmethod
    def _compact_text(content: str) -> str:
        return re.sub(r"\s+", " ", content).strip()

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
