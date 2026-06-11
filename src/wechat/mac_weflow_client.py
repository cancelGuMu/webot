"""macOS WeFlow-style WCDB reader.

This client mirrors the part of WeFlow we need for webot: use the stable
``@chatroom`` id as the target key, then resolve display names from WeChat's
local WCDB contact data.  It intentionally exposes the same small shape the
macOS backend already consumes: new messages, sessions, chatrooms and contacts.
"""

from __future__ import annotations

import ctypes as ct
import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

HEX_KEY_LEN = 64
DEFAULT_LIMIT = 200


class MacWeFlowClient:
    """Direct macOS WCDB client using WeFlow's native data library."""

    def __init__(
        self,
        data_dir: str | None = None,
        lib_dir: str | None = None,
        timeout: float = 5.0,
        sqlite_reader=None,
        config=None,
    ):
        self.data_dir = str(data_dir or "").strip()
        self.lib_dir = str(lib_dir or "").strip()
        self.timeout = timeout
        self._sqlite_reader = sqlite_reader
        self._opened_data_dir = ""
        self._chat_title_cache: dict[str, str] = {}
        self._display_name_cache: dict[str, str] = {}
        self._message_db_cache: dict[str, str] = {}
        self._last_error = ""
        # Voice recognition (lazy-init)
        self._voice: object | None = None
        self._voice_config = config

    def health(self) -> bool:
        try:
            return self._ensure_open()
        except Exception as exc:
            self._last_error = str(exc)
            logger.debug("macOS WeFlow health failed: %s", exc)
            return False

    def get_new_messages(
        self,
        state: dict[str, int] | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> dict:
        if not self._ensure_open():
            raise RuntimeError(self._last_error or "macOS WeFlow client is not ready")

        safe_limit = max(1, int(limit or DEFAULT_LIMIT))
        old_state = {
            str(k): int(v)
            for k, v in (state or {}).items()
            if _can_int(v)
        }
        sessions = self._session_rows(limit=500)
        group_sessions = [
            row for row in sessions
            if str(row.get("username") or row.get("user_name") or row.get("userName") or "").endswith("@chatroom")
        ]
        ids = [
            str(row.get("username") or row.get("user_name") or row.get("userName") or "").strip()
            for row in group_sessions
        ]
        self._hydrate_group_titles(ids)

        new_state: dict[str, int] = {}
        changed: list[str] = []
        fallback = int(time.time()) - 24 * 3600
        for row in group_sessions:
            username = str(row.get("username") or row.get("user_name") or row.get("userName") or "").strip()
            if not username:
                continue
            ts = _first_int(row, ("last_timestamp", "lastTimestamp", "sort_timestamp", "sortTimestamp"))
            if ts <= 0:
                ts = fallback
            new_state[username] = ts
            if ts > old_state.get(username, fallback):
                changed.append(username)

        out: list[dict[str, Any]] = []
        for username in changed:
            last = old_state.get(username, fallback)
            rows = self._message_rows(username, limit=safe_limit * 3, offset=0)
            for row in rows:
                normalized = self._message_to_source_row(username, row)
                if not normalized:
                    continue
                if int(normalized.get("timestamp") or 0) <= last:
                    continue
                out.append(normalized)
                if len(out) >= safe_limit:
                    break
            if len(out) >= safe_limit:
                break

        out.sort(key=lambda item: int(item.get("timestamp") or 0))
        return {
            "count": len(out),
            "messages": out,
            "new_state": new_state,
        }

    def get_sessions(self, limit: int = 500) -> dict:
        if not self._ensure_open():
            raise RuntimeError(self._last_error or "macOS WeFlow client is not ready")
        rows = self._session_rows(limit=limit)
        ids = [
            str(row.get("username") or row.get("user_name") or row.get("userName") or "").strip()
            for row in rows
        ]
        self._hydrate_group_titles([item for item in ids if item.endswith("@chatroom")])
        sessions = []
        for row in rows[: max(1, int(limit or 500))]:
            username = str(row.get("username") or row.get("user_name") or row.get("userName") or "").strip()
            if not username:
                continue
            display = self._chat_title_cache.get(username) or self._display_name_cache.get(username) or username
            is_group = username.endswith("@chatroom")
            sessions.append({
                **row,
                "username": username,
                "chat": display,
                "display": display,
                "nickname": display,
                "is_group": is_group,
                "chat_type": "group" if is_group else "private",
            })
        return {"count": len(sessions), "sessions": sessions}

    def get_chatrooms(self, limit: int = 500) -> dict:
        if not self._ensure_open():
            raise RuntimeError(self._last_error or "macOS WeFlow client is not ready")
        contact_rows = self._contact_rows()
        chatrooms = []
        for row in contact_rows:
            username = str(row.get("username") or row.get("userName") or row.get("user_name") or "").strip()
            if not username.endswith("@chatroom"):
                continue
            display = _display_name_from_row(row) or username
            self._remember_title(username, display)
            chatrooms.append({
                "name": username,
                "username": username,
                "display": display,
                "remark": str(row.get("remark") or row.get("Remark") or "").strip(),
                "nickname": str(
                    row.get("nick_name")
                    or row.get("nickName")
                    or row.get("nickname")
                    or row.get("NickName")
                    or ""
                ).strip(),
            })
        if not chatrooms:
            for row in self.get_sessions(limit=limit).get("sessions", []):
                username = str(row.get("username") or "").strip()
                if not username.endswith("@chatroom"):
                    continue
                display = str(row.get("display") or row.get("chat") or username).strip()
                chatrooms.append({
                    "name": username,
                    "username": username,
                    "display": display,
                    "remark": "",
                    "nickname": display if display != username else "",
                })
        return {"count": len(chatrooms), "chatrooms": chatrooms[: max(1, int(limit or 500))]}

    def get_contacts(self, limit: int = 500) -> dict:
        if not self._ensure_open():
            raise RuntimeError(self._last_error or "macOS WeFlow client is not ready")
        contacts = []
        for row in self._contact_rows()[: max(1, int(limit or 500))]:
            username = str(row.get("username") or row.get("userName") or row.get("user_name") or "").strip()
            if not username:
                continue
            display = _display_name_from_row(row) or username
            self._display_name_cache[username] = display
            contacts.append({
                "username": username,
                "name": username,
                "display": display,
                "remark": str(row.get("remark") or row.get("Remark") or "").strip(),
                "nickname": str(
                    row.get("nick_name")
                    or row.get("nickName")
                    or row.get("nickname")
                    or row.get("NickName")
                    or ""
                ).strip(),
                "alias": str(row.get("alias") or row.get("Alias") or "").strip(),
            })
        return {"count": len(contacts), "contacts": contacts}

    def _ensure_open(self) -> bool:
        if self._sqlite_reader is not None:
            health = getattr(self._sqlite_reader, "health", None)
            if callable(health) and not health():
                self._last_error = getattr(self._sqlite_reader, "last_error", "macOS WeFlow SQLite reader is not ready")
                return False
            return True

        if platform.system() != "Darwin":
            self._last_error = "MacWeFlowClient is only available on macOS"
            return False

        lib_dir = self._resolve_lib_dir()
        data_dir = self._resolve_data_dir()
        if not lib_dir:
            self._last_error = "WeFlow WCDB library not found"
            return False
        if not data_dir:
            self._last_error = "WeChat account data dir not found"
            return False

        session_db = Path(data_dir) / "db_storage" / "session" / "session.db"
        if not session_db.exists():
            self._last_error = f"session.db not found: {session_db}"
            return False

        try:
            reader = _WCDBSQLiteReader(data_dir=data_dir, lib_dir=lib_dir)
            if not reader.health():
                self._last_error = reader.last_error
                return False
            self._sqlite_reader = reader
            self._opened_data_dir = data_dir
            return True
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("Failed to open macOS WeFlow WCDB client: %s", exc)
            return False

    def _session_rows(self, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._reader().query(
            "session/session.db",
            "SELECT * FROM SessionTable ORDER BY sort_timestamp DESC, last_timestamp DESC",
        )
        rows = [row for row in rows if isinstance(row, dict)]
        return rows[: max(1, int(limit or 500))]

    def _message_rows(self, username: str, limit: int, offset: int) -> list[dict[str, Any]]:
        table = "Msg_" + hashlib.md5(username.encode("utf-8")).hexdigest()
        db_rel = self._message_db_for_table(table)
        if not db_rel:
            return []
        rows = self._reader().query(
            db_rel,
            (
                "SELECT m.local_id, m.server_id, m.local_type, m.sort_seq, "
                "m.real_sender_id, m.create_time, m.status, m.source, "
                "m.message_content, m.compress_content, m.WCDB_CT_message_content, "
                "m.WCDB_CT_source, n.user_name AS senderUsername "
                f"FROM {_sql_ident(table)} m "
                "LEFT JOIN Name2Id n ON n.rowid = m.real_sender_id "
                "WHERE m.local_type = 1 "
                "ORDER BY m.create_time DESC, m.local_id DESC "
                f"LIMIT {max(1, int(limit or DEFAULT_LIMIT))} OFFSET {max(0, int(offset or 0))}"
            ),
        )
        rows = [row for row in rows if isinstance(row, dict)]
        rows.sort(key=lambda row: (_first_int(row, ("createTime", "create_time", "timestamp")), _first_int(row, ("localId", "local_id"))))
        return rows

    def _contact_rows(self) -> list[dict[str, Any]]:
        return self._reader().query(
            "contact/contact.db",
            "SELECT * FROM contact WHERE username IS NOT NULL AND username != ''",
        )

    def _display_names(self, usernames: list[str]) -> dict[str, str]:
        clean = [str(item).strip() for item in usernames if str(item).strip()]
        if not clean:
            return {}
        rows = self._reader().query(
            "contact/contact.db",
            "SELECT * FROM contact WHERE username IN ("
            + ",".join(_sql_quote(item) for item in clean)
            + ")",
        )
        out: dict[str, str] = {}
        for row in rows:
            username = str(row.get("username") or row.get("userName") or row.get("user_name") or "").strip()
            display = _display_name_from_row(row) or username
            if username and display:
                out[username] = display
                self._display_name_cache[username] = display
        for username in clean:
            out.setdefault(username, username)
        return out

    def _hydrate_group_titles(self, usernames: list[str]) -> None:
        missing = [
            str(username).strip()
            for username in usernames
            if str(username).strip().endswith("@chatroom")
            and str(username).strip() not in self._chat_title_cache
        ]
        if not missing:
            return

        for row in self._contact_rows():
            username = str(row.get("username") or row.get("userName") or row.get("user_name") or "").strip()
            if username in missing:
                self._remember_title(username, _display_name_from_row(row) or username)

        still_missing = [username for username in missing if username not in self._chat_title_cache]
        if still_missing:
            for username, display in self._display_names(still_missing).items():
                self._remember_title(username, display)

    def _remember_title(self, username: str, title: str) -> None:
        username = str(username or "").strip()
        title = str(title or "").strip()
        if username and title:
            self._chat_title_cache[username] = title
            self._display_name_cache[username] = title

    def _hydrate_contact_names(self, usernames: list[str]) -> None:
        missing = [
            str(username).strip()
            for username in usernames
            if str(username).strip() and str(username).strip() not in self._display_name_cache
        ]
        if missing:
            self._display_names(missing)

    def _message_db_for_table(self, table: str) -> str:
        cached = self._message_db_cache.get(table, "")
        if cached:
            return cached
        rels = getattr(self._reader(), "message_db_rels", lambda: [])()
        for rel in rels:
            rows = self._reader().query(
                rel,
                "SELECT name FROM sqlite_master WHERE type='table' AND name="
                + _sql_quote(table)
                + " LIMIT 1",
            )
            if rows:
                self._message_db_cache[table] = rel
                return rel
        return ""

    def _message_to_source_row(self, chat_id: str, row: dict[str, Any]) -> dict[str, Any] | None:
        is_send = _first_int(row, ("isSend", "is_send"), default=-1)
        if is_send < 0:
            status = _first_int(row, ("status",), default=0)
            is_send = 1 if status == 2 else 0
        if is_send == 1:
            return None
        ts = _first_int(row, ("createTime", "create_time", "timestamp"))
        if ts <= 0:
            return None
        local_id = _first_int(row, ("localId", "local_id"), default=0)
        local_type = _first_int(row, ("localType", "local_type"), default=1)
        sender = str(
            row.get("senderUsername")
            or row.get("sender_username")
            or row.get("sender")
            or ""
        ).strip()
        content = str(
            row.get("parsedContent")
            or row.get("parsed_content")
            or row.get("rawContent")
            or row.get("message_content")
            or row.get("content")
            or ""
        ).strip()
        sender, content = _split_group_message_sender(sender, content)
        if local_type != 1:
            if local_type == 34:
                voice_text = self._try_voice(row)
                if voice_text:
                    content = f"[语音] {voice_text}"
                else:
                    content = _message_type_label(local_type)
            else:
                content = _message_type_label(local_type)
        elif _looks_corrupt_text(content):
            return None
        if not content:
            content = _message_type_label(local_type)
        display = self._chat_title_cache.get(chat_id) or chat_id
        if sender:
            self._hydrate_contact_names([sender])
        sender_display = self._display_name_cache.get(sender) or sender or "unknown"
        return {
            "timestamp": ts,
            "sender": sender_display,
            "sender_name": sender_display,
            "sender_id": sender or sender_display,
            "type": _message_type_name(local_type),
            "content": content,
            "local_id": local_id,
            "chat": display,
            "username": chat_id,
            "is_group": chat_id.endswith("@chatroom"),
            "chat_type": "group" if chat_id.endswith("@chatroom") else "private",
        }

    # ── Voice recognition helpers ────────────────────────────────────

    def _get_voice(self):
        """Lazy-init VoicePipeline."""
        if self._voice is not None:
            return self._voice
        if self._voice_config is None:
            self._voice = False
            return False
        try:
            from src.voice import VoicePipeline
            self._voice = VoicePipeline(self._voice_config)
        except Exception:
            logger.exception("VoicePipeline init failed — voice disabled")
            self._voice = False
        return self._voice

    def _try_voice(self, msg: dict) -> Optional[str]:
        """Attempt voice recognition; return text or None."""
        voice = self._get_voice()
        if not voice:
            return None
        try:
            return voice.process(msg)
        except Exception:
            logger.exception("VoicePipeline.process failed")
            return None

    def _resolve_lib_dir(self) -> str:
        if self.lib_dir:
            return self.lib_dir
        candidates: list[Path] = []
        for env_name in ("MAC_WEFLOW_WCDB_LIB_DIR", "WEFLOW_WCDB_LIB_DIR"):
            raw = os.getenv(env_name, "").strip()
            if raw:
                candidates.append(Path(raw).expanduser())
        roots = []
        if getattr(sys, "frozen", False):
            roots.extend([
                Path(sys.executable).resolve().parent,
                Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)),
            ])
        root = Path(__file__).resolve().parent.parent.parent
        roots.extend([root, Path.cwd()])
        for base in roots:
            candidates.extend([
                base / "lib" / "macos",
                base / "resources" / "wcdb" / "macos" / "universal",
            ])
        for candidate in _unique_paths(candidates):
            if (candidate / "libWCDB.dylib").exists():
                return str(candidate)
        return ""

    def _resolve_data_dir(self) -> str:
        if self.data_dir:
            resolved = _normalize_data_dir(self.data_dir)
            if resolved:
                return resolved
        for env_name in ("MAC_WEFLOW_DATA_DIR", "WECHAT_DATA_DIR"):
            raw = os.getenv(env_name, "").strip()
            if raw:
                resolved = _normalize_data_dir(raw)
                if resolved:
                    return resolved
        detected = _detect_wechat_data_dir()
        return detected

    def _reader(self):
        if self._sqlite_reader is None:
            raise RuntimeError("macOS WeFlow SQLite reader is not open")
        return self._sqlite_reader

    def close(self) -> None:
        close_reader = getattr(self._sqlite_reader, "close", None)
        if callable(close_reader):
            close_reader()
        self._sqlite_reader = None
        self._opened_data_dir = ""


