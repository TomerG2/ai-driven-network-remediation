# kafka_offset passthrough — end-to-end

**Parent:** [#76](https://github.com/rh-ai-quickstart/ai-driven-network-remediation/issues/76)
**Type:** AFK
**Blocked by:** None — can start immediately

## What to build

Add `kafka_offset` as transport metadata on `IncidentState` and wire the normalize node to pass it through to `LogEvent`. This prepares the plumbing for the Kafka consumer (issue #75) without requiring any parsing changes.

- **Model**: add `kafka_offset: int = 0` field to `IncidentState` (Pydantic BaseModel per ADR-0001).
- **Normalize node**: update `normalize.py` to copy `state.kafka_offset` into `LogEvent.kafka_offset` instead of hardcoding `0`.
- **Unit test**: verify that when `IncidentState` is created with a specific `kafka_offset` value, the resulting `LogEvent` carries that same value through.

## Acceptance criteria

- [ ] `IncidentState` has a `kafka_offset: int = 0` field
- [ ] Normalize node reads `state.kafka_offset` and passes it to `LogEvent.kafka_offset`
- [ ] Unit test confirms the passthrough (non-zero value in → same value out)
- [ ] All existing tests pass
