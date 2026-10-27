"""Preparation and disclosure remain public CLI operations over shared review facts."""

import json

import pytest

from brz2obsidian.cli import main
from brz2obsidian.cli_review import CliReviewResult, report


def test_review_help_explains_preparation_routes_and_retained_history_limits(capsys):
    assert main(["review", "--help"]) == 0
    group = capsys.readouterr()
    assert group.err == ""
    for term in (
        "prepare",
        "inspect",
        "apply",
        "status",
        "Windows",
        "idle",
        "Git",
        "missing history",
        "disk",
        "stage-two",
    ):
        assert term in group.out
    assert main(["review", "prepare", "--help"]) == 0
    preparation = capsys.readouterr()
    assert preparation.err == ""
    for term in (
        "BRZ",
        "source-update",
        "onboarding",
        "format-transition",
        "attachment-cleanup",
        "--original-source",
        "configuration",
        "history pruning",
    ):
        assert term in preparation.out


@pytest.mark.parametrize(
    "options",
    (
        (),
        ("--kind", "attachment-cleanup", "--source", "incoming.brz"),
        ("--kind", "format-transition", "--original-source", "original.brz"),
    ),
)
def test_prepare_rejects_inapplicable_source_options_before_touching_vault(
    tmp_path, capsys, options
):
    vault = tmp_path / "untouched"
    assert main(["review", "prepare", str(vault), *options, "--json"]) == 2
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["command"] == "prepare"
    assert (
        result["status"] == "refused" and result["code"] == "invalid_review_arguments"
    )
    assert result["ready"] is False and result["publication"] == "not_started"
    assert not vault.exists()


def test_prepared_review_reports_persistence_and_remaining_work(capsys):
    from brz2obsidian.application.checkpoint_contracts import CheckpointResult
    from brz2obsidian.contracts import OutputIdentity, SourceIdentity

    result = CliReviewResult(
        command="prepare",
        kind="source_update",
        status="prepared_review",
        code="saved",
        ready=False,
        proposal_id="review:prepared",
        generation=3,
        changes=5,
        unresolved=2,
        stale=0,
        source=SourceIdentity(
            source_id="collection-one",
            module_id="thebrain-brz",
            module_version="10",
            format_version="5",
            source_sha256="1" * 64,
            snapshot_digest="2" * 64,
        ),
        output_identity=OutputIdentity(
            collection_id="collection-one",
            module_id="thebrain-brz",
            module_version="10",
            profile_id="thebrain-format5-reviewed",
            profile_version="10",
            output_format=7,
            settings_digest="3" * 64,
        ),
        capture=CheckpointResult(
            schema_id="brz2obsidian.checkpoint-result",
            schema_version=1,
            status="captured",
            code="captured",
            commit="4" * 40,
            ref="refs/brz2obsidian/imports/example/checkpoints",
            history_retained=True,
            objects_written=True,
            object_storage="verified",
            authored_files_changed=False,
            message="Saved review.",
        ),
        checkpoint_commit="4" * 40,
        history_retained=True,
        publication="not_started",
        retained_source_provenance=False,
        source_gap_count=1,
        diagnostic_omission=True,
        recovery_gaps=("original_source_unavailable",),
        omissions=("source_gaps",),
        next_actions=("resolve_update", "save_update"),
        summary="Five review changes; two choices remain.",
        guidance=("Keep the target vault idle. Retained history grows disk use.",),
    )
    assert report(result, json_output=False) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    for text in (
        "thebrain-brz 10",
        "format: 5",
        "thebrain-format5-reviewed 10",
        "output format: 7",
        "review:prepared",
        "generation: 3",
        "unresolved: 2",
        "captured",
        "verified",
        "4" * 40,
        "Baseline payload bytes reused: no",
        "Source gaps: 1",
        "original_source_unavailable",
        "omitted",
        "resolve_update",
        "idle",
        "disk",
    ):
        assert text in captured.out


@pytest.mark.parametrize(
    ("command", "status", "publication", "expected"),
    (
        ("inspect", "prepared_review", "not_started", 0),
        ("inspect", "stale_review", "not_started", 2),
        ("apply", "no_content_change", "not_published", 0),
        ("apply", "cancelled_before_publication", "not_published", 2),
    ),
)
def test_review_purpose_exit_preserves_readiness_and_publication(
    capsys, command, status, publication, expected
):
    result = CliReviewResult(
        command=command,
        status=status,
        code="observed",
        ready=False,
        publication=publication,
        unresolved=2 if command == "inspect" else 0,
        summary="Actual supplied shared outcome.",
        guidance=(),
    )
    assert report(result, json_output=True) == expected
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == status and value["ready"] is False
    assert value["publication"] == publication
