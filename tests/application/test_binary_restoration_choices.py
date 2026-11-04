"""Binary restoration public verbs compile to the existing preservation choices."""

import json

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_offers import choice_offers
from brz2obsidian.application.update_facts import assemble_facts
from brz2obsidian.core import select_review_effects
from tests.application.test_update_lifecycle_admission import payload
from tests.application.test_update_lifecycle_contracts import preparation

PATH = "Assets/new.bin"
PAYLOAD = b"\x00new-source\xff"


def binary_restoration_preparation():
    baseline = payload("a", "Unchanged note.")
    incoming = payload("b", "Unchanged note.")
    record = json.loads(incoming["migration-record.json"])
    record["asset_targets"] = [
        {"asset_id": "new-asset", "relative_path": "Assets/new.bin"}
    ]
    incoming["migration-record.json"] = json.dumps(record).encode()
    incoming[PATH] = PAYLOAD
    facts = assemble_facts(
        baseline,
        incoming,
        dict(baseline),
        proposal_id="review:public-binary-restoration",
        generation=1,
    )
    return preparation(facts)


def approve_metadata(prepared):
    group = next(
        row for row in choice_offers(prepared) if row.domain == "compatible_group"
    )
    result = Operations().resolve_update_choice(
        prepared,
        requirement_id=group.requirement_id,
        choice="approve",
        assumptions_digest=group.assumptions_digest,
    )
    assert result.code == "accepted", result.code
    return result.preparation


@pytest.mark.parametrize("choice", ("restore_incoming", "decline_restoration"))
def test_public_binary_restoration_uses_offered_verbs(choice):
    prepared = binary_restoration_preparation()
    change = next(
        c for c in prepared.review.proposal.changes if c.item_id == "new-asset"
    )
    assert change.disposition == "restoration" and change.current is None
    assert change.target_path == "Assets/new.bin"
    assert change.attachment_review is not None and not prepared.review.ready
    prepared = approve_metadata(prepared)
    retained = prepared.review.approvals
    assert len(retained) == 1 and retained[0].target_path == "migration-record.json"
    assert not prepared.review.ready and len(prepared.review.requirements) == 1
    offer = next(row for row in choice_offers(prepared) if row.domain == "restoration")
    assert offer.change_id == change.change_id
    assert offer.choices == ("decline_restoration", "restore_incoming")
    result = Operations().resolve_update_choice(
        prepared,
        requirement_id=offer.requirement_id,
        choice=choice,
        assumptions_digest=offer.assumptions_digest,
    )
    assert result.code == "accepted" and result.ready, result.code
    assert result.publication == "not_started" and result.application is None
    plan = result.preparation.review
    assert plan.approvals[:-1] == retained
    approval, action = plan.approvals[-1], plan.actions[-1]
    assert approval.domain == action.domain == "restoration"
    assert approval.choice == action.choice == choice
    assert approval.target_path == "Assets/new.bin"
    effects = select_review_effects(plan)
    assert effects.status == "selected", effects.code
    files = {row.path: row.content.data for row in effects.files}
    assert files["migration-record.json"] == retained[0].result.data
    assert effects.remove_paths == ()
    if choice == "restore_incoming":
        assert approval.result.data == files["Assets/new.bin"] == b"\x00new-source\xff"
        assert approval.source_accepted and approval.source_memory is None
        assert action.attachment_selection.choice == "incoming"
        assert action.attachment_selection.item_id == "new-asset"
        assert action.attachment_selection.facet == "asset"
        assert [
            (row.target_id, row.path, row.content.data)
            for row in action.attachment_candidate.outputs
        ] == [("subject:new-asset:asset", "Assets/new.bin", b"\x00new-source\xff")]
    else:
        assert approval.result is None and not approval.source_accepted
        assert approval.source_memory.choice == "decline_restoration"
        assert approval.source_memory.reviewed_incoming.data == b"\x00new-source\xff"
        assert action.attachment_selection is action.attachment_candidate is None
        assert "Assets/new.bin" not in files


