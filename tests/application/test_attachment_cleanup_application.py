"""Explicit cleanup through shared public application preparation and lifecycle."""

from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.checkpoint_contracts import CheckpointLocator, VaultAssociation
from brz2obsidian.application.vault_contracts import VaultFile
from brz2obsidian.application.update_facts import output_identity
from brz2obsidian.publication.vault_native import observe_file
from tests.application.test_history_workflow import (
    absent_history,
    intact_local_history,
)
from tests.application.test_update_lifecycle_admission import COLLECTION, NOTE, note, payload
from tests.reconciliation.test_resolution import preflight
from tests.reconciliation.test_resolution import action
from brz2obsidian.contracts import AttachmentCandidate, AttachmentSelection, ExactContent, LinkOccurrenceChoice
from brz2obsidian.core import select_review_effects
from brz2obsidian.obsidian import interpret_link_target, interpret_links


@pytest.mark.parametrize("condition", ("recovery", "incomplete_references"))
def test_cleanup_preparation_keeps_recovery_and_uncertain_references_out_of_ready_state(
    condition,
):
    if condition == "recovery":
        history = absent_history()
        history = history.model_copy(
            update={
                "admission": history.admission.model_copy(
                    update={"status": "recovery_first"}
                )
            }
        )
        status, code, actions = (
            "recovery_required",
            "recovery_first",
            ("review_recovery",),
        )
    else:
        history = intact_local_history()
        history = history.model_copy(
            update={
                "admission": history.admission.model_copy(
                    update={"inventory_complete": False}
                )
            }
        )
        status, code, actions = (
            "refused",
            "reference_inventory_incomplete",
            ("review_tracking",),
        )

    class ObservedCleanup(Operations):
        def inspect_update_inputs(self, vault):
            return nullcontext(SimpleNamespace(history=history))

    result = ObservedCleanup().prepare_attachment_cleanup("unobserved-vault")
    assert result.kind == "attachment_cleanup"
    assert result.status == status and result.code == code
    assert result.next_actions == actions
    assert result.preparation is None and not result.ready
    assert result.publication == "not_started" and result.application is None
    assert result.recovery_gaps == history.admission.recovery_gaps


