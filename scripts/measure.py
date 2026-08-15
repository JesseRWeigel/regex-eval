#!/usr/bin/env python3
"""Recompute every reported number from the committed raw records, and fingerprint the result.

No model is contacted here. The raw JSONL under results/ holds the prompts and the responses
exactly as they came back, and the grading is executable: each candidate regex is compiled and run
over its corpus in a guarded child process. So the whole analysis is reproducible by anyone, and
the fingerprint below is the thing sabotage.py watches for movement.

The fingerprint hashes the derived statistics only. No absolute path and no timing goes into it,
because a fingerprint that moves for reasons unrelated to the code hands every sabotage a free
pass at gate 2.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rx import execute, grade, stats, tasks  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")
SUMMARY_PATH = os.path.join(RESULTS, "summary.json")


def load_records() -> list:
    records = []
    for path in sorted(glob.glob(os.path.join(RESULTS, "run-*.jsonl"))):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
    return records


def grade_all(records: list, task_list: list,
              timeout: float = execute.DEFAULT_TIMEOUT) -> list:
    index = tasks.by_id(task_list)
    rows = []
    for record in sorted(records, key=lambda r: (r["model"], r["think"], r["sample"], r["task"])):
        task = index[record["task"]]
        graded = grade.grade(task, record["response"], timeout=timeout)
        rows.append({
            "model": record["model"],
            "think": record["think"],
            "sample": record["sample"],
            "task": task.id,
            "kind": task.kind,
            "outcome": graded["outcome"],
            "correct": graded["correct"],
            "naive_subset_pass": graded["naive_subset_pass"],
            "pattern": graded["pattern"],
            "wrong_traps": sorted({entry["trap"] for entry in graded["wrong_cases"]}),
            "n_wrong": len(graded["wrong_cases"]),
            "cases": grade.case_level(task, graded),
        })
    return rows


def build_summary(rows: list, task_list: list) -> dict:
    summary = stats.summarise(rows)
    summary["meta"] = {
        "tasks": len(task_list),
        "corpus_cases": sum(len(task.cases) for task in task_list),
        "responses": len(rows),
        "arms": len(summary["arms"]),
    }
    return summary


def fingerprint(summary: dict, rows: list) -> str:
    payload = {
        "summary": summary,
        "outcomes": [[row["model"], row["think"], row["sample"], row["task"], row["outcome"],
                      row["n_wrong"], row["wrong_traps"]] for row in rows],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def percent(value: float) -> str:
    return f"{100 * value:5.1f}%"


def report(summary: dict) -> None:
    meta = summary["meta"]
    print(f"{meta['responses']} responses, {meta['arms']} arm(s), {meta['tasks']} tasks, "
          f"{meta['corpus_cases']} corpus cases")
    print("\narm                                 n  solvable pass   naive-ok  illusion  "
          "timeouts invalid")
    for name, arm in summary["arms"].items():
        print(f"{name:32s} {arm['n']:4d} {percent(arm['solvable_pass_rate'])} "
              f"{arm['solvable_pass']:3d}/{arm['solvable_n']:<3d} {arm['naive_subset_pass']:4d} "
              f"   {percent(arm['illusion_rate'])} {arm['naive_pass_full_fail']:3d}/"
              f"{arm['naive_subset_pass']:<3d} {arm['timeouts']:5d} {arm['invalid']:5d}")

    print("\ncontrols")
    for name, arm in summary["arms"].items():
        print(f"  {name:30s} easy {arm['easy_pass']}/{arm['easy_n']}   "
              f"impossible refused {arm['impossible_refused']}/{arm['impossible_n']}   "
              f"false refusals on solvable tasks {arm['false_refusal']}")

    print("\nper task pass rate")
    for name, cell in summary["tasks"].items():
        marker = {"control_easy": " [easy control]",
                  "control_impossible": " [impossible control, refusals: %d]" % cell["refused"],
                  "normal": ""}[cell["kind"]]
        print(f"  {name:14s} {cell['pass']:3d}/{cell['n']:<3d} {percent(cell['pass_rate'])}"
              f"{marker}")

    print("\nerror rate by held-out case type, over runnable regexes")
    for name, bucket in sorted(summary["traps"].items(),
                               key=lambda item: -item[1]["error_rate"]):
        print(f"  {name:18s} {bucket['wrong']:4d}/{bucket['cases']:<5d} "
              f"{percent(bucket['error_rate'])}")

    overall = summary["overall"]
    low, high = overall["illusion_ci"]
    print(f"\nheadline: of {overall['naive_subset_pass']} regexes that are correct on the naive "
          f"subset,\n          {overall['naive_pass_full_fail']} are wrong on the held-out cases, "
          f"{percent(overall['illusion_rate'])} "
          f"(95% CI {100 * low:.1f} to {100 * high:.1f})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="refresh results/summary.json")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    task_list = tasks.load()
    records = load_records()
    if not records:
        print("FAIL no records under results/run-*.jsonl, so there is nothing to measure")
        return 1
    rows = grade_all(records, task_list)
    summary = build_summary(rows, task_list)
    if not args.quiet:
        report(summary)
    if args.write:
        with open(SUMMARY_PATH, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
    print(f"FINGERPRINT {fingerprint(summary, rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
