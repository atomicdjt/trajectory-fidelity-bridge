# Observability Integration

Trajectory Fidelity Bridge provides an optional observability projection that converts an Agent Trajectory Interchange Format (ATIF) session into OpenTelemetry (OTel) spans following OpenInference GenAI semantic conventions. This allows viewing offline agent trajectories in tools like Arize Phoenix.

## Core Design Principle
**ATIF is the source of truth.** The observability projection is a one-way mapping *from* ATIF *to* OpenTelemetry. It does not replace ATIF as the portable trajectory format.

## Semantic Mapping Matrix

| TFB / ATIF concept | OpenTelemetry GenAI / OpenInference Representation | Confidence | Loss / Caveat |
| ------------------ | -------------------------------------------------- | ---------- | ------------- |
| source `session_id` | `session.id` | High | Emitted only when a genuine source session ID exists; no substitute is generated. |
| Agent Step (`source`) | `Span` (Kind: `AGENT`) | Medium | Grouped logically per step source. |
| step `source` | `agent_session_bridge.step_source` | High | TFB namespace; not an OpenInference message array. |
| `message` | `input.value` / `output.value` | High | Present only in explicit content modes. |
| `tool_calls` | `Span` (Kind: `TOOL`), `tool.name`, `tool.id` | High | Tool calls are mapped with `tool_call_id`. |
| `observation.results` | TOOL `output.value` | High | Present only in explicit content modes. Correlated via `source_call_id`. |
| tool error extras | TOOL status `ERROR` | Bounded | Recognizes TFB `is_error` and Harbor Claude `tool_result_is_error`; these are converter conventions, not ATIF-standard fields. |
| timestamps | Span points/boundaries | High | Step timestamps are source-observed points; tool execution duration is zero as observations do not have independent timestamps. |

## Trace Topology
The ATIF trajectory is mapped as one **historical projection** trace: a root `CHAIN` span contains one `AGENT` span per recorded step and its correlated `TOOL` spans. This is a structural representation of recorded observations, not a claim that TFB observed the original in-process runtime trace.

## Privacy & Content Capture
Coding-agent transcripts contain sensitive information. The projection supports multiple privacy modes:
- `metadata-only` (default): Only structure, roles, and tool names are exported. No text content or tool arguments are exported.
- `redacted-content`: Redacts known secrets on a copy before exporting.
- `full-content`: Exports all content. **Warning:** this can export source code, secrets, commands, file paths, proprietary information, and personal information.

## Tool outcome interpretation

Both `explain` and `observe` recognize the two error flags above. Boolean `true`,
integer `1`, and strings `true`/`1` (case-insensitive, trimmed) indicate an error.
An explicit error wins over a false flag or another non-error result correlated
with the same call. Unrelated calls cannot supply another call's status.
Result text and arbitrary nested metadata are not parsed for errors.

Telemetry retains the existing `OK` policy for a correlated result without a
recognized error; this is not proof that an unfamiliar converter reports failures
using these conventions. A call with no correlated result now remains `UNSET`.
Metadata-only error descriptions remain generic. Content modes use the first
correlated error's text for the status description, applying redaction when selected.
The output attribute still contains the first nonempty correlated result; additional
result bodies are not aggregated. Timestamp and duration behavior is unchanged.

See [the Harbor reproduction](../experiments/harbor_tool_errors/README.md) for the
real-session evidence and the limits of this compatibility claim.

## Fidelity Analysis
- **Preserved:** Tool invocation sequence, conversation roles, chronological order.
- **Transformed:** Timestamps (converted to synthesized spans).
- **Omitted:** Some low-level execution metadata if it lacks OTel standard representation.
- **Unsupported:** Granular token usage per step if only available as an aggregate.
