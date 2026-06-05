"""
DLL injector — starts WeChat suspended, injects keyhook.dll, resumes.

The DLL hooks wcdb_open_account() to capture the WCDB hex key,
writing it to a temp file for us to read.

Usage:
    from .native.injector import inject_and_capture_key
    key = inject_and_capture_key()   # Returns hex key string or None
"""
import ctypes as ct
from ctypes import wintypes
import logging
import os
import struct
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

kernel32 = ct.WinDLL("kernel32", use_last_error=True)
advapi32 = ct.WinDLL("advapi32", use_last_error=True)

# ── Win32 API declarations ─────────────────────────────────────────────

PROCESS_ALL_ACCESS = 0x1F0FFF
PROCESS_TERMINATE = 0x0001
PROCESS_CREATE_THREAD = 0x0002
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_WRITE = 0x0020
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
PAGE_READWRITE = 0x04
CREATE_SUSPENDED = 0x00000004
INFINITE = 0xFFFFFFFF
WAIT_TIMEOUT = 0x00000102

TH32CS_SNAPPROCESS = 0x00000002

kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.VirtualAllocEx.restype = ct.c_void_p
kernel32.VirtualAllocEx.argtypes = [
    wintypes.HANDLE, ct.c_void_p, ct.c_size_t, wintypes.DWORD, wintypes.DWORD,
]
kernel32.WriteProcessMemory.restype = wintypes.BOOL
kernel32.CreateRemoteThread.restype = wintypes.HANDLE
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.ResumeThread.restype = wintypes.DWORD
kernel32.TerminateProcess.restype = wintypes.BOOL

# ── WeChat process management ────────────────────────────────────────────

def _find_wechat_pid():
    """Find a running WeChat process PID."""
    class PROCESSENTRY32W(ct.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ct.c_void_p),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD), ("szExeFile", ct.c_wchar * 260),
        ]

    h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if h_snap == -1:
        return None

    pe = PROCESSENTRY32W()
    pe.dwSize = ct.sizeof(PROCESSENTRY32W)
    if kernel32.Process32FirstW(h_snap, ct.byref(pe)):
        while True:
            name = pe.szExeFile.lower()
            if "weixin" in name or "wechat" in name:
                kernel32.CloseHandle(h_snap)
                return pe.th32ProcessID, pe.szExeFile
            if not kernel32.Process32NextW(h_snap, ct.byref(pe)):
                break
    kernel32.CloseHandle(h_snap)
    return None, None


def _find_wechat_exe():
    """Find WeChat.exe path from running process or registry."""
    # 1. From running process
    class MODULEENTRY32W(ct.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("th32ModuleID", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD), ("GlblcntUsage", wintypes.DWORD),
            ("ProccntUsage", wintypes.DWORD), ("modBaseAddr", ct.c_void_p),
            ("modBaseSize", wintypes.DWORD), ("hModule", wintypes.HMODULE),
            ("szModule", ct.c_wchar * 256), ("szExePath", ct.c_wchar * 260),
        ]

    pid, _ = _find_wechat_pid()
    if pid:
        h_snap = kernel32.CreateToolhelp32Snapshot(0x00000008 | 0x00000010, pid)
        if h_snap != -1:
            me = MODULEENTRY32W()
            me.dwSize = ct.sizeof(MODULEENTRY32W)
            if kernel32.Module32FirstW(h_snap, ct.byref(me)):
                while True:
                    if me.szExePath and os.path.exists(me.szExePath):
                        kernel32.CloseHandle(h_snap)
                        return me.szExePath
                    if not kernel32.Module32NextW(h_snap, ct.byref(me)):
                        break
            kernel32.CloseHandle(h_snap)

    # 2. From registry
    try:
        import winreg
        for sub in [r"Software\Tencent\WeChat", r"Software\Tencent\Weixin"]:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub)
                path, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                exe = Path(path) / "Weixin.exe"
                if exe.exists():
                    return str(exe)
                exe = Path(path) / "WeChat.exe"
                if exe.exists():
                    return str(exe)
            except OSError:
                pass
    except Exception:
        pass

    # 3. Common install paths
    common = [
        r"C:\Program Files\Tencent\Weixin\Weixin.exe",
        r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
    ]
    for p in common:
        if os.path.exists(p):
            return p

    return None


# ── DLL injection ────────────────────────────────────────────────────────

def _allocate_and_write(handle, data):
    """Allocate memory in target process and write data. Returns address."""
    size = len(data)
    raw = kernel32.VirtualAllocEx(
        handle, None, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
    )
    if not raw:
        return None
    addr = ct.c_void_p(raw)
    written = ct.c_size_t(0)
    kernel32.WriteProcessMemory(handle, addr, data, size, ct.byref(written))
    return addr


