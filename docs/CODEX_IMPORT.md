# Importing a Codex rollout

TFB can read a bounded subset of Codex's recorded session-rollout JSONL and
produce an ATIF v1.7 document:

```bash
tfb import --from codex --source rollout.jsonl --output trajectory.atif.json --report
tfb explain trajectory.atif.json --output report.md
```

For an offline, wholly synthetic example, use
[`fixtures/codex_sample.jsonl`](../fixtures/codex_sample.jsonl). Codex's
[rollout recorder](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/recorder.rs)
describes the recorded JSONL format. A recorded rollout is different from the
`codex exec --json` live event stream, which this adapter does not claim to
support. Do not paste or publish private session files merely to try this feature.

## Supported source facts

- `session_meta` supplies a session ID and CLI version when present.
- `response_item` message records preserve user and assistant text. Developer
  messages map to ATIF system steps; this normalization is reported.
- Function and custom tool calls become agent steps with the recorded call ID,
  name and arguments. Codex function arguments that are JSON objects become
  ATIF argument objects. Custom input and non-object or malformed JSON arguments
  are wrapped under `input` or `value`, and the transformation is reported.
- Matching function and custom tool outputs become observations on the original
  call, even when results arrive later or out of order. Text output blocks retain
  their order; unusual non-text, non-list values are serialized to JSON text.
- Valid source timestamps on represented messages and calls are retained. ATIF
  v1.7 has no result timestamp field; attached result timestamps are counted as
  omitted. No execution duration is inferred.

Codex's serialized function output format does not provide a generally reliable
success flag in these records. TFB marks their outcome as unknown in its
namespaced observation metadata. Its OpenTelemetry projection leaves those tool
spans `UNSET` unless an explicit recognized error is present; a result is not
treated as proof of success.

## Boundaries and loss

The fidelity report records unsupported records, content blocks, ignored fields,
orphaned outputs, invalid timestamps and omitted result timestamps. In particular,
reasoning/encrypted content, token-usage events, multimodal blocks, tool namespace
metadata, subagent relationships and other non-response events are not fully
mapped; consult the detailed counts in the ATIF output and `tfb explain` report.
An output with no matching earlier call is not attached. Duplicate call IDs are
ambiguous: the first call is retained, the duplicate is reported, and later
results for that ID are not guessed. Replayed item IDs are reported and skipped.
Result type must match the original function/custom call type.

The input may contain private instructions, messages, source code, paths and
credentials. Import's redaction is heuristic, not a guarantee. Review any output
before sharing it. The adapter processes history as data; it never runs recorded
commands. It does not import history back into Codex or promise native resumption.

The checked-in fixture and adversarial tests are synthetic. An existing local
Codex session was also processed in memory without publishing its content, but
this is not independent user validation or evidence for every rollout version,
platform, tool, modality or interrupted-session shape. Harbor also has a
[Codex converter](https://github.com/harbor-framework/harbor/blob/main/src/harbor/agents/installed/codex.py);
TFB's adapter adds a direct TFB CLI path and the project's explicit fidelity
accounting, not a claim that Harbor cannot convert Codex sessions.

For the synthetic sample, a local run of Harbor 0.25.0 at commit
`9c7a39b991d7e2205019f6be0598cbd22d84bfc3` and TFB both preserved the same one
call ID, tool name, structured arguments and result. Harbor produced two ATIF
steps and TFB produced three because they group the events differently. The
comparison covers that fixture only.

The synthetic sample was also sent using `tfb observe --from codex` to a local
Phoenix 21.0.0 instance. Phoenix stored one trace with one `UNSET` tool span and
no input or output attributes in metadata-only mode. This checks that local
backend boundary for the synthetic sample, not production operation.
