"""Public selected filesystem effects from a completed S1 review."""

from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links


def test_ready_review_selects_exact_incoming_note_bytes_and_path():
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects

    facts = with_review_links(
        request(
            original=b"Original\r\n",
            current=b"Original\r\n",
            incoming=b"Incoming \xc3\xa9\r\n",
        ),
    )
    offered = prepare_review(facts, preflight=preflight())
    accepted = resolve_review(offered, action(offered))
    assert accepted.status == "accepted" and accepted.plan.ready

    selected = select_review_effects(accepted.plan)

    assert selected.status == "selected" and selected.code == "selected"
    assert selected.proposal_id == "review:one" and selected.generation == 1
    assert [(row.path, row.content.data) for row in selected.files] == [
        ("Notes/Opening.md", b"Incoming \xc3\xa9\r\n")
    ]
    assert selected.remove_paths == ()


def test_binary_both_keeps_current_path_and_selects_distinct_incoming_bytes():
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        attachment_request,
    )

    facts = attachment_request()
    offered = prepare_review(with_review_links(facts), preflight=preflight())
    selection, candidate = attachment_candidate(facts, "both")
    accepted = resolve_review(
        offered,
        action(
            offered,
            domain="attachment",
            choice="both",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert accepted.status == "accepted" and accepted.plan.ready

    selected = select_review_effects(accepted.plan)

    assert selected.status == "selected"
    assert [(row.path, row.content.data) for row in selected.files] == [
        ("Assets/data (incoming-ba7816bf).bin", b"abc"),
        ("Assets/data.bin", b"\x00authored"),
    ]
    assert selected.remove_paths == ()


def test_binary_both_selects_only_the_approved_literal_link_document():
    from brz2obsidian.contracts import ExactContent, LinkOccurrenceChoice
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        linked_attachment_request,
    )

    facts = linked_attachment_request()
    offered = prepare_review(facts, preflight=preflight())
    selection, candidate = attachment_candidate(facts, "both")
    original = facts.link_context.current_documents[0]
    changed = b"[[Assets/data.bin|Keep first]] and [Second edited alias](Assets/data%20%28incoming-ba7816bf%29.bin)"
    document = interpret_links(
        ExactContent(data=changed),
        document_id=original.document_id,
        source_path=original.source_path,
        path_mode="vault",
        targets=candidate.targets,
        target_facts=candidate.target_facts,
        inventory="complete",
    )
    link_choice = LinkOccurrenceChoice(
        document_id=original.document_id,
        occurrence_id=original.occurrences[1].occurrence_id,
        old=original.occurrences[1].meaning,
        replacement=b"[Second edited alias](Assets/data%20%28incoming-ba7816bf%29.bin)",
        selected=document.occurrences[1].meaning,
        expected_memberships=(),
        provenance="explicit_user",
    )
    chosen = selection.model_copy(update={"link_choices": (link_choice,)})
    states = tuple(
        interpret_link_target(
            document.content,
            target_id="owner:note",
            existence="present",
            memberships=(),
        )
        if state.target_id == "owner:note"
        else state
        for state in candidate.target_facts
    )
    candidate = candidate.model_copy(
        update={"documents": (document,), "target_facts": states}
    )
    accepted = resolve_review(
        offered,
        action(
            offered,
            domain="attachment",
            choice="both",
            attachment_selection=chosen,
            attachment_candidate=candidate,
        ),
    )
    assert accepted.status == "accepted" and accepted.plan.ready

    selected = select_review_effects(accepted.plan)

    assert selected.status == "selected"
    assert [(file.path, file.content.data) for file in selected.files] == [
        ("Assets/data (incoming-ba7816bf).bin", b"abc"),
        ("Assets/data.bin", b"\x00authored"),
        ("Notes/Owner.md", changed),
    ]
    assert selected.remove_paths == ()


def test_explicit_reviewed_rename_is_the_only_displaced_path_removal():
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
    from tests.reconciliation.test_identity import inventory_item

    facts = request(original=b"base\r\n", current=b"base\r\n", incoming=b"new\r\n")
    authored = inventory_item("moved", "entry:opening", "Authored/Name.md", b"base\r\n")
    facts = with_review_links(
        facts.model_copy(update={"identity_inventory": (authored,)})
    )
    offered = prepare_review(facts, preflight=preflight())
    renamed = resolve_review(
        offered, action(offered, domain="rename", choice="source_path")
    )
    accepted = resolve_review(
        renamed.plan, action(renamed.plan, decision_id="content:after-rename")
    )
    assert accepted.status == "accepted" and accepted.plan.ready

    selected = select_review_effects(accepted.plan)

    assert selected.status == "selected"
    assert [(file.path, file.content.data) for file in selected.files] == [
        ("Notes/Opening.md", b"new\r\n")
    ]
    assert selected.remove_paths == ("Authored/Name.md",)


def test_declined_restoration_retains_absence_without_a_delete_effect():
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
    from tests.reconciliation.test_absence import facts_for

    facts = with_review_links(facts_for(existence="absent", incoming=b"source\n"))
    offered = prepare_review(facts, preflight=preflight())
    accepted = resolve_review(
        offered,
        action(offered, domain="restoration", choice="decline_restoration"),
    )
    assert accepted.status == "accepted" and accepted.plan.ready

    selected = select_review_effects(accepted.plan)

    assert selected.status == "selected"
    assert selected.files == () and selected.remove_paths == ()


def test_unready_or_forged_review_never_selects_a_file():
    from brz2obsidian.core import prepare_review, select_review_effects

    offered = prepare_review(with_review_links(request()), preflight=preflight())
    assert not offered.ready
    pending = select_review_effects(offered)
    assert pending.status == "refused" and pending.code == "review_not_ready"
    assert pending.files == () and pending.remove_paths == ()

    forged = offered.model_copy(
        update={"ready": True, "readiness": "ready", "requirements": ()}
    )
    invalid = select_review_effects(forged)
    assert invalid.status == "refused" and invalid.code == "invalid_plan"
    assert invalid.files == () and invalid.remove_paths == ()


def test_no_context_no_change_review_selects_only_its_owned_current_bytes():
    from brz2obsidian.core import prepare_review, select_review_effects

    unchanged = b"authored \xc3\xa9\r\n"
    facts = request(original=unchanged, current=unchanged, incoming=unchanged)
    plan = prepare_review(facts, preflight=preflight())
    assert plan.ready and plan.facts.link_context is None

    selected = select_review_effects(plan)

    assert selected.status == "selected"
    assert [(file.path, file.content.data) for file in selected.files] == [
        ("Notes/Opening.md", unchanged)
    ]
    assert selected.remove_paths == ()
