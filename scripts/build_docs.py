#!/usr/bin/env python3
"""Generate docs/index.html from the recomputed results, or check that it is not stale.

The page is derived, never hand edited. `--check` rebuilds it in memory and diffs, so a published
page cannot quietly drift away from the data it claims to show.
"""

from __future__ import annotations

import argparse
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import measure  # noqa: E402

from rx import tasks  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "docs", "index.html")

CSS = """
:root {
  color-scheme: light dark;
  --bg: #fbfbfa; --fg: #1a1a1a; --muted: #5c5c5c; --line: #d9d7d2;
  --card: #ffffff; --accent: #8a3324; --good: #1f6f43;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #14161a; --fg: #e9e7e3; --muted: #a3a19c; --line: #2e3238;
    --card: #1b1e23; --accent: #e2825f; --good: #63c48c;
  }
}
:root[data-theme="dark"] {
  --bg: #14161a; --fg: #e9e7e3; --muted: #a3a19c; --line: #2e3238;
  --card: #1b1e23; --accent: #e2825f; --good: #63c48c;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem 1.25rem 4rem; background: var(--bg); color: var(--fg);
  font: 16px/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}
main { max-width: 60rem; margin: 0 auto; }
h1 { font-size: 1.7rem; margin: 0 0 .3rem; letter-spacing: -.01em; }
h2 { font-size: 1.05rem; margin: 2.4rem 0 .7rem; text-transform: uppercase;
     letter-spacing: .08em; color: var(--muted); }
p { margin: .6rem 0; max-width: 46rem; }
.lede { font-size: 1.1rem; }
.big { font-size: 2.6rem; font-weight: 700; color: var(--accent); line-height: 1.1; }
.cards { display: grid; gap: .9rem; grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr)); }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
        padding: 1rem 1.1rem; }
.card .label { color: var(--muted); font-size: .82rem; text-transform: uppercase;
               letter-spacing: .06em; }
.scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px;
          background: var(--card); }
table { border-collapse: collapse; width: 100%; font-size: .92rem; min-width: 34rem; }
th, td { text-align: right; padding: .5rem .7rem; border-bottom: 1px solid var(--line);
         white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
th { color: var(--muted); font-weight: 600; font-size: .8rem; text-transform: uppercase;
     letter-spacing: .05em; }
tr:last-child td { border-bottom: 0; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .9em;
       background: color-mix(in srgb, var(--fg) 8%, transparent); padding: .1em .35em;
       border-radius: 4px; }
.bar { display: inline-block; height: .62rem; background: var(--accent); border-radius: 3px;
       vertical-align: middle; }
footer { margin-top: 3rem; color: var(--muted); font-size: .85rem; }
a { color: var(--accent); }
"""


def bar(fraction: float, width: float = 9.0) -> str:
    return f'<span class="bar" style="width:{max(0.15, fraction * width):.2f}rem"></span>'


