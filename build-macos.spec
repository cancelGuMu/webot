# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the macOS webot app.

Build: .venv/bin/pyinstaller build-macos.spec
Output: dist/webot.app
"""
import os
from pathlib import Path

MACOS_CODESIGN_IDENTITY = os.getenv("MACOS_CODESIGN_IDENTITY") or None
MACOS_ENTITLEMENTS_FILE = "macos-entitlements.plist"
PROJECT_ROOT = Path(SPECPATH)
WEFLOW_WCDB_DIR = PROJECT_ROOT / "resources" / "wcdb" / "macos" / "universal"
WEFLOW_WCDB_BINARIES = [
    (str(path), "resources/wcdb/macos/universal")
    for path in (WEFLOW_WCDB_DIR / "libWCDB.dylib",)
    if path.exists()
]

a = Analysis(
    ["desktop_mac.py"],
    pathex=[],
    binaries=WEFLOW_WCDB_BINARIES,
    datas=[
        ("ui/dist", "ui/dist"),
        (".env.example", "."),
    ],
    hiddenimports=[
        "src",
        "src.admin",
        "src.bot",
        "src.config",
        "src.db",
        "src.db.schema",
        "src.db.store",
        "src.fun",
        "src.integrations",
        "src.integrations.feishu",
        "src.integrations.feishu.client",
        "src.integrations.feishu.exporter",
        "src.memory",
        "src.memory.consolidator",
        "src.nickname",
        "src.proactive",
        "src.proactive.gate",
        "src.proactive.modes",
        "src.proactive.rate_tracker",
        "src.proactive.sticky",
        "src.router",
        "src.summarize",
        "src.summarize.base",
        "src.summarize.claude_backend",
        "src.summarize.deepseek_backend",
        "src.summarize.models",
        "src.summarize.prompts",
        "src.trigger",
        "src.trigger.detector",
        "src.utils",
        "src.utils.logging_config",
        "src.web",
        "src.web.server",
        "src.wechat",
        "src.wechat.base",
        "src.wechat.mac_hybrid_backend",
        "src.wechat.mac_ui_backend",
        "src.wechat.mac_weflow_client",
        "anthropic",
        "openai",
        "pydantic",
        "dotenv",
        "ddgs",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "pyperclip",
        "psutil",
        "AppKit",
        "Quartz",
        "objc",
        "webview",
        "webview.platforms",
        "webview.platforms.cocoa",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "jedi",
        "IPython",
        "uiautomation",
        "win32api",
        "win32con",
        "win32gui",
        "win32clipboard",
        "win32process",
        "comtypes",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="webot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=MACOS_CODESIGN_IDENTITY,
    entitlements_file=MACOS_ENTITLEMENTS_FILE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="webot",
)

app = BUNDLE(
    coll,
    name="webot.app",
    icon=None,
    bundle_identifier="com.webot.desktop",
    codesign_identity=MACOS_CODESIGN_IDENTITY,
    entitlements_file=MACOS_ENTITLEMENTS_FILE,
    info_plist={
        "NSAppleEventsUsageDescription": "webot needs to control WeChat and System Events to switch chats and send replies.",
        "NSScreenCaptureUsageDescription": "webot needs to read the visible WeChat chat title and search results on macOS.",
    },
)
