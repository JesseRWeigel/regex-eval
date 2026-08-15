#!/usr/bin/env python3
"""A second opinion that imports nothing from `rx`, proved with `ast` rather than grep.

Calling the same grader twice would prove nothing, so everything here is a second implementation:

  * the answer is pulled out of each response by a hand written line scanner that walks characters
    and shares no pattern with rx.extract;
  * the candidate regex is executed under a different guard, an os.fork with a deadline and a
    SIGKILL, rather than the subprocess pipeline in rx.execute;
  * the corpus is read straight from data/tasks.json, and the labels are re-derived independently
    for two tasks by predicates written in plain Python, so a flipped label in the data file is
    visible from here too.

It then recomputes the headline count, the number of responses whose regex is right on the naive
subset and wrong on the held-out cases, and requires it to agree with results/summary.json.

A second implementation that is silently broken agrees with nothing and detects nothing, so the
scanner and the runner are checked against inputs with known answers before either is trusted.
"""

from __future__ import annotations

import ast
import glob
import json
import os
import re
import signal
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBES = os.path.join(ROOT, "scripts", "probes")
FORBIDDEN = "rx"
DEADLINE = 10.0


# ------------------------------------------------------------------ proving independence

def imported_names(path: str) -> set:
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
            if node.level:
                names.add("<relative>")
        elif isinstance(node, ast.Call):
            target = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if target in ("import_module", "__import__"):
                argument = node.args[0] if node.args else None
                names.add(
                    argument.value.split(".")[0]
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
                    else "<computed>"
                )
    return names


def prove_independence() -> list:
    problems = []
    reached = imported_names(os.path.abspath(__file__))
    for banned in (FORBIDDEN, "<computed>", "<relative>"):
        if banned in reached:
            problems.append(f"this checker reaches {banned}")
    if not problems:
        print(f"  independent: imports nothing from {FORBIDDEN}, by ast")

    probes = sorted(name for name in os.listdir(PROBES) if name.startswith("probe_"))
    if len(probes) < 4:
        return problems + ["fewer than four probes, so the prover was never shown to reject one"]
    for name in probes:
        reached = imported_names(os.path.join(PROBES, name))
        rejects = bool({FORBIDDEN, "<computed>", "<relative>"} & reached)
        should_reject = "clean" not in name
        if rejects != should_reject:
            problems.append(f"{name}: prover said {'reject' if rejects else 'accept'}, expected "
                            f"{'reject' if should_reject else 'accept'}")
        else:
            print(f"  {'rejected' if rejects else 'accepted'} as required: {name}")
    return problems


# ------------------------------------------------------------------ a second answer scanner

def scan_answer(response: str) -> tuple:
    """Walk the response line by line. Returns (kind, payload) with kind regex, refusal or none.

    Deliberately clumsy where rx.extract is regular: markers are found by upper casing and
    scanning for a colon by hand, and decoration is peeled by comparing first and last characters.
    """
    if not response:
        return ("none", None)
    last_regex = None
    last_refusal = None
    for raw in response.split("\n"):
        line = raw.strip()
        while line and line[0] in " \t>*_-":
            line = line[1:]
        if line.startswith("```"):
            continue
        upper = line.upper()
        for marker, slot in (("REGEX", "regex"), ("IMPOSSIBLE", "refusal")):
            if not upper.startswith(marker):
                continue
            rest = line[len(marker):].lstrip()
            while rest.startswith("*"):
                rest = rest[1:]
            if not rest.startswith(":"):
                continue
            payload = rest[1:].strip()
            while payload.startswith("*"):
                payload = payload[1:].strip()
            if slot == "regex":
                payload = peel(payload)
                if payload:
                    last_regex = payload
            elif payload:
                last_refusal = payload
    if last_regex is not None:
        return ("regex", last_regex)
    if last_refusal is not None:
        return ("refusal", last_refusal)
    return ("none", None)


