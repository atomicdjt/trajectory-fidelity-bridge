# Contributing to Trajectory Fidelity Bridge

Trajectory Fidelity Bridge welcomes focused contributions that make coding-agent history more portable **without overstating fidelity**.

## Contribution priorities

High-value contributions include:

1. **Source adapters** for documented transcript formats.
2. **Target exporters/importers** where the target tool exposes a supported ingestion boundary.
3. **Synthetic fixtures** that expose fidelity edge cases.
4. **ATIF fidelity accounting** improvements for fields that cannot be represented portably.
5. **Secret-redaction tests** for realistic credential shapes.
6. **ATIF profile/versioning critique** backed by concrete provider examples.
7. **CLI/documentation improvements** that make preservation and loss easier to inspect.

Small, bounded pull requests are preferred over broad rewrites.

## Local setup

```bash
git clone https://github.com/atomicdjt/trajectory-fidelity-bridge.git
cd trajectory-fidelity-bridge
python -m venv .venv
```

Activate the environment:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Install the project and development dependencies:

```bash
python -m pip install -e ".[dev]"
```

> The current PyPI distribution is `atomicdjt-trajectory-fidelity-bridge`. The shorter `agent-session-bridge` name belongs to an unrelated project. The previous `atomicdjt-agent-session-bridge` distribution remains available for existing installations.

## Verification

Before opening a pull request, run:

```bash
pytest
ruff check .
mypy --namespace-packages --explicit-package-bases src/
```

If your change affects parsing, normalization, loss reporting, redaction, or exporting, add focused tests that demonstrate the behavior.

## Contribution contract

### No real private user data

Fixtures committed to the repository must be synthetic or explicitly public-safe. Never commit:

- real coding-agent transcripts containing private project context;
- API keys, tokens, cookies, or credentials;
- proprietary source code;
- personal messages or personally identifying data.

### Loss must be explicit

A provider adapter must not silently imply that unsupported source information was preserved.

If a source field is:

- unsupported;
- normalized into a weaker representation;
- intentionally omitted;
- or impossible to reconstruct at the target,

record that boundary in the appropriate fidelity/loss output and cover it with tests.

### Do not mutate unsupported provider internals

A target adapter must use a documented or explicitly supported ingestion mechanism. Contributions that write directly into opaque provider databases or attempt unsafe session-store mutation are out of scope.

### Keep portability claims narrow

A successful parse/export does not prove that the target runtime can resume the full original session. Documentation and tests should distinguish:

- parsing;
- ATIF normalization;
- payload generation;
- supported target ingestion;
- and actual historical session resumption.

## Opening an issue first

Please open an issue before implementing a new provider adapter or schema-breaking change. Include:

- the provider/tool and version;
- a link to public format/API documentation when available;
- the proposed source/target boundary;
- known fidelity gaps;
- and a minimal synthetic example.

For bug fixes, a focused pull request with a regression test is welcome directly.

## Pull-request quality bar

A strong PR should answer:

- What invariant or user-visible behavior changes?
- How is the change tested?
- What information is preserved, normalized, degraded, or dropped?
- Does the change alter the security boundary?
- Does it introduce a new provider-specific assumption into an TFB ATIF extension or adapter?

Maintainer release steps are documented in [docs/RELEASING.md](docs/RELEASING.md).

## AI-assisted contributions

AI-assisted development is welcome. Contributors remain responsible for the submitted behavior, tests, licensing, security implications, and factual claims.
