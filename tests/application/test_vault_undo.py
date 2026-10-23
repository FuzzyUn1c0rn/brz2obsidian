"""Reviewed latest-operation Undo through the public Operations boundary."""

import hashlib
import json
import tempfile
from pathlib import Path

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.vault_recovery_contracts import VaultRecoveryPreparation
from brz2obsidian.application.vault_undo_contracts import VaultUndoPreparation
from brz2obsidian.contracts import ExactContent, LinkOccurrenceChoice, ReviewPlan
from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
from brz2obsidian.obsidian import interpret_link_target, interpret_links
from brz2obsidian.publication.vault_apply import _NativeExecutor
from tests.application.test_vault_apply import _apply
from tests.application.test_vault_checkpoints import user_state
from tests.application.test_vault_recovery_process import (
    _AFTER,
    _BASE,
    _BEFORE,
    _assert_user_state,
    _child,
    _fresh_status,
    _incoming_candidate,
    _two_note_case,
)
from tests.reconciliation.test_attachments import (
    attachment_candidate,
    linked_attachment_request,
)
from tests.reconciliation.test_resolution import action

_UNDO_CHILD = """
import os
import sys
from pathlib import Path
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.vault_undo_contracts import VaultUndoPreparation
from brz2obsidian.publication.vault_apply import _NativeExecutor

class StopAfterMove(_NativeExecutor):
    def move(self, stage, target, *, replace):
        super().move(stage, target, replace=replace)
        os._exit(81)

preparation = VaultUndoPreparation.model_validate_json(Path(sys.argv[2]).read_bytes())
result = Operations(vault_executor=StopAfterMove()).execute_undo(sys.argv[1], preparation)
print(result.model_dump_json(), flush=True)
os._exit(82)
"""


def _with_review(prepared, review):
    contract = type(prepared)
    assert contract in (VaultUndoPreparation, VaultRecoveryPreparation)
    return contract.model_validate(
        {**prepared.model_dump(mode="python"), "review": review}
    )


def _preserve_candidate_inputs(vault, preparation, selected_action):
    directory = (
        Path(__file__).resolve().parents[2]
        / "tmp/issue-275/candidate-fixtures"
        / vault.parent.name
    )
    directory.mkdir(parents=True)
    (directory / "prior-ready-preparation.json").write_bytes(
        preparation.model_dump_json().encode("utf-8")
    )
    (directory / "prior-action.json").write_bytes(
        selected_action.model_dump_json().encode("utf-8")
    )
    return directory


def _preserve_candidate_result(
    directory, vault, preparation, applied, returned, observed, before, allowed
):
    (directory / "executed-preparation.json").write_bytes(
        preparation.model_dump_json().encode("utf-8")
    )
    owner = json.loads((vault.parent / ".fixture-owner.json").read_text())
    expected = {
        "Assets/data.bin": b"\x00authored".hex(),
        "Notes/Closing.md": b"closing authored\r\n".hex(),
        "Notes/Opening.md": b"opening incoming\nlater writing\n".hex(),
        "Notes/Owner.md": (
            b"[[Assets/data.bin|Keep first]] and [[Assets/data.bin|Redirect second]]".hex()
        ),
        "Unrelated.bin": b"protected\x00\xff".hex(),
    }
    actual = {
        path.relative_to(vault).as_posix(): path.read_bytes().hex()
        for path in vault.rglob("*")
        if path.is_file()
        and path.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    }
    assert actual == expected
    files = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.iterdir()
        if path.is_file()
    }
    descriptor = {
        "vault": str(vault),
        "fixture_root": str(vault.parent),
        "fixture_owner": owner,
        "owner_ledger": str(
            Path(__file__).resolve().parents[2]
            / "tmp/issue-272/fixtures"
            / (owner["owner"] + ".json")
        ),
        "expected_authored_hex": expected,
        "expected_absent": ["Assets/data (incoming-ba7816bf).bin"],
        "expected_terminal": {
            "status": "undone",
            "kind": "undo",
            "direction": "finish",
            "planned_files": 3,
            "published_files": 3,
        },
        "applied": applied.model_dump(mode="json"),
        "returned": returned.model_dump(mode="json"),
        "undone": observed.model_dump(mode="json"),
        "user_git_before_hex": {
            name: value.hex()
            if isinstance(value, bytes)
            else [row.hex() for row in value]
            for name, value in before.items()
            if name != "authored"
        },
        "allowed_owned_refs_hex": sorted(row.hex() for row in allowed),
        "input_sha256": files,
    }
    (directory / "fixture.json").write_text(
        json.dumps(descriptor, indent=2), encoding="utf-8"
    )


