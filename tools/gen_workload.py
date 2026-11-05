#!/usr/bin/env python3

import json
from pathlib import Path

EVENTS = 1_000_000
TRACES = 5_000
KEYS = ("status", "phase", "owner", "result")
STATE_COUNT = TRACES * len(KEYS)

out_path = Path("fixtures/bench-1m.ndjson")
meta_path = Path("bench/bench-1m.meta")

states = {}

duplicates = 0
stale = 0
superseded = 0
inserted = 0
unique = 0

last_line = None

sources = ("agent", "tool", "service", "worker")

with out_path.open("wb") as f:
    for physical_i in range(EVENTS):

        # Exactly every tenth physical event is an exact duplicate.
        if physical_i % 10 == 9:
            assert last_line is not None
            f.write(last_line)
            duplicates += 1
            continue

        # State placement is based on UNIQUE event number,
        # not physical stream position.
        state_id = unique % STATE_COUNT

        trace_n = state_id // len(KEYS)
        key = KEYS[state_id % len(KEYS)]

        sk = (trace_n, key)
        current = states.get(sk)

        # Unique but deliberately stale event.
        make_stale = current is not None and unique % 7 == 0

        if make_stale:
            ts = max(0, current[0] - 1)
            seq = max(0, current[1] - 1)
            value = f"stale-{unique}"
            stale += 1

        else:
            if current is None:
                ts = 1
                seq = 1
                inserted += 1
            else:
                ts = current[0] + 1
                seq = current[1] + 1
                superseded += 1

            value = f"v{seq}"
            states[sk] = (ts, seq, value)

        event = {
            "trace_id": f"t{trace_n}",
            "event_id": f"e{unique}",
            "ts": ts,
            "seq": seq,
            "key": key,
            "value": value,
            "source": sources[unique % len(sources)],
        }

        last_line = (
            json.dumps(event, separators=(",", ":")) + "\n"
        ).encode()

        f.write(last_line)
        unique += 1

assert unique == 900_000
assert duplicates == 100_000
assert unique + duplicates == EVENTS
assert unique == inserted + superseded + stale
assert len(states) == STATE_COUNT

meta = f"""events={EVENTS}
unique={unique}
duplicates={duplicates}
inserted={inserted}
stale={stale}
superseded={superseded}
final={len(states)}
traces={TRACES}
keys_per_trace={len(KEYS)}
"""

meta_path.write_text(meta)

print(meta, end="")
print(f"bytes={out_path.stat().st_size}")
print("GENERATOR_INVARIANTS=GREEN")
