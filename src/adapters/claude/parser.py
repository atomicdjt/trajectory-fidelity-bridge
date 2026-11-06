from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, TextIO

from atif import (
    Agent,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
)

from bridge.models import FidelityReport, asb_extension

# Record types that Claude Code writes next to conversation turns. The classification
# is derived from the field names observed on real Claude Code 2.1.x logs; it is an
# observation about those logs, not a Claude Code specification.
# ``bookkeeping``: no text-bearing field was observed, only session metadata.
_BOOKKEEPING_RECORD_TYPES = frozenset(
    {
        "agent-name",
        "ai-title",
        "atis-latch",
        "bridge-session",
        "cost-state",
        "custom-title",
        "file-history-delta",
        "file-history-snapshot",
        "mode",
        "permission-mode",
        "pr-link",
    }
)
# ``text_bearing``: observed with text or content fields (context the harness gave the
# model, echoed prompts, hook output). ASB cannot show that this is not content loss.
_TEXT_BEARING_RECORD_TYPES = frozenset({"attachment", "last-prompt", "queue-operation"})
_BOOKKEEPING_SYSTEM_SUBTYPES = frozenset({"turn_duration"})
_TEXT_BEARING_SYSTEM_SUBTYPES = frozenset(
    {"compact_boundary", "local_command", "stop_hook_summary"}
)

_CONSUMED_RECORD_FIELDS = frozenset(
    {"type", "message", "timestamp", "sessionId", "version", "cwd", "gitBranch"}
)
_CONSUMED_MESSAGE_FIELDS = frozenset({"role", "content", "model", "usage", "id"})
_SYNTHETIC_MODEL = "<synthetic>"


def parse_claude_jsonl(file_stream: TextIO) -> Trajectory:
    """Normalize supported Claude Code JSONL records into an ATIF v1.7 trajectory.

    Claude Code places tool results inside later user records. ATIF models those
    results as observations on the agent step that made the corresponding call,
    so the parser moves only the tool-result block while preserving adjacent user
    text as its own ATIF user step.
    """
    steps: list[Step] = []
    tool_call_steps: dict[str, Step] = {}
    session_id: str | None = None
    version = "unknown"
    cwd: str | None = None
    git_branch: str | None = None
    fidelity = FidelityReport()
    normalized_tool_results = False
    usage_by_message: dict[str, Metrics] = {}
    line_number = 0

    for raw_line in file_stream:
        line = raw_line.strip()
        if not line:
            continue
        line_number += 1
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            fidelity.count_unsupported_record("(malformed JSON line)", "unrecognized")
            continue
        if not isinstance(record, dict):
            fidelity.count_unsupported_record("(non-object JSON value)", "unrecognized")
            continue

        record_type = record.get("type")
        if not isinstance(record_type, str) or record_type not in {"user", "assistant", "system"}:
            fidelity.count_unsupported_record(*_classify_record(record))
            continue

        session_id = session_id or record.get("sessionId")
        if version == "unknown" and record.get("version"):
            version = str(record["version"])
        cwd = cwd or record.get("cwd")
        git_branch = git_branch or record.get("gitBranch")

        message = record.get("message")
        if not isinstance(message, dict):
            fidelity.count_unsupported_record(*_classify_record(record))
            continue

        role = message.get("role", record_type)
        if not isinstance(role, str) or role not in {"user", "assistant", "system"}:
            fidelity.count_unsupported_record(f"{record_type} (unsupported role)", "unrecognized")
            continue

        timestamp = _step_timestamp(record.get("timestamp"), fidelity)
        content, tool_calls, tool_results = _parse_content_blocks(
            message.get("content", []), role, fidelity
        )

        if role == "assistant":
            model_name, metrics = _model_and_metrics(message, usage_by_message, fidelity)
            step = Step(
                step_id=len(steps) + 1,
                timestamp=timestamp,
                source="agent",
                model_name=model_name,
                message=content,
                tool_calls=tool_calls or None,
                metrics=metrics,
                extra=_step_extra(line_number, message.get("id")),
            )
            steps.append(step)
            for tool_call in tool_calls:
                tool_call_steps[tool_call.tool_call_id] = step
        else:
            _attach_tool_results(
                tool_results, tool_call_steps, fidelity, timestamp is not None
            )
            if content or not tool_results:
                steps.append(
                    Step(
                        step_id=len(steps) + 1,
                        timestamp=timestamp,
                        source="user" if role == "user" else "system",
                        message=content,
                        extra=_step_extra(line_number, None),
                    )
                )
            if tool_results and fidelity.observation_results_preserved > 0:
                normalized_tool_results = True

        fidelity.source_records_preserved += 1
        for field in record:
            if field not in _CONSUMED_RECORD_FIELDS:
                fidelity.count_ignored_field(field)
        for field in message:
            if field not in _CONSUMED_MESSAGE_FIELDS:
                fidelity.count_ignored_field(f"message.{field}")

    fidelity.sort_breakdowns()
    if normalized_tool_results:
        fidelity.transformations.append(
            "Moved Claude Code tool_result blocks to call-correlated ATIF observations."
        )

    return Trajectory(
        schema_version="ATIF-v1.7",
        session_id=session_id,
        agent=Agent(
            name="claude-code",
            version=version,
            extra={"provider": "anthropic"},
        ),
        steps=steps,
        extra=asb_extension(
            original_format="claude-code-jsonl",
            converted_by="agent-session-bridge",
            conversion_timestamp=datetime.now(UTC).isoformat(),
            fidelity=fidelity,
            workspace=_workspace_metadata(cwd, git_branch),
        ),
    )


