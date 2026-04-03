# Promise Template

- `promise`:
- `scope`:
- `check`:
- `proof rule`:
- `lane`:
- `stop condition`:

## Tiny Example

- `promise`: Empty input returns `[]`
- `scope`: `src/parser.py`
- `check`: `pytest tests/test_parser.py -q`
- `proof rule`: Keep only if the check passes
- `lane`: Auto. Keep the default lane unless you intentionally want to share this proof across agents.
- `stop condition`: One kept patch or one real blocker
