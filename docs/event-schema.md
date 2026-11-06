# Gander event schema v1

Input is NDJSON, one JSON object per physical record.

Required fields:

- `trace_id`: non-empty string, max 64 UTF-8 bytes
- `event_id`: non-empty string, max 64 UTF-8 bytes
- `ts`: signed i64
- `seq`: signed i64
- `key`: non-empty string, max 64 UTF-8 bytes
- `value`: string, max 256 UTF-8 bytes; may be empty
- `source`: non-empty string, max 64 UTF-8 bytes

Duplicate occurrences of required fields are rejected. Unknown fields are ignored for forward compatibility. Blank physical lines are ignored. Maximum retained physical record size is 65,536 bytes.

Reduction: validate -> window-local exact `event_id` dedupe -> state `(trace_id,key)` -> greatest `(ts,seq)` wins -> retain source provenance -> deterministic sorted snapshot.

Stable stream contract: stdout contains NDJSON snapshots only; stderr contains counters unless `--quiet` is used. `--strict` exits 3 if any record was rejected.