def render(summary: dict, task_list: list) -> str:
    overall = summary["overall"]
    low, high = overall["illusion_ci"]
    rows = []
    for name, arm in summary["arms"].items():
        rows.append(
            f"<tr><td>{html.escape(name)}</td>"
            f"<td>{arm['solvable_pass']} / {arm['solvable_n']}</td>"
            f"<td>{100 * arm['solvable_pass_rate']:.0f}%</td>"
            f"<td>{arm['naive_pass_full_fail']} / {arm['naive_subset_pass']}</td>"
            f"<td>{100 * arm['illusion_rate']:.0f}%</td>"
            f"<td>{arm['easy_pass']} / {arm['easy_n']}</td>"
            f"<td>{arm['impossible_refused']} / {arm['impossible_n']}</td>"
            f"<td>{arm['timeouts']}</td><td>{arm['invalid']}</td></tr>")

    traps = []
    for name, bucket in sorted(summary["traps"].items(), key=lambda item: -item[1]["error_rate"]):
        traps.append(
            f"<tr><td>{html.escape(name)}</td><td>{bucket['wrong']} / {bucket['cases']}</td>"
            f"<td>{100 * bucket['error_rate']:.1f}%</td>"
            f"<td>{bar(bucket['error_rate'])}</td></tr>")

    per_task = []
    for name, cell in summary["tasks"].items():
        note = {"control_easy": "easy control", "control_impossible": "impossible control",
                "normal": ""}[cell["kind"]]
        per_task.append(
            f"<tr><td>{html.escape(name)}</td><td>{cell['pass']} / {cell['n']}</td>"
            f"<td>{100 * cell['pass_rate']:.0f}%</td><td>{note}</td></tr>")

    meta = summary["meta"]
    return f"""<title>Regex against executable ground truth</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{CSS}</style>
<main>
<h1>Regex against executable ground truth</h1>
<p class="lede">Models were asked for a regular expression for a stated requirement. Each answer
was graded by <strong>running it</strong> over a corpus of labelled strings held back from the
prompt, with no judge model and no comparison against a reference pattern.</p>

<h2>The headline</h2>
<p class="big">{100 * overall['illusion_rate']:.0f}%</p>
<p>of the regexes that are correct on the obvious cases are wrong on the held-out ones.
That is {overall['naive_pass_full_fail']} of {overall['naive_subset_pass']} responses,
95% CI {100 * low:.0f} to {100 * high:.0f}. Overall
{overall['solvable_pass']} of {overall['solvable_n']} answers to solvable tasks were correct on
every case.</p>

<div class="cards">
  <div class="card"><div class="label">tasks</div><div>{meta['tasks']}, including one easy
    control and one contradictory control</div></div>
  <div class="card"><div class="label">corpus cases</div><div>{meta['corpus_cases']} labelled
    strings, none shown to the model</div></div>
  <div class="card"><div class="label">responses</div><div>{meta['responses']} across
    {meta['arms']} arms of a local Ollama</div></div>
</div>

<h2>By arm</h2>
<div class="scroll"><table>
<tr><th>arm</th><th>solvable correct</th><th></th><th>looked right, was wrong</th><th></th>
<th>easy control</th><th>refused the contradiction</th><th>timeouts</th><th>invalid</th></tr>
{''.join(rows)}
</table></div>

<h2>Where the regexes break</h2>
<p>Every corpus case carries a tag for the kind of mistake it is designed to catch. This is the
error rate per case, over regexes that compiled and ran.</p>
<div class="scroll"><table>
<tr><th>case type</th><th>wrong</th><th>rate</th><th></th></tr>
{''.join(traps)}
</table></div>

<h2>By task</h2>
<div class="scroll"><table>
<tr><th>task</th><th>passed</th><th>rate</th><th></th></tr>
{''.join(per_task)}
</table></div>

<h2>Threats to validity</h2>
<p>The corpora are written by one person and encode one reading of each requirement, so a
disagreement about the requirement scores as a model error. Sampling is three draws per task per
arm at temperature 0.7, which is enough to show a rate and not enough to separate arms that sit
close together. The models are small local ones, so the numbers describe them and not the frontier.
Two tasks carry a trap that is arguably a Python detail rather than a regex error, <code>\\d</code>
matching non-ASCII digits and <code>$</code> matching before a trailing newline, and the case type
table breaks those out so they can be discounted.</p>

<footer>Generated by <code>scripts/build_docs.py</code> from the raw run records. Task EVAL-019 of
a public catalog of build ideas.</footer>
</main>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    task_list = tasks.load()
    records = measure.load_records()
    if not records:
        print("   FAIL no records to build a page from")
        return 1
    rows = measure.grade_all(records, task_list)
    summary = measure.build_summary(rows, task_list)
    page = render(summary, task_list)

    if args.check:
        if not os.path.exists(PAGE):
            print("   FAIL docs/index.html does not exist. Run scripts/build_docs.py.")
            return 1
        with open(PAGE, encoding="utf-8") as handle:
            existing = handle.read()
        if existing != page:
            print("   FAIL docs/index.html is stale against the data. Rebuild it.")
            return 1
        print(f"   docs/index.html matches a fresh build from {len(records)} records")
        return 0

    os.makedirs(os.path.dirname(PAGE), exist_ok=True)
    with open(PAGE, "w", encoding="utf-8") as handle:
        handle.write(page)
    print(f"wrote {os.path.relpath(PAGE, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
