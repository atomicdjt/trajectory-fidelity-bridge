"""Fidelity breakdown, model, and usage mapping for Claude Code records.

Every record below is synthetic; only the shapes follow real Claude Code 2.1.x logs.
"""

import io
import json
from typing import Any

from atif import Trajectory

from adapters.claude.parser import parse_claude_jsonl
from security.redact import redact_trajectory


def _parse(*records: Any) -> Trajectory:
    lines = [record if isinstance(record, str) else json.dumps(record) for record in records]
    return parse_claude_jsonl(io.StringIO("\n".join(lines)))


def _fidelity(trajectory: Trajectory) -> dict[str, Any]:
    assert trajectory.extra is not None
    fidelity = trajectory.extra["agent_session_bridge"]["fidelity"]
    assert isinstance(fidelity, dict)
    return fidelity


def _user(text: str = "hello", **extra: Any) -> dict[str, Any]:
    return {
        "type": "user",
        "timestamp": "2026-01-01T00:00:00Z",
        "sessionId": "s",
        "message": {"role": "user", "content": text},
        **extra,
    }


def _assistant(
    blocks: list[dict[str, Any]],
    *,
    message_id: str | None = "msg_1",
    model: str | None = "claude-test-1",
    usage: Any = None,
    **message_extra: Any,
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": blocks, **message_extra}
    if message_id is not None:
        message["id"] = message_id
    if model is not None:
        message["model"] = model
    if usage is not None:
        message["usage"] = usage
    return {"type": "assistant", "timestamp": "2026-01-01T00:00:01Z", "message": message}


TEXT = [{"type": "text", "text": "ok"}]
USAGE = {
    "input_tokens": 2,
    "cache_read_input_tokens": 100,
    "cache_creation_input_tokens": 50,
    "output_tokens": 7,
}


def test_unsupported_records_are_split_by_type_and_category():
    trajectory = _parse(
        _user(),
        {"type": "file-history-snapshot", "snapshot": {}},
        {"type": "ai-title", "aiTitle": "t"},
        {"type": "attachment", "attachment": {"type": "date"}},
        {"type": "last-prompt", "lastPrompt": "hello"},
        {"type": "system", "subtype": "turn_duration", "durationMs": 5},
        {"type": "system", "subtype": "compact_boundary", "content": "x"},
        {"type": "system", "subtype": "brand_new_subtype"},
        {"type": "brand-new-record"},
        "not json",
        "[1, 2]",
    )
    fidelity = _fidelity(trajectory)
    by_type = {
        entry["type"]: (entry["category"], entry["records"])
        for entry in fidelity["unsupported_record_types"]
    }
    assert by_type == {
        "(malformed JSON line)": ("unrecognized", 1),
        "(non-object JSON value)": ("unrecognized", 1),
        "ai-title": ("bookkeeping", 1),
        "attachment": ("text_bearing", 1),
        "brand-new-record": ("unrecognized", 1),
        "file-history-snapshot": ("bookkeeping", 1),
        "last-prompt": ("text_bearing", 1),
        "system/brand_new_subtype": ("unrecognized", 1),
        "system/compact_boundary": ("text_bearing", 1),
        "system/turn_duration": ("bookkeeping", 1),
    }
    assert fidelity["unsupported_source_records"] == sum(v[1] for v in by_type.values())
    assert [e["type"] for e in fidelity["unsupported_record_types"]] == sorted(by_type)


def test_thinking_block_content_loss_depends_on_the_block():
    trajectory = _parse(
        _user(),
        _assistant([{"type": "thinking", "thinking": "", "signature": "opaque"}], message_id="a"),
        _assistant(
            [{"type": "thinking", "thinking": "visible reasoning", "signature": "s"}],
            message_id="b",
        ),
        _assistant([{"type": "mystery", "data": "x"}], message_id="c"),
    )
    fidelity = _fidelity(trajectory)
    blocks = {e["type"]: (e["blocks"], e["with_content"]) for e in fidelity["unsupported_block_types"]}
    assert blocks == {"thinking": (2, 1), "mystery": (1, 1)}
    assert fidelity["unsupported_source_blocks"] == 3


def test_fields_on_converted_records_that_are_not_carried_are_counted():
    trajectory = _parse(
        _user(uuid="u1", parentUuid=None),
        _assistant(TEXT, stop_reason="end_turn", usage=USAGE),
    )
    ignored = {e["field"]: e["records"] for e in _fidelity(trajectory)["ignored_fields"]}
    assert ignored == {"uuid": 1, "parentUuid": 1, "message.stop_reason": 1}


def test_usage_maps_to_atif_prompt_completion_and_cached_tokens():
    trajectory = _parse(_user(), _assistant(TEXT, usage=USAGE))
    step = trajectory.steps[1]

    assert step.model_name == "claude-test-1"
    assert step.metrics is not None
    # ATIF prompt_tokens includes cached tokens; Anthropic input_tokens does not.
    assert step.metrics.prompt_tokens == 152
    assert step.metrics.cached_tokens == 100
    assert step.metrics.completion_tokens == 7
    assert step.metrics.cost_usd is None
    assert step.metrics.extra == {
        "uncached_input_tokens": 2,
        "cache_creation_input_tokens": 50,
    }
    assert Trajectory.model_validate(json.loads(trajectory.model_dump_json())).steps[1].metrics


def test_usage_repeated_across_content_blocks_of_one_response_is_counted_once():
    trajectory = _parse(
        _user(),
        _assistant([{"type": "thinking", "thinking": "", "signature": "s"}], usage=USAGE),
        _assistant([{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}], usage=USAGE),
        _assistant(TEXT, message_id="msg_2", usage=USAGE),
    )
    metrics = [step.metrics for step in trajectory.steps]

    assert metrics[1] is not None and metrics[2] is None and metrics[3] is not None
    assert sum(m.prompt_tokens or 0 for m in metrics if m) == 2 * 152
    assert [s.model_name for s in trajectory.steps[1:]] == ["claude-test-1"] * 3
    assert _fidelity(trajectory)["duplicate_usage_records"] == 1
    assert _fidelity(trajectory)["conflicting_usage_records"] == 0


def test_differing_usage_within_one_response_is_reported_not_merged():
    changed = {**USAGE, "output_tokens": 99}
    trajectory = _parse(_user(), _assistant(TEXT, usage=USAGE), _assistant(TEXT, usage=changed))

    assert trajectory.steps[1].metrics is not None
    assert trajectory.steps[1].metrics.completion_tokens == 7
    assert trajectory.steps[2].metrics is None
    assert _fidelity(trajectory)["conflicting_usage_records"] == 1


def test_client_generated_synthetic_message_gets_no_model_or_metrics():
    zero = {"input_tokens": 0, "output_tokens": 0}
    trajectory = _parse(_user(), _assistant(TEXT, model="<synthetic>", usage=zero))

    assert trajectory.steps[1].model_name is None
    assert trajectory.steps[1].metrics is None
    assert _fidelity(trajectory)["synthetic_agent_records"] == 1


def test_invalid_usage_values_are_not_turned_into_metrics():
    for bad in ({"input_tokens": -1, "output_tokens": 1}, {"input_tokens": True, "output_tokens": 1},
                {"input_tokens": "2", "output_tokens": 1}, {"output_tokens": 1}, "usage"):
        trajectory = _parse(_user(), _assistant(TEXT, usage=bad))
        assert trajectory.steps[1].model_name == "claude-test-1"
        assert trajectory.steps[1].metrics is None


def test_missing_model_and_usage_leave_atif_fields_unset():
    trajectory = _parse(_user(), _assistant(TEXT, model=None))
    assert trajectory.steps[1].model_name is None
    assert trajectory.steps[1].metrics is None


def test_steps_record_their_source_line_and_api_message():
    trajectory = _parse(_user(), "", {"type": "ai-title"}, _assistant(TEXT, message_id="msg_9"))

    assert trajectory.steps[0].extra == {"agent_session_bridge": {"source_line": 1}}
    # Blank lines are not counted; the assistant record is the third non-blank line.
    assert trajectory.steps[1].extra == {
        "agent_session_bridge": {"source_line": 3, "source_message_id": "msg_9"}
    }


def test_redaction_preserves_model_metrics_and_step_provenance():
    trajectory = redact_trajectory(_parse(_user(), _assistant(TEXT, usage=USAGE)))
    step = trajectory.steps[1]

    assert step.model_name == "claude-test-1"
    assert step.metrics is not None and step.metrics.prompt_tokens == 152
    assert step.extra is not None and step.extra["agent_session_bridge"]["source_line"] == 2
    fidelity = _fidelity(trajectory)
    assert fidelity["duplicate_usage_records"] == 0
    assert isinstance(fidelity["unsupported_record_types"], list)


def test_non_string_record_types_and_roles_are_reported_and_later_records_survive():
    trajectory = _parse(
        {"type": []},
        {"type": {}},
        {"type": "user", "message": {"role": [], "content": "discarded"}},
        {"type": "assistant", "message": {"role": {}, "content": "discarded"}},
        _user("still here"),
    )
    assert [step.message for step in trajectory.steps] == ["still here"]
    fidelity = _fidelity(trajectory)
    assert fidelity["unsupported_source_records"] == 4
    assert {entry["type"]: entry["records"] for entry in fidelity["unsupported_record_types"]} == {
        "(untyped record)": 2,
        "user (unsupported role)": 1,
        "assistant (unsupported role)": 1,
    }
