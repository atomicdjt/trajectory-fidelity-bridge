"""Render an ATIF trajectory as a deterministic Markdown account.

Honesty rules the renderer keeps:

* Every value comes from the ATIF document or from an explicitly labelled sidecar
  manifest. Nothing is inferred, and no clock is read, so the same input always gives
  the same bytes.
* Source-level facts that ATIF does not carry (source hash, converter version, capture
  time) are shown only when the manifest supplies them, and are otherwise listed as
  not available.
* The "could not preserve" section reports what the converter counted in
  ``extra.agent_session_bridge.fidelity``. It does not guess at losses the converter
  did not count.
* Trace text only ever appears inside code fences or inline code spans, so it cannot
  become Markdown structure.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from atif import ContentPart, Step, ToolCall, Trajectory

from bridge.tool_results import tool_result_is_error

DEFAULT_MAX_CHARS = 2000

# Facts a manifest may supply. Anything else is rejected, so a manifest cannot smuggle
# arbitrary content into the report.
_MANIFEST_FIELDS = {
    "source_sha256": "Source file SHA-256",
    "claude_code_version": "Claude Code version (per manifest)",
    "converter_version": "Converter version",
    "capture_time": "Capture time",
    "note": "Note",
}
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_REDACTION_MARKER = re.compile(r"\[REDACTED\]|xox\?-\*\*\*REDACTED\*\*\*")

_CATEGORY_TITLES = {
    "bookkeeping": "session-metadata record(s)",
    "text_bearing": "record(s) that may hold content",
    "unrecognized": "unrecognized or malformed record(s)",
}


class ManifestError(ValueError):
    """The sidecar manifest is not usable."""


def load_manifest(path: str | Path) -> dict[str, str]:
    """Read and validate a sidecar manifest of source-level facts."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestError(f"cannot read manifest {path}: {error}") from error
    return validate_manifest(raw)


