"""Public optional path choices retain their own domain and safe availability."""

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_offers import choice_offers
from brz2obsidian.contracts import ExactContent
from brz2obsidian.core import (
    prepare_review,
    refresh_review,
    resolve_review,
    select_review_effects,
    validate_review,
)
from brz2obsidian.obsidian import interpret_links
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_attachments import attachment_request, binary_context
from tests.reconciliation.test_identity import inventory_item, with_subjects
from tests.reconciliation.test_optional_rename_offers import moved_facts
from tests.reconciliation.test_refresh import two_items
from tests.reconciliation.test_resolution import action, preflight, with_review_links


def moved_attachment_facts():
    facts = attachment_request()
    current = facts.subjects[0].current.model_copy(update={"path": "Authored/data.bin"})
    slot = (
        facts.subjects[0]
        .attachment.allocation_candidates[0]
        .model_copy(
            update={
                "path": "Authored/data (incoming-ba7816bf).bin",
                "target": facts.subjects[0]
                .attachment.allocation_candidates[0]
                .target.model_copy(
                    update={"normalized_path": "authored/data (incoming-ba7816bf).bin"}
                ),
            }
        )
    )
    subject = facts.subjects[0].model_copy(
        update={
            "current": current,
            "attachment": facts.subjects[0].attachment.model_copy(
                update={"allocation_candidates": (slot,)}
            ),
        }
    )
    entry = facts.identity_inventory[0].model_copy(
        update={
            "current": current,
            "target": facts.identity_inventory[0].target.model_copy(
                update={"normalized_path": "authored/data.bin"}
            ),
        }
    )
    facts = with_subjects(facts, (subject,), (entry,))
    return facts.model_copy(update={"link_context": binary_context(facts)})


def test_public_binary_optional_rename_is_not_an_attachment_selection():
    prepared = preparation(moved_attachment_facts())
    offers = choice_offers(prepared)
    binary = next(row for row in offers if row.domain == "attachment")
    rename = next(row for row in offers if row.domain == "rename")
    assert binary.requirement_id != rename.requirement_id
    assert binary.choices == ("current", "incoming", "both")
    assert rename.choices == ("keep_path", "source_path")
    kept = Operations().resolve_update_choice(
        prepared,
        requirement_id=rename.requirement_id,
        choice="keep_path",
        assumptions_digest=rename.assumptions_digest,
    )
    assert kept.code == "accepted", kept.code
    assert not kept.ready and kept.unresolved == 1
    assert kept.preparation.review.approvals == ()
    assert kept.preparation.review.actions[-1].attachment_candidate is None
    assert (
        kept.preparation.review.proposal.changes[0].target_path == "Authored/data.bin"
    )
    offers = choice_offers(kept.preparation)
    assert next(row for row in offers if row.domain == "rename").selected == "keep_path"
    assert next(row for row in offers if row.domain == "attachment").selected is None
    assert (
        next(row for row in offers if row.domain == "rename").unavailable_choices == ()
    )
    assert not next(row for row in offers if row.domain == "rename").reference_review
    assert next(row for row in offers if row.domain == "attachment").reference_review


def test_colliding_optional_source_path_stays_disabled_after_keep_replacement():
    facts = moved_facts()
    collision = inventory_item(
        "other", "entry:other", "Notes/Opening.md", b"Unrelated existing bytes.\n"
    )
    # Interpret the complete actual collision inventory through the public fixture.
    facts = facts.model_copy(
        update={
            "identity_inventory": facts.identity_inventory + (collision,),
            "link_context": None,
        }
    )
    from tests.reconciliation.test_resolution import with_review_links

    facts = with_review_links(facts)
    plan = prepare_review(facts, preflight=preflight())
    (change,) = plan.proposal.changes
    assert change.rename_review.status == "blocked"
    assert not change.rename_review.requires_decision
    refused = resolve_review(plan, action(plan, domain="rename", choice="source_path"))
    assert refused.code == "unsafe_producer_choice" and refused.plan == plan
    prepared = preparation(facts)
    for step in ("initial", "declined"):
        offer = next(row for row in choice_offers(prepared) if row.domain == "rename")
        assert offer.choices == ("keep_path",), step
        assert [(row.choice, row.reasons) for row in offer.unavailable_choices] == [
            ("source_path", ("unsafe_producer_choice",))
        ]
        before = prepared.review.model_dump_json()
        with pytest.raises(ValueError, match="Review offer changed"):
            Operations().resolve_update_choice(
                prepared,
                requirement_id=offer.requirement_id,
                choice="source_path",
                assumptions_digest=offer.assumptions_digest,
            )
        assert prepared.review.model_dump_json() == before
        if step == "initial":
            kept = Operations().resolve_update_choice(
                prepared,
                requirement_id=offer.requirement_id,
                choice="keep_path",
                assumptions_digest=offer.assumptions_digest,
            )
            assert kept.code == "accepted", kept.code
            prepared = kept.preparation
            assert (
                prepared.review.proposal.changes[0].rename_review.status == "declined"
            )
    assert prepared.review.proposal.changes[0].target_path == "Authored/Opening.md"
    assert len(prepared.review.requirements) == 1 and not prepared.review.ready


