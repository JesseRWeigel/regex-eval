#!/usr/bin/env python3
"""Ask a local Ollama model for one regex per task and record the raw responses.

This is the only file that needs a model, and nothing in scripts/verify.sh calls it. The raw
JSONL it writes is the committed artefact, and every number in the README is recomputed from
those records by scripts/measure.py, so the eval can be re-checked by anyone with no GPU.

Two Ollama traps, both measured on this workstation and both silent:

  * The hidden reasoning channel is on by default and is stripped from the response body, so a
    prompt that forbids reasoning still gets a model that reasons and you cannot see it. `think`
    is sent explicitly on every request here and recorded in every record.
  * Only `options.num_ctx` in the request body changes the loaded context length. Setting it in
    the REPL or through OLLAMA_CONTEXT_LENGTH leaves the server default in place without an error.

Usage:
    python3 scripts/run_eval.py --model gpt-oss:20b --samples 3 --think false
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rx import prompt, tasks  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")
HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
NUM_CTX = 8192
NUM_PREDICT = 1024


def call(model: str, text: str, seed: int, think, temperature: float) -> dict:
    body = {
        "model": model,
        "prompt": text,
        "stream": False,
        "think": think,
        "options": {
            "temperature": temperature,
            "seed": seed,
            "num_ctx": NUM_CTX,          # only this changes the loaded context, see the docstring
            "num_predict": NUM_PREDICT,
        },
    }
    request = urllib.request.Request(
        f"{HOST}/api/generate", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--think", default="false", choices=["false", "true"])
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    think = args.think == "true"
    task_list = tasks.load()
    os.makedirs(RESULTS, exist_ok=True)
    slug = args.model.replace(":", "-").replace("/", "-")
    path = args.out or os.path.join(RESULTS, f"run-{slug}-think{args.think}.jsonl")

    print(f"{len(task_list)} tasks x {args.samples} samples = "
          f"{len(task_list) * args.samples} calls -> {os.path.relpath(path, ROOT)}")
    started = time.time()
    written = 0
    with open(path, "w", encoding="utf-8") as handle:
        for sample in range(args.samples):
            for task in task_list:
                text = prompt.build(task)
                seed = 1000 + sample
                try:
                    reply = call(args.model, text, seed, think, args.temperature)
                except urllib.error.HTTPError as error:
                    detail = error.read().decode("utf-8", "replace")[:400]
                    print(f"HTTP {error.code} on {task.id}: {detail}")
                    return 1
                record = {
                    "model": args.model,
                    "think": think,
                    "sample": sample,
                    "seed": seed,
                    "temperature": args.temperature,
                    "num_ctx": NUM_CTX,
                    "task": task.id,
                    "prompt": text,
                    "response": reply.get("response", ""),
                    "thinking_chars": len(reply.get("thinking") or ""),
                    "done_reason": reply.get("done_reason"),
                    "eval_count": reply.get("eval_count"),
                    "total_duration_ns": reply.get("total_duration"),
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                written += 1
                first = (record["response"] or "").strip().splitlines()
                print(f"  [{written:3d}] {task.id:14s} {first[-1][:70] if first else '(empty)'}")
    print(f"{written} records in {time.time() - started:.0f}s -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
