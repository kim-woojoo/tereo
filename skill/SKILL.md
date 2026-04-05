---
name: tereo
description: Use TEREO when one repeatable check can judge one small change, especially to verify AI-made patches with promise-check-receipt, reject false gains, and keep only what proves itself.
---

# TEREO Rulebook

Use this rulebook when one repeatable check can judge one small change.

`AI writes. TEREO proves.`

`keep only if gain > noise`

`Doubt first. Keep later.`

## Public Shape

- `promise`
- `check`
- `receipt`

## Public Verbs

- `prove`
- `show`
- `log`

## Runtime

Prefer the installed `tereo` CLI.

If it is missing:

- inside the TEREO repo root, install with `pip install -e .`
- inside a repo that vendors TEREO, install with `pip install -e ./tereo`
- otherwise say that the TEREO runtime is not available yet

Do not fake a TEREO receipt without running the real CLI.

## Lane Law

- same agent or thread, same proof lane
- different agents or threads, different lanes
- let TEREO choose the lane automatically
- only set `--proof` when you intentionally want to share or inspect a lane

## Loop

1. write one small promise
2. freeze one fixed check that sees both the gain and the core you must not break
3. run `tereo prove`
4. make one small change
5. run `tereo prove` again
6. read the receipt
7. keep only what proves itself

## Freeze

- `promise`
- `scope`
- `check`
- `proof rule`
- `stop condition`

If you need a reminder for writing a promise, read [promise-template.md](promise-template.md).

## Agent Mode

- in normal use, do not pass `--proof`
- if multiple agents run in parallel, let each agent keep its own lane
- use `tereo show` and `tereo log` from the same agent or thread that ran the proof
- only share a lane on purpose when agents are continuing the exact same proof
- if you need to inspect another lane, pass `--proof` explicitly for that read

## Good Check

A good `check` does two things at once:

- shows the gain you want
- catches the core breakage that would make that gain false

If a patch hits the promise but breaks the core, that is a false gain, not a `keep`.

## Metric Law

- for metric proofs, prefer one explicit line: `TEREO_METRIC name value direction [unit]`
- if you can shape the check output, make the metric say its own name instead of relying on regex guessing
- if the check already prints a known line like `latency_ms: 12.3`, TEREO can auto-seed that on the first baseline
- if the metric is custom and you cannot change the output, pass `--metric-pattern`

## Default Commands

```bash
tereo prove --promise "Current parser behavior is the baseline"
tereo prove --scope src/parser.py --promise "Empty input returns []"
tereo prove --check "./bench.sh" --promise "Current latency is the baseline"
tereo show
tereo log
```

## Use It When

- a bug with a deterministic repro
- a feature with a clear acceptance check
- a refactor guarded by stable tests
- a performance change with an explicit metric

## Do Not Use It For

- broad product design
- open-ended invention
- taste-driven visual polish
- work with no stable check

## Rules

- prefer one file or one tight file cluster
- keep one primary hypothesis per run
- do not change the target and the check in the same pass
- do not make two agents push unrelated work through the same proof lane
- if a new failure makes the current win false, it belongs to this loop
- only move a new problem to the next promise when it does not make the current receipt false
- treat crashes and drift as data
- if the same failure repeats, change tactic
- `hold` means not yet proven, not failed
- one main agent owns the decision
- subagents are optional
- keep one writer per overlapping scope
- named metric first, regex second

Return:
- the promise
- the check
- the outcome
- the receipt
- the next move