def _choose_undo(vault, prepared, *, retained_path=None, prefix="undo"):
    outer_resolution = True
    while prepared.review.requirements:
        requirement = prepared.review.requirements[0]
        change = next(
            row
            for row in prepared.review.proposal.changes
            if row.change_id == requirement.change_id
        )
        subject = next(
            row
            for row in prepared.review.facts.subjects
            if (row.item_id, row.facet) == (change.item_id, change.facet)
        )
        keep = subject.path == retained_path
        choice = action(
            prepared.review,
            change,
            choice="current" if keep else "incoming",
            decision_id=prefix + ":" + subject.item_id,
            candidate=None
            if keep
            else _incoming_candidate(
                prepared.review.facts, subject, _BEFORE[subject.path]
            ),
        )
        if outer_resolution:
            prepared = Operations().resolve_undo(vault, prepared, choice)
            outer_resolution = False
        else:
            transition = resolve_review(prepared.review, choice)
            assert transition.status == "accepted", transition.code
            prepared = _with_review(prepared, transition.plan)
        assert prepared.status == "offered", prepared.code
    assert prepared.review.ready, prepared.review.blockers
    return prepared


def _choose_restore(prepared, *, retained_path):
    while prepared.review.requirements:
        requirement = prepared.review.requirements[0]
        change = next(
            row
            for row in prepared.review.proposal.changes
            if row.change_id == requirement.change_id
        )
        subject = next(
            row
            for row in prepared.review.facts.subjects
            if (row.item_id, row.facet) == (change.item_id, change.facet)
        )
        keep = subject.path == retained_path
        transition = resolve_review(
            prepared.review,
            action(
                prepared.review,
                change,
                choice="current" if keep else "incoming",
                decision_id="undo:restore:" + subject.item_id,
                candidate=None
                if keep
                else _incoming_candidate(
                    prepared.review.facts,
                    subject,
                    _AFTER[subject.path],
                ),
            ),
        )
        assert transition.status == "accepted", transition.code
        prepared = _with_review(prepared, transition.plan)
    assert prepared.review.ready, prepared.review.blockers
    return prepared


def _operation_ref(checkpoint_ref, operation_id):
    return (
        checkpoint_ref.removesuffix("checkpoints") + "operations/" + operation_id
    ).encode()


def _both_with_owner(facts, content):
    selection, candidate = attachment_candidate(facts, "both")
    old_doc = next(
        row
        for row in facts.link_context.current_documents
        if row.source_path == "Notes/Owner.md"
    )
    document = interpret_links(
        ExactContent(data=content),
        document_id=old_doc.document_id,
        source_path=old_doc.source_path,
        path_mode="vault",
        targets=candidate.targets,
        target_facts=candidate.target_facts,
        inventory="complete",
    )
    selection = selection.model_copy(
        update={
            "link_choices": (
                LinkOccurrenceChoice(
                    document_id=old_doc.document_id,
                    occurrence_id=old_doc.occurrences[1].occurrence_id,
                    old=old_doc.occurrences[1].meaning,
                    replacement=b"[Second edited alias](Assets/data%20%28incoming-ba7816bf%29.bin)",
                    selected=document.occurrences[1].meaning,
                    expected_memberships=(),
                    provenance="explicit_user",
                ),
            )
        }
    )
    candidate = candidate.model_copy(
        update={
            "documents": tuple(
                document if row.document_id == document.document_id else row
                for row in candidate.documents
            ),
            "target_facts": tuple(
                interpret_link_target(
                    document.content,
                    target_id="owner:note",
                    existence="present",
                    memberships=(),
                )
                if row.target_id == "owner:note"
                else row
                for row in candidate.target_facts
            ),
        }
    )
    return selection, candidate


