from datetime import datetime

from atif import Trajectory
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from observability.mapping import (
    get_openinference_span_attributes,
    get_tool_span_attributes,
)

tracer = trace.get_tracer("agent-session-bridge")


def parse_source_time(ts: str) -> int:
    try:
        dt = datetime.fromisoformat(ts)
        offset = dt.utcoffset()
        if dt.tzinfo is None or offset is None:
            raise ValueError()
        local_delta = dt.replace(tzinfo=None) - datetime(1970, 1, 1)
        delta = local_delta - offset
        nanoseconds = (delta.days * 86400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000
        return nanoseconds
    except (AttributeError, ValueError):
        raise ValueError(
            "observability projection requires a source-observed ISO-8601 timestamp for every step"
        )


def project_trajectory(trajectory: Trajectory, privacy_mode: str = "metadata-only"):
    """
    Project an TFB ATIF trajectory into OpenTelemetry spans.
    """
    if not trajectory.steps:
        return

    # We will treat each step as a root operation in the trace,
    # or if we want one big trace, we can wrap the whole trajectory.
    # Let's wrap the whole trajectory in one root trace.
    step_times = []
    for step in trajectory.steps:
        if not step.timestamp:
            raise ValueError("observability projection requires a source-observed ISO-8601 timestamp for every step")
        step_times.append(parse_source_time(step.timestamp))

    start_time_ns = min(step_times)
    end_time_ns = max(step_times)

    # Start root session span
    root_span = tracer.start_span(
        name="historical_trajectory",
        start_time=start_time_ns,
    )

    # Set session attributes
    if trajectory.session_id and trajectory.session_id != "unknown":
        root_span.set_attribute("session.id", trajectory.session_id)

    root_span.set_attribute("openinference.span.kind", "CHAIN")

    provider = None
    if trajectory.agent and trajectory.agent.extra:
        provider = trajectory.agent.extra.get("provider")
    if not provider and trajectory.extra:
        provider = trajectory.extra.get("provider")
    if provider:
        root_span.set_attribute("agent_session_bridge.provider", provider)

    if trajectory.agent and trajectory.agent.name:
        root_span.set_attribute("agent_session_bridge.agent", trajectory.agent.name)
    root_span.set_attribute(
        "agent_session_bridge.timestamp.provenance", "SOURCE_DERIVED"
    )
    root_span.set_attribute("agent_session_bridge.projection", "historical")

    # Process turns
    from opentelemetry.context import attach, detach

    ctx = trace.set_span_in_context(root_span)
    token = attach(ctx)

    try:
        for i, step in enumerate(trajectory.steps):
            if not step.timestamp:
                raise ValueError("observability projection requires a source-observed ISO-8601 timestamp for every step")

            step_start_ns = parse_source_time(step.timestamp)
            # A step timestamp is an observed point, not an execution interval.
            step_end_ns = step_start_ns

            # Create a span for the step
            step_span = tracer.start_span(
                name=f"turn_{step.source}",
                start_time=step_start_ns,
            )

            attrs = get_openinference_span_attributes(trajectory, step, privacy_mode)
            for k, v in attrs.items():
                step_span.set_attribute(k, v)
            step_span.set_attribute(
                "agent_session_bridge.timestamp.provenance", "SOURCE_OBSERVED"
            )

            # Tools
            if step.tool_calls:
                step_ctx = trace.set_span_in_context(step_span)
                step_token = attach(step_ctx)
                try:
                    for idx, tool_call in enumerate(step.tool_calls):
                        # Tool spans
                        # ObservationResults don't have independent timestamps, so we do not fabricate duration.
                        tool_start = step_start_ns
                        tool_end = tool_start

                        tool_span = tracer.start_span(
                            name=tool_call.function_name, start_time=tool_start
                        )
                        tool_attrs = get_tool_span_attributes(
                            tool_call, trajectory.session_id, privacy_mode
                        )
                        for k, v in tool_attrs.items():
                            tool_span.set_attribute(k, v)

                        # Look for correlated observation result
                        result_str = None
                        is_error = False

                        if step.observation and step.observation.results:
                            for res in step.observation.results:
                                if res.source_call_id == tool_call.tool_call_id:
                                    is_error_val = res.extra.get("is_error") if res.extra else None
                                    if (
                                        is_error_val is True
                                        or (
                                            isinstance(is_error_val, str)
                                            and is_error_val.strip().lower() in ("true", "1")
                                        )
                                        or (
                                            isinstance(is_error_val, int)
                                            and is_error_val == 1
                                            and not isinstance(is_error_val, bool)
                                        )
                                    ):
                                        is_error = True
                                    # We don't have a specific status code enum in basic ATIF,
                                    # but we assume success if a result is present, or parse from extra.
                                    if (
                                        privacy_mode
                                        in ("full-content", "redacted-content")
                                        and res.content
                                    ):
                                        from observability.mapping import project_text
                                        from security.redact import (
                                            _redact_text as redact_text,
                                        )
                                        text_content = project_text(res.content)
                                        result_str = (
                                            redact_text(text_content)
                                            if privacy_mode == "redacted-content"
                                            else text_content
                                        )
                                    break

                        if result_str:
                            tool_span.set_attribute("output.value", result_str)
                            tool_span.set_attribute("output.mime_type", "text/plain")

                        tool_span.set_attribute(
                            "agent_session_bridge.timestamp.provenance", "SOURCE_OBSERVED"
                        )

                        if is_error:
                            tool_span.set_status(
                                Status(StatusCode.ERROR, description=result_str or "Tool execution error")
                            )
                        else:
                            tool_span.set_status(Status(StatusCode.OK))

                        tool_span.end(end_time=tool_end)
                finally:
                    detach(step_token)

            step_span.end(end_time=step_end_ns)

    finally:
        detach(token)
        root_span.end(end_time=end_time_ns)
