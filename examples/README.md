# Examples

## CI/CD workflow state reduction

Gander reduces duplicate, delayed, and superseded workflow events into the
latest deterministic state.

From the repository after `make build`:

```bash
./build/gander \
  < examples/ci-pipeline.ndjson \
  > latest.ndjson \
  2> stats.log
```

Strict validation mode:

```bash
./build/gander --strict \
  < examples/ci-pipeline.ndjson \
  > latest.ndjson
```

The expected machine-readable output is committed as
`ci-pipeline.expected.ndjson`.

After `make install PREFIX="$HOME/.local"`, the same example can be run with
`gander` instead of `./build/gander`.