def _mixed_case():
    """One actual update owns text, a binary version and its real link document."""
    vault, source, review_path, user_before, checkpoint_ref = _two_note_case()
    notes = ReviewPlan.model_validate_json(review_path.read_bytes()).producer_facts
    binary = linked_attachment_request(payload_current=b"\x00authored")
    subject = binary.subjects[0].model_copy(update={"item_id": "entry:asset"})
    inventory = tuple(
        row.model_copy(
            update={
                "identity": row.identity.model_copy(update={"item_id": "entry:asset"}),
                "entry_id": "binary:" + row.entry_id,
            }
        )
        for row in binary.identity_inventory
    )
    context = binary.link_context.model_copy(
        update={
            name: tuple(
                reference.model_copy(
                    update={
                        "identity": reference.identity.model_copy(
                            update={"item_id": "entry:asset"}
                        )
                    }
                )
                if reference.identity is not None
                else reference
                for reference in getattr(binary.link_context, name)
            )
            for name in ("current_targets", "incoming_targets")
        }
    )
    merged_context = notes.link_context.model_copy(
        update={
            name: getattr(notes.link_context, name) + getattr(context, name)
            for name in (
                "current_targets",
                "incoming_targets",
                "current_target_facts",
                "incoming_target_facts",
                "current_documents",
                "incoming_documents",
            )
        }
    )
    facts = notes.model_copy(
        update={
            "subjects": (*notes.subjects, subject),
            "identity_inventory": (*notes.identity_inventory, *inventory),
            "link_context": merged_context,
            "format_operation": notes.format_operation.model_copy(
                update={
                    "established_baseline": notes.format_operation.established_baseline.model_copy(
                        update={
                            "outputs": (
                                *notes.format_operation.established_baseline.outputs,
                                *(
                                    row.model_copy(update={"item_id": "entry:asset"})
                                    for row in binary.format_operation.established_baseline.outputs
                                ),
                            )
                        }
                    )
                }
            ),
        }
    )
    (vault / "Assets").mkdir()
    (source / "Assets").mkdir()
    (vault / "Assets/data.bin").write_bytes(b"\x00authored")
    (source / "Assets/data.bin").write_bytes(b"\x00original")
    original_document = context.current_documents[0].content.data
    (vault / "Notes/Owner.md").write_bytes(original_document)
    (source / "Notes/Owner.md").write_bytes(original_document)
    for path, content in _BASE.items():
        (source / path).write_bytes(content)
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
    for path, content in _AFTER.items():
        (source / path).write_bytes(content)
    (source / "Assets/data.bin").write_bytes(b"abc")
    offered = prepare_review(
        facts, preflight=operations.inspect_history(vault).admission.preflight
    )
    changed_document = b"[[Assets/data.bin|Keep first]] and [Second edited alias](Assets/data%20%28incoming-ba7816bf%29.bin)"
    selection, candidate = _both_with_owner(facts, changed_document)
    resolved = resolve_review(
        offered,
        action(
            offered,
            next(
                row
                for row in offered.proposal.changes
                if row.facet == "attachment:payload"
            ),
            domain="attachment",
            choice="both",
            decision_id="mixed:binary",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert resolved.status == "accepted", resolved.code
    plan = resolved.plan
    for note in notes.subjects:
        change = next(row for row in plan.proposal.changes if row.path == note.path)
        resolved = resolve_review(
            plan,
            action(
                plan,
                change,
                choice="incoming",
                decision_id="mixed:" + note.item_id,
                candidate=_incoming_candidate(facts, note, _AFTER[note.path]),
            ),
        )
        assert resolved.status == "accepted", resolved.code
        plan = resolved.plan
    assert plan.ready, (plan.requirements, plan.blockers)
    return (
        vault,
        source,
        plan,
        user_before,
        checkpoint_ref,
        original_document,
        changed_document,
    )


def test_latest_undo_keeps_reviewed_imported_and_later_writing_while_reversing_other_note(
    monkeypatch,
):
    (
        vault,
        source,
        review,
        user_before,
        checkpoint_ref,
        original_document,
        changed_document,
    ) = _mixed_case()
    operations = Operations()

    class StopAfterMove(_NativeExecutor):
        def move(self, stage, target, *, replace):
            super().move(stage, target, replace=replace)
            raise OSError("controlled interruption after actual first apply move")

    stopped = _apply(
        Operations(vault_executor=StopAfterMove()),
        vault,
        source,
        review=review,
        vault_id="vault-one",
        import_id="import-one",
    )
    assert stopped.status == "incomplete" and stopped.publication == "partial", (
        stopped.code
    )
    recovery_writing = b"\nwriting retained by completed apply recovery\n"
    (vault / "Notes/Owner.md").write_bytes(original_document + recovery_writing)
    finish = operations.prepare_recovery(vault, direction="finish")
    assert finish.status == "offered", finish.code
    selection, candidate = _both_with_owner(
        finish.review.producer_facts, changed_document + recovery_writing
    )
    binary_change = next(
        row
        for row in finish.review.proposal.changes
        if row.facet == "attachment:payload"
    )
    selected = resolve_review(
        finish.review,
        action(
            finish.review,
            binary_change,
            domain="attachment",
            choice="both",
            decision_id="mixed:recovered:binary",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert selected.status == "accepted", selected.code
    finish = _with_review(finish, selected.plan)
    for path in _AFTER:
        change = next(row for row in finish.review.proposal.changes if row.path == path)
        subject = next(
            row for row in finish.review.producer_facts.subjects if row.path == path
        )
        selected = resolve_review(
            finish.review,
            action(
                finish.review,
                change,
                choice="incoming",
                decision_id="mixed:recovered:" + subject.item_id,
                candidate=_incoming_candidate(
                    finish.review.facts, subject, _AFTER[path]
                ),
            ),
        )
        assert selected.status == "accepted", selected.code
        finish = _with_review(finish, selected.plan)
    assert finish.review.ready, finish.review.requirements
    applied = operations.execute_recovery(vault, finish)
    assert applied.status == "applied", applied.code
    changed_document += recovery_writing
    created = vault / "Assets/data (incoming-ba7816bf).bin"
    assert created.read_bytes() == b"abc"
    assert (vault / "Notes/Owner.md").read_bytes() == changed_document
    later = b"opening incoming\nlater writing\n"
    (vault / "Notes/Opening.md").write_bytes(later)
    before = {path: (vault / path).read_bytes() for path in _AFTER}
    prepared = operations.prepare_undo(vault)
    assert prepared.status == "offered", prepared.code
    assert prepared.target_receipt_commit == applied.receipt_commit
    owner = next(
        row
        for row in prepared.review.facts.link_context.current_documents
        if row.source_path == "Notes/Owner.md"
    )
    assert owner.content.data == changed_document
    assert (
        owner.occurrences[1].meaning.target_id
        == "resource:payload:incoming:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert not prepared.review.ready
    refused = operations.execute_undo(vault, prepared)
    assert refused.status == "refused"
    assert not refused.authored_files_changed
    assert {path: (vault / path).read_bytes() for path in _AFTER} == before
    for path in (
        "Notes/Opening.md",
        "Notes/Closing.md",
        "Notes/Owner.md",
        "Assets/data.bin",
    ):
        change = next(
            row for row in prepared.review.proposal.changes if row.path == path
        )
        subject = next(
            row
            for row in prepared.review.facts.subjects
            if (row.item_id, row.facet) == (change.item_id, change.facet)
        )
        keep = subject.path == "Notes/Opening.md"
        reverse = subject.operation_reversal is not None
        choice = action(
            prepared.review,
            change,
            domain="reversal" if reverse else "text",
            choice="current" if keep else "reverse" if reverse else "incoming",
            decision_id="undo:mixed:" + subject.item_id + ":" + subject.facet,
            candidate=None
            if keep or reverse
            else _incoming_candidate(
                prepared.review.facts,
                subject,
                original_document
                if subject.path == "Notes/Owner.md"
                else _BEFORE[subject.path],
            ),
        )
        if keep:
            current_action = choice
            prepared = operations.resolve_undo(vault, prepared, choice)
        else:
            transition = resolve_review(prepared.review, choice)
            assert transition.status == "accepted", (path, transition.code)
            prepared = _with_review(prepared, transition.plan)
        assert prepared.status == "offered", (path, subject.facet, prepared.code)
    assert prepared.review.ready, prepared.review.blockers
    effects = select_review_effects(prepared.review)
    assert effects.remove_paths == ("Assets/data (incoming-ba7816bf).bin",)
    evidence = _preserve_candidate_inputs(vault, prepared, current_action)
    cancelled = operations.execute_undo(vault, prepared, cancel=lambda: True)
    assert cancelled.status == "cancelled", cancelled.code
    assert (
        cancelled.publication == "not_started" and not cancelled.authored_files_changed
    )
    assert created.read_bytes() == b"abc"
    assert (vault / "Notes/Opening.md").read_bytes() == later
    retry = operations.prepare_undo(vault, previous=prepared)
    assert retry.status == "offered", retry.code
    assert retry.target_receipt_commit == applied.receipt_commit
    assert retry.checkpoint_commit == cancelled.checkpoint_commit
    assert retry.review.ready, retry.review.requirements
    pending_status = operations.inspect_update_status(vault)
    cancelled_again = operations.execute_undo(vault, retry, cancel=lambda: True)
    assert cancelled_again.status == "cancelled", cancelled_again.code
    assert cancelled_again.checkpoint_commit == retry.checkpoint_commit
    assert not cancelled_again.authored_files_changed
    prepared = operations.prepare_undo(vault, previous=retry)
    assert prepared.status == "offered" and prepared.review.ready, prepared.code
    cleanup = tempfile.TemporaryDirectory.cleanup
    cleanup_failed = False

    def fail_owned_source_cleanup(directory):
        nonlocal cleanup_failed
        cleanup(directory)
        if Path(directory.name).name.startswith("brz2obsidian-recovery-source-"):
            cleanup_failed = True
            raise OSError("controlled owned source cleanup reporting failure")

    with monkeypatch.context() as boundary:
        boundary.setattr(
            tempfile.TemporaryDirectory, "cleanup", fail_owned_source_cleanup
        )
        undone = operations.execute_undo(vault, prepared)
    assert cleanup_failed
    fresh_undone = operations.inspect_update_status(vault)
    assert fresh_undone.status == "undone", fresh_undone.code
    assert (
        pending_status.planned_files,
        pending_status.published_files,
        pending_status.authored_files_changed,
        cancelled_again.generation,
        undone.status,
    ) == (
        applied.planned_files,
        applied.published_files,
        True,
        retry.generation,
        "undone",
    ), (
        pending_status.model_dump_json(),
        cancelled_again.model_dump_json(),
        undone.model_dump_json(),
    )
    assert "Kept reviewed current content at Notes/Opening.md" in undone.message
    assert "source cleanup reported an error" in undone.message
    assert undone.kind == "undo" and undone.direction == "finish"
    assert undone.planned_files == undone.published_files == 3
    assert (vault / "Notes/Opening.md").read_bytes() == later
    assert (vault / "Notes/Closing.md").read_bytes() == b"closing authored\r\n"
    assert (vault / "Unrelated.bin").read_bytes() == b"protected\x00\xff"
    assert (vault / "Assets/data.bin").read_bytes() == b"\x00authored"
    assert not created.exists()
    assert (
        (vault / "Notes/Owner.md").read_bytes()
        == b"[[Assets/data.bin|Keep first]] and [[Assets/data.bin|Redirect second]]"
    )
    again = operations.prepare_undo(vault)
    assert again.status == "already_undone", again.code
    replay = operations.execute_undo(vault, prepared)
    assert replay.status == "refused"
    assert (vault / "Notes/Opening.md").read_bytes() == later
    assert (vault / "Notes/Closing.md").read_bytes() == b"closing authored\r\n"
    allowed = frozenset(
        (
            checkpoint_ref.encode(),
            _operation_ref(checkpoint_ref, applied.operation_id),
            _operation_ref(checkpoint_ref, undone.operation_id),
        )
    )
    _assert_user_state(user_before, user_state(vault), allowed_refs=allowed)
    _preserve_candidate_result(
        evidence, vault, prepared, applied, undone, fresh_undone, user_before, allowed
    )


def test_production_undo_child_stops_partially_and_fresh_review_restores_same_target():
    vault, source, review_path, user_before, checkpoint_ref = _two_note_case()
    operations = Operations()
    applied = _apply(
        operations,
        vault,
        source,
        review=ReviewPlan.model_validate_json(review_path.read_bytes()),
        vault_id="vault-one",
        import_id="import-one",
    )
    assert applied.status == "applied", applied.code
    prepared = _choose_undo(vault, operations.prepare_undo(vault), prefix="undo:child")
    undo_path = vault.parent / "undo-preparation.json"
    undo_path.write_text(prepared.model_dump_json(), encoding="utf-8")
    _child(_UNDO_CHILD, vault, undo_path, expected=81)
    assert (vault / "Notes/Closing.md").read_bytes() == b"closing authored\r\n"
    assert (vault / "Notes/Opening.md").read_bytes() == b"opening incoming\n"
    stopped = _fresh_status(vault)
    assert stopped.kind == "undo" and stopped.status == "incomplete", stopped.code
    assert stopped.publication == "partial" and stopped.published_files == 1
    assert stopped.intent_commit != applied.intent_commit
    unavailable = operations.prepare_undo(vault)
    assert unavailable.status == "recovery_required"
    later = b"opening incoming\nwriting after Undo stopped\n"
    (vault / "Notes/Opening.md").write_bytes(later)
    restore_offer = operations.prepare_recovery(vault, direction="restore")
    assert restore_offer.status == "offered", restore_offer.code
    baselines = {
        row.path: row.baseline.content.data
        for row in restore_offer.review.facts.subjects
    }
    assert baselines == {
        "Notes/Closing.md": b"closing baseline\r\n",
        "Notes/Opening.md": b"opening baseline\r\n",
    }
    restore = _choose_restore(restore_offer, retained_path="Notes/Opening.md")
    restored = operations.execute_recovery(vault, restore)
    assert restored.status == "restored" and restored.kind == "undo", restored.code
    assert restored.direction == "restore"
    assert (vault / "Notes/Closing.md").read_bytes() == b"closing incoming\n"
    assert (vault / "Notes/Opening.md").read_bytes() == later
    fresh = _fresh_status(vault)
    assert fresh.status == "restored" and fresh.direction == "restore"
    repeat = operations.prepare_undo(vault)
    assert repeat.status == "offered", repeat.code
    assert repeat.target_receipt_commit == applied.receipt_commit
    assert repeat.checkpoint_commit != prepared.checkpoint_commit
    assert operations.execute_undo(vault, prepared).status == "refused"
    opposite = operations.prepare_recovery(vault, direction="finish")
    assert opposite.status == "refused"
    second = _choose_undo(
        vault,
        repeat,
        retained_path="Notes/Opening.md",
        prefix="undo:fresh-second",
    )
    undo_path.write_text(second.model_dump_json(), encoding="utf-8")
    _child(_UNDO_CHILD, vault, undo_path, expected=81)
    assert (vault / "Notes/Closing.md").read_bytes() == b"closing authored\r\n"
    assert (vault / "Notes/Opening.md").read_bytes() == later
    second_stop = _fresh_status(vault)
    assert second_stop.kind == "undo" and second_stop.status == "content_complete", (
        second_stop.code
    )
    assert second_stop.receipt_commit is None and second_stop.recovery_required
    finish = operations.prepare_recovery(vault, direction="finish")
    assert finish.status == "offered" and finish.review.ready, finish.code
    finished = operations.execute_recovery(vault, finish)
    assert finished.status == "undone" and finished.direction == "finish", finished.code
    assert finished.planned_files == finished.published_files == 0
    assert not finished.authored_files_changed
    final = _fresh_status(vault)
    assert (
        final.status == "undone"
        and final.kind == "undo"
        and final.direction == "finish"
    )
    assert operations.prepare_undo(vault).status == "already_undone"
    assert (vault / "Notes/Closing.md").read_bytes() == b"closing authored\r\n"
    assert (vault / "Notes/Opening.md").read_bytes() == later
    _assert_user_state(
        user_before,
        user_state(vault),
        allowed_refs=frozenset(
            (
                checkpoint_ref.encode(),
                _operation_ref(checkpoint_ref, applied.operation_id),
                _operation_ref(checkpoint_ref, stopped.operation_id),
                _operation_ref(checkpoint_ref, second_stop.operation_id),
            )
        ),
    )
