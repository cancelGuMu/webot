#!/usr/bin/env python3
"""Prepare macOS WeFlow/WCDB direct reads for webot.

This helper exposes only the setup steps still needed by the integrated
WeFlow path: diagnose the local WeChat account, extract/import database keys,
and verify direct WCDB reads. It does not start a sidecar HTTP service.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LIMIT = 5


def _load_key_helper():
    helper_path = Path(__file__).with_name("macos_" + "chat" + "log_setup.py")
    spec = importlib.util.spec_from_file_location("_macos_weflow_key_helper", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load key helper: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ensure_project_root_on_path() -> None:
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _client(data_dir: str = ""):
    _ensure_project_root_on_path()
    from src.wechat.mac_weflow_client import MacWeFlowClient

    return MacWeFlowClient(data_dir=data_dir or None)


def diagnose() -> int:
    helper = _load_key_helper()
    pid = helper.detect_wechat_pid()
    data_dir = helper.detect_data_dir(pid) if pid else helper.detect_data_dir_from_filesystem()
    keys_path = Path(data_dir) / "all_keys.json" if data_dir else None
    valid_keys = helper.count_valid_keys(keys_path) if keys_path else 0
    client = _client(data_dir)
    weflow_ok = client.health()

    print(f"system={helper.platform.system()}")
    print(f"sip_status={helper.get_sip_status()}")
    print(f"sudo_cached={'yes' if helper.sudo_cached() else 'no'}")
    print(f"lldb_python_path={helper.detect_lldb_python_path()}")
    print(f"wechat_version={helper.detect_wechat_version()}")
    print(f"wechat_pid={pid or ''}")
    print(f"data_dir={data_dir}")
    print(f"open_db_files={helper.count_open_db_files(pid, data_dir)}")
    print(f"all_keys={keys_path if keys_path else ''}")
    print(f"valid_key_entries={valid_keys}")
    print(f"weflow_health={'ok' if weflow_ok else 'down'}")

    if weflow_ok:
        try:
            rooms = client.get_chatrooms(limit=5).get("chatrooms", [])
        except Exception as exc:
            print(f"chatroom_sample_error={exc}", file=sys.stderr)
            return 1
        print(f"chatroom_sample_count={len(rooms)}")
        for idx, room in enumerate(rooms[:5], start=1):
            print(
                f"chatroom[{idx}]={room.get('username') or room.get('name')} "
                f"display={room.get('display') or ''}"
            )

    if not data_dir or valid_keys == 0 or not weflow_ok:
        return 1
    return 0


def verify_read(limit: int = DEFAULT_LIMIT) -> int:
    client = _client()
    if not client.health():
        print("weflow_health=down", file=sys.stderr)
        return 1
    try:
        payload = client.get_new_messages({}, limit=max(1, int(limit or DEFAULT_LIMIT)))
    except Exception as exc:
        print(f"weflow_read=error: {exc}", file=sys.stderr)
        return 1

    print("weflow_health=ok")
    print(f"message_count={payload.get('count', 0)}")
    for idx, msg in enumerate(payload.get("messages", [])[: max(1, int(limit or DEFAULT_LIMIT))], start=1):
        print(
            f"message[{idx}] chat_id={msg.get('username') or ''} "
            f"chat={msg.get('chat') or ''} sender={msg.get('sender') or ''} "
            f"type={msg.get('type') or ''}"
        )
    return 0


def extract_keys() -> int:
    return _load_key_helper().extract_keys()


def extract_keys_lldb() -> int:
    return _load_key_helper().run_lldb_keyscan()


def extract_keys_hook(duration: int | None = None) -> int:
    helper = _load_key_helper()
    if duration is None:
        return helper.run_lldb_keyscan(mode="aes-hook")
    return helper.run_lldb_keyscan(mode="aes-hook", duration=duration)


def extract_keys_restart_hook(
    *,
    duration: int | None,
    open_chats: list[str],
    assume_yes: bool,
    force: bool,
    verify_after: bool,
    limit: int,
) -> int:
    helper = _load_key_helper()
    rc = helper.restart_wechat_and_hook(
        duration=duration or helper.DEFAULT_RESTART_HOOK_DURATION,
        open_chats=open_chats,
        assume_yes=assume_yes,
        force=force,
        verify_after=False,
    )
    if rc != 0 or not verify_after:
        return rc
    return verify_read(limit=limit)


def import_keys(keys_file: str) -> int:
    return _load_key_helper().import_keys(keys_file)


def build_scanner() -> int:
    print(_load_key_helper().build_scanner())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="macOS WeFlow/WCDB setup helper")
    parser.add_argument(
        "command",
        choices=[
            "diagnose",
            "build-scanner",
            "extract-keys",
            "extract-keys-lldb",
            "extract-keys-hook",
            "extract-keys-restart-hook",
            "import-keys",
            "verify-read",
        ],
        help="diagnose WeFlow reads, extract/import keys, or verify direct WCDB reads",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--keys-file", default="wechat_keys.json")
    parser.add_argument("--duration", type=int)
    parser.add_argument("--open-chat", action="append", default=[])
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-verify-read", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "diagnose":
        return diagnose()
    if args.command == "build-scanner":
        return build_scanner()
    if args.command == "extract-keys":
        return extract_keys()
    if args.command == "extract-keys-lldb":
        return extract_keys_lldb()
    if args.command == "extract-keys-hook":
        return extract_keys_hook(args.duration)
    if args.command == "extract-keys-restart-hook":
        return extract_keys_restart_hook(
            duration=args.duration,
            open_chats=args.open_chat,
            assume_yes=args.yes,
            force=args.force,
            verify_after=not args.skip_verify_read,
            limit=args.limit,
        )
    if args.command == "import-keys":
        return import_keys(args.keys_file)
    if args.command == "verify-read":
        return verify_read(limit=args.limit)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
