#!/usr/bin/env python3

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GOOSE = ROOT / "build/gander-windowed"
RUST = ROOT / "target/release/gander_windowed_bench"

MAX_EVENT_BYTES = 65_536
WINDOW_RECORD_LIMIT = 65_536


def event(
    trace="t",
    eid="e",
    ts=1,
    seq=1,
    key="status",
    value="v",
    source="test",
):
    return {
        "trace_id": trace,
        "event_id": eid,
        "ts": ts,
        "seq": seq,
        "key": key,
        "value": value,
        "source": source,
    }


def line(e):
    return (
        json.dumps(e, separators=(",", ":")).encode()
        + b"\n"
    )


def run(binary, data, rust=False):
    cmd = [str(binary)]

    if rust:
        cmd.append("--emit")

    p = subprocess.run(
        cmd,
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if p.returncode != 0:
        print("PROCESS_FAILURE")
        print("cmd=", cmd)
        print("rc=", p.returncode)
        print(p.stderr.decode(errors="replace"))
        sys.exit(1)

    return p.stdout


def parse(output):
    text = output.decode()

    windows = []
    events = []
    total = None

    for raw in text.splitlines():

        if raw.startswith("window="):
            values = {}

            for item in raw.split():
                if "=" in item:
                    k, v = item.split("=", 1)
                    values[k] = int(v)

            windows.append(values)

        elif raw.startswith("{"):
            events.append(json.loads(raw))

        elif raw.startswith("total_windows="):
            values = {}

            for item in raw.split():
                if "=" in item:
                    k, v = item.split("=", 1)
                    values[k] = int(v)

            total = values

    return windows, events, total


def sha(data):
    return hashlib.sha256(data).hexdigest()


failures = []


def check(name, data, validator=None):

    goose = run(GOOSE, data)
    rust = run(RUST, data, rust=True)

    equal = goose == rust

    if not equal:
        failures.append(f"{name}: Goose/Rust output mismatch")
        print(f"{name}_BYTE_EQ=RED")
        return

    print(f"{name}_BYTE_EQ=GREEN")

    if validator is not None:
        try:
            validator(*parse(goose))
            print(f"{name}_SEMANTICS=GREEN")
        except AssertionError as exc:
            failures.append(f"{name}: {exc}")
            print(f"{name}_SEMANTICS=RED: {exc}")

    return goose


# ------------------------------------------------------------
# 1. Empty stream
# ------------------------------------------------------------

def validate_empty(windows, events, total):
    assert windows == [], windows
    assert events == [], events
    assert total["total_windows"] == 0, total
    assert total["total_records"] == 0, total


check(
    "EMPTY_INPUT",
    b"",
    validate_empty,
)


# ------------------------------------------------------------
# 2. (ts, seq) ordering
# ------------------------------------------------------------

ordering = b"".join([
    line(event(eid="e1", ts=100, seq=1, value="first")),
    line(event(eid="e2", ts=100, seq=2, value="seq-wins")),
    line(event(eid="e3", ts=99, seq=999, value="older-ts")),
    line(event(eid="e4", ts=100, seq=1, value="older-seq")),
])


def validate_ordering(windows, events, total):
    assert len(windows) == 1
    assert windows[0]["accepted"] == 4
    assert windows[0]["unique"] == 4
    assert windows[0]["superseded"] == 1
    assert windows[0]["stale"] == 2
    assert windows[0]["final"] == 1

    assert len(events) == 1
    assert events[0]["event_id"] == "e2"
    assert events[0]["value"] == "seq-wins"

    assert total["total_records"] == 4


check(
    "TS_SEQ_ORDERING",
    ordering,
    validate_ordering,
)


# ------------------------------------------------------------
# 3. Equal (ts, seq): first winner remains
# ------------------------------------------------------------

tie = b"".join([
    line(event(
        eid="tie1",
        ts=500,
        seq=7,
        value="first",
    )),
    line(event(
        eid="tie2",
        ts=500,
        seq=7,
        value="second",
    )),
])


def validate_tie(windows, events, total):
    assert windows[0]["stale"] == 1
    assert windows[0]["superseded"] == 0
    assert len(events) == 1
    assert events[0]["event_id"] == "tie1"


check(
    "EXACT_ORDER_TIE",
    tie,
    validate_tie,
)


# ------------------------------------------------------------
# 4. Exact duplicate inside one window
# ------------------------------------------------------------

dup = event(
    eid="duplicate",
    ts=100,
    seq=1,
    value="original",
)

duplicate_data = line(dup) + line(dup)


def validate_duplicate(windows, events, total):
    assert windows[0]["accepted"] == 2
    assert windows[0]["unique"] == 1
    assert windows[0]["duplicates"] == 1
    assert windows[0]["final"] == 1
    assert len(events) == 1


check(
    "INTRA_WINDOW_DUPLICATE",
    duplicate_data,
    validate_duplicate,
)


# ------------------------------------------------------------
# 5. Same event_id across a window boundary
#
# Dedupe is deliberately window-local.
# ------------------------------------------------------------

parts = []

parts.append(line(event(
    eid="shared",
    ts=1,
    seq=1,
    value="window-zero",
)))

for i in range(1, WINDOW_RECORD_LIMIT):
    parts.append(line(event(
        eid=f"fill{i}",
        ts=i + 1,
        seq=i + 1,
        value=f"v{i}",
    )))

parts.append(line(event(
    eid="shared",
    ts=WINDOW_RECORD_LIMIT + 1,
    seq=WINDOW_RECORD_LIMIT + 1,
    value="window-one",
)))

cross_window = b"".join(parts)


def validate_cross_window(windows, events, total):
    assert len(windows) == 2

    assert windows[0]["records"] == 65536
    assert windows[0]["duplicates"] == 0

    assert windows[1]["records"] == 1
    assert windows[1]["unique"] == 1
    assert windows[1]["duplicates"] == 0

    assert events[-1]["event_id"] == "shared"
    assert events[-1]["value"] == "window-one"

    assert total["total_records"] == 65537


check(
    "CROSS_WINDOW_EVENT_ID",
    cross_window,
    validate_cross_window,
)


# ------------------------------------------------------------
# 6. Exact field limits + one byte over limit
# ------------------------------------------------------------

valid_max = event(
    trace="t" * 64,
    eid="e" * 64,
    ts=1,
    seq=1,
    key="k" * 64,
    value="v" * 256,
    source="s" * 64,
)

invalid_value = event(
    eid="too-long",
    ts=2,
    seq=2,
    value="x" * 257,
)

limits = line(valid_max) + line(invalid_value)


def validate_limits(windows, events, total):
    assert windows[0]["records"] == 2
    assert windows[0]["accepted"] == 1
    assert windows[0]["rejected"] == 1
    assert windows[0]["final"] == 1

    assert len(events[0]["trace_id"]) == 64
    assert len(events[0]["event_id"]) == 64
    assert len(events[0]["key"]) == 64
    assert len(events[0]["value"]) == 256
    assert len(events[0]["source"]) == 64


check(
    "FIELD_LIMITS",
    limits,
    validate_limits,
)


# ------------------------------------------------------------
# 7. Malformed and incomplete JSON
# ------------------------------------------------------------

malformed = (
    b'{"trace_id":"broken"\n'
    + b'not-json\n'
    + line(event(eid="valid-after-bad"))
)


def validate_malformed(windows, events, total):
    assert windows[0]["records"] == 3
    assert windows[0]["accepted"] == 1
    assert windows[0]["rejected"] == 2
    assert len(events) == 1
    assert events[0]["event_id"] == "valid-after-bad"


check(
    "MALFORMED_RECOVERY",
    malformed,
    validate_malformed,
)


# ------------------------------------------------------------
# 8. Oversized record at EOF without newline
# ------------------------------------------------------------

oversized_eof = (
    line(event(eid="before-oversize"))
    + (b"x" * (MAX_EVENT_BYTES + 1))
)


def validate_oversized(windows, events, total):
    assert windows[0]["records"] == 2
    assert windows[0]["accepted"] == 1
    assert windows[0]["rejected"] == 1
    assert windows[0]["oversized"] == 1

    assert total["total_oversized"] == 1
    assert len(events) == 1


check(
    "OVERSIZED_EOF",
    oversized_eof,
    validate_oversized,
)


# ------------------------------------------------------------
# 9. Valid final record without newline
# ------------------------------------------------------------

no_newline = line(
    event(eid="first", ts=1)
) + line(
    event(eid="second", ts=2)
).rstrip(b"\n")


def validate_no_newline(windows, events, total):
    assert windows[0]["records"] == 2
    assert windows[0]["accepted"] == 2
    assert events[-1]["event_id"] == "second"
    assert total["total_records"] == 2


check(
    "EOF_WITHOUT_NEWLINE",
    no_newline,
    validate_no_newline,
)


# ------------------------------------------------------------
# 10. High-cardinality live state
# ------------------------------------------------------------

high_cardinality = b"".join(
    line(event(
        trace=f"t{i}",
        eid=f"e{i}",
        ts=i,
        seq=i,
        key="state",
        value=f"v{i}",
    ))
    for i in range(WINDOW_RECORD_LIMIT)
)


def validate_high_cardinality(windows, events, total):
    assert len(windows) == 1
    assert windows[0]["records"] == WINDOW_RECORD_LIMIT
    assert windows[0]["unique"] == WINDOW_RECORD_LIMIT
    assert windows[0]["final"] == WINDOW_RECORD_LIMIT
    assert len(events) == WINDOW_RECORD_LIMIT


high_out = check(
    "HIGH_CARDINALITY_65536",
    high_cardinality,
    validate_high_cardinality,
)


# ------------------------------------------------------------
# 11. Determinism
# ------------------------------------------------------------

if high_out is not None:

    hashes = []

    for i in range(3):
        result = run(GOOSE, high_cardinality)
        hashes.append(sha(result))

    print("DETERMINISM_HASHES=" + ",".join(hashes))

    if len(set(hashes)) == 1:
        print("REPEATED_RUN_DETERMINISM=GREEN")
    else:
        failures.append(
            "Repeated Goose runs were not byte deterministic"
        )
        print("REPEATED_RUN_DETERMINISM=RED")


# ------------------------------------------------------------
# FINAL
# ------------------------------------------------------------

print()
print("===== ADVERSARIAL SUMMARY =====")

if failures:
    for failure in failures:
        print("FAIL:", failure)

    print(f"FAILURE_COUNT={len(failures)}")
    print("GANDER_ADVERSARIAL_GATE=RED")
    sys.exit(1)

print("FAILURE_COUNT=0")
print("GANDER_ADVERSARIAL_GATE=GREEN")
