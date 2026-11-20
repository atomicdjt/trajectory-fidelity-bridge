"""Generate two in-memory provider worlds and normalize their shared Codex trace."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_ROOT = Path(__file__).resolve().parent
SCENARIOS = ("before_commit_timeout", "after_commit_response_loss")
SESSION_ID = "synthetic-ambiguous-session"
TOOL_CALL_ID = "synthetic-call-001"
TOOL_NAME = "synthetic_external_action"
TOOL_ARGUMENTS = {"action": "create_marker", "record": "fixture-record-001"}
USER_PROMPT = "Perform the synthetic action for fixture-record-001."
TIMEOUT_TEXT = (
    "Tool call timed out; no provider receipt or authoritative effect status was returned."
)


def simulate_provider(scenario: str) -> tuple[str, dict[str, Any]]:
    """Return caller-visible timeout text and a separate in-memory truth ledger."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown synthetic scenario: {scenario}")

    events: list[dict[str, Any]] = [{"event": "request_received"}]
    effects: list[dict[str, str]] = []
    if scenario == "before_commit_timeout":
        events.append({"event": "deadline_expired_before_commit"})
    else:
        effect = {"effect": "synthetic_marker_created", "record": "fixture-record-001"}
        effects.append(effect)
        events.extend(
            [
                {"event": "effect_committed", "effect_index": 1},
                {"event": "response_lost"},
                {"event": "deadline_expired"},
            ]
        )

    truth = {
        "schema_version": "tfb-synthetic-provider-truth-v1",
        "scenario": scenario,
        "harness_join_key": {
            "kind": "codex_tool_call_id",
            "value": TOOL_CALL_ID,
            "meaning": "test-harness association only; not a provider operation ID",
        },
        "provider_operation_identity_observed": False,
        "idempotency_key_observed": False,
        "retry_attempt_count": 0,
        "events": events,
        "effects": effects,
        "actual_effect_count": len(effects),
    }
    return TIMEOUT_TEXT, truth


def caller_visible_transcript(timeout_text: str) -> bytes:
    """Serialize only the caller-visible evidence as supported Codex rollout JSONL."""
    records = [
        {
            "type": "session_meta",
            "payload": {"id": SESSION_ID, "cli_version": "0.0.synthetic"},
        },
        {
            "type": "response_item",
            "timestamp": "2026-11-14T12:00:00Z",
            "payload": {
                "id": "item-user-001",
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": USER_PROMPT},
                ],
            },
        },
        {
            "type": "response_item",
            "timestamp": "2026-11-14T12:00:01Z",
            "payload": {
                "id": "item-call-001",
                "type": "function_call",
                "call_id": TOOL_CALL_ID,
                "name": TOOL_NAME,
                "arguments": json.dumps(TOOL_ARGUMENTS, separators=(",", ":")),
            },
        },
        {
            "type": "response_item",
            "timestamp": "2026-11-14T12:00:04Z",
            "payload": {
                "id": "item-output-001",
                "type": "function_call_output",
                "call_id": TOOL_CALL_ID,
                "output": timeout_text,
            },
        },
    ]
    text = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    return text.encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    try:
        return Path(os.path.relpath(path, REPO_ROOT)).as_posix()
    except ValueError:
        # Windows cannot compute a relative path between different drive roots.
        return path.resolve().as_posix()


def _version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _write_manifest(
    output_dir: Path,
    execution: dict[str, Any],
    source_sha256: str,
    repository_commit: str,
    worktree_clean_before_generation: bool,
) -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    artifact_paths = [
        output_dir / "caller-visible.source.jsonl",
        output_dir / "ground-truth-before_commit_timeout.json",
        output_dir / "ground-truth-after_commit_response_loss.json",
        output_dir / "decision-record.json",
        output_dir / "before_commit_timeout.atif.json",
        output_dir / "after_commit_response_loss.atif.json",
        output_dir / "before_commit_timeout.fidelity.json",
        output_dir / "after_commit_response_loss.fidelity.json",
        output_dir / "commands.json",
        output_dir / "execution.json",
        output_dir / "verification.json",
        output_dir / "before_commit_timeout.tfb.stdout.txt",
        output_dir / "before_commit_timeout.tfb.stderr.txt",
        output_dir / "after_commit_response_loss.tfb.stdout.txt",
        output_dir / "after_commit_response_loss.tfb.stderr.txt",
        output_dir / "verifier.stdout.txt",
        output_dir / "verifier.stderr.txt",
    ]
    code_paths = [
        EXPERIMENT_ROOT / "reproduce.py",
        EXPERIMENT_ROOT / "verify.py",
        EXPERIMENT_ROOT / "oracle.json",
        EXPERIMENT_ROOT / "decision-record.json",
        EXPERIMENT_ROOT / "README.md",
        REPO_ROOT / "tests" / "test_ambiguous_tool_outcomes.py",
    ]
    hashes = {
        f"packet/{path.name}": _sha256(path)
        for path in artifact_paths
        if path.exists()
    }
    hashes.update({_relative(path): _sha256(path) for path in code_paths})

    manifest = {
        "schema_version": "tfb-ambiguous-tool-outcomes-evidence-v1",
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "repository_commit": repository_commit,
        "repository_source_worktree_clean_before_generation": worktree_clean_before_generation,
        "evidence_output_directory_excluded_from_cleanliness_check": _relative(output_dir),
        "source_sha256_used_for_both_scenarios": source_sha256,
        "versions": {
            "python": sys.version.split()[0],
            "tfb": pyproject["project"]["version"],
            "atif": _version("atif"),
            "pydantic": _version("pydantic"),
            "pytest": _version("pytest"),
        },
        "commands_and_exit_statuses": execution,
        "sha256": hashes,
        "hash_note": "This file does not include its own hash.",
    }
    _write_json(output_dir / "manifest.json", manifest)


