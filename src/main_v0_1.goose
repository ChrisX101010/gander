import std;
import os;
import json;
import dictionary;

let MAX_EVENT_BYTES = 65536;

struct Event {
    trace_id: u8[..64],
    event_id: u8[..64],
    ts: i64,
    seq: i64,
    key: u8[..64],
    value: u8[..256],
    source: u8[..64],
}

struct StateKey {
    trace_id: u8[..64],
    key: u8[..64],
}

fn hash(k: StateKey) -> u64 {
    return hash_combine(hash(k.trace_id), hash(k.key));
}

fn put64(dst: u8[..64]&, src: const u8[:]) -> bool {
    if src.len > 64 {
        return false;
    }
    dst.append(src);
    return true;
}

fn put256(dst: u8[..256]&, src: const u8[:]) -> bool {
    if src.len > 256 {
        return false;
    }
    dst.append(src);
    return true;
}

fn empty_event() -> Event {
    return Event {
        trace_id: [],
        event_id: [],
        ts: 0,
        seq: 0,
        key: [],
        value: [],
        source: [],
    };
}

fn parse_event(text: const u8[:]) -> Event, bool {
    var r = json::reader(text);
    var scratch: u8[>..] = [];
    var e = empty_event();

    var have_trace = false;
    var have_event = false;
    var have_ts = false;
    var have_seq = false;
    var have_key = false;
    var have_value = false;
    var have_source = false;

    json::each_member(r) { field =>
        if field == "trace_id" {
            let s = json::read_string(r, scratch);
            have_trace = s.len > 0 && put64(e.trace_id, s);

        } else if field == "event_id" {
            let s = json::read_string(r, scratch);
            have_event = s.len > 0 && put64(e.event_id, s);

        } else if field == "ts" {
            e.ts = json::read_int(r);
            have_ts = true;

        } else if field == "seq" {
            e.seq = json::read_int(r);
            have_seq = true;

        } else if field == "key" {
            let s = json::read_string(r, scratch);
            have_key = s.len > 0 && put64(e.key, s);

        } else if field == "value" {
            let s = json::read_string(r, scratch);
            have_value = put256(e.value, s);

        } else if field == "source" {
            let s = json::read_string(r, scratch);
            have_source = s.len > 0 && put64(e.source, s);

        } else {
            json::skip(r);
        }
    };

    if !json::finish(r) {
        return e, false;
    }

    let valid =
        have_trace &&
        have_event &&
        have_ts &&
        have_seq &&
        have_key &&
        have_value &&
        have_source;

    return e, valid;
}

fn newer(a: Event, b: Event) -> bool {
    return a.ts > b.ts ||
           (a.ts == b.ts && a.seq > b.seq);
}

fn emit_event(e: Event) {
    var out: u8[>..] = [];

    out.append("{\"trace_id\":");
    json::format_string(out, e.trace_id);

    out.append(",\"event_id\":");
    json::format_string(out, e.event_id);

    out.append(",\"ts\":");
    format(out, e.ts);

    out.append(",\"seq\":");
    format(out, e.seq);

    out.append(",\"key\":");
    json::format_string(out, e.key);

    out.append(",\"value\":");
    json::format_string(out, e.value);

    out.append(",\"source\":");
    json::format_string(out, e.source);

    out.push('}');

    print(out);
}

fn main() {
    var seen = dictionary<u8[..64], bool> {};
    var states = dictionary<StateKey, Event> {};

    var accepted = 0;
    var rejected = 0;
    var duplicates = 0;
    var stale = 0;
    var superseded = 0;

    var line: u8[>..] = [];

    while read_line(line) {
        if line.len > MAX_EVENT_BYTES {
            rejected++;

        } else if line.len > 0 {
            let e, valid = parse_event(line);

            if !valid {
                rejected++;

            } else {
                accepted++;

                if seen.contains(e.event_id) {
                    duplicates++;

                } else {
                    seen.insert(e.event_id, true);

                    let sk = StateKey {
                        trace_id: e.trace_id,
                        key: e.key,
                    };

                    var exists = false;
                    var replace = false;

                    block {
                        let current = states.get(sk);

                        if current {
                            exists = true;
                            replace = newer(e, current);
                        }
                    }

                    if !exists {
                        states.insert(sk, e);

                    } else if replace {
                        states.insert(sk, e);
                        superseded++;

                    } else {
                        stale++;
                    }
                }
            }
        }

        line.clear();
    }

    var final: Event[>..] = [];

    states.each() { k, value =>
        final.push(value);
    };

    sort(final) { a, b =>
        compare(a.trace_id, b.trace_id) < 0 ||
        (a.trace_id == b.trace_id &&
         compare(a.key, b.key) < 0)
    };

    print(
        "accepted=", accepted,
        " rejected=", rejected,
        " unique=", seen.count,
        " duplicates=", duplicates,
        " stale=", stale,
        " superseded=", superseded,
        " final=", final.len
    );

    for e in final {
        emit_event(e);
    }
}
