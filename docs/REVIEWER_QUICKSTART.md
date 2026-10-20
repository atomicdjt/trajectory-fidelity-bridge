# Independent reviewer quickstart — Trajectory Fidelity Bridge

**Scope:** Python 3.11+; current source on `main`, with the separately published PyPI 0.4.1 distribution. This is a data-conversion and fidelity-reporting tool, **not** a native session-resumption engine.

## Minimal source verification

```bash
git clone https://github.com/atomicdjt/trajectory-fidelity-bridge.git
cd trajectory-fidelity-bridge
python -m venv .venv
# Activate .venv for your platform, then:
python -m pip install -e ".[dev]"
python -m pytest -q
python -m mypy src
python -m ruff check .
```

If a tool invocation fails because of environment/version differences, record that failure and compare the pinned [CI configuration](../.github/workflows/ci.yml) rather than silently adjusting the evidence. The primary package can also be installed independently with `python -m pip install atomicdjt-trajectory-fidelity-bridge==0.4.1`.

## Inspect a concrete conversion

Use the repository's [sanitized controlled-session fixture](../fixtures/real-session/README.md) and its [origin report](DEMO_REAL_SESSION.md); do not upload or publish a private Claude Code history for a demonstration. Supported local-source invocation:

```bash
agent-session import --from claude-code --source your_claude_log.jsonl --output trajectory.atif.json --report
agent-session explain trajectory.atif.json --output report.md
```

The input path above is a **placeholder**; select your own synthetic/sanitized JSONL fixture. Inspect the resulting ATIF JSON and `report.md` for preserved roles, tool arguments/results, unsupported records, and missing timestamp accounting. The optional `--manifest` metadata is unverified external input, not runtime observation.

## Falsification questions

- Does the output preserve a later tool result with the correct originating tool call?
- Are unsupported blocks and missing observation timestamps **counted as loss** rather than invented?
- Does reported redaction accidentally imply that a private transcript is safe to publish?
- Does a target mapping remain a **derived log** without implying target-native historical import?

Follow [compatibility](COMPATIBILITY.md), [format/timestamp semantics](FORMAT.md), [security/redaction limits](SECURITY.md), and the [Antigravity reproduction guide](EXPERIMENT_REPRO.md). The open [PR #43](https://github.com/atomicdjt/trajectory-fidelity-bridge/pull/43) proposes further boundary tests and is **not included as a merged main-branch result at the October 20 audit**.

**Claim boundary:** Local test success demonstrates bounded converter behavior on exercised inputs. It does not certify private-data removal, complete transcript capture, or cross-agent native resume.
