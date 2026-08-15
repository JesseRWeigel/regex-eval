#!/usr/bin/env bash
# The verify command. Its exit code is the result.
#
# Nothing here needs Ollama, a GPU or a network. The eval's raw responses are committed under
# results/, and every statistic is recomputed from them, so anyone can re-check the finding on a
# laptop. An eval whose verification needs the model back is an eval nobody will ever re-check.
#
# A step that cannot run is a FAILURE and not a skip, because in a log a week later a skipped
# check and a passing check look the same.
#
# The tree is digested before and after. A verify that edits the repository can pass on a later
# run for reasons an earlier run created, and that is indistinguishable from working.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

STEP=0
FAILED=0

step() {
  STEP=$((STEP + 1))
  printf '\n== %d. %s\n' "$STEP" "$1"
}

check() {
  if [ "$1" -eq 0 ]; then
    printf '   PASS\n'
  else
    printf '   FAIL (exit %d)\n' "$1"
    FAILED=$((FAILED + 1))
  fi
}

step "python, standard library only"
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  printf '   FAIL no python3 on PATH. Install python 3.10 or newer; every check below needs it.\n'
  exit 1
fi
"$PY" - <<'EOF'
import sys
if sys.version_info < (3, 10):
    print(f"   FAIL python {sys.version.split()[0]}, this needs 3.10 or newer for the type syntax")
    raise SystemExit(1)
print(f"   python {sys.version.split()[0]}, standard library only, no model required")
EOF
check $?
if [ "$FAILED" -ne 0 ]; then
  printf '\nVERIFY FAILED: the interpreter is unusable, so nothing below could be run honestly.\n'
  exit 1
fi

export PYTHONPATH="$ROOT"
export PYTHONDONTWRITEBYTECODE=1

digest() {
  "$PY" - <<'EOF'
import hashlib, os, subprocess
out = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
digest = hashlib.sha256()
for name in sorted(out.stdout.split()):
    if os.path.exists(name):
        with open(name, "rb") as handle:
            digest.update(name.encode())
            digest.update(handle.read())
print(digest.hexdigest())
EOF
}

BEFORE="$(digest)"

step "the recorded run is present and complete"
"$PY" - <<'EOF'
import glob, json, os, sys
sys.path.insert(0, ".")
from rx import tasks

expected = {task.id for task in tasks.load()}
paths = sorted(glob.glob(os.path.join("results", "run-*.jsonl")))
if not paths:
    print("   FAIL no recorded run under results/. The raw responses are the deliverable.")
    sys.exit(1)
total = 0
notes = []
for path in paths:
    with open(path, encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    if len({(r["model"], r["think"]) for r in records}) != 1:
        print(f"   FAIL {path} mixes arms")
        sys.exit(1)
    keys = {(r["sample"], r["task"]) for r in records}
    if len(keys) != len(records):
        print(f"   FAIL {path} has {len(records) - len(keys)} duplicated cell(s)")
        sys.exit(1)
    if {r["task"] for r in records} != expected:
        print(f"   FAIL {path} does not cover every task exactly once per sample")
        sys.exit(1)
    for record in records:
        for field in ("model", "think", "sample", "seed", "temperature", "num_ctx",
                      "num_predict", "task", "prompt", "response", "thinking_chars",
                      "done_reason", "eval_count"):
            if field not in record:
                print(f"   FAIL a record in {path} has no {field!r}")
                sys.exit(1)
    total += len(records)
    notes.append(f"{os.path.basename(path)} {len(records)}")
print(f"   {len(paths)} arms, {total} recorded responses: {', '.join(notes)}")
EOF
check $?

step "the reasoning-budget probe backs the claim made about it in the README"
"$PY" - <<'EOF'
import json, os, sys
path = os.path.join("fixtures", "think-budget-probe.jsonl")
if not os.path.exists(path):
    print(f"   FAIL {path} is missing, so the README's claim about the reasoning channel has "
          f"no evidence behind it")
    sys.exit(1)
with open(path, encoding="utf-8") as handle:
    records = [json.loads(line) for line in handle if line.strip()]
if len(records) < 3:
    print(f"   FAIL only {len(records)} probe record(s)")
    sys.exit(1)
if not all(record["think"] for record in records):
    print("   FAIL the probe is supposed to have the reasoning channel ON")
    sys.exit(1)
truncated = [r for r in records if r["done_reason"] == "length" and not r["response"].strip()]
readme = open("README.md", encoding="utf-8").read()
claim = f"{len(truncated)} of {len(records)}"
if claim not in readme:
    print(f"   FAIL the README does not state the probe result {claim!r}")
    sys.exit(1)
print(f"   {len(truncated)} of {len(records)} probe calls spent the whole token budget reasoning "
      f"and returned an empty answer, and the README says so")
EOF
check $?

step "unit tests, including the corpus labels and the timeout guard"
"$PY" -m unittest discover -s tests 2>&1 | tail -3
check "${PIPESTATUS[0]}"

step "the test count claimed in the README is still the count that exists"
"$PY" - <<'EOF'
import re, subprocess, sys
out = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                     capture_output=True, text=True)
ran = int(re.search(r"^Ran (\d+) tests", out.stderr, re.M).group(1))
readme = open("README.md", encoding="utf-8").read()
claimed = [int(n) for n in re.findall(r"Ran (\d+) tests", readme)]
if not claimed:
    print("   FAIL the README pastes no test count, so it cannot be checked")
    sys.exit(1)
if any(n != ran for n in claimed):
    print(f"   FAIL the README claims {claimed} tests, the suite has {ran}")
    sys.exit(1)
