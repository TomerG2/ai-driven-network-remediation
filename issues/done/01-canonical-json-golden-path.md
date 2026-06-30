# Canonical JSON golden path parsing — end-to-end

**Parent:** [#76](https://github.com/rh-ai-quickstart/ai-driven-network-remediation/issues/76)
**Type:** AFK
**Blocked by:** None — can start immediately

## What to build

Replace the normalize node stub with a real parsing function that extracts structured fields from canonical JSON events (matching `contracts/nginx-logs.schema.json`) into fully populated `LogEvent` instances. Cut through every layer end-to-end:

- **Parsing logic in `normalize.py`**: attempt JSON parse of `raw_event`, check for the canonical schema (presence of `kubernetes` key with nested fields, `@timestamp`, `labels`), and map fields per the schema:
  - `@timestamp` → `LogEvent.timestamp`
  - `message` → `LogEvent.message`
  - `level` → `LogEvent.level`
  - `kubernetes.namespace_name` → `LogEvent.namespace`
  - `kubernetes.pod_name` → `LogEvent.pod_name`
  - `kubernetes.container_name` → `LogEvent.container`
  - `labels.edge_site_id` → `LogEvent.edge_site_id`
  - Full original string → `LogEvent.raw`
- **CLI default**: update the hardcoded `raw_event` in `__init__.py` to use canonical JSON format so local testing exercises the real parsing path.
- **Test helpers**: update `make_state()` default `raw_event` to canonical JSON. Align `make_log_event()` defaults if needed.
- **Integration test**: update `test_normalize_produces_log_event` in `test_graph.py` to use canonical JSON input and assert real field extraction (namespace, pod_name, timestamp) — not just that a `LogEvent` exists.
- **Unit tests**: add tests for canonical JSON with all fields present, and canonical JSON with missing optional fields (e.g., no `labels`) defaulting to `"unknown"`.

After this slice, the system works with real structured data end-to-end.

## Acceptance criteria

- [ ] Normalize node extracts all canonical JSON fields into `LogEvent` per the field mapping above
- [ ] Missing optional fields in canonical JSON default to `"unknown"` (not crash)
- [ ] `LogEvent.raw` always contains the original `raw_event` string
- [ ] CLI default `raw_event` is valid canonical JSON matching the contract schema
- [ ] `make_state()` default `raw_event` is canonical JSON
- [ ] Integration test in `test_graph.py` asserts real field values (namespace, pod_name, timestamp)
- [ ] Unit tests cover: all fields present, missing optional fields
- [ ] All existing tests pass
