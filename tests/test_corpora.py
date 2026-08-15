"""The corpus is the ground truth, so it gets tested harder than anything else here.

Two properties matter. The labels must be right, which is checked by running a reference pattern
written by hand over every case. And the held-out cases must have teeth, which is checked by
running a deliberately naive pattern and requiring it to be perfect on the naive subset and wrong
on the full corpus. A trap that no plausible naive answer trips is decoration.
"""

import re
import unittest

from rx import tasks


class TestCorpora(unittest.TestCase):
    def setUp(self):
        self.tasks = tasks.load()

    def test_task_set_shape(self):
        kinds = [task.kind for task in self.tasks]
        self.assertEqual(kinds.count("control_easy"), 1)
        self.assertEqual(kinds.count("control_impossible"), 1)
        self.assertGreaterEqual(kinds.count("normal"), 8)
        self.assertEqual(len(self.tasks), 12)
        self.assertEqual(sum(len(task.cases) for task in self.tasks), 168)

    def test_reference_pattern_reproduces_every_label(self):
        for task in self.tasks:
            if task.reference is None:
                continue
            with self.subTest(task=task.id):
                compiled = re.compile(task.reference)
                for case in task.cases:
                    self.assertEqual(bool(compiled.search(case.s)), case.match,
                                     f"{task.id}: reference disagrees with the label for "
                                     f"{case.s!r}")

    def test_naive_pattern_passes_the_naive_subset(self):
        for task in self.tasks:
            if task.naive_pattern is None:
                continue
            with self.subTest(task=task.id):
                compiled = re.compile(task.naive_pattern)
                for case in task.naive_cases:
                    self.assertEqual(bool(compiled.search(case.s)), case.match,
                                     f"{task.id}: the naive pattern is already wrong on the "
                                     f"naive case {case.s!r}, so the illusion is not measured")

    def test_naive_pattern_fails_the_full_corpus(self):
        for task in self.tasks:
            if task.naive_pattern is None:
                continue
            with self.subTest(task=task.id):
                compiled = re.compile(task.naive_pattern)
                wrong = [case.s for case in task.cases
                         if bool(compiled.search(case.s)) != case.match]
                self.assertTrue(wrong, f"{task.id}: the naive pattern passes the whole corpus, "
                                       f"so this task holds nothing back")

    def test_every_task_has_a_boundary_case(self):
        for task in self.tasks:
            if task.kind == "control_impossible":
                continue
            with self.subTest(task=task.id):
                traps = {case.trap for case in task.cases}
                self.assertTrue({"boundary", "class-boundary", "length"} & traps,
                                f"{task.id}: no boundary case at all")

    def test_the_impossible_control_is_actually_impossible(self):
        impossible = [task for task in self.tasks if task.kind == "control_impossible"]
        self.assertEqual(len(impossible), 1)
        task = impossible[0]
        self.assertFalse(task.satisfiable)
        conflicts = [case.s for case in task.cases
                     if sum(1 for other in task.cases if other.s == case.s
                            and other.match != case.match)]
        self.assertTrue(conflicts, "the impossible control must label one string both ways, "
                                   "which is what proves no pattern can score full marks")

    def test_no_regex_at_all_can_pass_the_impossible_control(self):
        """Not an argument, a demonstration: try every reference and naive pattern in the file."""
        task = [t for t in self.tasks if t.kind == "control_impossible"][0]
        candidates = [t.reference for t in self.tasks if t.reference]
        candidates += [t.naive_pattern for t in self.tasks if t.naive_pattern]
        candidates += [".*", "q", "^(?!quick$).*q.*$", "(?!)", "", "^$"]
        for pattern in candidates:
            compiled = re.compile(pattern)
            wrong = [case.s for case in task.cases
                     if bool(compiled.search(case.s)) != case.match]
            self.assertTrue(wrong, f"{pattern!r} passed a corpus that must be unsatisfiable")

    def test_loader_rejects_a_contradictory_normal_task(self):
        import copy
        import json
        import os
        import tempfile
        with open(tasks.TASKS_PATH, encoding="utf-8") as source:
            raw = json.load(source)
        broken = copy.deepcopy(raw)
        victim = [entry for entry in broken["tasks"] if entry["kind"] == "normal"][0]
        first = dict(victim["cases"][0])
        first["match"] = not first["match"]
        victim["cases"].append(first)
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(broken, handle)
        handle.close()
        try:
            with self.assertRaises(ValueError):
                tasks.load(handle.name)
        finally:
            os.unlink(handle.name)


if __name__ == "__main__":
    unittest.main()
