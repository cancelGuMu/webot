# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for WeChat Bot Desktop.

Produces a single EXE with:
  - Native desktop window (pywebview + Edge Chromium)
  - Embedded React UI (ui/dist/)
  - Full Python bot runtime
  - System tray support

Build: pyinstaller build.spec
Output: dist/WeChatBot.exe
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

a = Analysis(
    ['desktop.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # Embed React UI
        ('ui/dist', 'ui/dist'),
        # Embed .env.example as template
        ('.env.example', '.'),
        # Embed data directory structure
    ],
    hiddenimports=[
        'src', 'src.bot', 'src.config', 'src.main',
        'src.db', 'src.db.schema', 'src.db.store',
        'src.trigger', 'src.trigger.detector',
        'src.summarize', 'src.summarize.base', 'src.summarize.claude_backend',
        'src.summarize.deepseek_backend', 'src.summarize.models', 'src.summarize.prompts',
        'src.proactive', 'src.proactive.gate', 'src.proactive.modes',
        'src.proactive.rate_tracker', 'src.proactive.sticky',
        'src.memory', 'src.memory.consolidator',
        'src.guard', 'src.guard.vulgar_detector',
        'src.wechat', 'src.wechat.base', 'src.wechat.wcdb_backend',
        'src.wechat.wcdb_client', 'src.wechat.direct_backend',
        'src.wechat.window_controller', 'src.wechat.keyboard',
        'src.wechat.helpers', 'src.wechat.uia_helpers',
        'src.wechat.extract_key',
        'src.web', 'src.web.server',
        'src.nickname', 'src.admin', 'src.fun',
        'src.utils', 'src.utils.logging_config', 'src.utils.web_search',
        'dotenv', 'anthropic', 'openai', 'pydantic',
        'webview', 'clr', 'pythonnet',
        'PIL', 'PIL.Image', 'PIL.ImageDraw',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'pandas',
        'scipy', 'jedi', 'IPython', 'ipykernel',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WeChatBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,          # Add .ico path here for custom icon
)
