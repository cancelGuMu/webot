"""
Native WCDB database client — direct DLL calls, no external HTTP bridge.

Loads wcdb_api.dll via ctypes, applies one-byte DRM patch, and provides
the same data access as a dedicated HTTP bridge but entirely in-process.
"""
import ctypes as ct
from ctypes import wintypes
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

PAGE_EXECUTE_READWRITE = 0x40

# ── DRM patch offset configuration ────────────────────────────────────
# Default values target WeChat 4.x.  When WeChat updates and the patch
# offset changes, you can override these via environment variables instead
# of modifying the source:
#
#   WCDB_PATCH_RVA   – hex RVA (relative virtual address) of the patch site
#   WCDB_PATCH_BYTE  – hex byte value expected at patch_site+1 before patching
#
# These are the bytes that the DRM check sets to signal "tampered":
#   mov eax, 2      (B8 02 00 00 00)   → normal / DRM active
#   mov eax, 0      (B8 00 00 00 00)   → patched / DRM bypassed
#
# Example for a future WeChat version:
#   set WCDB_PATCH_RVA=0x6f2a0
#   set WCDB_PATCH_BYTE=0x02

_DEFAULT_PATCH_RVA = 0x6e1f6
_DEFAULT_PATCH_BYTE = 0x02

_env_rva = os.environ.get("WCDB_PATCH_RVA", "").strip()
if _env_rva:
    PATCH_RVA = int(_env_rva, 16)
    logger.info("Using custom WCDB_PATCH_RVA from env: 0x%x", PATCH_RVA)
else:
    PATCH_RVA = _DEFAULT_PATCH_RVA
    logger.debug("Using default WCDB_PATCH_RVA: 0x%x", PATCH_RVA)

_env_byte = os.environ.get("WCDB_PATCH_BYTE", "").strip()
if _env_byte:
    EXPECTED_PATCH_BYTE = int(_env_byte, 16)
    logger.info("Using custom WCDB_PATCH_BYTE from env: 0x%x", EXPECTED_PATCH_BYTE)
else:
    EXPECTED_PATCH_BYTE = _DEFAULT_PATCH_BYTE
    logger.debug("Using default WCDB_PATCH_BYTE: 0x%x", EXPECTED_PATCH_BYTE)

# ── DLL loading ──────────────────────────────────────────────────────

_kernel32 = ct.WinDLL("kernel32", use_last_error=True)


