# Plain-text fallback and graceful error handling — end-to-end

**Parent:** [#76](https://github.com/rh-ai-quickstart/ai-driven-network-remediation/issues/76)
**Type:** AFK
**Blocked by:** [01-canonical-json-golden-path](01-canonical-json-golden-path.md)

## What to build

Add the fallback branch to the normalize parsing function for non-JSON and malformed input. The pipeline must never crash on unexpected input — malformed or unrecognized events produce a `LogEvent` with `"unknown"` defaults and a warning log, allowing downstream nodes to continue with degraded but functional data.

- **Fallback logic in `normalize.py`**: when `raw_event` is not valid JSON or doesn't match the canonical schema, populate `LogEvent.message` and `LogEvent.raw` with the original string and set all other fields to `"unknown"` / defaults.
- **Warning log**: emit a `loguru` warning when falling back, so operators can see that an event wasn't parsed.
- **Unit tests**: cover plain text input, broken/malformed JSON, empty string. Assert that the correct fields are populated and no exception is raised.

## Acceptance criteria

- [ ] Non-JSON `raw_event` produces a `LogEvent` with `message` and `raw` populated, all other fields `"unknown"` / defaults
- [ ] Malformed JSON (e.g., truncated, invalid syntax) is handled the same as plain text — no crash
- [ ] A `loguru` warning is emitted when the fallback path is taken
- [ ] Unit tests cover: plain text, broken JSON, empty string
- [ ] All existing tests pass
