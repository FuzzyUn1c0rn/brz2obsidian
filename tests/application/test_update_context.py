"""The producer keeps unsaved shared reviews behind finite context handles."""

from types import SimpleNamespace

from tests.application.test_attachment_cleanup_application import literal_cleanup_case


def worker_context_call(producer, arguments):
    import io
    from uuid import uuid4

    from brz2obsidian.application.contracts import WorkerRequest
    from brz2obsidian.application.protocol import (
        REQUEST_LIMIT,
        decode_request,
        encode_request,
    )
    from brz2obsidian.application.update_stream import WorkerStreamDecoder
    from brz2obsidian.application.update_worker import UpdateWorker

    output = io.BytesIO()
    request = WorkerRequest(
        request_id=str(uuid4()), operation="update", sequence=1, arguments=arguments
    )
    wire = encode_request(request)
    assert len(wire) <= REQUEST_LIMIT and b"attachment_candidate" not in wire
    UpdateWorker(context=producer, output=output).handle(decode_request(wire))
    decoder = WorkerStreamDecoder(request)
    terminal = None
    for frame in output.getvalue().splitlines(keepends=True):
        terminal = decoder.feed(frame)
    assert terminal is not None and terminal.protocol_error is None
    return terminal.result


def context_case(tmp_path):
    from brz2obsidian.application.update_context import UpdateContext

    case = literal_cleanup_case(tmp_path, independent_keep=True)
    operations_type = type(case.operations)

    class NativeInputs(operations_type):
        def read_checkpoint(self, vault, **kwargs):
            return SimpleNamespace(status="valid", **vars(case.history.checkpoint))

        def capture_checkpoint(self, *args, **kwargs):
            raise AssertionError("Opening or inspecting an unsaved review cannot Save")

    case.operations = NativeInputs()
    return UpdateContext(operations=case.operations), case


def test_reference_draft_blocks_other_operations_until_explicit_discard(tmp_path):
    context, case = context_case(tmp_path)
    selection = "11111111-1111-4111-8111-111111111111"
    opened = context.prepare(
        case.vault, selection_id=selection, kind="attachment_cleanup"
    )
    page = context.page(opened.binding, byte_limit=0)
    remove = next(row for row in page.page.items if row.item_id == "remove-asset")
    offer = next(row for row in page.offers if row.change_id == remove.change_id)
    reference = context.reference_page(
        opened.binding, requirement_id=offer.requirement_id, limit=1
    ).references[0]
    staged = worker_context_call(
        context,
        {
            "command": "stage_references",
            "binding": opened.binding,
            "requirement_id": offer.requirement_id,
            "choices": ({"reference_id": reference.reference_id, "choice": "drop"},),
        },
    )
    assert staged.draft_pending and not staged.ready
    for blocked in (
        context.history(case.vault, selection_id=selection),
        context.initialize_vault(staged.binding, choice="initialize"),
        context.prepare_history(staged.binding, action="undo"),
        context.refresh_history(staged.binding),
        context.execute_history(staged.binding),
        context.refresh(staged.binding),
        context.choose_configuration(
            staged.binding, group_id="unselected-configuration", choice="current"
        ),
    ):
        assert blocked.code in ("close_decision_required", "uncommitted_draft")
        assert blocked.binding == staged.binding and not blocked.ready
        assert context.draft_pending
        retained = context.reference_page(
            staged.binding, requirement_id=offer.requirement_id, limit=1
        )
        assert retained.references[0].reference_id == reference.reference_id
        assert retained.references[0].selected == "drop"
        wire_blocked = worker_context_call(
            context, {"command": "save", "binding": staged.binding}
        )
        assert wire_blocked.code == "uncommitted_draft"
        assert wire_blocked.draft_pending and not wire_blocked.ready
    assert context.page(staged.binding, byte_limit=0).page == page.page
    discarded = worker_context_call(
        context, {"command": "discard_draft", "binding": staged.binding}
    )
    assert discarded.code == "draft_discarded" and not discarded.draft_pending
    assert not discarded.ready
    assert discarded.binding.proposal_id == opened.binding.proposal_id
    assert {
        path: (case.vault / path).read_bytes() for path in case.current
    } == case.current


