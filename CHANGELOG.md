# Changelog

## [Unreleased]

### Added

- Added a pinned, local LangGraph cancellation negative control showing that consumer-observed custom stream output is not checkpoint state; the result remains `OBSERVED` / `NOT_PROVEN` / `UNKNOWN` and does not claim to reproduce the hosted Platform/API report.

### Renamed

- Renamed the public project from **Agent Session Bridge** to **Trajectory Fidelity Bridge (TFB)** on 2026-09-28 after identifying an older, unrelated public project that already used the former name. The projects are unaffiliated.
- The previous PyPI distribution and the `agent-session` command remain available for compatibility; new releases use the renamed distribution and also provide `tfb`.

## [0.4.2] - 2026-10-21

### Fixed

- Removed the obsolete `DTZ001` noqa suppression that caused Ruff's `RUF100` check to fail.

## [0.4.1] - 2026-09-28

### Changed

- Published this release as `atomicdjt-trajectory-fidelity-bridge`. The existing `atomicdjt-agent-session-bridge` PyPI project and its 0.4.0 release remain available for users who have not migrated.
- Added the `tfb` command as a shorter alias while retaining `agent-session` for existing scripts and documentation.
- Updated repository links and citation metadata to the renamed GitHub repository.

### Migration

- Existing installations of `atomicdjt-agent-session-bridge==0.4.0` continue to work. New environments should install `atomicdjt-trajectory-fidelity-bridge`.
- See [the PyPI migration guide](docs/PYPI_MIGRATION.md) before switching an existing environment.

This file records user-visible changes in Trajectory Fidelity Bridge releases.

## [0.4.0] - 2026-09-24

### Added

- `agent-session explain`, which renders an ATIF trajectory as a deterministic Markdown account of steps, tool calls, results, provenance, and conversion limits.
- Finer Claude Code fidelity evidence that distinguishes unsupported bookkeeping, potentially content-bearing records, unrecognized records, ignored fields, and duplicate usage records.
- A controlled real Claude Code fixture with synthetic data, pseudonymized identifiers, explicit provenance, and regression coverage.
- A private, local-only sanitizer and review procedure for preparing controlled real-session candidates without publishing raw logs.

### Changed

- Claude Code imports now carry observed model names and token usage into compatible ATIF step fields. Cost remains unavailable and is not inferred.

### Fixed

- The public real-session fixture preserves its source SHA-256 on Windows checkouts by pinning its JSONL line endings.
- Fixture regression tests now detect changed result content and tool-result correlation errors.

### Limitations

- The real-session fixture covers one controlled Windows session from Claude Code 2.1.266 using Read, Bash, Edit, and Write. It does not establish general compatibility across versions, operating systems, session shapes, or tools.
