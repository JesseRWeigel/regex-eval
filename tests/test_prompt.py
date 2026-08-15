"""The prompt states the grading contract, so its contents are part of the experiment.

If the prompt stopped saying that re.search is used, every unanchored answer would become a
misunderstanding rather than an error, and the anchor column of the results would mean nothing.
The recorded runs keep their own copy of the prompt, so these checks also compare the template
against what was actually sent.
"""

import glob
import json
import os
import unittest

from rx import prompt, tasks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestPrompt(unittest.TestCase):
    def test_the_search_semantics_are_stated(self):
        text = prompt.build(tasks.load()[0])
        self.assertIn("re.search", text)
        self.assertIn("anchor the pattern yourself", text)
        self.assertIn("not\n  re.fullmatch", text.replace("re.fullmatch,", "re.fullmatch"))

    def test_refusing_is_offered_as_an_answer(self):
        text = prompt.build(tasks.load()[0])
        self.assertIn("IMPOSSIBLE:", text)
        self.assertIn("REGEX:", text)

    def test_the_requirement_is_included_verbatim(self):
        for task in tasks.load():
            self.assertIn(task.requirement, prompt.build(task))

    def test_the_prompt_never_leaks_a_corpus_case(self):
        for task in tasks.load():
            text = prompt.build(task)
            for case in task.cases:
                if len(case.s) >= 4 and case.s.lower() not in task.requirement.lower():
                    self.assertNotIn(case.s, text,
                                     f"{task.id}: the corpus case {case.s!r} is visible in the "
                                     f"prompt, so it is not held out")

    def test_the_recorded_runs_used_this_prompt(self):
        paths = sorted(glob.glob(os.path.join(ROOT, "results", "run-*.jsonl")))
        self.assertTrue(paths, "no recorded run to check the prompt against")
        index = tasks.by_id(tasks.load())
        checked = 0
        for path in paths:
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    self.assertEqual(record["prompt"], prompt.build(index[record["task"]]),
                                     f"{os.path.basename(path)}: a recorded prompt differs from "
                                     f"the template, so the run and the analysis disagree about "
                                     f"what was asked")
                    checked += 1
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