def _classify_record(record: dict[str, Any]) -> tuple[str, str]:
    """Return ``(label, category)`` for a record ASB does not convert."""
    record_type = record.get("type")
    if not isinstance(record_type, str) or not record_type:
        return "(untyped record)", "unrecognized"
    if record_type == "system":
        subtype = record.get("subtype")
        if not isinstance(subtype, str) or not subtype:
            return "system", "unrecognized"
        label = f"system/{subtype}"
        if subtype in _BOOKKEEPING_SYSTEM_SUBTYPES:
            return label, "bookkeeping"
        if subtype in _TEXT_BEARING_SYSTEM_SUBTYPES:
            return label, "text_bearing"
        return label, "unrecognized"
    if record_type in _BOOKKEEPING_RECORD_TYPES:
        return record_type, "bookkeeping"
    if record_type in _TEXT_BEARING_RECORD_TYPES:
        return record_type, "text_bearing"
    if record_type in {"user", "assistant"}:
        return f"{record_type} (no message object)", "unrecognized"
    return record_type, "unrecognized"


def _step_extra(line_number: int, message_id: Any) -> dict[str, Any]:
    """Per-step provenance: which source line, and which API response, produced the step."""
    source: dict[str, Any] = {"source_line": line_number}
    if isinstance(message_id, str) and message_id:
        source["source_message_id"] = message_id
    return {"agent_session_bridge": source}


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _optional_count(value: Any) -> int | None:
    """An absent count is zero; a present but invalid one is ``None``."""
    return 0 if value is None else _non_negative_int(value)


def _usage_metrics(usage: Any) -> Metrics | None:
    """Map an Anthropic ``usage`` object to ATIF v1.7 ``Metrics`` (units: tokens).

    ATIF ``prompt_tokens`` counts all input tokens, cached and uncached, with
    ``cached_tokens`` a subset. Anthropic's ``input_tokens`` excludes cache reads and
    cache creation, so both are added back. Cost is never invented.
    """
    if not isinstance(usage, dict):
        return None
    uncached = _non_negative_int(usage.get("input_tokens"))
    output = _non_negative_int(usage.get("output_tokens"))
    cache_read = _optional_count(usage.get("cache_read_input_tokens"))
    cache_created = _optional_count(usage.get("cache_creation_input_tokens"))
    if uncached is None or output is None or cache_read is None or cache_created is None:
        return None
    return Metrics(
        prompt_tokens=uncached + cache_read + cache_created,
        completion_tokens=output,
        cached_tokens=cache_read,
        extra={
            "uncached_input_tokens": uncached,
            "cache_creation_input_tokens": cache_created,
        },
    )


def _model_and_metrics(
    message: dict[str, Any],
    usage_by_message: dict[str, Metrics],
    fidelity: FidelityReport,
) -> tuple[str | None, Metrics | None]:
    """Return the step's model and metrics without double counting or inventing values.

    Claude Code writes one record per content block and repeats the API response's
    ``usage`` on each. Metrics are attached to the first record of a response only, so
    per-step sums equal the response totals. ``<synthetic>`` marks a client-generated
    message, not model output, so it gets neither a model name nor metrics.
    """
    model = message.get("model")
    if not isinstance(model, str) or not model.strip():
        return None, None
    if model == _SYNTHETIC_MODEL:
        fidelity.synthetic_agent_records += 1
        return None, None
    candidate = _usage_metrics(message.get("usage"))
    if candidate is None:
        return model, None
    message_id = message.get("id")
    if not isinstance(message_id, str) or not message_id:
        return model, candidate
    first = usage_by_message.get(message_id)
    if first is None:
        usage_by_message[message_id] = candidate
        return model, candidate
    if first == candidate:
        fidelity.duplicate_usage_records += 1
    else:
        fidelity.conflicting_usage_records += 1
    return model, None


