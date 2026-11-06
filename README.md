<p align="center">
  <a href="https://github.com/aardappel/goose">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/aardappel/goose/master/docs/logo/logo_white_fg_trans_bg_mini.png">
      <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/aardappel/goose/master/docs/logo/logo_black_fg_white_bg_mini.png">
      <img alt="Built with the Goose programming language" width="330" src="https://raw.githubusercontent.com/aardappel/goose/master/docs/logo/logo_black_fg_white_bg_mini.png">
    </picture>
  </a>
</p>

<h1 align="center">Gander</h1>

<p align="center"><strong>Bounded-memory, deterministic event/state reduction — written in Goose.</strong></p>

<p align="center">
  <a href="https://github.com/ChrisX101010/gander/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ChrisX101010/gander/actions/workflows/ci.yml/badge.svg?branch=master"></a>
  <a href="https://github.com/ChrisX101010/gander/releases"><img alt="Release" src="https://img.shields.io/github/v/release/ChrisX101010/gander?include_prereleases"></a>
  <a href="LICENSE"><img alt="Apache-2.0" src="https://img.shields.io/github/license/ChrisX101010/gander"></a>
  <a href="https://github.com/aardappel/goose"><img alt="Written in Goose" src="https://img.shields.io/badge/written%20in-Goose-111111"></a>
</p>

<p align="center"><sub>Independent project built with Goose; not an official Goose project.</sub></p>

Gander turns noisy event streams into compact deterministic state snapshots while keeping retained state bounded by a fixed reduction window.

### Why it is useful

- **Unix-pipeline safe:** snapshot NDJSON on stdout; operational counters on stderr.
- **Bounded by design:** 65,536-byte records and 65,536-record windows.
- **Deterministic:** `(trace_id, key)` + greatest `(ts, seq)` + stable sorted output.
- **Differentially verified:** independent Rust references, adversarial tests, randomized workloads.
- **Honest evidence:** benchmark results stay public even when Rust wins.

### Real use case: collapse CI/CD state

```bash
make build GOOSE=/path/to/goose
./build/gander < examples/ci-pipeline.ndjson > latest.ndjson 2> stats.log
```

The fixture contains duplicate, stale and superseded workflow events; Gander emits only the latest deterministic state for `artifact`, `deploy`, `pipeline`, and `tests`.

For validation-sensitive pipelines:

```bash
./build/gander --strict < examples/ci-pipeline.ndjson > reduced.ndjson
```

`--strict` exits with status 3 if any physical input record is rejected.

### Install the command locally

After building:

```bash
make install PREFIX="$HOME/.local" GOOSE=/path/to/goose
```

If `$HOME/.local/bin` is on your `PATH`, Gander is then available as:

```bash
gander --version
gander --strict < examples/ci-pipeline.ndjson > state.ndjson
```

You can always run the repository build directly without installing it:

```bash
./build/gander --version
```


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
| 1,000,000 events | 49.63 MiB |
| 10,000,000 events | 52.12 MiB |

The tested stream grew by **10.000x**, while peak RSS grew by **1.050x**.

The 10M test ran inside one long-lived process and produced 153 bounded
windows. This demonstrates a memory plateau for the tested workload and
range; it is not a claim that every possible workload has identical peak
memory.

## Goose versus equivalent Rust

Fair one-million-event benchmark:

| Metric | Goose | Rust |
|---|---:|---:|
| Median runtime | 1.805 s | 1.615 s |
| Median throughput | 554,021 events/s | 619,201 events/s |
| p95 runtime | 1.890 s | 1.740 s |
| Median peak RSS | 49.70 MiB | 41.99 MiB |

For this workload, Rust was approximately 11.8% higher-throughput and used approximately 15.5% less peak RSS.

Gander does **not** claim that Goose universally outperforms Rust.

See [docs/benchmarks.md](docs/benchmarks.md).

Benchmark machine/toolchain details: [bench/environment-public.txt](bench/environment-public.txt).

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

## Distribution

Stable releases are intended to ship ready-to-run native archives for:

- Linux x86-64
- Windows x86-64
- macOS Apple Silicon

Each stable GitHub release also publishes `SHA256SUMS`.

Docker users can build the same pinned-Goose implementation with:

```bash
docker build -t gander .
docker run --rm -i gander --strict < examples/ci-pipeline.ndjson > state.ndjson
```

Source builds remain supported through `make build` and `make install`.

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
