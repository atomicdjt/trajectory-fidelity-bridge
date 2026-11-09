"""Convert a bounded subset of Codex session rollout JSONL to ATIF v1.7.

Rollouts contain response items and other events; only supported response items
are represented. Unconverted records and content are reported, not replayed.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, TextIO

from atif import (
    Agent,
    ContentPart,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
)

from bridge.models import FidelityReport, asb_extension

_TEXT_TYPES = frozenset({"input_text", "output_text", "text"})
_CALL_TYPES = frozenset({"function_call", "custom_tool_call"})
_RESULT_TYPES = frozenset({"function_call_output", "custom_tool_call_output"})


def _label(value: Any) -> str:
    """Keep source-type labels short and avoid inserting arbitrary text in reports."""
    if (
        isinstance(value, str)
        and value
        and len(value) <= 80
        and all(c.isascii() and (c.isalnum() or c in "_-") for c in value)
    ):
        return value
    return "(untyped)"


def _timestamp(value: Any, fidelity: FidelityReport) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value)
            return value
        except ValueError:
            pass
    fidelity.invalid_source_timestamps += 1
    return None


def _ignore_fields(
    value: dict[str, Any], consumed: set[str], prefix: str, fidelity: FidelityReport
) -> None:
    for field in value:
        if field not in consumed:
            fidelity.count_ignored_field(f"{prefix}{field}")


def _text_parts(
    value: Any, fidelity: FidelityReport, *, prefix: str
) -> list[ContentPart]:
    if not isinstance(value, list):
        fidelity.count_unsupported_block(
            f"{prefix}(non-list)", with_content=value is not None
        )
        return []
    parts: list[ContentPart] = []
    for part in value:
        if not isinstance(part, dict):
            fidelity.count_unsupported_block(f"{prefix}(non-object)", with_content=True)
            continue
        kind = part.get("type")
        if (
            isinstance(kind, str)
            and kind in _TEXT_TYPES
            and isinstance(part.get("text"), str)
        ):
            parts.append(ContentPart(type="text", text=part["text"]))
            _ignore_fields(part, {"type", "text"}, f"{prefix}content.", fidelity)
        else:
            fidelity.count_unsupported_block(
                f"{prefix}{_label(kind)}", with_content=True
            )
    return parts


def _result_content(
    value: Any, fidelity: FidelityReport
) -> str | list[ContentPart] | None:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, list):
        return _text_parts(value, fidelity, prefix="tool_output/")
    # Preserve unusual structured outputs as JSON text, without inventing a status.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _call_arguments(
    payload: dict[str, Any], kind: str
) -> tuple[dict[str, Any] | None, bool]:
    field = "arguments" if kind == "function_call" else "input"
    if field not in payload:
        return None, False
    value = payload[field]
    if kind == "custom_tool_call":
        return {"input": value}, True
    if isinstance(value, str):
        try:
            parsed = json.loads(
                value,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
                parse_float=_finite_float,
            )
        except (json.JSONDecodeError, ValueError):
            return {"input": value}, True
    else:
        parsed = value
    if isinstance(parsed, dict):
        return parsed, False
    return {"value": parsed}, True


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or Decimal(str(parsed)) != Decimal(value):
        raise ValueError("JSON number cannot be represented without decimal loss")
    return parsed


def _source(role: Any) -> Literal["user", "agent", "system"] | None:
    if role == "user":
        return "user"
    if role == "assistant":
        return "agent"
    if role in ("system", "developer"):
        return "system"
    return None


def parse_codex_jsonl(file_stream: TextIO) -> Trajectory:
    """Read Codex rollout records in source order and attach results by call ID.

    Duplicate call IDs are ambiguous: retain the first call, report the later
    call, and never guess where subsequent results belong. No commands run.
    """
    steps: list[Step] = []
    call_steps: dict[str, Step] = {}
    call_kinds: dict[str, str] = {}
    ambiguous_calls: set[str] = set()
    seen_items: set[tuple[str, str]] = set()
    session_id: str | None = None
    version = "unknown"
    fidelity = FidelityReport()
    normalized_arguments = False
    normalized_developer = False
    normalized_results = False
    normalized_structured_output = False
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
        payload = record.get("payload")
        if record_type == "session_meta" and isinstance(payload, dict):
            ids = [
                payload.get(key)
                for key in ("id", "session_id")
                if isinstance(payload.get(key), str) and payload.get(key)
            ]
            if len(set(ids)) > 1:
                fidelity.count_unsupported_record(
                    "session_meta (conflicting id)", "unrecognized"
                )
                continue
            sid = ids[0] if ids else None
            if isinstance(sid, str) and sid:
                if session_id is not None and session_id != sid:
                    fidelity.count_unsupported_record(
                        "session_meta (conflicting id)", "unrecognized"
                    )
                    continue
                session_id = sid
            if version == "unknown" and isinstance(payload.get("cli_version"), str):
                version = payload["cli_version"] or "unknown"
            _ignore_fields(
                payload, {"id", "session_id", "cli_version"}, "payload.", fidelity
            )
            _ignore_fields(record, {"type", "timestamp", "payload"}, "", fidelity)
            if record.get("timestamp") is not None:
                fidelity.count_ignored_field("timestamp")
            fidelity.source_records_preserved += 1
            continue
        if record_type != "response_item" or not isinstance(payload, dict):
            subtype = payload.get("type") if isinstance(payload, dict) else None
            label = _label(record_type)
            if subtype is not None:
                label += "/" + _label(subtype)
            fidelity.count_unsupported_record(label, "unrecognized")
            continue

        kind = payload.get("type")
        if not isinstance(kind, str) or kind not in {
            "message",
            *_CALL_TYPES,
            *_RESULT_TYPES,
        }:
            fidelity.count_unsupported_record(
                f"response_item/{_label(kind)}", "unrecognized"
            )
            continue
        item_id = payload.get("id")
        if isinstance(item_id, str) and item_id:
            key = (kind, item_id)
            if key in seen_items:
                repeated_call_id = payload.get("call_id")
                if (
                    kind in _CALL_TYPES
                    and isinstance(repeated_call_id, str)
                    and repeated_call_id in call_steps
                ):
                    ambiguous_calls.add(repeated_call_id)
                fidelity.count_unsupported_record(
                    f"response_item/{kind} (duplicate id)", "unrecognized"
                )
                continue
            seen_items.add(key)

        if kind == "message":
            role = payload.get("role")
            source = _source(role)
            if source is None:
                fidelity.count_unsupported_record(
                    "response_item/message (unsupported role)", "unrecognized"
                )
                continue
            content = payload.get("content")
            if isinstance(content, str):
                text: str | list[ContentPart] = content
            else:
                text = _text_parts(content, fidelity, prefix="")
                # A single text block has the same simple string representation as Claude.
                if len(text) == 1:
                    text = text[0].text or ""
            steps.append(
                Step(
                    step_id=len(steps) + 1,
                    timestamp=_timestamp(record.get("timestamp"), fidelity),
                    source=source,
                    message=text,
                    extra={"agent_session_bridge": {"source_line": line_number}},
                )
            )
            normalized_developer = normalized_developer or role == "developer"
            consumed = {"type", "role", "content"}
        elif kind in _CALL_TYPES:
            call_id, name = payload.get("call_id"), payload.get("name")
            arguments, wrapped = _call_arguments(payload, kind)
            if (
                not isinstance(call_id, str)
                or not call_id.strip()
                or not isinstance(name, str)
                or not name.strip()
                or arguments is None
            ):
                fidelity.count_unsupported_record(
                    f"response_item/{kind} (malformed)", "unrecognized"
                )
                continue
            if call_id in call_steps:
                ambiguous_calls.add(call_id)
                fidelity.count_unsupported_record(
                    f"response_item/{kind} (duplicate call id)", "unrecognized"
                )
                continue
            step = Step(
                step_id=len(steps) + 1,
                timestamp=_timestamp(record.get("timestamp"), fidelity),
                source="agent",
                message="",
                tool_calls=[
                    ToolCall(
                        tool_call_id=call_id, function_name=name, arguments=arguments
                    )
                ],
                extra={"agent_session_bridge": {"source_line": line_number}},
            )
            steps.append(step)
            call_steps[call_id] = step
            call_kinds[call_id] = kind
            fidelity.tool_calls_preserved += 1
            normalized_arguments = normalized_arguments or wrapped
            consumed = {
                "type",
                "name",
                "call_id",
                "arguments" if kind == "function_call" else "input",
            }
        else:
            call_id = payload.get("call_id")
            source_step = call_steps.get(call_id) if isinstance(call_id, str) else None
            expected_call = (
                "function_call"
                if kind == "function_call_output"
                else "custom_tool_call"
            )
            if (
                not isinstance(call_id, str)
                or source_step is None
                or call_id in ambiguous_calls
                or call_kinds.get(call_id) != expected_call
            ):
                fidelity.orphaned_tool_results += 1
                continue
            if "output" not in payload:
                fidelity.count_unsupported_record(
                    f"response_item/{kind} (missing output)", "unrecognized"
                )
                continue
            content = _result_content(payload["output"], fidelity)
            normalized_structured_output = (
                normalized_structured_output
                or not isinstance(payload["output"], (str, list, type(None)))
            )
            if source_step.observation is None:
                source_step.observation = Observation(results=[])
            source_step.observation.results.append(
                ObservationResult(
                    source_call_id=call_id,
                    content=content,
                    extra={"agent_session_bridge": {"outcome": "unknown"}},
                )
            )
            fidelity.observation_results_preserved += 1
            if _timestamp(record.get("timestamp"), fidelity) is not None:
                fidelity.omitted_tool_result_timestamps += 1
            normalized_results = True
            consumed = {"type", "call_id", "output"}

        fidelity.source_records_preserved += 1
        _ignore_fields(record, {"type", "timestamp", "payload"}, "", fidelity)
        _ignore_fields(payload, consumed, "payload.", fidelity)

    fidelity.sort_breakdowns()
    if normalized_arguments:
        fidelity.transformations.append(
            "Wrapped non-object or custom tool input in ATIF arguments."
        )
    if normalized_developer:
        fidelity.transformations.append(
            "Mapped Codex developer messages to ATIF system steps."
        )
    if normalized_results:
        fidelity.transformations.append(
            "Moved Codex tool outputs to call-correlated ATIF observations."
        )
    if normalized_structured_output:
        fidelity.transformations.append(
            "Serialized non-text tool outputs as JSON text."
        )

    return Trajectory(
        schema_version="ATIF-v1.7",
        session_id=session_id,
        agent=Agent(name="codex", version=version, extra={"provider": "openai"}),
        steps=steps,
        extra=asb_extension(
            original_format="codex-rollout-jsonl",
            converted_by="trajectory-fidelity-bridge",
            conversion_timestamp=datetime.now(UTC).isoformat(),
            fidelity=fidelity,
            workspace=None,
        ),
    )
