"""The single prompt template. It states the grading contract, so a failure is the model's.

Two things are said out loud because leaving them implicit would turn the eval into a guessing
game about house style rather than a measurement of regex correctness. First, the pattern is run
with `re.search` and no flags, so anchoring is the model's job and an unanchored answer is a real
error and not a misunderstanding. Second, refusing is an available and expected answer, so the
impossible control measures judgement rather than obedience.
"""

from __future__ import annotations

TEMPLATE = """Write one regular expression for Python's `re` module.

Requirement:
{requirement}

How your answer will be judged:
- Your pattern is compiled with re.compile(pattern) and then tested with re.search(pattern, s)
  against a set of strings you cannot see. No flags are applied. Because re.search is used and not
  re.fullmatch, anchor the pattern yourself if the requirement is about the whole string.
- Reply with exactly one line: REGEX: followed by the pattern itself, with no quotes, no backticks,
  and no explanation.
- If no regular expression can satisfy the requirement as stated, reply with exactly one line:
  IMPOSSIBLE: followed by a one sentence reason.
"""


def build(task) -> str:
    return TEMPLATE.format(requirement=task.requirement)
