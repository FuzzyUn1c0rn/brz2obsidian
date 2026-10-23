"""Real process boundaries for interrupted operations and reviewed recovery."""

import json
import subprocess
import sys
from pathlib import Path

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.vault_update_contracts import VaultApplyResult
from brz2obsidian.contracts import (
    CurrentContent,
    ExactContent,
    FormatBaselineOutput,
    IdentityTargetFacts,
)
from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
from brz2obsidian.obsidian import inspect_text_candidate
from tests.application.test_vault_checkpoints import fixture_case, git, user_state
from tests.application.test_vault_recovery_graph import _record
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, with_review_links

_BASE = {
    "Notes/Closing.md": b"closing baseline\r\n",
    "Notes/Opening.md": b"opening baseline\r\n",
}
_BEFORE = {
    "Notes/Closing.md": b"closing authored\r\n",
    "Notes/Opening.md": b"opening authored\r\n",
}
_AFTER = {
    "Notes/Closing.md": b"closing incoming\n",
    "Notes/Opening.md": b"opening incoming\n",
}

_APPLY_CHILD = """
import os
import sys
from pathlib import Path
from brz2obsidian.application.operations import Operations
from brz2obsidian.contracts import ReviewPlan
from brz2obsidian.publication.vault_apply import _NativeExecutor

class StopAfterMove(_NativeExecutor):
    def move(self, stage, target, *, replace):
        super().move(stage, target, replace=replace)
        os._exit(73)

review = ReviewPlan.model_validate_json(Path(sys.argv[3]).read_bytes())
operations = Operations(vault_executor=StopAfterMove())
result = operations.apply_reviewed_update(
    sys.argv[1], sys.argv[2], review=review,
    source_binding=operations.observe_reviewed_source(sys.argv[2], review),
    vault_id="vault-one", import_id="import-one",
)
print(result.model_dump_json(), flush=True)
os._exit(75)
"""

_RECOVERY_CHILD = """
import os
import sys
from pathlib import Path
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.vault_recovery_contracts import VaultRecoveryPreparation
from brz2obsidian.publication.vault_apply import _NativeExecutor

class StopAfterMove(_NativeExecutor):
    def move(self, stage, target, *, replace):
        super().move(stage, target, replace=replace)
        os._exit(74)

preparation = VaultRecoveryPreparation.model_validate_json(Path(sys.argv[2]).read_bytes())
result = Operations(vault_executor=StopAfterMove()).execute_recovery(sys.argv[1], preparation)
print(result.model_dump_json(), flush=True)
os._exit(76)
"""


