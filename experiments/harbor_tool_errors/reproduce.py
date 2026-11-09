"""Regenerate the minimized peer fixture using an installed, pinned Harbor checkout.

Run from the TFB root. This only converts public fixture data; no agent is run.
"""

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory


def remove_placeholders(value):
    """Remove sanitizer sentinels, which are not original provider field values."""
    if isinstance(value, dict):
        return {k: remove_placeholders(v) for k, v in value.items() if v != "[dropped]"}
    if isinstance(value, list):
        return [remove_placeholders(v) for v in value]
    return value


def main():
    from harbor.agents.installed.claude_code import ClaudeCode

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--full-output", type=Path, help="Also write the full peer conversion")
    args = parser.parse_args()
    source = Path("fixtures/real-session/claude-code-controlled-demo.source.jsonl")
    manifest = json.loads(source.with_name(
        "claude-code-controlled-demo.manifest.json"
    ).read_text(encoding="utf-8"))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest["source_sha256"]
    records = [remove_placeholders(json.loads(line))
               for line in source.read_text(encoding="utf-8").splitlines()]
    with TemporaryDirectory() as directory:
        root = Path(directory)
        sessions = root / "sessions"
        sessions.mkdir()
        (sessions / "session.jsonl").write_text(
            "\n".join(json.dumps(r) for r in records), encoding="utf-8"
        )
        agent = ClaudeCode(logs_dir=root / "logs")
        trajectory = agent._convert_events_to_trajectory(sessions)
        assert trajectory is not None
        document = json.loads(trajectory.model_dump_json())

    calls = sum(len(s.get("tool_calls") or []) for s in document["steps"])
    results = [r for s in document["steps"]
               for r in (s.get("observation") or {}).get("results", [])]
    errors = [r for r in results if (r.get("extra") or {}).get("tool_result_is_error") is True]
    assert (calls, len(results), len(errors)) == (6, 6, 1)
    if args.full_output:
        args.full_output.parent.mkdir(parents=True, exist_ok=True)
        args.full_output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
    document["steps"] = [s for s in document["steps"] if any(
        (r.get("extra") or {}).get("tool_result_is_error") is True
        for r in (s.get("observation") or {}).get("results", [])
    )]
    document["steps"][0]["step_id"] = 1
    document["steps"][0].pop("metrics", None)
    document.pop("final_metrics", None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"source_calls": calls, "results": len(results), "errors": len(errors),
                      "retained_steps": len(document["steps"])}))


if __name__ == "__main__":
    main()
