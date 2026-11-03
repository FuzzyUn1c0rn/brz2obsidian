"""Binary review exposes only actual offered output metadata to its consumers."""

from hashlib import sha256

import pytest

from brz2obsidian.application.checkpoint_contracts import CheckpointRead
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_offers import choice_detail_page, choice_offers
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.update_contracts import UpdateResult
from tests.application.test_update_context import worker_context_call
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_attachments import attachment_request
from tests.reconciliation.test_identity import inventory_item
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, with_review_links


def test_binary_output_details_page_actual_alternatives_without_references():
    prepared = preparation(attachment_request())
    original = prepared.model_dump_json()
    offer = next(row for row in choice_offers(prepared) if row.domain == "attachment")
    assert offer.choices == ("current", "incoming", "both")
    # These literal output expectations come from the canonical binary fixture:
    # current bytes stay at their path; the already offered Both allocation is
    # distinct. No link occurrence is needed to inspect those alternatives.
    assert prepared.review.producer_facts.link_context.current_documents == ()
    assert offer.detail_count == 4
    details = []
    for offset in (0, 2):
        rows, total, following = choice_detail_page(
            prepared, requirement_id=offer.requirement_id, offset=offset, limit=2
        )
        assert total == 4 and len(rows) == 2
        assert following == (2 if offset == 0 else None)
        details.extend(rows)
    current_hash = sha256(b"\x00authored").hexdigest()
    incoming_hash = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    secondary = "Assets/data (incoming-ba7816bf).bin"
    assert [
        (row.kind, row.choice, row.target_id, row.path, row.size, row.sha256)
        for row in details
    ] == [
        (
            "attachment_output",
            "current",
            "resource:payload",
            "Assets/data.bin",
            9,
            current_hash,
        ),
        (
            "attachment_output",
            "incoming",
            "resource:payload",
            "Assets/data.bin",
            3,
            incoming_hash,
        ),
        (
            "attachment_output",
            "both",
            "resource:payload",
            "Assets/data.bin",
            9,
            current_hash,
        ),
        (
            "attachment_output",
            "both",
            "resource:payload:incoming:" + incoming_hash,
            secondary,
            3,
            incoming_hash,
        ),
    ]
    assert secondary not in {row.path for row in prepared.review.facts.subjects}
    assert all(not hasattr(row, "content") for row in details)
    assert prepared.model_dump_json() == original


@pytest.mark.parametrize("state", ("offered", "declined"))
def test_bound_rename_alternatives_identify_current_and_source_before_acceptance(
    tmp_path,
    state,
):
    facts = request(
        current=b"Authored current body.\n", incoming=b"Changed source body.\n"
    )
    moved = inventory_item(
        "moved-opening",
        "entry:opening",
        "Authored/Opening.md",
        b"Authored current body.\n",
    )
    facts = with_review_links(
        facts.model_copy(
            update={
                "subjects": (
                    facts.subjects[0].model_copy(update={"current": moved.current}),
                ),
                "identity_inventory": (moved,),
            }
        )
    )
    vault = tmp_path / "vault"
    vault.mkdir()
    prepared = preparation(facts).model_copy(update={"vault": str(vault)})
    if state == "declined":
        kept = Operations().resolve_update(
            prepared,
            action(prepared.review, domain="rename", choice="keep_path"),
        )
        assert kept.code == "accepted"
        prepared = kept.preparation
    (change,) = prepared.review.proposal.changes
    assert change.rename_review.status == state
    assert (change.path, change.target_path) == (
        "Authored/Opening.md",
        "Authored/Opening.md",
    )
    assert change.rename_review.source_path == "Notes/Opening.md"
    original = prepared.model_dump_json()

    class NativeInputs(Operations):
        # Actual Core plan; only the outer prepare/checkpoint observations vary.
        def prepare_update(self, path, source, **kwargs):
            assert path == str(vault)
            return UpdateResult(
                status="unresolved",
                code="prepared",
                preparation=prepared,
                changes=1,
                unresolved=1,
                history_retained=True,
                checkpoint_commit=prepared.locator.commit,
                next_actions=("resolve_update", "save_update"),
            )

        def read_checkpoint(self, path, **kwargs):
            return CheckpointRead(
                schema_id="brz2obsidian.checkpoint-read",
                schema_version=1,
                status="valid",
                code="valid",
                locator=prepared.locator,
                manifest=None,
                review=None,
                message="Controlled retained checkpoint",
            )

    context = UpdateContext(operations=NativeInputs())
    opened = worker_context_call(
        context,
        {
            "command": "prepare",
            "kind": "source_update",
            "vault": str(vault),
            "source": str(tmp_path / "incoming.brz"),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    result = worker_context_call(
        context,
        {
            "command": "choices",
            "binding": opened.binding,
            "offset": 0,
            "limit": 1,
        },
    )
    assert result.status == "available" and result.binding == opened.binding
    (offer,) = result.offers
    # The text action identifies the current file; the separate optional rename
    # action discloses both paths before and after declining the rename.
    assert offer.domain == "text" and offer.choices == ("current", "incoming", "edited")
    assert offer.disclosure == "Current file: Authored/Opening.md"
    assert not offer.detail_omitted
    assert offer.selected is None and offer.decision_id is None
    assert result.total_choices == 2 and result.next_choice_offset == 1

    rename_result = worker_context_call(
        context,
        {
            "command": "choices",
            "binding": opened.binding,
            "offset": 1,
            "limit": 1,
        },
    )
    assert rename_result.status == "available"
    assert rename_result.binding == opened.binding
    assert rename_result.total_choices == 2 and rename_result.next_choice_offset is None
    (rename,) = rename_result.offers
    assert rename.domain == "rename" and rename.choices == ("keep_path", "source_path")
    assert rename.disclosure == (
        "Current path: Authored/Opening.md\nProposed source path: Notes/Opening.md"
    )
    assert not rename.detail_omitted
    assert rename.selected == (None if state == "offered" else "keep_path")
    assert rename.decision_id == change.rename_review.decision_id
    assert (rename.decision_id is None) == (state == "offered")
    assert offer.change_id == rename.change_id == change.change_id
    assert offer.requirement_id != rename.requirement_id
    assert offer.assumptions_digest != rename.assumptions_digest
    assert (offer, rename) == choice_offers(prepared)
    assert prepared.model_dump_json() == original and not prepared.review.ready
    assert list(vault.iterdir()) == []
