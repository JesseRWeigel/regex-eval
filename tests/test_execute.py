"""The timeout guard gets its own test, because a guard nobody has seen fire is a comment.

`(a+)+$` against a run of a's ending in a non-matching character is the standard exponential
blow-up. At 34 a's it will not finish in this decade, so if the guard were missing this test would
hang rather than fail, which is why it also asserts the elapsed time.
"""

import time
import unittest
from unittest import mock

from rx import execute

EVIL = r"(a+)+$"
EVIL_INPUT = "a" * 34 + "!"


class TestExecute(unittest.TestCase):
    def test_ordinary_pattern(self):
        run = execute.run_corpus(r"\Acat\Z", ["cat", "cats", ""])
        self.assertEqual(run.status, "ok")
        self.assertEqual(run.hits, (True, False, False))

    def test_search_semantics_not_fullmatch(self):
        run = execute.run_corpus("cat", ["a cat here"])
        self.assertEqual(run.hits, (True,))

    def test_invalid_pattern_is_its_own_outcome(self):
        run = execute.run_corpus("(unclosed", ["x"])
        self.assertEqual(run.status, "invalid")
        self.assertIn("unterminated subpattern", run.detail,
                      "the detail has to carry what re said, not merely that something went "
                      "wrong, or a rewritten error path would still look correct here")

    def test_a_child_that_stops_early_is_a_crash_and_says_how_far_it_got(self):
        """The completeness check is dormant while the child behaves, so it needs forcing.

        Nothing a model can write makes the child stop mid-transcript, which is why deleting the
        check moves no reported number. Truncating the child on purpose is the only way the suite
        notices the check is gone.
        """
        truncated = execute.CHILD.replace('for index, item in enumerate(payload["strings"]):',
                                          'for index, item in enumerate(payload["strings"][:1]):')
        self.assertNotEqual(truncated, execute.CHILD, "the child source has drifted, so this test "
                                                      "would be exercising nothing")
        with mock.patch.object(execute, "CHILD", truncated):
            run = execute.run_corpus("a", ["a", "a", "a"])
        self.assertEqual(run.status, "crash", "a partial transcript is not a result")
        self.assertEqual(run.detail, "the child reported 1 of 3 cases")
        self.assertEqual(run.reached, 1)

    def test_a_child_that_never_reports_DONE_is_a_crash(self):
        no_done = execute.CHILD.replace('print("DONE", flush=True)', "pass")
        self.assertNotEqual(no_done, execute.CHILD, "the child source has drifted, so this test "
                                                    "would be exercising nothing")
        with mock.patch.object(execute, "CHILD", no_done):
            run = execute.run_corpus("a", ["a", "b"])
        self.assertEqual(run.status, "crash", "every case answered is still not a finished run, "
                                              "because a kill mid-write looks the same")
        self.assertIn("2 of 2", run.detail)

    def test_a_child_that_answers_out_of_order_is_a_crash(self):
        shuffled = execute.CHILD.replace('print(f"CASE {index} {hit}", flush=True)',
                                         'print(f"CASE {len(payload[\'strings\']) - index - 1} '
                                         '{hit}", flush=True)')
        self.assertNotEqual(shuffled, execute.CHILD, "the child source has drifted, so this test "
                                                     "would be exercising nothing")
        with mock.patch.object(execute, "CHILD", shuffled):
            run = execute.run_corpus("a", ["a", "b", "a"])
        self.assertEqual(run.status, "crash")
        self.assertEqual(run.detail, "the child emitted cases out of order")

    def test_the_guard_fires_on_catastrophic_backtracking(self):
        started = time.time()
        run = execute.run_corpus(EVIL, [EVIL_INPUT], timeout=3.0)
        elapsed = time.time() - started
        self.assertEqual(run.status, "timeout")
        self.assertLess(elapsed, 20.0, "the guard did not stop the child")
        self.assertEqual(run.hits, ())

    def test_a_timeout_reports_how_far_it_got(self):
        run = execute.run_corpus(EVIL, ["a", "aa", EVIL_INPUT], timeout=3.0)
        self.assertEqual(run.status, "timeout")
        self.assertGreaterEqual(run.reached, 2, "the child should have answered the easy cases "
                                                "before hanging on the hard one")

    def test_the_evil_pattern_is_genuinely_evil(self):
        """Without this, a guard test could pass against a pattern that is merely slow."""
        run = execute.run_corpus(EVIL, ["a" * 12 + "!"], timeout=20.0)
        self.assertEqual(run.status, "ok", "a short input should still finish, so the blow-up is "
                                           "in the input length and not in the harness")

    def test_unicode_survives_the_round_trip(self):
        run = execute.run_corpus(r"\A[0-9]{5}\Z", ["١٢٣٤٥", "12345"])
        self.assertEqual(run.hits, (False, True))

    def test_newline_in_a_case_survives_the_round_trip(self):
        run = execute.run_corpus(r"^\d+$", ["12345\n"])
        self.assertEqual(run.hits, (True,), "re treats $ as matching before a trailing newline, "
                                            "and the harness must not hide that")


if __name__ == "__main__":
    unittest.main()