def test_cancelled_saved_inspection_never_retains_a_ready_context_handle(tmp_path):
    from brz2obsidian.application.update_context import UpdateContext
    from brz2obsidian.application.update_contracts import UpdatePreparation, UpdateResult
    from brz2obsidian.core import load_review, resolve_review, save_review
    from tests.application.test_update_lifecycle_contracts import preparation
    from tests.reconciliation.test_resolution import action

    pending = preparation()
    accepted = resolve_review(pending.review, action(pending.review, choice="current"))
    assert accepted.status == "accepted" and accepted.plan.ready
    prepared = UpdatePreparation.model_validate(
        pending.model_dump(mode="python")
        | {
            "vault": str(tmp_path),
            "review": accepted.plan,
            "locator": pending.locator.model_copy(update={"commit": "c" * 40}),
        }
    )
    loaded = load_review(save_review(accepted.plan).record.model_dump_json()).loaded
    assert loaded is not None and not loaded.ready

    calls = []

    class SavedInspection:
        def load_update(self, vault):
            calls.append("load")
            return UpdateResult(
                status="unresolved",
                code="revalidation_required",
                loaded=loaded,
                history_retained=True,
                checkpoint_commit="c" * 40,
            )

        def resume_update(self, vault):
            calls.append("resume")
            return UpdateResult(
                status="prepared_review",
                code="unchanged",
                preparation=prepared,
                ready=True,
                history_retained=True,
                checkpoint_commit="c" * 40,
            )

    selection = "11111111-1111-4111-8111-111111111111"
    for command in ("load", "resume"):
        positive = UpdateContext(operations=SavedInspection())
        available = getattr(positive, command)(tmp_path, selection_id=selection)
        assert calls == [command]
        calls.clear()
        if command == "resume":
            assert available.ready and available.binding is not None
            assert available.binding.proposal_id == accepted.plan.proposal.proposal_id
            assert available.binding.checkpoint_commit == "c" * 40
            assert positive.close(available.binding, choice="continue").ready
        else:
            assert not available.ready and available.binding is None
            assert available.code == "revalidation_required"
            assert available.history_retained
        before = UpdateContext(operations=SavedInspection())
        result = getattr(before, command)(
            tmp_path, selection_id=selection, cancel=lambda: True
        )
        assert result.code == "cancelled_before_inspection" and result.binding is None
        assert not result.ready and result.publication == "not_published"
        assert calls == []
        after = UpdateContext(operations=SavedInspection())
        checks = iter((False, True))
        result = getattr(after, command)(
            tmp_path, selection_id=selection, cancel=lambda: next(checks)
        )
        assert result.code == "cancelled_after_inspection" and result.binding is None
        assert not result.ready and result.history_retained
        assert result.checkpoint_commit == "c" * 40
        assert result.next_actions == ("inspect_history",)
        continued = after.close(choice="continue")
        assert not continued.ready and continued.binding is None
        assert calls == [command]
        calls.clear()


def test_onboarding_worker_preserves_separate_original_evidence_input(
    tmp_path, monkeypatch
):
    import hashlib
    import zipfile

    import pytest

    from brz2obsidian.application.contracts import WorkerRequest
    from brz2obsidian.application.update_context import UpdateContext
    from tests.application.test_onboarding_originals import (
        CURRENT,
        ORIGINAL,
        controlled_history,
        legacy_brz_case,
    )

    operations, vault, archive = legacy_brz_case(tmp_path)
    controlled_history(operations, vault, monkeypatch)
    monkeypatch.setattr(
        operations,
        "read_checkpoint",
        lambda *args, **kwargs: SimpleNamespace(status="absent", locator=None),
    )
    reference = tmp_path / "same-content-reference.brz"
    with (
        zipfile.ZipFile(archive) as source,
        zipfile.ZipFile(reference, "w", compression=zipfile.ZIP_DEFLATED) as target,
    ):
        for name in source.namelist():
            target.writestr(name, source.read(name))
    assert (
        hashlib.sha256(archive.read_bytes()).digest()
        != hashlib.sha256(reference.read_bytes()).digest()
    )
    before = {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*")
        if path.is_file()
    }
    arguments = {
        "command": "prepare",
        "kind": "onboarding",
        "vault": str(vault),
        "source": str(reference),
        "original_source": str(archive),
        "selection_id": "11111111-1111-4111-8111-111111111111",
    }
    context = UpdateContext(operations=operations)
    result = worker_context_call(context, arguments)
    assert (
        result.kind == "onboarding" and result.binding is not None and not result.ready
    )
    page = worker_context_call(context, {"command": "page", "binding": result.binding})
    assert page.status == "available"
    note = next(
        row
        for row in page.page.items
        if row.item_id == "22222222-2222-4222-8222-222222222222"
    )
    assert note.original == ORIGINAL and note.current == CURRENT
    for kind in ("source_update", "format_transition", "attachment_cleanup"):
        with pytest.raises(ValueError):
            WorkerRequest(
                request_id="11111111-1111-4111-8111-111111111111",
                operation="update",
                sequence=1,
                arguments=arguments | {"kind": kind},
            )
    assert {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*")
        if path.is_file()
    } == before


