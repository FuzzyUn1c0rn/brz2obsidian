import hashlib
import json

import pytest

from brz2obsidian.application.checkpoint_payload_contracts import (
    CheckpointPayloadRequest,
)
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_facts import assemble_facts
from brz2obsidian.core import prepare_review
from tests.application.test_vault_checkpoints import fixture_case, git
from tests.reconciliation.test_resolution import preflight


def _incoming_brain(*, scoped=True):
    prefix = "Imports/Brain B/" if scoped else ""
    path = prefix + "Opening.md"
    record_path = prefix + "migration-record.json"
    record = {
        "schema": "brz2obsidian.migration",
        "schema_version": 9,
        "profile_id": "fixture",
        "profile_version": "1",
        "source_identity": {
            "source_id": "brain-b",
            "module_id": "thebrain-brz",
            "module_version": "9",
            "snapshot_digest": "incoming-b",
            "format_version": "fixture/1",
            "source_sha256": "a" * 64,
        },
        "source_gaps": [],
        "item_targets": [
            {
                "original_identity": "opening",
                "item_key": "opening",
                "original_title": "Opening",
                "relative_path": path,
                "created": True,
            }
        ],
        "asset_targets": [],
    }
    note = b"---\nsource_collection_id: brain-b\nsource_item_id: opening\n---\nNew B text.\n"
    return (
        path,
        record_path,
        {path: note, record_path: json.dumps(record).encode("utf-8")},
    )


def test_first_import_distinguishes_unrelated_and_retained_source_identity():
    path, record_path, incoming = _incoming_brain()
    note = incoming[path]
    record = json.loads(incoming[record_path])
    record["original_excerpt"] = "[[Literal source evidence]]"
    incoming[record_path] = json.dumps(record).encode()

    def first_import(current):
        return assemble_facts(
            None,
            incoming,
            current,
            proposal_id="first-b",
            generation=1,
            record_path=record_path,
        )

    other = note.replace(b"brain-b", b"brain-a").replace(b"New B", b"Existing A")
    facts = first_import({"Opening.md": other})
    assert facts.format_operation.kind == "collection_import"
    assert facts.format_operation.established_baseline is None
    assert facts.format_operation.baseline_source_version is None
    planned = prepare_review(facts, preflight=preflight())
    opening = next(row for row in planned.proposal.changes if row.item_id == "opening")
    assert opening.path == path
    assert opening.disposition == "compatible"
    assert opening.result.data == note
    record_document = next(
        document
        for document in facts.link_context.incoming_documents
        if document.source_path == record_path
    )
    assert record_document.status == "supported"
    assert record_document.occurrences == ()
    assert planned.ready

    retained = note.replace(b"New B text.", b"Later authored text.")
    with pytest.raises(ValueError, match="^retained_source_identity_conflict$"):
        first_import({"Moved/Opening.md": retained})


def test_first_import_review_inspection_and_refresh_reobserve_current_inputs():
    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    path, record_path, incoming = _incoming_brain()
    for relative, raw in incoming.items():
        (source / relative).parent.mkdir(parents=True, exist_ok=True)
        (source / relative).write_bytes(raw)
    manual = vault / "Manual.md"
    manual.write_bytes(b"Original writing.\n")
    operations = Operations()
    offered = operations.prepare_collection_import(
        vault, source, record_path=record_path
    )
    assert offered.preparation is not None, offered.code
    assert offered.ready, offered.preparation.review.blockers
    prepared = offered.preparation
    assert prepared.locator is None

    def inspect(value):
        return operations.inspect_update_review(
            value,
            proposal_id=offered.operation_id,
            generation=value.review.proposal.generation,
        )

    page = inspect(prepared)
    assert page.status == "available", page.code
    refreshed = operations.refresh_update(prepared)
    assert refreshed.preparation is not None, refreshed.code
    assert refreshed.generation == offered.generation

    manual.write_bytes(b"Later writing.\r\n")
    assert inspect(prepared).status == "refused"
    changed = operations.refresh_update(prepared)
    assert changed.generation == offered.generation + 1, changed.code
    assert inspect(changed.preparation).status == "available"

    (source / path).write_bytes(incoming[path] + b"Changed source.\n")
    assert inspect(changed.preparation).code == "source_payload_changed"
    assert (
        operations.refresh_update(changed.preparation).code == "source_payload_changed"
    )
    assert operations.read_checkpoint(vault).status == "absent"


@pytest.mark.parametrize("scoped", [True, False], ids=["nested", "root"])
def test_scoped_update_binds_incoming_bytes_to_the_moved_note(scoped):
    path, record_path, original = _incoming_brain(scoped=scoped)
    record = json.loads(original[record_path])
    record["source_identity"]["snapshot_digest"] = "next-b"
    updated = original | {
        path: original[path].replace(b"New B text.", b"Latest B text."),
        record_path: json.dumps(record).encode(),
    }
    moved = "Moved/Opening.md"
    current = {moved: original[path], record_path: original[record_path]}
    facts = assemble_facts(
        original,
        updated,
        current,
        record_path=record_path,
        proposal_id="update-b",
        generation=1,
    )
    review = prepare_review(facts, preflight=preflight())
    assert review.ready, review.blockers
    from brz2obsidian.core import select_review_effects

    selected = select_review_effects(review)
    assert {row.path: row.content.data for row in selected.files} == {
        moved: updated[path],
        record_path: updated[record_path],
    }


