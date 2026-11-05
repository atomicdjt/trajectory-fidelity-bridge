# Independent reviewer quickstart — Trajectory Fidelity Bridge

**Scope:** Python 3.11+; current source on `main`, with the separately published PyPI 0.4.2 distribution (checked November 5, 2026). This is a data-conversion and fidelity-reporting tool, **not** a native session-resumption engine.

## Minimal source verification

```bash
git clone https://github.com/atomicdjt/trajectory-fidelity-bridge.git
cd trajectory-fidelity-bridge
python -m venv .venv
# Activate .venv for your platform, then:
python -m pip install -e ".[dev]"
python -m pytest -q
MYPYPATH=src python -m mypy --namespace-packages --explicit-package-bases src
python -m ruff check .
```

The `MYPYPATH=src` syntax is for POSIX shells; in PowerShell set `$env:MYPYPATH = "src"` before running the mypy command without its prefix. If a tool invocation fails because of environment/version differences, record that failure and compare the [CI configuration](../.github/workflows/ci.yml) rather than silently adjusting the evidence. The primary package can also be installed independently with `python -m pip install atomicdjt-trajectory-fidelity-bridge==0.4.2`.

## Inspect a concrete conversion

Run this synthetic fixture from the repository root after installing from source:

```bash
agent-session import --from claude-code --source fixtures/interoperability/claude-comprehensive.source.jsonl --output trajectory.atif.json --report
agent-session explain trajectory.atif.json --output report.md
```

For the checked-in fixture, the report should show six preserved source records, two tool calls, two correlated observations, two unsupported records and one unsupported block. Inspect the ATIF and report, then compare source facts with the [semantic oracle and verifier](INTEROPERABILITY.md). The fixture is synthetic, including its fake secret-like values; this exercise is not a live-provider test. Generated files contain fixture content and should be kept out of commits.

The [sanitized controlled-session fixture](../fixtures/real-session/README.md) and [origin report](DEMO_REAL_SESSION.md) provide a separate, bounded real-session artifact. Do not upload private histories for evaluation; heuristic redaction is not a guarantee. Optional manifest metadata is unverified external input, not runtime observation.

## Falsification questions

- Does the output preserve a later tool result with the correct originating tool call?
- Are unsupported blocks and missing observation timestamps **counted as loss** rather than invented?
- Does reported redaction accidentally imply that a private transcript is safe to publish?
- Does a target mapping remain a **derived log** without implying target-native historical import?

Follow [compatibility](COMPATIBILITY.md), [format/timestamp semantics](FORMAT.md), [security/redaction limits](SECURITY.md), and the [Antigravity reproduction guide](EXPERIMENT_REPRO.md). [PR #43](https://github.com/atomicdjt/trajectory-fidelity-bridge/pull/43) merged characterization tests for null and missing tool-result content; their textual output does not preserve all original JSON types.

**Claim boundary:** Local test success demonstrates bounded converter behavior on exercised inputs. It does not certify private-data removal, complete transcript capture, or cross-agent native resume.

## Report an evaluation

A useful evaluation records the exact commit or package version, Python and operating system, command, exit status, and expected versus observed result. For a mismatch, include a minimal **synthetic or carefully sanitized** input and the corresponding fidelity summary; omit credentials, private source and personal data. Use the [issue tracker](https://github.com/atomicdjt/trajectory-fidelity-bridge/issues) if you choose to share it.

Success means the reviewer can reproduce the stated fixture results, identify supported and omitted semantics, and explain whether the output serves their actual workflow. A star, a clone, or passing CI alone is not evidence of independent use or adoption.