class _WCDBSQLiteReader:
    """Read encrypted macOS WeChat SQLite databases through WeFlow's WCDB dylib."""

    _OPEN_READONLY = 0x00000001
    _OPEN_FULLMUTEX = 0x00010000

    def __init__(self, data_dir: str, lib_dir: str):
        self.data_dir = Path(data_dir)
        self.lib_dir = Path(lib_dir)
        self.last_error = ""
        self._keys: dict[str, str] | None = None
        self._lib = self._load_sqlite_lib()

    def health(self) -> bool:
        try:
            self.query("session/session.db", "SELECT name FROM sqlite_master LIMIT 1")
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def close(self) -> None:
        return None

    def message_db_rels(self) -> list[str]:
        root = self.data_dir / "db_storage" / "message"
        if not root.exists():
            return []
        rels = []
        for path in sorted(root.glob("*.db")):
            rels.append("message/" + path.name)
        return rels

    def query(self, db_rel: str, sql: str) -> list[dict[str, Any]]:
        db_path = self.data_dir / "db_storage" / db_rel
        if not db_path.exists():
            raise RuntimeError(f"WeFlow database not found: {db_rel}")
        key = self._key_for(db_rel)
        db = ct.c_void_p()
        rc = int(self._lib.sqlite3_open_v2(
            str(db_path).encode("utf-8"),
            ct.byref(db),
            self._OPEN_READONLY | self._OPEN_FULLMUTEX,
            None,
        ))
        if rc != 0 or not db.value:
            raise RuntimeError(f"sqlite open failed for {db_rel}: {rc}")
        try:
            key_expr = f"x'{key}'".encode("ascii")
            rc = int(self._lib.sqlite3_key(db, key_expr, len(key_expr)))
            if rc != 0:
                raise RuntimeError(f"sqlite key failed for {db_rel}: {rc}")

            rows: list[dict[str, Any]] = []

            def callback(_, count, values, names):
                row = {}
                for idx in range(count):
                    name = names[idx].decode("utf-8", errors="replace") if names[idx] else f"c{idx}"
                    value = values[idx].decode("utf-8", errors="replace") if values[idx] else None
                    row[name] = value
                rows.append(row)
                return 0

            c_callback = _SQLITE_EXEC_CALLBACK(callback)
            err = ct.c_char_p()
            rc = int(self._lib.sqlite3_exec(
                db,
                str(sql).encode("utf-8"),
                c_callback,
                None,
                ct.byref(err),
            ))
            if rc != 0:
                detail = err.value.decode("utf-8", errors="replace") if err.value else self._errmsg(db)
                raise RuntimeError(f"sqlite query failed for {db_rel}: {rc} {detail}")
            return rows
        finally:
            self._lib.sqlite3_close(db)

    def _key_for(self, db_rel: str) -> str:
        keys = self._load_keys()
        normalized = db_rel.replace("\\", "/").strip("/")
        key = keys.get(normalized, "")
        if not key:
            raise RuntimeError(f"WeFlow key not found for {normalized}")
        return key

    def _load_keys(self) -> dict[str, str]:
        if self._keys is not None:
            return self._keys
        keys_file = self.data_dir / "all_keys.json"
        try:
            raw = json.loads(keys_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Could not read WeChat all_keys.json: {exc}") from exc
        out: dict[str, str] = {}
        if isinstance(raw, dict):
            for rel, value in raw.items():
                key = value.get("enc_key", "") if isinstance(value, dict) else value
                key = str(key or "").strip().lower()
                if len(key) == HEX_KEY_LEN and all(ch in "0123456789abcdefABCDEF" for ch in key):
                    out[str(rel).replace("\\", "/").strip("/")] = key
        self._keys = out
        return out

    def _load_sqlite_lib(self):
        lib_path = self.lib_dir / "libWCDB.dylib"
        if not lib_path.exists():
            raise RuntimeError(f"WeFlow libWCDB.dylib not found: {lib_path}")
        lib = ct.CDLL(str(lib_path))
        lib.sqlite3_open_v2.argtypes = [ct.c_char_p, ct.POINTER(ct.c_void_p), ct.c_int, ct.c_char_p]
        lib.sqlite3_open_v2.restype = ct.c_int
        lib.sqlite3_key.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int]
        lib.sqlite3_key.restype = ct.c_int
        lib.sqlite3_exec.argtypes = [
            ct.c_void_p,
            ct.c_char_p,
            _SQLITE_EXEC_CALLBACK,
            ct.c_void_p,
            ct.POINTER(ct.c_char_p),
        ]
        lib.sqlite3_exec.restype = ct.c_int
        lib.sqlite3_errmsg.argtypes = [ct.c_void_p]
        lib.sqlite3_errmsg.restype = ct.c_char_p
        lib.sqlite3_close.argtypes = [ct.c_void_p]
        lib.sqlite3_close.restype = ct.c_int
        return lib

    def _errmsg(self, db) -> str:
        raw = self._lib.sqlite3_errmsg(db)
        return raw.decode("utf-8", errors="replace") if raw else ""


