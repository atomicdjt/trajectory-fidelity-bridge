"""Codex rollout coverage. All input content in these tests is synthetic."""

import json
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest
from atif import Trajectory

from adapters.codex.parser import parse_codex_jsonl
from security.redact import redact_trajectory


def event(kind, payload, timestamp="2026-01-01T00:00:00Z"):
    return {"type": kind, "timestamp": timestamp, "payload": payload}


def convert(*records):
    return parse_codex_jsonl(StringIO("\n".join(json.dumps(x) for x in records)))


def report(trajectory):
    return trajectory.extra["agent_session_bridge"]["fidelity"]


def test_normalizes_messages_interleaved_calls_and_results():
    trajectory = convert(
        event("session_meta", {"id": "demo-session", "cli_version": "0.0.test"}),
        event(
            "response_item",
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Inspect the sample."}],
            },
        ),
        event(
            "response_item",
            {
                "type": "function_call",
                "name": "shell",
                "call_id": "a",
                "arguments": '{"command":"echo example"}',
            },
        ),
        event(
            "response_item",
            {
                "type": "custom_tool_call",
                "name": "patch",
                "call_id": "b",
                "input": "synthetic patch",
            },
        ),
        event(
            "response_item",
            {
                "type": "custom_tool_call_output",
                "call_id": "b",
                "output": [
                    {"type": "input_text", "text": "one"},
                    {"type": "input_text", "text": "two"},
                ],
            },
        ),
        event(
            "response_item",
            {"type": "function_call_output", "call_id": "a", "output": "ok"},
        ),
        event(
            "response_item",
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Done."}],
            },
        ),
    )
    assert trajectory.schema_version == "ATIF-v1.7"
    assert trajectory.session_id == "demo-session"
    assert trajectory.agent.name == "codex" and trajectory.agent.version == "0.0.test"
    assert [s.source for s in trajectory.steps] == ["user", "agent", "agent", "agent"]
    first, second = trajectory.steps[1:3]
    assert first.tool_calls[0].arguments == {"command": "echo example"}
    assert second.tool_calls[0].arguments == {"input": "synthetic patch"}
    assert first.observation.results[0].content == "ok"
    assert [p.text for p in second.observation.results[0].content] == ["one", "two"]
    assert [
        first.observation.results[0].source_call_id,
        second.observation.results[0].source_call_id,
    ] == ["a", "b"]
    assert report(trajectory)["tool_calls_preserved"] == 2
    assert report(trajectory)["observation_results_preserved"] == 2
    assert report(trajectory)["omitted_tool_result_timestamps"] == 2


def test_loss_accounting_and_invalid_records_are_explicit():
    trajectory = parse_codex_jsonl(
        StringIO(
            "\n".join(
                [
                    "{truncated",
                    "[]",
                    json.dumps(event("event_msg", {"type": "item_completed"})),
                    json.dumps(
                        event(
                            "response_item",
                            {"type": "reasoning", "summary": ["private"]},
                        )
                    ),
                    json.dumps(
                        event(
                            "response_item",
                            {
                                "type": "message",
                                "role": "user",
                                "content": [
                                    {"type": "input_text", "text": "text"},
                                    {
                                        "type": "input_image",
                                        "image_url": "data:image/png;base64,AAA",
                                    },
                                ],
                            },
                        )
                    ),
                    json.dumps(
                        event(
                            "response_item",
                            {
                                "type": "function_call_output",
                                "call_id": "missing",
                                "output": "orphan",
                            },
                        )
                    ),
                    json.dumps(
                        event(
                            "response_item",
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "ok"}],
                            },
                            "invalid timestamp",
                        )
                    ),
                ]
            )
        )
    )
    fidelity = report(trajectory)
    assert fidelity["unsupported_source_records"] == 4
    assert fidelity["unsupported_source_blocks"] == 1
    assert fidelity["orphaned_tool_results"] == 1
    assert fidelity["invalid_source_timestamps"] == 1
    assert trajectory.steps[-1].timestamp is None
    assert any(
        x["type"] == "input_image" and x["with_content"] == 1
        for x in fidelity["unsupported_block_types"]
    )
    assert "private" not in trajectory.model_dump_json()