def _step_timestamp(value: Any, fidelity: FidelityReport) -> str | None:
    """Return a source timestamp ATIF can carry, or ``None`` without inventing one.

    An absent timestamp is not a loss. A present value that ATIF's ISO 8601
    validation would reject is omitted and counted instead of aborting the import.
    """
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value)
        except ValueError:
            pass
        else:
            return value
    fidelity.invalid_source_timestamps += 1
    return None


def _block_has_payload(block: dict[str, Any]) -> bool:
    """Whether an unconverted block carried content, judged from the block itself.

    A ``thinking`` block whose text is empty holds only an opaque signature, so
    dropping it loses no reasoning text. Any other unknown block is assumed to carry
    content: ASB cannot show otherwise.
    """
    if block.get("type") == "thinking":
        return bool(str(block.get("thinking") or "").strip())
    return True


def _parse_content_blocks(
    content_blocks: Any, role: str, fidelity: FidelityReport
) -> tuple[str, list[ToolCall], list[ObservationResult]]:
    if isinstance(content_blocks, str):
        return content_blocks, [], []
    if not isinstance(content_blocks, list):
        fidelity.count_unsupported_block(
            "(non-list content)", with_content=content_blocks not in (None, {}, [], "")
        )
        return "", [], []

    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    tool_results: list[ObservationResult] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            fidelity.count_unsupported_block("(non-object block)", with_content=True)
            continue
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text")
            if not isinstance(text, str):
                fidelity.count_unsupported_block("text (non-string)", with_content=True)
                continue
            text_parts.append(text)
        elif block_type == "tool_use":
            if role != "assistant":
                fidelity.count_unsupported_block("tool_use (outside assistant)", with_content=True)
                continue
            call_id = block.get("id")
            name = block.get("name")
            arguments = block.get("input", {})
            if (
                not isinstance(call_id, str)
                or not call_id.strip()
                or not isinstance(name, str)
                or not name.strip()
                or not isinstance(arguments, dict)
            ):
                fidelity.count_unsupported_block("tool_use (malformed)", with_content=True)
                continue
            tool_calls.append(
                ToolCall(
                    tool_call_id=call_id,
                    function_name=name,
                    arguments=arguments,
                )
            )
            fidelity.tool_calls_preserved += 1
        elif block_type == "tool_result":
            if role != "user":
                fidelity.count_unsupported_block("tool_result (outside user)", with_content=True)
                continue
            result_call_id = block.get("tool_use_id")
            tool_results.append(
                ObservationResult(
                    source_call_id=(
                        result_call_id
                        if isinstance(result_call_id, str) and result_call_id.strip()
                        else None
                    ),
                    content=_tool_result_text(block.get("content", ""), fidelity),
                    extra={"is_error": block["is_error"]} if block.get("is_error") else None,
                )
            )
        else:
            fidelity.count_unsupported_block(
                block_type if isinstance(block_type, str) and block_type else "(untyped block)",
                with_content=_block_has_payload(block),
            )
    return "\n".join(part for part in text_parts if part), tool_calls, tool_results


def _tool_result_text(value: Any, fidelity: FidelityReport) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        is_claude_content_blocks = (
            len(value) > 0
            and all(isinstance(block, dict) and "type" in block for block in value)
            and any(
                (block.get("type") == "text" and isinstance(block.get("text"), str))
                or (block.get("type") == "image" and isinstance(block.get("source"), dict))
                for block in value
            )
        )
        if is_claude_content_blocks:
            text_parts: list[str] = []
            for block in value:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text")
                    if isinstance(text, str):
                        text_parts.append(text)
                        continue
                inner_type = block.get("type") if isinstance(block, dict) else None
                fidelity.count_unsupported_block(
                    f"tool_result/{inner_type}"
                    if isinstance(inner_type, str)
                    else "tool_result/(untyped)",
                    with_content=True,
                )
            return "".join(text_parts)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _attach_tool_results(
    results: list[ObservationResult],
    tool_call_steps: dict[str, Step],
    fidelity: FidelityReport,
    record_has_timestamp: bool,
) -> None:
    for result in results:
        source_step = (
            tool_call_steps.get(result.source_call_id) if result.source_call_id else None
        )
        if source_step is None:
            fidelity.orphaned_tool_results += 1
            continue
        if source_step.observation is None:
            source_step.observation = Observation(results=[])
        source_step.observation.results.append(result)
        fidelity.observation_results_preserved += 1
        if record_has_timestamp:
            # ATIF v1.7 ObservationResult has no timestamp field; do not invent one.
            fidelity.omitted_tool_result_timestamps += 1


def _workspace_metadata(cwd: str | None, git_branch: str | None) -> dict[str, Any] | None:
    if not cwd and not git_branch:
        return None
    workspace: dict[str, Any] = {}
    if cwd:
        workspace["cwd"] = cwd
    if git_branch:
        workspace["repository"] = {"branch": git_branch}
    return workspace
