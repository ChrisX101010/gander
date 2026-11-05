use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::env;
use std::io::{self, Read, Write};

const MAX_EVENT_BYTES: usize = 65_536;
const WINDOW_RECORD_LIMIT: usize = 65_536;
const READ_CHUNK: usize = 4_096;

#[derive(Clone, Debug, Deserialize, Serialize)]
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
        self.trace_id.len() <= 64
            && self.event_id.len() <= 64
            && self.key.len() <= 64
            && self.value.len() <= 256
            && self.source.len() <= 64
    }
}

#[derive(Default)]
struct WindowCounters {
    records: usize,
    accepted: u64,
    rejected: u64,
    oversized: u64,
    duplicates: u64,
    stale: u64,
    superseded: u64,
    peak_line_bytes: usize,
}

#[derive(Default)]
struct TotalCounters {
    windows: u64,
    records: u64,
    accepted: u64,
    rejected: u64,
    oversized: u64,
    duplicates: u64,
    stale: u64,
    superseded: u64,
}

struct Engine {
    seen: HashSet<String>,
    states: HashMap<(String, String), Event>,

    window_id: u64,
    window: WindowCounters,
    total: TotalCounters,

    emit_snapshots: bool,
}

impl Engine {
    fn new(emit_snapshots: bool) -> Self {
        Self {
            seen: HashSet::with_capacity(WINDOW_RECORD_LIMIT),
            states: HashMap::with_capacity(WINDOW_RECORD_LIMIT),

            window_id: 0,
            window: WindowCounters::default(),
            total: TotalCounters::default(),

            emit_snapshots,
        }
    }

    fn process_line(&mut self, bytes: &[u8]) {
        let event = match serde_json::from_slice::<Event>(bytes) {
            Ok(e) if e.valid() => e,
            _ => {
                self.window.rejected += 1;
                self.total.rejected += 1;
                return;
            }
        };

        self.window.accepted += 1;
        self.total.accepted += 1;

        if !self.seen.insert(event.event_id.clone()) {
            self.window.duplicates += 1;
            self.total.duplicates += 1;
            return;
        }

        let state_key = (event.trace_id.clone(), event.key.clone());

        match self.states.get(&state_key) {
            None => {
                self.states.insert(state_key, event);
            }

            Some(current) => {
                let newer =
                    (event.ts, event.seq) > (current.ts, current.seq);

                if newer {
                    self.states.insert(state_key, event);

                    self.window.superseded += 1;
                    self.total.superseded += 1;
                } else {
                    self.window.stale += 1;
                    self.total.stale += 1;
                }
            }
        }
    }

    fn reject_oversized(&mut self) {
        self.window.rejected += 1;
        self.total.rejected += 1;

        self.window.oversized += 1;
        self.total.oversized += 1;
    }

    fn finish_record<W: Write>(&mut self, out: &mut W) -> io::Result<()> {
        self.window.records += 1;
        self.total.records += 1;

        if self.window.records >= WINDOW_RECORD_LIMIT {
            self.flush_window(out)?;
        }

        Ok(())
    }

    fn flush_window<W: Write>(&mut self, out: &mut W) -> io::Result<()> {
        if self.window.records == 0 {
            return Ok(());
        }

        // Deliberately materialize and sort the complete snapshot.
        // Goose benchmark mode performs the same reduction + sorting work
        // even though payload output is suppressed.
        let mut final_events: Vec<Event> =
            self.states.values().cloned().collect();

        final_events.sort_by(|a, b| {
            a.trace_id
                .cmp(&b.trace_id)
                .then_with(|| a.key.cmp(&b.key))
        });

        writeln!(
            out,
            "window={} records={} accepted={} rejected={} oversized={} \
unique={} duplicates={} stale={} superseded={} final={} peak_line_bytes={}",
            self.window_id,
            self.window.records,
            self.window.accepted,
            self.window.rejected,
            self.window.oversized,
            self.seen.len(),
            self.window.duplicates,
            self.window.stale,
            self.window.superseded,
            final_events.len(),
            self.window.peak_line_bytes,
        )?;

        if self.emit_snapshots {
            for event in &final_events {
                serde_json::to_writer(&mut *out, event)?;
                writeln!(out)?;
            }
        }

        self.total.windows += 1;
        self.window_id += 1;

        self.seen.clear();
        self.states.clear();

        self.window = WindowCounters::default();

        Ok(())
    }

    fn finish<W: Write>(&mut self, out: &mut W) -> io::Result<()> {
        self.flush_window(out)?;

        writeln!(
            out,
            "total_windows={} total_records={} total_accepted={} \
total_rejected={} total_oversized={} total_duplicates={} \
total_stale={} total_superseded={}",
            self.total.windows,
            self.total.records,
            self.total.accepted,
            self.total.rejected,
            self.total.oversized,
            self.total.duplicates,
            self.total.stale,
            self.total.superseded,
        )
    }
}

fn main() -> io::Result<()> {
    let emit_snapshots = env::args().any(|a| a == "--emit");

    let stdin = io::stdin();
    let stdout = io::stdout();

    let mut input = stdin.lock();
    let mut output = io::BufWriter::new(stdout.lock());

    let mut engine = Engine::new(emit_snapshots);

    let mut read_buf = [0u8; READ_CHUNK];

    let mut line = Vec::<u8>::with_capacity(MAX_EVENT_BYTES);
    let mut dropping = false;

    loop {
        let n = input.read(&mut read_buf)?;

        if n == 0 {
            break;
        }

        for &byte in &read_buf[..n] {
            if byte == b'\n' {
                if dropping {
                    engine.reject_oversized();

                    dropping = false;
                    line.clear();

                    engine.finish_record(&mut output)?;

                } else if !line.is_empty() {
                    engine.process_line(&line);
                    line.clear();

                    engine.finish_record(&mut output)?;
                }

            } else if dropping {
                // Discard remainder of oversized record.

            } else if line.len() < MAX_EVENT_BYTES {
                line.push(byte);

                if line.len() > engine.window.peak_line_bytes {
                    engine.window.peak_line_bytes = line.len();
                }

            } else {
                dropping = true;
                line.clear();
            }
        }
    }

    // EOF may terminate the final record without '\n'.
    if dropping {
        engine.reject_oversized();
        engine.finish_record(&mut output)?;

    } else if !line.is_empty() {
        engine.process_line(&line);
        engine.finish_record(&mut output)?;
    }

    engine.finish(&mut output)?;
    output.flush()
}
