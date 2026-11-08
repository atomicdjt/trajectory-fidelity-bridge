# Interoperability corpus

For a provider-derived consumer defect reproduced against current Harbor, see
[Harbor Claude errors through TFB consumers](../experiments/harbor_tool_errors/README.md).
That experiment is separate from the synthetic corpus below.

This corpus makes disagreements between independent ATIF implementations reproducible and inspectable. It is deliberately small, synthetic, and source-grounded.

The purpose of this corpus is not to prove that Trajectory Fidelity Bridge is correct; it is to make disagreements between independent implementations reproducible and inspectable.

## Contents

- `fixtures/interoperability/claude-comprehensive.source.jsonl` is the canonical synthetic Claude Code-shaped source. It contains ordinary text, two tool calls in one assistant turn, results that arrive out of order and non-adjacently, timestamps, structured arguments/results, one unsupported `thinking` block, two unsupported source records (`system/init` and `progress`), an intentionally ignored debug field, and obviously fake secret-like values.
- `fixtures/interoperability/expected-semantics.json` is the semantic oracle. It separates source facts, TFB policy, comparison policy, and ATIF limitations. It does not require generated metadata or JSON serialization to match.
- `src/interoperability/verifier.py` validates ATIF structure and classifies semantic checks as `PRESERVED`, `NORMALIZED`, `DEGRADED`, `OMITTED`, `CONFLICT`, or `NOT_APPLICABLE`.
- `tests/test_interoperability_verifier.py` tests the verifier itself with adversarial mutations.

## Reproduce and verify

From a clean checkout with the development dependencies installed:

```powershell
python -m interoperability.reproduce `
  --source fixtures/interoperability/claude-comprehensive.source.jsonl `
  --output work/claude-comprehensive.atif.json
python -m interoperability.verifier `
  --source fixtures/interoperability/claude-comprehensive.source.jsonl `
  --output work/claude-comprehensive.atif.json `
  --oracle fixtures/interoperability/expected-semantics.json
