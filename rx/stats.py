"""Aggregate graded records into the numbers the README reports.

The headline is the illusion rate: among responses whose regex is correct on the naive subset,
the share that is wrong on the held-out cases. That number only means something because the naive
subset was chosen in advance and is marked in data/tasks.json, not carved out after seeing results.
"""

from __future__ import annotations

import math

Z = 1.959963984540054  # two sided 95 percent


def wilson(successes: int, total: int) -> tuple:
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + Z * Z / total
    centre = (p + Z * Z / (2 * total)) / denominator
    spread = Z * math.sqrt(p * (1 - p) / total + Z * Z / (4 * total * total)) / denominator
    return (max(0.0, centre - spread), min(1.0, centre + spread))


def blank_arm() -> dict:
    return {
        "n": 0,
        "outcomes": {},
        "solvable_n": 0,
        "solvable_pass": 0,
        "naive_subset_pass": 0,
        "naive_pass_full_fail": 0,
        "easy_n": 0,
        "easy_pass": 0,
        "impossible_n": 0,
        "impossible_refused": 0,
        "false_refusal": 0,
        "timeouts": 0,
        "invalid": 0,
    }


def summarise(graded_rows: list) -> dict:
    """graded_rows: dicts with model, think, task, kind, outcome, correct, naive_subset_pass."""
    arms: dict = {}
    tasks: dict = {}
    traps: dict = {}

    for row in graded_rows:
        key = f"{row['model']} think={row['think']}"
        arm = arms.setdefault(key, blank_arm())
        arm["n"] += 1
        arm["outcomes"][row["outcome"]] = arm["outcomes"].get(row["outcome"], 0) + 1
        if row["outcome"] == "timeout":
            arm["timeouts"] += 1
        if row["outcome"] == "invalid":
            arm["invalid"] += 1

        if row["kind"] == "control_impossible":
            arm["impossible_n"] += 1
            arm["impossible_refused"] += int(row["outcome"] == "refused")
        else:
            arm["solvable_n"] += 1
            arm["solvable_pass"] += int(row["outcome"] == "pass")
            arm["false_refusal"] += int(row["outcome"] == "refused")
            if row["outcome"] in ("pass", "fail"):
                arm["naive_subset_pass"] += int(row["naive_subset_pass"])
                if row["naive_subset_pass"] and row["outcome"] == "fail":
                    arm["naive_pass_full_fail"] += 1
            if row["kind"] == "control_easy":
                arm["easy_n"] += 1
                arm["easy_pass"] += int(row["outcome"] == "pass")

        cell = tasks.setdefault(row["task"], {"n": 0, "pass": 0, "kind": row["kind"],
                                              "refused": 0})
        cell["n"] += 1
        cell["pass"] += int(row["outcome"] == "pass")
        cell["refused"] += int(row["outcome"] == "refused")

        for case in row.get("cases", []):
            bucket = traps.setdefault(case["trap"], {"cases": 0, "wrong": 0})
            bucket["cases"] += 1
            bucket["wrong"] += int(case["wrong"])

    for arm in arms.values():
        arm["solvable_pass_rate"] = ratio(arm["solvable_pass"], arm["solvable_n"])
        arm["solvable_pass_ci"] = wilson(arm["solvable_pass"], arm["solvable_n"])
        arm["illusion_rate"] = ratio(arm["naive_pass_full_fail"], arm["naive_subset_pass"])
        arm["illusion_ci"] = wilson(arm["naive_pass_full_fail"], arm["naive_subset_pass"])

    for cell in tasks.values():
        cell["pass_rate"] = ratio(cell["pass"], cell["n"])
    for bucket in traps.values():
        bucket["error_rate"] = ratio(bucket["wrong"], bucket["cases"])

    total_naive = sum(arm["naive_subset_pass"] for arm in arms.values())
    total_illusion = sum(arm["naive_pass_full_fail"] for arm in arms.values())
    return {
        "arms": dict(sorted(arms.items())),
        "tasks": dict(sorted(tasks.items())),
        "traps": dict(sorted(traps.items())),
        "overall": {
            "responses": sum(arm["n"] for arm in arms.values()),
            "naive_subset_pass": total_naive,
            "naive_pass_full_fail": total_illusion,
            "illusion_rate": ratio(total_illusion, total_naive),
            "illusion_ci": wilson(total_illusion, total_naive),
            "solvable_n": sum(arm["solvable_n"] for arm in arms.values()),
            "solvable_pass": sum(arm["solvable_pass"] for arm in arms.values()),
        },
    }


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
