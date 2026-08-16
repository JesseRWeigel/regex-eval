#!/usr/bin/env python3
"""Break the harness on purpose and require the tests to notice.

The grader is the instrument. If it quietly accepts a wrong regex, every number in the README is
wrong in the same direction and nothing else in the repository would reveal it, so a green suite
is only worth something once it has been shown failing on a tree that really is broken.

Three gates. A sabotage counts only if it clears all three.

  1. It APPLIES. The edit changed the file. A patch whose target text has drifted does nothing,
     and a suite that passes on an unmodified tree looks exactly like a suite that caught a bug.
  2. It MOVES THE MEASUREMENT. scripts/measure.py must print a different fingerprint. A crash is
     not a pass here: a tree that produces no fingerprint at all gets gate 2 for free, so a
     missing fingerprint is scored as a gate 2 failure.
  3. Only then, it is CAUGHT. The unit suite must fail.

Dormant guard code inverts gate 2. A check that nothing currently trips cannot change the output
when it is disabled, so for those the requirement is the opposite and stricter: the fingerprint
must be IDENTICAL and the suite must fail anyway. A guard whose removal moves the output was never
dormant and is rerun as a plain attack.

The null control runs first. An unmodified copy of the tree, in a directory with a different name
and a different path length, must fingerprint identically. If it does not, the measurement tracks
where the code lives rather than what it does, gate 2 is free for everything below, and the run is
void rather than merely disappointing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {".git", ".venv", "__pycache__", "docs", "node_modules", ".github"}

# (name, file, find, replace, dormant)
SABOTAGES = [
    # ---- execution, which is what makes this ground truth executable
    ("the corpus is matched with fullmatch instead of search, so anchoring stops mattering",
     "rx/execute.py", "    hit = 1 if compiled.search(item) else 0",
     "    hit = 1 if compiled.fullmatch(item) else 0", False),
    ("a case that does not match is recorded as a match", "rx/execute.py",
     "    hit = 1 if compiled.search(item) else 0", "    hit = 1", False),
    ("an uncompilable pattern is reported as matching nothing rather than as invalid",
     "rx/execute.py", '    print("INVALID " + json.dumps(f"{type(exc).__name__}: {exc}"), flush=True)\n    raise SystemExit(0)',
     '    compiled = re.compile("(?!)")', False),
    ("a partial child transcript is accepted as a complete result", "rx/execute.py",
     '    if len(hits) != len(strings) or "DONE" not in out:',
     "    if False:", True),
    ("the timeout guard is removed, so a catastrophic regex hangs the eval", "rx/execute.py",
     "            text=True, timeout=timeout, env=environment,",
     "            text=True, env=environment,", True),

    # ---- extraction, which decides what the model actually said
    ("the first regex line wins instead of the last", "rx/extract.py",
     "    for raw in reversed(regex_hits):", "    for raw in regex_hits:", False),
    ("a refusal outranks a regex, so answering counts as refusing", "rx/extract.py",
     "    for raw in reversed(regex_hits):",
     "    if refusal_hits:\n        return Extraction('refusal', None, refusal_hits[-1].strip() "
     "or '(no reason given)')\n    for raw in reversed(regex_hits):", False),
    ("a quote wrapper is stripped even when the pattern is about quotes", "rx/extract.py",
     "                if inner and closer[-1] in inner:\n                    continue",
     "                if False:\n                    continue", False),
    ("code fences swallow their contents instead of only the fence lines", "rx/extract.py",
     '    return "\\n".join(line for line in text.splitlines() if not line.strip().startswith("```"))',
     '    return "\\n".join(line for line in text.splitlines() if "REGEX" not in line or True) '
     'if "```" not in text else ""', False),
    ("an empty answer after the marker counts as a pattern", "rx/extract.py",
     "        if candidate:\n            return Extraction(\"regex\", candidate, None)",
     "        return Extraction(\"regex\", candidate, None)", False),

    # ---- grading, where a wrong answer becomes a right one
    ("one wrong case is forgiven", "rx/grade.py",
     '    result["outcome"] = "pass" if not wrong else "fail"',
     '    result["outcome"] = "pass" if len(wrong) <= 1 else "fail"', False),
    ("the naive subset flag ignores which cases are naive", "rx/grade.py",
     '    result["naive_subset_pass"] = naive_wrong == 0',
     '    result["naive_subset_pass"] = True', False),
    ("a refusal is correct everywhere, including on solvable tasks", "rx/grade.py",
     '        result["correct"] = task.kind == "control_impossible"',
     '        result["correct"] = True', True),
    # Filed as a plain attack rather than a dormant guard, having been run and watched. No
    # recorded response timed out or failed to compile, so against the 108 real records this is
    # dormant and the fingerprint does not move. It moves anyway, because the synthetic probe
    # vector carries an invalid-pattern probe and that probe's outcome is inside the fingerprint.
    # Which is the probe vector doing the job it exists for, so gate 2 applies here in full.
    ("a timeout is folded into the wrong-answer bucket", "rx/grade.py",
     '    if run.status != "ok":\n        result["outcome"] = run.status',
     '    if run.status != "ok":\n        result["outcome"] = "fail"', False),

    # ---- the corpus, which is the ground truth itself
    ("a corpus label is flipped, so the ground truth lies", "data/tasks.json",
     '{"s": "24:00", "match": false, "trap": "class-boundary", "naive": false}',
     '{"s": "24:00", "match": true, "trap": "class-boundary", "naive": false}', False),
    ("the naive flag is inverted, so the held-out subset is the visible one", "rx/tasks.py",
     '                 naive=bool(case["naive"]))', '                 naive=not case["naive"])',
     False),
    ("an impossible control whose corpus is satisfiable loads anyway", "rx/tasks.py",
     "            if task.satisfiable:", "            if False:", True),
    ("a solvable task may contradict itself", "rx/tasks.py",
     "            if not task.satisfiable:", "            if False:", True),

    # ---- aggregation
    ("the illusion rate is divided by every response instead of the naive passers", "rx/stats.py",
     '        arm["illusion_rate"] = ratio(arm["naive_pass_full_fail"], arm["naive_subset_pass"])',
     '        arm["illusion_rate"] = ratio(arm["naive_pass_full_fail"], arm["n"])', False),
    ("the impossible control is counted as a solvable task", "rx/stats.py",
     '        if row["kind"] == "control_impossible":', "        if False:", False),
    ("the confidence interval uses the wrong z", "rx/stats.py",
     "Z = 1.959963984540054  # two sided 95 percent", "Z = 1.0  # two sided 95 percent", False),
    ("the trap breakdown counts every case as correct", "rx/stats.py",
     '            bucket["wrong"] += int(case["wrong"])', '            bucket["wrong"] += 0',
     False),

    # ---- the harness probe, which is what keeps the extractor branches measurable
    ("the synthetic probe vector is dropped from the fingerprint", "scripts/measure.py",
     '        "probes": [[row["id"], row["outcome"], row["pattern"]] for row in probes],',
     '        "probes": [],', False),
    ("a probe is graded against the wrong task", "scripts/measure.py",
     '        graded = grade.grade(index[probe["task"]], probe["response"])',
     '        graded = grade.grade(task_list[0], probe["response"])', False),

    # ---- the prompt, which is not read during re-analysis and so cannot move the fingerprint
    ("the prompt stops saying the pattern is run with re.search", "rx/prompt.py",
     "  re.fullmatch, anchor the pattern yourself if the requirement is about the whole string.",
     "  re.fullmatch, do whatever you think best.", True),
]


def copy_tree(destination: str) -> None:
    os.makedirs(destination, exist_ok=True)
    for name in os.listdir(ROOT):
        if name in SKIP:
            continue
        source = os.path.join(ROOT, name)
        target = os.path.join(destination, name)
        if os.path.isdir(source):
            shutil.copytree(source, target, ignore=shutil.ignore_patterns(*SKIP))
        else:
            shutil.copy2(source, target)


# One sabotage removes the timeout guard itself, which means the sabotaged tree really will hang
# forever on the catastrophic pattern in the unit suite. Every child here therefore gets its own
# outer bound, and a hang counts as a failing suite, which is what a hang is.
WALL = 240.0


def run(tree: str, args: list):
    try:
        return subprocess.run(
            [sys.executable, *args], cwd=tree, capture_output=True, text=True, timeout=WALL,
            env={**os.environ, "PYTHONPATH": tree, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired:
        return None


def fingerprint(tree: str):
    out = run(tree, ["scripts/measure.py", "--quiet"])
    if out is None:
        return None
    for line in out.stdout.splitlines():
        if line.startswith("FINGERPRINT "):
            return line.split(" ", 1)[1].strip()
    return None


def tests_pass(tree: str) -> bool:
    out = run(tree, ["-m", "unittest", "discover", "-s", "tests"])
    return out is not None and out.returncode == 0


def main() -> int:
    workspace = tempfile.mkdtemp(prefix="rx-sabotage-")

    baseline_tree = os.path.join(workspace, "baseline")
    copy_tree(baseline_tree)
    baseline = fingerprint(baseline_tree)
    if baseline is None:
        print("FAIL the baseline tree produced no fingerprint at all")
        return 1

    control_tree = os.path.join(workspace, "an-entirely-differently-named-directory")
    copy_tree(control_tree)
    control = fingerprint(control_tree)
    if control != baseline:
        print("FAIL null control: an unmodified copy fingerprinted differently.")
        print(f"     baseline {baseline}\n     control  {control}")
        print("     The measurement tracks the working directory, so gate 2 would pass for free")
        print("     for every sabotage below. Not scoring this run.")
        return 1
    print(f"null control: an unmodified copy fingerprints identically ({baseline[:16]})")

    if not tests_pass(baseline_tree):
        print("FAIL the suite does not pass on an unsabotaged tree, so a failure below would "
              "mean nothing")
        return 1
    print("baseline: the suite passes before anything is broken\n")

    caught = 0
    failures: list = []
    for index, (name, relative, find, replace, dormant) in enumerate(SABOTAGES):
        tree = os.path.join(workspace, f"s{index:02d}")
        copy_tree(tree)
        path = os.path.join(tree, relative)
        with open(path, encoding="utf-8") as handle:
            original = handle.read()
        if find not in original:
            failures.append(f"{name}: DID NOT APPLY, the target text is not in {relative}")
            print(f"  gate 1 FAIL  {name}")
            continue
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(original.replace(find, replace, 1))

        moved = fingerprint(tree)
        if dormant:
            if moved != baseline:
                failures.append(
                    f"{name}: filed as a dormant guard, but the measurement moved, so it was "
                    f"doing something visible. Rerun it as a plain attack.")
                print(f"  gate 2 FAIL  {name} (a dormant guard changed the output)")
                continue
        else:
            if moved is None:
                failures.append(f"{name}: the tree stopped producing a fingerprint at all, so "
                                f"gate 2 cannot tell a break from a crash")
                print(f"  gate 2 FAIL  {name} (no output to compare)")
                continue
            if moved == baseline:
                failures.append(f"{name}: APPLIED but the measurement did not move, so requiring "
                                f"the tests to catch it would be requiring an opinion about style")
                print(f"  gate 2 FAIL  {name} (output unchanged)")
                continue

        if tests_pass(tree):
            failures.append(f"{name}: NOT CAUGHT, the suite passed on a broken tree")
            print(f"  gate 3 FAIL  {name}")
            continue
        caught += 1
        print(f"  caught{' (dormant guard)' if dormant else '':17s} {name}")

    print(f"\n{caught} of {len(SABOTAGES)} sabotages applied, moved the measurement as expected, "
          f"and were caught")
    if failures:
        print("\nfailures:")
        for message in failures:
            print(f"  - {message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
