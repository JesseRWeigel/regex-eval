"""Load the task set and refuse to load a corpus that contradicts itself.

The corpus is the ground truth, so a mislabelled case would silently become a wrong finding for
every model at once. `reference` and `naive_pattern` are here for the unit suite to check the
labels against, and nothing in the grading path reads them.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_PATH = os.path.join(ROOT, "data", "tasks.json")

KINDS = ("normal", "control_easy", "control_impossible")


@dataclass(frozen=True)
class Case:
    s: str
    match: bool
    trap: str
    naive: bool


@dataclass(frozen=True)
class Task:
    id: str
    kind: str
    requirement: str
    reference: str | None
    naive_pattern: str | None
    cases: tuple

    @property
    def strings(self) -> list:
        return [case.s for case in self.cases]

    @property
    def naive_cases(self) -> list:
        return [case for case in self.cases if case.naive]

    @property
    def satisfiable(self) -> bool:
        """False when two identical strings carry opposite labels, which no regex can satisfy."""
        seen: dict = {}
        for case in self.cases:
            if case.s in seen and seen[case.s] != case.match:
                return False
            seen[case.s] = case.match
        return True


def load(path: str = TASKS_PATH) -> list:
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)
    tasks = []
    seen_ids: set = set()
    for entry in raw["tasks"]:
        if entry["kind"] not in KINDS:
            raise ValueError(f"{entry['id']}: unknown kind {entry['kind']!r}")
        if entry["id"] in seen_ids:
            raise ValueError(f"duplicate task id {entry['id']!r}")
        seen_ids.add(entry["id"])
        if not entry["cases"]:
            raise ValueError(f"{entry['id']}: empty corpus")
        cases = tuple(
            Case(s=case["s"], match=bool(case["match"]), trap=case["trap"],
                 naive=bool(case["naive"]))
            for case in entry["cases"]
        )
        task = Task(id=entry["id"], kind=entry["kind"], requirement=entry["requirement"],
                    reference=entry["reference"], naive_pattern=entry["naive_pattern"],
                    cases=cases)
        if task.kind == "control_impossible":
            if task.satisfiable:
                raise ValueError(f"{task.id}: an impossible control whose corpus is satisfiable "
                                 f"is not a control, it is an ordinary task")
        else:
            if not task.satisfiable:
                raise ValueError(f"{task.id}: the corpus labels the same string both ways")
            if not task.reference:
                raise ValueError(f"{task.id}: a solvable task needs a reference for the "
                                 f"label check")
            if not task.naive_cases:
                raise ValueError(f"{task.id}: no case is marked naive, so the naive subset "
                                 f"comparison would be vacuous")
            if len(task.naive_cases) == len(task.cases):
                raise ValueError(f"{task.id}: every case is marked naive, so nothing is held out")
        tasks.append(task)
    return tasks


def by_id(tasks: list) -> dict:
    return {task.id: task for task in tasks}
