"""Known converter conventions in ATIF extras, not ATIF-standard status fields."""

from typing import Any


def tool_result_is_error(extra: dict[str, Any] | None) -> bool:
    """Recognize TFB and Harbor Claude error flags; explicit errors take precedence.

    Keep the historical telemetry acceptance of true/1 strings and integer 1.
    Do not infer failure from result text or arbitrary nested provider metadata.
    """
    if not extra:
        return False
    for key in ("is_error", "tool_result_is_error"):
        value = extra.get(key)
        if value is True:
            return True
        if isinstance(value, str) and value.strip().lower() in {"true", "1"}:
            return True
        if isinstance(value, int) and not isinstance(value, bool) and value == 1:
            return True
    return False
