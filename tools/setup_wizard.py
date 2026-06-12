"""
First-time setup wizard — extracts WeChat DB key.

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


def extract_key(timeout: float = 60) -> str | None:
    """Extract WCDB decrypt key using wx_key.dll hook.

    Returns the hex key string or None.
    """
    import sys as _sys
    _sys.path.insert(0, str(PROJECT_ROOT))
    from src.wechat.extract_key import extract_wcdb_key

    print("\n[info] Extracting database key via wx_key.dll...")
    print("       WeChat must be started during key capture.")

    key = extract_wcdb_key()
    if key:
        return key

    print("\n[warning] Key extraction failed.")
    print("       Please ensure:")
    print("       1. WeChat version is compatible")
    print("       2. wx_key.dll is in the native/windows/ directory")
    print("       3. Follow the prompts to restart WeChat")
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
    updated = {"WECHAT_BACKEND": False, "WECHAT_GROUPS": False}

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("WECHAT_BACKEND="):
            new_lines.append("WECHAT_BACKEND=wcdb")
            updated["WECHAT_BACKEND"] = True
        elif stripped.startswith("WECHAT_GROUPS="):
            new_lines.append("WECHAT_GROUPS=*")
            updated["WECHAT_GROUPS"] = True
        else:
            new_lines.append(line)

    # Add missing fields
    if not updated["WECHAT_BACKEND"]:
        new_lines.append("WECHAT_BACKEND=wcdb")
    if not updated["WECHAT_GROUPS"]:
        new_lines.append("WECHAT_GROUPS=*")

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

    # Step 3: Extract the decrypt key
    print("\n[info] Extracting database key...")
    key = extract_key()

    if key:
        print(f"[OK] Key extracted: {key[:16]}...{key[-16:]}")
    else:
        print("\n[warning] Automatic key extraction failed.")
        print("        Please ensure:")
        print("        1. WeChat version is compatible")
        print("        2. wx_key.dll is in the native/windows/ directory")
        print("        3. Follow the prompts to restart WeChat")
        return

    # Step 4: Write .env
    env_path = PROJECT_ROOT / ".env"
    write_env(db_path, wxid, key, env_path)

    print()
    print("=" * 50)
    print("  Setup complete!")
    print("=" * 50)
    print()
    print("  You can now run:")
    print("    python desktop.py")
    print("  or double-click start.bat")
    print()
    print("  The WCDB bridge starts automatically with zero manual steps.")


if __name__ == "__main__":
    main()