@pytest.mark.parametrize("scoped", [True, False], ids=["nested", "root"])
def test_scoped_reversal_reads_generated_predecessor_by_moved_note_identity(
    monkeypatch, scoped
):
    from types import SimpleNamespace

    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import review_owned_outputs
    from brz2obsidian.publication import vault_recovery

    path, record_path, original = _incoming_brain(scoped=scoped)
    moved = "Moved/Opening.md"
    authored = original[path]
    produced = original[path].replace(b"New B text.", b"Applied update.")
    next_record = json.loads(original[record_path])
    next_record["source_identity"]["snapshot_digest"] = "new-b"
    updated = original | {path: produced, record_path: json.dumps(next_record).encode()}
    origin = prepare_review(
        assemble_facts(
            original,
            updated,
            {moved: authored, record_path: original[record_path]},
            record_path=record_path,
            proposal_id="selected-update",
            generation=1,
        ),
        preflight=preflight(),
    )
    assert origin.ready, origin.blockers
    selected_change = next(
        change for change in origin.proposal.changes if change.path == moved
    )
    queries = ((selected_change.change_id, None),)
    owned_outputs = review_owned_outputs(origin, queries)
    facts = assemble_facts(
        original,
        updated,
        {moved: produced, record_path: original[record_path]},
        record_path=record_path,
        proposal_id="reverse-b",
        generation=1,
    )
    owner = next(row for row in facts.identity_inventory if row.current.path == moved)
    generated = SimpleNamespace(path=path, content=ExactContent(data=original[path]))
    mapping = SimpleNamespace(
        path=record_path, content=ExactContent(data=original[record_path])
    )
    physical_preimage = SimpleNamespace(path=moved, content=ExactContent(data=authored))
    selected = SimpleNamespace(path=moved, content=ExactContent(data=produced))
    predecessor = SimpleNamespace(
        identity=facts.incoming_identity,
        collection_record_path=record_path if scoped else None,
        collection_baseline_commit=None if scoped else "a" * 40,
        source=(mapping, generated),
    )
    produced_source = SimpleNamespace(
        previous="retained",
        identity=facts.incoming_identity,
        collection_record_path=record_path if scoped else None,
        collection_baseline_commit=None,
        source=tuple(
            SimpleNamespace(path=relative, content=ExactContent(data=raw))
            for relative, raw in updated.items()
        ),
    )
    evidence = SimpleNamespace(
        git=None,
        intent=SimpleNamespace(
            affected_paths=(moved,),
            operation_id="a" * 32,
            generation=9,
            association_id="b" * 64,
            kind="apply",
        ),
        origin_commit="c" * 40,
        source_prepared=produced_source,
        retained=SimpleNamespace(owned={"retained": (predecessor, None)}),
        original=origin,
        before={moved: physical_preimage},
        produced={moved: selected},
    )
    monkeypatch.setattr(
        vault_recovery,
        "_owned_content",
        lambda git, row, **kwargs: None if row is None else row.content,
    )

    def reversed_note():
        subjects, baselines = [], []
        vault_recovery._restore_associated_documents(
            evidence,
            owned_outputs,
            facts,
            {},
            {moved: owner.current},
            subjects,
            baselines,
            owned_groups={},
            _owner=None,
        )
        return subjects[0], baselines[0]

    subject, baseline = reversed_note()
    assert (subject.path, subject.baseline.content.data, subject.incoming.data) == (
        moved,
        produced,
        authored,
    )
    assert (baseline.item_id, baseline.content.data) == ("opening", produced)
    proof = subject.operation_reversal
    assert proof is not None
    assert [
        (row.path, row.produced.data, row.target.data) for row in proof.outputs
    ] == [
        (moved, produced, authored),
    ]

    duplicate = json.loads(original[record_path])
    duplicate["item_targets"].append(duplicate["item_targets"][0])
    mapping.content = ExactContent(data=json.dumps(duplicate).encode())
    with pytest.raises(OSError, match="Associated recovery document source"):
        reversed_note()