def main(argv: list[str] | None = None) -> int:
    """Simulate both provider worlds and run the supported TFB Codex import."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/ambiguous_tool_outcomes/evidence"),
        help="New or empty directory for the generated evidence packet.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing generated files in a non-empty output directory.",
    )
    args = parser.parse_args(argv)

    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()) and not args.overwrite:
        parser.error(f"Output directory is not empty: {output_dir}; choose a new path or --overwrite")

    repository_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    worktree_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    output_relative = _relative(output_dir).rstrip("/")
    source_changes = [
        line
        for line in worktree_status.splitlines()
        if not (
            line[3:].rstrip("/").replace("\\", "/") == output_relative
            or line[3:].replace("\\", "/").startswith(f"{output_relative}/")
        )
    ]
    worktree_clean_before_generation = not source_changes
    output_dir.mkdir(parents=True, exist_ok=True)

    before_text, before_truth = simulate_provider("before_commit_timeout")
    after_text, after_truth = simulate_provider("after_commit_response_loss")
    before_source = caller_visible_transcript(before_text)
    after_source = caller_visible_transcript(after_text)
    if before_source != after_source:
        raise RuntimeError("The counterfactual caller-visible transcripts differ.")

    source_path = output_dir / "caller-visible.source.jsonl"
    source_path.write_bytes(before_source)
    _write_json(output_dir / "ground-truth-before_commit_timeout.json", before_truth)
    _write_json(
        output_dir / "ground-truth-after_commit_response_loss.json", after_truth
    )
    decision_source = EXPERIMENT_ROOT / "decision-record.json"
    decision_path = output_dir / "decision-record.json"
    decision_path.write_bytes(decision_source.read_bytes())

    source_sha256 = _sha256(source_path)
    env = os.environ.copy()
    inherited_pythonpath = env.get("PYTHONPATH")
    pythonpath = [str(REPO_ROOT / "src"), str(REPO_ROOT)]
    if inherited_pythonpath:
        pythonpath.append(inherited_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)

    normalization_commands: list[dict[str, Any]] = []
    stdout_paths: list[Path] = []
    stderr_paths: list[Path] = []
    for scenario in SCENARIOS:
        output_path = output_dir / f"{scenario}.atif.json"
        command = [
            sys.executable,
            "-m",
            "cli.main",
            "import",
            "--from",
            "codex",
            "--source",
            _relative(source_path),
            "--output",
            _relative(output_path),
            "--report",
        ]
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        stdout_path = output_dir / f"{scenario}.tfb.stdout.txt"
        stderr_path = output_dir / f"{scenario}.tfb.stderr.txt"
        stdout_path.write_text(completed.stdout, encoding="utf-8", newline="\n")
        stderr_path.write_text(completed.stderr, encoding="utf-8", newline="\n")
        stdout_paths.append(stdout_path)
        stderr_paths.append(stderr_path)
        normalization_commands.append(
            {
                "scenario": scenario,
                "source": _relative(source_path),
                "source_sha256": source_sha256,
                "argv": command,
                "exit_code": completed.returncode,
            }
        )
        if completed.returncode == 0:
            document = json.loads(output_path.read_text(encoding="utf-8"))
            fidelity = document["extra"]["agent_session_bridge"]["fidelity"]
            _write_json(output_dir / f"{scenario}.fidelity.json", fidelity)

    commands_path = output_dir / "commands.json"
    _write_json(commands_path, normalization_commands)
    execution: dict[str, Any] = {"normalization": normalization_commands}
    if any(command["exit_code"] != 0 for command in normalization_commands):
        _write_json(output_dir / "execution.json", execution)
        _write_manifest(
            output_dir,
            execution,
            source_sha256,
            repository_commit,
            worktree_clean_before_generation,
        )
        return 1

    verification_path = output_dir / "verification.json"
    verifier_command = [
        sys.executable,
        "-m",
        "experiments.ambiguous_tool_outcomes.verify",
        "--source",
        _relative(source_path),
        "--ground-truth-before",
        _relative(output_dir / "ground-truth-before_commit_timeout.json"),
        "--ground-truth-after",
        _relative(output_dir / "ground-truth-after_commit_response_loss.json"),
        "--before-output",
        _relative(output_dir / "before_commit_timeout.atif.json"),
        "--after-output",
        _relative(output_dir / "after_commit_response_loss.atif.json"),
        "--decision-record",
        _relative(decision_path),
        "--oracle",
        _relative(EXPERIMENT_ROOT / "oracle.json"),
        "--commands",
        _relative(commands_path),
        "--report",
        _relative(verification_path),
    ]
    verified = subprocess.run(
        verifier_command,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    (output_dir / "verifier.stdout.txt").write_text(
        verified.stdout, encoding="utf-8", newline="\n"
    )
    (output_dir / "verifier.stderr.txt").write_text(
        verified.stderr, encoding="utf-8", newline="\n"
    )
    execution["independent_verifier"] = {
        "argv": verifier_command,
        "exit_code": verified.returncode,
    }
    _write_json(output_dir / "execution.json", execution)
    _write_manifest(
        output_dir,
        execution,
        source_sha256,
        repository_commit,
        worktree_clean_before_generation,
    )
    return verified.returncode


if __name__ == "__main__":
    raise SystemExit(main())