def test_closed_binary_restoration_refuses_wrong_handles_then_replaces_decline(
    tmp_path,
):
    from uuid import uuid4

    from brz2obsidian.application.checkpoint_contracts import CheckpointRead
    from brz2obsidian.application.update_context import UpdateContext
    from brz2obsidian.application.update_contracts import UpdateResult
    from tests.application.test_update_context import worker_context_call

    vault = tmp_path / "vault"
    vault.mkdir()
    prepared = approve_metadata(binary_restoration_preparation()).model_copy(
        update={"vault": str(vault)}
    )
    metadata = prepared.review.approvals[0].result.data

    class Inputs(Operations):
        def prepare_update(self, *args, **kwargs):
            return UpdateResult(
                status="unresolved",
                code="prepared",
                preparation=prepared,
                changes=len(prepared.review.proposal.changes),
                unresolved=1,
                history_retained=True,
                checkpoint_commit=prepared.locator.commit,
            )

        def read_checkpoint(self, path, **kwargs):
            assert path == str(vault)
            return CheckpointRead(
                schema_id="brz2obsidian.checkpoint-read",
                schema_version=1,
                status="valid",
                code="controlled_current",
                locator=prepared.locator,
                manifest=None,
                review=None,
                message="Controlled current checkpoint",
            )

        def capture_checkpoint(self, *args, **kwargs):
            raise AssertionError("Review must not Save automatically")

        def apply_reviewed_update(self, *args, **kwargs):
            raise AssertionError("Review must not publish automatically")

    producer = UpdateContext(operations=Inputs())
    opened = worker_context_call(
        producer,
        {
            "command": "prepare",
            "kind": "source_update",
            "vault": str(vault),
            "source": str(tmp_path / "controlled.brz"),
            "selection_id": str(uuid4()),
        },
    )
    assert opened.binding is not None and not opened.ready and opened.unresolved == 1
    before = worker_context_call(
        producer, {"command": "page", "binding": opened.binding}
    )
    offer = next(row for row in before.offers if row.domain == "restoration")
    assert next(
        row for row in offer.unavailable_choices if row.choice == "incoming"
    ).reasons == ("choice_not_admitted",)
    arguments = {
        "command": "choose",
        "binding": opened.binding,
        "requirement_id": offer.requirement_id,
        "choice": "restore_incoming",
        "assumptions_digest": offer.assumptions_digest,
    }
    for changed, expected in (
        (
            {
                "binding": opened.binding.model_copy(
                    update={"selection_id": str(uuid4())}
                )
            },
            "context_changed",
        ),
        ({"assumptions_digest": "0" * 64}, "offer_changed"),
        ({"choice": "incoming"}, "offer_changed"),
    ):
        refused = worker_context_call(producer, arguments | changed)
        assert refused.code == expected and not refused.ready
        unchanged = worker_context_call(
            producer, {"command": "page", "binding": opened.binding}
        )
        assert unchanged.page == before.page
    declined = worker_context_call(
        producer, arguments | {"choice": "decline_restoration"}
    )
    assert declined.code == "accepted" and declined.ready and declined.unresolved == 0
    stale = worker_context_call(producer, arguments)
    assert stale.code == "context_changed" and not stale.ready
    page = worker_context_call(
        producer, {"command": "page", "binding": declined.binding}
    )
    asset = next(row for row in page.page.items if row.item_id == "new-asset")
    assert (
        asset.current is asset.result is None
        and asset.incoming == b"\x00new-source\xff"
    )
    offer = next(row for row in page.offers if row.domain == "restoration")
    assert offer.selected == "decline_restoration"
    restored = worker_context_call(
        producer,
        arguments
        | {
            "binding": declined.binding,
            "requirement_id": offer.requirement_id,
            "assumptions_digest": offer.assumptions_digest,
        },
    )
    assert restored.code == "accepted" and restored.ready and restored.unresolved == 0
    page = worker_context_call(
        producer, {"command": "page", "binding": restored.binding}
    )
    asset = next(row for row in page.page.items if row.item_id == "new-asset")
    assert asset.current is asset.result is None
    assert asset.incoming == b"\x00new-source\xff"
    assert asset.current_path == "Assets/new.bin"
    assert (
        next(
            row
            for row in page.page.items
            if row.current_path == "migration-record.json"
        ).result
        == metadata
    )
    assert (
        next(row for row in page.offers if row.domain == "restoration").selected
        == "restore_incoming"
    )
    assert restored.publication == "not_started" and list(vault.iterdir()) == []


def test_unsafe_observed_binary_destination_has_no_admitted_restore():
    prepared = binary_restoration_preparation()
    original = next(
        row for row in choice_offers(prepared) if row.domain == "restoration"
    )
    facts = prepared.review.facts
    asset = next(row for row in facts.subjects if row.item_id == "new-asset")
    outside = asset.source_target.model_copy(
        update={"status": "unsafe", "containment": "outside"}
    )
    context = facts.link_context
    facts = facts.model_copy(
        update={
            "subjects": tuple(
                row.model_copy(update={"source_target": outside})
                if row.item_id == "new-asset"
                else row
                for row in facts.subjects
            ),
            "identity_inventory": tuple(
                row.model_copy(update={"target": outside})
                if row.identity is not None and row.identity.item_id == "new-asset"
                else row
                for row in facts.identity_inventory
            ),
            "link_context": context.model_copy(
                update={
                    key: tuple(
                        row.model_copy(update={"target": outside, "status": "unsafe"})
                        if row.target_id == "subject:new-asset:asset"
                        else row
                        for row in getattr(context, key)
                    )
                    for key in ("current_targets", "incoming_targets")
                }
            ),
        }
    )
    blocked = preparation(facts)
    assert any(
        row.code == "unsafe_identity_target" for row in blocked.review.proposal.findings
    )
    assert not blocked.review.ready
    assert all("restore_incoming" not in row.choices for row in choice_offers(blocked))
    before = blocked.review.model_dump_json()
    with pytest.raises(ValueError, match="Review offer changed"):
        Operations().resolve_update_choice(
            blocked,
            requirement_id=original.requirement_id,
            choice="restore_incoming",
            assumptions_digest=original.assumptions_digest,
        )
    assert blocked.review.model_dump_json() == before
