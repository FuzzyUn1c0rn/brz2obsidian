"""Native producer controls keep immutable binary snapshots across requests."""

import gc
import hashlib
import io
import json
import shutil
import tempfile
import weakref
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.contracts import OutputIdentity, ReviewPlan
from tests.application.test_owned_update_preparation import _digest, _tree
from tests.application.test_update_context import worker_context_call
from tests.application.test_vault_checkpoints import git, user_state
from tests.application.test_verified_coverage import (
    add_attachment,
    change_record,
    source_parts,
    write_source,
)


def _native_controls_case(monkeypatch, *, automatic_linked_note=False):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-362-controls-"))
    marker = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(marker), encoding="utf-8")
    evidence = (
        Path(__file__).resolve().parents[2]
        / "tmp/r347-owned-preparation-20261109/fixtures"
    )
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (marker["owner"] + ".json")).write_text(
        json.dumps(marker), encoding="utf-8"
    )
    initial = root / "initial"
    initial.mkdir()
    parts = source_parts(initial)
    asset_id = "66666666-6666-4666-8666-666666666666"
    asset_path = "Attachments/22222222/payload.bin"
    original = b"\xffBaseline binary.\r\n"
    current = b"\xfeAuthored binary.\r\n"
    incoming = b"\xffIncoming binary.\r\n"
    replacement = b"\xfeReplacement binary.\r\n"
    add_attachment(parts, asset_id, 1, "payload.bin", original)
    automatic_note_id = "44444444-4444-4444-8444-444444444444"
    automatic_attachment_id = "55555555-5555-4555-8555-555555555555"
    original_clean = b"Original clean [[Attachments/22222222/payload.bin]].\r\n"
    incoming_clean = b"Incoming clean [[Attachments/22222222/payload.bin]].\r\n"
    if automatic_linked_note:
        thought = json.loads(parts["thoughts.json"].splitlines()[0])
        thought.update(Id=automatic_note_id, Name="Clean linked note")
        parts["thoughts.json"] += b"\n" + json.dumps(thought).encode()
        add_attachment(
            parts,
            automatic_attachment_id,
            1,
            "Notes.md",
            original_clean,
            owner=automatic_note_id,
        )
    initial_archive = write_source(initial, parts)
    workflow = default_workflow()
    metadata = workflow.metadata_factory()
    workflow.metadata_factory = lambda: metadata
    vault, baseline = root / "vault", root / "baseline"
    converted = workflow.convert(initial_archive, vault)
    assert converted.receipt is not None and converted.receipt.verified, converted
    assert (vault / asset_path).read_bytes() == original
    automatic_note_path = None
    if automatic_linked_note:
        record = json.loads((vault / "migration-record.json").read_bytes())
        automatic_note_path = next(
            row["relative_path"]
            for row in record["item_targets"]
            if row["original_identity"] == automatic_note_id
        )
        assert original_clean in (vault / automatic_note_path).read_bytes()
    shutil.copytree(vault, baseline)
    note_path = "Home — Entry thought.md"
    note = (vault / note_path).read_bytes()
    assert b"Authored body." in note and b"payload.bin" in note
    current_note = note.replace(b"Authored body.", b"Local writing.")
    (vault / note_path).write_bytes(current_note)
    (vault / asset_path).write_bytes(current)
    for name, payload in (("incoming", incoming), ("replacement", replacement)):
        directory = root / name
        directory.mkdir()
        parts["22222222-2222-4222-8222-222222222222/payload.bin"] = payload
        change_record(parts, asset_id, DataLength=len(payload))
        parts["22222222-2222-4222-8222-222222222222/Notes.md"] = b"Incoming prose.\r\n"
        change_record(parts, "33333333-3333-4333-8333-333333333333", DataLength=17)
        if automatic_linked_note:
            parts[automatic_note_id + "/Notes.md"] = incoming_clean
            change_record(
                parts, automatic_attachment_id, DataLength=len(incoming_clean)
            )
        write_source(directory, parts)
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Personal.md").write_bytes(b"Committed personal writing.\r\n")
    git(vault, "add", "Personal.md")
    git(vault, "commit", "-qm", "Independent controls fixture")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    (vault / "Personal.md").write_bytes(b"Staged personal writing.\r\n")
    git(vault, "add", "Personal.md")
    (vault / "Personal.md").write_bytes(b"Unstaged personal writing.\r\n")
    scratch = root / "owned-temporary"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    operations = Operations(workflow=workflow)
    seed = operations.capture_checkpoint(
        vault,
        baseline,
        vault_id="native-controls-vault",
        import_id="native-controls-import",
        identity=OutputIdentity(
            collection_id="11111111-1111-4111-8111-111111111111",
            module_id="thebrain-brz",
            module_version="11",
            profile_id="thebrain-format5-reviewed",
            profile_version="11",
            output_format=8,
            settings_digest=hashlib.sha256(b"{}").hexdigest(),
        ),
        admission=operations.inspect_history(vault).admission,
    )
    assert seed.status == "captured" and seed.locator.generation == 1, seed
    manifest = json.loads(
        git(vault, "cat-file", "blob", seed.commit + ":manifest.json")
    )
    assert manifest["review_object"] is None
    return SimpleNamespace(
        root=root,
        vault=vault,
        baseline=baseline,
        scratch=scratch,
        operations=operations,
        seed=seed,
        asset_id=asset_id,
        asset_path=asset_path,
        note_path=note_path,
        current_note=current_note,
        original=original,
        current=current,
        incoming=incoming,
        replacement=replacement,
        initial_archive=initial_archive,
        incoming_archive=root / "incoming/source.brz",
        replacement_archive=root / "replacement/source.brz",
        automatic_note_id=automatic_note_id if automatic_linked_note else None,
        automatic_note_path=automatic_note_path,
    )


