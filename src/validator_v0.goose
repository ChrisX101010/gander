import std;
import os;
import json;

let MAX_EVENT_BYTES = 65536;

fn valid_event(text: u8[:]) -> bool {
    var r = json::reader(text);
    var scratch: u8[>..] = [];

    var have_trace = false;
    var have_event = false;
    var have_ts = false;
    var have_seq = false;
    var have_key = false;
    var have_value = false;
    var have_source = false;

    json::each_member(r) { field =>
        if field == "trace_id" {
            let value = json::read_string(r, scratch);
            have_trace = value.len > 0;
        } else if field == "event_id" {
            let value = json::read_string(r, scratch);
            have_event = value.len > 0;
        } else if field == "ts" {
            json::read_int(r);
            have_ts = true;
        } else if field == "seq" {
            json::read_int(r);
            have_seq = true;
        } else if field == "key" {
            let value = json::read_string(r, scratch);
            have_key = value.len > 0;
        } else if field == "value" {
            json::read_string(r, scratch);
            have_value = true;
        } else if field == "source" {
            let value = json::read_string(r, scratch);
            have_source = value.len > 0;
        } else {
            json::skip(r);
        }
    };

    if !json::finish(r) {
        return false;
    }

    return have_trace &&
           have_event &&
           have_ts &&
           have_seq &&
           have_key &&
           have_value &&
           have_source;
}

fn main() {
    var accepted = 0;
    var rejected = 0;
    var line: u8[>..] = [];

    while read_line(line) {
        if line.len > MAX_EVENT_BYTES {
            rejected++;
        } else if line.len > 0 {
            if valid_event(line) {
                accepted++;
            } else {
                rejected++;
            }
        }

        line.clear();
    }

    print("accepted=", accepted, " rejected=", rejected);
}
