"""The aggregator, checked against rows whose totals were worked out by hand."""

import unittest

from rx import stats


def row(model="m", think=False, task="t", kind="normal", outcome="pass", correct=True,
        naive_ok=True, cases=()):
    return {"model": model, "think": think, "task": task, "kind": kind, "outcome": outcome,
            "correct": correct, "naive_subset_pass": naive_ok, "cases": list(cases)}


class TestStats(unittest.TestCase):
    def test_illusion_denominator_is_the_naive_passers_and_not_everything(self):
        rows = [
            row(outcome="pass", naive_ok=True, task="a"),
            row(outcome="fail", naive_ok=True, task="b"),
            row(outcome="fail", naive_ok=False, task="c"),
            row(outcome="invalid", naive_ok=False, task="d"),
        ]
        summary = stats.summarise(rows)
        arm = summary["arms"]["m think=False"]
        self.assertEqual(arm["naive_subset_pass"], 2)
        self.assertEqual(arm["naive_pass_full_fail"], 1)
        self.assertEqual(arm["illusion_rate"], 0.5)

    def test_the_impossible_control_is_kept_out_of_the_solvable_denominator(self):
        rows = [
            row(kind="normal", outcome="pass", task="a"),
            row(kind="control_impossible", outcome="refused", task="z"),
        ]
        arm = stats.summarise(rows)["arms"]["m think=False"]
        self.assertEqual(arm["solvable_n"], 1)
        self.assertEqual(arm["impossible_n"], 1)
        self.assertEqual(arm["impossible_refused"], 1)
        self.assertEqual(arm["solvable_pass_rate"], 1.0)

    def test_a_refusal_on_a_solvable_task_is_a_false_refusal(self):
        arm = stats.summarise([row(kind="normal", outcome="refused", naive_ok=False)])["arms"][
            "m think=False"]
        self.assertEqual(arm["false_refusal"], 1)
        self.assertEqual(arm["solvable_pass"], 0)

    def test_arms_are_split_by_the_think_setting(self):
        summary = stats.summarise([row(think=True), row(think=False)])
        self.assertEqual(sorted(summary["arms"]), ["m think=False", "m think=True"])

    def test_trap_breakdown_counts_cases_not_responses(self):
        cases = [{"task": "t", "trap": "anchor", "naive": False, "wrong": True},
                 {"task": "t", "trap": "anchor", "naive": False, "wrong": False},
                 {"task": "t", "trap": "greedy", "naive": False, "wrong": True}]
        traps = stats.summarise([row(cases=cases)])["traps"]
        self.assertEqual(traps["anchor"], {"cases": 2, "wrong": 1, "error_rate": 0.5})
        self.assertEqual(traps["greedy"]["error_rate"], 1.0)

    def test_wilson_interval_brackets_the_point_estimate(self):
        low, high = stats.wilson(5, 10)
        self.assertLess(low, 0.5)
        self.assertGreater(high, 0.5)
        self.assertAlmostEqual(low, 0.2365931, places=5)
        self.assertAlmostEqual(high, 0.7634069, places=5)

    def test_wilson_on_an_empty_denominator_does_not_divide_by_zero(self):
        self.assertEqual(stats.wilson(0, 0), (0.0, 0.0))

    def test_a_perfect_score_does_not_produce_an_interval_above_one(self):
        low, high = stats.wilson(20, 20)
        self.assertLessEqual(high, 1.0)
        self.assertGreater(low, 0.7)


if __name__ == "__main__":
    unittest.main()
