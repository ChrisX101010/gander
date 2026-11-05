use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashSet};
use std::io::{self, Read};

const MAX_EVENT_BYTES: usize = 65_536;

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Event {
    trace_id: String,
    event_id: String,
    ts: i64,
    seq: i64,
    key: String,
    value: String,
    source: String,
}

impl Event {
    fn valid(&self) -> bool {
        !self.trace_id.is_empty()
            && self.trace_id.len() <= 64
            && !self.event_id.is_empty()
            && self.event_id.len() <= 64
            && !self.key.is_empty()
            && self.key.len() <= 64
            && self.value.len() <= 256
            && !self.source.is_empty()
            && self.source.len() <= 64
    }
}

fn newer(a: &Event, b: &Event) -> bool {
    a.ts > b.ts || (a.ts == b.ts && a.seq > b.seq)
}

#[derive(Default)]
struct Engine {
    seen: HashSet<String>,
    states: BTreeMap<(String, String), Event>,

    accepted: usize,
    rejected: usize,
    oversized: usize,
    duplicates: usize,
    stale: usize,
    superseded: usize,
    peak_line_bytes: usize,
}

impl Engine {
    fn process_line(&mut self, line: &[u8]) {
        let event: Event = match serde_json::from_slice(line) {
            Ok(e) => e,
            Err(_) => {
                self.rejected += 1;
                return;
            }
        };

        if !event.valid() {
            self.rejected += 1;
            return;
        }

        self.accepted += 1;

        if !self.seen.insert(event.event_id.clone()) {
            self.duplicates += 1;
            return;
        }

        let state_key = (event.trace_id.clone(), event.key.clone());

        match self.states.get(&state_key) {
            None => {
                self.states.insert(state_key, event);
            }

            Some(current) if newer(&event, current) => {
                self.states.insert(state_key, event);
                self.superseded += 1;
            }

            Some(_) => {
                self.stale += 1;
            }
        }
    }
}

fn main() -> io::Result<()> {
    let stdin = io::stdin();
    let mut input = stdin.lock();

    let mut engine = Engine::default();

    let mut chunk = [0u8; 4096];
    let mut line = Vec::<u8>::with_capacity(MAX_EVENT_BYTES);
    let mut dropping = false;

    loop {
        let n = input.read(&mut chunk)?;

        if n == 0 {
            break;
        }

        for &c in &chunk[..n] {
            if c == b'\n' {
                if dropping {
                    engine.rejected += 1;
                    engine.oversized += 1;
                    dropping = false;
                    line.clear();
                } else if !line.is_empty() {
                    engine.process_line(&line);
                    line.clear();
                }
            } else if dropping {
                // Discard oversized record until newline.
            } else if line.len() < MAX_EVENT_BYTES {
                line.push(c);

                if line.len() > engine.peak_line_bytes {
                    engine.peak_line_bytes = line.len();
                }
            } else {
                // This byte would be byte 65,537.
                dropping = true;
                line.clear();
            }
        }
    }

    if dropping {
        engine.rejected += 1;
        engine.oversized += 1;
    } else if !line.is_empty() {
        engine.process_line(&line);
    }

    println!(
        "accepted={} rejected={} oversized={} unique={} duplicates={} stale={} superseded={} final={} peak_line_bytes={}",
        engine.accepted,
        engine.rejected,
        engine.oversized,
        engine.seen.len(),
        engine.duplicates,
        engine.stale,
        engine.superseded,
        engine.states.len(),
        engine.peak_line_bytes
    );

    for event in engine.states.values() {
        println!("{}", serde_json::to_string(event).unwrap());
    }

    Ok(())
}
