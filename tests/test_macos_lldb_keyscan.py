"""Tests for the macOS LLDB key scanner's pure parsing helpers."""

import importlib.util
import sys
from pathlib import Path


def _load_scanner_module():
    path = Path(__file__).resolve().parent.parent / "tools" / "macos_lldb_keyscan.py"
    spec = importlib.util.spec_from_file_location("macos_lldb_keyscan", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_iter_hex_candidates_accepts_quoted_key_salt_pattern():
    scanner = _load_scanner_module()
    key = "a" * 64
    salt = "b" * 32

    candidates = list(scanner.iter_hex_candidates(f"prefix x'{key}{salt}' suffix".encode()))

    assert candidates == [(key, salt)]


def test_iter_hex_candidates_accepts_key_only_pattern():
    scanner = _load_scanner_module()
    key = "c" * 64

    candidates = list(scanner.iter_hex_candidates(f"x'{key}'".encode()))

    assert candidates == [(key, None)]


def test_iter_hex_candidates_accepts_bare_key_salt_pattern():
    scanner = _load_scanner_module()
    key = "d" * 64
    salt = "e" * 32

    candidates = list(scanner.iter_hex_candidates(f" {key}{salt} ".encode()))

    assert candidates == [(key, salt)]


def test_iter_hex_candidates_rejects_embedded_bare_hex_pattern():
    scanner = _load_scanner_module()
    key = "f" * 64
    salt = "1" * 32

    candidates = list(scanner.iter_hex_candidates(f"0{key}{salt}2".encode()))

    assert candidates == []


def test_sqlite_header_tail_plausibility_matches_darwin_v4_page_body():
    scanner = _load_scanner_module()

    assert scanner.sqlite_header_tail_is_plausible(
        b"\x10\x00\x01\x01\x00\x40\x20\x20" + b"\x00" * 8
    )
    assert not scanner.sqlite_header_tail_is_plausible(b"not sqlite header")


def test_first_register_value_supports_arm64_and_x86_64_names():
    scanner = _load_scanner_module()

    class FakeRegister:
        def __init__(self, value):
            self.value = value

        def IsValid(self):
            return self.value is not None

        def GetValueAsUnsigned(self):
            return self.value

    class FakeFrame:
        def __init__(self, registers):
            self.registers = registers

        def FindRegister(self, name):
            return FakeRegister(self.registers.get(name))

    assert scanner.first_register_value(FakeFrame({"x0": 17}), ["x0", "rdi"]) == 17
    assert scanner.first_register_value(FakeFrame({"rdi": 23}), ["x0", "rdi"]) == 23
    assert scanner.first_register_value(FakeFrame({}), ["x0", "rdi"]) == 0


def test_add_lldb_python_path_discovers_lldb_p_path(monkeypatch):
    scanner = _load_scanner_module()
    original_path = list(sys.path)

    def fake_check_output(cmd, text=True, timeout=5):
        assert cmd == ["lldb", "-P"]
        return "/tmp/lldb-python\n"

    monkeypatch.setattr(scanner.subprocess, "check_output", fake_check_output)
    try:
        assert scanner.add_lldb_python_path("") is True
        assert sys.path[0] == "/tmp/lldb-python"
    finally:
        sys.path[:] = original_path
