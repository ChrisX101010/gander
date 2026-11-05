#!/usr/bin/env python3

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent

INPUT = ROOT / "fixtures/bench-1m.ndjson"

GOOSE = ROOT / "build/gander-windowed-bench"
RUST = ROOT / "target/release/gander_windowed_bench"

CSV_PATH = ROOT / "bench/fair-1m.csv"
SUMMARY_PATH = ROOT / "bench/fair-1m-summary.json"
ENV_PATH = ROOT / "bench/environment.txt"

EVENTS = 1_000_000
WARMUPS = 2
RUNS = 10


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def command_output(cmd):
    try:
        return subprocess.check_output(
            cmd,
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except Exception as e:
        return f"<unavailable: {e}>"


# Pin both implementations to exactly the same allowed logical CPU.
try:
    allowed = sorted(os.sched_getaffinity(0))
except AttributeError:
    allowed = list(range(os.cpu_count() or 1))

if not allowed:
    print("CPU_AFFINITY=RED")
    sys.exit(1)

# Avoid CPU 0 when possible.
cpu = allowed[min(2, len(allowed) - 1)]

use_taskset = shutil.which("taskset") is not None

if use_taskset:
    probe = subprocess.run(
        ["taskset", "-c", str(cpu), "true"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    use_taskset = probe.returncode == 0

print(f"allowed_cpus={allowed}")
print(f"benchmark_cpu={cpu}")
print(f"taskset={'yes' if use_taskset else 'no'}")


def run_one(name, binary):
    prefix = []

    if use_taskset:
        prefix = ["taskset", "-c", str(cpu)]

    cmd = [
        "/usr/bin/time",
        "-f",
        "GANDER_TIME=%e GANDER_RSS=%M",
        *prefix,
        str(binary),
    ]

    with open(INPUT, "rb") as inp:
        p = subprocess.run(
            cmd,
            stdin=inp,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

    if p.returncode != 0:
        print(f"{name}_RUN=RED rc={p.returncode}")
        print(p.stderr)
        sys.exit(1)

    marker = None

    for line in p.stderr.splitlines():
        if line.startswith("GANDER_TIME="):
            marker = line

    if marker is None:
        print(f"{name}_TIME_PARSE=RED")
        print(p.stderr)
        sys.exit(1)

    fields = dict(
        x.split("=", 1)
        for x in marker.split()
    )

    elapsed = float(fields["GANDER_TIME"])
    rss_kb = int(fields["GANDER_RSS"])

    return {
        "implementation": name,
        "seconds": elapsed,
        "events_per_second": EVENTS / elapsed,
        "rss_kb": rss_kb,
        "rss_mib": rss_kb / 1024,
    }


print()
print("===== WARM INPUT CACHE =====")

with open(INPUT, "rb") as f:
    while f.read(1024 * 1024):
        pass

print("INPUT_CACHE_WARMED=YES")


print()
print("===== WARMUPS =====")

for i in range(WARMUPS):
    g = run_one("goose", GOOSE)
    r = run_one("rust", RUST)

    print(
        f"warmup={i + 1} "
        f"goose={g['seconds']:.3f}s "
        f"rust={r['seconds']:.3f}s"
    )


print()
print("===== MEASURED RUNS =====")

rows = []

# Alternate order to reduce thermal/order bias.
for iteration in range(1, RUNS + 1):

    if iteration % 2:
        order = [
            ("goose", GOOSE),
            ("rust", RUST),
        ]
    else:
        order = [
            ("rust", RUST),
            ("goose", GOOSE),
        ]

    iteration_results = {}

    for name, binary in order:
        result = run_one(name, binary)
        result["iteration"] = iteration

        rows.append(result)
        iteration_results[name] = result

    g = iteration_results["goose"]
    r = iteration_results["rust"]

    print(
        f"run={iteration:02d} "
        f"goose={g['seconds']:.3f}s "
        f"rust={r['seconds']:.3f}s "
        f"goose_rss={g['rss_mib']:.2f}MiB "
        f"rust_rss={r['rss_mib']:.2f}MiB"
    )


CSV_PATH.parent.mkdir(parents=True, exist_ok=True)

with open(CSV_PATH, "w", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "iteration",
            "implementation",
            "seconds",
            "events_per_second",
            "rss_kb",
            "rss_mib",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)


def percentile(values, p):
    xs = sorted(values)
    i = max(
        0,
        min(
            len(xs) - 1,
            math.ceil((p / 100) * len(xs)) - 1,
        ),
    )
    return xs[i]


def summarize(name):
    xs = [
        r
        for r in rows
        if r["implementation"] == name
    ]

    times = [r["seconds"] for r in xs]
    throughputs = [r["events_per_second"] for r in xs]
    rss_values = [r["rss_kb"] for r in xs]

    return {
        "runs": len(xs),

        "seconds_median": statistics.median(times),
        "seconds_mean": statistics.mean(times),
        "seconds_min": min(times),
        "seconds_max": max(times),
        "seconds_p95": percentile(times, 95),

        "events_per_second_median":
            statistics.median(throughputs),

        "events_per_second_mean":
            statistics.mean(throughputs),

        "rss_kb_median":
            statistics.median(rss_values),

        "rss_kb_max":
            max(rss_values),

        "rss_mib_median":
            statistics.median(rss_values) / 1024,

        "rss_mib_max":
            max(rss_values) / 1024,
    }


goose = summarize("goose")
rust = summarize("rust")

# > 1 means Goose completes the workload faster.
goose_speedup = (
    rust["seconds_median"]
    / goose["seconds_median"]
)

# < 1 means Goose uses less peak RSS.
goose_rss_ratio = (
    goose["rss_kb_median"]
    / rust["rss_kb_median"]
)


summary = {
    "events_per_run": EVENTS,
    "window_records": 65_536,
    "warmups": WARMUPS,
    "measured_runs_per_implementation": RUNS,
    "cpu": cpu,
    "taskset": use_taskset,

    "input_sha256": sha256(INPUT),
    "goose_binary_sha256": sha256(GOOSE),
    "rust_binary_sha256": sha256(RUST),

    "goose": goose,
    "rust": rust,

    "goose_speedup_vs_rust_median":
        goose_speedup,

    "goose_rss_ratio_vs_rust_median":
        goose_rss_ratio,
}

SUMMARY_PATH.write_text(
    json.dumps(summary, indent=2) + "\n"
)


environment = f"""Gander benchmark environment

git_commit:
{command_output(["git", "rev-parse", "HEAD"])}

uname:
{command_output(["uname", "-a"])}

lscpu:
{command_output(["lscpu"])}

Goose:
{command_output([str(Path.home() / "projects/goose/build/goose"), "--version"])}

rustc:
{command_output(["rustc", "--version"])}

cargo:
{command_output(["cargo", "--version"])}

input:
{INPUT}

input_sha256:
{sha256(INPUT)}

benchmark_cpu:
{cpu}

taskset:
{use_taskset}
"""

ENV_PATH.write_text(environment)


print()
print("===== FAIR BENCHMARK SUMMARY =====")

print(
    f"GOOSE_MEDIAN_SECONDS="
    f"{goose['seconds_median']:.4f}"
)

print(
    f"RUST_MEDIAN_SECONDS="
    f"{rust['seconds_median']:.4f}"
)

print(
    f"GOOSE_MEDIAN_EVENTS_PER_SEC="
    f"{goose['events_per_second_median']:.0f}"
)

print(
    f"RUST_MEDIAN_EVENTS_PER_SEC="
    f"{rust['events_per_second_median']:.0f}"
)

print(
    f"GOOSE_P95_SECONDS="
    f"{goose['seconds_p95']:.4f}"
)

print(
    f"RUST_P95_SECONDS="
    f"{rust['seconds_p95']:.4f}"
)

print(
    f"GOOSE_MEDIAN_RSS_MIB="
    f"{goose['rss_mib_median']:.2f}"
)

print(
    f"RUST_MEDIAN_RSS_MIB="
    f"{rust['rss_mib_median']:.2f}"
)

print(
    f"GOOSE_SPEEDUP_VS_RUST_MEDIAN="
    f"{goose_speedup:.3f}x"
)

print(
    f"GOOSE_RSS_RATIO_VS_RUST_MEDIAN="
    f"{goose_rss_ratio:.3f}x"
)

print()
print(f"CSV={CSV_PATH}")
print(f"SUMMARY={SUMMARY_PATH}")
print(f"ENVIRONMENT={ENV_PATH}")

print()
print("FAIR_BENCHMARK_COMPLETE=GREEN")
