# Production readiness contract

Gander v1 targets a deliberately narrow production scope: a single-process deterministic NDJSON event/state reducer.

## Guaranteed by the v1 contract

- 65,536-byte retained physical-record cap.
- 65,536 physical records per reduction window.
- Exact `event_id` dedupe inside a window.
- `(trace_id,key)` state identity and strict greatest `(ts,seq)` winner.
- Deterministic snapshot ordering.
- Pure NDJSON on stdout and operational counters on stderr.
- Recovery after malformed or oversized records.
- Duplicate required JSON fields are rejected.
- Unknown JSON fields are ignored.
- `--strict` provides fail-closed validation behavior.

## Exit codes

- `0`: processing completed.
- `2`: invalid CLI option.
- `3`: `--strict` and one or more records were rejected.

## Non-goals

No durable state, replication, distributed execution, Kafka wire compatibility, SQL, or cross-window exact duplicate suppression is claimed in v1.

## Stable-candidate evidence

The final local gate verifies:

- production CLI contract,
- release and debug builds,
- explicit adversarial cases,
- 500 deterministic randomized Goose/Rust differential seeds,
- one-million-event split-stream Goose/Rust equality,
- one-million-event fair benchmark,
- one long-lived 10M-event memory run.

Latest measured long-stream result:

- 1M peak RSS: 49.63 MiB
- 10M peak RSS: 52.12 MiB
- RSS growth: 1.050x
- 10M records: 153 windows

## Running from a checkout

```bash
make build GOOSE=/path/to/goose
./build/gander --strict < examples/ci-pipeline.ndjson > state.ndjson
```

Optional local installation:

```bash
make install PREFIX="$HOME/.local" GOOSE=/path/to/goose
```