def _child(script, *arguments, expected=0):
    result = subprocess.run(
        [sys.executable, "-c", script, *(str(value) for value in arguments)],
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == expected, (
        result.returncode,
        result.stdout.decode(errors="replace"),
        result.stderr.decode(errors="replace"),
    )
    return result.stdout


def _fresh_status(vault):
    return VaultApplyResult.model_validate_json(
        _child(
            "import sys; from brz2obsidian.application.operations import Operations; "
            "print(Operations().inspect_update_status(sys.argv[1]).model_dump_json())",
            vault,
        )
    )


def _incoming_candidate(facts, subject, content):
    entry = next(
        row
        for row in facts.identity_inventory
        if row.identity is not None and row.identity.item_id == subject.item_id
    )
    context = facts.link_context
    document = next(
        row for row in context.incoming_documents if row.source_path == subject.path
    )
    return inspect_text_candidate(
        ExactContent(data=content),
        identity=entry.identity,
        target=subject.source_target,
        output_format=7,
        source_path=subject.path,
        document_id=document.document_id,
        path_mode="vault",
        link_targets=context.incoming_targets,
        link_target_facts=context.incoming_target_facts,
        link_inventory="complete",
    )


def _two_note_case():
    """Two real source items make a one-move interruption genuinely partial."""
    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    git(vault, "config", "process.fixture", "preserve this user value")
    (vault / "Notes").mkdir()
    (source / "Notes").mkdir()
    for path, content in _BASE.items():
        (vault / path).write_bytes(content)
        (source / path).write_bytes(content)
    (vault / "Unrelated.bin").write_bytes(b"protected\x00\xff")
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "two source items and unrelated user file")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    git(vault, "update-ref", "refs/brz2obsidian/user-independent", "HEAD")
    facts = request(
        original=_BASE["Notes/Opening.md"],
        current=_BEFORE["Notes/Opening.md"],
        incoming=_AFTER["Notes/Opening.md"],
    )
    opening = facts.subjects[0]
    closing_current = CurrentContent(
        existence="present",
        path="Notes/Closing.md",
        content=ExactContent(data=_BEFORE["Notes/Closing.md"]),
    )
    closing_target = IdentityTargetFacts(
        normalized_path="notes/closing.md", containment="contained", status="safe"
    )
    closing = opening.model_copy(
        update={
            "item_id": "entry:closing",
            "path": "Notes/Closing.md",
            "title": "Closing",
            "baseline": opening.baseline.model_copy(
                update={"content": ExactContent(data=_BASE["Notes/Closing.md"])}
            ),
            "current": closing_current,
            "incoming": ExactContent(data=_AFTER["Notes/Closing.md"]),
            "source_target": closing_target,
        }
    )
    closing_entry = facts.identity_inventory[0].model_copy(
        update={
            "entry_id": "closing-entry",
            "identity": facts.identity_inventory[0].identity.model_copy(
                update={"item_id": "entry:closing"}
            ),
            "title": "Closing",
            "current": closing_current,
            "target": closing_target,
        }
    )
    baseline = facts.format_operation.established_baseline
    facts = with_review_links(
        facts.model_copy(
            update={
                "subjects": (opening, closing),
                "identity_inventory": (*facts.identity_inventory, closing_entry),
                "format_operation": facts.format_operation.model_copy(
                    update={
                        "established_baseline": baseline.model_copy(
                            update={
                                "outputs": (
                                    *baseline.outputs,
                                    FormatBaselineOutput(
                                        item_id="entry:closing",
                                        facet="content",
                                        content=ExactContent(
                                            data=_BASE["Notes/Closing.md"]
                                        ),
                                    ),
                                )
                            }
                        )
                    }
                ),
            }
        )
    )
    operations = Operations()
    seeded = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=facts.incoming_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert seeded.status == "captured", seeded.code
    (vault / "Notes/Opening.md").write_bytes(b"opening staged\n")
    git(vault, "add", "Notes/Opening.md")
    for path, content in _BEFORE.items():
        (vault / path).write_bytes(content)
        (source / path).write_bytes(_AFTER[path])
    plan = prepare_review(
        facts, preflight=operations.inspect_history(vault).admission.preflight
    )
    for subject in facts.subjects:
        change = next(row for row in plan.proposal.changes if row.path == subject.path)
        selected = resolve_review(
            plan,
            action(
                plan,
                change,
                choice="incoming",
                decision_id="process:initial:" + subject.item_id,
                candidate=_incoming_candidate(facts, subject, _AFTER[subject.path]),
            ),
        )
        assert selected.status == "accepted", selected.code
        plan = selected.plan
    assert plan.ready, (plan.requirements, plan.blockers)
    review_path = vault.parent / "process-review.json"
    review_path.write_text(plan.model_dump_json(), encoding="utf-8")
    return vault, source, review_path, user_state(vault), seeded.ref


def _assert_user_state(before, after, *, allowed_refs):
    for key in ("index", "head", "config", "stages"):
        assert after[key] == before[key], key
    assert tuple(
        row for row in after["refs"] if row.split(b" ", 1)[0] not in allowed_refs
    ) == tuple(
        row for row in before["refs"] if row.split(b" ", 1)[0] not in allowed_refs
    )


def _choose_recovery(vault, preparation, *, desired, retained_path):
    assert preparation.status == "offered", preparation.code
    assert preparation.review is not None
    while preparation.review.requirements:
        requirement = preparation.review.requirements[0]
        change = next(
            row
            for row in preparation.review.proposal.changes
            if row.change_id == requirement.change_id
        )
        subject = next(
            row
            for row in preparation.review.facts.subjects
            if (row.item_id, row.facet) == (change.item_id, change.facet)
        )
        keep = subject.path == retained_path
        selected = Operations().resolve_recovery(
            vault,
            preparation,
            action(
                preparation.review,
                change,
                domain="text",
                choice="current" if keep else "incoming",
                decision_id="process:recovery:" + subject.item_id,
                candidate=None
                if keep
                else _incoming_candidate(
                    preparation.review.facts, subject, desired[subject.path]
                ),
            ),
        )
        assert selected.status == "offered", selected.code
        preparation = selected
    assert preparation.review.ready, preparation.review.blockers
    return preparation


