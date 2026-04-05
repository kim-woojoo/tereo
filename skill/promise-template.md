# Promise Template

- `promise`:
- `scope`:
- `check`:
- `metric`:
- `proof rule`:
- `lane`:
- `stop condition`:

## Tiny Example

- `promise`: Empty input returns `[]`
- `scope`: `src/parser.py`
- `check`: `pytest tests/test_parser.py -q`
- `metric`: none
- `proof rule`: Keep only if the check passes
- `lane`: Auto. Keep the default lane unless you intentionally want to share this proof across agents.
- `stop condition`: One kept patch or one real blocker

## Metric Examples

- `metric`: `TEREO_METRIC latency 12.3 lower ms`
- `metric`: `latency_ms: 12.3` if the existing benchmark already prints that shape
- `metric`: custom output, so pass `--metric-pattern`
