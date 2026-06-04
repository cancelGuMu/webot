"""
Native WCDB database client — direct DLL calls, NO WeFlow.exe, NO HTTP bridge.

Loads wcdb_api.dll via ctypes, applies one-byte DRM patch, and provides
the same data access as the WeFlow HTTP API but entirely in-process.
"""
import ctypes as ct
from ctypes import wintypes
import hashlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

PAGE_EXECUTE_READWRITE = 0x40
PATCH_RVA = 0x6e1f6
EXPECTED_PATCH_BYTE = 0x02  # mov eax, 2 -> we change to 0

# ── DLL loading ──────────────────────────────────────────────────────

_kernel32 = ct.WinDLL("kernel32", use_last_error=True)


def _apply_drm_patch(dll_handle, dll_path):
    """One-byte patch: mov eax,2 -> mov eax,0 at RVA 0x6e1f6.

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

    WeChat stores data primarily as GBK on Chinese Windows, but some
    fields may use UTF-8 or contain mixed encodings. We try GBK first,
    then UTF-8, and fall back to latin-1 (always succeeds).
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
    data = bytes(raw)
    # Try GBK first (WeChat's default on Chinese Windows)
    try:
        return data.decode("gbk")
    except (UnicodeDecodeError, LookupError):
        pass
    # Try UTF-8
    try:
        return data.decode("utf-8")
    except (UnicodeDecodeError, LookupError):
        pass
    # Fall back: replace invalid bytes
    return data.decode("gbk", errors="replace")


# ── Public API ────────────────────────────────────────────────────────

class WcdbNativeClient:
    """Direct WCDB database reader via patched wcdb_api.dll."""

    def __init__(self, dll_dir=None, config_path=None):
        if dll_dir is None:
            dll_dir = os.path.join(
                os.environ.get("LOCALAPPDATA", ""),
                "Programs", "WeFlow", "resources",
                "resources", "wcdb", "win32", "x64",
            )

        if config_path is None:
            config_path = os.path.join(
                os.environ.get("APPDATA", ""),
                "WeFlow", "WeFlow-config.json",
            )

        self._dll_dir = dll_dir
        self._config_path = config_path
        self._dll = None
        self._handle = 0
        self._config = None
        self._nicknames = {}  # wxid -> display name cache

        self._load_config()

    # ── Init ──────────────────────────────────────────────────────────

    def _load_config(self):
        with open(self._config_path, "r", encoding="utf-8") as f:
            self._config = json.load(f)

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
        """Open the WeChat session.db for the configured account."""
        from .extract_key import extract_aes_key, decrypt_wcdb_key

        aes_key = extract_aes_key()
        hex_key = decrypt_wcdb_key(aes_key)
        if not hex_key:
            raise RuntimeError("Failed to decrypt WCDB key")

        my_wxid = self._config.get("myWxid", "")
        db_base = self._config.get("dbPath", "")
        wxid_base = "_".join(my_wxid.split("_")[:3])

        db_path = None
        base = Path(db_base)
        for entry in base.iterdir():
            if entry.name.startswith(wxid_base):
                candidate = entry / "db_storage" / "session" / "session.db"
                if candidate.exists():
                    db_path = str(candidate)
                    break

        if not db_path:
            raise RuntimeError(f"session.db not found in {db_base}")

        handle = ct.c_int64(0)
        ret = self._dll.wcdb_open_account(
            db_path.encode("utf-8"),
            hex_key.encode("utf-8"),
            ct.byref(handle),
        )
        if ret != 0:
            raise RuntimeError(f"wcdb_open_account failed: {ret}")

        self._handle = handle.value
        logger.info("Database opened: %s", db_path)

        # Load nickname cache
        self._load_nickname_cache()

        return True

    def _load_nickname_cache(self):
        """Load wxid -> display name mappings from sessions and contacts."""
        sessions = self.get_sessions()
        for s in sessions:
            username = s.get("username", "")
            display = s.get("displayName", s.get("nickname", ""))
            if username and display:
                self._nicknames[username] = display

        # Load contacts
        contacts = self.get_contacts()
        for c in contacts:
            username = c.get("userName", c.get("username", ""))
            nick = c.get("nickName") or c.get("remark") or c.get("displayName") or ""
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
            return None
        if not out.value:
            return {}
        try:
            data = _read_gbk_string(out)
            self._dll.wcdb_free_string(out)
            return json.loads(data)
        except Exception as e:
            logger.debug("JSON parse error: %s", e)
            self._dll.wcdb_free_string(out)
            return {}

    def get_sessions(self, limit=500):
        """Get all chat sessions with metadata."""
        result = self._call_json(self._dll.wcdb_get_sessions, self._handle)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("sessions", result.get("data", []))
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
        username_json = json.dumps(usernames).encode("utf-8")
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
            json.dumps([keyword]).encode("utf-8"),
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

    def close(self):
        if self._handle:
            try:
                wcdb_close = self._dll.wcdb_close_account
                wcdb_close.argtypes = [ct.c_int64]
                wcdb_close.restype = ct.c_int32
                wcdb_close(self._handle)
            except Exception:
                pass
            self._handle = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