def test_ambiguous_duplicate_call_ids_are_not_misassociated():
    def call(name):
        return event(
            "response_item",
            {
                "type": "function_call",
                "name": name,
                "call_id": "same",
                "arguments": "{}",
            },
        )

    trajectory = convert(
        call("first"),
        call("second"),
        event(
            "response_item",
            {"type": "function_call_output", "call_id": "same", "output": "ambiguous"},
        ),
    )
    assert len(trajectory.steps) == 1
    assert trajectory.steps[0].observation is None
    assert report(trajectory)["orphaned_tool_results"] == 1
    assert any(
        "duplicate" in x["type"] for x in report(trajectory)["unsupported_record_types"]
    )


def test_duplicate_event_id_and_unsupported_output_blocks_are_accounted_for():
    message = event(
        "response_item",
        {
            "id": "m1",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "hello"}],
        },
    )
    trajectory = convert(
        message,
        message,
        event(
            "response_item",
            {
                "type": "custom_tool_call",
                "name": "tool",
                "call_id": "c",
                "input": "input",
            },
        ),
        event(
            "response_item",
            {
                "type": "custom_tool_call_output",
                "call_id": "c",
                "output": [
                    {"type": "input_text", "text": "visible"},
                    {"type": "input_image", "image_url": "x"},
                ],
            },
        ),
    )
    assert len(trajectory.steps) == 2
    assert report(trajectory)["unsupported_source_records"] == 1
    assert report(trajectory)["unsupported_source_blocks"] == 1
    assert trajectory.steps[1].observation.results[0].content[0].text == "visible"


@pytest.mark.parametrize("raw", ['{"nested": [1, 2]}', "[1, 2]", "not-json"])
def test_function_arguments_are_never_silently_dropped(raw):
    trajectory = convert(
        event(
            "response_item",
            {"type": "function_call", "name": "x", "call_id": "c", "arguments": raw},
        )
    )
    args = trajectory.steps[0].tool_calls[0].arguments
    if raw.startswith("{"):
        assert args == {"nested": [1, 2]}
    elif raw.startswith("["):
        assert args == {"value": [1, 2]}
    else:
        assert args == {"input": raw}


def test_redaction_applies_to_codex_text_arguments_and_results():
    secret = "sk-testSecret1234567890"
    trajectory = convert(
        event(
            "response_item",
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": secret}],
            },
        ),
        event(
            "response_item",
            {
                "type": "custom_tool_call",
                "name": "tool",
                "call_id": "c",
                "input": secret,
            },
        ),
        event(
            "response_item",
            {
                "type": "custom_tool_call_output",
                "call_id": "c",
                "output": [{"type": "input_text", "text": secret}],
            },
        ),
    )
    assert secret not in redact_trajectory(trajectory).model_dump_json()


@pytest.mark.parametrize(
    "raw",
    [
        '{"key": 1, "key": 2}',
        '{"x": NaN}',
        '{"x": 1e999}',
        '{"x": 0.1234567890123456789}',
    ],
)
def test_nonstandard_or_ambiguous_json_arguments_preserve_the_original_string(raw):
    trajectory = convert(
        event(
            "response_item",
            {"type": "function_call", "name": "x", "call_id": "c", "arguments": raw},
        )
    )
    assert trajectory.steps[0].tool_calls[0].arguments == {"input": raw}


