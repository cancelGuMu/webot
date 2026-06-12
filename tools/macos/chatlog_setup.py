#!/usr/bin/env python3
"""Prepare macOS WeChat DB reading through a local chatlog service.

This helper does not print or store key material outside WeChat's account
directory. The key scanner writes ``all_keys.json`` next to ``db_storage``.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCANNER_DIR = Path(__file__).resolve().parent / "keyscan"
SCANNER_SOURCE = SCANNER_DIR / "main.go"
SCANNER_BINARY = SCANNER_DIR / "macscan-min"
LLDB_SCANNER_SCRIPT = Path(__file__).resolve().parent / "lldb_keyscan.py"
DEFAULT_LLDB_PYTHON_BIN = "/usr/bin/python3"
CHATLOG_DIR = Path(__file__).resolve().parent / "chatlog"
CHATLOG_SOURCE_DIR = CHATLOG_DIR / "chatlog_alpha-src"
CHATLOG_BINARY = CHATLOG_DIR / "chatlog-alpha"
CHATLOG_BINARY_MARKER = CHATLOG_DIR / "chatlog-alpha.headless"
CHATLOG_LOG = PROJECT_ROOT / "data" / "chatlog_alpha.log"
CHATLOG_ALPHA_ARCHIVE_URL = (
    "https://github.com/teest114514/chatlog_alpha/archive/refs/heads/main.tar.gz"
)
DEFAULT_CHATLOG_BASE_URL = "http://127.0.0.1:5030"
DEFAULT_RESTART_HOOK_DURATION = 180
DEFAULT_HOOK_OPEN_CHATS = ["文件传输助手"]
WECHAT_BUNDLE_ID = "com.tencent.xinWeChat"
HEX_KEY_RE = re.compile(r"^[0-9a-fA-F]{64}$")
SENSITIVE_MESSAGE_FIELDS = {
    "content",
    "sender",
    "sender_name",
    "chat",
    "username",
    "message",
    "text",
}
CHATLOG_DUMMY_DATA_KEY = "0" * 64
CHATLOG_HEADLESS_WRAPPER = """package main

import (
    "log"
    "os"
    "strings"

    "github.com/sjzar/chatlog/internal/chatlog"
)

