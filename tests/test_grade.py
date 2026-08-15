"""Grade known-good, known-bad and known-pathological answers, where the answer is not in doubt.

Every case here is one where a human can say in advance what the outcome must be, which is the
only way to tell a working grader from a grader that agrees with itself.
"""

import unittest

from rx import grade, tasks


class TestGrade(unittest.TestCase):
    def setUp(self):
        self.by_id = tasks.by_id(tasks.load())

    def grade(self, task_id, response, **kwargs):
        return grade.grade(self.by_id[task_id], response, **kwargs)

    def test_the_reference_answer_passes_every_solvable_task(self):
        for task in self.by_id.values():
            if not task.reference:
                continue
            with self.subTest(task=task.id):
                result = grade.grade(task, f"REGEX: {task.reference}")
                self.assertEqual(result["outcome"], "pass", result["wrong_cases"])
                self.assertTrue(result["correct"])

    def test_the_naive_answer_passes_the_naive_subset_and_fails_the_corpus(self):
        for task in self.by_id.values():
            if not task.naive_pattern:
                continue
            with self.subTest(task=task.id):
                result = grade.grade(task, f"REGEX: {task.naive_pattern}")
                self.assertEqual(result["outcome"], "fail")
                self.assertTrue(result["naive_subset_pass"],
                                "this is the whole illusion measurement, and it is empty if the "
                                "naive answer already fails the naive subset")

    def test_an_unanchored_answer_is_caught_by_the_corpus(self):
        result = self.grade("literal", "REGEX: cat")
        self.assertEqual(result["outcome"], "fail")
        self.assertIn("cats", [entry["s"] for entry in result["wrong_cases"]])

    def test_the_easy_control_is_passed_by_the_obvious_answer(self):
        self.assertEqual(self.grade("literal", "REGEX: ^cat$")["outcome"], "pass")

    def test_refusing_the_impossible_control_is_correct(self):
        result = self.grade("contradiction", "IMPOSSIBLE: quick must both match and not match")
        self.assertEqual(result["outcome"], "refused")
        self.assertTrue(result["correct"])

    def test_answering_the_impossible_control_with_a_regex_is_not_correct(self):
        for pattern in ("q", "^(?!quick$).*q", ".*"):
            result = self.grade("contradiction", f"REGEX: {pattern}")
            self.assertIn(result["outcome"], ("fail", "pass"))
            self.assertFalse(result["correct"],
                             "no regex may be scored correct on an unsatisfiable corpus")

    def test_refusing_a_solvable_task_is_not_correct(self):
        result = self.grade("zip", "IMPOSSIBLE: too hard")
        self.assertEqual(result["outcome"], "refused")
        self.assertFalse(result["correct"])

    def test_an_uncompilable_answer_is_invalid_and_not_merely_wrong(self):
        result = self.grade("zip", "REGEX: ^[0-9]{5}(?:-[0-9]{4}$")
        self.assertEqual(result["outcome"], "invalid")
        self.assertFalse(result["correct"])

    def test_a_catastrophic_answer_times_out_and_is_not_counted_as_wrong(self):
        # None of the shipped corpora contain a string long enough to blow up, which is by design:
        # the eval measures correctness and not endurance. The guard still has to work, so this
        # builds the pathological case explicitly rather than hoping a corpus provokes it.
        evil = tasks.Task(
            id="evil", kind="normal", requirement="unused in grading",
            reference=None, naive_pattern=None,
            cases=(tasks.Case(s="a" * 34 + "!", match=False, trap="plain", naive=True),),
        )
        result = grade.grade(evil, "REGEX: ^(a+)+$", timeout=3.0)
        self.assertEqual(result["outcome"], "timeout")
        self.assertFalse(result["correct"])
        self.assertEqual(result["wrong_cases"], [])
        self.assertEqual(grade.case_level(evil, result), [])

    def test_one_wrong_case_is_still_a_failure(self):
        # This is the whole point of an executable ground truth. The pattern below is what a
        # careful person writes, and it is wrong on exactly one of sixteen strings.
        result = self.grade("zip", "REGEX: \\A\\d{5}(?:-\\d{4})?\\Z")
        self.assertEqual(result["outcome"], "fail")
        self.assertEqual(len(result["wrong_cases"]), 1)
        self.assertTrue(result["naive_subset_pass"])

    def test_a_response_that_fails_the_naive_subset_is_recorded_as_such(self):
        result = self.grade("zip", "REGEX: .*")
        self.assertEqual(result["outcome"], "fail")
        self.assertFalse(result["naive_subset_pass"],
                         "the naive subset flag must reflect the naive cases only, and a pattern "
                         "that matches everything fails them")

    def test_a_silent_model_is_no_answer(self):
        self.assertEqual(self.grade("zip", "I would rather not.")["outcome"], "no_answer")

    def test_case_rows_only_exist_for_regexes_that_ran(self):
        ran = self.grade("zip", "REGEX: ^[0-9]{5}$")
        self.assertEqual(len(grade.case_level(self.by_id["zip"], ran)), 16)
        for response in ("REGEX: (", "I decline"):
            broken = self.grade("zip", response)
            self.assertEqual(grade.case_level(self.by_id["zip"], broken), [])

    def test_case_rows_mark_exactly_the_wrong_cases(self):
        result = self.grade("zip", "REGEX: \\A\\d{5}(?:-\\d{4})?\\Z")
        rows = grade.case_level(self.by_id["zip"], result)
        wrong = [row for row in rows if row["wrong"]]
        self.assertEqual([row["trap"] for row in wrong], ["unicode-digit"],
                         "backslash-d admits Arabic-Indic digits, and that is the only case this "
                         "otherwise correct pattern should miss")


if __name__ == "__main__":
    unittest.main()
