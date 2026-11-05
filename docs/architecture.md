# Gander architecture

## Design goal

Total stream length must not force retained in-memory state to grow
proportionally.

Current principal limits:

```text
MAX_EVENT_BYTES     = 65,536
WINDOW_RECORD_LIMIT = 65,536
```

## Ingress

Input is read in bounded chunks.

A physical record is retained only up to `MAX_EVENT_BYTES`. When byte 65,537
is encountered, Gander enters dropping mode, clears the retained partial
record, discards input until newline, counts the record as rejected and
oversized, then resumes framing.

EOF without a trailing newline is supported.

## Reduction window

At 65,536 physical records Gander:

1. materializes the reduced state,
2. sorts it deterministically by `trace_id` and then `key`,
3. emits the snapshot,
4. clears window-local dedupe state,
5. clears window-local reduced state,
6. begins the next window.

Retained dedupe and state cardinality therefore depend on one window rather
than total stream lifetime.

## State semantics

State identity is `(trace_id, key)`.

For two candidates with the same state key, only a strictly greater `(ts, seq)`
tuple replaces the winner. Equal tuples preserve the first accepted winner.

The winner retains the `source` field as provenance.

## Dedupe semantics

`event_id` deduplication is exact inside one window and intentionally resets
across window boundaries.

## Snapshot composition

The same latest-wins rule can reduce window snapshots again.

On the deterministic one-million-event workload:

```text
global final states   = 20,000
composed final states = 20,000
mismatches            = 0
```

## Goose-specific experiment

Goose uses compiler-managed data stacks. Gander aligns a semantic reduction
boundary with a memory-lifetime boundary.

That combination is the central systems experiment in this project.

## Rust references

`src/main.rs` is an independent correctness oracle.

`src/bin/gander_windowed_bench.rs` mirrors the bounded architecture closely
enough for a fair implementation comparison.

## v1.0 boundaries

The engine is single-process, single-threaded, non-durable, and
non-distributed.

Persistence, recovery, replication, networking, and cluster semantics are
outside the v1.0 scope.
