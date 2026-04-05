# TEREO Examples

## Quick Start

If you want the fastest possible first win, start here:

```bash
bash runtime/examples/quickstart.sh
```

## GIF Capture

If you want one clean install + demo recording:

```bash
python3 -m pip install tereo
tereo demo
```

That is the shortest visible path.
If the short command is not on `PATH` yet, `python3 -m tereo demo` is the same runtime.

If you want the same real install and run inside a temporary sandbox, with cleanup after recording:

```bash
bash runtime/examples/capture-demo.sh
```

It creates a fresh temp workspace, runs the real `pip install tereo`, runs the real `tereo demo`, and deletes the sandbox on exit.
It also types the visible commands slowly enough to record and pauses on the final `keep` verdict for a beat.
Add `--workspace /tmp/tereo-demo` if you want a shorter path on screen, or `--keep-workspace` if you want to inspect the sandbox after.

If you want the same flow from this repo instead of PyPI:

```bash
bash runtime/examples/capture-demo.sh --source local
```

Recording tips:

- keep the terminal around 90 columns
- use a large mono font
- record only the terminal window
- let the last frame sit for 2 seconds
- if you are on macOS, `Cmd+Shift+5` is enough

## PR Comment Integration

If you want one sticky receipt comment in every trusted same-repo PR:

<p>
  <img
    src="https://raw.githubusercontent.com/kim-woojoo/tereo/main/assets/readme/tereo-pr-comment-preview.svg"
    alt="TEREO sticky PR comment preview"
    width="860"
  />
</p>

- copy `runtime/examples/github/tereo-pr-comment.yml` to `.github/workflows/tereo-pr-comment.yml`
- copy `runtime/examples/github/tereo-pr-comment.sh` to `.github/scripts/tereo-pr-comment.sh`

Change only these three values.
Keep the loop:

- `TEREO_CHECK`
- `TEREO_SCOPE`
- `TEREO_PROMISE`

The workflow compares the base branch with the PR head, then updates the same TEREO comment instead of adding a new one every run.

Start without control.
Add `tereo control --repeat 5` only when the check is noisy or metric-based.

## Pytest

```bash
tereo init --check "pytest -q"
tereo prove --promise "Current tests are green"
tereo prove --scope src/parser.py --promise "Empty input returns []"
tereo show
tereo log
```

## npm test

```bash
tereo init --check "npm test -- --runInBand"
tereo prove --promise "Current tests are green"
tereo prove --scope src/parser.ts --promise "Blank lines are ignored"
tereo show
tereo log
```

## Shell check

```bash
tereo init --check "./smoke-test.sh"
tereo prove --promise "The smoke test is green"
tereo prove --scope script.sh --promise "The script handles missing args"
tereo show
tereo log
```

## Metric Mode

If your benchmark can print one explicit metric line, that is the cleanest path:

```bash
tereo prove \
  --check "./bench.sh" \
  --promise "Current latency is the baseline"

tereo prove \
  --scope src/cache.py \
  --promise "Cache hits lower latency"

tereo show
tereo log
```

With output like:

```text
TEREO_METRIC latency 12.3 lower ms
```

Known lines such as `latency_ms: 12.3` can also auto-seed on the first baseline.

If your check prints a custom number and cannot be changed, fall back to a regex:

```bash
tereo prove \
  --check "./bench.sh" \
  --metric-pattern "latency_ms: ([0-9.]+)" \
  --direction lower \
  --promise "Current latency is the baseline"

tereo prove \
  --scope src/cache.py \
  --promise "Cache hits lower latency" \
  --metric-pattern "latency_ms: ([0-9.]+)" \
  --direction lower

tereo show
tereo log
```