def choose(prepared, domain, choice, *, item_id="entry:opening"):
    offer = next(
        row
        for row in choice_offers(prepared)
        if row.domain == domain
        and next(
            c for c in prepared.review.proposal.changes if c.change_id == row.change_id
        ).item_id
        == item_id
    )
    result = Operations().resolve_update_choice(
        prepared,
        requirement_id=offer.requirement_id,
        choice=choice,
        assumptions_digest=offer.assumptions_digest,
    )
    assert result.code == "accepted", result.code
    return result


def test_source_first_current_preserves_exact_authored_bytes_at_selected_path():
    facts = moved_facts()
    second = two_items().subjects[1]
    second = second.model_copy(
        update={
            "current": second.current.model_copy(
                update={
                    "content": ExactContent(data=b"Unrelated authored writing.\r\n"),
                }
            )
        }
    )
    entry = inventory_item(
        "second",
        second.item_id,
        second.current.path,
        b"Unrelated authored writing.\r\n",
    )
    facts = with_subjects(
        facts, facts.subjects + (second,), facts.identity_inventory + (entry,)
    )
    facts = with_review_links(facts.model_copy(update={"link_context": None}))
    prepared = choose(
        preparation(facts), "text", "current", item_id="entry:second"
    ).preparation
    retained = prepared.review.approvals[0]
    renamed = choose(prepared, "rename", "source_path")
    assert not renamed.ready and renamed.unresolved == 1
    current = choose(renamed.preparation, "text", "current")
    assert current.ready and current.unresolved == 0
    selected = select_review_effects(current.preparation.review)
    assert selected.status == "selected", selected.code
    assert [(row.path, row.content.data) for row in selected.files] == [
        ("Notes/Opening.md", b"Independent authored writing.\r\n"),
        ("Notes/Second.md", b"Unrelated authored writing.\r\n"),
    ]
    assert selected.remove_paths == ("Authored/Opening.md",)
    assert current.publication == "not_started" and current.application is None
    assert retained in current.preparation.review.approvals
    plan = current.preparation.review
    fresh = refresh_review(
        plan, plan.facts.model_copy(update={"generation": 2}), preflight=preflight()
    )
    assert fresh.status == "accepted" and fresh.plan.ready
    assert fresh.plan.approvals == plan.approvals
    assert validate_review(fresh.plan).status == "accepted"
    assert select_review_effects(fresh.plan).files == selected.files
    observed = fresh.plan.facts
    owner = observed.identity_inventory[0]
    updated_current = owner.current.model_copy(
        update={"content": ExactContent(data=b"Authored after review.\r\n")}
    )
    changed = with_review_links(
        observed.model_copy(
            update={
                "generation": 3,
                "link_context": None,
                "identity_inventory": (
                    owner.model_copy(update={"current": updated_current}),
                )
                + observed.identity_inventory[1:],
                "subjects": (
                    observed.subjects[0].model_copy(
                        update={
                            "current": observed.subjects[0].current.model_copy(
                                update={"content": updated_current.content}
                            )
                        }
                    ),
                )
                + observed.subjects[1:],
            }
        )
    )
    invalidated = refresh_review(fresh.plan, changed, preflight=preflight())
    assert invalidated.status == "accepted" and not invalidated.plan.ready
    assert invalidated.plan.approvals == (retained,)
    assert invalidated.plan.actions == plan.actions
    assert validate_review(invalidated.plan).status == "accepted"
    assert select_review_effects(invalidated.plan).status == "refused"
    history = current.preparation.review.actions
    kept = choose(current.preparation, "rename", "keep_path")
    assert not kept.ready and kept.unresolved == 1
    assert kept.preparation.review.actions[:-1] == history
    assert kept.preparation.review.approvals == (retained,)
    returned = choose(kept.preparation, "text", "current")
    assert returned.ready
    assert returned.preparation.review.actions[-1].candidate is None
    selected = select_review_effects(returned.preparation.review)
    assert selected.status == "selected", selected.code
    assert [(row.path, row.content.data) for row in selected.files] == [
        ("Authored/Opening.md", b"Independent authored writing.\r\n"),
        ("Notes/Second.md", b"Unrelated authored writing.\r\n"),
    ]
    assert selected.remove_paths == ()