def peel(text: str) -> str:
    """Take off matching decoration, but never a quote that also occurs inside."""
    for _ in range(3):
        if len(text) < 3:
            return text
        first, last = text[0], text[-1]
        if first != last or first not in "`\"'/":
            if text.startswith("**") and text.endswith("**") and len(text) > 4:
                inner = text[2:-2].strip()
                if inner and compiles(inner):
                    text = inner
                    continue
            return text
        inner = text[1:-1].strip()
        if not inner or first in inner or not compiles(inner):
            return text
        text = inner
    return text


def compiles(pattern: str) -> bool:
    try:
        re.compile(pattern)
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ a second guarded runner

def run_forked(pattern: str, strings: list, deadline: float = DEADLINE):
    """Match in a forked child killed at a deadline. Returns a list of bools, or None on trouble.

    An in-process alarm would not do: a signal handler runs between bytecodes, and a runaway match
    sits inside C code in the `re` module for the whole time, so SIGALRM would be delivered only
    once the damage was done. Killing a separate process is the guard that actually works.
    """
    try:
        compiled = re.compile(pattern)
    except Exception:
        return "invalid"
    read_fd, write_fd = os.pipe()
    child = os.fork()
    if child == 0:                                       # pragma: no cover - child process
        try:
            os.close(read_fd)
            bits = bytes(1 if compiled.search(item) else 0 for item in strings)
            os.write(write_fd, bits)
            os.close(write_fd)
        finally:
            os._exit(0)
    os.close(write_fd)
    collected = b""
    deadline_at = time.time() + deadline
    os.set_blocking(read_fd, False)
    status = None
    while time.time() < deadline_at:
        try:
            chunk = os.read(read_fd, 4096)
        except BlockingIOError:
            time.sleep(0.01)
            continue
        if not chunk:
            break
        collected += chunk
    done, _ = os.waitpid(child, os.WNOHANG)
    if done == 0:
        os.kill(child, signal.SIGKILL)
        os.waitpid(child, 0)
        status = "timeout"
    os.close(read_fd)
    if status == "timeout" or len(collected) != len(strings):
        return "timeout"
    return [bit == 1 for bit in collected]


# ------------------------------------------------------------------ self checks

def self_check() -> list:
    problems = []
    expectations = [
        ("REGEX: ^cat$", ("regex", "^cat$")),
        ("blah\n```\nREGEX: `^a$`\n```", ("regex", "^a$")),
        ("**REGEX:** ^b$", ("regex", "^b$")),
        ('REGEX: "[^"]*"', ("regex", '"[^"]*"')),
        ('REGEX: "^c$"', ("regex", "^c$")),
        ("IMPOSSIBLE: contradictory", ("refusal", "contradictory")),
        ("no marker here", ("none", None)),
        ("REGEX: ^a$\nREGEX: ^b$", ("regex", "^b$")),
    ]
    for text, expected in expectations:
        got = scan_answer(text)
        if got != expected:
            problems.append(f"scanner: {text!r} gave {got!r}, expected {expected!r}")
    if not problems:
        print(f"  the second scanner agrees with {len(expectations)} hand written expectations")

    if run_forked(r"\Acat\Z", ["cat", "cats"]) != [True, False]:
        problems.append("the forked runner disagrees on a trivial pattern")
    if run_forked("(", ["x"]) != "invalid":
        problems.append("the forked runner did not report an uncompilable pattern")
    started = time.time()
    if run_forked(r"(a+)+$", ["a" * 34 + "!"], deadline=3.0) != "timeout":
        problems.append("the forked runner did not stop a catastrophic pattern")
    elif time.time() - started > 20:
        problems.append("the forked runner stopped the catastrophic pattern far too late")
    else:
        print("  the second guard, an os.fork with a deadline, fired on (a+)+$")
    return problems


# ------------------------------------------------------------------ independent label derivation

def derive_zip(text: str) -> bool:
    """A ZIP code by hand, no regex at all."""
    def ascii_digits(chunk: str) -> bool:
        return bool(chunk) and all("0" <= character <= "9" for character in chunk)

    if len(text) == 5:
        return ascii_digits(text)
    if len(text) == 10 and text[5] == "-":
        return ascii_digits(text[:5]) and ascii_digits(text[6:])
    return False


