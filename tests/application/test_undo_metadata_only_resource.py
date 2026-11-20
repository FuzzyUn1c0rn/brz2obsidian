"""Undo retains imported context and unrelated metadata without claiming writes."""

import json

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_facts import assemble_facts
from brz2obsidian.application.update_lifecycle import text_choice_action
from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
from tests.application.test_vault_checkpoints import fixture_case, git, user_state
from tests.application.test_vault_recovery_process import _assert_user_state
from tests.application.test_vault_undo import _operation_ref
from tests.reconciliation.test_resolution import action
from tests.reconciliation.test_type_tag_dependencies import graph_payload


def test_current8_undo_retains_unaffected_metadata_only_resource_without_fabricating_state():
    baseline = {
        name: raw.replace(b"[[A.svg]]", b"[[Attachments/A.svg]]")
        for name, raw in graph_payload().items()
    }
    incoming = dict(baseline)
    incoming["Categories/C.md"] = baseline["Categories/C.md"].replace(
        b"Original.", b"Incoming C."
    )
    current = dict(baseline)
    current["Attachments/A.svg"] = baseline["Attachments/A.svg"] + b"\n"
    vault, source = fixture_case()
    for directory in (vault, source):
        for name, raw in baseline.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    (vault / "Attachments/A.svg").write_bytes(current["Attachments/A.svg"])
    manual = vault / "Attachments/manual.bin"
    manual.write_bytes(b"\x00unrelated ordinary user attachment")
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "Retained unrelated binary")
    operations = Operations()
    observed = operations.inspect_history(vault)
    facts = assemble_facts(
        baseline,
        incoming,
        current,
        proposal_id="metadata-only-undo",
        generation=1,
        current_inventory=tuple(
            row
            for row in observed.admission.inventory
            if row.path == "Attachments/manual.bin"
        ),
    )
    target_id = "physical:Attachments/manual.bin"
    assert any(t.target_id == target_id for t in facts.link_context.current_targets)
    assert not any(
        s.target_id == target_id for s in facts.link_context.current_target_facts
    )
    captured = operations.capture_checkpoint(
        vault,
        source,
        vault_id="metadata-only-vault",
        import_id="metadata-only-import",
        identity=facts.incoming_identity,
        admission=observed.admission,
    )
    assert captured.status == "captured", captured.code
    (source / "Categories/C.md").write_bytes(incoming["Categories/C.md"])
    source_before = {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }
    plan = prepare_review(
        facts, preflight=operations.inspect_history(vault).admission.preflight
    )
    change = next(c for c in plan.proposal.changes if c.item_id == "category:C")
    chosen = resolve_review(
        plan,
        text_choice_action(plan, action(plan, change, choice="incoming")),
    )
    assert chosen.status == "accepted" and chosen.plan.ready, chosen.code
    applied = operations.apply_reviewed_update(
        vault,
        source,
        review=chosen.plan,
        source_binding=operations.observe_reviewed_source(source, chosen.plan),
        vault_id="metadata-only-vault",
        import_id="metadata-only-import",
    )
    assert applied.status == "applied" and applied.history == "terminal", applied.code
    later_image = current["Attachments/A.svg"] + b"<!-- Later authored SVG edit. -->\n"
    (vault / "Attachments/A.svg").write_bytes(later_image)
    user_before = user_state(vault)
    before = (
        manual.read_bytes(),
        git(vault, "rev-parse", "HEAD"),
        (vault / ".git/index").read_bytes(),
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)"),
        operations.read_checkpoint(vault).locator,
    )
    offered = operations.prepare_undo(vault)
    assert (
        offered.status == "offered"
        and offered.checkpoint_commit == applied.result_commit
    ), offered.code
    assert offered.checkpoint_commit == before[-1].commit
    assert offered.generation == before[-1].generation
    assert offered.target_receipt_commit == applied.receipt_commit
    context = offered.review.producer_facts.link_context
    original = next(
        t for t in facts.link_context.current_targets if t.target_id == target_id
    )
    for stage in ("current", "incoming"):
        assert (
            next(
                t
                for t in getattr(context, stage + "_targets")
                if t.target_id == target_id
            )
            == original
        )
        assert not any(
            s.target_id == target_id for s in getattr(context, stage + "_target_facts")
        )
        owned_image = next(
            state
            for state in getattr(context, stage + "_target_facts")
            if state.target_id == "subject:image:a:asset"
        )
        assert owned_image.existence == "present" and owned_image.content is not None
        assert owned_image.file_roles is not None and owned_image.file_roles.image_path
        assert owned_image.resource_origin is None
    assert not any(
        s.current.path == "Attachments/manual.bin"
        for s in offered.review.producer_facts.subjects
    )
    assert offered.review.facts.format_operation.automatic_merge
    assert offered.review.ready and offered.review.requirements == ()
    assert offered.review.actions == offered.review.approvals == ()
    retained = next(
        s for s in offered.review.producer_facts.subjects if s.item_id == "image:a"
    )
    assert retained.current.content.data == later_image
    assert (
        retained.baseline.content.data
        == retained.incoming.data
        == baseline["Attachments/A.svg"]
    )
    assert retained.baseline.content.data != retained.current.content.data
    assert retained.operation_reversal is None
    assert retained.attachment.retained_ownership is None
    effects = select_review_effects(offered.review)
    assert effects.status == "selected" and not effects.remove_paths
    assert [(row.path, row.content.data) for row in effects.files] == [
        ("Attachments/A.svg", later_image),
        ("Categories/C.md", baseline["Categories/C.md"]),
    ]
    assert (
        manual.read_bytes(),
        git(vault, "rev-parse", "HEAD"),
        (vault / ".git/index").read_bytes(),
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)"),
        operations.read_checkpoint(vault).locator,
    ) == before
    assert (vault / "Categories/C.md").read_bytes() == incoming["Categories/C.md"]
    assert {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    } == source_before

    from brz2obsidian.contracts import CurrentContent

    unknown = CurrentContent(
        existence="unknown", path=retained.current.path, content=None
    )
    incomplete = offered.review.producer_facts.model_copy(
        update={
            "subjects": tuple(
                s.model_copy(update={"current": unknown})
                if s.item_id == retained.item_id
                else s
                for s in offered.review.producer_facts.subjects
            ),
            "identity_inventory": tuple(
                row.model_copy(update={"current": unknown})
                if row.current.path == retained.current.path
                else row
                for row in offered.review.producer_facts.identity_inventory
            ),
            "link_context": context.model_copy(
                update={
                    "current_target_facts": tuple(
                        state.model_copy(
                            update={
                                "existence": "unknown",
                                "content": None,
                                "structure": None,
                                "file_roles": None,
                            }
                        )
                        if state.target_id == "subject:image:a:asset"
                        else state
                        for state in context.current_target_facts
                    )
                }
            ),
        }
    )
    refused = prepare_review(incomplete, preflight=offered.review.preflight)
    assert not refused.ready and select_review_effects(refused).status == "refused"

    from brz2obsidian.contracts import (
        AttachmentCandidate,
        AttachmentSelection,
        LinkOccurrenceChoice,
    )
    from brz2obsidian.core import validate_attachment_candidate
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    asset_change = next(
        c for c in offered.review.proposal.changes if c.item_id == retained.item_id
    )
    alternative = next(
        row
        for row in asset_change.attachment_review.alternatives
        if row.choice == "incoming"
    )
    assert alternative.eligible and len(alternative.outputs) == 1
    output = alternative.outputs[0]
    states = tuple(
        s for s in context.current_target_facts if s.target_id != output.target_id
    ) + (
        interpret_link_target(
            output.content,
            target_id=output.target_id,
            existence="present",
            memberships=(),
            membership_targets=context.current_targets,
            source_path=output.path,
            output_format=8,
            qualify_roles=True,
        ),
    )
    documents = tuple(
        interpret_links(
            doc.content,
            document_id=doc.document_id,
            source_path=doc.source_path,
            path_mode=doc.path_mode,
            targets=context.current_targets,
            target_facts=states,
            inventory="complete",
            output_format=8,
            record_format=8,
        )
        for doc in context.current_documents
    )
    links = []
    for link in asset_change.attachment_review.links:
        old_doc = next(
            doc
            for doc in context.current_documents
            if doc.document_id == link.document_id
        )
        new_doc = next(doc for doc in documents if doc.document_id == link.document_id)
        old = next(
            o for o in old_doc.occurrences if o.occurrence_id == link.occurrence_id
        )
        new = next(
            o for o in new_doc.occurrences if o.occurrence_id == link.occurrence_id
        )
        links.append(
            LinkOccurrenceChoice(
                document_id=link.document_id,
                occurrence_id=link.occurrence_id,
                old=old.meaning,
                replacement=old.raw,
                selected=new.meaning,
                expected_memberships=(),
                provenance="explicit_user",
            )
        )
    selection = AttachmentSelection(
        schema_id="brz2obsidian.attachment-selection",
        schema_version=1,
        proposal_id=offered.review.proposal.proposal_id,
        generation=offered.review.proposal.generation,
        item_id=retained.item_id,
        facet=retained.facet,
        reviewed_change_id=asset_change.change_id,
        reviewed_assumptions=asset_change.assumptions,
        choice="incoming",
        link_choices=tuple(links),
        provenance="explicit_user",
    )
    candidate = AttachmentCandidate(
        schema_id="brz2obsidian.attachment-candidate",
        schema_version=1,
        outputs=alternative.outputs,
        documents=documents,
        targets=context.current_targets,
        target_facts=states,
    )
    assert validate_attachment_candidate(
        offered.review.producer_facts, selection, candidate
    ).valid
    incoming_action = action(
        offered.review,
        asset_change,
        domain="attachment",
        choice="incoming",
        attachment_selection=selection,
        attachment_candidate=candidate,
        decision_id="attempt-context-write",
    )
    extra_write = operations.resolve_undo(vault, offered, incoming_action)
    assert extra_write.status == "offered" and extra_write.review.ready, (
        extra_write.code
    )
    assert (
        next(
            row.content.data
            for row in select_review_effects(extra_write.review).files
            if row.path == retained.path
        )
        == baseline["Attachments/A.svg"]
    )
    before_refusal = user_state(vault)
    denied = operations.execute_undo(vault, extra_write)
    assert denied.code == "undo_effect_outside_origin"
    assert denied.status == "refused" and not denied.authored_files_changed, denied.code
    assert (
        denied.publication in ("not_started", "not_published")
        and denied.intent_commit is None
    )
    assert user_state(vault) == before_refusal
    assert operations.read_checkpoint(vault).locator == before[-1]

    undone = operations.execute_undo(vault, offered)
    assert undone.status == "undone" and undone.publication == "complete", undone.code
    intent = json.loads(
        git(vault, "cat-file", "blob", undone.intent_commit + ":intent.json")
    )
    assert intent["affected_paths"] == ["Categories/C.md"]
    assert (vault / "Attachments/A.svg").read_bytes() == later_image
    assert manual.read_bytes() == b"\x00unrelated ordinary user attachment"
    assert (vault / "Categories/C.md").read_bytes() == baseline["Categories/C.md"]
    allowed = {
        before[-1].association.ref.encode(),
        _operation_ref(before[-1].association.ref, undone.operation_id),
    }
    _assert_user_state(user_before, user_state(vault), allowed_refs=allowed)
    assert {
        p.relative_to(source).as_posix(): p.read_bytes()
        for p in source.rglob("*")
        if p.is_file()
    } == source_before