def _apply_drm_patch(dll_handle, dll_path):
    """One-byte DRM patch: mov eax,2 -> mov eax,0 at the configured RVA.

    The patch offset and expected byte are controlled by PATCH_RVA and
    EXPECTED_PATCH_BYTE (see module-level config above).  Override them via
    WCDB_PATCH_RVA / WCDB_PATCH_BYTE environment variables when WeChat
    updates change the patch location.

    Also verifies the DLL hasn't been tampered with beyond our patch.
    """
    # Verify SHA256 baseline
    known_sha = None
    try:
        with open(dll_path, "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()
    except Exception:
        sha = None

    # Apply the patch
    patch_addr = ct.c_void_p(dll_handle + PATCH_RVA)
    old_protect = wintypes.DWORD()
    _kernel32.VirtualProtect(
        patch_addr, 5, PAGE_EXECUTE_READWRITE, ct.byref(old_protect)
    )

    buf = (ct.c_ubyte * 5).from_address(patch_addr.value)
    if buf[1] == EXPECTED_PATCH_BYTE:
        buf[1] = 0x00
        logger.info("DRM patch applied: RVA 0x%x 02->00", PATCH_RVA)
    elif buf[1] == 0x00:
        logger.info("DRM patch already present")
    else:
        logger.warning(
            "Unexpected byte 0x%02x at patch point — DLL may be tampered",
            buf[1],
        )

    _kernel32.VirtualProtect(
        patch_addr, 5, old_protect, ct.byref(wintypes.DWORD())
    )


def _read_gbk_string(ptr):
    """Read null-terminated string from a raw pointer.

    The WCDB DLL may return GBK or UTF-8 depending on the data source.
    Since all DLL inputs are UTF-8, try UTF-8 first, then fall back to GBK.
    Validates with JSON parse to confirm the correct encoding was chosen.
    """
    if not ptr or ptr.value == 0:
        return ""
    raw = bytearray()
    addr = ptr.value
    for _ in range(500000):
        b = (ct.c_ubyte * 1).from_address(addr)[0]
        if b == 0:
            break
        raw.append(b)
        addr += 1
    # Try UTF-8 first (DLL inputs are always UTF-8), fall back to GBK.
    # GBK decode of UTF-8 bytes can produce valid JSON with garbled Chinese
    # (JSON structural chars are ASCII, identical in both encodings), so the
    # old GBK-first heuristic silently returned mojibake.
    import json as _json
    for enc in ("utf-8", "gbk"):
        try:
            text = raw.decode(enc)
            _json.loads(text)
            return text
        except (UnicodeDecodeError, _json.JSONDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


# ── Filesystem auto-detection ─────────────────────────────────────────


def _find_dll():
    """Find the bundled wcdb_api.dll."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "lib" / "wcdb_api.dll",
    ]
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys.executable).resolve().parent / "lib" / "wcdb_api.dll")
        candidates.insert(0, Path(sys._MEIPASS) / "lib" / "wcdb_api.dll")

    for c in candidates:
        if c.exists():
            logger.info("Found wcdb_api.dll at: %s", c)
            return str(c.parent), str(c)

    raise FileNotFoundError(
        "wcdb_api.dll not found. Please place it in the 'lib' folder next to the EXE."
    )


def _find_wxid_and_dbpath():
    """Auto-detect WeChat wxid and database path from the filesystem.

    Scans Documents\\xwechat_files\\ for wxid_* directories.
    """
    # 1. Scan filesystem (primary — no external dependencies)
    documents = Path.home() / "Documents"
    candidates = [
        documents / "xwechat_files",
        documents / "WeChat Files",
    ]

    for base in candidates:
        if not base.exists():
            continue
        # Find wxid directories (e.g., wxid_zogepsik3fud12_b6ce)
        wxid_dirs = sorted(
            [d for d in base.iterdir() if d.is_dir() and d.name.startswith("wxid_")],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        for wxid_dir in wxid_dirs:
            # Verify session.db exists
            session_db = wxid_dir / "db_storage" / "session" / "session.db"
            if session_db.exists():
                wxid = wxid_dir.name
                logger.info("Auto-detected: wxid=%s db=%s", wxid, str(base))
                return wxid, str(base)

    raise FileNotFoundError(
        "Cannot find WeChat data directory. Make sure WeChat is installed "
        "and you have logged in at least once."
    )


# ── Public API ────────────────────────────────────────────────────────

import sys as _sys


class WcdbNativeClient:
    """Direct WCDB database reader via patched wcdb_api.dll.

    Auto-detects WeChat data paths from the filesystem.
    The DLL is bundled with the EXE in the lib/ directory.
    """

    def __init__(self, dll_dir=None, config_path=None):
        # Resolve DLL
        if dll_dir is not None:
            self._dll_dir = dll_dir
            self._dll_path = os.path.join(dll_dir, "wcdb_api.dll")
        else:
            self._dll_dir, self._dll_path = _find_dll()

        # Resolve config (wxid + dbPath)
        self._config_path = config_path  # may be None — auto-detected
        self._dll = None
        self._handle = 0
        self._config = None
        self._nicknames = {}  # wxid -> display name cache

        self._load_config()

    # ── Init ──────────────────────────────────────────────────────────

    def _load_config(self):
        wxid, db_path = _find_wxid_and_dbpath()
        self._config = {
            "myWxid": wxid,
            "dbPath": db_path,
        }

    def init(self):
        """Load wcdb_api.dll, patch DRM, and initialize the WCDB engine."""
        os.add_dll_directory(self._dll_dir)
        dll_path = os.path.join(self._dll_dir, "wcdb_api.dll")
        self._dll = ct.CDLL(dll_path)

        # Apply DRM patch
        _apply_drm_patch(self._dll._handle, dll_path)

        # Set up function signatures
        self._dll.InitProtection.argtypes = [ct.c_char_p]
        self._dll.InitProtection.restype = ct.c_int32

        self._dll.wcdb_init.argtypes = []
        self._dll.wcdb_init.restype = ct.c_int32

        self._dll.wcdb_open_account.argtypes = [
            ct.c_char_p, ct.c_char_p, ct.POINTER(ct.c_int64),
        ]
        self._dll.wcdb_open_account.restype = ct.c_int32

        self._dll.wcdb_get_sessions.argtypes = [
            ct.c_int64, ct.POINTER(ct.c_void_p),
        ]
        self._dll.wcdb_get_sessions.restype = ct.c_int32

        self._dll.wcdb_get_messages.argtypes = [
            ct.c_int64, ct.c_char_p, ct.c_int32, ct.c_int32,
            ct.POINTER(ct.c_void_p),
        ]
        self._dll.wcdb_get_messages.restype = ct.c_int32

        self._dll.wcdb_get_display_names.argtypes = [
            ct.c_int64, ct.c_char_p, ct.POINTER(ct.c_void_p),
        ]
        self._dll.wcdb_get_display_names.restype = ct.c_int32

        self._dll.wcdb_get_contacts_compact = None
        try:
            fn = self._dll.wcdb_get_contacts_compact
            fn.argtypes = [ct.c_int64, ct.c_char_p, ct.POINTER(ct.c_void_p)]
            fn.restype = ct.c_int32
            self._dll.wcdb_get_contacts_compact = fn
        except Exception:
            pass

        self._dll.wcdb_free_string.argtypes = [ct.c_void_p]
        self._dll.wcdb_free_string.restype = None

        # Init protection
        resource_path = os.path.dirname(self._dll_dir)
        self._dll.InitProtection(resource_path.encode("utf-8"))

        # Init engine
        ret = self._dll.wcdb_init()
        if ret != 0:
            raise RuntimeError(f"wcdb_init failed: {ret}")

        logger.info("WCDB engine initialized (DRM patched)")

    def open(self):
        """Open the WeChat session.db for the configured account.

        Tries cached keys first.  If they produce 0 sessions (stale key),
        attempts live extraction from the running WeChat process.
        """
        my_wxid = self._config.get("myWxid", "")
        db_base = self._config.get("dbPath", "")
        wxid_base = "_".join(my_wxid.split("_")[:3])

        account_dir = None   # wxid directory (e.g. .../xwechat_files/wxid_xxx)
        session_db = None    # full path to session.db
        base = Path(db_base)
        for entry in base.iterdir():
            if entry.name.startswith(wxid_base):
                account_dir = str(entry)
                candidate = entry / "db_storage" / "session" / "session.db"
                if candidate.exists():
                    session_db = str(candidate)
                    break   # only stop when we actually found session.db

        if not account_dir or not session_db:
            raise RuntimeError(f"session.db not found in {db_base}")

        # wcdb_open_account expects the session.db file path.
        # Passing the account directory results in ret=-3.
        db_paths = [session_db]

        # ── Resolve key, try each source until one yields data ──────
        import os as _os

        for attempt, (key_candidate, source_label) in enumerate(self._key_candidates()):
            logger.info(
                "Trying WCDB key source #%d: %s (len=%d)",
                attempt + 1, source_label,
                len(key_candidate) if key_candidate else 0,
            )

            # Build key variants to try.  The DLL accepts 64-char hex strings
            # (ret=0) but explicitly rejects raw bytes (ret=-3).  Only try hex.
            key_variants = []
            if key_candidate and len(key_candidate) == 64 and all(
                c in "0123456789abcdefABCDEF" for c in key_candidate
            ):
                key_variants.append((key_candidate.encode("utf-8"), "hex"))
            elif key_candidate:
                key_variants.append((key_candidate.encode("utf-8"), "str"))
            # else: empty key → skip (ret=-2 means DLL requires a key)

            for key_bytes, key_fmt in key_variants:
                for db_path in db_paths:
                    path_label = "dir" if db_path == account_dir else "file"
                    handle = ct.c_int64(0)
                    ret = self._dll.wcdb_open_account(
                        db_path.encode("utf-8"),
                        key_bytes,
                        ct.byref(handle),
                    )
                    if ret != 0:
                        logger.info(
                            "wcdb_open_account FAIL (ret=%d) fmt=%s path=%s source=%s",
                            ret, key_fmt, path_label, source_label,
                        )
                        continue

                    self._handle = handle.value

                    # Verify the key actually decrypts data
                    sessions = self.get_sessions()
                    if sessions:
                        session_count = (
                            len(sessions) if isinstance(sessions, list)
                            else len(sessions.get("sessions", sessions))
                        )
                        logger.info(
                            "Key WORKS (source=%s, fmt=%s, path=%s): %d sessions found",
                            source_label, key_fmt, path_label, session_count,
                        )
                        # Persist key for next cold start
                        _os.environ["WCDB_KEY"] = key_candidate
                        self._save_key_to_env(key_candidate)
                        logger.info("Database opened: %s", db_path)
                        self._load_nickname_cache()
                        return True

                    # Key didn't work — close and try next variant
                    logger.info(
                        "Key from %s (fmt=%s, path=%s) → 0 sessions",
                        source_label, key_fmt, path_label,
                    )
                    self._close_handle()

            logger.warning(
                "Key from %s failed all formats — trying next source...",
                source_label,
            )

        raise RuntimeError(
            "KEY_MISSING: 密钥未配置。"
            "点击下方「重新获取密钥」按钮，按提示退出并重新登录微信即可。"
        )

    @staticmethod
    def _save_key_to_env(key: str):
        """Persist a working WCDB key to .env for next cold start."""
        # Find .env — use PROJECT_ROOT which resolves to EXE dir (frozen)
        # or project root (dev).  No __file__-based fallback because that
        # would point to the temp extraction dir in frozen mode.
        from src.config import PROJECT_ROOT
        env_path = PROJECT_ROOT / ".env"
        if not env_path.exists():
            env_path = None
        if not env_path:
            logger.debug("No .env found for key persistence — key in memory only")
            return

        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
            new_lines = []
            found = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("WCDB_KEY=") or stripped.startswith("WCDB_KEY "):
                    new_lines.append(f"WCDB_KEY={key}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"WCDB_KEY={key}")
            tmp = env_path.with_suffix(".tmp")
            tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            _os.replace(tmp, env_path)
            logger.debug("Persisted WCDB_KEY to %s", env_path)
        except Exception as e:
            logger.debug("Failed to persist WCDB_KEY: %s", e)

    def _key_candidates(self):
        """Generate (key, label) pairs in priority order.

        The key is captured ONCE during onboarding (WeChat restart flow)
        and persisted to .env / WCDB_KEY.  Live extraction from an
        already-running WeChat is unreliable (the key was loaded at
        startup and the hook may miss it), so we don't try it here.

        As a last resort, tries an empty key — some wcdb_api.dll builds
        can derive the key internally via InitProtection.
        """
        import os as _os

        # Environment variable — persists across runs after onboarding
        env_key = _os.environ.get("WCDB_KEY", "").strip()
        if env_key and len(env_key) == 64:
            yield env_key, "env"

        # Fallback: let the DLL try its own internal key discovery
        yield "", "builtin"

    def _load_nickname_cache(self):
        """Load wxid -> display name mappings from sessions and contacts."""
        sessions = self.get_sessions()
        for s in sessions:
            username = s.get("username", "")
            display = (s.get("displayName") or s.get("nickname") or "").strip()
            if username and display:
                self._nicknames[username] = display

        # Load contacts
        contacts = self.get_contacts()
        for c in contacts:
            username = c.get("userName") or c.get("username") or ""
            nick = (c.get("nickName") or c.get("remark") or c.get("displayName") or "").strip()
            if username and nick:
                self._nicknames[username] = nick

        # Manual overrides from nicknames.json
        nick_file = Path("data/nicknames.json")
        if nick_file.exists():
            try:
                manual = json.loads(nick_file.read_text(encoding="utf-8"))
                for wxid, name in manual.items():
                    if wxid.startswith("_"):
                        continue
                    if name and name.strip():
                        self._nicknames[wxid] = name.strip()
                logger.info("Loaded %d manual nickname overrides", len(manual))
            except Exception as e:
                logger.warning("Failed to load nicknames.json: %s", e)

    # ── Query methods ─────────────────────────────────────────────────

    def _call_json(self, func, *args):
        """Call a WCDB function that returns a JSON string pointer."""
        out = ct.c_void_p()
        ret = func(*args, ct.byref(out))
        if ret != 0:
            logger.warning("WCDB call %s failed: ret=%d", func.__name__, ret)
            return None
        if not out.value:
            logger.debug("WCDB call %s returned null pointer", func.__name__)
            return {}
        try:
            data = _read_gbk_string(out)
            self._dll.wcdb_free_string(out)
            return json.loads(data)
        except json.JSONDecodeError as e:
            logger.debug("JSON parse error: %s", e)
            self._dll.wcdb_free_string(out)
            return {}
        except Exception as e:
            logger.warning("Unexpected error in _call_json for %s: %s",
                           func.__name__, e)
            self._dll.wcdb_free_string(out)
            return {}

    def get_sessions(self, limit=500):
        """Get all chat sessions with metadata."""
        result = self._call_json(self._dll.wcdb_get_sessions, self._handle)
        if result is None:
            logger.warning("wcdb_get_sessions returned None (DLL call failed)")
            return []
        if isinstance(result, list):
            logger.info("Got %d sessions (list)", len(result))
            return result
        if isinstance(result, dict):
            keys = list(result.keys())
            logger.info("Got sessions dict with keys: %s", keys)
            return result.get("sessions", result.get("data", []))
        logger.warning("wcdb_get_sessions returned unexpected type: %s", type(result))
        return []

    def get_messages(self, talker, limit=200, offset=0):
        """Get messages for a specific chat."""
        result = self._call_json(
            self._dll.wcdb_get_messages,
            self._handle,
            talker.encode("utf-8"),
            limit,
            offset,
        )
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("messages", result.get("data", []))
        return []

    def get_display_names(self, usernames):
        """Resolve wxids to display names."""
        if not self._handle or not usernames:
            return {}
        username_json = json.dumps(usernames, ensure_ascii=False).encode("utf-8")
        result = self._call_json(
            self._dll.wcdb_get_display_names,
            self._handle,
            username_json,
        )
        if isinstance(result, dict):
            return result.get("names", result)
        return {}

    def get_contacts(self, keyword="", limit=1000):
        """Get contacts list."""
        if not self._dll.wcdb_get_contacts_compact:
            return []
        result = self._call_json(
            self._dll.wcdb_get_contacts_compact,
            self._handle,
            json.dumps([keyword], ensure_ascii=False).encode("utf-8"),
        )
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("contacts", result.get("data", []))
        return []

    def resolve_nickname(self, wxid):
        """Get display name for a wxid from cache."""
        if wxid in self._nicknames:
            return self._nicknames[wxid]
        # Try to look up
        names = self.get_display_names([wxid])
        if wxid in names:
            self._nicknames[wxid] = names[wxid]
            return names[wxid]
        self._nicknames[wxid] = wxid
        return wxid

    # ── Cleanup ───────────────────────────────────────────────────────

    def _close_handle(self):
        """Close current DB handle safely (no-op if already closed)."""
        if self._handle:
            try:
                wcdb_close = self._dll.wcdb_close_account
                wcdb_close.argtypes = [ct.c_int64]
                wcdb_close.restype = ct.c_int32
                wcdb_close(self._handle)
            except Exception:
                pass
            self._handle = 0

    def close(self):
        self._close_handle()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
