# TEREO Update Log

Use this file for short product updates.
Keep entries compact.
Prefer outcomes over implementation detail.

## 2026-04-04

### Repo logging started

- added [TEREO_ERR_LOG.md](/Users/general/Documents/Tereo/TEREO_ERR_LOG.md) for active and resolved product issues
- added [TEREO_UPDATE_LOG.md](/Users/general/Documents/Tereo/TEREO_UPDATE_LOG.md) for short, cumulative product updates
- these logs are intended to be updated continuously as work progresses

### Release 0.1.2 path tightened

- restored the short front door: `pip install tereo` then `tereo`
- kept `python3 -m tereo` as fallback, not the default
- added a minimal [pyproject.toml](/Users/general/Documents/Tereo/pyproject.toml) build-system entry
- bumped package version to `0.1.2`
- added publish smoke checks for both `tereo --help` and `python -m tereo --help`
- changed PyPI publish automation to run from `main` release commits as well as manual dispatch
- current public status check: PyPI still shows `0.1.1`; the new main-based publish run is `23968215703`

### Doctor got more realistic

- `tereo doctor` now recognizes more Python repo shapes
- TEREO-style `runtime/tests` layouts are now treated as Python preset candidates
- regression coverage was added so this does not silently drift again

### Recent baseline work already in repo

- proof lanes became thread-aware for subagent-safe parallel work
- receipts and state became proof-scoped instead of workspace-singleton only
- README gained a link to the detailed blog post: [What Is TEREO?](https://kimwoojoo.me/en/blog/what-is-tereo)

## How To Update These Logs

- add a new block at the top when a new issue appears
- move an item from `Open` to `Resolved` only when there is proof
- keep update entries short enough to scan in under a minute
- prefer absolute dates
- include one pointer to code, a test, or a run when possible
