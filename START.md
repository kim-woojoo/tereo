# Start TEREO

Same engine. Different doorways.
TEREO uses the same `tereo` runtime in each one.

## Terminal

1. Install TEREO.

```bash
pip install tereo
```

2. Feel the loop first.

```bash
tereo demo
```

3. Start your own repo with one small check.

```bash
tereo init --preset pytest
tereo prove --promise "Current tests are the baseline"
```

A good first check shows one gain and catches the core breakage that would make that gain false.

4. Make one small change, then prove it.

```bash
tereo prove --scope src/parser.py --promise "Empty input returns []"
tereo show
tereo log
```

Working on this repo itself? Use `pip install -e .`.

If you prefer module execution, run `python3 -m tereo` instead.

If you are not sure which check to trust first:

```bash
tereo doctor
```

## Agent IDE / CLI

Use the same TEREO runtime.
Codex, Claude Code, OpenClaw, and similar agent tools all fit here.
Give the AI this small contract:

```text
Use tereo for small, checkable changes.
Freeze a promise, scope, check, proof rule, and stop condition.
Think in Promise -> Check -> Receipt.
Use `tereo prove` as the default path.
Keep only what earns a receipt.
If a new failure makes the current win false, keep it in the same loop.
```

The AI may write the change.
`tereo` decides whether the change stays.

Use the same portable rule through:

- [skill/SKILL.md](skill/SKILL.md)

## Browser AI

Use browser AI as the idea partner, not the judge:

1. ask the AI for one small change idea
2. run `tereo` locally in your repo
3. paste the receipt or report back into the AI
4. iterate only on what the proof supports

## Pick A First Check

If you are not sure where to start, choose the smallest check that already matters:

- `pytest -q`
  for a Python repo with stable tests
- `npm test -- --runInBand`
  for a Node repo with a real test command
- `./smoke-test.sh`
  for a shell or mixed repo with a simple pass/fail check
- `./bench.sh`
  for a metric-printing benchmark such as latency or memory

The first check should not only show the hoped-for gain.
It should also catch the core breakage that would turn that gain into a false win.

If the first check is flaky, shrink it before trusting the loop.

## Advanced

If you need the deeper engine, it is still there:

- `tereo doctor`
- `tereo init`
- `tereo baseline`
- `tereo try`
- `tereo control`
- `tereo report`
- `tereo comment`

## Research

If you want the philosophy behind the shape:

- [WHY.md](WHY.md)
- [dogfood/README.md](dogfood/README.md)
- [skill/SKILL.md](skill/SKILL.md)
- [flows/](flows)

This project is small on purpose.
The front door is meant to be smaller than the thinking behind it.