_SQLITE_EXEC_CALLBACK = ct.CFUNCTYPE(
    ct.c_int,
    ct.c_void_p,
    ct.c_int,
    ct.POINTER(ct.c_char_p),
    ct.POINTER(ct.c_char_p),
)


def _normalize_data_dir(value: str) -> str:
    path = Path(value).expanduser()
    if path.name == "db_storage":
        path = path.parent
    if (path / "db_storage" / "session" / "session.db").exists():
        return str(path)
    return ""


def _detect_wechat_data_dir() -> str:
    pid = _detect_wechat_pid()
    if pid:
        data_dir = _data_dir_from_lsof(pid)
        if data_dir:
            return data_dir
    base = (
        Path.home()
        / "Library"
        / "Containers"
        / "com.tencent.xinWeChat"
        / "Data"
        / "Documents"
        / "xwechat_files"
    )
    candidates = []
    for session_db in base.glob("wxid_*/db_storage/session/session.db"):
        try:
            candidates.append((session_db.stat().st_mtime, session_db.parent.parent.parent))
        except OSError:
            continue
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return str(candidates[0][1])


def _detect_wechat_pid() -> int:
    try:
        result = subprocess.run(
            ["pgrep", "-x", "WeChat"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    first = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    return int(first) if first.isdigit() else 0


def _data_dir_from_lsof(pid: int) -> str:
    try:
        result = subprocess.run(
            ["lsof", "-n", "-P", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    marker = "/db_storage/session/session.db"
    for line in result.stdout.splitlines():
        if marker not in line:
            continue
        path = line.split()[-1]
        if path.endswith(marker):
            return path[: -len(marker)]
    return ""


def _display_name_from_row(row: dict[str, Any]) -> str:
    return _first_text(row, (
        "remark",
        "Remark",
        "nick_name",
        "nickName",
        "nickname",
        "NickName",
        "displayName",
        "display",
        "alias",
        "Alias",
    ))


def _split_group_message_sender(sender: str, content: str) -> tuple[str, str]:
    sender = str(sender or "").strip()
    content = str(content or "").strip()
    if ":\n" not in content:
        return sender, content
    prefix, body = content.split(":\n", 1)
    prefix = prefix.strip()
    if prefix.startswith("wxid_") or prefix.endswith("@chatroom"):
        if not sender:
            sender = prefix
        content = body.strip()
    elif sender and prefix == sender:
        content = body.strip()
    return sender, content


def _looks_corrupt_text(value: str) -> bool:
    text = str(value or "")
    if "\ufffd" in text:
        return True
    controls = [
        ch for ch in text
        if ord(ch) < 32 and ch not in {"\n", "\r", "\t"}
    ]
    return len(controls) >= 1


def _sql_quote(value: str) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def _sql_ident(value: str) -> str:
    return '"' + str(value or "").replace('"', '""') + '"'


def _first_text(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _first_int(row: dict[str, Any], keys: tuple[str, ...], default: int = 0) -> int:
    for key in keys:
        value = row.get(key)
        if _can_int(value):
            return int(value)
    return default


def _can_int(value) -> bool:
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def _message_type_name(local_type: int) -> str:
    return {
        1: "text",
        3: "image",
        34: "voice",
        43: "video",
        47: "emoji",
        49: "app",
    }.get(int(local_type or 0), "message")


def _message_type_label(local_type: int) -> str:
    return {
        3: "[图片]",
        34: "[语音]",
        43: "[视频]",
        47: "[表情]",
        49: "[消息]",
    }.get(int(local_type or 0), "[消息]")


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen = set()
    result = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result
