<div align="center">

<img src="./docs/images/repository-header.svg" alt="TRAJECTORY FIDELITY BRIDGE — portfolio identity banner" width="100%" />

<br />

[**PROJECT PAGE**](https://ai-project-portfolio-portfolio-hub.vercel.app/projects/agent-session-bridge) · [**PYPI**](https://pypi.org/project/atomicdjt-trajectory-fidelity-bridge/) · [**PROFILE**](https://github.com/atomicdjt) · [**ARCHITECTURE**](docs/ARCHITECTURE.md)

</div>

<br />

# Trajectory Fidelity Bridge

[![CI](https://github.com/atomicdjt/trajectory-fidelity-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/atomicdjt/trajectory-fidelity-bridge/actions/workflows/ci.yml)

**Move structured coding-agent history between tools without collapsing it into a prose summary.**

> **Rename note — September 28, 2026:** This project was renamed from **Agent Session Bridge** to **Trajectory Fidelity Bridge** after discovering an older, unrelated public project already using the former name. The projects are unaffiliated. The `agent-session` CLI, `extra.agent_session_bridge` extension namespace, and older PyPI distribution remain available as compatibility identifiers.

**[Canonical project page](https://ai-project-portfolio-portfolio-hub.vercel.app/projects/agent-session-bridge) · [PyPI](https://pypi.org/project/atomicdjt-trajectory-fidelity-bridge/) · [Open issues](https://github.com/atomicdjt/trajectory-fidelity-bridge/issues) · [Architecture](docs/ARCHITECTURE.md)**

Trajectory Fidelity Bridge is an MIT-licensed reference implementation for converting supported coding-agent transcripts into the [Agent Trajectory Interchange Format (ATIF)](https://github.com/harbor-framework/harbor/blob/main/rfcs/0001-trajectory-format.md). It is not a competing interchange standard.

> **Current status:** Claude Code JSONL normalization to ATIF v1.7, heuristic secret redaction, TFB fidelity reporting, and an Antigravity derived-log mapping are implemented. Native Antigravity session rehydration is not supported because Antigravity has no supported historical-session import boundary.
>
> **External validation wanted:** sanitized provider fixtures that expose a normalization failure, disagreements with the fidelity report, evidence about additional documented ingestion boundaries, and reproducible cross-provider transformation cases are especially useful. [Open an issue](https://github.com/atomicdjt/trajectory-fidelity-bridge/issues) with the smallest safe fixture that demonstrates the problem.

![Trajectory Fidelity Bridge quick tour](docs/images/agent-session-bridge-quick-tour.gif)

*Animated architecture tour based on documented behavior; it is not a fabricated live screen recording.*

## What ATIF provides and what TFB adds

ATIF is the portable trajectory layer: ordered system/user/agent steps, structured tool calls, call-correlated observations, agent metadata, metrics, and a namespaced `extra` extension mechanism. TFB converts provider-specific transcript shapes into that public format.

TFB's distinct responsibilities are deliberately narrower:

- provider-specific parsing and normalization;
- best-effort secret redaction before export;
- transformation/fidelity accounting in `extra.agent_session_bridge`;
- target-specific mappings, such as the observed Antigravity derived-log shape; and
- explicit refusal to fabricate native resumable session state.

The current Antigravity reference mapper reports any ATIF system messages it cannot map to the observed derived-log shape; it does not silently invent a target record type.

See [the ATIF mapping](docs/FORMAT.md) and [layered architecture](docs/ARCHITECTURE.md) for exact preserved, transformed, and unsupported semantics.

The reproducible synthetic interoperability corpus, semantic oracle, adversarial verifier, current ATIF v1.8 audit, and cross-converter evidence are documented in [docs/INTEROPERABILITY.md](docs/INTEROPERABILITY.md). A passing corpus check is not independent practitioner validation or proof of universal provider compatibility.

## What works today

| Capability | Status | Notes |
| --- | --- | --- |
| Claude Code JSONL import | ✅ | Parses supported message and tool structures into ATIF v1.7 |
| Portable interchange document | ✅ | Validated by the official `atif` Python models |
| TFB fidelity reporting | ✅ | Namespaced provenance and unsupported/degraded source counts in ATIF `extra` |
| Human-readable session report | ✅ | `agent-session explain` renders an ATIF file as Markdown, with what the conversion could not preserve |
| Heuristic secret redaction | ✅ | Best effort only; output still requires human review |
| Antigravity derived-log mapping | ✅ | Reference payload based on observed `transcript.jsonl` structures |
| Native Antigravity session import | ❌ blocked upstream | No supported API creates or resumes external historical state |

## Quick start

This project is published on PyPI as `atomicdjt-trajectory-fidelity-bridge`. The earlier `atomicdjt-agent-session-bridge` project remains available at 0.4.0 for existing users. The shorter name `agent-session-bridge` belongs to an unrelated project. Python 3.11 or newer is required. See [the migration guide](docs/PYPI_MIGRATION.md) before switching an existing environment.

Install the published package:

```bash
python -m pip install atomicdjt-trajectory-fidelity-bridge
```

To install the current published release explicitly:

```bash
python -m pip install atomicdjt-trajectory-fidelity-bridge==0.4.2
```

For development from source:

```bash
git clone https://github.com/atomicdjt/trajectory-fidelity-bridge.git
cd trajectory-fidelity-bridge
python -m venv .venv
```

Activate the environment, then install the package:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

python -m pip install -e .
```

Normalize a Claude Code transcript to an ATIF document, inspect TFB's source-fidelity report, or generate the Antigravity reference mapping:

```bash
agent-session import --from claude-code --source your_claude_log.jsonl --output trajectory.atif.json --report
agent-session convert --from claude-code --to antigravity your_claude_log.jsonl
agent-session handoff --from claude-code --to antigravity your_claude_log.jsonl
```

`handoff` returns `UnsupportedNativeImport` after producing the reference payload. It does not imply that Antigravity can resume the converted history.

Render the resulting ATIF file as a deterministic Markdown account of the agent's actions, tool calls and results, provenance, and what the conversion could not preserve:

```bash
agent-session explain trajectory.atif.json --output report.md
```

Source-level facts that ATIF does not carry (source hash, converter version, capture time) are shown only if you supply them in an optional `--manifest` JSON file, and are then labelled as unverified. [`fixtures/real-session/`](fixtures/real-session/README.md) is a sanitized ATIF trajectory and manifest from one controlled, real Claude Code session with synthetic content; it demonstrates this path, not general compatibility. See [docs/DEMO_REAL_SESSION.md](docs/DEMO_REAL_SESSION.md) for the private, reproducible procedure that produced it.

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

For the current Claude Code adapter, TFB preserves supported roles, valid ISO-8601 step timestamps, text, tool names, tool arguments, and tool results. It normalizes later Claude `tool_result` blocks into ATIF observations attached to their originating calls. Unsupported source records or blocks are counted in `extra.agent_session_bridge.fidelity`; they are never represented as successfully preserved. ATIF v1.7 has no timestamp on an observation result, so tool-result timestamps are not carried into the output; they are counted as `omitted_tool_result_timestamps` and no time is ever invented ([details](docs/FORMAT.md#timestamp-semantics)).

- Imported history is processed as data. Historical commands are never executed.
- Redaction is heuristic and is not a guarantee; see [what it does and does not cover](docs/SECURITY.md#what-redaction-covers).
- Do not publish a converted transcript without reviewing it for credentials, personal data, private source, or proprietary context.
- TFB does not reverse-engineer or write Antigravity's opaque internal session database.

## Optional observability projection

The observability implementation is an optional downstream projection of ATIF, not a replacement for ATIF, and not original runtime instrumentation. It is a historical structural projection.

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
python -m pip install -e ".[observability]"
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

For implementation details, see [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md). For the evidence model, ecosystem comparison, limitations, and external-review questions, see [Reconstructing Agent Traces After the Fact Without Inventing Runtime Truth](docs/HISTORICAL_OBSERVABILITY_WRITEUP.md).

## Migration from v0.1 ASEF output

v0.2 removes the proprietary ASEF schema. Existing `*.asef.json` files are not ATIF documents and must not be relabeled as such. Re-run the original source transcript through `agent-session import` (or `tfb import`) to produce a validated `*.atif.json` file, then review the TFB fidelity report. Python 3.11 is now the minimum supported version because the official ATIF models require it.

## Releasing

This project is published to PyPI through GitHub Actions and PyPI Trusted Publishing using OpenID Connect (OIDC). The workflow builds the wheel and source distribution and runs `twine check`. For tag-triggered releases, it also verifies that the release tag matches the project version before publishing. A manual `workflow_dispatch` does not perform the tag/version check; it publishes the version currently declared in `pyproject.toml`. No PyPI API token is stored in this repository.

The current package is available at:

https://pypi.org/project/atomicdjt-trajectory-fidelity-bridge/

The previous distribution, `atomicdjt-agent-session-bridge`, remains published at version 0.4.0. It is not deleted or replaced by a stub. Existing installations keep working; migration instructions are in [docs/PYPI_MIGRATION.md](docs/PYPI_MIGRATION.md).

For future releases:

1. Update `project.version` in `pyproject.toml` and any related release metadata.
2. Merge the change into `main`.
3. Create a matching GitHub tag and release from `main`, such as `v0.4.2`.
4. Wait for the `Publish to PyPI` workflow to complete.
5. Verify the new version on PyPI.
6. Test installation in a clean environment.

Before the first release of the new distribution, add a pending PyPI Trusted Publisher for `atomicdjt-trajectory-fidelity-bridge`, owner `atomicdjt`, repository `trajectory-fidelity-bridge`, workflow `publish.yml`, and environment `pypi`. The tag must match the project version exactly. For example, tag `v0.4.2` requires project version `0.4.2`.

## Contributing

Useful contributions include provider transcript fixtures, source adapters, target mappings for documented ingestion boundaries, fidelity-report improvements, and reproducible evidence about real cross-provider transformations. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT License. See [LICENSE](LICENSE).