def test_finish_rebinds_already_published_imported_undo_to_active_intent(monkeypatch):
    from types import SimpleNamespace

    from brz2obsidian.application.update_lifecycle import text_choice_action
    from brz2obsidian.content_values import content_sha, content_size
    from brz2obsidian.contracts import OperationReversalOutput, OperationReversalTarget
    from brz2obsidian.core import resolve_review, select_review_effects
    from brz2obsidian.publication import vault_recovery
    from tests.reconciliation.test_resolution import action

    path, record_path, previous = _incoming_brain(scoped=False)
    moved = "Moved/Opening.md"
    rendered = json.loads(previous[record_path])
    rendered["source_identity"]["snapshot_digest"] = "reviewed-update"
    updated = previous | {
        path: previous[path].replace(b"New B text.", b"Updated note."),
        record_path: json.dumps(rendered).encode(),
    }

    def facts(current_note, generation):
        return assemble_facts(
            updated,
            previous,
            {moved: current_note, record_path: previous[record_path]},
            record_path=record_path,
            proposal_id="undo-collection-update",
            generation=generation,
        )

    before = facts(updated[path], 1)
    subject = next(row for row in before.subjects if row.item_id == "opening")
    reference = next(
        row
        for row in before.link_context.current_targets
        if row.canonical_path == moved
    )
    proof = OperationReversalTarget(
        schema_id="brz2obsidian.operation-reversal-target",
        schema_version=1,
        operation_id="a" * 32,
        operation_kind="apply",
        direction="restore",
        operation_generation=4,
        history_fingerprint="original-apply",
        origin_change_id="prior-apply-note",
        owned_targets=(reference,),
        outputs=(
            OperationReversalOutput(
                path=moved,
                target_id=reference.target_id,
                produced_existence="present",
                produced=subject.current.content,
                current=subject.current,
                target_existence="present",
                target=subject.incoming,
            ),
        ),
    )
    undo_subject = subject.model_copy(
        update={"path": moved, "structure": None, "operation_reversal": proof}
    )
    undo = prepare_review(
        before.model_copy(update={"subjects": (undo_subject,)}), preflight=preflight()
    )
    change = next(
        row for row in undo.proposal.changes if row.item_id == subject.item_id
    )
    decision = text_choice_action(
        undo, action(undo, change, domain="reversal", choice="reverse")
    )
    chosen = resolve_review(undo, decision)
    assert chosen.status == "accepted", chosen.code
    undo = chosen.plan
    assert undo.ready, undo.blockers

    after = facts(previous[path], undo.proposal.generation + 1)
    observed = next(
        row.current for row in after.identity_inventory if row.current.path == moved
    )
    fresh = after.model_copy(
        update={"subjects": (undo_subject.model_copy(update={"current": observed}),)}
    )
    retained = SimpleNamespace(
        owned={
            "prepared": (
                None,
                SimpleNamespace(historical_effects=select_review_effects(undo)),
            )
        }
    )

    def exact(value):
        return SimpleNamespace(
            path=moved,
            size=content_size(value),
            sha256=content_sha(value),
            content=value,
        )

    intent = SimpleNamespace(
        kind="undo",
        operation_id="b" * 32,
        generation=7,
        association_id="c" * 64,
        undo_of_receipt_commit="d" * 40,
        prepared_commit="prepared",
        affected_paths=(moved,),
        before=(exact(undo_subject.current.content),),
        proposed=(exact(observed.content),),
    )
    monkeypatch.setattr(
        vault_recovery,
        "_review_observation",
        lambda *a, **kw: (
            undo,
            intent,
            "e" * 40,
            None,
            fresh,
            undo.preflight,
            {moved: observed},
            retained,
        ),
    )
    monkeypatch.setattr(
        vault_recovery, "_owned_content", lambda git, row, **kw: row.content
    )
    result = vault_recovery._finish_review(None, None)
    assert result.ready, (result.blockers, result.requirements)
    active = result.facts.subjects[0].operation_reversal
    assert (active.operation_id, active.direction) == (intent.operation_id, "finish")
    assert (
        active.outputs[0].current.content
        == active.outputs[0].target
        == observed.content
    )

    later = previous[path] + b"Authored after the interruption.\r\n"
    after = facts(later, undo.proposal.generation + 1)
    observed = next(
        row.current for row in after.identity_inventory if row.current.path == moved
    )
    fresh = after.model_copy(
        update={"subjects": (undo_subject.model_copy(update={"current": observed}),)}
    )
    result = vault_recovery._finish_review(None, None)
    assert result.blockers == () and len(result.requirements) == 1
    requirement = result.requirements[0]
    assert requirement.domain == "reversal" and "current" in requirement.choices
    change = next(row for row in result.proposal.changes if row.path == moved)
    retained_edit = resolve_review(
        result,
        action(
            result,
            change,
            domain="reversal",
            choice="current",
            decision_id="recovery:preserve-later",
        ),
    )
    assert retained_edit.status == "accepted", retained_edit.code
    assert retained_edit.plan.ready, retained_edit.plan.blockers
    selection = select_review_effects(retained_edit.plan)
    assert not selection.remove_paths
    assert all(
        row.content.data == later for row in selection.files if row.path == moved
    )

    intent.proposed = (exact(undo_subject.current.content),)
    with pytest.raises(OSError, match="exact selected recovery versions"):
        vault_recovery._finish_review(None, None)