def current_links_preparation(raw, *, backlink=False):
    """Normalize actual current paths; no prospective Current document is supplied."""
    facts = moved_facts()
    current = facts.identity_inventory[0].current.model_copy(
        update={"content": ExactContent(data=raw)}
    )
    subject = facts.subjects[0].model_copy(
        update={
            "current": facts.subjects[0].current.model_copy(
                update={"content": current.content}
            )
        }
    )
    inventory = (
        facts.identity_inventory[0].model_copy(update={"current": current}),
        inventory_item("shared", "entry:shared", "Shared/Guide.md", b"# Section\r\n"),
        inventory_item(
            "old-local", "entry:old-local", "Authored/Local.md", b"Old local.\r\n"
        ),
        inventory_item(
            "new-local", "entry:new-local", "Notes/Local.md", b"Different local.\r\n"
        ),
    )
    if backlink:
        inventory += (
            inventory_item(
                "backlink",
                "entry:backlink",
                "Docs/Backlink.md",
                b"Keep [[Authored/Opening.md]].\r\n",
            ),
        )
    facts = facts.model_copy(
        update={
            "subjects": (subject,),
            "identity_inventory": inventory,
            "link_context": None,
        }
    )
    facts = with_review_links(facts)
    context = facts.link_context
    documents = tuple(
        interpret_links(
            d.content,
            document_id=d.document_id,
            source_path=d.source_path,
            path_mode="relative",
            targets=context.current_targets,
            target_facts=context.current_target_facts,
            inventory=context.inventory,
        )
        if d.source_path == "Authored/Opening.md"
        else d
        for d in context.current_documents
    )
    facts = facts.model_copy(
        update={
            "link_context": context.model_copy(update={"current_documents": documents})
        }
    )
    return preparation(type(facts).model_validate(facts.model_dump()))


@pytest.mark.parametrize(
    "raw,safe",
    (
        (b"Authored [shared](../Shared/Guide.md#Section).\r\n", True),
        (b"Authored [local](Local.md).\r\n", False),
    ),
    ids=("same-relative-meaning", "changed-relative-target"),
)
def test_current_at_source_path_preserves_relative_identity_and_fragment(raw, safe):
    prepared = current_links_preparation(raw)
    renamed = choose(prepared, "rename", "source_path").preparation
    offer = next(row for row in choice_offers(renamed) if row.domain == "text")
    result = Operations().resolve_update_choice(
        renamed,
        requirement_id=offer.requirement_id,
        choice="current",
        assumptions_digest=offer.assumptions_digest,
    )
    if safe:
        assert result.code == "accepted" and result.ready, result.code
        selected = select_review_effects(result.preparation.review)
        assert selected.status == "selected", selected.code
        assert [(row.path, row.content.data) for row in selected.files] == [
            ("Notes/Opening.md", raw)
        ]
        assert selected.remove_paths == ("Authored/Opening.md",)
    else:
        assert result.code == "invalid_candidate" and not result.ready
        assert result.preparation.review == renamed.review
        assert select_review_effects(result.preparation.review).status == "refused"


def test_current_at_source_does_not_preserve_a_backlink_to_the_displaced_path():
    prepared = current_links_preparation(
        b"Independent authored writing.\r\n", backlink=True
    )
    renamed = choose(prepared, "rename", "source_path")
    current = choose(renamed.preparation, "text", "current")
    assert not current.ready
    assert "selected_link_context_conflict" in current.preparation.review.blockers
    assert select_review_effects(current.preparation.review).status == "refused"
