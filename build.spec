# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for WeChat Bot Desktop.

Build: pyinstaller build.spec
Output: dist/WeChatBot.exe
"""
import sys
import site
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH)

# ── Resolve webview runtime DLLs dynamically ───────────────────────────
def _find_webview_runtime_dir():
    """Find the webview package's runtime directory in site-packages."""
    for sp in site.getsitepackages():
        candidate = Path(sp) / "webview" / "lib"
        if candidate.exists():
            return candidate
    # Fallback: try user site-packages
    user_sp = site.getusersitepackages()
    if user_sp:
        candidate = Path(user_sp) / "webview" / "lib"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "webview package not found. Install with: pip install pywebview"
    )

_webview_dir = _find_webview_runtime_dir()
_webview_runtime = _webview_dir / "runtimes" / "win-x64" / "native" / "WebView2Loader.dll"
_webview_interop = _webview_dir / "WebBrowserInterop.x64.dll"

if not _webview_runtime.exists():
    raise FileNotFoundError(f"WebView2Loader.dll not found at {_webview_runtime}")
if not _webview_interop.exists():
    raise FileNotFoundError(f"WebBrowserInterop.x64.dll not found at {_webview_interop}")

a = Analysis(
    ['desktop.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[
        (str(_webview_runtime), './runtimes/win-x64/native'),
        (str(_webview_interop), './lib'),
        (str(PROJECT_ROOT / 'lib' / 'wcdb_api.dll'), 'lib'),
        (str(PROJECT_ROOT / 'lib' / 'WCDB.dll'), 'lib'),
        (str(PROJECT_ROOT / 'lib' / 'MSVCP140.dll'), 'lib'),
        (str(PROJECT_ROOT / 'lib' / 'VCRUNTIME140.dll'), 'lib'),
        (str(PROJECT_ROOT / 'lib' / 'VCRUNTIME140_1.dll'), 'lib'),
        (str(PROJECT_ROOT / 'lib' / 'wx_key.dll'), 'lib'),
    ],
    datas=[
        ('ui/dist', 'ui/dist'),
        ('.env.example', '.'),
        ('data', 'data'),
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
        'src.wechat', 'src.wechat.base', 'src.wechat.wcdb_backend',
        'src.wechat.wcdb_client', 'src.wechat.window_controller',
        'src.wechat.keyboard', 'src.wechat.helpers', 'src.wechat.extract_key',
        'src.wechat.native', 'src.wechat.native.injector',
        'src.web', 'src.web.server',
        'src.nickname', 'src.admin', 'src.fun',
        'src.utils', 'src.utils.logging_config',
        'dotenv', 'anthropic', 'openai', 'pydantic',
        'uiautomation',
        'webview', 'webview.platforms', 'webview.platforms.edgechromium',
        'PIL', 'PIL.Image', 'PIL.ImageDraw',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'jedi', 'IPython'],
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
    icon='image/logo_assets/logo.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
