"""
Memory scanner to find WCDB key from WeChat process.
Scans WeChatWin.dll memory for 64-char hex strings.
"""
import ctypes as ct
from ctypes import wintypes
import os
import sys
from pathlib import Path

def find_wechat_pids():
    """Find WeChat process PIDs (skip webot.exe)."""
    kernel32 = ct.WinDLL("kernel32", use_last_error=True)
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32W(ct.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ct.c_void_p),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ct.c_wchar * 260),
        ]

    my_pid = os.getpid()
    pids = []

    h = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if h == -1:
        return []
    pe = PROCESSENTRY32W()
    pe.dwSize = ct.sizeof(PROCESSENTRY32W)
    if kernel32.Process32FirstW(h, ct.byref(pe)):
        while True:
            name = pe.szExeFile.lower()
            if pe.th32ProcessID != my_pid and ("weixin" in name or "wechat" in name):
                pids.append(pe.th32ProcessID)
            if not kernel32.Process32NextW(h, ct.byref(pe)):
                break
    kernel32.CloseHandle(h)
    return pids

def find_wechat_base_module(pids):
    """Get WeChatWin.dll base address and size."""
    kernel32 = ct.WinDLL("kernel32", use_last_error=True)

    PROCESS_VM_READ = 0x0010
    PROCESS_QUERY_INFORMATION = 0x0400
    TH32CS_SNAPMODULE = 0x00000008

    class MODULEENTRY32W(ct.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("th32ModuleID", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("GlblcntUsage", wintypes.DWORD),
            ("ProccntUsage", wintypes.DWORD),
            ("modBaseAddr", ct.c_void_p),
            ("modBaseSize", wintypes.DWORD),
            ("hModule", wintypes.HMODULE),
            ("szModule", ct.c_wchar * 256),
            ("szExePath", ct.c_wchar * 260),
        ]

    for pid in pids:
        h_process = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not h_process:
            continue

        h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
        if h_snap == -1:
            continue

        me = MODULEENTRY32W()
        me.dwSize = ct.sizeof(MODULEENTRY32W)

        if kernel32.Module32FirstW(h_snap, ct.byref(me)):
            while True:
                name = me.szModule.lower()
                if "wechatwin" in name:
                    base = me.modBaseAddr
                    size = me.modBaseSize
                    print(f"WeChatWin.dll: base=0x{base:X}, size={size//1024//1024}MB")
                    return base, size
                if not kernel32.Module32NextW(h_snap, ct.byref(me)):
                    break
        kernel32.CloseHandle(h_snap)
        kernel32.CloseHandle(h_process)

def scan_memory_for_key(pid, base, size):
    """Scan WeChatWin.dll memory for WCDB key hex strings."""
    kernel32 = ct.WinDLL("kernel32", use_last_error=True)

    h_process = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h_process:
        print(f"Failed to open process {pid}: error {ct.get_last_error()}")
        return None

    try:
        # Scan in 64KB chunks
        CHUNK = 64 * 1024  # 64KB
        buf = ct.create_string_buffer(CHUNK)
        bytes_read = ct.c_size_t(0)

        key = None
        offset = 0
        hex_chars = set("0123456789abcdefABCDEF")

        while offset < size:
            to_read = min(CHUNK, size - offset)
            if not kernel32.ReadProcessMemory(h_process, ct.c_void_p(base + offset), buf, to_read, ct.byref(bytes_read)):
                break

            data = bytes(buf)
            for i in range(bytes_read.value):
                ch = chr(data[i])
                if ch in hex_chars:
                    if offset % 2 == 0:  # Every other byte is hex
                        key_candidate = data[i:i+64]
                        # Try to find 64 consecutive hex chars
            offset += to_read

        kernel32.CloseHandle(h_process)
        return key

if __name__ == "__main__":
    pids = find_wechat_pids()
    print(f"Found {len(pids)} WeChat processes")
    for pid in pids:
        base, size = find_wechat_base_module(pids)
        if base and size:
            print(f"Scanning WeChatWin.dll...")
            key = scan_memory_for_key(pid, base, size)
            if key:
                print(f"Key found: {key[:16]}...")
            else:
                print("No key found in any process")
