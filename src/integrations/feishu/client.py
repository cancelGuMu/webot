"""Feishu/Lark OpenAPI client.

Uses tenant_access_token from a self-built app.  The implementation stays on
Python stdlib HTTP so packaged builds do not need another network dependency.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable


class FeishuError(RuntimeError):
    """Raised when Feishu OpenAPI returns an error response."""


RequestJson = Callable[[str, str, dict | None, str | None, dict | None], dict]


class FeishuClient:
    """Small Feishu OpenAPI wrapper for the export feature."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        base_url: str = "https://open.feishu.cn",
        request_json: RequestJson | None = None,
        now: Callable[[], float] | None = None,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self._request_json = request_json or self._default_request_json
        self._now = now or time.time
        self._tenant_token = ""
        self._tenant_token_expires_at = 0.0

    def tenant_access_token(self) -> str:
        """Return a cached tenant_access_token, refreshing before expiry."""
        if self._tenant_token and self._tenant_token_expires_at - self._now() > 300:
            return self._tenant_token

        data = self._request_json(
            "POST",
            "/open-apis/auth/v3/tenant_access_token/internal",
            {
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            },
            None,
            None,
        )
        self._raise_for_error(data)
        token = str(data.get("tenant_access_token", "")).strip()
        if not token:
            raise FeishuError("Feishu tenant_access_token response is missing token")
        expire = int(data.get("expire", 7200))
        self._tenant_token = token
        self._tenant_token_expires_at = self._now() + max(expire, 0)
        return token

    def append_spreadsheet_rows(
        self,
        spreadsheet_token: str,
        range_name: str,
        rows: list[list[object]],
    ) -> dict:
        """Append rows to a Feishu spreadsheet."""
        data = self._request_json(
            "POST",
            f"/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values_append",
            {
                "valueRange": {
                    "range": range_name,
                    "values": rows,
                },
            },
            self.tenant_access_token(),
            {"insertDataOption": "INSERT_ROWS"},
        )
        self._raise_for_error(data)
        return data

    def create_bitable_record(
        self,
        app_token: str,
        table_id: str,
        fields: dict[str, object],
    ) -> dict:
        """Create a single Feishu Bitable record."""
        data = self._request_json(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            {"fields": fields},
            self.tenant_access_token(),
            None,
        )
        self._raise_for_error(data)
        return data

    def create_bitable_app(self, name: str, folder_token: str = "") -> dict:
        """Create a Feishu Bitable app and return the API response."""
        body: dict[str, object] = {"name": name}
        if folder_token:
            body["folder_token"] = folder_token
        data = self._request_json(
            "POST",
            "/open-apis/bitable/v1/apps",
            body,
            self.tenant_access_token(),
            None,
        )
        self._raise_for_error(data)
        return data

    def create_bitable_table(
        self,
        app_token: str,
        table_name: str,
        fields: list[dict],
    ) -> dict:
        """Create a Bitable table with the fields used by webot."""
        data = self._request_json(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables",
            {
                "table": {
                    "name": table_name,
                    "default_view_name": "默认视图",
                },
                "fields": fields,
            },
            self.tenant_access_token(),
            None,
        )
        self._raise_for_error(data)
        return data

    def create_docx_document(self, title: str, folder_token: str = "") -> dict:
        """Create a Feishu docx document and return the API response."""
        body: dict[str, object] = {"title": title}
        if folder_token:
            body["folder_token"] = folder_token
        data = self._request_json(
            "POST",
            "/open-apis/docx/v1/documents",
            body,
            self.tenant_access_token(),
            None,
        )
        self._raise_for_error(data)
        return data

    def create_docx_blocks(
        self,
        document_id: str,
        block_id: str,
        children: list[dict],
    ) -> dict:
        """Append child blocks under a docx block."""
        data = self._request_json(
            "POST",
            f"/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/children",
            {"children": children},
            self.tenant_access_token(),
            None,
        )
        self._raise_for_error(data)
        return data

    def create_docx_with_markdown(
        self,
        title: str,
        markdown: str,
        folder_token: str = "",
    ) -> dict:
        """Create a docx document and write markdown-like text as paragraphs."""
        created = self.create_docx_document(title=title, folder_token=folder_token)
        document = created.get("data", {}).get("document", {})
        document_id = str(document.get("document_id", "")).strip()
        if not document_id:
            raise FeishuError("Feishu create document response is missing document_id")

        children = self._markdown_to_text_blocks(markdown)
        if children:
            self.create_docx_blocks(document_id, document_id, children)
        return created

    @staticmethod
    def _markdown_to_text_blocks(markdown: str) -> list[dict]:
        """Convert simple markdown text to Feishu text block payloads."""
        blocks: list[dict] = []
        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            text = line.lstrip("#").strip() if line.startswith("#") else line
            blocks.append({
                "block_type": 2,
                "text": {
                    "elements": [
                        {
                            "text_run": {
                                "content": text,
                            }
                        }
                    ],
                    "style": {},
                },
            })
        return blocks

    def _default_request_json(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        token: str | None = None,
        query: dict | None = None,
    ) -> dict:
        query_string = ""
        if query:
            query_string = "?" + urllib.parse.urlencode(query)
        url = self.base_url + path + query_string
        payload = json.dumps(body or {}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=payload, method=method)
        request.add_header("Content-Type", "application/json; charset=utf-8")
        if token:
            request.add_header("Authorization", f"Bearer {token}")

        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise FeishuError(f"Feishu HTTP {e.code}: {raw}") from e
        except urllib.error.URLError as e:
            raise FeishuError(f"Feishu request failed: {e}") from e

        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError as e:
            raise FeishuError(f"Feishu returned invalid JSON: {raw[:200]}") from e

    @staticmethod
    def _raise_for_error(data: dict) -> None:
        code = data.get("code", 0)
        if code not in (0, None):
            msg = data.get("msg") or data.get("message") or "unknown error"
            raise FeishuError(f"Feishu OpenAPI error {code}: {msg}")
