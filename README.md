# regex-eval

Grade model-written regular expressions by running them over a corpus of labelled strings that the
model never sees.

Catalog task: `EVAL-019`. One of a public catalog of build ideas:
https://github.com/JesseRWeigel/722-things-to-build

## Finding

PLACEHOLDER_FINDING

## What this is

Twelve tasks. Each one is a requirement in prose plus a corpus of strings labelled match or
no-match. The corpus is held back from the prompt. A model is asked for one regex, and grading is
running that regex over the corpus with `re.search`. There is no judge model and no comparison
against a reference pattern, so the ground truth is executable and the score is a fact about the
regex rather than an opinion about it.

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
statistic is recomputed from them, so the finding can be re-checked on a laptop.

## Status

PLACEHOLDER_STATUS

## Unfinished

PLACEHOLDER_UNFINISHED
