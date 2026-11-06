#!/usr/bin/env python3

import hashlib
import json
import os
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GOOSE = ROOT / "build/gander-windowed"
RUST = ROOT / "target/release/gander_windowed_bench"

SEEDS = int(os.environ.get("GANDER_FUZZ_SEEDS", "50"))
MAX_EVENT_BYTES = 65_536


def run_goose(data):
    p = subprocess.run([str(GOOSE)], input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError(f"Goose rc={p.returncode}\n" + p.stderr.decode(errors="replace"))
    return p.stdout, p.stderr


def split_rust_reference(output):
    data, diagnostics = [], []
    for raw in output.splitlines(keepends=True):
        (data if raw.startswith(b"{") else diagnostics).append(raw)
    return b"".join(data), b"".join(diagnostics)


def run_rust(data):
    p = subprocess.run([str(RUST), "--emit"], input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError(f"Rust rc={p.returncode}\n" + p.stderr.decode(errors="replace"))
    return split_rust_reference(p.stdout)


def enc(obj):
    return (
        json.dumps(
            obj,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
        + b"\n"
    )


def make_event(
    trace,
    event_id,
    ts,
    seq,
    key,
    value,
    source,
):
    return {
        "trace_id": trace,
        "event_id": event_id,
        "ts": ts,
        "seq": seq,
        "key": key,
        "value": value,
        "source": source,
    }


def random_stream(seed):
    r = random.Random(seed)

    # Two seeds deliberately cross the 65,536-record window boundary.
    if seed in (0, 1):
        physical_records = 70_000
    else:
        physical_records = r.randint(500, 4_000)

    traces = [f"t{i}" for i in range(r.randint(4, 40))]
    keys = [
        "status",
        "phase",
        "owner",
        "result",
        "mode",
        "step",
    ]

    sources = [
        "agent",
        "tool",
        "worker",
        "service",
        "test",
    ]

    output = []
    previous_valid_lines = []

    logical_id = 0

    # Track rough latest timestamp per state only to generate meaningful
    # stale/newer mixtures. This is generator state, not an oracle.
    state_clock = {}

    for physical_i in range(physical_records):

        choice = r.random()

        # --------------------------------------------------------
        # Exact duplicate.
        # --------------------------------------------------------
        if previous_valid_lines and choice < 0.10:
            output.append(r.choice(previous_valid_lines))
            continue

        # --------------------------------------------------------
        # Malformed records.
        # --------------------------------------------------------
        if choice < 0.125:
            malformed = r.choice([
                b'{"trace_id":"broken"\n',
                b'not-json\n',
                b'{"trace_id":1}\n',
                b'[]\n',
                b'{"trace_id":"x","event_id":"y"}\n',
            ])

            output.append(malformed)
            continue

        # --------------------------------------------------------
        # Oversized records.
        # --------------------------------------------------------
        if choice < 0.13:
            extra = r.randint(1, 512)

            output.append(
                b"x" * (MAX_EVENT_BYTES + extra)
                + b"\n"
            )
            continue

        trace = r.choice(traces)
        key = r.choice(keys)

        state_key = (trace, key)

        current = state_clock.get(state_key)

        event_id = f"s{seed}-e{logical_id}"
        logical_id += 1

        if current is None:
            ts = r.randint(0, 10_000)
            seq = r.randint(0, 100)

        else:
            mode = r.random()

            if mode < 0.20:
                # Older timestamp => stale.
                ts = current[0] - r.randint(1, 20)
                seq = current[1] + r.randint(0, 20)

            elif mode < 0.35:
                # Same timestamp, lower/equal sequence => stale/tie.
                ts = current[0]
                seq = max(
                    0,
                    current[1] - r.randint(0, 3),
                )

            else:
                # Newer.
                ts = current[0] + r.randint(0, 20)

                if ts == current[0]:
                    seq = current[1] + r.randint(1, 5)
                else:
                    seq = r.randint(0, 200)

        value = f"value-{seed}-{logical_id}-{r.randint(0, 9999)}"

        event = make_event(
            trace=trace,
            event_id=event_id,
            ts=ts,
            seq=seq,
            key=key,
            value=value,
            source=r.choice(sources),
        )

        # Occasionally hit exact allowed field limits.
        if r.random() < 0.002:
            event["trace_id"] = "t" * 64
            event["event_id"] = (
                "e" * 50
                + f"{logical_id:014d}"[-14:]
            )
            event["key"] = "k" * 64
            event["value"] = "v" * 256
            event["source"] = "s" * 64

        # Occasionally produce a semantically invalid field length.
        if r.random() < 0.002:
            event["value"] = "z" * 257

        # Occasionally produce an empty required identifier.
        if r.random() < 0.002:
            event[r.choice(["trace_id", "event_id", "key", "source"])] = ""

        raw = enc(event)

        output.append(raw)

        # Only syntactically valid lines are duplicate candidates.
        previous_valid_lines.append(raw)

        # Keep memory bounded in the Python generator itself.
        if len(previous_valid_lines) > 2_000:
            del previous_valid_lines[:1_000]

        # Update approximate generator clock only for field-valid events.
        if (
            len(event["trace_id"]) <= 64
            and len(event["event_id"]) <= 64
            and len(event["key"]) <= 64
            and len(event["value"]) <= 256
            and len(event["source"]) <= 64
        ):
            old = state_clock.get(
                (event["trace_id"], event["key"])
            )

            if old is None or (
                event["ts"],
                event["seq"],
            ) > old:
                state_clock[
                    (event["trace_id"], event["key"])
                ] = (
                    event["ts"],
                    event["seq"],
                )

    data = b"".join(output)

    # Exercise valid or invalid final record without newline.
    if data.endswith(b"\n") and r.random() < 0.50:
        data = data[:-1]

    return data


def sha(data):
    return hashlib.sha256(data).hexdigest()


failures = []

print(
    f"seeds={SEEDS} "
    f"cross_window_seeds=2"
)

for seed in range(SEEDS):

    data = random_stream(seed)

    try:
        goose_stdout, goose_stderr = run_goose(data)
        rust_stdout, rust_stderr = run_rust(data)

    except Exception as exc:
        print(f"seed={seed:02d} PROCESS=RED")
        print(exc)
        failures.append((seed, "process failure"))
        continue

    if goose_stdout != rust_stdout or goose_stderr != rust_stderr:
        print(
            f"seed={seed:02d} "
            f"bytes={len(data)} "
            "DIFF=RED"
        )

        print(
            "goose_sha256=",
            sha(goose_stdout + b"\0" + goose_stderr),
        )

        print(
            "rust_sha256=",
            sha(rust_stdout + b"\0" + rust_stderr),
        )

        failure_input = Path(
            f"/tmp/gander-diff-failure-{seed}.ndjson"
        )

        failure_input.write_bytes(data)

        Path(
            f"/tmp/gander-diff-goose-{seed}.out"
        ).write_bytes(goose_stdout + b"\n--- STDERR ---\n" + goose_stderr)

        Path(
            f"/tmp/gander-diff-rust-{seed}.out"
        ).write_bytes(rust_stdout + b"\n--- STDERR ---\n" + rust_stderr)

        print(
            "failure_input=",
            failure_input,
        )

        failures.append(
            (seed, "byte mismatch")
        )

        # Continue, so one mismatch doesn't hide others.
        continue

    # For several seeds, also verify repeated Goose determinism.
    deterministic = True

    if seed < 5:
        goose_second = run_goose(data)

        deterministic = (
            goose_second == (goose_stdout, goose_stderr)
        )

        if not deterministic:
            failures.append(
                (seed, "Goose nondeterminism")
            )

    print(
        f"seed={seed:02d} "
        f"input_bytes={len(data)} "
        f"output_sha256={sha(goose_stdout + b'\0' + goose_stderr)[:16]} "
        f"eq=GREEN "
        f"determinism="
        f"{'GREEN' if deterministic else 'RED'}"
    )


print()
print("===== RANDOMIZED DIFFERENTIAL SUMMARY =====")

print(f"seeds_tested={SEEDS}")
print(f"failure_count={len(failures)}")

if failures:

    for seed, reason in failures:
        print(
            f"FAIL seed={seed}: {reason}"
        )

    print(
        "GANDER_RANDOM_DIFFERENTIAL_GATE=RED"
    )

    sys.exit(1)

print(
    "GANDER_RANDOM_DIFFERENTIAL_GATE=GREEN"
)
