"""Run a candidate regex over a corpus in a child process, under a wall clock guard.

Catastrophic backtracking is not a rare theoretical hazard here, it is one of the things a model
can hand you: `(a+)+$` against thirty a's and a bang runs for longer than the heat death of the
afternoon. Running that in this process would hang the whole eval, and Python's `re` releases no
lock you can interrupt from a thread, so each candidate goes to a child process that gets killed.

A timeout is reported as its own outcome and never folded into "wrong". A pattern that would have
answered correctly given a year is a different failure from one that answers incorrectly at once,
and collapsing them would hide the only class of bug that also takes a production service down.

The child prints one line per case and flushes, so a kill still tells us how far it got.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass

DEFAULT_TIMEOUT = 10.0

CHILD = r"""
import json, re, sys
payload = json.loads(sys.stdin.read())
try:
    compiled = re.compile(payload["pattern"])
except Exception as exc:
    print("INVALID " + json.dumps(f"{type(exc).__name__}: {exc}"), flush=True)
    raise SystemExit(0)
print("COMPILED", flush=True)
for index, item in enumerate(payload["strings"]):
    hit = 1 if compiled.search(item) else 0
    print(f"CASE {index} {hit}", flush=True)
print("DONE", flush=True)
"""


@dataclass(frozen=True)
class Execution:
    status: str            # "ok", "invalid", "timeout", "crash"
    hits: tuple            # bool per case, only complete when status == "ok"
    reached: int           # how many cases the child got through
    detail: str


def run_corpus(pattern: str, strings: list, timeout: float = DEFAULT_TIMEOUT) -> Execution:
    payload = json.dumps({"pattern": pattern, "strings": list(strings)})
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        finished = subprocess.run(
            [sys.executable, "-I", "-c", CHILD], input=payload, capture_output=True,
            text=True, timeout=timeout, env=environment,
        )
        out, err, code = finished.stdout, finished.stderr, finished.returncode
    except subprocess.TimeoutExpired as expired:
        partial = expired.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        return Execution("timeout", (), _reached(partial),
                         f"killed after {timeout:g}s, catastrophic backtracking is the usual cause")

    if out.startswith("INVALID "):
        return Execution("invalid", (), 0, json.loads(out[len("INVALID "):].splitlines()[0]))
    if code != 0:
        return Execution("crash", (), _reached(out), (err.strip().splitlines() or ["no stderr"])[-1])

    hits: list = []
    for line in out.splitlines():
        if line.startswith("CASE "):
            _, index, hit = line.split()
            if int(index) != len(hits):
                return Execution("crash", (), len(hits), "the child emitted cases out of order")
            hits.append(hit == "1")
    if len(hits) != len(strings) or "DONE" not in out:
        return Execution("crash", tuple(hits), len(hits),
                         f"the child reported {len(hits)} of {len(strings)} cases")
    return Execution("ok", tuple(hits), len(hits), "")


def _reached(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.startswith("CASE "))
