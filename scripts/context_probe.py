#!/usr/bin/env python3
"""Ask each model for one token with options.num_ctx set, then read back what Ollama loaded.

AGENTS.md in the parent fleet records that only `options.num_ctx` in the request body changes the
loaded context length, and that the REPL and the environment variable both fail silently. Running
this eval turned up a further wrinkle worth writing down: even the request body is a request, and
at least one model here ignored it and stayed at the server default.

Writes fixtures/context-probe.json. Needs Ollama, so it is not part of verify.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
ASKED = 8192


def post(path: str, body: dict) -> dict:
    request = urllib.request.Request(f"{HOST}{path}", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def loaded() -> dict:
    with urllib.request.urlopen(f"{HOST}/api/ps", timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {model["name"]: model.get("context_length") for model in payload.get("models", [])}


def main() -> int:
    models = sys.argv[1:] or ["qwen3.5:9b", "gemma4:e4b", "gpt-oss:20b"]
    rows = []
    for model in models:
        post("/api/generate", {"model": model, "prompt": "hi", "stream": False, "think": False,
                               "options": {"num_ctx": ASKED, "num_predict": 1, "seed": 1}})
        got = loaded().get(model)
        rows.append({"model": model, "asked_num_ctx": ASKED, "loaded_context_length": got,
                     "honoured": got == ASKED})
        print(f"  {model:16s} asked {ASKED}, loaded {got}, "
              f"{'honoured' if got == ASKED else 'IGNORED'}")
    path = os.path.join(ROOT, "fixtures", "context-probe.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"host_default_note": "read from /api/ps immediately after a one token call",
                   "probes": rows}, handle, indent=2)
        handle.write("\n")
    print(f"wrote {os.path.relpath(path, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
