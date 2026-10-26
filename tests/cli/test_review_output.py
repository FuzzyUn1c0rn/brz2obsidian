"""Typed CLI presentation keeps operation truth and its exit status together."""

import json

import pytest

from brz2obsidian.application.vault_update_contracts import VaultApplyResult
from brz2obsidian.cli_review import CliReviewResult, report


@pytest.mark.parametrize(
    "status,native_status,publication,history,expected_exit,json_output",
    [
        ("available", "applied", "complete", "terminal", 0, True),
        ("available", "no_content_change", "complete", "terminal", 0, True),
        ("available", "undone", "complete", "terminal", 0, True),
        ("available", "restored", "complete", "terminal", 0, False),
        ("recovery_required", "incomplete", "partial", "intent", 2, False),
        ("recovery_required", "unknown", "unknown", "unknown", 1, True),
        ("recovery_required", "failed", "not_published", "prepared", 1, False),
        ("unavailable", "refused", "not_started", "none", 2, True),
        ("initialization_required", "unknown", "unknown", "unknown", 2, True),
        ("unknown", None, None, None, 1, True),
    ],
)
def test_review_report_preserves_outcome_and_classifies_requested_status(
    capsys, status, native_status, publication, history, expected_exit, json_output
):
    operation = None
    if native_status is not None:
        complete = publication == "complete"
        no_change = native_status == "no_content_change"
        absent = status in ("initialization_required", "unavailable")
        operation = VaultApplyResult(
            schema_id="brz2obsidian.vault-apply-result",
            schema_version=1,
            status=native_status,
            code="operation_history_invalid" if absent else "observed_operation",
            operation_id=None if absent else "1" * 32,
            kind="undo" if native_status == "undone" else "apply",
            direction=None
            if absent
            else "restore"
            if native_status == "restored"
            else "finish",
            generation=None if absent else 7,
            phase="admission" if absent else "terminal" if complete else "publication",
            publication=publication,
            history=history,
            planned_files=0 if no_change or absent else 2,
            published_files=0
            if no_change
            else 2
            if complete
            else 1
            if publication == "partial"
            else 0,
            authored_files_changed=False
            if no_change or publication in ("not_started", "not_published")
            else True
            if complete or publication == "partial"
            else None,
            checkpoint_commit=None if absent else "2" * 40,
            intent_commit=None if absent else "3" * 40,
            result_commit="4" * 40 if complete else None,
            receipt_commit="5" * 40 if complete else None,
            recovery_required=not complete,
            elapsed_ms=12,
            message="Observed native operation.",
        )
    next_action = (
        "initialize_vault"
        if status == "initialization_required"
        else "review_update"
        if status == "available"
        else "inspect_history"
    )
    result = CliReviewResult(
        command="status",
        status=status,
        code="observed_history",
        operation=operation,
        history_retained=None
        if operation is None
        else history in ("prepared", "intent", "terminal"),
        next_actions=(next_action,),
        summary="Current shared history observation.",
        guidance=("Keep the vault idle while an operation runs.",),
    )

    exit_code = report(result, json_output=json_output)
    captured = capsys.readouterr()
    assert exit_code == expected_exit
    assert captured.err == ""
    if json_output:
        value = json.loads(captured.out)
        assert value["schema"] == "brz2obsidian.cli-review-result"
        assert value["status"] == status
        assert value["ready"] is False
        assert value["next_actions"] == [next_action]
        if operation is None:
            assert value["operation"] is None
        else:
            assert value["operation"]["status"] == native_status
            assert value["operation"]["operation_id"] == (None if absent else "1" * 32)
            assert value["operation"]["generation"] == (None if absent else 7)
            assert value["operation"]["publication"] == publication
            assert value["operation"]["history"] == history
    else:
        assert f"review status: {status}" in captured.out
        assert f"Outcome: {native_status}" in captured.out
        assert f"Operation: {'1' * 32}; generation: 7" in captured.out
        assert f"publication: {publication}; history: {history}" in captured.out
        assert f"Next actions: {next_action}" in captured.out
        assert "Keep the vault idle" in captured.out