print(f"   {ran} tests, and the README says so")
EOF
check $?

step "the measurement is deterministic"
A="$("$PY" scripts/measure.py --quiet | grep '^FINGERPRINT')"
B="$("$PY" scripts/measure.py --quiet | grep '^FINGERPRINT')"
if [ -n "$A" ] && [ "$A" = "$B" ]; then
  printf '   %s\n' "$A"
  check 0
else
  printf '   two runs disagreed:\n     %s\n     %s\n' "$A" "$B"
  check 1
fi

step "the committed summary is not stale against the raw records"
"$PY" - <<'EOF'
import json, subprocess, sys
sys.path.insert(0, "scripts")
sys.path.insert(0, ".")
import measure
from rx import tasks
task_list = tasks.load()
rows = measure.grade_all(measure.load_records(), task_list)
fresh = measure.build_summary(rows, task_list)
with open("results/summary.json", encoding="utf-8") as handle:
    committed = json.load(handle)
if json.dumps(fresh, sort_keys=True) != json.dumps(committed, sort_keys=True):
    print("   FAIL results/summary.json does not match a fresh recomputation. "
          "Run: python3 scripts/measure.py --write")
    sys.exit(1)
print(f"   summary.json reproduces exactly from {fresh['meta']['responses']} raw responses")
EOF
check $?

step "the headline number in the README is the one in the data"
"$PY" - <<'EOF'
import json, re, sys
summary = json.load(open("results/summary.json", encoding="utf-8"))
overall = summary["overall"]
readme = open("README.md", encoding="utf-8").read()
needle = (f"{overall['naive_pass_full_fail']} of {overall['naive_subset_pass']}")
if needle not in readme:
    print(f"   FAIL the README does not state the headline count {needle!r}")
    sys.exit(1)
responses = summary["meta"]["responses"]
if f"{responses} responses" not in readme:
    print(f"   FAIL the README does not state the sample size, {responses} responses")
    sys.exit(1)
print(f"   the README states {needle} and {responses} responses, matching the data")
EOF
check $?

step "sabotage suite, three gates and a null control"
"$PY" scripts/sabotage.py 2>&1 | tail -4
check "${PIPESTATUS[0]}"

step "independent recount, importing nothing from rx and re-running every regex another way"
"$PY" scripts/check_independent.py 2>&1 | tail -12
check "${PIPESTATUS[0]}"

step "privacy scan with planted control credentials"
"$PY" scripts/privacy_scan.py
check $?

step "the published page is not stale against the data"
"$PY" scripts/build_docs.py --check
check $?

step "the page carries numbers the build script must have produced"
"$PY" - <<'EOF'
import json, re, sys
page = open("docs/index.html", encoding="utf-8").read()
summary = json.load(open("results/summary.json", encoding="utf-8"))
problems = []
if "<title>" not in page:
    problems.append("the page has no title")
for name, arm in summary["arms"].items():
    if name not in page:
        problems.append(f"the page never names the arm {name}")
    if f"{arm['solvable_pass']} / {arm['solvable_n']}" not in page:
        problems.append(f"the page does not show the score for {name}")
for name, bucket in summary["traps"].items():
    if f"{bucket['wrong']} / {bucket['cases']}" not in page:
        problems.append(f"the page does not show the {name} case count")
if re.search(r"overflow-x:\s*hidden", page):
    problems.append("the page hides overflow instead of letting a wide table scroll")
for phrase in ("Threats to validity", "held back from the"):
    if phrase not in page:
        problems.append(f"the page does not say {phrase!r}")
if problems:
    for message in problems:
        print(f"   FAIL {message}")
    sys.exit(1)
print(f"   the page carries every arm score, all {len(summary['traps'])} case type counts, "
      f"a title and the threats section")
EOF
check $?

step "the README is finished and its status matches this script"
"$PY" - <<'EOF'
import re, sys
raw = open("README.md", encoding="utf-8").read()
# The Status section holds this script's own transcript, which contains every marker a scaffold
# check looks for. Fenced blocks are stripped before the search, never excluded from it.
prose = re.sub(r"```.*?```", "", raw, flags=re.S)
problems = []
for marker in ("TODO", "FIXME", "NOT YET VERIFIED", "replace with a real description"):
    if marker in prose:
        problems.append(f"the README prose still contains {marker!r}")
for heading in ("## Finding", "## Status", "## Unfinished"):
    if heading not in raw:
        problems.append(f"the README has no {heading} section")
status = raw.split("## Status", 1)[-1]
if "VERIFY PASSED" not in status:
    problems.append("the Status section carries no passing transcript of this script")
if "regex-eval" not in status:
    problems.append("the Status transcript is not this project's")
if problems:
    for message in problems:
        print(f"   FAIL {message}")
    sys.exit(1)
print("   README has a Finding, a Status transcript and an Unfinished section, no scaffold text")
EOF
check $?

step "verify did not modify the tree it was verifying"
AFTER="$(digest)"
if [ "$BEFORE" = "$AFTER" ]; then
  printf '   %s tracked files unchanged\n' "$(git ls-files | wc -l)"
  check 0
else
  printf '   the tree changed during verification\n     before %s\n     after  %s\n' \
    "$BEFORE" "$AFTER"
  check 1
fi

printf '\n'
if [ "$FAILED" -eq 0 ]; then
  printf 'VERIFY PASSED: regex-eval, %d of %d steps\n' "$STEP" "$STEP"
  exit 0
fi
printf 'VERIFY FAILED: regex-eval, %d of %d steps failed\n' "$FAILED" "$STEP"
exit 1
