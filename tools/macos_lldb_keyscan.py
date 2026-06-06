#!/usr/bin/env python3
"""Extract macOS WeChat DB keys with LLDB memory scanning.

The scanner writes chatlog-compatible ``all_keys.json`` into the active WeChat
account directory. It intentionally never prints key material.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac as hmac_mod
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path


PAGE_SIZE = 4096
KEY_SIZE = 32
SALT_SIZE = 16
MAX_REGION_SIZE = 500 * 1024 * 1024
CHUNK_SIZE = 8 * 1024 * 1024
QUOTED_HEX_PATTERN = re.compile(rb"x'([0-9a-fA-F]{64,192})'")
BARE_HEX_PATTERN = re.compile(
    rb"(?<![0-9a-fA-F])([0-9a-fA-F]{96}|[0-9a-fA-F]{64})(?![0-9a-fA-F])"
)
AES_BREAKPOINT_NAMES = [
    "openssl_aes_arm_set_decrypt_key",
    "openssl_aes_arm_set_encrypt_key",
    "AES_set_decrypt_key",
    "AES_set_encrypt_key",
]
HOOK_BREAKPOINT_NAMES = [
    "sqlite3_key_v2",
    "sqlite3_key",
    "loadKeyCCCrypt",
    "sqliteCodecCCCrypto",
    "CCCryptorCreateWithMode",
    "CCCryptorCreateFromData",
    "CCCryptorCreate",
    "CCCrypt",
    *AES_BREAKPOINT_NAMES,
]
MAX_HOOK_KEY_BYTES = 256
HOOK_KEY_ARGUMENT_SPECS = [
    {
        "names": tuple(AES_BREAKPOINT_NAMES),
        "ptr_regs": ["x0", "rdi"],
        "len_regs": ["x1", "rsi"],
        "len_unit": "bits",
    },
    {
        "names": ("sqlite3_key",),
        "ptr_regs": ["x1", "rsi"],
        "len_regs": ["x2", "rdx"],
        "len_unit": "bytes",
    },
    {
        "names": ("sqlite3_key_v2",),
        "ptr_regs": ["x2", "rdx"],
        "len_regs": ["x3", "rcx"],
        "len_unit": "bytes",
    },
    {
        "names": ("CCCrypt", "CCCryptorCreate", "CCCryptorCreateFromData"),
        "ptr_regs": ["x3", "rcx"],
        "len_regs": ["x4", "r8"],
        "len_unit": "bytes",
    },
    {
        "names": ("CCCryptorCreateWithMode",),
        "ptr_regs": ["x5", "r9"],
        "len_regs": ["x6"],
        "len_unit": "bytes",
    },
]
GENERIC_KEY_POINTER_SYMBOLS = ("loadKeyCCCrypt", "sqliteCodecCCCrypto")
GENERIC_KEY_POINTER_REGS = ["x0", "x1", "x2", "x3", "x4", "x5", "rdi", "rsi", "rdx", "rcx", "r8", "r9"]


def resolve_db_storage(data_dir: Path) -> tuple[Path, Path]:
    clean = data_dir.expanduser().resolve()
    if clean.name.lower() == "db_storage":
        return clean.parent, clean
    return clean, clean / "db_storage"


def collect_db_files(db_storage: Path) -> tuple[list[dict], dict[str, list[str]]]:
    db_files: list[dict] = []
    salt_to_dbs: dict[str, list[str]] = {}

    for path in db_storage.rglob("*.db"):
        if path.name.endswith(("-wal", "-shm")):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size < PAGE_SIZE:
            continue
        try:
            page1 = path.read_bytes()[:PAGE_SIZE]
        except OSError:
            continue
        if len(page1) < PAGE_SIZE or page1[:15] == b"SQLite format 3":
            continue

        rel = path.relative_to(db_storage).as_posix().lower()
        salt = page1[:SALT_SIZE].hex()
        item = {
            "rel": rel,
            "path": str(path),
            "size": size,
            "salt": salt,
            "page1": page1,
        }
        db_files.append(item)
        salt_to_dbs.setdefault(salt, []).append(rel)

    return db_files, salt_to_dbs


def verify_key_for_db(enc_key: bytes, db_page1: bytes) -> bool:
    if len(enc_key) != KEY_SIZE or len(db_page1) < PAGE_SIZE:
        return False
    return verify_sqlcipher_hmac_key(enc_key, db_page1) or verify_darwin_v4_page_key(enc_key, db_page1)


def verify_sqlcipher_hmac_key(enc_key: bytes, db_page1: bytes) -> bool:
    salt = db_page1[:SALT_SIZE]
    mac_salt = bytes(byte ^ 0x3A for byte in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, dklen=KEY_SIZE)

    hmac_data = db_page1[SALT_SIZE: PAGE_SIZE - 80 + 16]
    stored_hmac = db_page1[PAGE_SIZE - 64: PAGE_SIZE]
    digest = hmac_mod.new(mac_key, hmac_data, hashlib.sha512)
    digest.update(struct.pack("<I", 1))
    return digest.digest() == stored_hmac


def verify_darwin_v4_page_key(enc_key: bytes, db_page1: bytes) -> bool:
    iv_offset = PAGE_SIZE - 80
    iv = db_page1[iv_offset: iv_offset + 16]
    first_block = db_page1[SALT_SIZE: SALT_SIZE + 16]
    if len(iv) != 16 or len(first_block) != 16:
        return False

    try:
        result = subprocess.run(
            [
                "/usr/bin/openssl",
                "enc",
                "-d",
                "-aes-256-cbc",
                "-K",
                enc_key.hex(),
                "-iv",
                iv.hex(),
                "-nopad",
            ],
            input=first_block,
            capture_output=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    return sqlite_header_tail_is_plausible(result.stdout)


def sqlite_header_tail_is_plausible(value: bytes) -> bool:
    if len(value) < 8:
        return False
    page_size = int.from_bytes(value[:2], "big")
    return (
        page_size in {1024, 2048, 4096, 8192, 16384, 32768, 65536}
        and value[2] in {1, 2}
        and value[3] in {1, 2}
        and value[4] == 0
        and value[5:8] == b"\x40\x20\x20"
    )


def decode_hex_candidate(hex_text: str) -> tuple[str, str | None] | None:
    hex_len = len(hex_text)
    if hex_len == 64:
        return hex_text.lower(), None
    if hex_len == 96:
        return hex_text[:64].lower(), hex_text[64:].lower()
    if hex_len > 96 and hex_len % 2 == 0:
        return hex_text[:64].lower(), hex_text[-32:].lower()
    return None


def iter_hex_candidates(data: bytes):
    quoted_spans: list[tuple[int, int]] = []
    for match in QUOTED_HEX_PATTERN.finditer(data):
        quoted_spans.append(match.span(1))
        decoded = decode_hex_candidate(match.group(1).decode("ascii"))
        if decoded:
            yield decoded

    for match in BARE_HEX_PATTERN.finditer(data):
        span = match.span(1)
        if any(start <= span[0] and span[1] <= end for start, end in quoted_spans):
            continue
        decoded = decode_hex_candidate(match.group(1).decode("ascii"))
        if decoded:
            yield decoded


def add_lldb_python_path(path: str = "") -> bool:
    candidates = []
    if path.strip():
        candidates.append(path.strip())
    try:
        discovered = subprocess.check_output(["lldb", "-P"], text=True, timeout=5).strip()
        if discovered:
            candidates.append(discovered)
    except (OSError, subprocess.SubprocessError):
        pass

    changed = False
    for candidate in candidates:
        if candidate and candidate not in sys.path:
            sys.path.insert(0, candidate)
            changed = True
    return changed


def import_lldb():
    add_lldb_python_path(os.getenv("LLDB_PYTHONPATH", ""))
    try:
        import lldb  # type: ignore
    except Exception as exc:
        print(f"lldb_import=error: {exc}", file=sys.stderr)
        print("hint=Run with: sudo env PYTHONPATH=$(lldb -P) /usr/bin/python3 tools/macos_lldb_keyscan.py", file=sys.stderr)
        raise SystemExit(1) from exc
    return lldb


def attach_process(lldb, pid: int):
    debugger = lldb.SBDebugger.Create()
    debugger.SetAsync(False)
    target = debugger.CreateTarget("")
    error = lldb.SBError()

    if pid:
        process = target.AttachToProcessWithID(debugger.GetListener(), pid, error)
    else:
        process = target.AttachToProcessWithName(debugger.GetListener(), "WeChat", False, error)

    if not error.Success():
        print(f"attach=error: {error.GetCString()}", file=sys.stderr)
        print("hint=Ensure WeChat is running, SIP is disabled, and sudo is active.", file=sys.stderr)
        raise SystemExit(1)
    return debugger, process


def readable_regions(lldb, process) -> list[tuple[int, int]]:
    region_info = lldb.SBMemoryRegionInfo()
    regions: list[tuple[int, int]] = []
    addr = 0

    while True:
        error = process.GetMemoryRegionInfo(addr, region_info)
        if error.Fail():
            break

        base = int(region_info.GetRegionBase())
        end = int(region_info.GetRegionEnd())
        if end <= base:
            break

        size = end - base
        if region_info.IsReadable() and not region_info.IsExecutable() and 0 < size < MAX_REGION_SIZE:
            regions.append((base, size))

        addr = end
        if addr == 0:
            break

    return regions


def remember_key(
    key_map: dict[str, str],
    remaining_salts: set[str],
    db_files: list[dict],
    salt_hex: str,
    enc_key_hex: str,
) -> bool:
    if salt_hex not in remaining_salts:
        return False
    try:
        enc_key = bytes.fromhex(enc_key_hex)
    except ValueError:
        return False

    for db in db_files:
        if db["salt"] != salt_hex:
            continue
        if verify_key_for_db(enc_key, db["page1"]):
            key_map[salt_hex] = enc_key_hex.lower()
            remaining_salts.discard(salt_hex)
            return True
    return False


def scan_process_memory(lldb, process, db_files: list[dict], salt_to_dbs: dict[str, list[str]]) -> dict:
    regions = readable_regions(lldb, process)
    total_bytes = sum(size for _, size in regions)
    key_map: dict[str, str] = {}
    remaining_salts = set(salt_to_dbs)
    hex_matches = 0
    scanned_bytes = 0

    print(f"regions={len(regions)}")
    print(f"scan_mb={total_bytes // 1024 // 1024}")

    error = lldb.SBError()
    for idx, (base, size) in enumerate(regions):
        offset = 0
        carry = b""
        while offset < size:
            read_size = min(CHUNK_SIZE, size - offset)
            data = process.ReadMemory(base + offset, read_size, error)
            offset += read_size
            scanned_bytes += read_size
            if not error.Success() or not data:
                carry = b""
                continue

            chunk = carry + data
            carry = chunk[-256:] if len(chunk) > 256 else chunk

            for enc_key_hex, salt_hex in iter_hex_candidates(chunk):
                hex_matches += 1
                if salt_hex:
                    remember_key(key_map, remaining_salts, db_files, salt_hex, enc_key_hex)
                else:
                    for db in db_files:
                        if remember_key(key_map, remaining_salts, db_files, db["salt"], enc_key_hex):
                            break

        if (idx + 1) % 50 == 0 or idx == len(regions) - 1:
            print(
                "progress={:.1f}% found_salts={} patterns={}".format(
                    (scanned_bytes / total_bytes * 100) if total_bytes else 100,
                    len(key_map),
                    hex_matches,
                )
            )
        if not remaining_salts:
            break

    if remaining_salts and key_map:
        for db in db_files:
            salt_hex = db["salt"]
            if salt_hex not in remaining_salts:
                continue
            for known_key in list(key_map.values()):
                if remember_key(key_map, remaining_salts, db_files, salt_hex, known_key):
                    break

    return {
        "key_map": key_map,
        "remaining_salts": remaining_salts,
        "hex_matches": hex_matches,
        "regions": regions,
    }


def create_hook_breakpoints(target) -> int:
    locations = 0
    for name in HOOK_BREAKPOINT_NAMES:
        bp = target.BreakpointCreateByName(name)
        bp.SetAutoContinue(False)
        locations += bp.GetNumLocations()
    return locations


def register_value(frame, name: str) -> int:
    reg = frame.FindRegister(name)
    if not reg.IsValid():
        return 0
    try:
        return int(reg.GetValueAsUnsigned())
    except Exception:
        return 0


def first_register_value(frame, names: list[str]) -> int:
    for name in names:
        value = register_value(frame, name)
        if value:
            return value
    return 0


def frame_function_name(frame) -> str:
    try:
        name = frame.GetFunctionName()
        if name:
            return str(name)
    except Exception:
        pass

    try:
        symbol = frame.GetSymbol()
        if symbol.IsValid():
            name = symbol.GetName()
            if name:
                return str(name)
    except Exception:
        pass
    return ""


def symbol_name_matches(symbol_name: str, target_name: str) -> bool:
    if not symbol_name:
        return False
    tokens = [token for token in re.split(r"[^0-9A-Za-z_]+", symbol_name) if token]
    return target_name in tokens


def hook_key_argument_ranges(frame) -> list[tuple[int, int]]:
    function_name = frame_function_name(frame)
    ranges: list[tuple[int, int]] = []

    for spec in HOOK_KEY_ARGUMENT_SPECS:
        if not any(symbol_name_matches(function_name, name) for name in spec["names"]):
            continue
        key_ptr = first_register_value(frame, spec["ptr_regs"])
        key_len = first_register_value(frame, spec["len_regs"])
        if spec["len_unit"] == "bits":
            if key_len % 8 != 0:
                continue
            key_len //= 8
        if key_ptr and 0 < key_len <= MAX_HOOK_KEY_BYTES:
            ranges.append((key_ptr, key_len))

    if any(symbol_name_matches(function_name, name) for name in GENERIC_KEY_POINTER_SYMBOLS):
        seen_ptrs = {address for address, _ in ranges}
        for reg_name in GENERIC_KEY_POINTER_REGS:
            key_ptr = register_value(frame, reg_name)
            if key_ptr and key_ptr not in seen_ptrs:
                ranges.append((key_ptr, KEY_SIZE))
                seen_ptrs.add(key_ptr)

    return ranges


def decode_hook_key_buffer(data: bytes) -> list[bytes]:
    if not data:
        return []

    candidates: list[bytes] = []
    if len(data) == KEY_SIZE:
        candidates.append(data)

    text = data.split(b"\x00", 1)[0].strip()
    for enc_key_hex, _salt_hex in iter_hex_candidates(text):
        try:
            raw = bytes.fromhex(enc_key_hex)
        except ValueError:
            continue
        if len(raw) == KEY_SIZE:
            candidates.append(raw)

    deduped: list[bytes] = []
    seen: set[bytes] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


def extract_hook_key_candidates(lldb, process, frame) -> list[bytes]:
    candidates: list[bytes] = []
    seen: set[bytes] = set()

    for key_ptr, key_len in hook_key_argument_ranges(frame):
        error = lldb.SBError()
        raw = process.ReadMemory(key_ptr, key_len, error)
        if not error.Success() or not raw:
            continue

        for candidate in decode_hook_key_buffer(raw):
            if candidate in seen:
                continue
            seen.add(candidate)
            candidates.append(candidate)

    return candidates


def selected_frame_for_breakpoint(process):
    for thread in process:
        if thread.GetStopReason() != 3:  # lldb.eStopReasonBreakpoint
            continue
        frame = thread.GetFrameAtIndex(0)
        if frame.IsValid():
            return frame
    thread = process.GetSelectedThread()
    if thread.IsValid() and thread.GetNumFrames() > 0:
        return thread.GetFrameAtIndex(0)
    return None


def scan_aes_hook_keys(
    lldb,
    debugger,
    target,
    process,
    db_files: list[dict],
    salt_to_dbs: dict[str, list[str]],
    duration: int,
) -> dict:
    locations = create_hook_breakpoints(target)
    print(f"hook_breakpoint_locations={locations}")
    if locations == 0:
        return {"key_map": {}, "hook_hits": 0, "candidate_keys": 0}

    debugger.SetAsync(True)
    listener = debugger.GetListener()
    deadline = time_monotonic() + max(5, duration)
    key_map: dict[str, str] = {}
    remaining_salts = set(salt_to_dbs)
    seen_keys: set[bytes] = set()
    hook_hits = 0
    candidate_keys = 0

    process.Continue()
    while time_monotonic() < deadline and remaining_salts:
        event = lldb.SBEvent()
        if not listener.WaitForEvent(1, event):
            continue
        state = lldb.SBProcess.GetStateFromEvent(event)
        if state != lldb.eStateStopped:
            continue

        frame = selected_frame_for_breakpoint(process)
        if frame is not None:
            hook_hits += 1
            for raw_key in extract_hook_key_candidates(lldb, process, frame):
                if len(raw_key) != KEY_SIZE or raw_key in seen_keys:
                    continue
                seen_keys.add(raw_key)
                candidate_keys += 1
                key_hex = raw_key.hex()
                for db in db_files:
                    remember_key(key_map, remaining_salts, db_files, db["salt"], key_hex)
                    if not remaining_salts:
                        break

        process.Continue()

    try:
        process.Stop()
    except Exception:
        pass
    return {
        "key_map": key_map,
        "hook_hits": hook_hits,
        "candidate_keys": candidate_keys,
    }


def normalize_all_keys_owner(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass

    if os.geteuid() != 0:
        return
    uid_raw = os.environ.get("SUDO_UID", "").strip()
    gid_raw = os.environ.get("SUDO_GID", "").strip()
    if not uid_raw or not gid_raw:
        return
    try:
        uid = int(uid_raw)
        gid = int(gid_raw)
    except ValueError:
        return
    if uid <= 0 or gid <= 0:
        return
    try:
        os.chown(path, uid, gid)
        path.chmod(0o600)
    except OSError:
        pass


def write_all_keys(account_dir: Path, db_files: list[dict], key_map: dict[str, str]) -> Path:
    out: dict[str, dict[str, str]] = {}
    for db in db_files:
        key = key_map.get(db["salt"])
        if key:
            out[db["rel"]] = {"enc_key": key.lower()}
    if not out:
        raise RuntimeError("no verified keys found")

    path = account_dir / "all_keys.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    normalize_all_keys_owner(path)
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan macOS WeChat memory for DB keys")
    parser.add_argument("--pid", type=int, default=0)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--mode", choices=["scan", "aes-hook"], default="scan")
    parser.add_argument("--duration", type=int, default=45)
    return parser.parse_args(argv)


def time_monotonic() -> float:
    import time
    return time.monotonic()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    account_dir, db_storage = resolve_db_storage(Path(args.data_dir))
    if not db_storage.is_dir():
        print(f"db_storage=missing: {db_storage}", file=sys.stderr)
        return 1

    db_files, salt_to_dbs = collect_db_files(db_storage)
    print(f"dbs={len(db_files)} salts={len(salt_to_dbs)}")
    if not db_files or not salt_to_dbs:
        print("no encrypted db files found", file=sys.stderr)
        return 1

    lldb = import_lldb()
    debugger = None
    process = None
    try:
        debugger, process = attach_process(lldb, args.pid)
        print(f"attached_pid={process.GetProcessID()}")
        if args.mode == "aes-hook":
            scan = scan_aes_hook_keys(
                lldb,
                debugger,
                debugger.GetSelectedTarget(),
                process,
                db_files,
                salt_to_dbs,
                args.duration,
            )
        else:
            scan = scan_process_memory(lldb, process, db_files, salt_to_dbs)
    finally:
        if process is not None:
            process.Detach()
            print("detached=yes")
        if debugger is not None:
            lldb.SBDebugger.Destroy(debugger)

    key_map = scan["key_map"]
    if not key_map:
        if args.mode == "aes-hook":
            print(f"found_key_entries=0 hook_hits={scan.get('hook_hits', 0)} candidate_keys={scan.get('candidate_keys', 0)}")
        else:
            print(f"found_key_entries=0 patterns={scan['hex_matches']}")
        return 1

    keys_path = write_all_keys(account_dir, db_files, key_map)
    missing = len({db["salt"] for db in db_files} - set(key_map))
    print(f"all_keys={keys_path}")
    print(f"found_salts={len(key_map)} missing_salts={missing}")
    print(f"valid_key_entries={sum(1 for db in db_files if db['salt'] in key_map)}")
    return 0 if missing == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