def literal_cleanup_case(tmp_path, *, unchanged_note=False, independent_keep=False):
    vault = tmp_path / "vault"
    vault.mkdir()
    retained = payload("a", "Generated ![[Assets/remove.bin]]." if independent_keep else "Generated ![[Assets/remove.bin]] and [[Assets/keep.bin]].")
    asset_bytes = {"Assets/remove.bin": b"\x00remove-original", "Assets/keep.bin": b"\x00keep-original"}
    retained.update(asset_bytes)
    record = json.loads(retained["migration-record.json"])
    record["asset_targets"] = [
        {"asset_id": "remove-asset", "relative_path": "Assets/remove.bin"},
        {"asset_id": "keep-asset", "relative_path": "Assets/keep.bin"},
    ]
    retained["migration-record.json"] = json.dumps(record).encode()
    current = retained | {
        NOTE: retained[NOTE] if unchanged_note else note("Authored ![[Assets/remove.bin]]." if independent_keep else "Authored ![[Assets/remove.bin]] and [[Assets/keep.bin]]."),
        "Manual.md": b"Manual [[Assets/remove.bin|old]]. `[[Assets/remove.bin]]`\r\n",
        "Unrelated.bin": b"\xffunrelated\x00",
    }
    if independent_keep:
        current["Keep.md"] = b"Independent [[Assets/keep.bin]].\r\n"
    inventory = []
    for path, raw in sorted(current.items()):
        actual = vault / path
        actual.parent.mkdir(parents=True, exist_ok=True)
        actual.write_bytes(raw)
        info, sha, _, physical_identity = observe_file(vault, actual, prefix_limit=0)
        inventory.append(
            VaultFile(path=path, mode="100644", size=info.st_size, sha256=sha, identity=physical_identity, tracked=True, excluded=False, exclusion=None)
        )
    association = VaultAssociation(
        schema_id="brz2obsidian.vault-association", schema_version=1,
        association_id="a" * 64, vault_id="cleanup-vault", import_id="cleanup-import",
        collection_id=COLLECTION, module_id="thebrain-brz", vault_anchor="physical-vault", git_anchor="physical-git",
        ref="refs/brz2obsidian/imports/" + "a" * 64 + "/checkpoint",
    )
    locator = CheckpointLocator(schema_id="brz2obsidian.checkpoint-locator", schema_version=1, association=association, generation=2, commit="b" * 40)
    history = SimpleNamespace(
        status="intact",
        admission=SimpleNamespace(status="supported", vault=str(vault), inventory_complete=True, inventory=tuple(inventory), findings=(), recovery_gaps=(), repository=SimpleNamespace(kind="root"), preflight=preflight()),
        checkpoint=SimpleNamespace(locator=locator, review=None, manifest=SimpleNamespace(boundary="result", identity=output_identity(record), source=tuple(SimpleNamespace(path=p, size=len(raw), mode="100644", sha256=hashlib.sha256(raw).hexdigest()) for p, raw in sorted(retained.items())), reviewed_source=None)),
    )
    from brz2obsidian.contracts import ImportedItemIdentity, RetainedAttachmentOwnership

    case = SimpleNamespace(vault=vault, history=history, retained=retained, current=current)
    case.owners = tuple(RetainedAttachmentOwnership(
        schema_id="brz2obsidian.retained-attachment-ownership", schema_version=1,
        association_id=association.association_id, checkpoint_commit="1" * 40,
        generation=1, identity=ImportedItemIdentity(collection_id=COLLECTION,
            module_id="thebrain-brz", item_id=row["asset_id"]), facet="asset",
        source_path=row["relative_path"], source_version="a" * 64,
        mapping_sha256=hashlib.sha256(retained["migration-record.json"]).hexdigest(),
        payload_sha256=hashlib.sha256(asset_bytes[row["relative_path"]]).hexdigest(),
        payload_size=len(asset_bytes[row["relative_path"]]), payload_mode="100644",
    ) for row in record["asset_targets"])

    class ObservedCleanup(Operations):
        def inspect_update_inputs(self, path):
            refreshed = []
            for old in history.admission.inventory:
                info, sha, _, physical_identity = observe_file(vault, vault / old.path, prefix_limit=0)
                refreshed.append(old.model_copy(update={"size": info.st_size, "sha256": sha, "identity": physical_identity}))
            history.admission.inventory = tuple(refreshed)
            return nullcontext(SimpleNamespace(history=history, read_payload=lambda **kwargs: SimpleNamespace(status="available", chunks=tuple(SimpleNamespace(path=p, data=raw) for p, raw in retained.items())), read_attachment_ownership=lambda **kwargs: tuple(owner for owner in case.owners if owner.source_path in kwargs["paths"]), inspect=lambda **kwargs: history))

    case.operations = ObservedCleanup()
    return case


@pytest.mark.parametrize("ownership", ("retained", "removed-then-manual"))
def test_cleanup_keeps_historical_original_distinct_from_current_retained_source(tmp_path, ownership):
    case = literal_cleanup_case(tmp_path)
    case.retained.pop("Assets/remove.bin")
    record = json.loads(case.retained["migration-record.json"])
    record["asset_targets"] = [row for row in record["asset_targets"] if row["asset_id"] != "remove-asset"]
    record["source_identity"]["snapshot_digest"] = "b" * 64
    case.retained["migration-record.json"] = json.dumps(record).encode()
    case.history.checkpoint.manifest.source = tuple(SimpleNamespace(path=p, size=len(raw), mode="100644", sha256=hashlib.sha256(raw).hexdigest()) for p, raw in sorted(case.retained.items()))
    if ownership == "removed-then-manual":
        case.owners = tuple(owner for owner in case.owners if owner.identity.item_id != "remove-asset")
        (case.vault / "Assets/remove.bin").write_bytes(b"later manual bytes at the old name\x00")
    before = {path: (case.vault / path).read_bytes() for path in case.current}
    offered = case.operations.prepare_attachment_cleanup(case.vault)
    assert offered.preparation is not None, offered.code
    plan = offered.preparation.review
    assert plan.facts.format_operation.target_source_version == "b" * 64
    subjects = {s.item_id: s for s in plan.producer_facts.subjects}
    if ownership == "retained":
        asset = subjects["remove-asset"]
        assert asset.baseline.status == "unknown" and asset.baseline.content is None
        assert asset.incoming is None and asset.current.content.data == b"\x00remove-original"
        assert asset.attachment.retained_ownership.source_version == "a" * 64
        change = next(c for c in plan.proposal.changes if c.item_id == "remove-asset")
        assert next(a for a in change.attachment_review.alternatives if a.choice == "remove").eligible
    else:
        assert "remove-asset" not in subjects
    assert {path: (case.vault / path).read_bytes() for path in case.current} == before
    assert {p.relative_to(Path(offered.preparation.payload_directory)).as_posix(): p.read_bytes() for p in Path(offered.preparation.payload_directory).rglob("*") if p.is_file()} == case.retained


