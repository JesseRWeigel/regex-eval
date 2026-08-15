"""Pull the candidate regex, or a refusal, out of a model response.

The prompt asks for one line beginning REGEX: or one line beginning IMPOSSIBLE:. Models decorate
anyway, so this strips one layer of backticks and one layer of surrounding quotes, and only when
stripping leaves something that still compiles. Stripping unconditionally would corrupt a pattern
that legitimately begins and ends with a quote character, which one of the tasks here invites.

Extraction is part of the instrument. If it is too generous it credits an answer the model did not
give, and if it is too strict it scores a formatting habit as a regex error, so both directions are
tested in tests/test_extract.py and re-derived by a separate reader in scripts/check_independent.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The trailing (?:\*\*[ \t]*)? catches `**REGEX:** ^a$`, where the bold run closes after the
# colon. A pattern cannot begin with `**` anyway, since that is not a valid quantifier.
REGEX_LINE = re.compile(r"^[ \t>*_-]*(?:\*\*)?REGEX(?:\*\*)?[ \t]*:[ \t]*(?:\*\*[ \t]*)?(.*)$",
                        re.MULTILINE)
IMPOSSIBLE_LINE = re.compile(
    r"^[ \t>*_-]*(?:\*\*)?IMPOSSIBLE(?:\*\*)?[ \t]*:[ \t]*(?:\*\*[ \t]*)?(.*)$", re.MULTILINE)

WRAPPERS = (("`", "`"), ('"', '"'), ("'", "'"), ("r'", "'"), ('r"', '"'), ("/", "/"),
            ("**", "**"))


def compiles(pattern: str) -> bool:
    try:
        re.compile(pattern)
    except (re.error, RecursionError, OverflowError, ValueError):
        return False
    return True


def unwrap(text: str) -> str:
    """Remove decorative wrappers, conservatively.

    A wrapper comes off only when what is left still compiles AND the closing character does not
    also occur inside. That second condition is what protects the quoted-string task, where
    `"[^"]*"` is a pattern about quotes rather than a quoted pattern. Removing the outer quotes
    there would leave `[^"]*`, a different and silently wrong regex, and the model would be graded
    on a pattern it never wrote.
    """
    stripped = text.strip()
    for _ in range(3):
        for opener, closer in WRAPPERS:
            if (len(stripped) > len(opener) + len(closer)
                    and stripped.startswith(opener) and stripped.endswith(closer)):
                inner = stripped[len(opener):-len(closer)].strip()
                if inner and closer[-1] in inner:
                    continue
                if inner and compiles(inner):
                    stripped = inner
                    break
        else:
            break
    return stripped


@dataclass(frozen=True)
class Extraction:
    kind: str          # "regex", "refusal", "none"
    pattern: str | None
    reason: str | None


def extract(response: str) -> Extraction:
    if response is None:
        return Extraction("none", None, None)
    body = strip_code_fences(response)
    regex_hits = REGEX_LINE.findall(body)
    refusal_hits = IMPOSSIBLE_LINE.findall(body)
    # A model that says both has answered, so the regex wins and the corpus decides.
    for raw in reversed(regex_hits):
        candidate = unwrap(raw)
        if candidate:
            return Extraction("regex", candidate, None)
    if refusal_hits:
        return Extraction("refusal", None, refusal_hits[-1].strip() or "(no reason given)")
    return Extraction("none", None, None)


def strip_code_fences(text: str) -> str:
    """Drop the ``` lines themselves, keeping their contents, so a fenced REGEX: line is seen."""
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("```"))
