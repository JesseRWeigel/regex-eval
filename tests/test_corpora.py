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

    def load_edited(self, edit):
        """Write a copy of the real task file with `edit` applied to it and load that.

        `load` raises ValueError for six different reasons, so the tests below match on the
        message. Asserting only the type would pass on any of the other five, which is the same as
        not testing the guard at all.
        """
        import copy
        import json
        import os
        import tempfile
        with open(tasks.TASKS_PATH, encoding="utf-8") as source:
            raw = json.load(source)
        broken = copy.deepcopy(raw)
        edit(broken)
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(broken, handle)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_loader_rejects_a_contradictory_normal_task(self):
        def contradict(raw):
            victim = [entry for entry in raw["tasks"] if entry["kind"] == "normal"][0]
            first = dict(victim["cases"][0])
            first["match"] = not first["match"]
            victim["cases"].append(first)

        with self.assertRaisesRegex(ValueError, "labels the same string both ways"):
            tasks.load(self.load_edited(contradict))

    def test_loader_rejects_an_impossible_control_that_is_satisfiable(self):
        """The other half of the same guard, and the half that has no visible effect on the data.

        A satisfiable impossible control still loads, still grades and still produces every number
        in the summary, so nothing downstream can notice that the check is gone. That makes this
        test the only thing standing between the control and quietly becoming an ordinary task.
        """
        def resolve(raw):
            victim = [entry for entry in raw["tasks"] if entry["kind"] == "control_impossible"][0]
            seen: dict = {}
            kept = []
            for case in victim["cases"]:
                if case["s"] in seen and seen[case["s"]] != case["match"]:
                    continue
                seen[case["s"]] = case["match"]
                kept.append(case)
            victim["cases"] = kept

        with self.assertRaisesRegex(ValueError, "an impossible control whose corpus is satisfiable"):
            tasks.load(self.load_edited(resolve))

    def test_loader_rejects_a_solvable_task_with_no_held_out_cases(self):
        def mark_everything_naive(raw):
            victim = [entry for entry in raw["tasks"] if entry["kind"] == "normal"][0]
            for case in victim["cases"]:
                case["naive"] = True

        with self.assertRaisesRegex(ValueError, "every case is marked naive"):
            tasks.load(self.load_edited(mark_everything_naive))

    def test_loader_rejects_a_solvable_task_with_no_naive_cases(self):
        def mark_nothing_naive(raw):
            victim = [entry for entry in raw["tasks"] if entry["kind"] == "normal"][0]
            for case in victim["cases"]:
                case["naive"] = False

        with self.assertRaisesRegex(ValueError, "no case is marked naive"):
            tasks.load(self.load_edited(mark_nothing_naive))


if __name__ == "__main__":
    unittest.main()
