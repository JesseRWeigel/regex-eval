"""Extraction is part of the instrument, so it is tested in both directions.

Too generous and it credits an answer the model never gave. Too strict and a formatting habit is
scored as a regex error, which would make the eval a test of instruction following wearing the
costume of a test of regex correctness.
"""

import unittest

from rx import extract


class TestExtract(unittest.TestCase):
    def test_plain_line(self):
        found = extract.extract("REGEX: ^cat$")
        self.assertEqual((found.kind, found.pattern), ("regex", "^cat$"))

    def test_fenced_and_backticked(self):
        found = extract.extract("Sure.\n```\nREGEX: `^\\d{5}$`\n```\n")
        self.assertEqual(found.pattern, "^\\d{5}$")

    def test_bold_marker_from_a_chatty_model(self):
        found = extract.extract("**REGEX:** ^[a-z]+$")
        self.assertEqual(found.pattern, "^[a-z]+$")

    def test_quotes_are_only_stripped_when_the_rest_still_compiles(self):
        # The pattern for the quoted-string task begins and ends with a quote character on
        # purpose. Stripping unconditionally would silently corrupt it.
        found = extract.extract('REGEX: "[^"]*"')
        self.assertEqual(found.pattern, '"[^"]*"')

    def test_a_wrapper_is_removed_when_the_inside_is_a_valid_pattern(self):
        found = extract.extract('REGEX: "^abc$"')
        self.assertEqual(found.pattern, "^abc$")

    def test_the_last_regex_line_wins(self):
        found = extract.extract("REGEX: ^a$\nOn reflection:\nREGEX: ^b$")
        self.assertEqual(found.pattern, "^b$")

    def test_refusal(self):
        found = extract.extract("IMPOSSIBLE: the two conditions contradict each other")
        self.assertEqual(found.kind, "refusal")
        self.assertIn("contradict", found.reason)

    def test_a_regex_beats_a_refusal_when_both_appear(self):
        found = extract.extract("IMPOSSIBLE: hmm\nREGEX: ^a$")
        self.assertEqual((found.kind, found.pattern), ("regex", "^a$"))

    def test_no_marker_at_all(self):
        for text in ("here you go: ^cat$", "", "I cannot help with that."):
            self.assertEqual(extract.extract(text).kind, "none")

    def test_empty_pattern_after_the_marker_is_not_an_answer(self):
        self.assertEqual(extract.extract("REGEX:   ").kind, "none")

    def test_unwrap_never_returns_something_that_does_not_compile(self):
        for text in ("`(`", '"("', "((", "`^a$`"):
            candidate = extract.unwrap(text)
            self.assertTrue(candidate)
            if candidate != text.strip():
                self.assertTrue(extract.compiles(candidate))


if __name__ == "__main__":
    unittest.main()
