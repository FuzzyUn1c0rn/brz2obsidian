"""The producer keeps unsaved shared reviews behind finite context handles."""

from types import SimpleNamespace

from tests.application.test_attachment_cleanup_application import literal_cleanup_case


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
    removed = context.choose(
        opened.binding,
        requirement_id=offer.requirement_id,
        choice="remove",
        assumptions_digest=offer.assumptions_digest,
        references=tuple(
            {"reference_id": row.reference_id, "choice": "drop"} for row in refs
        ),
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
    from brz2obsidian.application.update_context import UpdateContext
    from brz2obsidian.core import load_review, save_review

    context, case = context_case(tmp_path)
    captured = []

    def wire(producer, arguments):
        import io
        from uuid import uuid4

        from brz2obsidian.application.contracts import WorkerRequest
        from brz2obsidian.application.protocol import decode_request, encode_request
        from brz2obsidian.application.update_stream import WorkerStreamDecoder
        from brz2obsidian.application.update_worker import UpdateWorker

        output = io.BytesIO()
        request = WorkerRequest(
            request_id=str(uuid4()), operation="update", sequence=1, arguments=arguments
        )
        UpdateWorker(context=producer, output=output).handle(
            decode_request(encode_request(request))
        )
        decoder = WorkerStreamDecoder(request)
        terminal = None
        for frame in output.getvalue().splitlines(keepends=True):
            terminal = decoder.feed(frame)
        assert terminal is not None and terminal.protocol_error is None
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
    opened = context.prepare(
        case.vault,
        selection_id="11111111-1111-4111-8111-111111111111",
        kind="attachment_cleanup",
    )
    assert opened.binding.checkpoint_generation == 2
    page = context.page(opened.binding, byte_limit=0)
    change = next(row for row in page.page.items if row.item_id == "keep-asset")
    offer = next(row for row in page.offers if row.change_id == change.change_id)
    accepted = context.choose(
        opened.binding,
        requirement_id=offer.requirement_id,
        choice="current",
        assumptions_digest=offer.assumptions_digest,
    )
    saved = wire(context, {"command": "save", "binding": accepted.binding})
    assert captured == [True] and saved.code == "saved"
    assert saved.binding.checkpoint_commit == "c" * 40
    assert (
        saved.binding.checkpoint_generation == 3
        and saved.binding.revision > accepted.binding.revision
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
    assert unknown.next_actions == ("inspect_update_status",)
    assert context.page(binding).code == "context_changed"
    assert {
        path: (case.vault / path).read_bytes() for path in case.current
    } == case.current
