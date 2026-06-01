"""Find a message marker across recent WeFlow sessions."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_config
from src.wechat.weflow_backend import WeFlowClient


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python tools/find_weflow_message.py <marker> [wait_sec]")

    marker = sys.argv[1]
    wait_sec = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    if wait_sec:
        time.sleep(wait_sec)

    config = load_config()
    client = WeFlowClient(
        base_url=config.weflow_url,
        access_token=config.weflow_token,
    )

    sessions = client.get_sessions(limit=500)
    hits = []
    for session in sessions:
        talker = session.get("username", session.get("talker", ""))
        if not talker:
            continue
        for msg in client.get_messages(talker, limit=50):
            if marker in str(msg.get("content", "")):
                hits.append(
                    {
                        "talker": talker,
                        "displayName": session.get("displayName", ""),
                        "localId": msg.get("localId"),
                        "createTime": msg.get("createTime"),
                        "isSend": msg.get("isSend"),
                        "senderUsername": msg.get("senderUsername"),
                        "content": msg.get("content"),
                    }
                )

    print(
        json.dumps(
            {
                "marker": marker,
                "session_count": len(sessions),
                "hits": hits,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if hits else 1


if __name__ == "__main__":
    raise SystemExit(main())
