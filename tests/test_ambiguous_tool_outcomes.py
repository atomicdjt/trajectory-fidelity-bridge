"""Replayable evidence checks for ambiguous external tool outcomes."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from experiments.ambiguous_tool_outcomes.verify import verify_experiment

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = REPO_ROOT / "experiments" / "ambiguous_tool_outcomes"


@pytest.fixture(scope="module")
def evidence(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output_dir = tmp_path_factory.mktemp("ambiguous-tool-outcomes")
    env = os.environ.copy()
    paths = [str(REPO_ROOT), str(REPO_ROOT / "src")]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "experiments.ambiguous_tool_outcomes.reproduce",
            "--output-dir",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return output_dir


def test_reproduction_preserves_same_unknown_receipt_across_different_truth(
    evidence: Path,
):
    """The shared source yields identical unknown receipts despite different effects."""
    report = json.loads((evidence / "verification.json").read_text(encoding="utf-8"))
    before = json.loads((evidence / "ground-truth-before_commit_timeout.json").read_text(encoding="utf-8"))
    after = json.loads((evidence / "ground-truth-after_commit_response_loss.json").read_text(encoding="utf-8"))
    before_receipt = json.loads((evidence / "before_commit_timeout.atif.json").read_text(encoding="utf-8"))
    after_receipt = json.loads((evidence / "after_commit_response_loss.atif.json").read_text(encoding="utf-8"))
    commands = json.loads((evidence / "commands.json").read_text(encoding="utf-8"))

    assert report["summary"]["passed"] is True
    assert report["summary"]["conflicts"] == 0
    assert before["actual_effect_count"] == 0
    assert after["actual_effect_count"] == 1
    assert before_receipt["steps"] == after_receipt["steps"]
    assert before_receipt["extra"]["agent_session_bridge"]["fidelity"] == after_receipt[
        "extra"
    ]["agent_session_bridge"]["fidelity"]
    assert [item["source_sha256"] for item in commands] == [commands[0]["source_sha256"]] * 2
    result = before_receipt["steps"][1]["observation"]["results"][0]
    assert result["extra"]["agent_session_bridge"]["outcome"] == "unknown"


def test_experiment_verifier_rejects_fabricated_status_and_unreported_loss(
    evidence: Path, tmp_path: Path
):
    """False result claims, broken correlation, and missing loss counts are detected."""
    source = evidence / "caller-visible.source.jsonl"
    truth_before = evidence / "ground-truth-before_commit_timeout.json"
    truth_after = evidence / "ground-truth-after_commit_response_loss.json"
    after_output = evidence / "after_commit_response_loss.atif.json"
    decision = evidence / "decision-record.json"
    oracle = EXPERIMENT_ROOT / "oracle.json"
    commands = evidence / "commands.json"
    before_output = evidence / "before_commit_timeout.atif.json"
    original = json.loads(before_output.read_text(encoding="utf-8"))

    mutations = {
        "fabricated_success": lambda document: document["steps"][1]["observation"]["results"][0][
            "extra"
        ]["agent_session_bridge"].update(outcome="succeeded"),
        "broken_call_correlation": lambda document: document["steps"][1]["observation"][
            "results"
        ][0].update(source_call_id="different-call"),
        "unreported_result_timestamp_loss": lambda document: document["extra"][
            "agent_session_bridge"
        ]["fidelity"].update(omitted_tool_result_timestamps=0),
    }
    expected_checks = {
        "fabricated_success": [
            "before_commit_timeout_external_effect_outcome_unknown",
        ],
        "broken_call_correlation": [
            "before_commit_timeout_result_correlation_preserved",
            "before_commit_timeout_atif_validation",
        ],
        "unreported_result_timestamp_loss": [
            "before_commit_timeout_omitted_timestamp_counted",
        ],
    }

    for name, mutate in mutations.items():
        candidate = copy.deepcopy(original)
        mutate(candidate)
        candidate_path = tmp_path / f"{name}.atif.json"
        candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
        report = verify_experiment(
            source_path=source,
            ground_truth_before_path=truth_before,
            ground_truth_after_path=truth_after,
            before_output_path=candidate_path,
            after_output_path=after_output,
            decision_record_path=decision,
            oracle_path=oracle,
            commands_path=commands,
        )
        assert report["summary"]["passed"] is False
        check_names = {check["name"] for check in report["checks"]}
        matching_names = set(expected_checks[name]) & check_names
        assert matching_names, sorted(check_names)
        finding = next(
            check
            for check in report["checks"]
            if check["name"] in matching_names and check["status"] == "CONFLICT"
        )
        assert finding["status"] == "CONFLICT"