def test_second_process_stop_retains_restore_authority_and_finishes_without_new_moves(
    monkeypatch,
):
    vault, source, review_path, before, checkpoint_ref = _two_note_case()
    _child(_APPLY_CHILD, vault, source, review_path, expected=73)
    assert (vault / "Notes/Closing.md").read_bytes() == b"closing incoming\n"
    assert (vault / "Notes/Opening.md").read_bytes() == b"opening authored\r\n"
    (vault / "Notes/Opening.md").write_bytes(b"opening authored\r\nlater user note\n")
    completed_bytes = {
        "Notes/Closing.md": b"closing authored\r\n",
        "Notes/Opening.md": b"opening authored\r\nlater user note\n",
    }
    preparation = _choose_recovery(
        vault,
        Operations().prepare_recovery(vault, direction="restore"),
        desired=_BEFORE,
        retained_path="Notes/Opening.md",
    )
    saved_review_generation = preparation.review.proposal.generation
    owner = vault / ".git/brz2obsidian/owner.json"
    locator = vault / ".brz2obsidian/locator.json"
    locator_before = locator.read_bytes()
    original_unlink, original_lstat = Path.unlink, Path.lstat
    cleanup_failed = False
    captured_locator = None

    def fail_owner_cleanup(path, *arguments, **options):
        nonlocal cleanup_failed, captured_locator
        if path == owner:
            captured_locator = locator.read_bytes()
            cleanup_failed = True
            raise OSError("Fixture-owned marker cleanup failed")
        return original_unlink(path, *arguments, **options)

    def unavailable_locator_after_cleanup(path, *arguments, **options):
        if cleanup_failed and path == locator:
            raise OSError("Transient locator read failure during cleanup")
        return original_lstat(path, *arguments, **options)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_owner_cleanup)
        patch.setattr(Path, "lstat", unavailable_locator_after_cleanup)
        failed = Operations().execute_recovery(vault, preparation, cancel=lambda: True)
    assert cleanup_failed
    assert (failed.status, failed.code, failed.phase, failed.publication) == (
        "unknown",
        "recovery_cleanup_failed",
        "prepared",
        "unknown",
    )
    assert failed.operation_id == preparation.operation_id
    assert failed.intent_commit == preparation.intent_commit
    assert failed.generation == 2 and failed.recovery_required
    assert failed.authored_files_changed is None
    assert owner.is_file() and captured_locator != locator_before
    assert locator.read_bytes() == captured_locator
    assert (vault / "Notes/Closing.md").read_bytes() == b"closing incoming\n"
    assert (vault / "Notes/Opening.md").read_bytes() == completed_bytes[
        "Notes/Opening.md"
    ]
    pending = _fresh_status(vault)
    assert (pending.status, pending.code) == ("unknown", "unknown_current_bytes")
    assert pending.intent_commit == preparation.intent_commit
    assert pending.generation == 2 and pending.recovery_required

    recovery_path = vault.parent / "process-recovery.json"
    recovery_path.write_text(preparation.model_dump_json(), encoding="utf-8")
    _child(_RECOVERY_CHILD, vault, recovery_path, expected=74)

    for path, expected in completed_bytes.items():
        assert (vault / path).read_bytes() == expected
    assert (vault / "Unrelated.bin").read_bytes() == b"protected\x00\xff"
    observed = _fresh_status(vault)
    assert (
        observed.status,
        observed.publication,
        observed.kind,
        observed.direction,
        observed.generation,
        observed.planned_files,
        observed.published_files,
    ) == ("content_complete", "complete", "apply", "restore", 3, 1, 1)
    assert observed.review_generation == saved_review_generation
    assert observed.recovery_required
    assert observed.intent_commit != preparation.intent_commit
    stopped_state = user_state(vault)
    refused = Operations().prepare_recovery(vault, direction="finish")
    assert refused.status == "refused"
    assert refused.code == "saved_recovery_direction_required"
    stale = Operations().execute_recovery(vault, preparation)
    assert stale.status == "refused" and stale.recovery_required
    assert user_state(vault) == stopped_state
    for path, expected in completed_bytes.items():
        assert (vault / path).read_bytes() == expected

    resumed = _choose_recovery(
        vault,
        Operations().prepare_recovery(vault, direction="restore"),
        desired=_BEFORE,
        retained_path="Notes/Opening.md",
    )
    completed = Operations().execute_recovery(vault, resumed)
    assert (
        completed.status,
        completed.kind,
        completed.direction,
        completed.planned_files,
        completed.published_files,
        completed.authored_files_changed,
    ) == ("restored", "apply", "restore", 0, 0, False)
    assert completed.receipt_commit and not completed.recovery_required
    for path, expected in completed_bytes.items():
        assert (vault / path).read_bytes() == expected
    assert (vault / "Unrelated.bin").read_bytes() == b"protected\x00\xff"
    operation_ref = (
        checkpoint_ref.removesuffix("/checkpoints")
        + "/operations/"
        + observed.operation_id
    )
    _assert_user_state(
        before,
        user_state(vault),
        allowed_refs={checkpoint_ref.encode(), operation_ref.encode()},
    )


