import os
from typing import List, Dict

import requests
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="web", static_url_path="")

CHANNELS = {
    "thinking": {
        "model": "gemma4:e2b",
        "url_env": "GEMMA_THINKING_URL",
        "key_env": "GEMMA_THINKING_KEY",
        "default_url": "https://api-cz.top",
    },
    "nothinking": {
        "model": "gemma4:e2b",
        "url_env": "GEMMA_NOTHINKING_URL",
        "key_env": "GEMMA_NOTHINKING_KEY",
        "default_url": "https://api-cz.top",
    },
}


def mask_key_tail(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 4:
        return "*" * len(api_key)
    return "*" * (len(api_key) - 4) + api_key[-4:]


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    mode = payload.get("mode", "thinking")
    user_message = (payload.get("message") or "").strip()
    history: List[Dict[str, str]] = payload.get("history") or []

    if mode not in CHANNELS:
        return jsonify({"ok": False, "error": "无效 mode，仅支持 thinking / nothinking"}), 400
    if not user_message:
        return jsonify({"ok": False, "error": "message 不能为空"}), 400

    conf = CHANNELS[mode]
    base_url = os.getenv(conf["url_env"], conf["default_url"]).rstrip("/")
    api_key = os.getenv(conf["key_env"])
    debug_info = {
        "mode": mode,
        "model": conf["model"],
        "url_env": conf["url_env"],
        "key_env": conf["key_env"],
        "upstream": f"{base_url}/v1/chat/completions",
        "key_tail_masked": mask_key_tail(api_key),
    }

    if not api_key:
        return jsonify({"ok": False, "error": f"缺少环境变量 {conf['key_env']}", "debug": debug_info}), 400

    messages = []
    for item in history[-10:]:
        role = item.get("role", "user")
        content = (item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})

    req_body = {
        "model": conf["model"],
        "messages": messages,
        "temperature": float(payload.get("temperature", 0.7)),
        "max_tokens": int(payload.get("max_tokens", 512)),
    }

    try:
        resp = requests.post(
            f"{base_url}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=req_body,
            timeout=120,
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": f"请求失败: {exc}", "debug": debug_info}), 502

    if resp.status_code >= 400:
        return jsonify({"ok": False, "error": f"HTTP {resp.status_code}: {resp.text}", "debug": debug_info}), 502

    data = resp.json()
    choices = data.get("choices") or []
    content = ""
    if choices:
        content = (choices[0].get("message") or {}).get("content") or ""

    return jsonify({"ok": True, "reply": content, "raw": data, "debug": debug_info})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8787, debug=False)
