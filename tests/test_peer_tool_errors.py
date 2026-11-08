"""Consumer regression: actual Harbor conversion of the public real-session fixture."""

from pathlib import Path

import pytest
from atif import Trajectory
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from bridge.tool_results import tool_result_is_error
from explain import render_report
from observability import spans as projection


@pytest.fixture
def peer_trajectory():
    return Trajectory.model_validate_json(
        Path("fixtures/interoperability/harbor-claude-error.atif.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def exporter(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(projection, "tracer", provider.get_tracer("peer-regression"))
    yield exporter
    provider.shutdown()


def test_harbor_real_session_error_is_visible_in_report(peer_trajectory):
    report = render_report(peer_trajectory)
    assert "1 with an error result" in report
    assert "**Result (error):**" in report


def test_harbor_real_session_error_survives_projection(peer_trajectory, exporter):
    projection.project_trajectory(peer_trajectory)
    tools = [s for s in exporter.get_finished_spans() if "tool.id" in s.attributes]
    assert len(tools) == 1
    assert tools[0].status.status_code == StatusCode.ERROR
    assert tools[0].status.description == "Tool execution error"
    assert "input.value" not in tools[0].attributes
    assert "output.value" not in tools[0].attributes


@pytest.mark.parametrize("key", ["is_error", "tool_result_is_error"])
@pytest.mark.parametrize("value", [True, "true", "  TRUE  ", "1", 1])
def test_supported_error_flags(key, value):
    assert tool_result_is_error({key: value})


@pytest.mark.parametrize("value", [False, "false", "0", 0, None, "error", [], {}, 1.0])
def test_non_error_values_are_not_truthy_errors(value):
    assert not tool_result_is_error({"is_error": value, "tool_result_is_error": value})


def test_conflicting_flags_preserve_explicit_error(peer_trajectory, exporter):
    peer_trajectory.steps[0].observation.results[0].extra["is_error"] = False
    assert "1 with an error result" in render_report(peer_trajectory)
    projection.project_trajectory(peer_trajectory, privacy_mode="full-content")
    tool = next(s for s in exporter.get_finished_spans() if "tool.id" in s.attributes)
    assert tool.status.status_code == StatusCode.ERROR


def test_later_correlated_error_is_not_hidden_by_first_result(peer_trajectory, exporter):
    results = peer_trajectory.steps[0].observation.results
    first = results[0].model_copy(deep=True)
    first.extra = {"tool_result_is_error": False}
    first.content = "Earlier result"
    results.insert(0, first)
    projection.project_trajectory(peer_trajectory, privacy_mode="full-content")
    tool = next(s for s in exporter.get_finished_spans() if "tool.id" in s.attributes)
    assert tool.status.status_code == StatusCode.ERROR
    assert "Earlier result" not in tool.status.description
    assert "does not exist" in tool.status.description


def test_uncorrelated_error_does_not_mark_other_call_failed(peer_trajectory, exporter):
    from atif import ToolCall

    peer_trajectory.steps[0].tool_calls.append(
        ToolCall(tool_call_id="other-call", function_name="Read", arguments={})
    )
    projection.project_trajectory(peer_trajectory)
    tools = {s.attributes["tool.id"]: s for s in exporter.get_finished_spans()
             if "tool.id" in s.attributes}
    assert tools["tool-call-0003"].status.status_code == StatusCode.ERROR
    # A call without a correlated result has no evidence of success or failure.
    assert tools["other-call"].status.status_code == StatusCode.UNSET


@pytest.mark.parametrize("mode", ["redacted-content", "full-content"])
def test_peer_error_content_respects_privacy_mode(peer_trajectory, exporter, mode):
    result = peer_trajectory.steps[0].observation.results[0]
    result.content = "password=synthetic-secret-value"
    projection.project_trajectory(peer_trajectory, privacy_mode=mode)
    tool = next(s for s in exporter.get_finished_spans() if "tool.id" in s.attributes)
    assert tool.status.status_code == StatusCode.ERROR
    if mode == "redacted-content":
        assert "synthetic-secret-value" not in tool.attributes["output.value"]
        assert "synthetic-secret-value" not in tool.status.description
    else:
        assert tool.attributes["output.value"] == result.content


def test_arbitrary_nested_flags_and_error_text_are_not_interpreted():
    assert not tool_result_is_error({"provider_data": {"is_error": True}, "text": "error"})
