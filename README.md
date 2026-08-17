# regex-eval

Grade model-written regular expressions by running them over a corpus of labelled strings that the
model never sees.

Catalog task: `EVAL-019`. One of a public catalog of build ideas:
https://github.com/JesseRWeigel/722-things-to-build

## Finding

**33 of 82 regexes that were right on the obvious cases were wrong on the held-out ones, 40.2%
(95% CI 30.3 to 51.1).** Three small local models, 12 tasks, 3 samples each, 108 responses in all.

Being right on the obvious cases is close to no evidence at all. The 40.2% is the rate at which a
pattern that handles every example a person would think to try still fails on a case chosen to
probe one specific mistake. Per arm, on the same tasks:

| arm | correct on every case | right on the obvious, wrong on the held-out |
|---|---|---|
| gpt-oss:20b | 28 / 33 (85%) | 4 / 32 (13%) |
| gemma4:e4b | 16 / 33 (48%) | 13 / 29 (45%) |
| qwen3.5:9b | 5 / 33 (15%) | 16 / 21 (76%) |

Two other results from the same run:

- **No model ever refused the contradictory task.** The `contradiction` control states a
  requirement whose corpus labels one string both match and no-match, so the correct answer is to
  say it cannot be done. All three arms answered with a regex all nine times, 0 of 9 refusals. The
  easy control went 9 of 9, so the arms were not simply failing at everything.
- **The mistakes cluster.** Over regexes that compiled and ran, the error rate by held-out case
  type was 26% on leading zeros, 11% on greedy quantifiers, 8% on the per-requirement boundary
  case, 6.5% on negation, 5% on character-class boundaries and 2.6% on anchoring. Two case types
  are arguably a Python detail rather than a regex error, `\d` matching non-ASCII digits (78%
  wrong) and `$` matching before a trailing newline (89% wrong); they are broken out separately so
  they can be discounted.

## What this is

Twelve tasks. Each one is a requirement in prose plus a corpus of strings labelled match or
no-match, 168 cases in total. 47 of those cases are marked naive in advance, meaning the obvious
examples a person would try first; the other 121 are held back. The whole corpus is held back from
the prompt. A model is asked for one regex, and grading is running that regex over the corpus with
`re.search`. There is no judge model and no comparison against a reference pattern, so the ground
truth is executable and the score is a fact about the regex rather than an opinion about it.

Two of the twelve are controls. `literal` is trivial and every model should pass it, and
`contradiction` states a requirement whose corpus labels one string both match and no-match, so no
regex can score full marks and the correct answer is to say so. A harness that cannot tell those
apart is not measuring anything.

Every corpus case carries a tag for the kind of mistake it exists to catch: anchoring, greedy
quantifiers, character classes that admit one character too many, leading zeros, negation, and a
boundary case for each requirement. Each task also carries a hand written reference pattern and a
deliberately naive one, used only by the unit suite to prove the labels are consistent and that the
held-out cases actually have teeth.

Every candidate regex runs in a child process under a wall clock guard, because catastrophic
backtracking is one of the things a model can hand you. A timeout is its own outcome and is never
counted as a wrong answer.

## The reasoning channel

Every arm here was run with `think: false` sent explicitly in the request body, and the flag is
recorded in every record. Ollama leaves the hidden reasoning channel on by default and strips it
from the response body, so an arm that only asks the model in the prompt not to reason silently
measures a reasoning model.

There is no `think: true` arm because the answers do not arrive. `scripts/probe_think_budget.py`
asked qwen3.5:9b for four of these tasks with `think: true` and `num_predict` 4096. **4 of 4 calls
spent the entire token budget in the hidden channel and returned an empty response body**, 12885 to
15861 characters of reasoning each, `done_reason` `length`. The transcript is committed at
`fixtures/think-budget-probe.jsonl` and `scripts/verify.sh` checks this paragraph against it.

One arm did not honour the flag. `gpt-oss:20b` returned reasoning text on all 36 calls despite
`think: false`, between 313 and 4922 characters. `gemma4:e4b` and `qwen3.5:9b` returned none on any
call. So the gpt-oss column is a reasoning arm in a table of non-reasoning ones, which is the most
likely reason it leads, and its 85% should not be compared to the other two as though the three
were run under one condition.

The other Ollama trap this run had to route around: only `options.num_ctx` in the request body
changes the loaded context length. Setting it in the REPL with `/set parameter num_ctx` or through
`OLLAMA_CONTEXT_LENGTH` leaves the server default in place and reports no error.

## Running it

```bash
bash scripts/verify.sh          # the whole check, no model and no network needed
python3 scripts/measure.py      # recompute every number from the raw records
```

Reproducing the run itself needs a local Ollama:

