# Gander bounded window contract

Gander global mode is the finite-stream correctness baseline.

Gander windowed mode is intended for arbitrarily long streams.

## Bounds

- Maximum retained bytes for one input record: 65,536.
- Maximum physical records processed in one reduction window: 65,536.
- Exact event_id deduplication is scoped to one window.
- Live reduced state is scoped to one window.
- At a window boundary Gander emits a deterministic state snapshot.
- Window-local dedupe and state are reset before processing the next window.
- Memory therefore depends on configured window size and record limits,
  not total stream length.

## Reduction

State identity:

    (trace_id, key)

Winner:

    greatest (ts, seq)

Each emitted event retains source provenance.

## Composition

Each window snapshot is itself a reduced event set.

A downstream latest-wins reduction of window snapshots can reconstruct
the latest state across windows.

Exact duplicate accounting is window-local by design.
