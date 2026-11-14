"""Check source-grounded invariants in the ambiguous-outcome evidence packet."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from atif import Trajectory
from pydantic import ValidationError


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError("Codex JSONL records must be JSON objects.")
        records.append(value)
    return records


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(checks: list[dict[str, Any]], name: str, expected: Any, observed: Any) -> None:
    checks.append(
        {
            "name": name,
            "status": "PASS" if observed == expected else "CONFLICT",
            "expected": expected,
            "observed": observed,
        }
    )


def _find_keys(value: Any, names: set[str]) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in names:
                found.append(key)
            found.extend(_find_keys(item, names))
    elif isinstance(value, list):
        for item in value:
            found.extend(_find_keys(item, names))
    return found


def _string_values(value: Any) -> set[str]:
    values: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            values.add(str(key))
            values.update(_string_values(item))
    elif isinstance(value, list):
        for item in value:
            values.update(_string_values(item))
    elif isinstance(value, str):
        values.add(value)
    return values


def _is_codex_import(command: dict[str, Any]) -> bool:
    argv = command.get("argv", [])
    if not isinstance(argv, list):
        return False
    try:
        return (
            argv[argv.index("-m") + 1] == "cli.main"
            and argv[argv.index("import") + 1] == "--from"
            and argv[argv.index("--from") + 1] == "codex"
            and argv[argv.index("--source") + 1] == command.get("source")
        )
    except (ValueError, IndexError):
        return False


def _semantic_projection(document: dict[str, Any]) -> dict[str, Any]:
    projected = copy.deepcopy(document)
    provenance = (
        projected.get("extra", {})
        .get("agent_session_bridge", {})
        .get("provenance", {})
    )
    if isinstance(provenance, dict):
        provenance.pop("conversion_timestamp", None)
    return projected


def verify_experiment(
    *,
    source_path: Path,
    ground_truth_before_path: Path,
    ground_truth_after_path: Path,
    before_output_path: Path,
    after_output_path: Path,
    decision_record_path: Path,
    oracle_path: Path,
    commands_path: Path | None = None,
) -> dict[str, Any]:
    """Verify the two hidden-effect worlds against one caller-visible Codex trace."""
    checks: list[dict[str, Any]] = []
    oracle = _read_json(oracle_path)
    source_facts = oracle["source"]
    normalized_facts = oracle["normalized"]
    records = _read_jsonl(source_path)

    session_record = next(
        (record for record in records if record.get("type") == "session_meta"), {}
    )
    session_payload = session_record.get("payload", {})
    call_record = next(
        (
            record
            for record in records
            if record.get("type") == "response_item"
            and isinstance(record.get("payload"), dict)
            and record["payload"].get("type") == "function_call"
        ),
        {},
    )
    result_record = next(
        (
            record
            for record in records
            if record.get("type") == "response_item"
            and isinstance(record.get("payload"), dict)
            and record["payload"].get("type") == "function_call_output"
        ),
        {},
    )
    call_payload = call_record.get("payload", {})
    result_payload = result_record.get("payload", {})
    user_record = next(
        (
            record
            for record in records
            if record.get("type") == "response_item"
            and isinstance(record.get("payload"), dict)
            and record["payload"].get("type") == "message"
            and record["payload"].get("role") == "user"
        ),
        {},
    )
    user_payload = user_record.get("payload", {})
    user_text = "\n".join(
        block.get("text", "")
        for block in user_payload.get("content", [])
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    )
    call_arguments: Any = None
    if isinstance(call_payload.get("arguments"), str):
        try:
            call_arguments = json.loads(call_payload["arguments"])
        except json.JSONDecodeError:
            call_arguments = call_payload["arguments"]
    source_item_ids = [
        record["payload"]["id"]
        for record in records
        if record.get("type") == "response_item"
        and isinstance(record.get("payload"), dict)
        and isinstance(record["payload"].get("id"), str)
    ]

    _record(checks, "source_session_id", source_facts["session_id"], session_payload.get("id"))
    _record(checks, "source_codex_item_ids", source_facts["codex_item_ids"], source_item_ids)
    _record(checks, "source_user_prompt", source_facts["user_prompt"], user_text)
    _record(checks, "source_call_id", source_facts["tool_call_id"], call_payload.get("call_id"))
    _record(checks, "source_tool_name", source_facts["tool_name"], call_payload.get("name"))
    _record(checks, "source_tool_arguments", source_facts["tool_arguments"], call_arguments)
    _record(checks, "source_call_timestamp", source_facts["call_timestamp"], call_record.get("timestamp"))
    _record(checks, "source_timeout_text", source_facts["timeout_text"], result_payload.get("output"))
    _record(
        checks,
        "source_result_correlation",
        source_facts["tool_call_id"],
        result_payload.get("call_id"),
    )
    _record(
        checks,
        "source_result_timestamp",
        source_facts["result_timestamp"],
        result_record.get("timestamp"),
    )

    forbidden_identity_keys = {
        "operation_id",
        "logical_operation_id",
        "provider_operation_id",
        "idempotency_key",
        "provider_receipt",
    }
    found_identity_keys = _find_keys(records, forbidden_identity_keys)
    _record(checks, "no_provider_operation_or_idempotency_identity_in_source", [], found_identity_keys)

    truth_paths = {
        "before_commit_timeout": ground_truth_before_path,
        "after_commit_response_loss": ground_truth_after_path,
    }
    truths: dict[str, dict[str, Any]] = {}
    ground_truth_counts: dict[str, int] = {}
    for scenario, path in truth_paths.items():
        truth = _read_json(path)
        truths[scenario] = truth
        expected_count = oracle["expected_ground_truth"][scenario]
        commit_events = sum(event.get("event") == "effect_committed" for event in truth["events"])
        effect_list_count = len(truth.get("effects", []))
        ground_truth_counts[scenario] = int(truth.get("actual_effect_count", -1))
        _record(checks, f"{scenario}_truth_label", scenario, truth.get("scenario"))
        _record(checks, f"{scenario}_commit_events", expected_count, commit_events)
        _record(checks, f"{scenario}_effect_list_count", expected_count, effect_list_count)
        _record(checks, f"{scenario}_actual_effect_count", expected_count, ground_truth_counts[scenario])
        _record(checks, f"{scenario}_no_provider_operation_id", False, truth.get("provider_operation_identity_observed"))
        _record(checks, f"{scenario}_no_idempotency_key", False, truth.get("idempotency_key_observed"))
        _record(checks, f"{scenario}_no_retry_attempt", 0, truth.get("retry_attempt_count"))
        _record(
            checks,
            f"{scenario}_harness_key_is_labeled_non_provider_identity",
            "test-harness association only; not a provider operation ID",
            truth.get("harness_join_key", {}).get("meaning"),
        )

    _record(
        checks,
        "ground_truths_differ",
        [0, 1],
        [ground_truth_counts["before_commit_timeout"], ground_truth_counts["after_commit_response_loss"]],
    )

    output_paths = {
        "before_commit_timeout": before_output_path,
        "after_commit_response_loss": after_output_path,
    }
    output_documents: dict[str, dict[str, Any]] = {}
    for scenario, path in output_paths.items():
        document = _read_json(path)
        output_documents[scenario] = document
        try:
            trajectory = Trajectory.model_validate(document)
            validation_error = None
        except (TypeError, ValidationError) as error:
            trajectory = None
            validation_error = str(error)
        _record(checks, f"{scenario}_atif_validation", None, validation_error)
        if trajectory is None:
            continue

        calls = [
            call
            for step in trajectory.steps
            for call in (step.tool_calls or [])
        ]
        results = [
            result
            for step in trajectory.steps
            for result in (step.observation.results if step.observation else [])
        ]
        outcome = None
        if len(results) == 1 and isinstance(results[0].extra, dict):
            asb_extra = results[0].extra.get("agent_session_bridge", {})
            if isinstance(asb_extra, dict):
                outcome = asb_extra.get("outcome")
        fidelity = (
            document.get("extra", {})
            .get("agent_session_bridge", {})
            .get("fidelity", {})
        )
        _record(
            checks,
            f"{scenario}_schema_version",
            normalized_facts["schema_version"],
            trajectory.schema_version,
        )
        _record(
            checks,
            f"{scenario}_session_id_preserved",
            source_facts["session_id"],
            trajectory.session_id,
        )
        _record(
            checks,
            f"{scenario}_step_sources",
            normalized_facts["step_sources"],
            [step.source for step in trajectory.steps],
        )
        _record(
            checks,
            f"{scenario}_step_timestamps",
            [source_facts["message_timestamp"], source_facts["call_timestamp"]],
            [step.timestamp for step in trajectory.steps],
        )
        _record(
            checks,
            f"{scenario}_user_prompt_preserved",
            source_facts["user_prompt"],
            trajectory.steps[0].message if trajectory.steps else None,
        )
        _record(checks, f"{scenario}_tool_call_count", 1, len(calls))
        if len(calls) == 1:
            _record(
                checks,
                f"{scenario}_tool_call_id_preserved",
                normalized_facts["tool_call_id"],
                calls[0].tool_call_id,
            )
            _record(
                checks,
                f"{scenario}_tool_name_preserved",
                normalized_facts["tool_name"],
                calls[0].function_name,
            )
            _record(
                checks,
                f"{scenario}_tool_arguments_normalized",
                normalized_facts["tool_arguments"],
                calls[0].arguments,
            )
        _record(checks, f"{scenario}_observation_result_count", 1, len(results))
        if len(results) == 1:
            _record(
                checks,
                f"{scenario}_result_correlation_preserved",
                normalized_facts["result_call_id"],
                results[0].source_call_id,
            )
            _record(
                checks,
                f"{scenario}_timeout_text_preserved",
                normalized_facts["result_text"],
                results[0].content,
            )
        _record(
            checks,
            f"{scenario}_external_effect_outcome_unknown",
            normalized_facts["external_effect_outcome"],
            outcome,
        )

        serialized = json.dumps(document, ensure_ascii=False)
        _record(
            checks,
            f"{scenario}_result_timestamp_omitted_from_receipt",
            False,
            source_facts["result_timestamp"] in serialized,
        )
        _record(
            checks,
            f"{scenario}_omitted_timestamp_counted",
            normalized_facts["fidelity"]["omitted_tool_result_timestamps"],
            fidelity.get("omitted_tool_result_timestamps"),
        )
        for counter in (
            "source_records_preserved",
            "unsupported_source_records",
            "unsupported_source_blocks",
            "orphaned_tool_results",
            "invalid_source_timestamps",
        ):
            _record(
                checks,
                f"{scenario}_{counter}",
                normalized_facts["fidelity"][counter],
                fidelity.get(counter),
            )
        _record(
            checks,
            f"{scenario}_call_counted",
            normalized_facts["fidelity"]["tool_calls_preserved"],
            fidelity.get("tool_calls_preserved"),
        )
        _record(
            checks,
            f"{scenario}_result_counted",
            normalized_facts["fidelity"]["observation_results_preserved"],
            fidelity.get("observation_results_preserved"),
        )
        ignored = fidelity.get("ignored_fields", [])
        id_omission: dict[str, Any] = next(
            (item for item in ignored if item.get("field") == normalized_facts["fidelity"]["ignored_field"]),
            {},
        )
        _record(
            checks,
            f"{scenario}_event_ids_omitted_and_accounted_for",
            normalized_facts["fidelity"]["ignored_field_records"],
            id_omission.get("records"),
        )
        output_string_values = _string_values(document)
        _record(
            checks,
            f"{scenario}_codex_item_ids_not_copied",
            [],
            sorted(set(source_facts["codex_item_ids"]) & output_string_values),
        )
        output_identity_keys = _find_keys(document, forbidden_identity_keys)
        _record(
            checks,
            f"{scenario}_no_provider_identity_in_receipt",
            [],
            output_identity_keys,
        )

    if len(output_documents) == 2:
        _record(
            checks,
            "normalized_receipts_semantically_equal",
            _semantic_projection(output_documents["before_commit_timeout"]),
            _semantic_projection(output_documents["after_commit_response_loss"]),
        )

    decision = _read_json(decision_record_path)
    source_has_authoritative_receipt = "provider_receipt" in _find_keys(
        records, {"provider_receipt"}
    )
    caller_outcome = (
        "KNOWN"
        if source_has_authoritative_receipt
        else "UNKNOWN"
        if result_payload.get("output") == source_facts["timeout_text"]
        else "UNRESOLVED"
    )
    for scenario in truth_paths:
        decision_facts = decision.get("scenarios", {}).get(scenario, {})
        _record(
            checks,
            f"{scenario}_decision_uses_unknown",
            oracle["decision"]["external_effect_outcome"],
            decision_facts.get("external_effect_outcome"),
        )
        _record(
            checks,
            f"{scenario}_retry_not_authorized_from_current_evidence",
            "NOT_AUTHORIZED_FROM_AVAILABLE_EVIDENCE",
            decision_facts.get("automatic_retry"),
        )
    _record(
        checks,
        "caller_side_external_effect_classification",
        oracle["decision"]["external_effect_outcome"],
        caller_outcome,
    )

    command_facts: dict[str, Any] = {"checked": False}
    if commands_path is not None:
        command_records = json.loads(commands_path.read_text(encoding="utf-8"))
        source_paths = [item.get("source") for item in command_records]
        source_hashes = [item.get("source_sha256") for item in command_records]
        truth_names = {ground_truth_before_path.name, ground_truth_after_path.name}
        truth_arguments = [
            argument
            for item in command_records
            for argument in item.get("argv", [])
            if any(name in str(argument) for name in truth_names)
        ]
        _record(checks, "two_normalization_commands", 2, len(command_records))
        _record(
            checks,
            "both_normalization_commands_succeeded",
            [0, 0],
            [item.get("exit_code") for item in command_records],
        )
        _record(checks, "both_commands_use_same_source", 1, len(set(source_paths)))
        _record(checks, "both_commands_use_same_source_hash", 1, len(set(source_hashes)))
        _record(checks, "normalizer_not_given_truth_files", [], truth_arguments)
        _record(
            checks,
            "normalizer_source_hash_matches_fixture",
            _sha256(source_path),
            source_hashes[0] if source_hashes else None,
        )
        command_shapes = [_is_codex_import(item) for item in command_records]
        _record(checks, "normalizer_uses_supported_codex_import", [True, True], command_shapes)
        command_facts = {
            "checked": True,
            "normalizer_inputs": source_paths,
            "source_hashes": source_hashes,
            "ground_truth_arguments": truth_arguments,
        }

    conflicts = [check for check in checks if check["status"] == "CONFLICT"]
    return {
        "schema_version": "tfb-ambiguous-tool-outcomes-verification-v1",
        "summary": {
            "passed": not conflicts,
            "checks": len(checks),
            "conflicts": len(conflicts),
        },
        "caller_visible_conclusion": {
            "external_effect_outcome": caller_outcome,
            "basis": "the same timeout output is present and no authoritative provider receipt is present",
            "tfb_annotation": "unknown",
        },
        "provider_ground_truth": {
            scenario: {"actual_effect_count": ground_truth_counts[scenario], "events": truths[scenario]["events"]}
            for scenario in truth_paths
        },
        "retry_decision": decision,
        "normalizer_command_boundary": command_facts,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--ground-truth-before", type=Path, required=True)
    parser.add_argument("--ground-truth-after", type=Path, required=True)
    parser.add_argument("--before-output", type=Path, required=True)
    parser.add_argument("--after-output", type=Path, required=True)
    parser.add_argument("--decision-record", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--commands", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    try:
        report = verify_experiment(
            source_path=args.source,
            ground_truth_before_path=args.ground_truth_before,
            ground_truth_after_path=args.ground_truth_after,
            before_output_path=args.before_output,
            after_output_path=args.after_output,
            decision_record_path=args.decision_record,
            oracle_path=args.oracle,
            commands_path=args.commands,
        )
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"Verification could not complete: {error}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if report["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