def test_cleanup_preparation_binds_recorded_asset_and_independent_manual_references(tmp_path):
    case = literal_cleanup_case(tmp_path)
    offered = case.operations.prepare_attachment_cleanup(case.vault)
    assert offered.status == "prepared_review", offered.code
    assert offered.kind == "attachment_cleanup" and not offered.ready
    prepared = offered.preparation
    assert prepared.locator == case.history.checkpoint.locator
    facts = prepared.review.producer_facts
    assert facts.format_operation.kind == "attachment_cleanup"
    assert facts.format_operation.baseline_source_version == facts.format_operation.target_source_version == "a" * 64
    change = next(c for c in prepared.review.proposal.changes if c.item_id == "remove-asset")
    assert change.facet == "asset" and change.path == "Assets/remove.bin"
    assert change.current.data == b"\x00remove-original"
    alternatives = {a.choice: a for a in change.attachment_review.alternatives}
    assert alternatives["current"].eligible and alternatives["remove"].eligible
    assert alternatives["remove"].outputs == ()
    context = facts.link_context
    assert {d.source_path for d in context.current_documents} >= {NOTE, "Manual.md"}
    affected = [o for d in context.current_documents for o in d.occurrences if o.meaning.target_id == "subject:remove-asset:asset"]
    assert len(affected) == 2
    assert {path: (case.vault / path).read_bytes() for path in case.current} == case.current
    assert {p.relative_to(Path(prepared.payload_directory)).as_posix(): p.read_bytes() for p in Path(prepared.payload_directory).rglob("*") if p.is_file()} == case.retained


def cleanup_asset_action(plan, item, choice, *, document_edits=None):
    change = next(c for c in plan.proposal.changes if c.item_id == item)
    alternative = next(a for a in change.attachment_review.alternatives if a.choice == choice)
    context = plan.producer_facts.link_context
    documents, states, links = context.current_documents, context.current_target_facts, ()
    if choice == "remove":
        target_id = "subject:remove-asset:asset"
        states = tuple(interpret_link_target(None, target_id=s.target_id, existence="missing", memberships=()) if s.target_id == target_id else s for s in states)
        edited = document_edits if document_edits is not None else {NOTE: note("Authored  and [[Assets/keep.bin]]."), "Manual.md": b"Manual . `[[Assets/remove.bin]]`\r\n"}
        documents = tuple(interpret_links(ExactContent(data=edited.get(d.source_path, d.content.data)), document_id=d.document_id, source_path=d.source_path, path_mode=d.path_mode, targets=context.current_targets, target_facts=states, inventory="complete") for d in documents)
        states = tuple(interpret_link_target(d.content, target_id=s.target_id, existence="present", memberships=()) if (d := next((d for d in documents if d.document_id == s.target_id), None)) is not None else s for s in states)
        links = tuple(LinkOccurrenceChoice(document_id=d.document_id, occurrence_id=o.occurrence_id, old=o.meaning, replacement=b"", selected=None, expected_memberships=(), provenance="explicit_user") for d in context.current_documents for o in d.occurrences if o.meaning.target_id == target_id)
    selection = AttachmentSelection(schema_id="brz2obsidian.attachment-selection", schema_version=1, proposal_id=plan.proposal.proposal_id, generation=plan.proposal.generation, item_id=change.item_id, facet=change.facet, reviewed_change_id=change.change_id, reviewed_assumptions=change.assumptions, choice=choice, link_choices=links, provenance="explicit_user")
    candidate = AttachmentCandidate(schema_id="brz2obsidian.attachment-candidate", schema_version=1, outputs=alternative.outputs, documents=documents, targets=context.current_targets, target_facts=states)
    return action(plan, change, decision_id="cleanup:" + item, domain="attachment", choice=choice, attachment_selection=selection, attachment_candidate=candidate)