def test_native_owned_controls_cancel_refresh_and_retire_snapshots(monkeypatch):
    case = _native_controls_case(monkeypatch)
    context = UpdateContext(operations=case.operations)
    user_before = user_state(case.vault, owned_ref=case.seed.ref)
    baseline_before, scratch_before = _tree(case.baseline), _tree(case.scratch)
    archives_before = tuple(
        _digest(path)
        for path in (
            case.initial_archive,
            case.incoming_archive,
            case.replacement_archive,
        )
    )
    refs_before = git(case.vault, "for-each-ref", "--format=%(refname) %(objectname)")
    locator_before = (case.vault / ".brz2obsidian/locator.json").read_bytes()
    opened = worker_context_call(
        context,
        {
            "command": "prepare",
            "vault": str(case.vault),
            "source": str(case.incoming_archive),
            "kind": "source_update",
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    assert opened.status == "prepared_review" and opened.binding is not None, opened
    page = worker_context_call(
        context, {"command": "page", "binding": opened.binding, "byte_limit": 0}
    )
    assert page.status == "available", page

    # Observe real typed construction without keeping the returned plans alive.
    # Repeated unchanged queries may retain a stable canonical graph, but must
    # not accumulate temporary full plans with the number of requests.
    constructed_plans = []
    actual_validate = ReviewPlan.model_validate.__func__

    def observe_plan(cls, *arguments, **keywords):
        result = actual_validate(cls, *arguments, **keywords)
        constructed_plans.append(weakref.ref(result))
        return result

    def query_unchanged_page():
        repeated = worker_context_call(
            context,
            {"command": "page", "binding": opened.binding, "byte_limit": 0},
        )
        assert repeated.status == "available", repeated
        assert repeated.binding == page.binding
        assert repeated.page == page.page and repeated.offers == page.offers

    with monkeypatch.context() as construction:
        construction.setattr(ReviewPlan, "model_validate", classmethod(observe_plan))
        query_unchanged_page()
        gc.collect()
        warmed_live = sum(reference() is not None for reference in constructed_plans)
        for _ in range(2):
            query_unchanged_page()
            gc.collect()
            assert (
                sum(reference() is not None for reference in constructed_plans)
                <= warmed_live
            )

    asset = next(
        row
        for row in page.page.items
        if row.item_id == case.asset_id and row.facet == "asset"
    )
    asset_offer = next(
        row
        for row in page.offers
        if row.change_id == asset.change_id and row.domain == "attachment"
    )
    details = worker_context_call(
        context,
        {
            "command": "choice_details",
            "binding": opened.binding,
            "requirement_id": asset_offer.requirement_id,
        },
    )
    assert details.status == "available", details
    current_detail = next(
        row for row in details.choice_details if row.choice == "current"
    )
    assert current_detail.path == case.asset_path
    assert (current_detail.size, current_detail.sha256) == (
        len(case.current),
        hashlib.sha256(case.current).hexdigest(),
    )
    references = worker_context_call(
        context,
        {
            "command": "references",
            "binding": opened.binding,
            "requirement_id": asset_offer.requirement_id,
        },
    )
    assert references.status == "available" and references.total_references > 0, (
        references
    )
    assert all(
        b"payload.bin" in row.snippet and "keep_current" in row.choices
        for row in references.references
    )
    staged = worker_context_call(
        context,
        {
            "command": "stage_references",
            "binding": opened.binding,
            "requirement_id": asset_offer.requirement_id,
            "choices": tuple(
                {"reference_id": row.reference_id, "choice": "keep_current"}
                for row in references.references
            ),
        },
    )
    assert staged.code == "reference_choices_staged" and staged.draft_pending
    assert context.save(staged.binding).code == "uncommitted_draft"
    discarded = worker_context_call(
        context, {"command": "discard_draft", "binding": staged.binding}
    )
    assert (
        not discarded.draft_pending
        and discarded.binding.revision > staged.binding.revision
    )
    page = worker_context_call(
        context, {"command": "page", "binding": discarded.binding, "byte_limit": 0}
    )
    note = next(row for row in page.page.items if row.current_path == case.note_path)
    note_offer = next(
        row
        for row in page.offers
        if row.change_id == note.change_id and row.domain == "text"
    )
    edited = case.current_note.replace(b"Local writing.", b"Reviewed bounded edit.")
    draft = worker_context_call(
        context,
        {
            "command": "begin_edit",
            "binding": discarded.binding,
            "requirement_id": note_offer.requirement_id,
            "size": len(edited),
            "sha256": hashlib.sha256(edited).hexdigest(),
        },
    )
    assert draft.code == "edit_started" and draft.edit is not None, draft
    handle = draft.edit.handle
    written = worker_context_call(
        context,
        {"command": "write_edit", "handle": handle, "offset": 0, "data": edited},
    )
    assert written.edit.received_bytes == len(edited)
    sealed = worker_context_call(context, {"command": "seal_edit", "handle": handle})
    assert sealed.edit.sealed
    accepted = worker_context_call(
        context,
        {
            "command": "choose",
            "binding": sealed.binding,
            "requirement_id": note_offer.requirement_id,
            "choice": "edited",
            "assumptions_digest": note_offer.assumptions_digest,
            "edit_handle": handle,
        },
    )
    assert accepted.code == "accepted", accepted
    page = worker_context_call(
        context, {"command": "page", "binding": accepted.binding, "byte_limit": 65536}
    )
    reviewed_note = next(
        row for row in page.page.items if row.current_path == case.note_path
    )
    assert reviewed_note.result == edited
    assert reviewed_note.current == case.current_note
    decision = next(
        row
        for row in page.offers
        if row.change_id == note.change_id and row.domain == "text"
    )
    assert decision.selected == "edited" and decision.decision_id is not None
    cancelled_event, reached = Event(), []
    actual_open = io.open

    def cancel_after_actual_source_open(file, *arguments, **keywords):
        stream = actual_open(file, *arguments, **keywords)
        if (
            isinstance(file, (str, Path))
            and Path(file).absolute() == case.incoming_archive
            and not reached
        ):
            reached.append(str(case.incoming_archive))
            cancelled_event.set()
        return stream

    with monkeypatch.context() as fault:
        fault.setattr(io, "open", cancel_after_actual_source_open)
        cancelled = context.save(accepted.binding, cancel=cancelled_event.is_set)
    assert reached == [str(case.incoming_archive)] and cancelled_event.is_set()
    assert (
        cancelled.status == "cancelled_before_publication"
        and cancelled.code == "cancelled_before_snapshot"
    ), cancelled
    assert (
        not cancelled.ready
        and cancelled.capture is None
        and cancelled.binding is not None
    )
    assert (
        git(case.vault, "for-each-ref", "--format=%(refname) %(objectname)")
        == refs_before
    )
    assert (case.vault / ".brz2obsidian/locator.json").read_bytes() == locator_before
    usable = worker_context_call(
        context, {"command": "choices", "binding": cancelled.binding}
    )
    assert usable.status == "available" and cancelled_event.is_set(), usable
    retained_decision = next(
        row
        for row in usable.offers
        if row.change_id == note.change_id and row.domain == "text"
    )
    assert (
        retained_decision.decision_id == decision.decision_id
        and retained_decision.selected == "edited"
    )
    refreshed = worker_context_call(
        context, {"command": "refresh", "binding": cancelled.binding, "source": None}
    )
    assert refreshed.status == "prepared_review" and refreshed.code == "current", (
        refreshed
    )
    assert refreshed.binding.generation == cancelled.binding.generation
    assert context.page(cancelled.binding).code == "context_changed"
    refused = worker_context_call(
        context,
        {
            "command": "refresh",
            "binding": refreshed.binding,
            "source": str(case.root / "absent.brz"),
        },
    )
    assert refused.status == "refused" and refused.code == "refresh_unavailable", (
        refused
    )
    assert refused.binding.proposal_id == refreshed.binding.proposal_id
    assert refused.binding.generation == refreshed.binding.generation
    after_refusal = worker_context_call(
        context, {"command": "choices", "binding": refused.binding}
    )
    unchanged = next(
        row
        for row in after_refusal.offers
        if row.change_id == note.change_id and row.domain == "text"
    )
    assert (
        unchanged.selected == "edited" and unchanged.decision_id == decision.decision_id
    )
    replaced = worker_context_call(
        context,
        {
            "command": "refresh",
            "binding": refused.binding,
            "source": str(case.replacement_archive),
        },
    )
    assert replaced.status == "prepared_review" and replaced.binding is not None, (
        replaced
    )
    assert replaced.binding.proposal_id == refused.binding.proposal_id
    assert replaced.binding.generation == refused.binding.generation + 1
    assert context.page(refused.binding).code == "context_changed"
    page = worker_context_call(
        context, {"command": "page", "binding": replaced.binding, "byte_limit": 0}
    )
    offset = next(
        index
        for index, row in enumerate(page.page.items)
        if row.item_id == case.asset_id and row.facet == "asset"
    )
    shown = worker_context_call(
        context,
        {
            "command": "page",
            "binding": replaced.binding,
            "offset": offset,
            "limit": 1,
            "byte_limit": 4096,
        },
    )
    assert shown.status == "available", shown
    binary = shown.page.items[0]
    assert (
        binary.original == case.original
        and binary.current == case.current
        and binary.incoming == case.replacement
    )
    assert not binary.omitted and binary.next_byte_offset is None
    closed = worker_context_call(
        context, {"command": "close", "binding": replaced.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and closed.binding is None
    assert _tree(case.scratch) == scratch_before
    assert user_state(case.vault, owned_ref=case.seed.ref) == user_before
    assert _tree(case.baseline) == baseline_before
    assert (
        tuple(
            _digest(path)
            for path in (
                case.initial_archive,
                case.incoming_archive,
                case.replacement_archive,
            )
        )
        == archives_before
    )
    assert (
        git(case.vault, "for-each-ref", "--format=%(refname) %(objectname)")
        == refs_before
    )
    assert (case.vault / ".brz2obsidian/locator.json").read_bytes() == locator_before