def derive_time(text: str) -> bool:
    parts = text.split(":")
    if len(parts) != 2:
        return False
    hour, minute = parts
    if len(hour) != 2 or len(minute) != 2:
        return False
    if not all("0" <= character <= "9" for character in hour + minute):
        return False
    return 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59


def check_labels(task_data: dict) -> list:
    problems = []
    derivers = {"zip": derive_zip, "time24": derive_time}
    checked = 0
    for task in task_data["tasks"]:
        deriver = derivers.get(task["id"])
        if not deriver:
            continue
        for case in task["cases"]:
            if deriver(case["s"]) != case["match"]:
                problems.append(f"{task['id']}: the label for {case['s']!r} disagrees with a "
                                f"plain Python predicate")
            checked += 1
    if not problems:
        print(f"  {checked} corpus labels re-derived without a regex and they agree")
    return problems


# ------------------------------------------------------------------ the recount

def recount() -> tuple:
    with open(os.path.join(ROOT, "data", "tasks.json"), encoding="utf-8") as handle:
        task_data = json.load(handle)
    tasks = {task["id"]: task for task in task_data["tasks"]}

    naive_ok = 0
    illusion = 0
    solvable_pass = 0
    solvable_total = 0
    refused_impossible = 0
    outcome_counts: dict = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "results", "run-*.jsonl"))):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                task = tasks[record["task"]]
                impossible = task["kind"] == "control_impossible"
                if not impossible:
                    solvable_total += 1
                kind, payload = scan_answer(record["response"])
                if kind == "none":
                    outcome_counts["no_answer"] = outcome_counts.get("no_answer", 0) + 1
                    continue
                if kind == "refusal":
                    outcome_counts["refused"] = outcome_counts.get("refused", 0) + 1
                    refused_impossible += int(impossible)
                    continue
                verdict = run_forked(payload, [case["s"] for case in task["cases"]])
                if verdict in ("invalid", "timeout"):
                    outcome_counts[verdict] = outcome_counts.get(verdict, 0) + 1
                    continue
                wrong = [case for case, hit in zip(task["cases"], verdict)
                         if hit != case["match"]]
                outcome_counts["pass" if not wrong else "fail"] = outcome_counts.get(
                    "pass" if not wrong else "fail", 0) + 1
                if impossible:
                    continue
                if not wrong:
                    solvable_pass += 1
                if not any(case["naive"] for case in wrong):
                    naive_ok += 1
                    if wrong:
                        illusion += 1
    return ({"naive_subset_pass": naive_ok, "naive_pass_full_fail": illusion,
             "solvable_pass": solvable_pass, "solvable_n": solvable_total,
             "refused_impossible": refused_impossible}, outcome_counts, task_data)


def main() -> int:
    problems = prove_independence()
    problems += self_check()

    counts, outcomes, task_data = recount()
    problems += check_labels(task_data)

    summary_path = os.path.join(ROOT, "results", "summary.json")
    if not os.path.exists(summary_path):
        print("  FAIL results/summary.json is missing, so there is nothing to check against")
        return 1
    with open(summary_path, encoding="utf-8") as handle:
        summary = json.load(handle)

    claimed = {
        "naive_subset_pass": summary["overall"]["naive_subset_pass"],
        "naive_pass_full_fail": summary["overall"]["naive_pass_full_fail"],
        "solvable_pass": summary["overall"]["solvable_pass"],
        "solvable_n": summary["overall"]["solvable_n"],
        "refused_impossible": sum(arm["impossible_refused"] for arm in summary["arms"].values()),
    }
    for key, value in sorted(claimed.items()):
        mine = counts[key]
        flag = "agrees" if mine == value else "DISAGREES"
        print(f"  {key:22s} summary {value:5d}  recount {mine:5d}  {flag}")
        if mine != value:
            problems.append(f"{key}: summary says {value}, the independent recount says {mine}")

    print(f"  outcomes by the second route: "
          f"{', '.join(f'{k} {v}' for k, v in sorted(outcomes.items()))}")

    if problems:
        print("\nFAIL")
        for message in problems:
            print(f"  - {message}")
        return 1
    print("\nindependent recount agrees with the committed summary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
