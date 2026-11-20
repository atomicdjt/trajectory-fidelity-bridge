<div align="center">

<img src="https://raw.githubusercontent.com/atomicdjt/trajectory-fidelity-bridge/4b1c43bc94a0dcc8f68e8810d06969f97c01956d/docs/images/repository-header.svg" alt="Trajectory Fidelity Bridge" width="100%" />

<br />

[**PROJECT PAGE**](https://ai-project-portfolio-portfolio-hub.vercel.app/projects/agent-session-bridge) · [**PYPI**](https://pypi.org/project/atomicdjt-trajectory-fidelity-bridge/) · [**PROFILE**](https://github.com/atomicdjt) · [**ARCHITECTURE**](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/docs/ARCHITECTURE.md)

</div>

<br />

# Trajectory Fidelity Bridge

[![CI](https://github.com/atomicdjt/trajectory-fidelity-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/atomicdjt/trajectory-fidelity-bridge/actions/workflows/ci.yml)

**Move structured coding-agent history between tools without collapsing it into a prose summary.**

Trajectory Fidelity Bridge (**TFB**) converts supported coding-agent transcripts into the **Agent Trajectory Interchange Format (ATIF)**, a shared format for conversations, tool calls, and results. Its fidelity report counts supported and omitted material so you can inspect what survived conversion.

**[Canonical project page](https://ai-project-portfolio-portfolio-hub.vercel.app/projects/agent-session-bridge) · [PyPI](https://pypi.org/project/atomicdjt-trajectory-fidelity-bridge/) · [Open issues](https://github.com/atomicdjt/trajectory-fidelity-bridge/issues) · [Architecture](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/docs/ARCHITECTURE.md)**

Trajectory Fidelity Bridge is an MIT-licensed reference implementation for converting supported coding-agent transcripts into the [Agent Trajectory Interchange Format (ATIF)](https://github.com/harbor-framework/harbor/blob/main/rfcs/0001-trajectory-format.md). It is not a competing interchange standard.

> **Current status:** Claude Code transcripts and a bounded subset of Codex session rollouts can be normalized to ATIF v1.7. TFB includes heuristic secret redaction, fidelity reporting, and an Antigravity derived-log mapping. It cannot import its generated trajectories into native Antigravity sessions.
>
> **External validation wanted:** sanitized provider fixtures that expose a normalization failure, disagreements with the fidelity report, evidence about additional documented ingestion boundaries, and reproducible cross-provider transformation cases are especially useful. [Open an issue](https://github.com/atomicdjt/trajectory-fidelity-bridge/issues) with the smallest safe fixture that demonstrates the problem.

## What ATIF provides and what TFB adds

ATIF is the portable trajectory layer: ordered system/user/agent steps, structured tool calls, call-correlated observations, agent metadata, metrics, and a namespaced `extra` extension mechanism. TFB converts provider-specific transcript shapes into that public format.

TFB's distinct responsibilities are deliberately narrower:

- provider-specific parsing and normalization;
- best-effort secret redaction before export;
- transformation/fidelity accounting in `extra.agent_session_bridge`;
- target-specific mappings, such as the observed Antigravity derived-log shape; and
- explicit refusal to fabricate native resumable session state.

The current Antigravity reference mapper reports any ATIF system messages it cannot map to the observed derived-log shape; it does not silently invent a target record type.

See [the ATIF mapping](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/docs/FORMAT.md) and [layered architecture](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/docs/ARCHITECTURE.md) for exact preserved, transformed, and unsupported semantics.

Non-string Claude record types and message roles are reported as unsupported records, allowing conversion to continue to later valid records. Other malformed fields may still prevent conversion; inspect the fidelity report and output.

The reproducible synthetic interoperability corpus, semantic oracle, adversarial verifier, current ATIF v1.8 audit, and cross-converter evidence are documented in [docs/INTEROPERABILITY.md](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/docs/INTEROPERABILITY.md). A passing corpus check is not independent practitioner validation or proof of universal provider compatibility.

## What works today

| Capability | Status | Notes |
| --- | --- | --- |
| Claude Code JSONL import | ✅ | Parses supported message and tool structures into ATIF v1.7 |
| Codex rollout JSONL import | ✅ bounded | Preserves supported messages and tool/result links; unsupported events are counted |
| Portable interchange document | ✅ | Validated by the official `atif` Python models |
| TFB fidelity reporting | ✅ | Namespaced provenance and unsupported/degraded source counts in ATIF `extra` |
| Human-readable session report | ✅ | `tfb explain` renders an ATIF file as Markdown, with what the conversion could not preserve |
| Heuristic secret redaction | ✅ | Best effort only; output still requires human review |
| Antigravity derived-log mapping | ✅ | Reference payload based on observed `transcript.jsonl` structures |
| Native Antigravity session import | ❌ unsupported | TFB cannot create or resume a native session from its reference payload |

## Quick start

Python 3.11 or newer is required. The package is named `atomicdjt-trajectory-fidelity-bridge` on PyPI, and its primary command is `tfb`.

Install the published package:

```bash
python -m pip install atomicdjt-trajectory-fidelity-bridge
```

Convert a Claude Code JSONL transcript to ATIF, then write a readable report:

```bash
tfb import --from claude-code --source your_claude_log.jsonl --output trajectory.atif.json --report
tfb explain trajectory.atif.json --output report.md
```

To try a safe synthetic fixture from a repository checkout (after installing the package), run:

```bash
tfb import --from claude-code --source fixtures/claude_sample.jsonl --output trajectory.atif.json --report
tfb explain trajectory.atif.json --output report.md
```

For the repository's [synthetic sample](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/fixtures/claude_sample.jsonl), the import command's `--report` produces:

```text
--- TFB Fidelity Report ---
Source records preserved: 4
Tool calls preserved:     1
Observations preserved:   1
Unsupported records:      0
Unsupported blocks:       0
---------------------------
```

These are counts for that fixture, not a guarantee that every part of a transcript survived. The ATIF output contains a more detailed accounting, including omitted timestamps and orphaned results. Review the report and output before sharing; redaction is best effort.

For a Codex recorded session rollout, use `--from codex` instead:

```bash
tfb import --from codex --source rollout.jsonl --output trajectory.atif.json --report
tfb explain trajectory.atif.json --output report.md
```

This accepts a bounded subset of recorded Codex rollout JSONL, not the `codex exec --json` live event stream. See the [supported fields and limitations](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/docs/CODEX_IMPORT.md) and the [synthetic example](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/fixtures/codex_sample.jsonl). The `convert` reference mapping below currently accepts Claude Code only.

To generate an Antigravity-shaped **reference payload** from a Claude Code transcript:

```bash
tfb convert --from claude-code --to antigravity your_claude_log.jsonl
```

This produces a derived log; it does not import or resume a session in Antigravity. The older `tfb handoff` command remains available for compatibility and reports `UnsupportedNativeImport`; it cannot perform a native handoff.

The earlier `agent-session` command is an alias for `tfb`. The `extra.agent_session_bridge` extension key and the older `atomicdjt-agent-session-bridge` distribution are retained for compatibility. The shorter PyPI name `agent-session-bridge` belongs to an unrelated project. See [the migration guide](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/docs/PYPI_MIGRATION.md).

Source-level facts that ATIF does not carry (source hash, converter version, capture time) are shown only if you supply them in an optional `--manifest` JSON file, and are then labelled as unverified. [`fixtures/real-session/`](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/fixtures/real-session/README.md) is a sanitized ATIF trajectory and manifest from one controlled, real Claude Code session with synthetic content; it demonstrates this path, not general compatibility. See [docs/DEMO_REAL_SESSION.md](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/docs/DEMO_REAL_SESSION.md) for the private, reproducible procedure that produced it.

## Architecture

```text
provider transcript
       │
       ▼
source parser and normalizer
       │
       ▼
ATIF trajectory ─────► TFB provenance/fidelity extension
       │
       ├──────────────► redacted portable trajectory
       │
       ▼
target-specific mapper
       │
       ▼
target payload / supported importer, if one exists
```

ATIF makes a trajectory portable; it does not require target runtimes to ingest it as native state. Native resumption remains a target-owned capability, with target-owned validation, persistence, and security constraints.

## Fidelity and security boundaries

For the current Claude Code adapter, TFB preserves supported roles, valid ISO-8601 step timestamps, text, tool names, tool arguments, and tool results. It normalizes later Claude `tool_result` blocks into ATIF observations attached to their originating calls. Unsupported source records or blocks are counted in `extra.agent_session_bridge.fidelity`; they are never represented as successfully preserved. ATIF v1.7 has no timestamp on an observation result, so tool-result timestamps are not carried into the output; they are counted as `omitted_tool_result_timestamps` and no time is ever invented ([details](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/docs/FORMAT.md#timestamp-semantics)).

- Imported history is processed as data. Historical commands are never executed.
- Redaction is heuristic and is not a guarantee; see [what it does and does not cover](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/docs/SECURITY.md#what-redaction-covers).
- Do not publish a converted transcript without reviewing it for credentials, personal data, private source, or proprietary context.
- TFB does not reverse-engineer or write Antigravity's opaque internal session database.

## Optional observability projection

The observability implementation is an optional downstream projection of ATIF, not a replacement for ATIF, and not original runtime instrumentation. It can read an ATIF document produced by another tool, subject to TFB's supported ATIF fields and error-flag conventions. It is a historical structural projection.

```text
provider transcript
        ↓
Trajectory Fidelity Bridge
        ↓
ATIF v1.7
        ↓
historical observability projection
        ↓
OpenTelemetry / OpenInference
        ↓
OTLP
        ↓
Phoenix or another compatible backend
```

To install the optional observability dependencies:

```bash
python -m pip install "atomicdjt-trajectory-fidelity-bridge[observability]"
```

For the local Phoenix example, Phoenix may be installed separately. It is not required for core Trajectory Fidelity Bridge operation:

```bash
python -m pip install arize-phoenix
```

A Claude Code source may also be observed using the existing supported `--from claude-code` path where appropriate.

```bash
tfb observe trajectory.atif.json \
  --from atif \
  --backend phoenix \
  --endpoint http://127.0.0.1:6006/v1/traces
```

### Privacy

- `metadata-only` is the default.
- `redacted-content` exports redacted textual content.
- `full-content` must be explicitly selected and may expose sensitive transcript data. Treat `full-content` carefully.

### Historical timing

As this is a historical structural projection:
- ATIF Step timestamps may be represented as observed timing.
- Root boundaries may be derived from observed Step timestamps.
- Where independent tool completion timing is unavailable from ATIF, the projection does not pretend to have measured runtime duration.

For implementation details, see [docs/OBSERVABILITY.md](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/docs/OBSERVABILITY.md). For the evidence model, ecosystem comparison, limitations, and external-review questions, see [Reconstructing Agent Traces After the Fact Without Inventing Runtime Truth](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/docs/HISTORICAL_OBSERVABILITY_WRITEUP.md).

## Migration from v0.1 ASEF output

v0.2 removes the proprietary ASEF schema. Existing `*.asef.json` files are not ATIF documents and must not be relabeled as such. Re-run the original source transcript through `tfb import` to produce a validated `*.atif.json` file, then review the TFB fidelity report. Python 3.11 is now the minimum supported version because the official ATIF models require it.

## Contributing

Useful contributions include provider transcript fixtures, source adapters, target mappings for documented ingestion boundaries, fidelity-report improvements, and reproducible evidence about real cross-provider transformations. See [CONTRIBUTING.md](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/CONTRIBUTING.md).

## License

MIT License. See [LICENSE](https://github.com/atomicdjt/trajectory-fidelity-bridge/blob/main/LICENSE).
