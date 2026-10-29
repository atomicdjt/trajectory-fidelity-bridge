"""Focused Claude/ATIF boundary regressions. No production behavior is changed."""

import json
from io import StringIO

import pytest

from adapters.claude.parser import parse_claude_jsonl


def _convert(result_block):
    call = {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "call-1", "name": "read_file", "input": {}}
    ]}}
    response = {"type": "user", "message": {"role": "user", "content": [result_block]}}
    stream = StringIO("\n".join(json.dumps(row) for row in (call, response)))
    trajectory = parse_claude_jsonl(stream)
    result = trajectory.steps[0].observation.results[0]
    return trajectory, result


@pytest.mark.parametrize(
    ("content", "expected"),
    [(None, "null"), ("null", "null"), ({"value": None}, '{"value":null}')],
)
def test_tool_result_null_representation_is_explicit_and_not_python_repr(content, expected):
    """Preserve the original JSON value's serialized meaning, not Python's None repr."""
    trajectory, result = _convert({
        "type": "tool_result", "tool_use_id": "call-1", "content": content,
    })
    assert result.content == expected
    assert result.source_call_id == "call-1"
    assert trajectory.extra["agent_session_bridge"]["fidelity"]["observation_results_preserved"] == 1


def test_missing_tool_result_content_remains_distinct_from_explicit_null():
    """Missing content uses Claude adapter's documented empty-string fallback."""
    _, absent = _convert({"type": "tool_result", "tool_use_id": "call-1"})
    _, explicit_null = _convert({
        "type": "tool_result", "tool_use_id": "call-1", "content": None,
    })
    assert absent.content == ""
    assert explicit_null.content == "null"


@pytest.mark.parametrize("is_error", [True, False])
def test_boolean_error_flag_never_inverts_failure_interpretation(is_error):
    """Only a true source error flag is asserted as an error in ATIF extra."""
    _, result = _convert({
        "type": "tool_result", "tool_use_id": "call-1",
        "content": "operation completed", "is_error": is_error,
    })
    assert (result.extra or {}).get("is_error") is (True if is_error else None)