def test_wrong_result_type_and_replayed_call_do_not_create_false_correlations():
    call = event(
        "response_item",
        {
            "type": "custom_tool_call",
            "id": "item",
            "name": "tool",
            "call_id": "call",
            "input": "input",
        },
    )
    trajectory = convert(
        call,
        call,
        event(
            "response_item",
            {
                "type": "custom_tool_call_output",
                "call_id": "call",
                "output": "uncertain",
            },
        ),
    )
    assert trajectory.steps[0].observation is None
    assert report(trajectory)["orphaned_tool_results"] == 1
    trajectory = convert(
        call,
        event(
            "response_item",
            {"type": "function_call_output", "call_id": "call", "output": "wrong kind"},
        ),
    )
    assert trajectory.steps[0].observation is None
    assert report(trajectory)["orphaned_tool_results"] == 1


def test_unknown_codex_tool_outcome_is_not_marked_successful(monkeypatch):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    from opentelemetry.trace import StatusCode

    from observability import spans

    trajectory = convert(
        event(
            "response_item",
            {
                "type": "custom_tool_call",
                "name": "tool",
                "call_id": "c",
                "input": "input",
            },
        ),
        event(
            "response_item",
            {"type": "custom_tool_call_output", "call_id": "c", "output": "done"},
        ),
    )
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(spans, "tracer", provider.get_tracer("codex-status-test"))
    try:
        spans.project_trajectory(trajectory)
        tool = next(
            s for s in exporter.get_finished_spans() if "tool.id" in s.attributes
        )
        assert tool.status.status_code == StatusCode.UNSET
    finally:
        provider.shutdown()


def test_cli_imports_codex_rollout_and_preserves_json_stdout(tmp_path):
    source = tmp_path / "rollout.jsonl"
    source.write_text(
        json.dumps(
            event(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                },
            )
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.main",
            "import",
            "--from",
            "codex",
            "--source",
            str(source),
            "--report",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    trajectory = Trajectory.model_validate_json(result.stdout)
    assert trajectory.agent.name == "codex"
    assert trajectory.steps[0].message == "hello"
    assert "TFB Fidelity Report" in result.stderr


def test_published_synthetic_sample_has_expected_fidelity():
    with Path("fixtures/codex_sample.jsonl").open(encoding="utf-8") as source:
        trajectory = parse_codex_jsonl(source)
    fidelity = report(trajectory)
    assert fidelity["source_records_preserved"] == 5
    assert (
        fidelity["tool_calls_preserved"]
        == fidelity["observation_results_preserved"]
        == 1
    )
    assert fidelity["unsupported_source_records"] == 1
    assert fidelity["omitted_tool_result_timestamps"] == 1


def test_malformed_record_fields_and_metadata_conflicts_do_not_abort():
    trajectory = convert(
        event("session_meta", {"id": "first", "session_id": "different"}),
        event("response_item", {"type": "message", "role": ["user"], "content": []}),
        event(
            "response_item",
            {"type": "function_call", "name": "tool", "call_id": [], "arguments": "{}"},
        ),
        event(
            "response_item",
            {"type": "function_call_output", "call_id": {}, "output": "x"},
        ),
        event(
            "response_item",
            {
                "type": "message",
                "role": "developer",
                "content": [
                    {"type": "input_text", "text": "system context"},
                    {"type": {}, "text": "unknown"},
                ],
            },
        ),
    )
    assert trajectory.session_id is None
    assert len(trajectory.steps) == 1 and trajectory.steps[0].source == "system"
    assert report(trajectory)["unsupported_source_records"] == 3
    assert report(trajectory)["orphaned_tool_results"] == 1
    assert report(trajectory)["unsupported_source_blocks"] == 1


def test_import_never_executes_recorded_commands(tmp_path):
    target = tmp_path / "must-not-exist"
    source = tmp_path / "rollout.jsonl"
    source.write_text(
        json.dumps(
            event(
                "response_item",
                {
                    "type": "function_call",
                    "name": "shell",
                    "call_id": "c",
                    "arguments": json.dumps(
                        {
                            "command": f"\"{sys.executable}\" -c \"open({str(target)!r}, 'w').write('bad')\""
                        }
                    ),
                },
            )
        ),
        encoding="utf-8",
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.main",
            "import",
            "--from",
            "codex",
            "--source",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    assert not target.exists()
