#!/usr/bin/env python3
"""Record what happens when the reasoning channel is left on for a small model on this task.

The first attempt at a reasoning arm was abandoned because the answers never arrived: the model
spent its entire token budget in the hidden channel and returned an empty response body with
done_reason "length". That is worth keeping evidence for rather than asserting from memory, so
this writes a small probe file the verify script checks the README against.

Needs Ollama, so it is not part of verify.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rx import prompt, tasks  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL = os.environ.get("PROBE_MODEL", "qwen3.5:9b")
NUM_PREDICT = 4096
WANTED = ("zip", "time24", "ipv4", "semver")


def main() -> int:
    index = tasks.by_id(tasks.load())
    rows = []
    for task_id in WANTED:
        task = index[task_id]
        body = {"model": MODEL, "prompt": prompt.build(task), "stream": False, "think": True,
                "options": {"temperature": 0.7, "seed": 1000, "num_ctx": 8192,
                            "num_predict": NUM_PREDICT}}
        request = urllib.request.Request(f"{HOST}/api/generate",
                                         data=json.dumps(body).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=900) as response:
            reply = json.loads(response.read().decode("utf-8"))
        row = {"model": MODEL, "think": True, "task": task_id, "num_predict": NUM_PREDICT,
               "response": reply.get("response", ""),
               "thinking_chars": len(reply.get("thinking") or ""),
               "done_reason": reply.get("done_reason"), "eval_count": reply.get("eval_count")}
        rows.append(row)
        print(f"  {task_id:8s} thinking {row['thinking_chars']:6d} chars, "
              f"answer {len(row['response'].strip()):4d} chars, done_reason {row['done_reason']}")
    path = os.path.join(ROOT, "fixtures", "think-budget-probe.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {os.path.relpath(path, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
