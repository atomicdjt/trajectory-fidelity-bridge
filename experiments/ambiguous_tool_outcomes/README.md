# Ambiguous external tool outcomes

## Research question

When two provider executions produce the same caller-visible timeout transcript,
but one commits an effect and the other does not, does TFB preserve the available
evidence without assigning different outcomes to the two cases?

The competing outcomes are:

- Both receipts preserve the same tool call and timeout, with an unresolved
  external effect outcome.
- A receipt claims success or failure, loses the call relationship, or drops
  evidence without accounting for it.

This is a small transcript-to-ATIF experiment. The provider is a deterministic,
in-memory fixture; it performs no network calls, sleeps, or real external side
effects. The truth ledger records only fixture events and an in-memory effect
count. The same single Codex JSONL transcript is passed to TFB twice, so its
caller-visible bytes are identical by construction. The separate truth ledgers
are never passed to the normalizer.

The timestamps in the source are fixed synthetic record values. They are not
runtime measurements, and this experiment infers no duration from them.

## Existing coverage audit

| Requirement | Existing coverage | Evidence | Gap before this experiment |
|---|---|---|---|
| Tool-call identity | Codex `call_id` is used to associate calls and outputs; a matching call ID is retained in ATIF. | `src/adapters/codex/parser.py:160-164, 343-364`; `tests/test_codex_parser.py:28-96` | No counterfactual timeout case checks identity preservation across different hidden provider effects. |
| Operation/idempotency identity | No provider operation ID or idempotency-key field is modeled by the Codex adapter. A call ID is only the rollout's call/result correlation key. | `src/adapters/codex/parser.py:160-164, 327-365`; `docs/CODEX_IMPORT.md:21-35` | No provider deduplication contract or logical-operation identity. |
| Tool timeout | Generic tool output is retained, but existing Codex fixtures use ordinary output text. | `tests/test_codex_parser.py:28-96, 339-365` | No timeout transcript with an independent effect ledger. |
| Caller-visible uncertainty | Codex output receives the TFB extension value `outcome: unknown`; the test checks the projected tool span remains `UNSET`. | `src/adapters/codex/parser.py:359-366`; `tests/test_codex_parser.py:339-374`; `docs/CODEX_IMPORT.md:35-40` | Existing check has no distinct provider ground truth or two-world comparison. |
| Retry relationships | Duplicate call IDs and mismatched result types are treated as ambiguous rather than guessed. | `tests/test_codex_parser.py:167-193, 303-337` | No explicit retry attempt, relationship, or recovery policy is represented. |
| Delayed or lost results | Interleaved/out-of-order outputs correlate to calls. | `tests/test_codex_parser.py:28-96` | No lost-response case or later reconciliation is covered. |
| External effect ground truth | The Codex importer consumes transcript records and does not execute recorded tools. | `src/adapters/codex/parser.py:160-161`; `docs/CODEX_IMPORT.md:53-55` | No test tracks provider-side commit events or effect counts. |
| Timestamp fidelity | Source step timestamps are retained; a result timestamp that ATIF v1.7 cannot encode is counted. | `tests/test_timestamp_and_block_fidelity.py:53-78`; `docs/FORMAT.md:92-103`; `docs/INTEROPERABILITY.md:58` | Existing tests do not pair result-time loss with an ambiguous external effect. |
| Unsupported-field accounting | Unmapped fields are counted in the namespaced fidelity report. | `src/bridge/models.py:15-85`; `docs/FORMAT.md:53-66` | No test checks the Codex rollout item-ID omission in an ambiguous-timeout receipt. |
| Unknown-outcome handling | Codex output records are marked `unknown`; Claude's explicit error flag is preserved separately. | `tests/test_codex_parser.py:339-374`; `tests/test_timestamp_and_block_fidelity.py:118-129` | No test checks that the unknown annotation is unchanged across hidden outcomes. |
| Safe-retry decision boundary | TFB documents that ATIF does not define a tool re-execution policy. | `docs/FORMAT.md:115-121` | No retry decision criteria or provider evidence are recorded by the existing importer. |

## Artifact boundaries

| Artifact | Role |
|---|---|
| `reproduce.py` | Runs the synthetic provider model, writes one caller-visible Codex transcript and separate truth ledgers, then invokes TFB's supported Codex CLI import. |
| `caller-visible.source.jsonl` in `evidence/` | The exact transcript passed to both conversion runs. |
| `ground-truth-*.json` in `evidence/` | Provider-fixture events, synthetic effect count, and an explicit note that the Codex call ID is only a test-harness join key. |
| `oracle.json` | Source, output, truth-count, and decision expectations checked by the verifier. |
| `*.atif.json` in `evidence/` | Actual serialized ATIF v1.7 outputs from the TFB CLI. |
| `*.fidelity.json` in `evidence/` | Fidelity extension extracted from each actual output. |
| `decision-record.json` | Caller-side conclusion and conditional retry requirements, kept separate from both the transcript and provider truth. |
| `verify.py` | Independent checker. It reads the source, truth ledgers, oracle, and generated ATIF documents; it does not import the TFB parser. It validates ATIF with the installed ATIF model, then checks the raw source/output fields directly. |
| `verification.json` in `evidence/` | Observed checks, ground-truth counts, unknown classification, omissions, and verifier exit result. |
| `commands.json`, `execution.json`, `manifest.json` in `evidence/` | Normalizer argv and exit codes, verifier argv and exit code, versions, source commit, source-worktree cleanliness, and SHA-256 hashes. The selected output directory is excluded from the cleanliness check so `--overwrite` can record a clean source state during regeneration. The manifest intentionally does not hash itself. |

