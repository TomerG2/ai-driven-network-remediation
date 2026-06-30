# Level normalization — end-to-end

**Parent:** [#76](https://github.com/rh-ai-quickstart/ai-driven-network-remediation/issues/76)
**Type:** AFK
**Blocked by:** [01-canonical-json-golden-path](01-canonical-json-golden-path.md)

## What to build

Add log level normalization to the normalize parsing function so downstream consumers can rely on a consistent set of level values. This is a small but complete vertical slice — touches the parsing logic and adds targeted tests.

- **Normalization logic in `normalize.py`**: lowercase the `level` field and map common aliases:
  - `"WARNING"` → `"warn"`
  - `"CRITICAL"` → `"error"`
  - Already-correct values (`"error"`, `"warn"`, `"info"`) pass through unchanged after lowercasing.
- **Unit tests**: cover uppercase variants, alias mapping, already-normalized values, and unexpected level strings (pass through lowercased, no crash).

## Acceptance criteria

- [ ] `level` field is lowercased in all cases
- [ ] `"WARNING"` (any case) maps to `"warn"`
- [ ] `"CRITICAL"` (any case) maps to `"error"`
- [ ] Unrecognized level values are lowercased and passed through (no crash or rejection)
- [ ] Unit tests cover: `"WARNING"`, `"CRITICAL"`, `"Error"`, `"info"`, `"INFO"`, unexpected values
- [ ] All existing tests pass
