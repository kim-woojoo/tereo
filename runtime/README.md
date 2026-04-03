# TEREO Runtime

`tereo` is the runtime and CLI behind TEREO.
It turns a promise into a receipt.
It is designed to reveal the truth of a change, not just the first good-looking run.

Its law is:

Gain has to beat measured noise.

Its instinct is:

`Doubt first. Keep later.`

It does not ask you to adopt one special test runner or benchmark.
You bring the check command. The runtime wraps it in a small proof workflow.
A check can be a test suite, a smoke script, a CLI expectation, or a latency run.
A good check shows the local gain you want and catches the core breakage that would make that gain false.

## Public Model

- `promise`
- `check`
- `receipt`

## Public Commands

```bash
tereo demo
tereo prove
tereo show
tereo log
```

If you do not pass `--repeat`, TEREO starts small and measures deeper when the signal deserves doubt.
`hold` is a normal outcome, not an error state.

## Install

```bash
pip install tereo
```

If you prefer module execution, use `python3 -m tereo` instead.

If you are working inside this repo instead:

```bash
pip install -e .
```

## Developer Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
PYTHONPATH=runtime/src python3 -m unittest discover -s runtime/tests -v
```

`pytest` in the examples is an example project check, not a runtime dependency.

## 3-Minute Proof

1. Install TEREO.

```bash
pip install tereo
```

2. Run the throwaway demo loop.

```bash
tereo demo
```

## Quick Start

1. Save one small check.

```bash
tereo init --preset pytest --timeout-seconds 30
```

2. Record the current baseline.

```bash
tereo prove --promise "Current parser behavior is the baseline"
```

3. Make one small change, then prove it.

```bash
tereo prove --scope src/parser.py --promise "Empty input returns []"
tereo show
tereo log
```

Use `--preset latency` when your check is performance.

## First-Check Shortcuts

```bash
tereo init --preset pytest
tereo init --preset npm-test
tereo init --preset smoke
tereo init --preset latency
```

If you are not sure which one fits your repo:

```bash
tereo doctor
```

## Commands

- `tereo demo`
  Run the throwaway TEREO demo loop in a temporary workspace.
- `tereo prove`
  The default path. If there is no baseline yet, it records one. If there is one, it compares the current change and writes a receipt.
- `tereo show`
  Show the latest receipt.
- `tereo log`
  Show a short recent receipt history.
- `tereo init`
  Create the `.tereo/` workspace and save an optional default check.
  Presets: `pytest`, `npm-test`, `smoke`, `latency`.
- `tereo baseline`
  Run the current check and record the baseline.
- `tereo try`
  Run the same check after a change and write a receipt.
- `tereo control`
  Rerun the current baseline several times and measure drift, noise, and confidence.
- `tereo report`
  Show the proofboard: current frontier, confidence, and recent receipts.
- `tereo comment`
  Render a short PR comment from the latest receipt and confidence state.
- `tereo doctor`
  Inspect local setup and available tools.

## Why TEREO Is Different

- bring your own check
- works across Python, Node, shell, and mixed repos
- writes short receipts and exact scorecards instead of long theory
- treats `hold` as a useful verdict when proof is still weak
- reruns controls so one lucky run is not enough
- reports confidence so signal can be compared against noise
- safe to stop at any time
- works especially well beside AI because it verifies what the AI suggested

## Turn Up Certainty

The quick path stays simple.
When you need more evidence, add repeated runs or the advanced control step:

```bash
tereo prove --promise "Current latency is the baseline" --repeat 5
tereo prove --scope src/cache.py --promise "Cache hits lower latency" --repeat 5
tereo control --repeat 5
```

Repeated `baseline` and `try` runs add:

- a mean score instead of a single lucky run
- a 95% confidence interval for the measured value
- a bootstrap `win_probability`
- an improvement interval that shows how much gain is still plausible under noise

The important part is that `tereo prove` can do a smaller version of this automatically.
You only reach for explicit `--repeat` when you want to force more certainty yourself.

## FAQ

These moves are for the current proof loop, not a full project review.
The goal is not to force `keep`.
The goal is to move to a smaller, more provable change.

### I keep getting `hold`

That usually means the change is still too close to noise.

- shrink the scope
- stabilize the check
- add `--repeat`
- run `tereo control --repeat 5` if the check is noisy or metric-based

### I keep getting `drop`

That usually means the patch did not hold.

- discard the patch
- change the tactic
- or change the promise before trying again

Do not keep pushing the same failed patch through the loop.

### I found a new problem while proving

Do not ask the current receipt to ignore it first.

If the new problem makes the current win false, it belongs to this loop.
Tighten the current check, or drop the patch.

If the new problem does not make the current win false, keep it out of this loop.
Make it the next promise instead.

### My first check feels flaky

Do not push the loop harder yet.
Shrink the check first.

- use a smaller test target
- use a stabler smoke check
- remove unrelated work from the first proof

TEREO is strongest when one repeatable check can judge one small change.

## Scientific Shape

TEREO keeps the front door small, but the thinking is serious:

- `promise`
  The claim you want to test.
- `check`
  The repeated command that decides whether the claim holds and whether the gain is real enough to keep.
- `receipt`
  The human and machine proof left behind.

## Code Shape

The runtime is built around three ideas:

- `law`
  keep only if gain beats measured noise
- `measure`
  run the check and collect evidence
- `judge`
  decide whether gain beats noise
- `receipt`
  save and show the result

## Examples

See [examples/README.md](examples/README.md).

For a sticky PR receipt comment, copy:

- `runtime/examples/github/tereo-pr-comment.yml`
- `runtime/examples/github/tereo-pr-comment.sh`

Start without `control`.
Add `tereo control --repeat 5` only when the check is noisy or metric-based.