def test_undo_lease_uses_reviewed_collection_lineage_even_at_vault_root(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace

    from brz2obsidian.publication import collection_publication, vault_apply

    held = SimpleNamespace(
        boundary="prepared",
        collection_record_path=None,
        collection_preparation_owner="a" * 32,
    )
    origin = SimpleNamespace(operation_id="a" * 32, prepared_commit="b" * 40)
    target = SimpleNamespace(
        receipt_commit="c" * 40,
        intent=origin,
        observation=SimpleNamespace(owned={origin.prepared_commit: (held, None)}),
    )
    checkpoint = SimpleNamespace(manifest=SimpleNamespace(), locator=object())
    acquisitions = []
    monkeypatch.setattr(
        vault_apply, "_acquire", lambda *args: acquisitions.append(args)
    )
    monkeypatch.setattr(
        collection_publication,
        "acquire_collection_apply",
        lambda *args, **kwargs: acquisitions.append((args, kwargs)),
    )
    root = Path("vault").absolute()
    assert vault_apply._acquire_reviewed_apply(root, "d" * 32, checkpoint, target)
    assert acquisitions.pop() == (
        (root, "d" * 32, checkpoint.locator),
        {"undo_receipt": target.receipt_commit},
    )
    held.collection_preparation_owner = None
    assert not vault_apply._acquire_reviewed_apply(root, "d" * 32, checkpoint, target)
    assert acquisitions == [(root, "d" * 32)]


def test_root_undo_locator_proof_requires_exact_owned_receipt(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace

    from brz2obsidian.publication import (
        collection_result_locator,
        vault_apply,
        vault_history,
    )

    association = "a" * 64
    apply_operation = "b" * 32
    undo_operation = "c" * 32
    apply_prepared = "d" * 40
    undo_prepared = "e" * 40
    apply_receipt = "f" * 40
    apply_intent = SimpleNamespace(
        kind="apply",
        association_id=association,
        operation_id=apply_operation,
        prepared_commit=apply_prepared,
    )
    undo_intent = SimpleNamespace(
        kind="undo",
        association_id=association,
        operation_id=undo_operation,
        prepared_commit=undo_prepared,
        undo_of_receipt_commit=apply_receipt,
    )
    marker = SimpleNamespace(
        operation_id=undo_operation,
        collection_saved_checkpoint=undo_prepared,
        collection_undo_receipt=apply_receipt,
    )
    manifests = {
        apply_prepared: SimpleNamespace(
            boundary="prepared",
            collection_record_path=None,
            collection_preparation_owner=apply_operation,
        ),
        undo_prepared: SimpleNamespace(
            previous="0" * 40,
            undo_of_receipt_commit=apply_receipt,
            collection_record_path=None,
            collection_preparation_owner=None,
        ),
    }
    monkeypatch.setattr(
        collection_result_locator, "read_native_marker", lambda root: marker
    )
    monkeypatch.setattr(
        vault_apply,
        "_operation_graph",
        lambda git, commit: SimpleNamespace(
            receipt=SimpleNamespace(status="applied"),
            authorities=((None, apply_intent),),
        ),
    )
    monkeypatch.setattr(
        vault_history,
        "_checkpoint_graph",
        lambda git, commit, *args: (None, None, manifests[commit], None),
    )
    graph = SimpleNamespace(intent=undo_intent, authorities=((None, undo_intent),))
    git = SimpleNamespace(call=lambda *args: apply_receipt.encode())

    def qualified():
        return collection_result_locator._scoped_result_owner(
            Path("vault").absolute(), git, graph
        )

    assert qualified()
    marker.collection_saved_checkpoint = "1" * 40
    assert not qualified()
    marker.collection_saved_checkpoint = undo_prepared
    marker.collection_undo_receipt = "2" * 40
    assert not qualified()


def test_scoped_terminal_receipt_offers_cleanup_after_later_edit(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from brz2obsidian.publication import (
        collection_publication,
        vault_apply,
        vault_history,
    )

    operation = "a" * 32
    saved = "b" * 40
    prepared = "c" * 40
    commit = "d" * 40
    intent = SimpleNamespace(
        operation_id=operation,
        kind="apply",
        direction="finish",
        generation=4,
        affected_paths=("Brain B/Opening.md",),
        prepared_commit=prepared,
    )
    receipt = SimpleNamespace(
        status="applied",
        published_paths=intent.affected_paths,
        intent_commit="e" * 40,
        result_commit="f" * 40,
    )
    owner = SimpleNamespace(
        operation_id=operation,
        collection_saved_checkpoint=saved,
        collection_undo_receipt=None,
    )
    manifest = SimpleNamespace(
        boundary="prepared",
        previous=saved,
        collection_preparation_owner=operation,
        collection_record_path="Brain B/migration-record.json",
    )
    (tmp_path / ".git/brz2obsidian").mkdir(parents=True)
    monkeypatch.setattr(vault_apply, "_terminal_result_in_history", lambda *args: True)
    monkeypatch.setattr(vault_apply, "_terminal_files_match", lambda *args: False)
    monkeypatch.setattr(
        collection_publication, "read_native_marker", lambda root: owner
    )
    monkeypatch.setattr(
        vault_apply,
        "_operation_graph",
        lambda git, commit: SimpleNamespace(
            authorities=((None, intent),), intent=intent
        ),
    )
    monkeypatch.setattr(
        vault_history, "_checkpoint_graph", lambda *args: (None, None, manifest, None)
    )

    def status():
        return vault_apply._terminal_operation_status(
            tmp_path,
            object(),
            SimpleNamespace(status="valid"),
            intent,
            receipt,
            commit,
            0,
            None,
        )

    assert status().code == "terminal_cleanup_required"
    owner.collection_saved_checkpoint = "0" * 40
    assert status().code == "terminal_requires_recovery"
    monkeypatch.setattr(vault_apply, "_terminal_files_match", lambda *args: True)
    assert status().code == "terminal_requires_recovery"
    owner.collection_saved_checkpoint = None
    assert status().code == "terminal_requires_recovery"
    manifest.collection_preparation_owner = None
    manifest.collection_record_path = None
    assert status().code == "terminal_cleanup_required"


def test_active_recovery_rejects_wrong_or_incomplete_scoped_marker(monkeypatch):
    from types import SimpleNamespace

    from brz2obsidian.application.vault_update_contracts import VaultOperationLock
    from brz2obsidian.publication import (
        collection_publication,
        vault_apply,
        vault_recovery,
    )
    from brz2obsidian.publication.vault_native import verify_directory

    vault, _ = fixture_case()
    git(vault, "init", "-q")
    operation = "a" * 32
    commit = "b" * 40
    saved = "c" * 40
    prepared = SimpleNamespace(
        boundary="prepared",
        previous=saved,
        collection_record_path=None,
        collection_preparation_owner=operation,
    )
    origin = SimpleNamespace(
        kind="apply", operation_id=operation, prepared_commit=commit
    )
    graph = SimpleNamespace(receipt=None, authorities=((None, origin),), intent=origin)
    authority = SimpleNamespace(graph=graph, owned={commit: (prepared, None)})
    observed = SimpleNamespace(
        status="incomplete",
        recovery_required=True,
        intent_commit=commit,
        operation_id=operation,
        generation=4,
    )
    marker = vault / ".git/brz2obsidian"
    marker.mkdir()
    (marker / "held").write_bytes(b"1")

    def write_owner(checkpoint, undo_receipt=None):
        owner = VaultOperationLock(
            schema_id="brz2obsidian.vault-operation-lock",
            schema_version=1,
            operation_id=operation,
            vault_anchor=verify_directory(vault),
            git_anchor=verify_directory(vault / ".git"),
            collection_saved_checkpoint=checkpoint,
            collection_undo_receipt=undo_receipt,
        )
        (marker / "owner.json").write_text(owner.model_dump_json(), encoding="utf-8")

    offered = object()
    monkeypatch.setattr(
        vault_recovery, "_build_recovery_review", lambda *a, **kw: offered
    )
    write_owner(saved)
    assert (
        vault_recovery._prepare_recovery_observed(vault, observed, authority) is offered
    )

    for wrong in (None, "d" * 40):
        write_owner(wrong)
        refused = vault_recovery._prepare_recovery_observed(vault, observed, authority)
        assert (refused.status, refused.code) == (
            "unavailable",
            "operation_marker_invalid",
        )
    write_owner(saved, "e" * 40)
    refused = vault_recovery._prepare_recovery_observed(vault, observed, authority)
    assert refused.code == "operation_marker_invalid"

    prepared.collection_preparation_owner = None
    write_owner(None)
    assert (
        vault_recovery._prepare_recovery_observed(vault, observed, authority) is offered
    )

    origin.kind = "undo"
    origin.undo_of_receipt_commit = "f" * 40
    origin.association_id = "0" * 64
    prepared.undo_of_receipt_commit = origin.undo_of_receipt_commit
    monkeypatch.setattr(
        collection_publication,
        "scoped_undo_receipt",
        lambda git, receipt, association: receipt == origin.undo_of_receipt_commit,
    )
    write_owner(saved, origin.undo_of_receipt_commit)
    assert (
        vault_recovery._prepare_recovery_observed(vault, observed, authority) is offered
    )
    vault_apply._adopt(vault, operation)
    publication = SimpleNamespace(
        root=vault, saved=SimpleNamespace(operation_id=operation), authority=authority
    )
    state = SimpleNamespace(acquired=True)
    assert vault_recovery._recheck_held_recovery_marker(publication, state)
    write_owner(saved, "e" * 40)
    assert not vault_recovery._recheck_held_recovery_marker(publication, state)
    assert not state.acquired
    assert (marker / "held").read_bytes() == b"1"
    refused = vault_recovery._prepare_recovery_observed(vault, observed, authority)
    assert refused.code == "operation_marker_invalid"


def test_interrupted_scoped_apply_start_releases_marker_without_checkpoint_write():
    from brz2obsidian.publication import vault_apply

    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    path, record_path, incoming = _incoming_brain()
    for relative, raw in incoming.items():
        (source / relative).parent.mkdir(parents=True, exist_ok=True)
        (source / relative).write_bytes(raw)
    operations = Operations()
    offered = operations.prepare_collection_import(
        vault, source, record_path=record_path
    )
    saved = operations.save_update(offered.preparation)
    assert saved.code == "saved", saved
    operation_id = "d" * 32
    vault_apply._acquire_reviewed_apply(
        vault, operation_id, operations.read_checkpoint(vault), None
    )
    fresh = Operations()
    live_offer = fresh.prepare_recovery(vault)
    busy = fresh.execute_recovery(vault, live_offer)
    assert busy.recovery_required and vault_apply.owns_operation(vault, operation_id)
    vault_apply._park(vault, operation_id)
    assert fresh.inspect_history(vault).admission.status == "recovery_first"
    recovery = fresh.prepare_recovery(vault)
    assert (recovery.status, recovery.code) == ("cleanup", "scoped_apply_start_pending")
    assert recovery.unpublished_checkpoint == saved.checkpoint_commit
    recovered = fresh.execute_recovery(vault, recovery)
    assert recovered.code == "scoped_apply_start_released", recovered
    assert not recovered.authored_files_changed
    assert not (vault / ".git/brz2obsidian").exists()
    assert fresh.read_checkpoint(vault).locator.commit == saved.checkpoint_commit
    assert fresh.resume_update(vault).code == "resumed"
    assert not (vault / path).exists()


@pytest.mark.parametrize(
    "boundary",
    ["prepared_locator", "saved_locator", "lease_release", "inside_retirement"],
)
def test_unpublished_collection_recovery_can_itself_be_interrupted(
    monkeypatch, boundary
):
    from brz2obsidian.publication import unpublished_collection, vault_apply

    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    path, record_path, incoming = _incoming_brain()
    for relative, raw in incoming.items():
        (source / relative).parent.mkdir(parents=True, exist_ok=True)
        (source / relative).write_bytes(raw)
    operations = Operations()
    prepared = operations.prepare_collection_import(
        vault, source, record_path=record_path
    )
    saved = operations.save_update(prepared.preparation)
    assert saved.code == "saved", saved
    locator_file = vault / ".brz2obsidian/locator.json"
    saved_locator = locator_file.read_bytes()
    association = saved.checkpoint.association
    plan = saved.preparation.review
    operation_id = "b" * 32
    vault_apply._acquire(vault, operation_id)
    try:
        snapshot = operations.capture_checkpoint(
            vault,
            source,
            vault_id=association.vault_id,
            import_id=association.import_id,
            identity=plan.facts.incoming_identity,
            admission=operations.inspect_history(
                vault, active_operation=operation_id
            ).admission,
            review=plan,
            boundary="prepared",
            proposed=source,
            active_operation=operation_id,
            source_binding=saved.preparation.source_binding,
            observed_source=saved.preparation.observed_source,
        )
        assert snapshot.status == "captured", snapshot.code
    finally:
        if boundary == "saved_locator":
            vault_apply._park(vault, operation_id)
        else:
            vault_apply._release(vault, operation_id)
    if boundary == "saved_locator":
        locator_file.write_bytes(saved_locator)
    offered = Operations().prepare_recovery(vault, direction="restore")
    assert (offered.status, offered.code) == (
        "cleanup",
        "unpublished_collection_prepared",
    )
    assert offered.operation_id == operation_id
    assert offered.unpublished_checkpoint == snapshot.commit
    assert offered.intent_commit is None
    assert Operations().inspect_history(vault).admission.status == "recovery_first"
    assert not (vault / path).exists()
    if boundary == "inside_retirement":
        original_unlink = type(vault).unlink
        injected = []

        def stop_after_owner_removal(marker_file, *args, **kwargs):
            original_unlink(marker_file, *args, **kwargs)
            if marker_file.name == "owner.json" and marker_file.is_relative_to(
                vault / ".git"
            ):
                injected.append(marker_file)
                raise OSError("Injected interruption during marker deletion")

        with monkeypatch.context() as injection:
            injection.setattr(type(vault), "unlink", stop_after_owner_removal)
            Operations().execute_recovery(vault, offered)
        assert injected
        resumed = Operations().resume_update(vault)
        assert resumed.code == "resumed", resumed
        assert resumed.operation_id == plan.proposal.proposal_id
        assert not (vault / ".git/brz2obsidian").exists()
        assert not (vault / path).exists()
        return

    with monkeypatch.context() as injection:
        if boundary == "lease_release":

            def stop_before_release(root, operation):
                raise OSError("Injected interruption after locator replacement")

            injection.setattr(
                unpublished_collection, "_retire_collection_marker", stop_before_release
            )
        else:

            def stop_after_ref(root, native_git, association, manifest, writes):
                native_git.call(
                    "update-ref", writes.ref, writes.commit, manifest.previous
                )
                raise OSError("Injected interruption before locator replacement")

            injection.setattr(
                unpublished_collection, "_publish_locator", stop_after_ref
            )
        stopped = Operations().execute_recovery(vault, offered)
    assert stopped.recovery_required and not stopped.authored_files_changed
    retained = git(vault, "rev-parse", association.ref).decode().strip()
    assert retained != snapshot.commit
    owner_file = vault / ".git/brz2obsidian/owner.json"
    original_owner = owner_file.read_bytes()
    wrong_owner = json.loads(original_owner)
    wrong_owner["operation_id"] = "c" * 32
    owner_file.write_bytes(json.dumps(wrong_owner).encode())
    try:
        bad = Operations().prepare_recovery(vault, direction="restore")
        assert bad.status != "cleanup"
    finally:
        owner_file.write_bytes(original_owner)
    old_locator = locator_file.read_bytes()
    invalid_locator = json.loads(old_locator)
    invalid_locator["generation"] += 7
    locator_file.write_bytes(json.dumps(invalid_locator).encode())
    try:
        assert (
            Operations().prepare_recovery(vault, direction="restore").status
            != "cleanup"
        )
        assert git(vault, "rev-parse", association.ref).decode().strip() == retained
    finally:
        locator_file.write_bytes(old_locator)
    restarted = Operations().prepare_recovery(vault, direction="restore")
    assert restarted.status == "cleanup", restarted
    assert restarted.operation_id == operation_id
    assert restarted.unpublished_checkpoint == retained
    restored = Operations().execute_recovery(vault, restarted)
    assert restored.code == "saved_collection_review_restored", restored
    assert not restored.authored_files_changed
    assert restored.checkpoint_commit == retained
    assert not owner_file.exists()
    resumed = Operations().resume_update(vault)
    assert resumed.code == "resumed", resumed
    assert resumed.operation_id == plan.proposal.proposal_id
    assert not (vault / record_path).exists()
    discarded = Operations().discard_saved_review(vault, expected_commit=retained)
    assert discarded.code == "saved_review_discarded", discarded
    assert Operations().read_checkpoint(vault).locator.commit == discarded.commit
    assert Operations().load_update(vault).code == "saved_update_unavailable"
    assert (
        Operations()
        .prepare_collection_import(vault, source, record_path=record_path)
        .ready
    )


@pytest.mark.parametrize("advanced", [False, True], ids=["before_ref", "after_ref"])
def test_first_collection_saved_checkpoint_can_recover_without_old_locator(
    monkeypatch, advanced
):
    from brz2obsidian.publication import collection_publication, vault_history

    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    path, record_path, incoming = _incoming_brain()
    for relative, raw in incoming.items():
        (source / relative).parent.mkdir(parents=True, exist_ok=True)
        (source / relative).write_bytes(raw)
    established = vault / "Authored.md"
    established.write_bytes(b"Independent note.\r\n")
    operations = Operations()
    review = operations.prepare_collection_import(
        vault, source, record_path=record_path
    )
    assert review.ready, review

    def interrupted(root, native_git, association, manifest, writes):
        assert manifest.boundary == "local"
        assert manifest.previous is None
        if advanced:
            native_git.call("update-ref", writes.ref, writes.commit, "0" * 40)
        raise OSError("Injected interruption during scoped LOCAL publication")

    with monkeypatch.context() as injection:
        injection.setattr(vault_history, "_publish_locator", interrupted)
        failed = operations.save_update(review.preparation)
    assert failed.code == "capture_unavailable", failed
    assert not (vault / ".brz2obsidian/locator.json").exists()
    fresh = Operations()
    assert fresh.inspect_history(vault).admission.status == "recovery_first"
    recovery = fresh.prepare_recovery(vault)
    assert (
        recovery.status,
        recovery.code,
    ) == ("cleanup", "collection_local_locator_pending"), recovery
    assert recovery.unpublished_checkpoint is not None
    assert (
        fresh.prepare_collection_import(vault, source, record_path=record_path).code
        == "recovery_first"
    )
    journal_path = vault / ".git" / collection_publication._JOURNAL
    journal_bytes = journal_path.read_bytes()
    wrong_anchor = json.loads(journal_bytes)
    wrong_anchor["locator"]["association"]["vault_anchor"] += "-wrong"
    journal_path.write_bytes(json.dumps(wrong_anchor).encode())
    try:
        invalid = fresh.prepare_recovery(vault)
        assert (invalid.status, invalid.code) == (
            "unavailable",
            "collection_local_publication_invalid",
        )
    finally:
        journal_path.write_bytes(journal_bytes)
    with collection_publication.collection_publication_guard(vault):
        busy = fresh.execute_recovery(vault, recovery)
        assert busy.recovery_required and journal_path.read_bytes() == journal_bytes
    recovered = fresh.execute_recovery(vault, recovery)
    assert recovered.code == (
        "collection_local_locator_resealed"
        if advanced
        else "collection_local_publication_abandoned"
    ), recovered
    assert not recovered.authored_files_changed
    assert not (vault / path).exists()
    assert established.read_bytes() == b"Independent note.\r\n"
    if advanced:
        assert (
            fresh.read_checkpoint(vault).locator.commit
            == recovery.unpublished_checkpoint
        )
        assert fresh.resume_update(vault).code == "resumed"

        def interrupt_discard(root, native_git, association, manifest, writes):
            assert manifest.discarded_review == recovery.unpublished_checkpoint
            native_git.call("update-ref", writes.ref, writes.commit, manifest.previous)
            raise OSError("Injected interruption during scoped discard")

        with monkeypatch.context() as injection:
            injection.setattr(vault_history, "_publish_locator", interrupt_discard)
            discarded = fresh.discard_saved_review(
                vault, expected_commit=recovery.unpublished_checkpoint
            )
        assert discarded.code == "capture_unavailable", discarded
        discard_recovery = fresh.prepare_recovery(vault)
        assert discard_recovery.code == "collection_local_locator_pending"
        assert (
            fresh.execute_recovery(vault, discard_recovery).code
            == "collection_local_locator_resealed"
        )
        assert (
            fresh.read_checkpoint(vault).locator.commit
            == discard_recovery.unpublished_checkpoint
        )
        assert fresh.load_update(vault).code == "saved_update_unavailable"
    else:
        assert fresh.read_checkpoint(vault).status == "absent"


def test_saved_unrelated_review_keeps_the_established_source_available():
    vault, source_a = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    authored = b"Existing A.\r\n"
    original = b"Original A.\n"
    (vault / "Opening.md").write_bytes(authored)
    (source_a / "Opening.md").write_bytes(original)
    path_b, record_path, incoming = _incoming_brain()
    record_a = json.loads(incoming[record_path])
    record_a["source_identity"]["source_id"] = "brain-a"
    record_a["source_identity"]["snapshot_digest"] = "original-a"
    record_a["item_targets"][0]["relative_path"] = "Opening.md"
    asset_a = "Assets/shared.bin"
    asset_b = "Imports/Brain B/Assets/shared.bin"
    record_a["asset_targets"] = [{"asset_id": "shared", "relative_path": asset_a}]
    (source_a / "migration-record.json").write_bytes(json.dumps(record_a).encode())
    (vault / "migration-record.json").write_bytes(json.dumps(record_a).encode())
    for directory in (vault, source_a):
        (directory / asset_a).parent.mkdir()
        (directory / asset_a).write_bytes(b"Historical A resource\x00")
    record_b = json.loads(incoming[record_path])
    record_b["asset_targets"] = [{"asset_id": "shared", "relative_path": asset_b}]
    incoming[record_path] = json.dumps(record_b).encode()
    incoming[asset_b] = b"Distinct B resource\xff"
    operations = Operations()
    first = operations.capture_checkpoint(
        vault,
        source_a,
        vault_id="vault",
        import_id="stage-one",
        identity={
            "collection_id": "brain-a",
            "module_id": "thebrain-brz",
            "module_version": "9",
            "profile_id": "fixture",
            "profile_version": "1",
            "output_format": 9,
            "settings_digest": hashlib.sha256(b"{}").hexdigest(),
        },
        admission=operations.inspect_history(vault).admission,
    )
    assert first.status == "captured", first.code
    source_b = source_a.parent / "brain-b"
    for path, raw in incoming.items():
        (source_b / path).parent.mkdir(parents=True, exist_ok=True)
        (source_b / path).write_bytes(raw)
    offered = operations.prepare_collection_import(
        vault, source_b, record_path=record_path
    )
    assert offered.ready, offered
    saved = operations.save_update(offered.preparation.model_dump())
    assert saved.code == "saved", saved
    reopened = operations.read_checkpoint(vault)
    assert reopened.status == "valid"
    assert reopened.review.saved.plan.proposal.proposal_id == offered.operation_id
    assert reopened.manifest.source == ()
    assert reopened.locator.association == first.locator.association
    assert (
        operations.inspect_history(vault).admission.preflight
        == saved.preparation.review.preflight
    )
    source = operations.read_checkpoint_payload(
        vault,
        locator=reopened.locator,
        collection=("thebrain-brz", "brain-a"),
        requests=(CheckpointPayloadRequest(path="Opening.md", limit=64),),
        byte_limit=64,
    )
    assert source.status == "available", source.code
    assert source.chunks[0].data == original
    absent = operations.read_checkpoint_payload(
        vault,
        locator=reopened.locator,
        collection=("thebrain-brz", "brain-b"),
        requests=(CheckpointPayloadRequest(path="Opening.md", limit=64),),
        byte_limit=64,
    )
    assert absent.code == "collection_not_active", absent
    with operations.inspect_update_inputs(vault) as observed:
        (owner,) = observed.read_attachment_ownership(
            locator=reopened.locator, paths=(asset_a,)
        )
    assert owner.checkpoint_commit == first.commit
    assert owner.identity.collection_id == "brain-a"
    assert owner.source_path == asset_a
    resumed = Operations().resume_update(vault)
    assert resumed.code == "resumed", resumed
    assert resumed.operation_id == offered.operation_id
    assert (vault / "Opening.md").read_bytes() == authored
    assert not (vault / record_path).exists()
    discarded = operations.discard_saved_review(
        vault, expected_commit=reopened.locator.commit
    )
    assert discarded.code == "saved_review_discarded", discarded

    source_a_next = source_a.parent / "brain-a-next"
    source_a_next.mkdir()
    record_a["source_identity"]["snapshot_digest"] = "next-a"
    (source_a_next / "migration-record.json").write_text(
        json.dumps(record_a), encoding="utf-8"
    )
    (source_a_next / "Opening.md").write_bytes(b"Next A.\n")
    (source_a_next / asset_a).parent.mkdir()
    (source_a_next / asset_a).write_bytes(b"Historical A resource\x00")
    next_a = operations.prepare_collection_update(
        vault, source_a_next, record_path="migration-record.json"
    )
    assert next_a.preparation is not None, next_a
    refreshed = operations.refresh_update(next_a.preparation)
    assert refreshed.preparation is not None, refreshed.code
    note = next(
        subject
        for subject in refreshed.preparation.review.facts.subjects
        if subject.item_id == "opening"
    )
    assert note.baseline.content.data == original
    assert note.current.content.data == authored
    assert operations.save_update(next_a.preparation).code == "saved"
    assert not (vault / path_b).exists()