func main() {
    log.SetFlags(log.LstdFlags | log.Lshortfile)
    dataDir := strings.TrimSpace(os.Getenv("CHATLOG_DATA_DIR"))
    if dataDir == "" {
        log.Fatal("CHATLOG_DATA_DIR is required")
    }
    httpAddr := strings.TrimSpace(os.Getenv("CHATLOG_HTTP_ADDR"))
    if httpAddr == "" {
        httpAddr = "127.0.0.1:5030"
    }
    workDir := strings.TrimSpace(os.Getenv("CHATLOG_WORK_DIR"))
    cmdConf := map[string]any{
        "data_dir": dataDir,
        "data_key": "%s",
        "platform": "darwin",
        "version": 4,
        "http_addr": httpAddr,
        "work_dir": workDir,
        "auto_decrypt": false,
        "wal_enabled": true,
    }
    if err := chatlog.New().CommandHTTPServer("", cmdConf); err != nil {
        log.Fatal(err)
    }
}
""" % CHATLOG_DUMMY_DATA_KEY


def parse_data_dir_from_lsof(output: str) -> str:
    """Return the active account dir from lsof output."""
    marker = "/db_storage/session/session.db"
    for line in output.splitlines():
        if marker not in line:
            continue
        path = line.split()[-1]
        if path.endswith(marker):
            return path[: -len(marker)]
    return ""


def count_valid_keys(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    count = 0
    for value in data.values():
        key = ""
        if isinstance(value, str):
            key = value
        elif isinstance(value, dict):
            key = str(value.get("enc_key", ""))
        if HEX_KEY_RE.fullmatch(key.strip()):
            count += 1
    return count


def normalize_key_entries(data: dict) -> dict[str, dict[str, str]]:
    result = {}
    for rel_path, value in data.items():
        rel = str(rel_path).strip()
        if not rel or rel.startswith("__"):
            continue
        key = ""
        if isinstance(value, str):
            key = value
        elif isinstance(value, dict):
            key = str(value.get("enc_key", ""))
        key = key.strip().lower()
        if not HEX_KEY_RE.fullmatch(key):
            continue
        result[rel] = {"enc_key": key}
    return result


def write_all_keys(data_dir: str, entries: dict[str, dict[str, str]]) -> Path:
    if not entries:
        raise RuntimeError("no valid key entries")
    clean_dir = Path(data_dir).expanduser()
    path = clean_dir / "all_keys.json"
    encoded = json.dumps(entries, indent=2, ensure_ascii=False)
    path.write_text(encoded, encoding="utf-8")
    path.chmod(0o600)
    try:
        stat = clean_dir.stat()
        os.chown(path, stat.st_uid, stat.st_gid)
    except (AttributeError, OSError):
        pass
    return path


def build_extract_command(scanner: str, pid: int, data_dir: str) -> list[str]:
    return ["sudo", scanner, "--pid", str(pid), "--data-dir", data_dir]


def build_lldb_extract_command(
    script: Path,
    python_bin: str,
    pid: int,
    data_dir: str,
    mode: str = "scan",
    duration: int = 45,
    lldb_python_path: str = "",
) -> list[str]:
    cmd = ["sudo", "env"]
    if lldb_python_path.strip():
        cmd.append(f"PYTHONPATH={lldb_python_path.strip()}")
    cmd.extend([
        python_bin,
        str(script),
        "--pid",
        str(pid),
        "--data-dir",
        data_dir,
    ])
    if mode != "scan":
        cmd.extend(["--mode", mode])
    if mode == "aes-hook":
        cmd.extend(["--duration", str(duration)])
    return cmd


def build_lldb_env(
    lldb_python_path: str,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    env = dict(base_env or os.environ)
    existing = env.get("PYTHONPATH", "").strip()
    lldb_path = lldb_python_path.strip()
    if lldb_path and existing:
        env["PYTHONPATH"] = f"{lldb_path}{os.pathsep}{existing}"
    elif lldb_path:
        env["PYTHONPATH"] = lldb_path
    return env


def resolve_lldb_python_bin() -> str:
    env_bin = os.getenv("MACOS_LLDB_PYTHON", "").strip()
    if env_bin:
        return env_bin
    if Path(DEFAULT_LLDB_PYTHON_BIN).exists():
        return DEFAULT_LLDB_PYTHON_BIN
    return sys.executable


def build_chatlog_build_command(source_dir: Path, output: Path) -> list[str]:
    return ["go", "build", "-o", str(output), "./cmd/chatlog_server"]


def run_text(cmd: list[str], timeout: int = 10) -> str:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return result.stdout


def run_combined_text(cmd: list[str], timeout: int = 10) -> str:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return (result.stdout or "") + (result.stderr or "")


def ensure_project_root_on_path(paths: list[str] | None = None) -> bool:
    target = str(PROJECT_ROOT)
    active_paths = paths if paths is not None else sys.path
    if target in active_paths:
        return False
    active_paths.insert(0, target)
    return True


def parse_sip_status(output: str) -> str:
    lowered = output.lower()
    if "disabled" in lowered:
        return "disabled"
    if "enabled" in lowered:
        return "enabled"
    return "unknown"


def get_sip_status() -> str:
    if platform.system() != "Darwin":
        return "not_darwin"
    return parse_sip_status(run_combined_text(["csrutil", "status"], timeout=5))


def sudo_cached() -> bool:
    result = subprocess.run(
        ["sudo", "-n", "true"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def detect_wechat_version() -> str:
    out = run_text([
        "defaults",
        "read",
        "/Applications/WeChat.app/Contents/Info.plist",
        "CFBundleShortVersionString",
    ], timeout=5)
    return out.strip().splitlines()[0] if out.strip() else ""


def detect_lldb_python_path() -> str:
    out = run_text(["lldb", "-P"], timeout=5)
    return out.strip().splitlines()[0] if out.strip() else ""


def detect_wechat_pid() -> int:
    out = run_text(["pgrep", "-x", "WeChat"])
    first = out.strip().splitlines()[0] if out.strip() else ""
    return int(first) if first.isdigit() else 0


def detect_data_dir(pid: int) -> str:
    if not pid:
        return ""
    out = run_text(["lsof", "-n", "-P", "-p", str(pid)], timeout=20)
    data_dir = parse_data_dir_from_lsof(out)
    if data_dir:
        return data_dir
    return detect_data_dir_from_filesystem()


def count_open_db_files(pid: int, data_dir: str) -> int:
    if not pid or not data_dir:
        return 0
    out = run_text(["lsof", "-n", "-P", "-p", str(pid)], timeout=20)
    prefix = str(Path(data_dir).expanduser() / "db_storage")
    seen = set()
    for line in out.splitlines():
        if prefix not in line:
            continue
        path = line.split()[-1]
        if ".db" not in path and ".kvdb" not in path:
            continue
        if path.endswith((".db", ".db-wal", ".db-shm", ".kvdb", ".kvdb-wal", ".kvdb-shm")):
            seen.add(path)
    return len(seen)


def detect_data_dir_from_filesystem() -> str:
    base = Path.home() / "Library" / "Containers" / "com.tencent.xinWeChat" / "Data" / "Documents" / "xwechat_files"
    candidates = []
    for session_db in base.glob("wxid_*/db_storage/session/session.db"):
        try:
            mtime = session_db.stat().st_mtime
        except OSError:
            continue
        candidates.append((mtime, session_db.parent.parent.parent))
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return str(candidates[0][1])


def build_scanner() -> Path:
    if platform.system() != "Darwin":
        raise RuntimeError("macOS key scanner can only be built on Darwin")
    if not SCANNER_SOURCE.exists():
        raise RuntimeError(f"scanner source not found: {SCANNER_SOURCE}")
    env = os.environ.copy()
    env["CGO_ENABLED"] = "1"
    env["GO111MODULE"] = "off"
    result = subprocess.run(
        ["go", "build", "-o", str(SCANNER_BINARY), str(SCANNER_SOURCE)],
        cwd=str(PROJECT_ROOT),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return SCANNER_BINARY


def chatlog_health(base_url: str = DEFAULT_CHATLOG_BASE_URL) -> bool:
    try:
        req = Request(base_url.rstrip("/") + "/health", headers={"Accept": "application/json"})
        with urlopen(req, timeout=2) as resp:
            body = resp.read(512).decode("utf-8", errors="replace")
        return resp.status < 400 and ("ok" in body.lower() or body.strip())
    except (OSError, URLError):
        return False


def find_chatlog_binary() -> Path | None:
    env_bin = os.getenv("CHATLOG_BIN", "").strip()
    if env_bin:
        candidate = Path(env_bin).expanduser()
        if candidate.exists() and os.access(candidate, os.X_OK) and is_launchable_binary(candidate):
            return candidate
    if (
        CHATLOG_BINARY_MARKER.exists()
        and CHATLOG_BINARY.exists()
        and os.access(CHATLOG_BINARY, os.X_OK)
        and is_launchable_binary(CHATLOG_BINARY)
    ):
        return CHATLOG_BINARY

    path_bin = shutil.which("chatlog")
    if path_bin:
        candidate = Path(path_bin)
        if candidate.exists() and os.access(candidate, os.X_OK) and is_launchable_binary(candidate):
            return candidate
    return None


def is_launchable_binary(path: Path) -> bool:
    try:
        header = path.read_bytes()[:4]
    except OSError:
        return False
    return header in {
        b"\xcf\xfa\xed\xfe",  # Mach-O 64-bit little-endian
        b"\xfe\xed\xfa\xcf",  # Mach-O 64-bit big-endian
        b"\xca\xfe\xba\xbe",  # Mach-O fat
        b"\xca\xfe\xba\xbf",  # Mach-O fat 64
    } or header[:2] == b"#!"


def _safe_extract_tar(archive: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        roots = {
            Path(member.name).parts[0]
            for member in members
            if Path(member.name).parts
        }
        if len(roots) != 1:
            raise RuntimeError("chatlog_alpha archive has unexpected layout")
        root = roots.pop()
        for member in members:
            target = dest / member.name
            if not str(target.resolve()).startswith(str(dest.resolve())):
                raise RuntimeError("unsafe path in chatlog_alpha archive")
        try:
            tar.extractall(dest, filter="data")
        except TypeError:
            tar.extractall(dest)
    extracted = dest / root
    if not extracted.exists():
        raise RuntimeError("chatlog_alpha archive did not extract source dir")
    return extracted


def download_chatlog_source(archive_url: str = CHATLOG_ALPHA_ARCHIVE_URL) -> Path:
    CHATLOG_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / "chatlog_alpha.tar.gz"
        req = Request(
            archive_url,
            headers={"User-Agent": "wechat-group-bot-macos-setup"},
        )
        with urlopen(req, timeout=120) as resp, archive.open("wb") as fh:
            shutil.copyfileobj(resp, fh)
        extracted = _safe_extract_tar(archive, tmp_path / "src")
        if CHATLOG_SOURCE_DIR.exists():
            shutil.rmtree(CHATLOG_SOURCE_DIR)
        shutil.move(str(extracted), str(CHATLOG_SOURCE_DIR))
    return CHATLOG_SOURCE_DIR


def write_chatlog_headless_wrapper(source_dir: Path) -> Path:
    wrapper = source_dir / "cmd" / "chatlog_server" / "main.go"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(CHATLOG_HEADLESS_WRAPPER, encoding="utf-8")
    return wrapper


def build_chatlog() -> Path:
    existing = find_chatlog_binary()
    if existing and existing == CHATLOG_BINARY and CHATLOG_BINARY_MARKER.exists():
        return existing
    if shutil.which("go") is None:
        raise RuntimeError("go is required to build chatlog_alpha")
    source_dir = download_chatlog_source()
    write_chatlog_headless_wrapper(source_dir)
    CHATLOG_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        build_chatlog_build_command(source_dir, CHATLOG_BINARY),
        cwd=str(source_dir),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    CHATLOG_BINARY.chmod(0o755)
    CHATLOG_BINARY_MARKER.write_text("headless\n", encoding="utf-8")
    return CHATLOG_BINARY


def ensure_chatlog_binary() -> Path:
    env_bin = os.getenv("CHATLOG_BIN", "").strip()
    if env_bin:
        binary = Path(env_bin).expanduser()
        if binary.exists() and os.access(binary, os.X_OK) and is_launchable_binary(binary):
            return binary
    if (
        CHATLOG_BINARY_MARKER.exists()
        and CHATLOG_BINARY.exists()
        and os.access(CHATLOG_BINARY, os.X_OK)
        and is_launchable_binary(CHATLOG_BINARY)
    ):
        return CHATLOG_BINARY
    return build_chatlog()


def chatlog_json(path: str, params: dict[str, str],
                 base_url: str = DEFAULT_CHATLOG_BASE_URL) -> dict:
    url = f"{base_url.rstrip('/')}{path}?{urlencode(params)}"
    req = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read(1000).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    data = json.loads(raw or "{}")
    if not isinstance(data, dict):
        raise RuntimeError(f"chatlog returned non-object JSON from {path}")
    return data


def summarize_new_messages_payload(payload: dict) -> list[str]:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        messages = []
    new_state = payload.get("new_state")
    if not isinstance(new_state, dict):
        new_state = {}
    lines = [
        f"message_count={len(messages)}",
        f"new_state_entries={len(new_state)}",
    ]
    if messages and isinstance(messages[0], dict):
        sample = messages[0]
        safe_fields = sorted(k for k in sample.keys() if k not in SENSITIVE_MESSAGE_FIELDS)
        lines.append("sample_fields=" + ",".join(safe_fields))
        if "timestamp" in sample:
            lines.append(f"sample_timestamp={sample.get('timestamp')}")
        if "type" in sample:
            lines.append(f"sample_type={sample.get('type')}")
        if "is_group" in sample:
            lines.append(f"sample_is_group={sample.get('is_group')}")
    return lines


def chatlog_addr_from_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.netloc:
        return parsed.netloc
    return base_url.replace("http://", "").replace("https://", "").strip("/")


def chatlog_port_from_base_url(base_url: str) -> int:
    parsed = urlparse(base_url)
    if parsed.port:
        return parsed.port
    addr = chatlog_addr_from_base_url(base_url)
    if ":" in addr:
        raw_port = addr.rsplit(":", 1)[1]
        if raw_port.isdigit():
            return int(raw_port)
    return 5030


def print_diagnose(base_url: str = DEFAULT_CHATLOG_BASE_URL) -> int:
    pid = detect_wechat_pid()
    data_dir = detect_data_dir(pid)
    keys_path = Path(data_dir) / "all_keys.json" if data_dir else None
    valid_keys = count_valid_keys(keys_path) if keys_path else 0
    service_ok = chatlog_health(base_url)
    chatlog_bin = find_chatlog_binary()

    print(f"system={platform.system()}")
    print(f"sip_status={get_sip_status()}")
    print(f"sudo_cached={'yes' if sudo_cached() else 'no'}")
    print(f"go_bin={shutil.which('go') or ''}")
    print(f"lldb_python_path={detect_lldb_python_path()}")
    print(f"wechat_version={detect_wechat_version()}")
    print(f"wechat_pid={pid or ''}")
    print(f"data_dir={data_dir}")
    print(f"open_db_files={count_open_db_files(pid, data_dir)}")
    print(f"all_keys={keys_path if keys_path else ''}")
    print(f"valid_key_entries={valid_keys}")
    print(f"chatlog_bin={chatlog_bin if chatlog_bin else ''}")
    print(f"chatlog_health={'ok' if service_ok else 'down'}")

    if not pid or not data_dir or valid_keys == 0 or not service_ok:
        return 1
    return 0


def extract_keys() -> int:
    pid = detect_wechat_pid()
    if not pid:
        print("WeChat is not running.", file=sys.stderr)
        return 1
    data_dir = detect_data_dir(pid)
    if not data_dir:
        print("Could not detect the active WeChat account data dir.", file=sys.stderr)
        return 1
    scanner = build_scanner()
    cmd = build_extract_command(str(scanner), pid, data_dir)
    print("Running key scanner with sudo. It will not print key material.")
    print("Command:", " ".join(cmd))
    result = subprocess.run(cmd, check=False)
    keys_path = Path(data_dir) / "all_keys.json"
    valid_keys = count_valid_keys(keys_path)
    if result.returncode == 0 and valid_keys > 0:
        print(f"valid_key_entries={valid_keys}")
        return 0

    if result.returncode != 0:
        print("mach_scanner=failed_or_no_match")
    else:
        print(f"valid_key_entries={valid_keys}")
    print("Trying lldb key scanner fallback. It will not print key material.")
    return run_lldb_keyscan(pid, data_dir)


def run_lldb_keyscan(
    pid: int | None = None,
    data_dir: str | None = None,
    mode: str = "scan",
    duration: int = 45,
) -> int:
    pid = pid or detect_wechat_pid()
    if not pid:
        print("WeChat is not running.", file=sys.stderr)
        return 1
    data_dir = data_dir or detect_data_dir(pid) or detect_data_dir_from_filesystem()
    if not data_dir:
        print("Could not detect the active WeChat account data dir.", file=sys.stderr)
        return 1
    if not LLDB_SCANNER_SCRIPT.exists():
        print(f"LLDB scanner script not found: {LLDB_SCANNER_SCRIPT}", file=sys.stderr)
        return 1

    lldb_python_path = detect_lldb_python_path()
    if not lldb_python_path:
        print("Could not detect lldb Python path. Install Xcode Command Line Tools or llvm.", file=sys.stderr)
        return 1

    python_bin = resolve_lldb_python_bin()
    env = build_lldb_env(lldb_python_path)
    cmd = build_lldb_extract_command(
        LLDB_SCANNER_SCRIPT,
        python_bin,
        pid,
        data_dir,
        mode=mode,
        duration=duration,
        lldb_python_path=env.get("PYTHONPATH", lldb_python_path),
    )
    print(f"Running lldb key scanner ({mode}) with sudo. It will not print key material.")
    print("Command:", " ".join(cmd))
    result = subprocess.run(cmd, env=env, check=False)
    keys_path = Path(data_dir) / "all_keys.json"
    print(f"valid_key_entries={count_valid_keys(keys_path)}")
    return result.returncode


def normalize_open_chats(open_chats: list[str] | None) -> list[str]:
    chats = [chat.strip() for chat in (open_chats or []) if chat and chat.strip()]
    return chats or list(DEFAULT_HOOK_OPEN_CHATS)


def confirm_restart_wechat(assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    message = (
        "This will quit and reopen WeChat to attach the AES hook before DBs are "
        "loaded. Save unsent drafts first. Continue? [y/N] "
    )
    if not sys.stdin.isatty():
        print("Refusing to restart WeChat without confirmation. Re-run with --yes.", file=sys.stderr)
        return False
    answer = input(message).strip().lower()
    return answer in {"y", "yes"}


def ensure_sudo_ticket() -> bool:
    print("Requesting sudo for lldb attach. No key material will be printed.")
    result = subprocess.run(["sudo", "-v"], check=False)
    if result.returncode != 0:
        print("sudo authentication failed.", file=sys.stderr)
        return False
    return True


def quit_wechat_gracefully(force: bool = False) -> bool:
    scripts = [
        f'tell application id "{WECHAT_BUNDLE_ID}" to quit',
        'tell application "WeChat" to quit',
    ]
    for script in scripts:
        result = subprocess.run(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return True

    if force:
        result = subprocess.run(
            ["killall", "WeChat"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0

    print("Could not ask WeChat to quit. Close WeChat manually or re-run with --force.", file=sys.stderr)
    return False


def wait_for_wechat_exit(pid: int, timeout: int = 20) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["kill", "-0", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            return True
        time.sleep(0.5)
    return False


def launch_wechat() -> bool:
    commands = [
        ["open", "-a", "WeChat"],
        ["open", "/Applications/WeChat.app"],
    ]
    for cmd in commands:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return True
    print("Could not launch WeChat.", file=sys.stderr)
    return False


def detect_wechat_pids() -> list[int]:
    out = run_text(["pgrep", "-x", "WeChat"])
    pids = []
    for line in out.strip().splitlines():
        if line.strip().isdigit():
            pids.append(int(line.strip()))
    return pids


def wait_for_new_wechat_pid(old_pid: int, timeout: int = 30) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pids = detect_wechat_pids()
        candidates = [pid for pid in pids if pid != old_pid]
        if candidates:
            return max(candidates)
        if old_pid == 0 and pids:
            return max(pids)
        time.sleep(0.5)
    return 0


def warm_wechat_chats(open_chats: list[str]) -> None:
    ensure_project_root_on_path()
    try:
        from src.wechat.mac_ui_backend import MacUIAutomation
    except Exception as exc:
        print(f"open_chat=unavailable error={exc}", file=sys.stderr)
        return

    automation = MacUIAutomation()
    for chat in normalize_open_chats(open_chats):
        ok = automation.open_chat(chat)
        print(f"open_chat={chat} ok={'yes' if ok else 'no'}")
        time.sleep(1)


def start_chat_warmup(open_chats: list[str] | None, duration: int) -> threading.Thread:
    chats = normalize_open_chats(open_chats)
    deadline = time.monotonic() + max(10, duration)

    def run() -> None:
        time.sleep(5)
        while time.monotonic() < deadline:
            warm_wechat_chats(chats)
            time.sleep(10)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def restart_wechat_and_hook(
    duration: int = DEFAULT_RESTART_HOOK_DURATION,
    open_chats: list[str] | None = None,
    assume_yes: bool = False,
    force: bool = False,
    verify_after: bool = True,
    base_url: str = DEFAULT_CHATLOG_BASE_URL,
) -> int:
    duration = max(30, int(duration))
    chats = normalize_open_chats(open_chats)

    if not confirm_restart_wechat(assume_yes):
        return 1

    old_pid = detect_wechat_pid()
    data_dir = detect_data_dir(old_pid) if old_pid else detect_data_dir_from_filesystem()

    if not ensure_sudo_ticket():
        return 1

    if old_pid:
        print(f"Quitting WeChat pid={old_pid}...")
        if not quit_wechat_gracefully(force=force):
            return 1
        if not wait_for_wechat_exit(old_pid):
            print("WeChat did not exit in time. Close it manually and retry.", file=sys.stderr)
            return 1

    print("Launching WeChat...")
    if not launch_wechat():
        return 1

    new_pid = wait_for_new_wechat_pid(old_pid)
    if not new_pid:
        print("Could not detect restarted WeChat pid.", file=sys.stderr)
        return 1

    if not data_dir:
        data_dir = detect_data_dir(new_pid) or detect_data_dir_from_filesystem()
    if not data_dir:
        print("Could not detect the active WeChat account data dir.", file=sys.stderr)
        return 1

    print(f"WeChat restarted pid={new_pid}")
    print("Starting chat warmup while AES hook is active...")
    start_chat_warmup(chats, duration=duration)

    rc = run_lldb_keyscan(new_pid, data_dir, mode="aes-hook", duration=duration)
    if rc != 0:
        return rc

    if not verify_after:
        return 0
    restart_rc = restart_chatlog(base_url)
    if restart_rc != 0:
        return restart_rc
    return verify_read(base_url, limit=5)


def import_keys(keys_file: str) -> int:
    path = Path(keys_file).expanduser()
    if not path.exists():
        print(f"Key file not found: {path}", file=sys.stderr)
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read key file: {exc}", file=sys.stderr)
        return 1
    if not isinstance(data, dict):
        print("Key file must contain a JSON object.", file=sys.stderr)
        return 1

    entries = normalize_key_entries(data)
    if not entries:
        print("No valid key entries found in key file.", file=sys.stderr)
        return 1

    pid = detect_wechat_pid()
    data_dir = detect_data_dir(pid) or detect_data_dir_from_filesystem()
    if not data_dir:
        print("Could not detect the active WeChat account data dir.", file=sys.stderr)
        return 1

    try:
        out = write_all_keys(data_dir, entries)
    except Exception as exc:
        print(f"Could not write all_keys.json: {exc}", file=sys.stderr)
        return 1
    print(f"all_keys={out}")
    print(f"valid_key_entries={count_valid_keys(out)}")
    return 0


def print_build_chatlog() -> int:
    try:
        print(build_chatlog())
        return 0
    except Exception as exc:
        print(f"Failed to build chatlog_alpha: {exc}", file=sys.stderr)
        return 1


def start_chatlog(base_url: str = DEFAULT_CHATLOG_BASE_URL) -> int:
    if chatlog_health(base_url):
        print("chatlog_health=ok")
        return 0
    try:
        binary = ensure_chatlog_binary()
    except Exception as exc:
        print(f"Failed to prepare chatlog_alpha: {exc}", file=sys.stderr)
        return 1
    pid = detect_wechat_pid()
    data_dir = detect_data_dir(pid)
    if not data_dir:
        print("Could not detect the active WeChat account data dir.", file=sys.stderr)
        return 1

    CHATLOG_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_fh = CHATLOG_LOG.open("a", encoding="utf-8")
    env = os.environ.copy()
    env["CHATLOG_DATA_DIR"] = data_dir
    env["CHATLOG_HTTP_ADDR"] = chatlog_addr_from_base_url(base_url)
    proc = subprocess.Popen(
        [str(binary)],
        cwd=str(PROJECT_ROOT),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    print(f"chatlog_pid={proc.pid}")
    print(f"chatlog_log={CHATLOG_LOG}")

    for _ in range(30):
        if chatlog_health(base_url):
            print("chatlog_health=ok")
            return 0
        if proc.poll() is not None:
            break
        time.sleep(1)

    if proc.poll() is not None:
        print(f"chatlog_exit_code={proc.returncode}", file=sys.stderr)
    print("chatlog_health=down", file=sys.stderr)
    return 1


def stop_chatlog(base_url: str = DEFAULT_CHATLOG_BASE_URL) -> int:
    port = chatlog_port_from_base_url(base_url)
    raw = run_text(["lsof", "-n", "-P", "-ti", f"TCP:{port}", "-sTCP:LISTEN"], timeout=5)
    pids = [line.strip() for line in raw.splitlines() if line.strip().isdigit()]
    if not pids:
        print("chatlog_running=no")
        return 0
    for pid in pids:
        subprocess.run(["kill", pid], check=False)
    for _ in range(10):
        if not chatlog_health(base_url):
            print("chatlog_stopped=yes")
            print("chatlog_pids=" + ",".join(pids))
            return 0
        time.sleep(1)
    print("chatlog_stopped=no", file=sys.stderr)
    print("chatlog_pids=" + ",".join(pids), file=sys.stderr)
    return 1


def restart_chatlog(base_url: str = DEFAULT_CHATLOG_BASE_URL) -> int:
    stop_rc = stop_chatlog(base_url)
    if stop_rc != 0:
        return stop_rc
    return start_chatlog(base_url)


def verify_read(base_url: str = DEFAULT_CHATLOG_BASE_URL, limit: int = 5) -> int:
    if not chatlog_health(base_url):
        print("chatlog_health=down", file=sys.stderr)
        return 1
    try:
        payload = chatlog_json(
            "/api/v1/new_messages",
            {"format": "json", "limit": str(max(1, limit))},
            base_url=base_url,
        )
    except Exception as exc:
        print(f"chatlog_read=error: {exc}", file=sys.stderr)
        return 1
    print("chatlog_health=ok")
    for line in summarize_new_messages_payload(payload):
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="macOS chatlog setup helper")
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
            "build-chatlog",
            "start-chatlog",
            "stop-chatlog",
            "restart-chatlog",
            "verify-read",
        ],
        help="diagnose, extract keys, prepare chatlog_alpha, or verify reads",
    )
    parser.add_argument("--chatlog-base-url", default=DEFAULT_CHATLOG_BASE_URL)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--keys-file", default="wechat_keys.json")
    parser.add_argument("--duration", type=int)
    parser.add_argument("--open-chat", action="append", default=[])
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-verify-read", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "diagnose":
        return print_diagnose(args.chatlog_base_url)
    if args.command == "build-scanner":
        print(build_scanner())
        return 0
    if args.command == "extract-keys":
        return extract_keys()
    if args.command == "extract-keys-lldb":
        return run_lldb_keyscan()
    if args.command == "extract-keys-hook":
        if args.duration is None:
            return run_lldb_keyscan(mode="aes-hook")
        return run_lldb_keyscan(mode="aes-hook", duration=args.duration)
    if args.command == "extract-keys-restart-hook":
        duration = args.duration or DEFAULT_RESTART_HOOK_DURATION
        return restart_wechat_and_hook(
            duration=duration,
            open_chats=args.open_chat,
            assume_yes=args.yes,
            force=args.force,
            verify_after=not args.skip_verify_read,
            base_url=args.chatlog_base_url,
        )
    if args.command == "import-keys":
        return import_keys(args.keys_file)
    if args.command == "build-chatlog":
        return print_build_chatlog()
    if args.command == "start-chatlog":
        return start_chatlog(args.chatlog_base_url)
    if args.command == "stop-chatlog":
        return stop_chatlog(args.chatlog_base_url)
    if args.command == "restart-chatlog":
        return restart_chatlog(args.chatlog_base_url)
    if args.command == "verify-read":
        return verify_read(args.chatlog_base_url, limit=args.limit)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