def inject_dll(pid, dll_path):
    """Inject a DLL into a running process via CreateRemoteThread + LoadLibraryA.

    Returns True on success.
    """
    h_process = kernel32.OpenProcess(
        PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION
        | PROCESS_VM_WRITE | PROCESS_VM_READ | PROCESS_QUERY_INFORMATION,
        False, pid,
    )
    if not h_process:
        logger.error("Failed to open process %d (error %d)", pid, kernel32.GetLastError())
        return False

    # Write DLL path to target process
    dll_bytes = dll_path.encode("utf-8") + b"\x00"
    dll_addr = _allocate_and_write(h_process, dll_bytes)
    if not dll_addr:
        kernel32.CloseHandle(h_process)
        return False

    # Get LoadLibraryA address (same in all processes for kernel32.dll)
    kernel32_handle = ct.c_void_p()
    kernel32_handle.value = kernel32._handle
    load_library_addr = kernel32.GetProcAddress(
        ct.c_void_p(kernel32._handle), b"LoadLibraryA"
    )
    if not load_library_addr:
        logger.error("Failed to find LoadLibraryA")
        kernel32.CloseHandle(h_process)
        return False

    # Create remote thread
    h_thread = kernel32.CreateRemoteThread(
        h_process, None, 0,
        load_library_addr,
        dll_addr,
        0, None,
    )
    if not h_thread:
        logger.error("CreateRemoteThread failed (error %d)", kernel32.GetLastError())
        kernel32.CloseHandle(h_process)
        return False

    # Wait for DLL to initialize
    kernel32.WaitForSingleObject(h_thread, 5000)
    kernel32.CloseHandle(h_thread)
    kernel32.CloseHandle(h_process)
    return True


# ── Main API ──────────────────────────────────────────────────────────────

def inject_and_capture_key(timeout_sec=30):
    """Restart WeChat with DLL injection to capture the WCDB key.

    1. Kills any running WeChat
    2. Starts WeChat suspended
    3. Injects keyhook.dll
    4. Resumes WeChat
    5. Waits for the key file to appear
    6. Reads and returns the key

    Returns the hex key string, or None if extraction fails.
    """
    # Locate DLL
    dll_path = _find_hook_dll()
    if not dll_path:
        logger.error("keyhook.dll not found")
        return None

    # Find WeChat
    wechat_exe = _find_wechat_exe()
    if not wechat_exe:
        logger.error("WeChat not found on this system")
        return None

    logger.info("WeChat found: %s", wechat_exe)
    logger.info("Hook DLL: %s", dll_path)

    # Kill existing WeChat
    pid, _ = _find_wechat_pid()
    if pid:
        logger.info("Terminating existing WeChat (PID %d)...", pid)
        h = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if h:
            kernel32.TerminateProcess(h, 0)
            kernel32.CloseHandle(h)
        time.sleep(2)  # Wait for cleanup

    # Set up key output file
    output_file = os.path.join(tempfile.gettempdir(), "wcdb_key.txt")
    if os.path.exists(output_file):
        os.remove(output_file)

    # Start WeChat suspended
    logger.info("Starting WeChat suspended...")

    class STARTUPINFOW(ct.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("lpReserved", ct.c_wchar_p),
            ("lpDesktop", ct.c_wchar_p), ("lpTitle", ct.c_wchar_p),
            ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ct.c_void_p), ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE),
        ]

    class PROCESS_INFORMATION(ct.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD),
        ]

    si = STARTUPINFOW()
    si.cb = ct.sizeof(STARTUPINFOW)
    pi = PROCESS_INFORMATION()

    # Start WeChat with CREATE_SUSPENDED (DLL uses default temp path)
    success = ct.windll.kernel32.CreateProcessW(
        wechat_exe, None, None, None, False,
        CREATE_SUSPENDED, None, None, ct.byref(si), ct.byref(pi),
    )

    if not success:
        logger.error("CreateProcess failed (error %d)", kernel32.GetLastError())
        return None

    new_pid = pi.dwProcessId
    h_process = pi.hProcess
    h_thread = pi.hThread
    logger.info("WeChat started suspended (PID %d)", new_pid)

    # Inject DLL
    if not inject_dll(new_pid, dll_path):
        kernel32.TerminateProcess(h_process, 0)
        kernel32.CloseHandle(h_process)
        kernel32.CloseHandle(h_thread)
        return None

    logger.info("DLL injected, resuming WeChat...")

    # Resume WeChat
    kernel32.ResumeThread(h_thread)
    kernel32.CloseHandle(h_thread)
    kernel32.CloseHandle(h_process)

    # Wait for key file
    logger.info("Waiting for key (up to %d seconds)...", timeout_sec)
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            try:
                with open(output_file, "r") as f:
                    key = f.read().strip()
                if key and len(key) == 64:
                    logger.info("Key captured: %s...", key[:16])
                    os.remove(output_file)
                    return key
            except Exception:
                pass
        time.sleep(0.5)

    logger.error("Timeout waiting for key")
    return None


def _find_hook_dll():
    """Locate keyhook.dll: bundled lib/ first, then alongside this file."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent / "lib" / "keyhook.dll",
        Path(__file__).resolve().parent / "keyhook.dll",
    ]
    # PyInstaller bundle
    import sys
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys._MEIPASS) / "lib" / "keyhook.dll")
        candidates.insert(1, Path(sys.executable).resolve().parent / "lib" / "keyhook.dll")

    for c in candidates:
        if c.exists():
            return str(c)
    return None
