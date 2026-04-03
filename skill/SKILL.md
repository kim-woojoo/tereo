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
- if a new failure makes the current win false, it belongs to this loop
- only move a new problem to the next promise when it does not make the current receipt false
- treat crashes and drift as data
- if the same failure repeats, change tactic
- `hold` means not yet proven, not failed

Return:
- the promise
- the check
- the outcome
- the receipt
- the next move
