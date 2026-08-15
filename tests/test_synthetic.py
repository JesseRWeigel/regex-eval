"""Run the whole analysis over invented responses whose scores are known in advance.

This is the end to end check that the reported statistics mean what the README says. Four
synthetic arms are built by hand: a perfect solver, a naive solver, a refuser, and a model that
answers with a catastrophic pattern. The expected counts are written out as literals rather than
derived, because a test that computes its own expectation with the code under test is a mirror.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "scripts"))

import measure  # noqa: E402

from rx import tasks  # noqa: E402


def synthetic_records(label: str, responder) -> list:
    records = []
    for sample in range(2):
        for task in tasks.load():
            records.append({"model": label, "think": False, "sample": sample, "task": task.id,
                            "response": responder(task)})
    return records


class TestSynthetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = tasks.load()
        cls.solvable = [task for task in cls.tasks if task.kind != "control_impossible"]

    def summarise(self, records):
        rows = measure.grade_all(records, self.tasks)
        return measure.build_summary(rows, self.tasks), rows

    def test_a_perfect_solver_scores_every_solvable_task_and_refuses_the_control(self):
        def answer(task):
            if task.reference is None:
                return "IMPOSSIBLE: the corpus labels one string both ways"
            return f"REGEX: {task.reference}"

        summary, _ = self.summarise(synthetic_records("perfect", answer))
        arm = summary["arms"]["perfect think=False"]
        self.assertEqual(arm["n"], 24)
        self.assertEqual(arm["solvable_n"], 22)
        self.assertEqual(arm["solvable_pass"], 22)
        self.assertEqual(arm["impossible_refused"], 2)
        self.assertEqual(arm["false_refusal"], 0)
        self.assertEqual(arm["naive_pass_full_fail"], 0)
        self.assertEqual(summary["overall"]["illusion_rate"], 0.0)

    def test_a_naive_solver_looks_right_and_is_wrong_every_time(self):
        def answer(task):
            if task.naive_pattern is None:
                return "REGEX: q"
            return f"REGEX: {task.naive_pattern}"

        summary, _ = self.summarise(synthetic_records("naive", answer))
        arm = summary["arms"]["naive think=False"]
        self.assertEqual(arm["solvable_pass"], 0)
        self.assertEqual(arm["naive_subset_pass"], 22)
        self.assertEqual(arm["naive_pass_full_fail"], 22)
        self.assertEqual(summary["overall"]["illusion_rate"], 1.0)
        self.assertEqual(arm["impossible_refused"], 0)

    def test_a_refuser_gets_the_impossible_control_and_nothing_else(self):
        summary, _ = self.summarise(
            synthetic_records("refuser", lambda task: "IMPOSSIBLE: I decline"))
        arm = summary["arms"]["refuser think=False"]
        self.assertEqual(arm["impossible_refused"], 2)
        self.assertEqual(arm["false_refusal"], 22)
        self.assertEqual(arm["solvable_pass"], 0)
        self.assertEqual(arm["naive_subset_pass"], 0,
                         "a refusal has no pattern, so it cannot enter the illusion denominator")

    def test_timeouts_are_counted_apart_from_wrong_answers(self):
        # No shipped corpus contains a string long enough to blow up, so the pathological task is
        # built here. A timeout must reach the summary as its own outcome and must contribute
        # nothing to the wrong-answer counts or to the trap breakdown.
        evil = tasks.Task(id="evil", kind="normal", requirement="unused", reference=None,
                          naive_pattern=None,
                          cases=(tasks.Case(s="a" * 34 + "!", match=False, trap="plain",
                                            naive=True),))
        records = [{"model": "hangs", "think": False, "sample": index, "task": "evil",
                    "response": "REGEX: ^(a+)+$"} for index in range(2)]
        rows = measure.grade_all(records, [evil], timeout=3.0)
        summary = measure.build_summary(rows, [evil])
        arm = summary["arms"]["hangs think=False"]
        self.assertEqual(arm["outcomes"], {"timeout": 2})
        self.assertEqual(arm["timeouts"], 2)
        self.assertEqual(arm["solvable_pass"], 0)
        self.assertEqual(arm["naive_subset_pass"], 0)
        self.assertEqual(summary["traps"], {})
        for row in rows:
            self.assertEqual(row["n_wrong"], 0)
            self.assertEqual(row["cases"], [])

    def test_an_invalid_pattern_never_reaches_the_trap_breakdown(self):
        summary, _ = self.summarise(synthetic_records("broken", lambda task: "REGEX: (["))
        arm = summary["arms"]["broken think=False"]
        self.assertEqual(arm["invalid"], 24)
        self.assertEqual(summary["traps"], {})

    def test_the_fingerprint_moves_when_one_response_changes(self):
        records = synthetic_records("perfect", lambda task: f"REGEX: {task.reference or 'q'}")
        rows = measure.grade_all(records, self.tasks)
        before = measure.fingerprint(measure.build_summary(rows, self.tasks), rows)
        records[3]["response"] = "REGEX: .*"
        rows = measure.grade_all(records, self.tasks)
        after = measure.fingerprint(measure.build_summary(rows, self.tasks), rows)
        self.assertNotEqual(before, after)

    def test_the_fingerprint_is_stable_across_repeated_runs(self):
        records = synthetic_records("perfect", lambda task: f"REGEX: {task.reference or 'q'}")
        seen = set()
        for _ in range(2):
            rows = measure.grade_all(records, self.tasks)
            seen.add(measure.fingerprint(measure.build_summary(rows, self.tasks), rows))
        self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    unittest.main()
