# Contributing

Contributions are welcome.

Before opening a pull request:

```bash
make verify GOOSE=/path/to/goose
cargo fmt --all -- --check
cargo clippy --all-targets --all-features -- -D warnings
```

Changes to reduction semantics should include an explicit contract update,
an adversarial regression test, and Goose/Rust differential evidence.

Performance claims should include reproducible methodology and should be
reported even when they do not favor Goose.
