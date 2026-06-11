"""
First-time setup wizard — extracts WeChat DB key without needing
to manually open or interact with WeFlow.

Only needed ONCE. After setup, bot runs fully standalone.

Usage:
    python tools/setup_wizard.py

What it does:
    1. Auto-detects dbPath (Documents/xwechat_files)
    2. Auto-detects myWxid (scans dbPath for wxid_* directories)
    3. Extracts the WCDB decrypt key via wx_key.dll hook
    4. Saves everything to .env
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def find_wechat_db_path() -> str | None:
    """Auto-detect WeChat database root directory."""
    candidates = [
        Path.home() / "Documents" / "xwechat_files",
        Path.home() / "Documents" / "WeChat Files",
        Path("D:/Documents") / "xwechat_files",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def find_wechat_accounts(db_path: str) -> list[dict]:
    """Find all WeChat accounts (wxid directories with session.db)."""
    accounts = []
    root = Path(db_path)
    if not root.exists():
        return accounts

    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        session_db = entry / "db_storage" / "session" / "session.db"
        flat_session = entry / "db_storage" / "session.db"
        if session_db.exists() or flat_session.exists():
            accounts.append({
                "wxid": entry.name,
                "session_db": str(session_db) if session_db.exists() else str(flat_session),
                "path": str(entry),
            })

    return accounts


def find_weflow_exe() -> Path | None:
    """Find WeFlow.exe for runtime + one-time key extraction."""
    paths = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "WeFlow" / "WeFlow.exe",
        Path("C:/Program Files/WeFlow/WeFlow.exe"),
    ]
    for p in paths:
        if p.exists():
            return p
    return None


def extract_key_via_weflow(weflow_exe: Path, timeout: float = 60) -> str | None:
    """Extract WCDB decrypt key using wx_key.dll hook.

    Uses the current key extraction method (wx_key.dll) which hooks
    WeChat on startup to capture the database key.

    Returns the hex key string or None.
    """
    import sys as _sys
    _sys.path.insert(0, str(PROJECT_ROOT))
    from src.wechat.extract_key import extract_wcdb_key

    print("\n[信息] 正在使用 wx_key.dll 提取数据库密钥...")
    print("       微信需要在启动时完成密钥捕获。")

    key = extract_wcdb_key()
    if key:
        return key

    print("\n[警告] 密钥提取失败。")
    print("       请确保：")
    print("       1. 微信版本兼容")
    print("       2. wx_key.dll 在 lib/ 目录中")
    print("       3. 按照提示重启微信")
    return None


def write_env(db_path: str, wxid: str, key: str, env_path: Path | None = None) -> None:
    """Write the detected configuration to .env."""
    if env_path is None:
        env_path = PROJECT_ROOT / ".env"

    # Read existing .env or .env.example
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
    elif (PROJECT_ROOT / ".env.example").exists():
        with open(PROJECT_ROOT / ".env.example", "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = ""

    # Update key fields
    lines = content.split("\n")
    updated = {"WECHAT_BACKEND": False, "WECHAT_GROUPS": False,
               "WEFLOW_TOKEN": False}

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("WECHAT_BACKEND="):
            new_lines.append("WECHAT_BACKEND=weflow")
            updated["WECHAT_BACKEND"] = True
        elif stripped.startswith("WECHAT_GROUPS="):
            new_lines.append("WECHAT_GROUPS=*")
            updated["WECHAT_GROUPS"] = True
        elif stripped.startswith("WEFLOW_TOKEN="):
            new_lines.append(f"WEFLOW_TOKEN={key}")
            updated["WEFLOW_TOKEN"] = True
        else:
            new_lines.append(line)

    # Add missing fields
    if not updated["WECHAT_BACKEND"]:
        new_lines.append("WECHAT_BACKEND=weflow")
    if not updated["WECHAT_GROUPS"]:
        new_lines.append("WECHAT_GROUPS=*")
    if not updated["WEFLOW_TOKEN"]:
        new_lines.append(f"WEFLOW_TOKEN={key}")

    env_path.write_text("\n".join(new_lines), encoding="utf-8")
    print(f"[OK] 配置已写入 {env_path}")


def main():
    print("=" * 50)
    print("  webot — 首次设置向导")
    print("=" * 50)
    print()

    # Step 1: Find WeChat DB path
    db_path = find_wechat_db_path()
    if not db_path:
        print("[错误] 未找到微信数据库目录。")
        print("       请确认微信已安装并登录过。")
        return
    print(f"[OK] 微信数据目录: {db_path}")

    # Step 2: Find WeChat accounts
    accounts = find_wechat_accounts(db_path)
    if not accounts:
        print("[错误] 未找到微信账号数据。请先登录微信。")
        return

    print(f"[OK] 找到 {len(accounts)} 个账号:")
    for i, acc in enumerate(accounts):
        print(f"     [{i+1}] {acc['wxid']}")

    if len(accounts) == 1:
        wxid = accounts[0]["wxid"]
        print(f"     自动选择: {wxid}")
    else:
        choice = input(f"     请选择账号 [1-{len(accounts)}]: ").strip()
        try:
            wxid = accounts[int(choice) - 1]["wxid"]
        except (ValueError, IndexError):
            print("[错误] 无效选择")
            return

    # Step 3: Find WeFlow.exe (for key extraction)
    weflow_exe = find_weflow_exe()
    if not weflow_exe:
        print("\n[警告] 未找到 WeFlow.exe。")
        print("       WeFlow.exe 需要作为 Node.js 运行时来加载 WCDB DLL。")
        print("       请下载并安装 WeFlow: https://github.com/hicccc77/WeFlow/releases")
        print()
        print("       或者已有 WeFlow 安装，请设置环境变量:")
        print("       WEFLOW_EXE_PATH=C:\\path\\to\\WeFlow.exe")
        return

    print(f"[OK] WeFlow.exe: {weflow_exe}")

    # Step 4: Extract the decrypt key
    print("\n[信息] 正在提取数据库密钥...")
    key = extract_key_via_weflow(weflow_exe)

    if key:
        print(f"[OK] 密钥提取成功: {key[:16]}...{key[-16:]}")
    else:
        print("\n[警告] 自动密钥提取失败。")
        print("       请手动运行一次 WeFlow 完成初始化设置：")
        print(f"       1. 打开 {weflow_exe}")
        print("       2. 完成初始设置（选择数据目录和账号）")
        print("       3. 关闭 WeFlow")
        print("       4. 再次运行本向导")
        return

    # Step 5: Write .env
    env_path = PROJECT_ROOT / ".env"
    write_env(db_path, wxid, key, env_path)

    print()
    print("=" * 50)
    print("  设置完成!")
    print("=" * 50)
    print()
    print("  现在可以直接运行:")
    print("    python desktop.py")
    print("  或双击 start.bat")
    print()
    print("  WCDB Bridge 会自动启动，零人工操作。")
    print("  WeFlow.exe 仅在后台作为 DLL 运行时，不显示窗口。")


if __name__ == "__main__":
    main()
