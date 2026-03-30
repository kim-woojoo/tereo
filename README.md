# TEREO

AI writes. TEREO proves.

TEREO is a proof layer for AI coding.
`keep only if gain > noise`
Each kept receipt becomes the next baseline.

It watches one small change, reruns one fixed check, and writes one readable receipt.
The check can prove a bug fix, a behavior change, or a speedup.

TEREO comes from Ancient Greek `τηρέω` (`tēréō`):
to watch over, guard, preserve.

One proofboard.

<p>
  <img
    src="https://raw.githubusercontent.com/kim-woojoo/tereo/main/assets/readme/tereo-proofboard.svg"
    alt="TEREO proofboard"
    width="860"
  />
</p>

## Demo

1. Install TEREO.

```bash
pip install tereo
```

2. Feel the loop.

```bash
tereo demo
```

Working on this repo itself? See the local setup in [runtime/README.md](runtime/README.md).

The demo should close with something like this:

```text
scorecard: latency: 10.000000 ms -> 8.000000 ms; 2.000000 ms better (20.00%)
verdict: keep
confidence: high
```

## Quick Start

1. Install TEREO.

```bash
pip install tereo
```

2. Run TEREO locally.

```bash
tereo --help
```

3. If you prefer module execution, run:

```bash
python3 -m tereo --help
```

Use your own check.
Keep your own workflow.
Make it yours.

TEREO is small on purpose.
Fork it. Keep it. Make it yours.

## Public Commands

```bash
tereo demo
tereo prove
tereo show
tereo log
```

Everything else is there to support this surface, not to replace it.

## Why This Is Hard

- one good-looking run can lie
- gains drift
- noise changes verdicts
- checks matter more than vibes
- `hold` is different from `keep`

## Narrow By Design

TEREO is strongest when one fixed check can judge one small change.
That is a feature, not a full replacement for broader product judgment.

## Read Next

- [START.md](START.md)
  Start here.
- [runtime/README.md](runtime/README.md)
  The runtime, advanced commands, receipts, and proofboard.
- [skill/README.md](skill/README.md)
  The portable rulebook for humans and agents.
- [WHY.md](WHY.md)
  Why TEREO stays this small.

If the project is easy to explain, it is easy to trust.