```bash
python3 scripts/run_eval.py --model qwen3.5:9b --samples 3 --think false --num-predict 1024
```

`verify.sh` never contacts a model. The raw responses are committed under `results/`, and every
statistic is recomputed from them, so the finding can be re-checked on a laptop. It takes about
nine minutes, almost all of it in the sabotage suite, which builds 25 broken copies of the tree and
requires the tests to fail on each one.

## Status

```
== 1. python, standard library only
   python 3.12.3, standard library only, no model required
   PASS

== 2. the recorded run is present and complete
   3 arms, 108 recorded responses: run-gemma4-e4b-thinkfalse.jsonl 36, run-gpt-oss-20b-thinkfalse.jsonl 36, run-qwen3.5-9b-thinkfalse.jsonl 36
   PASS

== 3. the reasoning-budget probe backs the claim made about it in the README
   4 of 4 probe calls spent the whole token budget reasoning and returned an empty answer, and the README says so
   PASS

== 4. unit tests, including the corpus labels and the timeout guard
Ran 72 tests in 20.430s

OK
   PASS

== 5. the test count claimed in the README is still the count that exists
   72 tests, and the README says so
   PASS

== 6. the measurement is deterministic
   FINGERPRINT c411b86b52566b24488092fa818b3c607a77d28d67d11a75784a9c7a9a0ae640
   PASS

== 7. the committed summary is not stale against the raw records
   summary.json reproduces exactly from 108 raw responses
   PASS

== 8. the headline number in the README is the one in the data
   the README states 33 of 82 and 108 responses, matching the data
   PASS

== 9. sabotage suite, three gates and a null control
  caught                  a probe is graded against the wrong task
  caught (dormant guard)  the prompt stops saying the pattern is run with re.search

25 of 25 sabotages applied, moved the measurement as expected, and were caught
   PASS

== 10. independent recount, importing nothing from rx and re-running every regex another way
  rejected as required: probe_relative.py
  the second scanner agrees with 8 hand written expectations
  the second guard, an os.fork with a deadline, fired on (a+)+$
  32 corpus labels re-derived without a regex and they agree
  naive_pass_full_fail   summary    33  recount    33  agrees
  naive_subset_pass      summary    82  recount    82  agrees
  refused_impossible     summary     0  recount     0  agrees
  solvable_n             summary    99  recount    99  agrees
  solvable_pass          summary    49  recount    49  agrees
  outcomes by the second route: fail 59, pass 49

independent recount agrees with the committed summary
   PASS

== 11. privacy scan with planted control credentials
   41 tracked files, 308449 bytes read, no findings; 6 planted controls all caught and a clean control stayed clean
   PASS

== 12. the published page is not stale against the data
   docs/index.html matches a fresh build from 108 records
   PASS

== 13. the page carries numbers the build script must have produced
   the page carries every arm score, all 12 case type counts, a title and the threats section
   PASS

== 14. the README is finished and its status matches this script
   README has a Finding, a Status transcript and an Unfinished section, no scaffold text
   PASS

== 15. verify did not modify the tree it was verifying
   41 tracked files unchanged
   PASS

VERIFY PASSED: regex-eval, 15 of 15 steps
```

## Unfinished

- **No reasoning arm.** The probe above shows why the obvious way of getting one does not work with
  a 9B model and a 4096-token budget. A real reasoning arm needs a much larger `num_predict`, and
  then it is measuring a different amount of compute rather than a different setting.
- **`gpt-oss:20b` ignores `think: false`**, so one of the three arms is not under the condition its
  label claims. Ollama exposes reasoning effort levels for that model rather than an off switch.
  Nothing here has been rerun with `"think": "low"` to see how far the gap closes.
- **Three small local models at one temperature.** 0.7, three samples per task per arm. That is
  enough to show a rate and not enough to separate arms that sit close together. Nothing here says
  anything about frontier models.
- **The corpora are written by one person** and encode one reading of each requirement, so a
  defensible disagreement about the requirement scores as a model error.
- **No per-case difficulty model.** The held-out cases are grouped by the mistake they target, and
  the counts per group are small enough that the ordering between the middle groups is not
  meaningful.

## Layout

```
rx/            tasks, prompt, extraction, guarded execution, grading, statistics
data/          tasks.json, the corpora and their labels; harness_probe.json, synthetic responses
results/       raw model responses as JSONL, plus the recomputed summary.json
scripts/       run_eval, measure, build_docs, sabotage, check_independent, privacy_scan, verify
tests/         the unit suite
docs/          the published page, generated from the data and checked for staleness
fixtures/      the reasoning-budget probe transcript
```

Measurements on the development machine: RTX 5090 (32 GB VRAM), 12 cores, 48 GB RAM, Linux under
WSL2, Ollama serving all three models locally.

## License

MIT.