Generated-artifact hash keys use the `packet/` prefix and are relative to the
evidence packet, so the manifest remains accurate when `--output-dir` points to
a different directory.

## Reproduce

From the repository root, install the project and development dependencies once:

```powershell
python -m pip install -e ".[dev]"
```

Generate a fresh packet in a new directory:

```powershell
python -m experiments.ambiguous_tool_outcomes.reproduce --output-dir work/ambiguous-tool-outcomes
```

To regenerate the checked-in `evidence/` directory in place, add
`--overwrite`. The script replaces only the named generated files and removes
nothing. Its manifest records the exact TFB import and independent-verifier
commands and their exit codes.

The independent command sequence below runs the TFB import directly, twice, on
the same source. It then verifies those two replay outputs against the source,
truth ledgers, and oracle. The `work/` output paths should be new or empty.

```powershell
python -m cli.main import --from codex --source experiments/ambiguous_tool_outcomes/evidence/caller-visible.source.jsonl --output work/replay-before.atif.json --report
python -m cli.main import --from codex --source experiments/ambiguous_tool_outcomes/evidence/caller-visible.source.jsonl --output work/replay-after.atif.json --report
python -m experiments.ambiguous_tool_outcomes.verify --source experiments/ambiguous_tool_outcomes/evidence/caller-visible.source.jsonl --ground-truth-before experiments/ambiguous_tool_outcomes/evidence/ground-truth-before_commit_timeout.json --ground-truth-after experiments/ambiguous_tool_outcomes/evidence/ground-truth-after_commit_response_loss.json --before-output work/replay-before.atif.json --after-output work/replay-after.atif.json --decision-record experiments/ambiguous_tool_outcomes/evidence/decision-record.json --oracle experiments/ambiguous_tool_outcomes/oracle.json --report work/replay-verification.json
```

Run the regression and style checks:

```powershell
python -m pytest -q
python -m ruff check .
$env:MYPYPATH = (Resolve-Path src).Path
python -m mypy --namespace-packages --explicit-package-bases src/
```

At the audited base commit `fbdc273`, the repository-wide Ruff command already
reported `DTZ001` at `src/observability/spans.py:22`. This experiment does not
touch that file; its own files are checked separately and are clean.

## Observed results

The primary run used the same SHA-256 input for both conversions. The in-memory
provider truth ledger recorded an effect count of zero before commit and one
after commit before response loss. The independent checker passed all checks
with zero conflicts. It also rejected adversarial mutations for a fabricated
successful outcome, broken call/result correlation, and an understated result
timestamp omission.

| Property | Before-commit timeout | After-commit response loss |
|---|---|---|
| Caller-visible evidence | Same source transcript, same call ID, request, output text, and timestamps. | Same source transcript, same call ID, request, output text, and timestamps. |
| Provider ground truth | No commit event; actual in-memory effect count 0. | One commit event before response loss; actual in-memory effect count 1. |
| Normalized TFB representation | ATIF v1.7 call and correlated timeout observation; TFB extension outcome is `unknown`. | Same ATIF semantics and TFB extension outcome is `unknown`. |
| Preserved identities | Session ID, tool call ID, and result-to-call relationship. | Same. |
| Omitted evidence | Result-record timestamp omitted and counted once; three Codex `payload.id` fields omitted and counted. | Same. |
| Verified interpretation | External effect outcome `UNKNOWN`; no automatic retry authorized from this evidence. | Same. |
| Retry decision | Reconsider only with a valid provider deduplication guarantee, authoritative reconciliation that the action did not occur, or a demonstrated application recovery procedure. | Same. |

`ObservationResult` in the tested ATIF v1.7 Python model has no timestamp
field. TFB retained the call step timestamp, omitted the source result timestamp,
and reported `omitted_tool_result_timestamps: 1`. TFB also retained the timeout
text and result correlation. The source's three Codex `payload.id` values were
not copied into ATIF; the fidelity report counted them as `payload.id` ignored
on three records. The Codex `call_id` is preserved as a tool-call/result
correlation ID, but neither source nor receipt contains a provider operation ID
or idempotency key.

The `unknown` value is TFB-specific metadata on the Codex observation. It does
not mean the effect failed, and it is not an ATIF core field. The retry decision
is a separate evidence policy; the normalizer does not authorize retries.

## Limits and relation to ARC Issue #51

The fixture does not test a real provider, external side effect, retry, delayed
receipt, provider deduplication contract, or reconciliation endpoint. The
timestamp values are synthetic and no duration is measured. Passing this local
oracle is not independent operator review, provider validation, or proof of a
general safe-retry guarantee.

[ARC Issue #51](https://github.com/mbabby/agent-research-commons/issues/51)
already documents synthetic before-commit and after-commit timeout cases, later
reconciliation and pending-operation experiments, and their limits. This TFB
packet does not add a new retry or provider-behavior finding. Its narrower
increment is a replayable transcript-to-ATIF demonstration: the same caller
evidence and its identities normalize to the same unknown receipt across two
separate truth ledgers, while timestamp and event-ID losses are accounted for.
That makes it a possible supplemental interoperability artifact, not a novel
resolution of ARC's broader research question.