def test_worker_pages_bound_consent_and_identity_choices_from_real_preparation(
    tmp_path, monkeypatch
):
    from brz2obsidian.application.update_context import UpdateContext
    from brz2obsidian.contracts import ReviewConsentRequirement
    from tests.application.test_onboarding_originals import (
        NOTE,
        controlled_history,
        legacy_brz_case,
    )

    operations, vault, archive = legacy_brz_case(tmp_path)
    duplicate = vault / "Duplicate.md"
    duplicate.write_bytes((vault / NOTE).read_bytes())
    controlled_history(operations, vault, monkeypatch)
    history = operations.inspect_history(vault)
    history.admission.preflight = history.admission.preflight.model_copy(
        update={
            "consents": (
                ReviewConsentRequirement(
                    schema_id="brz2obsidian.review-consent-requirement",
                    schema_version=1,
                    consent_id="tracked-legacy",
                    kind="tracking",
                    requirement="required",
                    policy="ordinary",
                    fingerprint="native-policy-snapshot",
                    disclosure="Include the exact reviewed ignored note in owned history.",
                    subjects=(),
                ),
            )
        }
    )
    before = {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*")
        if path.is_file()
    }
    context = UpdateContext(operations=operations)
    opened = worker_context_call(
        context,
        {
            "command": "prepare",
            "kind": "onboarding",
            "vault": str(vault),
            "source": str(archive),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    assert opened.binding is not None
    page = worker_context_call(
        context,
        {"command": "choices", "binding": opened.binding, "offset": 0, "limit": 100},
    )
    assert page.total_choices == len(page.offers) and page.next_choice_offset is None
    consent = next(row for row in page.offers if row.domain == "tracking")
    assert consent.choices == ("accept", "decline")
    assert (
        consent.disclosure
        == "Include the exact reviewed ignored note in owned history."
    )
    assert consent.policy == "ordinary" and not consent.detail_omitted
    accepted = worker_context_call(
        context,
        {
            "command": "choose",
            "binding": opened.binding,
            "requirement_id": consent.requirement_id,
            "choice": "accept",
            "assumptions_digest": consent.assumptions_digest,
        },
    )
    assert accepted.code == "accepted" and not accepted.ready
    identity = next(row for row in page.offers if row.domain == "identity")
    entries = []
    for index in range(2):
        detail = worker_context_call(
            context,
            {
                "command": "choice_details",
                "binding": accepted.binding,
                "requirement_id": identity.requirement_id,
                "offset": index,
                "limit": 1,
            },
        )
        assert detail.total_choice_details == 2 and len(detail.choice_details) == 1
        entries.extend(detail.choice_details)
    assert {row.path for row in entries} == {NOTE, "Duplicate.md"}
    assert all(
        row.entry_id and row.sha256 and row.eligible and row.target_safe
        for row in entries
    )
    selected = worker_context_call(
        context,
        {
            "command": "choose",
            "binding": accepted.binding,
            "requirement_id": identity.requirement_id,
            "choice": "associate",
            "assumptions_digest": identity.assumptions_digest,
            "selected_entry_id": entries[0].entry_id,
            "disassociate_entry_ids": (entries[1].entry_id,),
        },
    )
    assert (
        selected.code == "accepted"
        and not selected.ready
        and selected.publication == "not_started"
    )
    assert {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*")
        if path.is_file()
    } == before


def test_unsaved_context_retains_proposal_and_refuses_foreign_or_stale_page(tmp_path):
    context, case = context_case(tmp_path)
    selection = "11111111-1111-4111-8111-111111111111"
    offered = context.prepare(
        case.vault, selection_id=selection, kind="attachment_cleanup"
    )
    assert offered.status == "prepared_review" and offered.code == "prepared"
    assert offered.binding is not None and not offered.ready
    assert offered.binding.selection_id == selection
    assert offered.binding.association_id == "a" * 64
    assert offered.kind == "attachment_cleanup"
    assert offered.unresolved == 2
    assert "remove-original" not in offered.model_dump_json()
    assert "payload_directory" not in offered.model_dump_json()
    first = context.page(offered.binding, limit=1, byte_limit=128)
    assert first.status == "available" and first.page is not None
    assert first.page.proposal_id == offered.binding.proposal_id
    assert first.page.generation == offered.binding.generation
    assert len(first.page.items) == 1 and first.page.next_offset == 1
    again = context.page(offered.binding, limit=1, byte_limit=128)
    assert again.page == first.page
    assert not (case.vault / ".brz2obsidian").exists()

    for foreign in (
        offered.binding.model_copy(
            update={"selection_id": "22222222-2222-4222-8222-222222222222"}
        ),
        offered.binding.model_copy(update={"association_id": "b" * 64}),
        offered.binding.model_copy(
            update={"generation": offered.binding.generation + 1}
        ),
    ):
        refused = context.page(foreign, limit=1, byte_limit=128)
        assert refused.status == "refused" and refused.code == "context_changed"
        assert refused.page is None
    assert {path: (case.vault / path).read_bytes() for path in case.current} == (
        case.current
    )


def test_small_current_choice_uses_offered_attachment_without_candidate_on_wire(
    tmp_path,
):
    context, case = context_case(tmp_path)
    offered = context.prepare(
        case.vault,
        selection_id="11111111-1111-4111-8111-111111111111",
        kind="attachment_cleanup",
    )
    page = context.page(offered.binding, byte_limit=0)
    change = next(row for row in page.page.items if row.item_id == "keep-asset")
    choice = next(row for row in page.offers if row.change_id == change.change_id)
    assert choice.domain == "attachment" and choice.choices == ("current", "remove")
    assert len(choice.assumptions_digest) == 64
    assert "attachment_candidate" not in page.model_dump_json()
    accepted = context.choose(
        offered.binding,
        requirement_id=choice.requirement_id,
        choice="current",
        assumptions_digest=choice.assumptions_digest,
    )
    assert accepted.code == "accepted" and not accepted.ready
    assert accepted.unresolved == 1
    assert accepted.binding.proposal_id == offered.binding.proposal_id
    assert accepted.binding.generation == offered.binding.generation
    assert accepted.binding.revision == offered.binding.revision + 1
    assert "keep-original" not in accepted.model_dump_json()
    stale = context.choose(
        offered.binding,
        requirement_id=choice.requirement_id,
        choice="remove",
        assumptions_digest=choice.assumptions_digest,
    )
    assert stale.status == "refused" and stale.code == "context_changed"
    assert not (case.vault / ".brz2obsidian").exists()
    assert {path: (case.vault / path).read_bytes() for path in case.current} == (
        case.current
    )


def test_remove_choice_uses_bounded_offered_references_and_preserves_other_spans(
    tmp_path,
):
    from brz2obsidian.core import select_review_effects

    context, case = context_case(tmp_path)
    opened = context.prepare(
        case.vault,
        selection_id="11111111-1111-4111-8111-111111111111",
        kind="attachment_cleanup",
    )
    page = context.page(opened.binding, byte_limit=0)
    change = next(row for row in page.page.items if row.item_id == "remove-asset")
    offer = next(row for row in page.offers if row.change_id == change.change_id)
    first = context.reference_page(
        opened.binding, requirement_id=offer.requirement_id, offset=0, limit=1
    )
    assert first.status == "available" and len(first.references) == 1
    assert first.total_references == 2 and first.next_reference_offset == 1
    second = context.reference_page(
        opened.binding, requirement_id=offer.requirement_id, offset=1, limit=1
    )
    assert len(second.references) == 1 and second.next_reference_offset is None
    refs = first.references + second.references
    assert all(row.choices == ("drop",) for row in refs)
    assert first.references[0].document_path.endswith(".md")
    assert b"Assets/remove.bin" in first.references[0].snippet
    assert len(first.references[0].snippet) <= 512
    assert "Manual ." not in first.model_dump_json()
    forged = context.choose(
        opened.binding,
        requirement_id=offer.requirement_id,
        choice="remove",
        assumptions_digest=offer.assumptions_digest,
        references=({"reference_id": "0" * 64, "choice": "drop"},),
    )
    assert forged.status == "refused" and forged.code == "offer_changed"
    missing = context.choose(
        opened.binding,
        requirement_id=offer.requirement_id,
        choice="remove",
        assumptions_digest=offer.assumptions_digest,
    )
    assert missing.status == "refused" and missing.code == "offer_changed"
    staged = context.stage_references(
        opened.binding,
        requirement_id=offer.requirement_id,
        choices=({"reference_id": refs[0].reference_id, "choice": "drop"},),
    )
    assert staged.code == "reference_choices_staged" and staged.unresolved == 2
    assert context.save(staged.binding).code == "uncommitted_draft"
    assert context.apply(staged.binding).code == "uncommitted_draft"
    incomplete = context.choose(
        staged.binding,
        requirement_id=offer.requirement_id,
        choice="remove",
        assumptions_digest=offer.assumptions_digest,
    )
    assert incomplete.code == "offer_changed"
    staged = context.stage_references(
        staged.binding,
        requirement_id=offer.requirement_id,
        choices=({"reference_id": refs[1].reference_id, "choice": "drop"},),
    )
    assert all(
        row.selected == "drop"
        for row in context.reference_page(
            staged.binding, requirement_id=offer.requirement_id
        ).references
    )
    removed = context.choose(
        staged.binding,
        requirement_id=offer.requirement_id,
        choice="remove",
        assumptions_digest=offer.assumptions_digest,
    )
    assert removed.code == "accepted" and removed.unresolved == 1
    # The public shared seam also serves non-worker callers; candidate bytes stay local.
    prepared = case.operations.prepare_attachment_cleanup(case.vault).preparation
    native = case.operations.resolve_update_choice(
        prepared,
        requirement_id=offer.requirement_id,
        choice="remove",
        assumptions_digest=offer.assumptions_digest,
        references=tuple(
            {"reference_id": row.reference_id, "choice": "drop"} for row in refs
        ),
    )
    keep = next(
        row
        for row in native.preparation.review.requirements
        if row.change_id != change.change_id
    )
    from brz2obsidian.application.review_choices import requirement_digest

    ready = case.operations.resolve_update_choice(
        native.preparation,
        requirement_id=keep.requirement_id,
        choice="current",
        assumptions_digest=requirement_digest(keep),
    )
    effects = select_review_effects(ready.preparation.review)
    assert ready.ready and effects.status == "selected"
    manual = next(row for row in effects.files if row.path == "Manual.md")
    assert manual.content.data == b"Manual . `[[Assets/remove.bin]]`\r\n"
    assert effects.remove_paths == ("Assets/remove.bin",)
    assert {
        path: (case.vault / path).read_bytes() for path in case.current
    } == case.current


def test_explicit_save_load_unready_and_resume_rebind_the_native_checkpoint(
    tmp_path, monkeypatch
):
    from brz2obsidian.application.checkpoint_contracts import CheckpointResult
    from brz2obsidian.application.operations import ApplicationSession
    from brz2obsidian.application.update_context import UpdateContext
    from brz2obsidian.core import load_review, save_review

    context, case = context_case(tmp_path)
    captured = []
    sessions = {}

    def wire(producer, arguments):
        import io

        from brz2obsidian.application.protocol import decode_request, encode_request
        from brz2obsidian.application.transport import Terminal
        from brz2obsidian.application.update_stream import WorkerStreamDecoder
        from brz2obsidian.application.update_worker import UpdateWorker

        output = io.BytesIO()
        if producer not in sessions:
            sessions[producer] = ApplicationSession()
            sessions[producer].select_update(
                arguments["vault"], selection_id=arguments["selection_id"]
            )
        session = sessions[producer]
        request = session.start_update(arguments)
        assert request is not None
        UpdateWorker(context=producer, output=output).handle(
            decode_request(encode_request(request))
        )
        decoder = WorkerStreamDecoder(request)
        terminal = None
        for frame in output.getvalue().splitlines(keepends=True):
            terminal = decoder.feed(frame)
        assert terminal is not None and terminal.protocol_error is None
        session.complete_update(
            request.request_id, Terminal(phase="completed", response=terminal)
        )
        return terminal.result

    def persist(
        self, vault, source, *, review, source_binding, observed_source, **kwargs
    ):
        saved = save_review(review)
        assert saved.status == "saved"
        loaded = load_review(saved.record.model_dump_json())
        assert loaded.status == "loaded" and not loaded.loaded.saved.plan.ready
        checkpoint = case.history.checkpoint
        checkpoint.review = loaded.loaded
        checkpoint.locator = checkpoint.locator.model_copy(
            update={"commit": "c" * 40, "generation": 3}
        )
        checkpoint.manifest.boundary = "local"
        checkpoint.manifest.reviewed_source = source_binding
        checkpoint.manifest.observed_source = observed_source
        captured.append(True)
        return CheckpointResult(
            schema_id="brz2obsidian.checkpoint-result",
            schema_version=1,
            status="captured",
            code="captured",
            commit=checkpoint.locator.commit,
            ref=checkpoint.locator.association.ref,
            history_retained=True,
            objects_written=True,
            object_storage="verified",
            authored_files_changed=False,
            message="Controlled public native persistence.",
            locator=checkpoint.locator,
        )

    monkeypatch.setattr(type(case.operations), "capture_checkpoint", persist)
    opened = wire(
        context,
        {
            "command": "prepare",
            "vault": str(case.vault),
            "source": None,
            "selection_id": "11111111-1111-4111-8111-111111111111",
            "kind": "attachment_cleanup",
        },
    )
    assert opened.binding.checkpoint_generation == 2
    page = wire(
        context, {"command": "page", "binding": opened.binding, "byte_limit": 0}
    )
    change = next(row for row in page.page.items if row.item_id == "keep-asset")
    offer = next(row for row in page.offers if row.change_id == change.change_id)
    accepted = wire(
        context,
        {
            "command": "choose",
            "binding": opened.binding,
            "requirement_id": offer.requirement_id,
            "choice": "current",
            "assumptions_digest": offer.assumptions_digest,
        },
    )
    saved = wire(context, {"command": "save", "binding": accepted.binding})
    assert captured == [True] and saved.code == "saved"
    assert saved.binding.checkpoint_commit == "c" * 40
    assert (
        saved.binding.checkpoint_generation == 3
        and saved.binding.revision > accepted.binding.revision
    )
    for command in ("references", "choice_details"):
        refused = wire(
            context,
            {
                "command": command,
                "binding": saved.binding,
                "requirement_id": "unoffered-requirement",
            },
        )
        assert refused.code == "offer_changed" and not refused.ready
        assert refused.binding == saved.binding and refused.history_retained
        assert (
            refused.checkpoint_commit == saved.checkpoint_commit
            and refused.capture == saved.capture
        )
        assert refused.publication == saved.publication
        snapshot = sessions[context].update_snapshot
        assert snapshot.binding == saved.binding and snapshot.history_retained
        assert (
            snapshot.checkpoint_commit == saved.checkpoint_commit
            and not snapshot.needs_inspection
        )
    assert context.page(accepted.binding).code == "context_changed"
    fresh = UpdateContext(operations=type(case.operations)())
    loaded = wire(
        fresh,
        {
            "command": "load",
            "vault": str(case.vault),
            "selection_id": "22222222-2222-4222-8222-222222222222",
        },
    )
    assert not loaded.ready and loaded.binding is None and loaded.history_retained
    resumed = wire(
        fresh,
        {
            "command": "resume",
            "vault": str(case.vault),
            "selection_id": "22222222-2222-4222-8222-222222222222",
        },
    )
    assert resumed.binding is not None and resumed.binding.checkpoint_commit == "c" * 40
    assert resumed.binding.context_id != saved.binding.context_id
    assert resumed.unresolved == 1 and resumed.kind == "attachment_cleanup"
    assert context.page(resumed.binding).code == "context_changed"
    assert {
        path: (case.vault / path).read_bytes() for path in case.current
    } == case.current
    page = wire(context, {"command": "page", "binding": saved.binding, "byte_limit": 0})
    change = next(row for row in page.page.items if row.item_id == "remove-asset")
    offer = next(row for row in page.offers if row.change_id == change.change_id)
    references = wire(
        context,
        {
            "command": "references",
            "binding": saved.binding,
            "requirement_id": offer.requirement_id,
        },
    ).references
    ready = wire(
        context,
        {
            "command": "choose",
            "binding": saved.binding,
            "requirement_id": offer.requirement_id,
            "choice": "remove",
            "assumptions_digest": offer.assumptions_digest,
            "references": tuple(
                {"reference_id": row.reference_id, "choice": "drop"}
                for row in references
            ),
        },
    )
    assert ready.ready and sessions[context].update_snapshot.ready
    case.history.checkpoint.locator = case.history.checkpoint.locator.model_copy(
        update={"commit": "d" * 40, "generation": 4}
    )
    refused = wire(context, {"command": "page", "binding": ready.binding})
    assert refused.code == "association_or_history_changed" and not refused.ready
    assert refused.binding is None and refused.page is None
    assert refused.next_actions == ("inspect_history",)
    snapshot = sessions[context].update_snapshot
    assert snapshot.needs_inspection and snapshot.binding is None and not snapshot.ready
    assert (
        worker_context_call(
            context, {"command": "apply", "binding": ready.binding}
        ).code
        == "context_changed"
    )
    continued = wire(
        context, {"command": "close", "binding": None, "choice": "continue"}
    )
    assert (
        not continued.ready
        and continued.binding is None
        and continued.next_actions == ("inspect_history",)
    )
    assert captured == [True]


def test_refused_unresolved_apply_retains_unsaved_review_for_explicit_save(tmp_path):
    context, case = context_case(tmp_path)
    opened = context.prepare(
        case.vault,
        selection_id="11111111-1111-4111-8111-111111111111",
        kind="attachment_cleanup",
    )
    result = context.apply(opened.binding)
    assert result.code == "review_not_ready" and not result.ready
    assert result.binding is not None
    assert result.binding.revision > opened.binding.revision
    assert context.page(opened.binding).code == "context_changed"
    assert context.page(result.binding, byte_limit=0).status == "available"
    assert "save_update" in result.next_actions
    assert {
        path: (case.vault / path).read_bytes() for path in case.current
    } == case.current


def test_lost_native_reply_retires_context_and_requires_history_inspection(
    tmp_path, monkeypatch
):
    context, case = context_case(tmp_path)
    opened = context.prepare(
        case.vault,
        selection_id="11111111-1111-4111-8111-111111111111",
        kind="attachment_cleanup",
    )
    page, binding = context.page(opened.binding, byte_limit=0), opened.binding
    for item, choice in (("keep-asset", "current"), ("remove-asset", "remove")):
        change = next(row for row in page.page.items if row.item_id == item)
        offer = next(row for row in page.offers if row.change_id == change.change_id)
        refs = (
            context.reference_page(
                binding, requirement_id=offer.requirement_id
            ).references
            if choice == "remove"
            else ()
        )
        result = context.choose(
            binding,
            requirement_id=offer.requirement_id,
            choice=choice,
            assumptions_digest=offer.assumptions_digest,
            references=tuple(
                {"reference_id": row.reference_id, "choice": "drop"} for row in refs
            ),
        )
        assert result.code == "accepted"
        binding = result.binding
    assert result.ready
    case.history.checkpoint.manifest.vault = case.history.admission.inventory
    contacted = []

    def lost_reply(self, *args, **kwargs):
        contacted.append(True)
        raise OSError("Synthetic loss after native contact")

    monkeypatch.setattr(type(case.operations), "apply_reviewed_update", lost_reply)
    unknown = context.apply(binding)
    assert contacted == [True]
    assert unknown.status == "publication_unknown" and unknown.publication == "unknown"
    assert unknown.binding is None and not unknown.ready
    assert unknown.operation is None
    assert unknown.next_actions == ("inspect_update_status",)
    assert context.page(binding).code == "context_changed"
    assert {
        path: (case.vault / path).read_bytes() for path in case.current
    } == case.current


def test_chunked_edit_handle_binds_exact_large_bytes_without_a_candidate_on_wire(
    tmp_path, monkeypatch
):
    import hashlib
    from uuid import uuid4

    from brz2obsidian.application.update_context import UpdateContext
    from tests.application.test_format_transition import transition_case
    from tests.support.recorded_format6 import CURRENT, FIXTURE, NOTE

    operations, vault, history = transition_case(tmp_path, monkeypatch)
    monkeypatch.setattr(
        operations,
        "read_checkpoint",
        lambda *_args, **_kwargs: SimpleNamespace(
            **(vars(history.checkpoint) | {"status": "valid"})
        ),
    )
    context = UpdateContext(operations=operations)
    opened = context.prepare(
        vault,
        selection_id=str(uuid4()),
        kind="format_transition",
        source=FIXTURE / "source.brz",
    )
    assert opened.binding is not None
    page = context.page(opened.binding, byte_limit=0)
    assert page.status == "available", page.code
    assert page.configuration is not None
    current_config = {
        row.current_path: (vault / row.current_path).read_bytes()
        for row in page.page.items
        if row.current_path.startswith(".obsidian/")
    }
    assert len(current_config) == page.configuration.member_count
    cfg = worker_context_call(
        context,
        {
            "command": "choose_configuration",
            "binding": opened.binding,
            "group_id": page.configuration.group_id,
            "choice": "current",
        },
    )
    assert cfg.code == "accepted" and not cfg.ready
    assert context.page(cfg.binding, byte_limit=0).configuration.selected == "current"
    page = context.page(cfg.binding, byte_limit=0)
    index, note = next(
        (number, row)
        for number, row in enumerate(page.page.items)
        if row.current_path == NOTE
    )
    offer = next(row for row in page.offers if row.change_id == note.change_id)
    assert "edited" in offer.choices
    edited = CURRENT + b"\r\nReviewed bounded edit.\r\n" + b"x" * (270 * 1024)
    assert len(edited) > 256 * 1024
    draft = worker_context_call(
        context,
        {
            "command": "begin_edit",
            "binding": cfg.binding,
            "requirement_id": offer.requirement_id,
            "size": len(edited),
            "sha256": hashlib.sha256(edited).hexdigest(),
        },
    )
    assert draft.edit is not None and not draft.edit.sealed
    assert draft.edit.handle.binding.revision > opened.binding.revision
    handle = draft.edit.handle
    assert (
        context.write_edit(handle, offset=1, data=b"foreign gap").code
        == "edit_offset_changed"
    )
    assert (
        context.choose(
            draft.binding,
            requirement_id=offer.requirement_id,
            choice="edited",
            assumptions_digest=offer.assumptions_digest,
            edit_handle=handle,
        ).code
        == "edit_unsealed"
    )
    assert context.save(draft.binding).code == "uncommitted_draft"
    for offset in range(0, len(edited), 32768):
        part = edited[offset : offset + 32768]
        written = worker_context_call(
            context,
            {"command": "write_edit", "handle": handle, "offset": offset, "data": part},
        )
        assert written.edit.received_bytes == offset + len(part)
        assert "Reviewed bounded edit" not in written.model_dump_json()
    sealed = worker_context_call(context, {"command": "seal_edit", "handle": handle})
    assert sealed.edit.sealed and sealed.edit.received_bytes == len(edited)
    accepted = worker_context_call(
        context,
        {
            "command": "choose",
            "binding": sealed.binding,
            "requirement_id": offer.requirement_id,
            "choice": "edited",
            "assumptions_digest": offer.assumptions_digest,
            "edit_handle": handle,
        },
    )
    assert (
        accepted.code == "accepted"
        and accepted.binding.revision > sealed.binding.revision
    )
    assert (
        context.page(accepted.binding, byte_limit=0).configuration.selected == "current"
    )
    all_rows = context.page(accepted.binding, byte_limit=0).page.items
    for position, comparison in enumerate(all_rows):
        if comparison.current_path in current_config:
            shown = context.page(
                accepted.binding, offset=position, limit=1, byte_limit=65536
            )
            assert shown.page.items[0].result == current_config[comparison.current_path]
    result = bytearray()
    byte_offset = 0
    while True:
        shown = context.page(
            accepted.binding,
            offset=index,
            limit=1,
            byte_offset=byte_offset,
            byte_limit=65536,
        )
        row = shown.page.items[0]
        result.extend(row.result)
        if row.next_byte_offset is None:
            break
        assert row.next_byte_offset > byte_offset
        byte_offset = row.next_byte_offset
    assert bytes(result) == edited
    assert (
        context.write_edit(handle, offset=len(edited), data=b"late").code
        == "edit_changed"
    )
    assert (vault / NOTE).read_bytes() == CURRENT


def test_explicit_close_preserves_pending_edit_or_discards_only_its_owned_file(
    tmp_path, monkeypatch
):
    import hashlib
    import tempfile
    from uuid import uuid4

    from brz2obsidian.application.update_context import UpdateContext
    from tests.application.test_format_transition import transition_case
    from tests.support.recorded_format6 import FIXTURE, NOTE

    operations, vault, history = transition_case(tmp_path, monkeypatch)
    monkeypatch.setattr(
        operations,
        "read_checkpoint",
        lambda *_args, **_kwargs: SimpleNamespace(
            **(vars(history.checkpoint) | {"status": "valid"})
        ),
    )
    context = UpdateContext(operations=operations)
    opened = context.prepare(
        vault,
        selection_id=str(uuid4()),
        kind="format_transition",
        source=FIXTURE / "source.brz",
    )
    page = context.page(opened.binding, byte_limit=0)
    assert page.status == "available"
    note = next(row for row in page.page.items if row.current_path == NOTE)
    offer = next(row for row in page.offers if row.change_id == note.change_id)
    before = {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }
    actual_file = tempfile.TemporaryFile
    created = []

    def owned_file(*args, **kwargs):
        result = actual_file(*args, **kwargs)
        created.append(result)
        return result

    monkeypatch.setattr(tempfile, "TemporaryFile", owned_file)
    draft = context.begin_edit(
        opened.binding,
        requirement_id=offer.requirement_id,
        size=1,
        sha256=hashlib.sha256(b"x").hexdigest(),
    )
    assert draft.edit is not None and len(created) == 1 and not created[0].closed
    continuing = context.close(draft.binding, choice="continue")
    assert continuing.code == "continue_review" and continuing.binding == draft.binding
    assert not created[0].closed
    assert context.close(draft.binding, choice="save").code == "uncommitted_draft"
    assert (
        context.prepare(
            vault,
            selection_id=str(uuid4()),
            kind="format_transition",
            source=FIXTURE / "source.brz",
        ).code
        == "close_decision_required"
    )
    assert (
        context.load(vault, selection_id=str(uuid4())).code == "close_decision_required"
    )
    assert (
        context.resume(vault, selection_id=str(uuid4())).code
        == "close_decision_required"
    )
    assert not created[0].closed
    local = worker_context_call(
        context, {"command": "discard_draft", "binding": draft.binding}
    )
    assert local.code == "draft_discarded" and local.binding is not None
    assert local.binding.proposal_id == draft.binding.proposal_id
    assert local.binding.generation == draft.binding.generation
    assert created[0].closed
    assert (
        context.write_edit(draft.edit.handle, offset=0, data=b"x").code
        == "edit_changed"
    )
    draft = context.begin_edit(
        local.binding,
        requirement_id=offer.requirement_id,
        size=1,
        sha256=hashlib.sha256(b"x").hexdigest(),
    )
    assert len(created) == 2 and not created[1].closed
    discarded = context.close(draft.binding, choice="discard")
    assert discarded.code == "context_closed" and discarded.binding is None
    assert discarded.history_retained and discarded.checkpoint_commit == "b" * 40
    assert all(file.closed for file in created)
    assert context.page(draft.binding).code == "context_changed"
    cancelled = context.prepare(
        vault / "another-vault",
        selection_id=str(uuid4()),
        kind="onboarding",
        cancel=lambda: True,
    )
    assert cancelled.status == "cancelled_before_publication"
    closed = context.close(choice="discard")
    assert closed.kind == "onboarding" and not closed.history_retained
    assert closed.checkpoint_commit is None
    assert {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    } == before


def test_discarding_reference_draft_keeps_review_and_independent_approval(tmp_path):
    context, case = context_case(tmp_path)
    opened = context.prepare(
        case.vault,
        selection_id="11111111-1111-4111-8111-111111111111",
        kind="attachment_cleanup",
    )
    page = context.page(opened.binding, byte_limit=0)
    keep = next(row for row in page.page.items if row.item_id == "keep-asset")
    offered = next(row for row in page.offers if row.change_id == keep.change_id)
    accepted = context.choose(
        opened.binding,
        requirement_id=offered.requirement_id,
        choice="current",
        assumptions_digest=offered.assumptions_digest,
    )
    stable = context.page(accepted.binding, byte_limit=0)
    independent = next(row for row in stable.offers if row.change_id == keep.change_id)
    remove = next(row for row in stable.page.items if row.item_id == "remove-asset")
    requirement = next(
        row for row in stable.offers if row.change_id == remove.change_id
    )
    reference = context.reference_page(
        accepted.binding, requirement_id=requirement.requirement_id, limit=1
    ).references[0]
    staged = worker_context_call(
        context,
        {
            "command": "stage_references",
            "binding": accepted.binding,
            "requirement_id": requirement.requirement_id,
            "choices": ({"reference_id": reference.reference_id, "choice": "drop"},),
        },
    )
    assert staged.draft_pending and not staged.ready
    discarded = worker_context_call(
        context, {"command": "discard_draft", "binding": staged.binding}
    )
    assert discarded.code == "draft_discarded" and not discarded.draft_pending
    assert discarded.binding.proposal_id == accepted.binding.proposal_id
    assert discarded.binding.generation == accepted.binding.generation
    again = context.page(discarded.binding, byte_limit=0)
    assert (
        next(row for row in again.offers if row.change_id == keep.change_id)
        == independent
    )
    assert all(
        row.selected is None
        for row in context.reference_page(
            discarded.binding, requirement_id=requirement.requirement_id
        ).references
    )
    assert {
        path: (case.vault / path).read_bytes() for path in case.current
    } == case.current


def test_rechoosing_an_approved_row_keeps_the_other_decision_and_blocks_old_ready_apply(
    tmp_path,
):
    from uuid import uuid4

    context, case = context_case(tmp_path)
    result = context.prepare(
        case.vault, selection_id=str(uuid4()), kind="attachment_cleanup"
    )
    for item in ("keep-asset", "remove-asset"):
        page = context.page(result.binding, byte_limit=0)
        change = next(row for row in page.page.items if row.item_id == item)
        offered = next(row for row in page.offers if row.change_id == change.change_id)
        result = context.choose(
            result.binding,
            requirement_id=offered.requirement_id,
            choice="current",
            assumptions_digest=offered.assumptions_digest,
        )
        assert result.code == "accepted"
    assert result.ready
    before = context.page(result.binding, byte_limit=0)
    keep_change = next(row for row in before.page.items if row.item_id == "keep-asset")
    other_change = next(
        row for row in before.page.items if row.item_id == "remove-asset"
    )
    revisited = next(
        row for row in before.offers if row.change_id == keep_change.change_id
    )
    independent = next(
        row for row in before.offers if row.change_id == other_change.change_id
    )
    assert revisited.selected == independent.selected == "current"
    assert revisited.decision_id and independent.decision_id
    references = context.reference_page(
        result.binding, requirement_id=revisited.requirement_id
    )
    assert references.references
    draft = context.stage_references(
        result.binding,
        requirement_id=revisited.requirement_id,
        choices=tuple(
            {"reference_id": row.reference_id, "choice": "drop"}
            for row in references.references
        ),
    )
    assert context.apply(draft.binding).code == "uncommitted_draft"
    changed = context.choose(
        draft.binding,
        requirement_id=revisited.requirement_id,
        choice="remove",
        assumptions_digest=revisited.assumptions_digest,
    )
    assert changed.code == "accepted" and changed.ready
    assert changed.binding.proposal_id == result.binding.proposal_id
    assert changed.binding.generation == result.binding.generation
    after = context.page(changed.binding, byte_limit=0)
    kept = next(row for row in after.offers if row.change_id == independent.change_id)
    replaced = next(row for row in after.offers if row.change_id == revisited.change_id)
    assert kept.decision_id == independent.decision_id and kept.selected == "current"
    assert (
        replaced.decision_id != revisited.decision_id and replaced.selected == "remove"
    )
    assert {
        path: (case.vault / path).read_bytes() for path in case.current
    } == case.current
