import argparse
import json
import os
import sys

import requests

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


def call_chat(mode: str, prompt: str, temperature: float, max_tokens: int):
    conf = CHANNELS[mode]
    base_url = os.getenv(conf["url_env"], conf["default_url"]).rstrip("/")
    api_key = os.getenv(conf["key_env"])

    if not api_key:
        raise RuntimeError(f"缺少环境变量: {conf['key_env']}")

    url = f"{base_url}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": conf["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        return "", data

    content = choices[0].get("message", {}).get("content", "")
    return content, data


def main():
    parser = argparse.ArgumentParser(description="Gemma thinking / nothinking 最小调用示例")
    parser.add_argument("--mode", choices=["thinking", "nothinking"], required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--raw", action="store_true", help="同时打印完整返回 JSON")
    args = parser.parse_args()

    try:
        text, raw = call_chat(
            mode=args.mode,
            prompt=args.prompt,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
    except Exception as exc:
        print(f"调用失败: {exc}", file=sys.stderr)
        sys.exit(1)

    print("=== 模型输出 ===")
    print(text if text else "(空输出)")

    if args.raw:
        print("\n=== 原始 JSON ===")
        print(json.dumps(raw, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
