#!/usr/bin/env python3
"""Run local inference with a base model + LoRA adapter."""

from __future__ import annotations

import argparse
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def build_prompt(context: str, instruction: str) -> str:
    return (
        "你是该用户本人，请基于上下文，按这个人的语气和风格回答。\n"
        f"任务：{instruction}\n"
        "上下文：\n"
        f"{context.strip()}\n\n"
        "回复："
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Infer with LoRA style adapter.")
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--adapter-dir", required=True)
    parser.add_argument("--context", required=True, help="聊天上下文，建议格式：我:...\\n对方:...")
    parser.add_argument("--instruction", default="请根据上下文，用该用户本人语气回复。")
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--temperature", type=float, default=0.65)
    parser.add_argument("--top-p", type=float, default=0.85)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--repetition-penalty", type=float, default=1.18)
    parser.add_argument("--no-repeat-ngram-size", type=int, default=4)
    args = parser.parse_args()

    adapter_dir = Path(args.adapter_dir).resolve()
    device = "cuda" if torch.cuda.is_available() else "cpu"

    tokenizer = AutoTokenizer.from_pretrained(str(adapter_dir), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token or tokenizer.unk_token

    target_dtype = torch.float16 if device == "cuda" else torch.float32
    try:
        base = AutoModelForCausalLM.from_pretrained(
            args.base_model,
            dtype=target_dtype,
            trust_remote_code=True,
        )
    except TypeError:
        base = AutoModelForCausalLM.from_pretrained(
            args.base_model,
            torch_dtype=target_dtype,
            trust_remote_code=True,
        )
    model = PeftModel.from_pretrained(base, str(adapter_dir))
    model.to(device)
    model.eval()

    prompt = build_prompt(args.context, args.instruction)
    encoded = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=args.max_length)
    encoded = {k: v.to(device) for k, v in encoded.items()}

    with torch.no_grad():
        out = model.generate(
            **encoded,
            max_new_tokens=args.max_new_tokens,
            do_sample=True,
            temperature=args.temperature,
            top_p=args.top_p,
            top_k=args.top_k,
            repetition_penalty=args.repetition_penalty,
            no_repeat_ngram_size=args.no_repeat_ngram_size,
            renormalize_logits=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    gen = out[0][encoded["input_ids"].shape[1] :]
    text = tokenizer.decode(gen, skip_special_tokens=True).strip()
    print(text)


if __name__ == "__main__":
    main()
