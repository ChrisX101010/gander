# Benchmarks and evidence

## Principle

Correctness is established before performance is compared. Results are
preserved even when they do not favor Goose.

## Deterministic 1M workload

```text
physical events = 1,000,000
unique          =   900,000
duplicates      =   100,000
state keys      =    20,000
```

Global result:

```text
accepted   = 1,000,000
rejected   = 0
unique     = 900,000
duplicates = 100,000
stale      = 125,714
superseded = 754,286
final      = 20,000
```

The Goose implementation and independent Rust oracle produced identical
output.

## Window composition

The 1M workload produced 16 bounded windows. Composing the snapshots produced:

```text
global final states   = 20,000
composed final states = 20,000
mismatches            = 0
```

## Long-stream memory

```text
1M peak RSS  = 49.61 MiB
10M peak RSS = 51.92 MiB

input growth = 10.000x
RSS growth   = 1.047x
```

The 10M stream was processed by one long-lived process in 153 windows.

## Fair Goose versus Rust benchmark

Method:

```text
2 warmups
10 measured Goose runs
10 measured Rust runs
alternating execution order
same warmed input
same logical CPU
same window size
same reducer semantics
same deterministic sorting
snapshot payload output suppressed
```

Results:

| Metric | Goose | Rust |
|---|---:|---:|
| Median runtime | 1.805 s | 1.615 s |
| Mean runtime | 1.718 s | 1.580 s |
| p95 runtime | 1.890 s | 1.740 s |
| Median throughput | 591,716 ev/s | 638,984 ev/s |
| Median peak RSS | 49.70 MiB | 41.99 MiB |

For this workload Rust is faster and uses less peak RSS.

## Correctness gates

```text
global Goose/Rust oracle equality         GREEN
65,537-record boundary equality           GREEN
1M full-snapshot byte equality            GREEN
explicit adversarial differential suite   GREEN
65,536-live-state high-cardinality test   GREEN
repeated deterministic output             GREEN
50-seed randomized differential suite     GREEN
```

Raw fair benchmark evidence is stored in:

```text
bench/fair-1m.csv
bench/fair-1m-summary.json
```

## Stable-candidate re-run

The final local stable gate re-ran the fair one-million-event benchmark after
the production CLI/parser hardening.

| Metric | Goose | Rust |
|---|---:|---:|
| Median runtime | 1.805 s | 1.615 s |
| Median throughput | 554,021 events/s | 619,201 events/s |
| p95 runtime | 1.890 s | 1.740 s |
| Median peak RSS | 49.70 MiB | 41.99 MiB |

On this re-run Rust had approximately 11.8% higher median
throughput and used approximately 15.5% less median peak RSS.

The p95 values are intentionally reported as measured; this run included
host-noise outliers and Gander does not discard unfavorable samples.

The long-stream re-run measured 49.63 MiB peak RSS at 1M events and
52.12 MiB at 10M events, a 1.050x RSS ratio for 10x input.

See `bench/fair-1m-summary.json`, `bench/stable-long-stream-summary.json`, and
`bench/environment-public.txt`.