def validate_manifest(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ManifestError("manifest must be a JSON object")
    unknown = sorted(set(raw) - set(_MANIFEST_FIELDS))
    if unknown:
        raise ManifestError(
            f"unknown manifest field(s): {', '.join(unknown)}; "
            f"allowed: {', '.join(sorted(_MANIFEST_FIELDS))}"
        )
    manifest: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(value, str) or not value.strip():
            raise ManifestError(f"manifest field {key!r} must be a non-empty string")
        if key == "source_sha256" and not _SHA256.match(value):
            raise ManifestError("source_sha256 must be 64 hexadecimal characters")
        if key == "capture_time":
            try:
                datetime.fromisoformat(value)
            except ValueError as error:
                raise ManifestError("capture_time must be an ISO 8601 timestamp") from error
        manifest[key] = value
    return manifest


def render_report(
    trajectory: Trajectory,
    *,
    manifest: dict[str, str] | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Return the Markdown report. ``max_chars <= 0`` disables truncation."""
    validated = validate_manifest(manifest) if manifest is not None else None
    bridge = _bridge(trajectory)
    fidelity = bridge.get("fidelity")
    fidelity = fidelity if isinstance(fidelity, dict) else None

    lines: list[str] = [
        "# Agent session report",
        "",
        ("Generated from an ATIF trajectory by `agent-session explain`. Each value comes "
        "from the ATIF document or from the optional manifest, and is labelled with which. "
        "Nothing here is inferred, and the report contains no time of its own."),
        "",
    ]
    lines += _summary(trajectory)
    lines += _provenance(trajectory, bridge, validated)
    lines += _timeline(trajectory, max_chars)
    lines += _tool_call_table(trajectory)
    lines += _token_usage(trajectory)
    lines += _limits(trajectory, fidelity)
    return "\n".join(lines).rstrip("\n") + "\n"


# --- small Markdown helpers -------------------------------------------------------


def _one_line(value: object) -> str:
    return " ".join(str(value).split())


def _code(value: object) -> str:
    """Inline code span that survives backticks and never spans lines."""
    text = _one_line(value)
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    ticks = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{ticks}{pad}{text}{pad}{ticks}"


def _fence(text: str, info: str = "") -> list[str]:
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    ticks = "`" * max(3, longest + 1)
    return [f"{ticks}{info}", text, ticks]


def _clip(text: str, max_chars: int) -> tuple[str, str | None]:
    if max_chars <= 0 or len(text) <= max_chars:
        return text, None
    return text[:max_chars], (
        f"_Truncated: first {max_chars} of {len(text)} characters shown. "
        "Use `--max-chars 0` for the full text._"
    )


def _cell(value: object) -> str:
    """Inline code for a table cell; an unescaped pipe would end the cell."""
    return _code(value).replace("|", "\\|")


def _count(source: dict[str, Any] | None, key: str) -> int | None:
    if source is None:
        return None
    value = source.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _entries(source: dict[str, Any] | None, key: str) -> list[dict[str, Any]] | None:
    if source is None or not isinstance(source.get(key), list):
        return None
    return [entry for entry in source[key] if isinstance(entry, dict)]


def _bridge(trajectory: Trajectory) -> dict[str, Any]:
    bridge = (trajectory.extra or {}).get("agent_session_bridge")
    return bridge if isinstance(bridge, dict) else {}


def _step_source(step: Step) -> dict[str, Any]:
    bridge = (step.extra or {}).get("agent_session_bridge")
    return bridge if isinstance(bridge, dict) else {}


def _content_text(content: str | list[ContentPart] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        if part.type == "text" and part.text is not None:
            parts.append(part.text)
        else:
            parts.append(f"[{part.type} content part not shown in this report]")
    return "\n".join(parts)


def _is_error(result_extra: dict[str, Any] | None) -> bool:
    return tool_result_is_error(result_extra)


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


# --- sections -----------------------------------------------------------------------


def _calls(step: Step) -> list[ToolCall]:
    return list(step.tool_calls or [])


def _call_status(step: Step, call: ToolCall) -> str:
    """``result``, ``error``, or ``no result`` for one call, by ID correlation."""
    results = [
        result
        for result in (step.observation.results if step.observation else [])
        if result.source_call_id == call.tool_call_id
    ]
    if not results:
        return "no result"
    return "error" if any(_is_error(result.extra) for result in results) else "result"


def _summary(trajectory: Trajectory) -> list[str]:
    steps = trajectory.steps
    by_source = {
        source: sum(1 for step in steps if step.source == source)
        for source in ("user", "agent", "system")
    }
    statuses = [_call_status(step, call) for step in steps for call in _calls(step)]
    timestamps = [step.timestamp for step in steps if step.timestamp]
    models = sorted({step.model_name for step in steps if step.model_name})

    lines = ["## Summary", ""]
    lines.append(
        f"- Steps: {len(steps)} (user {by_source['user']}, agent {by_source['agent']}, "
        f"system {by_source['system']})"
    )
    lines.append(
        f"- Tool calls: {len(statuses)} — {statuses.count('result')} with a result, "
        f"{statuses.count('error')} with an error result, {statuses.count('no result')} "
        "with no result recorded"
    )
    lines.append(
        "- Models named on steps: "
        + (", ".join(_code(model) for model in models) if models else "none recorded")
    )
    if timestamps:
        lines.append(
            f"- First and last step timestamps, in step order: {_code(timestamps[0])} and "
            f"{_code(timestamps[-1])}. These are observed points; no durations are derived."
        )
    else:
        lines.append("- Step timestamps: none recorded")
    lines.append("")
    return lines


def _provenance(
    trajectory: Trajectory, bridge: dict[str, Any], manifest: dict[str, str] | None
) -> list[str]:
    provenance = bridge.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    workspace = bridge.get("workspace")
    workspace = workspace if isinstance(workspace, dict) else {}
    agent = trajectory.agent

    rows: list[tuple[str, object]] = [("ATIF schema version", trajectory.schema_version)]
    if trajectory.session_id:
        rows.append(("Session ID", trajectory.session_id))
    rows.append(("Agent", f"{agent.name} {agent.version}"))
    provider = (agent.extra or {}).get("provider")
    if provider:
        rows.append(("Provider (recorded on the agent)", provider))
    for label, key in (
        ("Original format", "original_format"),
        ("Converted by", "converted_by"),
        ("Conversion timestamp", "conversion_timestamp"),
    ):
        if provenance.get(key):
            rows.append((label, provenance[key]))
    repository = workspace.get("repository")
    if isinstance(repository, dict) and repository.get("branch"):
        rows.append(("Source git branch", repository["branch"]))
    if workspace.get("cwd"):
        rows.append(("Source working directory", workspace["cwd"]))

    lines = ["## Provenance", "", "### Recorded in the ATIF document", ""]
    lines += ["| Fact | Value |", "| --- | --- |"]
    lines += [f"| {label} | {_cell(value)} |" for label, value in rows]
    if not provenance:
        lines += [
            "",
            ("This document has no `extra.agent_session_bridge.provenance`, so it was not "
            "produced by Trajectory Fidelity Bridge or carries no TFB provenance."),
        ]
    lines.append("")

    if manifest:
        lines += [
            "### Supplied by the manifest (not verified by this report)",
            "",
            "| Fact | Value |",
            "| --- | --- |",
        ]
        lines += [
            f"| {_MANIFEST_FIELDS[key]} | {_cell(manifest[key])} |"
            for key in _MANIFEST_FIELDS
            if key in manifest
        ]
        claimed = manifest.get("claude_code_version")
        if claimed and claimed != agent.version:
            lines += [
                "",
                (f"The manifest names Claude Code version {_code(claimed)}, which differs "
                f"from the version recorded in the ATIF document ({_code(agent.version)})."),
            ]
        lines.append("")

    missing = [
        label
        for key, label in (
            ("source_sha256", "Source file SHA-256"),
            ("converter_version", "Converter version"),
            ("capture_time", "Capture time"),
        )
        if not (manifest and key in manifest)
    ]
    if missing:
        lines += [
            "### Not available",
            "",
            "ATIF does not carry these source-level facts, and no manifest supplied them: "
            + ", ".join(missing)
            + ". They are omitted, not inferred. Pass `--manifest` to supply them.",
            "",
        ]
    return lines


def _step_heading(step: Step) -> str:
    parts = [f"Step {step.step_id}", step.source]
    if step.timestamp:
        parts.append(_code(step.timestamp))
    if step.model_name:
        parts.append(f"model {_code(step.model_name)}")
    return "### " + " · ".join(parts)


def _timeline(trajectory: Trajectory, max_chars: int) -> list[str]:
    lines = ["## Timeline", ""]
    if not trajectory.steps:
        return lines + ["The trajectory has no steps.", ""]

    steps_by_message: dict[str, list[int]] = {}
    for step in trajectory.steps:
        message_id = _step_source(step).get("source_message_id")
        if isinstance(message_id, str):
            steps_by_message.setdefault(message_id, []).append(step.step_id)

    for step in trajectory.steps:
        lines += [_step_heading(step), ""]
        source = _step_source(step)
        notes: list[str] = []
        if "source_line" in source:
            notes.append(f"source line {source['source_line']}")
        message_id = source.get("source_message_id")
        if isinstance(message_id, str):
            notes.append(f"API response {_code(message_id)}")
            siblings = [n for n in steps_by_message.get(message_id, []) if n != step.step_id]
            if siblings:
                notes.append(
                    "shares that response with step" + ("s " if len(siblings) > 1 else " ")
                    + ", ".join(str(n) for n in siblings)
                )
        if notes:
            lines += ["_" + "; ".join(notes) + "_", ""]

        text = _content_text(step.message)
        calls = _calls(step)
        if text.strip():
            clipped, note = _clip(text, max_chars)
            lines += _fence(clipped, "text") + [""]
            if note:
                lines += [note, ""]
        elif not calls:
            lines += ["_No message text and no tool calls in this step._", ""]

        for call in calls:
            lines += _render_call(step, call, max_chars)
        lines += _render_unmatched_results(step, calls, max_chars)

        if step.metrics and step.metrics.prompt_tokens is not None:
            metrics = step.metrics
            lines += [
                (f"_Tokens: prompt {metrics.prompt_tokens} (cached {metrics.cached_tokens}), "
                f"completion {metrics.completion_tokens}_"),
                "",
            ]
    return lines


def _render_call(step: Step, call: ToolCall, max_chars: int) -> list[str]:
    lines = [f"**Tool call** {_code(call.function_name)} (call ID {_code(call.tool_call_id)})", ""]
    arguments = json.dumps(call.arguments, indent=2, ensure_ascii=False)
    clipped, note = _clip(arguments, max_chars)
    lines += _fence(clipped, "json") + [""]
    if note:
        lines += [note, ""]

    results = [
        result
        for result in (step.observation.results if step.observation else [])
        if result.source_call_id == call.tool_call_id
    ]
    if not results:
        return lines + ["**Result:** none recorded for this call ID.", ""]
    for result in results:
        heading = "**Result (error):**" if _is_error(result.extra) else "**Result:**"
        lines += [heading, ""]
        content = _content_text(result.content)
        if not content.strip():
            lines += ["_Empty result._", ""]
            continue
        clipped, note = _clip(content, max_chars)
        lines += _fence(clipped, "text") + [""]
        if note:
            lines += [note, ""]
    return lines


def _render_unmatched_results(step: Step, calls: list[ToolCall], max_chars: int) -> list[str]:
    known = {call.tool_call_id for call in calls}
    unmatched = [
        result
        for result in (step.observation.results if step.observation else [])
        if result.source_call_id not in known
    ]
    lines: list[str] = []
    for result in unmatched:
        call_id = result.source_call_id
        lines += [
            "**Observation not matched to a tool call on this step"
            + (f" (source call ID {_code(call_id)})" if call_id else " (no source call ID)")
            + ":**",
            "",
        ]
        clipped, note = _clip(_content_text(result.content), max_chars)
        lines += _fence(clipped, "text") + [""]
        if note:
            lines += [note, ""]
    return lines


def _tool_call_table(trajectory: Trajectory) -> list[str]:
    rows = [
        (step.step_id, call, _call_status(step, call))
        for step in trajectory.steps
        for call in _calls(step)
    ]
    lines = ["## Tool calls and results", ""]
    if not rows:
        return lines + ["No tool calls in this trajectory.", ""]
    lines += ["| Step | Tool | Call ID | Outcome |", "| --- | --- | --- | --- |"]
    lines += [
        f"| {step_id} | {_cell(call.function_name)} | {_cell(call.tool_call_id)} | {status} |"
        for step_id, call, status in rows
    ]
    lines += [
        "",
        ("Outcome is judged from the ATIF document: `error` when the correlated result carries "
        "a recognized `is_error` (TFB) or `tool_result_is_error` (Harbor Claude) flag, "
        "`result` when a result is present without one. These flags are converter "
        "conventions, not standard ATIF status fields."),
        "",
    ]
    return lines


def _token_usage(trajectory: Trajectory) -> list[str]:
    all_metrics = [step.metrics for step in trajectory.steps if step.metrics]
    counted = [m for m in all_metrics if m.prompt_tokens is not None]
    if not counted:
        return []
    prompt = sum(m.prompt_tokens or 0 for m in counted)
    cached = sum(m.cached_tokens or 0 for m in counted)
    completion = sum(m.completion_tokens or 0 for m in counted)
    lines = [
        "## Token usage",
        "",
        f"Summed over {_plural(len(counted), 'step')} that carry metrics (tokens):",
        "",
        f"- Prompt tokens, including cached: {prompt}",
        f"- Of which cached: {cached}",
        f"- Completion tokens: {completion}",
    ]
    created = 0
    has_created = False
    for metrics in counted:
        value = (metrics.extra or {}).get("cache_creation_input_tokens")
        if isinstance(value, int) and not isinstance(value, bool):
            created += value
            has_created = True
    if has_created:
        lines.append(f"- Of the prompt tokens, written to the prompt cache: {created}")
    lines += [
        "",
        "No monetary cost is shown: the document carries none, and none is computed.",
        "",
    ]
    return lines


def _redaction_markers(trajectory: Trajectory) -> int:
    total = 0
    for step in trajectory.steps:
        total += len(_REDACTION_MARKER.findall(_content_text(step.message)))
        for call in _calls(step):
            total += len(_REDACTION_MARKER.findall(json.dumps(call.arguments, ensure_ascii=False)))
        for result in step.observation.results if step.observation else []:
            total += len(_REDACTION_MARKER.findall(_content_text(result.content)))
    return total


def _limits(trajectory: Trajectory, fidelity: dict[str, Any] | None) -> list[str]:
    lines = ["## What this conversion could not preserve", ""]
    if fidelity is None:
        return lines + [
            ("This document has no `extra.agent_session_bridge.fidelity` report, so what the "
            "conversion dropped or changed cannot be determined from it. That is not evidence "
            "that nothing was lost."),
            "",
        ]

    lost: list[str] = []
    represented: list[str] = []

    # Source records that were not converted.
    total_records = _count(fidelity, "unsupported_source_records")
    record_types = _entries(fidelity, "unsupported_record_types")
    if record_types is None:
        if total_records:
            lost.append(
                f"- Source records not converted: {total_records}. This converter version "
                "did not report which kinds, so bookkeeping cannot be told apart from content."
            )
    else:
        for category in ("text_bearing", "unrecognized", "bookkeeping"):
            group = [e for e in record_types if e.get("category") == category]
            count = sum(e["records"] for e in group if isinstance(e.get("records"), int))
            if not group:
                continue
            kinds = ", ".join(f"{_code(e.get('type'))} ×{e.get('records')}" for e in group)
            line = f"- **{count} {_CATEGORY_TITLES[category]}** not converted: {kinds}."
            if category == "bookkeeping":
                line += " No text-bearing field was observed on these types."
            elif category == "text_bearing":
                line += (
                    " These types carry text fields (for example context supplied to the "
                    "model, echoed prompts, or hook output). TFB does not convert them and "
                    "cannot show they held nothing that mattered."
                )
            else:
                line += " Treated as possible content loss."
            lost.append(line)

    # Content blocks that were not converted.
    total_blocks = _count(fidelity, "unsupported_source_blocks")
    block_types = _entries(fidelity, "unsupported_block_types")
    if block_types is None:
        if total_blocks:
            lost.append(
                f"- Content blocks not converted: {total_blocks}. This converter version "
                "did not report their types."
            )
    else:
        for entry in block_types:
            blocks = entry.get("blocks")
            with_content = entry.get("with_content")
            kind = _code(entry.get("type"))
            if with_content == 0:
                detail = "none carried content; the block held no text of its own"
                if entry.get("type") == "thinking":
                    detail = "none had any text; each held only an opaque signature"
            else:
                detail = f"{with_content} carried content that is absent from the trajectory"
            lost.append(f"- {kind} blocks not converted: {blocks}; {detail}.")

    # Fields on converted records that ATIF has no place for.
    ignored = _entries(fidelity, "ignored_fields")
    if ignored:
        lines_fields = ", ".join(f"{_code(e.get('field'))} ({e.get('records')})" for e in ignored)
        lost.append(
            "- Fields present on converted source records but not carried into the trajectory "
            f"(records affected in parentheses; values are not preserved): {lines_fields}."
        )

    timestamps = _count(fidelity, "omitted_tool_result_timestamps")
    if timestamps:
        lost.append(
            f"- Tool-result timestamps not represented: {timestamps}. ATIF v1.7 observation "
            "results have no timestamp field, and none was invented."
        )
    invalid = _count(fidelity, "invalid_source_timestamps")
    if invalid:
        lost.append(f"- Source timestamps that were not valid ISO 8601 (omitted): {invalid}.")
    orphaned = _count(fidelity, "orphaned_tool_results")
    if orphaned:
        lost.append(f"- Tool results that matched no tool call (not attached): {orphaned}.")
    conflicting = _count(fidelity, "conflicting_usage_records")
    if conflicting:
        lost.append(
            "- Records that repeated a response's token usage with different numbers "
            f"(the first record's numbers were kept): {conflicting}."
        )

    # Changes that are not losses.
    duplicates = _count(fidelity, "duplicate_usage_records")
    if duplicates:
        represented.append(
            "- Records that repeated an earlier record's token usage for the same API "
            f"response (counted once): {duplicates}."
        )
    synthetic = _count(fidelity, "synthetic_agent_records")
    if synthetic:
        represented.append(
            "- Agent steps from client-generated messages (model `<synthetic>`, not model "
            f"output; no model name or token metrics): {synthetic}."
        )
    markers = _redaction_markers(trajectory)
    if markers:
        represented.append(
            "- Redaction markers in message, argument, or result text (the original text "
            f"is not recoverable from this document): {markers}."
        )

    converted = _count(fidelity, "source_records_preserved")
    if converted is not None:
        lines.append(
            f"Source records the converter reports as converted: {converted}. Steps in this "
            f"document: {len(trajectory.steps)}."
        )
        lines.append("")

    lines += ["### Lost or not carried", ""]
    lines += lost or ["- The fidelity report counts nothing lost."]
    lines.append("")
    if represented:
        lines += ["### Changed but not lost", ""] + represented + [""]

    transformations = [t for t in fidelity.get("transformations") or [] if isinstance(t, str)]
    if transformations:
        lines += ["### Transformations recorded by the converter", ""]
        lines += [f"- {_one_line(text)}" for text in transformations]
        lines += [
            "",
            ("Quoted from the converter as written. This report does not judge whether "
            "each one lost information."),
            "",
        ]

    lines += ["### Consistency checks", ""]
    lines += _consistency(trajectory, fidelity)
    lines += [
        "",
        "### Limits of this section",
        "",
        ("It lists only what the converter counted. Fields and blocks are counted, not "
        "their values, and a loss the converter did not count cannot appear here."),
        "",
    ]
    return lines


def _consistency(trajectory: Trajectory, fidelity: dict[str, Any]) -> list[str]:
    document_calls = sum(len(_calls(step)) for step in trajectory.steps)
    document_results = sum(
        len(step.observation.results) for step in trajectory.steps if step.observation
    )
    lines = []
    for label, reported, actual in (
        ("Tool calls", _count(fidelity, "tool_calls_preserved"), document_calls),
        ("Observation results", _count(fidelity, "observation_results_preserved"), document_results),
    ):
        if reported is None:
            lines.append(f"- {label}: the fidelity report gives no count to compare.")
        elif reported == actual:
            lines.append(f"- {label}: the fidelity report ({reported}) matches the document ({actual}).")
        else:
            lines.append(
                f"- {label}: **mismatch** — the fidelity report says {reported}, the document "
                f"contains {actual}."
            )
    return lines
