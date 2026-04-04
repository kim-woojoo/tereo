# TEREO Error Log

Use this file for real product, runtime, packaging, and release errors.
Keep entries short.
One issue, one block.
Update status instead of rewriting history.

## Open

### 2026-04-04 - PyPI tag publish did not match trusted publisher

- status: open
- surface: release / PyPI
- symptom: the `v0.1.2` tag-triggered publish run built successfully but failed at the PyPI publish step
- root cause: PyPI trusted publishing did not recognize the tag-based claims for this repo
- evidence:
  - run: `23968160377`
  - error: `invalid-publisher`
  - claim seen by PyPI: `repo:kim-woojoo/tereo:ref:refs/tags/v0.1.2`
- impact: tag-based release publishing is not currently reliable
- mitigation: publish flow was moved to a `main` push path gated by `Release ...` commits
- next check: confirm the main-based publish flow run `23968215703` completes and PyPI reflects `0.1.2`

## Resolved

### 2026-04-04 - `doctor` missed `runtime/tests` Python repos

- status: resolved
- surface: `tereo doctor`
- symptom: repos shaped like TEREO itself could show `no obvious preset detected`
- root cause: preset detection only looked for top-level `tests`, `pytest.ini`, and `pyproject.toml`
- fix: Python preset detection now also checks `test`, `runtime/tests`, and `tox.ini`
- proof:
  - code: [runtime/src/tereo/cli.py](/Users/general/Documents/Tereo/runtime/src/tereo/cli.py)
  - test: [runtime/tests/test_cli.py](/Users/general/Documents/Tereo/runtime/tests/test_cli.py)

### 2026-04-04 - First-run docs were less reliable than the actual launcher

- status: resolved
- surface: docs / install UX
- symptom: docs and examples pointed to different first-run paths
- root cause: docs drifted away from the real shortest front door
- fix: front-door docs were reset to `pip install tereo` then `tereo ...`; module execution is now the fallback path
- proof:
  - docs: [README.md](/Users/general/Documents/Tereo/README.md)
  - docs: [runtime/README.md](/Users/general/Documents/Tereo/runtime/README.md)
