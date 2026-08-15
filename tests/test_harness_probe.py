"""The synthetic probe vector, whose correct outcome is known by construction.

Real models are tidier than the extractor has to be. Not one recorded response fenced its answer,
wrapped it in quotes, refused, or failed to compile, so these branches are exercised here and
nowhere else. Each probe states its expected outcome in data/harness_probe.json and this asserts it.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "scripts"))

import measure  # noqa: E402

from rx import tasks  # noqa: E402


class TestHarnessProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = tasks.load()
        cls.rows = measure.grade_probes(cls.tasks)

    def test_every_probe_grades_as_expected(self):
        for row in self.rows:
            with self.subTest(probe=row["id"]):
                self.assertEqual(row["outcome"], row["expect"],
                                 f"{row['id']}: pattern taken as {row['pattern']!r}")

    def test_the_probe_vector_covers_the_branches_real_models_did_not(self):
        with open(measure.PROBE_PATH, encoding="utf-8") as handle:
            probes = json.load(handle)["probes"]
        outcomes = {probe["expect"] for probe in probes}
        for wanted in ("pass", "fail", "refused", "invalid", "no_answer"):
            self.assertIn(wanted, outcomes, f"no probe expects {wanted}")
        self.assertGreaterEqual(len(probes), 10)

    def test_the_quoted_pattern_probe_keeps_its_outer_quotes(self):
        row = [entry for entry in self.rows if entry["id"] == "pattern-about-quotes"][0]
        self.assertEqual(row["pattern"], '"[^"]*"',
                         "stripping the wrapper here would grade a pattern the model never wrote")

    def test_probes_are_absent_from_the_reported_statistics(self):
        summary = measure.build_summary(measure.grade_all(measure.load_records(), self.tasks),
                                        self.tasks)
        self.assertEqual(summary["meta"]["responses"] % len(self.tasks), 0,
                         "the response count should be whole samples of the task set, which it "
                         "would not be if probes leaked into it")
        self.assertNotIn("probe", json.dumps(summary))

    def test_probes_are_inside_the_fingerprint(self):
        rows = measure.grade_all(measure.load_records(), self.tasks)
        summary = measure.build_summary(rows, self.tasks)
        with_probes = measure.fingerprint(summary, rows, self.rows)
        moved = [dict(row) for row in self.rows]
        moved[0]["outcome"] = "fail"
        self.assertNotEqual(with_probes, measure.fingerprint(summary, rows, moved))


if __name__ == "__main__":
    unittest.main()
