"""Grade one response by running its regex, never by comparing it to a reference pattern.

Outcomes, deliberately not collapsed into pass and fail:

  pass       every case in the held-out corpus came out right
  fail       the regex ran and got at least one case wrong
  invalid    the regex did not compile
  timeout    the guard killed it, which is a distinct engineering failure from being wrong
  refused    the model said the requirement is impossible
  no_answer  neither a REGEX: line nor an IMPOSSIBLE: line came back

For a normal task, correct means pass. For the impossible control, correct means refused, and a
harness that cannot tell those two apart is not measuring anything.
"""

from __future__ import annotations

from rx import execute, extract

OUTCOMES = ("pass", "fail", "invalid", "timeout", "crash", "refused", "no_answer")


def grade(task, response: str, timeout: float = execute.DEFAULT_TIMEOUT) -> dict:
    found = extract.extract(response)
    result = {
        "task": task.id,
        "kind": task.kind,
        "pattern": found.pattern,
        "outcome": None,
        "correct": False,
        "naive_subset_pass": False,
        "wrong_cases": [],
        "detail": "",
    }
    if found.kind == "none":
        result["outcome"] = "no_answer"
        return result
    if found.kind == "refusal":
        result["outcome"] = "refused"
        result["correct"] = task.kind == "control_impossible"
        result["detail"] = found.reason or ""
        return result

    run = execute.run_corpus(found.pattern, task.strings, timeout=timeout)
    if run.status != "ok":
        result["outcome"] = run.status
        result["detail"] = run.detail
        result["reached"] = run.reached
        return result

    wrong = []
    naive_wrong = 0
    for case, hit in zip(task.cases, run.hits):
        if hit != case.match:
            wrong.append({"s": case.s, "expected": case.match, "got": hit, "trap": case.trap,
                          "naive": case.naive})
            if case.naive:
                naive_wrong += 1
    result["wrong_cases"] = wrong
    result["naive_subset_pass"] = naive_wrong == 0
    result["outcome"] = "pass" if not wrong else "fail"
    result["correct"] = task.kind != "control_impossible" and not wrong
    return result


def case_level(task, graded: dict) -> list:
    """One row per corpus case for a runnable regex, used for the failure-by-trap breakdown."""
    if graded["outcome"] not in ("pass", "fail"):
        return []
    wrong = {(entry["s"], entry["trap"]) for entry in graded["wrong_cases"]}
    return [
        {"task": task.id, "trap": case.trap, "naive": case.naive,
         "wrong": (case.s, case.trap) in wrong}
        for case in task.cases
    ]
