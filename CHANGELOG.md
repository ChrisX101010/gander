# Changelog

## [Unreleased]

### Changed
- stdout is now NDJSON data only; counters moved to stderr.
- added `--quiet`, `--strict`, `--help`, and `--version`.
- duplicate required JSON fields are rejected.
- added production CLI gate and a CI/CD workflow-state example.
- added Goose branding and production-readiness documentation.

## [1.0.0-rc1] - 2026-11-05

First public release candidate with bounded-window reduction, independent Rust verification, adversarial/randomized differential tests, reproducible 1M benchmarks, and 10M memory-plateau evidence.
