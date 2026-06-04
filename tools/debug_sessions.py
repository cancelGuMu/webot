"""Diagnostic: dump WCDB sessions to understand field names."""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.wechat.wcdb_client import WcdbNativeClient

client = WcdbNativeClient()
client.init()
client.open()

sessions = client.get_sessions()
print(f"Total sessions: {len(sessions)}")
print()

# Count field names across all sessions
field_counts = {}
for s in sessions:
    for key in s.keys():
        field_counts[key] = field_counts.get(key, 0) + 1

print("=== Field names found across sessions ===")
for key, count in sorted(field_counts.items(), key=lambda x: -x[1]):
    print(f"  {key!r}: {count}/{len(sessions)} sessions")

print()

# Show all @chatroom sessions
print("=== @chatroom sessions ===")
chatroom_count = 0
for s in sessions:
    # Try multiple field name variants
    username = (
        s.get("username") or s.get("userName") or s.get("UserName")
        or s.get("talker") or ""
    )
    if "@chatroom" in str(username):
        chatroom_count += 1
        display = (
            s.get("displayName") or s.get("DisplayName") or s.get("displayname")
            or s.get("nickname") or s.get("nickName") or s.get("NickName")
            or s.get("name") or ""
        )
        print(f"  username={username!r}  display={display!r}")
        if chatroom_count >= 20 and len(sessions) > 20:
            print(f"  ... and {sum(1 for s in sessions if '@chatroom' in str(s.get('username', s.get('userName', '')))) - 20} more")
            break

print(f"\nTotal @chatroom sessions: {chatroom_count}")

# Show first 3 sessions in full (handle encoding safely)
print("\n=== First 3 session raw data ===")
for i, s in enumerate(sessions[:3]):
    print(f"\n-- Session {i+1} --")
    for k, v in sorted(s.items()):
        try:
            val = str(v)[:200]
            print(f"  {k!r}: {val}")
        except UnicodeEncodeError:
            print(f"  {k!r}: <unicode error, len={len(str(v))}>")

# Check display names via DLL
print("\n=== Resolving @chatroom names via DLL ===")
chatroom_usernames = [
    s["username"] for s in sessions
    if "@chatroom" in s.get("username", "")
]
names = client.get_display_names(chatroom_usernames)
print(f"get_display_names result: {json.dumps(names, ensure_ascii=False, indent=2)[:2000]}")

# Also try resolve_nickname for each
print("\n=== resolve_nickname for each @chatroom ===")
for u in chatroom_usernames[:5]:
    name = client.resolve_nickname(u)
    print(f"  {u!r} -> {name!r}")

client.close()
