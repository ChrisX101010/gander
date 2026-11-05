# Gander V0 Event

Input format: NDJSON, one JSON event per line.

Required fields:

- trace_id: string
- event_id: string
- ts: integer
- seq: integer
- key: string
- value: string
- source: string

V0 pipeline:

validate
→ deduplicate by event_id
→ supersede state by (trace_id, key)
→ newer (ts, seq) wins
→ preserve source provenance
→ deterministic output