def test_cleanup_resolution_and_refresh_keep_only_unaffected_current_choices(tmp_path):
    case = literal_cleanup_case(tmp_path, independent_keep=True)
    offered = case.operations.prepare_attachment_cleanup(case.vault)
    prepared = offered.preparation
    kept = case.operations.resolve_update(prepared, cleanup_asset_action(prepared.review, "keep-asset", "current"))
    assert kept.code == "accepted", kept.code
    prepared = kept.preparation
    removed = case.operations.resolve_update(prepared, cleanup_asset_action(prepared.review, "remove-asset", "remove", document_edits={NOTE: note("Authored ."), "Manual.md": b"Manual . `[[Assets/remove.bin]]`\r\n"}))
    (tmp_path / "removed-preparation.json").write_text(removed.model_dump_json(), encoding="utf-8")
    assert removed.code == "accepted" and removed.ready, (
        removed.code, removed.preparation.review.blockers,
        [(r.domain, r.change_id, r.choices) for r in removed.preparation.review.requirements],
    )
    prepared = removed.preparation
    selected = select_review_effects(prepared.review)
    assert selected.remove_paths == ("Assets/remove.bin",)
    assert {f.path: f.content.data for f in selected.files}["Manual.md"] == b"Manual . `[[Assets/remove.bin]]`\r\n"
    assert {f.path: f.content.data for f in selected.files}[NOTE] == note("Authored .")
    assert {path: (case.vault / path).read_bytes() for path in case.current} == case.current
    changed = case.current["Manual.md"] + b"Later independent writing.\n"
    (case.vault / "Manual.md").write_bytes(changed)
    refreshed = case.operations.refresh_update(prepared)
    (tmp_path / "refreshed-preparation.json").write_text(refreshed.model_dump_json(), encoding="utf-8")
    assert refreshed.preparation is not None and not refreshed.ready, refreshed.code
    assert refreshed.kind == "attachment_cleanup"
    plan = refreshed.preparation.review
    assert plan.proposal.generation == prepared.review.proposal.generation + 1
    old_keep = next(c for c in prepared.review.proposal.changes if c.item_id == "keep-asset")
    new_keep = next(c for c in plan.proposal.changes if c.item_id == "keep-asset")
    old_assumptions = {a.key: a.fingerprint for a in old_keep.assumptions}
    changed_assumptions = tuple(a.key for a in new_keep.assumptions if old_assumptions.get(a.key) != a.fingerprint)
    assert [a.decision_id for a in plan.approvals] == ["cleanup:keep-asset"], changed_assumptions
    pending = {r.change_id for r in plan.requirements}
    assert {c.item_id for c in plan.proposal.changes if c.change_id in pending} == {"remove-asset"}
    assert (case.vault / "Manual.md").read_bytes() == changed
    assert (case.vault / "Assets/remove.bin").read_bytes() == b"\x00remove-original"
    assert (case.vault / NOTE).read_bytes() == case.current[NOTE]


def test_cleanup_keeps_explicit_note_current_in_conflict_with_reference_edit(tmp_path):
    case = literal_cleanup_case(tmp_path, unchanged_note=True)
    prepared = case.operations.prepare_attachment_cleanup(case.vault).preparation
    note_change = next(c for c in prepared.review.proposal.changes if c.path == NOTE)
    locked = case.operations.resolve_update(prepared, action(prepared.review, note_change, domain="text", choice="current", decision_id="explicit-note-current"))
    assert locked.code == "accepted", locked.code
    assert any(a.decision_id == "explicit-note-current" and a.choice == "current" for a in locked.preparation.review.approvals)
    prepared = locked.preparation
    kept = case.operations.resolve_update(prepared, cleanup_asset_action(prepared.review, "keep-asset", "current"))
    assert kept.code == "accepted", kept.code
    prepared = kept.preparation
    removed = case.operations.resolve_update(prepared, cleanup_asset_action(prepared.review, "remove-asset", "remove", document_edits={NOTE: note("Generated  and [[Assets/keep.bin]]."), "Manual.md": b"Manual . `[[Assets/remove.bin]]`\r\n"}))
    assert not removed.ready
    assert "selected_output_conflict" in removed.preparation.review.blockers
    assert select_review_effects(removed.preparation.review).status == "refused"
    assert {path: (case.vault / path).read_bytes() for path in case.current} == case.current
