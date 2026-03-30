# TEREO Examples

## Quick Start

If you want the fastest possible first win, start here:

```bash
bash runtime/examples/quickstart.sh
```

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

When your check prints a number, you can compare it with a regex:

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
