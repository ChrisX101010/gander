# Gander

**A bounded-memory event and state reduction engine written in Goose.**

Gander is an application-level systems experiment designed around the Goose
memory model. It consumes NDJSON event streams, performs exact window-local
deduplication, reduces state deterministically, retains provenance, and emits
deterministic snapshots.

The repository includes independent Rust implementations and deliberately
preserves benchmark results even when Goose does not win.

## Event model

Each input record is one NDJSON object:

```json
{"trace_id":"t1","event_id":"e1","ts":100,"seq":1,"key":"status","value":"started","source":"agent"}
```

State identity is `(trace_id, key)`. A candidate replaces the current state
only when `(candidate.ts, candidate.seq) > (current.ts, current.seq)`.
Equal ordering tuples preserve the first accepted winner.

Exact `event_id` deduplication is scoped to one reduction window.

## Hard bounds

| Limit | Value |
|---|---:|
| Retained physical record | 65,536 bytes |
| Records per reduction window | 65,536 |
| `trace_id` | 64 bytes |
| `event_id` | 64 bytes |
| `key` | 64 bytes |
| `value` | 256 bytes |
| `source` | 64 bytes |

## Architecture

```text
NDJSON stream
    |
bounded reads
    |
65,536-byte record cap
    |
parse + validate
    |
window-local exact dedupe
    |
latest-wins state reduction
    |
deterministic sort
    |
window snapshot
    |
clear window state -> next window
```

A reduction window acts as both a semantic boundary and a memory-lifetime
boundary.

See [docs/architecture.md](docs/architecture.md).

## Correctness

Current verified gates include:

- independent Rust correctness oracle
- 65,537-record window-boundary equality
- one-million-event full snapshot byte equality
- explicit adversarial differential suite
- 65,536-live-state high-cardinality test
- deterministic repeated output
- 50 deterministic randomized differential seeds
- randomized cross-window workloads

All current Goose-versus-Rust differential gates pass byte-for-byte.

## Long-stream memory

Measured during development:

| Input | Peak RSS |
|---|---:|
| 1,000,000 events | 49.61 MiB |
| 10,000,000 events | 51.92 MiB |

The tested stream grew by **10.000x**, while peak RSS grew by **1.047x**.

The 10M test ran inside one long-lived process and produced 153 bounded
windows. This demonstrates a memory plateau for the tested workload and
range; it is not a claim that every possible workload has identical peak
memory.

## Goose versus equivalent Rust

Fair one-million-event benchmark:

| Metric | Goose | Rust |
|---|---:|---:|
| Median runtime | 1.690 s | 1.565 s |
| Median throughput | 591,716 events/s | 638,984 events/s |
| p95 runtime | 1.800 s | 1.670 s |
| Median peak RSS | 49.62 MiB | 41.94 MiB |

For this workload, Rust was approximately 8.0% higher-throughput and used
approximately 15.5% less peak RSS.

Gander does **not** claim that Goose universally outperforms Rust.

See [docs/benchmarks.md](docs/benchmarks.md).

## Build

Requirements:

- Goose
- a native C compiler supported by Goose
- Rust
- Python 3

```bash
make build GOOSE=/path/to/goose
```

With a local Goose checkout:

```bash
make build GOOSE=~/projects/goose/build/goose
```

Primary bounded executable:

```text
build/gander-windowed
```

Example:

```bash
build/gander-windowed < fixtures/smoke.ndjson
```

## Verify

```bash
make verify GOOSE=/path/to/goose
```

Expected final marker:

```text
GANDER_VERIFY=GREEN
```

## Repository layout

```text
src/main.goose
    Finite-stream global baseline.

src/windowed.goose
    Primary bounded Goose engine.

src/windowed_bench.goose
    Quiet benchmark version.

src/main.rs
    Independent Rust correctness oracle.

src/bin/gander_windowed_bench.rs
    Equivalent bounded Rust implementation.

tools/gen_workload.py
    Deterministic 1M workload generator.

tools/adversarial_gate.py
    Explicit adversarial tests.

tools/differential_fuzz.py
    Deterministic randomized differential tests.

tools/bench_compare.py
    Reproducible Goose-versus-Rust benchmark.
```

## Scope

Gander v1.0 is intentionally single-process, single-threaded, NDJSON-oriented,
non-durable, and non-distributed.

It is not a replacement for distributed platforms such as Apache Flink,
Kafka Streams, RisingWave, or Materialize.

Gander explores a smaller systems design point: deterministic bounded-memory
native state reduction.

## Status

**v1.0 release candidate.**

Core reducer semantics are frozen unless correctness testing identifies a
concrete defect.