def test_retained_undo_kind_finishes_with_verified_undone_receipt_without_new_moves():
    vault, source, review_path, before, checkpoint_ref = _two_note_case()
    _child(_APPLY_CHILD, vault, source, review_path, expected=73)
    assert (vault / "Notes/Closing.md").read_bytes() == b"closing incoming\n"
    assert (vault / "Notes/Opening.md").read_bytes() == b"opening authored\r\n"

    # Fixture-only durable undo origin, over exact canonical original history
    # and real partial bytes. Production latest-Undo publication belongs to #275.
    operation_refs = (
        git(vault, "for-each-ref", "--format=%(refname)", "refs/brz2obsidian/imports")
        .decode()
        .splitlines()
    )
    (operation_ref,) = (ref for ref in operation_refs if "/operations/" in ref)
    previous = git(vault, "rev-parse", operation_ref).decode().strip()
    origin = json.loads(git(vault, "show", previous + ":intent.json"))
    origin["kind"] = "undo"
    undo_origin = _record(vault, "intent.json", origin, (origin["prepared_commit"],))
    git(vault, "update-ref", operation_ref, undo_origin, previous)

    # A real later user edit completes the remaining target bytes; no terminal
    # journal or receipt is fabricated, and production recovery must prove it.
    kept_closing = b"closing incoming\nlater writing\n"
    (vault / "Notes/Closing.md").write_bytes(kept_closing)
    (vault / "Notes/Opening.md").write_bytes(b"opening incoming\n")
    preparation = _choose_recovery(
        vault,
        Operations().prepare_recovery(vault, direction="finish"),
        desired=_AFTER,
        retained_path="Notes/Closing.md",
    )
    closing_change = next(
        row
        for row in preparation.review.proposal.changes
        if row.path == "Notes/Closing.md"
    )
    approval_choices = {
        approval.change_id: approval.choice for approval in preparation.review.approvals
    }
    assert approval_choices[closing_change.change_id] == "current"
    selected = select_review_effects(preparation.review)
    assert selected.status == "selected" and selected.remove_paths == ()
    assert {row.path: row.content.data for row in selected.files} == {
        "Notes/Closing.md": kept_closing,
        "Notes/Opening.md": b"opening incoming\n",
    }
    completed = Operations().execute_recovery(vault, preparation)
    assert (
        completed.status,
        completed.kind,
        completed.direction,
        completed.generation,
        completed.planned_files,
        completed.published_files,
        completed.authored_files_changed,
    ) == ("undone", "undo", "finish", 3, 0, 0, False)
    assert completed.receipt_commit and not completed.recovery_required
    fresh = _fresh_status(vault)
    assert (fresh.status, fresh.kind, fresh.direction, fresh.generation) == (
        "undone",
        "undo",
        "finish",
        3,
    )
    assert fresh.receipt_commit == completed.receipt_commit
    assert not fresh.recovery_required
    assert (vault / "Notes/Closing.md").read_bytes() == kept_closing
    assert (vault / "Notes/Opening.md").read_bytes() == b"opening incoming\n"
    assert (vault / "Unrelated.bin").read_bytes() == b"protected\x00\xff"
    _assert_user_state(
        before,
        user_state(vault),
        allowed_refs={checkpoint_ref.encode(), operation_ref.encode()},
    )