```

The equivalent POSIX command uses `\` for line continuation. The generated artifact includes TFB's conversion timestamp, so byte equality is intentionally not the contract. The verifier compares source-grounded semantics and reports the volatile metadata boundary explicitly.

The compact CI-equivalent check is:

```text
python -m pytest -q
python -m ruff check .
python -m mypy --namespace-packages --explicit-package-bases src
```

The CI workflow runs the reproduction and verifier after those checks.

## ATIF v1.8 compatibility result

**November 5, 2026:** [PR #49](https://github.com/atomicdjt/trajectory-fidelity-bridge/pull/49) widened the main-branch dependency to `atif>=1.7,<1.9`. The converter still emits `ATIF-v1.7`; the separately published TFB 0.4.2 distribution retains its original dependency constraint until a later release.

A local comparison used separate Windows/Python 3.14 virtual environments with released `atif==1.7.0` and `atif==1.8.0`, each with Pydantic 2.14.3 and the optional observability dependencies. With this checkout's source on `PYTHONPATH`, the full suite passed **222 tests in each environment**. Both versions passed the synthetic corpus verifier with zero conflicts; their generated JSON objects were equal after removing only the volatile conversion timestamp. `pip check` passed in each environment. The 1.8 environment ran the source directly because the comparison began before the dependency bound was widened. The [PR CI run](https://github.com/atomicdjt/trajectory-fidelity-bridge/actions/runs/42133758960) subsequently installed ATIF 1.8.0 and passed its six Python 3.11/3.12 OS matrix jobs and dependency audit.

These results cover the existing tests and one synthetic corpus, not every provider trace, ATIF 1.8 feature, or native target import. In particular, TFB has no Claude audio mapping and does not claim to emit 1.8 audio. They are not independent practitioner validation.

Earlier, the Harbor ATIF implementation at commit `d6514c49e3dc321df46c6653cb3ee8166ab12efe` validated the generated TFB artifact as both `ATIF-v1.7` and, after changing only the schema-version label, `ATIF-v1.8`; both retained five steps. That reference-model experiment predates the released package comparison and does not itself establish migration to v1.8.

## Source positions and timestamp findings

Record numbers in the oracle are 1-based ordinals over the non-blank lines of the source, counted exactly as the parser iterates the file. The verifier reads the source the same way (line iteration, not `str.splitlines()`), so characters such as U+2028 or U+0085 inside a JSON string do not create phantom records.

The `tool_result_timestamps` finding is derived from the source: it counts source tool results whose record carries a timestamp and reports them as `OMITTED` because ATIF v1.7 cannot represent them. For TFB output it additionally requires the fidelity report's `omitted_tool_result_timestamps` to equal that count, so an understated loss is a `CONFLICT`.

## Comparison model

An independent implementation may serialize different IDs, metadata, extensions, optional fields, or formatting while preserving equivalent trajectory facts. The comparison categories mean:

- `PRESERVED`: the source fact survives without semantic change.
- `NORMALIZED`: the representation changes while the source meaning and relationship survive, such as moving a later Claude `tool_result` into an ATIF observation.
- `DEGRADED`: the source includes material outside the supported representation and the loss is explicitly accounted for.
- `OMITTED`: the source or field is intentionally not emitted, such as the provider-only debug field or a tool-result timestamp that ATIF v1.7 cannot represent.
- `CONFLICT`: the candidate output contradicts a source fact or an explicitly tested policy.
- `NOT_APPLICABLE`: an TFB-specific policy is not imposed on a peer implementation, or the source fixture contains nothing the check could apply to (for example, `tool_result_timestamps` when no source tool result carries a timestamp).

TFB is not the reference authority. The source facts and the ATIF contract are the authority for portable semantics; redaction defaults, extension layout, generated metadata, and result-only-record presentation remain implementation-defined unless the format requires otherwise.

## Peer comparison matrix

The following results were run from the canonical source at SHA-256 `4FD858F21F934568FB49E12CD8C9595A82791EE66F73AE011DC2DC414E835D90`. The semantic oracle SHA-256 is `7998B39A3957D1F0D3EED4991E5AC94B5377CBB2D4C4C3B899DD53C9EF61D5AC`. The TFB artifact was generated with the reproduction command above; peer outputs were kept outside this repository.

| Implementation | Tested provenance | Experiment and command | Observed result | Classification |
| --- | --- | --- | --- | --- |
| Trajectory Fidelity Bridge | `cb360a8`; `atif 1.7.0` | `python -m interoperability.reproduce ...` then `python -m interoperability.verifier ...` | Five steps, two calls, two correlated results, source step timestamps, and redaction passed; one unsupported block and two unsupported records were accounted for. | TFB self-validation |
| `eddiechu888/agent-trajectory-store` | `7d62fe94c96c4c2ebb93506e4e9d8591f928fce4`; package `0.1.1` | `ClaudeAdapter().convert(AdapterInput(...))`; verifier with `--implementation agent-trajectory-store` | Five steps and two calls/results preserved. Result JSON key order and multiline whitespace normalized; no default redaction and no TFB fidelity extension. | Equivalent semantics plus intentional policy difference; verifier passed |
| `davanstrien/agent-traces` | `63df6415bdd651c49d66f161665e000c5c6d94f2`; package `0.1.0` | `parse_sessions(canonical.source.jsonl)` and `parse_sessions(canonical.atif.json)` | Direct Claude parsing returned eight flat source rows and exposed thinking text. The ATIF path expects legacy `{"lines": [...]}` documents; the TFB root `steps` artifact was not recognized and triggered a scalar-detection `TypeError`. | ATIF shape incompatibility / peer defect candidate; not an TFB conformance failure |
| `waldekmastykarz/atifact` | `db0bf0fcac29adc26778185383d42f2d7c8ceba6`; package `0.12.1` | `node dist/src/index.js canonical.source.jsonl --format claude-code-jsonl --json --quiet`; verifier with `--implementation atifact` | Output was valid ATIF v1.7 with four steps, two calls, and one result. It omitted the delayed second result and adjacent user text after its pending tool step had already flushed; it also omitted source timestamps. | Differential conflict requiring source-format/implementation triage; no upstream change made |
| `Eli-Chandler/atif-lens` | `78a8a247bdd9cae30897134f22864b6d1d3c9733`; package `0.2.0` | `npm ci --ignore-scripts`; existing web tests plus a temporary local `parseTrajectory`/`lintTrajectory` test against the TFB artifact | Existing 23 tests passed; the TFB artifact parsed and linted with zero warnings. | Independent parser/linter agreement |
| `theagenticguy/atif-sql` | `5793d935bfb0117994ba04c75125151ba805598c`; workspace source inspected | `python -m pip install -e <peer> --quiet` was bounded and stopped while resolving its dependency graph; conversion was not run. | No conversion result collected. | NOT TESTED; source indicates Claude-to-ATIF conversion is backed by a pinned Harbor adapter |

The peer commands are intentionally not CI dependencies. They are reproducibility notes for the captured local experiments, not claims that local execution constitutes independent practitioner validation.

## Safety and evidence boundary

All canonical fixture content is synthetic and uses fake credentials. A passing corpus check does not prove universal provider correctness, arbitrary Claude Code compatibility, perfect redaction, production safety, native target resumability, or practitioner validation. It also does not turn a local peer run into independent adoption or production evidence.
