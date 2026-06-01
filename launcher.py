"""One-click launcher for WeChat Summarizer Bot.

Checks environment, installs dependencies, guides first-time setup,
then launches the bot.

Usage:
    python launcher.py
"""

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, cwd=str(PROJECT_ROOT), **kwargs)


def _get_env_value(env_path: Path, key: str) -> str | None:
    """Read a value from .env file."""
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip()
    return None


def _validate_env(env_path: Path) -> None:
    """Check that .env has valid AI_BACKEND and corresponding API key."""
    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Parse AI_BACKEND
    backend = "claude"
    api_key_found = False

    for line in lines:
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()

        if key == "AI_BACKEND":
            backend = value.strip().lower()
        elif key == "ANTHROPIC_API_KEY" and value.strip() and "your-key" not in value.lower():
            api_key_found = True
        elif key == "DEEPSEEK_API_KEY" and value.strip() and "your-deepseek-key" not in value.lower():
            api_key_found = True

    if backend not in ("claude", "deepseek"):
        print(f"[警告] AI_BACKEND='{backend}' 无效，支持: claude, deepseek")
        print("        将使用默认值 claude")

    if not api_key_found:
        print()
        print("=" * 44)
        if backend == "deepseek":
            print("  未检测到有效的 DEEPSEEK_API_KEY！")
        else:
            print("  未检测到有效的 ANTHROPIC_API_KEY！")
        print("=" * 44)
        print(f"\n  请在 .env 中填入有效的 API Key。")
        print(f"  文件位置: {env_path}\n")
        input("\n按 Enter 退出...")
        sys.exit(1)


def main():
    print("=" * 44)
    print("  WeChat 群聊总结机器人 - 一键启动")
    print("=" * 44)
    print()

    # ── 1. Check Python version ───────────────────────────────────
    py_ver = sys.version_info
    if py_ver < (3, 10):
        print(f"[错误] Python 版本过低: {py_ver.major}.{py_ver.minor}")
        print("        需要 Python 3.10 或更高版本")
        print("        下载: https://www.python.org/downloads/")
        input("\n按 Enter 退出...")
        sys.exit(1)
    print(f"[OK] Python {py_ver.major}.{py_ver.minor}.{py_ver.micro}")

    # ── 2. Check / create .env ────────────────────────────────────
    if not ENV_FILE.exists():
        print("\n[警告] 未找到 .env 配置文件，正在从模板创建...")

        content = ENV_EXAMPLE.read_text(encoding="utf-8") if ENV_EXAMPLE.exists() else ""
        ENV_FILE.write_text(content, encoding="utf-8")

        print()
        print("=" * 44)
        print("  请先编辑 .env 文件，填入你的 API Key！")
        print("=" * 44)
        print(f"\n  文件位置: {ENV_FILE}\n")
        print("  AI_BACKEND 决定用哪个 AI 服务：")
        print("    deepseek → 填 DEEPSEEK_API_KEY")
        print("    claude   → 填 ANTHROPIC_API_KEY")
        print()
        print("  必填项:")
        print("    BOT_DISPLAY_NAME=你的机器人微信昵称")
        print("    以及对应后端的 API_KEY")
        print()
        print("  编辑完成后，再次双击 start.bat 即可启动。")

        # Try to open .env in notepad
        try:
            os.startfile(str(ENV_FILE))
        except Exception:
            pass

        input("\n按 Enter 退出...")
        sys.exit(0)

    # Validate .env has a valid AI_BACKEND and corresponding API key
    _validate_env(ENV_FILE)
    print("[OK] .env 配置文件已找到")

    # ── 3. Check / install dependencies ───────────────────────────
    print("[检查] 正在检查依赖...")

    # Determine which WeChat backend is configured
    wechat_backend = _get_env_value(ENV_FILE, "WECHAT_BACKEND") or "weflow"

    # Only wx4py needs a special package beyond requirements.txt
    needs_wx4py = wechat_backend == "wx4py"
    deps_ok = True
    if needs_wx4py:
        try:
            import wx4py  # noqa: F401
        except ImportError:
            deps_ok = False

    if not deps_ok:
        print("[信息] 首次运行，正在安装依赖包...")
        print()

        # First install regular PyPI packages
        result = run([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)])
        if result.returncode != 0:
            print()
            print("[错误] 依赖安装失败，请检查网络连接")
            print(f"        或手动运行: pip install -r requirements.txt")
            input("\n按 Enter 退出...")
            sys.exit(1)

        # Install wx4py if needed
        if needs_wx4py:
            print("[信息] 正在安装 wx4py...")
            result = run([sys.executable, "-m", "pip", "install", "wx4py"])
            if result.returncode != 0:
                print()
                print("[错误] wx4py 安装失败")
                print("        pip install wx4py")
                input("\n按 Enter 退出...")
                sys.exit(1)

        print()

    print("[OK] 依赖已就绪")

    # ── 4. Pre-flight checklist ───────────────────────────────────
    print()
    print("=" * 44)
    print("  启动前检查清单:")
    print("=" * 44)
    print("  [ ] 微信桌面版已登录，窗口不能最小化")
    print("        (可以被其他窗口挡住，但不要点 _ 按钮)")
    print("  [ ] .env 中 BOT_DISPLAY_NAME 配置正确")
    print("  [ ] 建议使用微信小号运行")
    print()
    print("  按 Ctrl+C 可随时停止机器人")
    print("=" * 44)
    print()
    print("正在启动，请稍候...")
    print()

    # ── 5. Launch the bot ─────────────────────────────────────────
    try:
        result = run([sys.executable, "-m", "src.main"])
        print()
        if result.returncode != 0:
            print("[错误] 机器人异常退出 (退出码: {})".format(result.returncode))
            print()
            print("常见问题:")
            print("  1. 微信没有打开或没有登录")
            print("  2. API Key 未配置或无效")
            print("     DeepSeek → DEEPSEEK_API_KEY")
            print("     Claude   → ANTHROPIC_API_KEY")
            print("  3. WECHAT_BACKEND 配置错误或依赖未安装")
            print("  4. 网络问题导致 API 调用失败")
        else:
            print("机器人已正常停止。")
    except KeyboardInterrupt:
        print()
        print("机器人已停止。")

    input("\n按 Enter 退出...")


if __name__ == "__main__":
    main()
