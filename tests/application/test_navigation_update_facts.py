"""Version-bound note promotion at the generated review and link seams."""

import pytest

from brz2obsidian.application.update_facts import assemble_facts, automatic_merge_facts
from brz2obsidian.application.update_lifecycle import text_choice_action
from brz2obsidian.core import (
    analyze,
    inspect_review_choices,
    load_review,
    plan,
    prepare_review,
    resolve_review,
    save_review,
    select_review_effects,
)
from brz2obsidian.obsidian import render
from tests.application.test_graph_modules import POLICY, edge, item, snapshot
from tests.application.test_module_seams import METADATA
from tests.reconciliation.test_resolution import action, preflight

PATH = "Notes/Leaf.md"
MANUAL = "Manual.md"
LINK = b"Read [[Notes/Leaf.md|Leaf]].\r\n"
CASE_EQUIVALENT_LINK = b"Read [[notes/LEAF.md|Leaf]].\r\n"


def generated(analysis, generation):
    metadata = METADATA.model_copy(update={"renderer_version": str(generation)})
    return {
        f.relative_path: f.content
        for f in render(
            plan(analysis, output_format=generation), metadata
        ).generated_files
    }


def navigation_review(*, occupant=None, observer=LINK, extra=None, owner_edit=None):
    analysis = analyze(
        snapshot((item("leaf", "Leaf"),), (edge("edge", "entry", "leaf"),)), POLICY
    )
    original, incoming = (generated(analysis, generation) for generation in (8, 9))
    assert PATH not in original and PATH in incoming
    current = original | {MANUAL: observer} | (extra or {})
    if occupant is not None:
        current[PATH] = occupant
    if owner_edit is not None:
        home = "Home \u2014 Entry.md"
        current[home] = owner_edit(current[home])
    facts = assemble_facts(
        original, incoming, current, proposal_id="promotion", generation=1
    )
    operation = facts.format_operation.model_copy(update={"kind": "format_transition"})
    facts = automatic_merge_facts(
        facts.model_copy(update={"format_operation": operation})
    )
    return prepare_review(facts, preflight=preflight())


def comparison(review, item_id):
    return next(row for row in review.proposal.changes if row.item_id == item_id)


def choose(review, item_id, domain, choice, **parameters):
    row = comparison(review, item_id)
    edited = parameters.pop("edited", None)
    requested = action(
        review,
        row,
        domain=domain,
        choice=choice,
        decision_id=f"{item_id}:{choice}",
        **parameters,
    )
    result = resolve_review(
        review, text_choice_action(review, requested, edited=edited)
    )
    assert result.status == "accepted", result.code
    return result.plan


def test_promotion_keeps_the_reserved_identity_of_an_unchanged_authored_exact_link():
    review = navigation_review(
        observer=LINK + CASE_EQUIVALENT_LINK + b"Read [Leaf](./notes/LEAF).\r\n"
    )
    context = review.facts.link_context
    (local,) = [d for d in context.current_documents if d.source_path == MANUAL]
    assert [
        (
            occurrence.query.mode,
            occurrence.meaning.status,
            occurrence.meaning.path,
            occurrence.meaning.target_identity.item_id,
        )
        for occurrence in local.occurrences
    ] == [("exact", "intentionally_uncreated", PATH, "leaf")] * 3
    row = comparison(review, "leaf")
    assert row.original is None and row.current is None
    assert b"## Parents\n\n- [[Home \xe2\x80\x94 Entry.md|Entry]]" in row.incoming.data
    chosen = choose(review, "leaf", "format", "incoming")
    assert chosen.ready, (chosen.blockers, chosen.requirements)
    effects = select_review_effects(chosen)
    assert effects.status == "selected" and not effects.remove_paths
    assert (
        next(f for f in effects.files if f.path == PATH).content.data
        == row.incoming.data
    )
    assert all(f.path != MANUAL for f in effects.files)


@pytest.mark.parametrize(
    "local",
    (b"", b"---\ncustom: analyst\n---\n\nVault prose.\n"),
    ids=("empty", "edited"),
)
def test_same_path_occupant_needs_identity_and_result_approval(local):
    review = navigation_review(occupant=local)
    row = comparison(review, "leaf")
    assert row.original is None and row.result is None
    assert row.identity_review.selected_entry_id is None
    (candidate,) = [c for c in row.identity_review.candidates if c.current.path == PATH]
    agreed = choose(
        review, "leaf", "identity", "associate", selected_entry_id=candidate.entry_id
    )
    row = comparison(agreed, "leaf")
    assert row.original is None and row.current.data == local and not agreed.ready
    assert b"## Parents" in row.incoming.data
    (required,) = [
        offer
        for offer in inspect_review_choices(agreed)
        if offer.change_id == row.change_id
    ]
    assert required.domain == "format"
    assert required.enabled_choices == (
        ("edited",) if local else ("incoming", "edited")
    )
    assert select_review_effects(agreed).status != "selected"
    if local:
        result = row.incoming.data.replace(
            b"---\n\n# Leaf\n\n",
            b"custom: analyst\n---\n\n# Leaf\n\nVault prose.\n\n",
        )
        unsigned = b"".join(
            line
            for line in result.splitlines(keepends=True)
            if not line.startswith((b"source_collection_id:", b"source_item_id:"))
        )
        requested = action(agreed, row, domain="format", choice="edited")
        invalid = resolve_review(
            agreed, text_choice_action(agreed, requested, edited=unsigned)
        )
        assert invalid.status == "refused" and not invalid.plan.ready
        chosen = choose(agreed, "leaf", "format", "edited", edited=result)
    else:
        result = row.incoming.data
        chosen = choose(agreed, "leaf", "format", "incoming")
    assert chosen.ready, (chosen.blockers, chosen.requirements)
    (approval,) = [a for a in chosen.approvals if a.change_id == row.change_id]
    assert approval.domain == "format" and approval.result.data == result
    effects = select_review_effects(chosen)
    assert effects.status == "selected"
    assert next(f for f in effects.files if f.path == PATH).content.data == result


def test_retirement_of_a_locally_deleted_note_survives_review_serialization():
    versions = []
    for digest, relationships in (
        ("a", (edge("edge", "entry", "leaf"),)),
        ("b", ()),
        ("c", (edge("jump", "entry", "leaf", "related"),)),
    ):
        graph = snapshot((item("leaf", "Leaf"),), relationships)
        graph = graph.model_copy(
            update={
                "identity": graph.identity.model_copy(
                    update={"snapshot_digest": digest * 64}
                )
            }
        )
        versions.append(generated(analyze(graph, POLICY), 9))
    original, dormant, qualifying = versions
    current = {path: raw for path, raw in original.items() if path != PATH}
    retired = assemble_facts(
        original, dormant, current, proposal_id="retire", generation=1
    )
    retirement = prepare_review(retired, preflight=preflight())
    assert comparison(retirement, "leaf").disposition == "local_deleted"
    assert retirement.facts.retired_note_ids == ("leaf",)
    saved = save_review(retirement)
    loaded = load_review(saved.record.model_dump_json()).loaded
    assert loaded.saved.plan.facts.retired_note_ids == ("leaf",)

    facts = assemble_facts(
        dormant,
        qualifying,
        dormant,
        proposal_id="requalify",
        generation=1,
        retired_note_ids=loaded.saved.plan.facts.retired_note_ids,
    )
    reopened = prepare_review(facts, preflight=preflight())
    deletion = comparison(reopened, "leaf")
    assert deletion.original is None and deletion.current is None
    assert deletion.disposition == "local_deleted" and not deletion.requires_decision
    effects = select_review_effects(reopened)
    assert effects.status == "selected", (reopened.blockers, reopened.requirements)
    assert all(f.path != PATH for f in effects.files)

    omitted_graph = snapshot((), ())
    omitted_graph = omitted_graph.model_copy(
        update={
            "identity": omitted_graph.identity.model_copy(
                update={"snapshot_digest": "d" * 64}
            )
        }
    )
    omitted = generated(analyze(omitted_graph, POLICY), 9)
    omission = prepare_review(
        assemble_facts(
            dormant,
            omitted,
            dormant,
            proposal_id="omission",
            generation=1,
            retired_note_ids=loaded.saved.plan.facts.retired_note_ids,
        ),
        preflight=preflight(),
    )
    assert omission.facts.retired_note_ids == ("leaf",)
    assert all(subject.item_id != "leaf" for subject in omission.facts.subjects)
    selected = select_review_effects(omission)
    assert selected.status == "selected", (omission.blockers, omission.requirements)
    current = {f.path: f.content.data for f in selected.files}
    current.pop("Uncreated targets.md", None)
    returned = prepare_review(
        assemble_facts(
            omitted,
            qualifying,
            current,
            proposal_id="return",
            generation=1,
            retired_note_ids=omission.facts.retired_note_ids,
        ),
        preflight=preflight(),
    )
    deletion = comparison(returned, "leaf")
    assert deletion.original is None and deletion.disposition == "local_deleted"
    selected = select_review_effects(returned)
    assert selected.status == "selected", (returned.blockers, returned.requirements)
    assert all(f.path != PATH for f in selected.files)


def test_authored_short_name_blocks_a_promotion_to_an_ambiguous_destination():
    review = navigation_review(
        observer=b"Read [[Leaf]].\r\n",
        extra={"Another/Leaf.md": b"# Different leaf\n"},
    )
    context = review.facts.link_context
    (observer,) = [d for d in context.current_documents if d.source_path == MANUAL]
    (occurrence,) = observer.occurrences
    assert len(occurrence.meaning.candidates) == 2
    chosen = choose(review, "leaf", "format", "incoming")
    assert not chosen.ready
    assert "selected_link_context_conflict" in chosen.blockers


def test_unrelated_claim_at_a_reserved_path_cannot_be_adopted():
    occupant = (
        b'---\nsource_collection_id: "collection"\n'
        b'source_item_id: "unrelated"\n---\n\n# Independent\n'
    )
    review = navigation_review(occupant=occupant, observer=CASE_EQUIVALENT_LINK)
    (observer,) = [
        doc
        for doc in review.facts.link_context.current_documents
        if doc.source_path == MANUAL
    ]
    (link,) = observer.occurrences
    assert (link.query.mode, link.meaning.status, link.meaning.path) == (
        "exact",
        "resolved",
        PATH,
    )
    assert link.meaning.target_identity.item_id == "unrelated"
    row = comparison(review, "leaf")
    assert row.original is None and row.current.data == occupant
    assert row.identity_review.status != "matched"
    assert not any(
        c.eligible for c in row.identity_review.candidates if c.current.path == PATH
    )
    assert not review.ready


def test_obsolete_listing_retains_current_bytes_and_has_no_incoming_file():
    analysis = analyze(
        snapshot(
            (item("a", "Jump A"), item("b", "Jump B")),
            (edge("jump", "a", "b", "related"),),
        ),
        POLICY,
    )
    original, incoming = (generated(analysis, version) for version in (8, 9))
    path = "Uncreated targets.md"
    assert path not in incoming
    local = original[path] + b"\nLocal annotation.\r\n"
    facts = assemble_facts(
        original,
        incoming,
        original | {path: local},
        proposal_id="obsolete-listing",
        generation=1,
    )
    operation = facts.format_operation.model_copy(update={"kind": "format_transition"})
    review = prepare_review(
        automatic_merge_facts(facts.model_copy(update={"format_operation": operation})),
        preflight=preflight(),
    )
    listing = comparison(review, "support:" + path)
    assert listing.incoming is None and listing.disposition == "source_absent"
    assert listing.result.data == local and not listing.requires_decision


@pytest.mark.parametrize("placement", ("free", "occupied", "authored-before"))
def test_generated_navigation_requires_the_approved_moved_note_destination(placement):
    occupied = placement != "free"
    authored = placement == "authored-before"
    canonical, relocated = b"[[Notes/Leaf.md|Leaf]]", b"[[Moved/Leaf.md|Leaf]]"
    heading = b"## Children\n\n"
    authored_block = heading + b"- " + canonical + b"\n\nAuthored context.\n\n"
    moved = "Moved/Leaf.md"
    local = (
        b'---\nsource_collection_id: "collection"\n'
        b'source_item_id: "leaf"\n---\n\n# Leaf\n\nLocal prose.\r\n'
    )
    occupant = b"# Unrelated local file\r\n" if occupied else None
    review = navigation_review(
        occupant=occupant,
        observer=LINK if occupied else b"Independent local prose.\r\n",
        extra={moved: local},
        owner_edit=lambda body: (
            body.replace(heading, authored_block + heading, 1) if authored else body
        ),
    )
    leaf = comparison(review, "leaf")
    assert leaf.target_path == moved and leaf.original is None
    leaf_result = leaf.incoming.data + b"\nLocal prose.\r\n"
    chosen = choose(review, "leaf", "format", "edited", edited=leaf_result)
    entry = comparison(chosen, "entry")
    (offer,) = [
        offer
        for offer in inspect_review_choices(chosen)
        if offer.change_id == entry.change_id
    ]
    assert offer.enabled_choices == ("edited",) and not chosen.ready
    initial = entry.current.data
    assert b"[[Notes/Leaf.md|Leaf]]" in initial
    refused = resolve_review(
        chosen,
        text_choice_action(
            chosen,
            action(chosen, entry, domain=offer.domain, choice="edited"),
            edited=initial,
        ),
    )
    assert refused.status == "refused"
    prefix, generated, suffix = initial.rpartition(canonical)
    assert generated == canonical
    corrected = prefix + relocated + suffix
    if authored:
        assert authored_block in corrected
        requested = action(chosen, entry, domain=offer.domain, choice="edited")
        for wrong in (
            initial.replace(canonical, relocated, 1),
            initial.replace(canonical, relocated),
        ):
            outcome = resolve_review(
                chosen, text_choice_action(chosen, requested, edited=wrong)
            )
            assert outcome.status == "refused"
    final = choose(chosen, "entry", offer.domain, "edited", edited=corrected)
    effects = select_review_effects(final)
    assert effects.status == "selected", (final.blockers, final.requirements)
    published = {f.path: f.content.data for f in effects.files}
    assert published[moved] == leaf_result and published[entry.path] == corrected
    assert (
        PATH not in published and MANUAL not in published and not effects.remove_paths
    )
    (approval,) = [a for a in final.actions if a.change_id == entry.change_id]
    (changed,) = [
        link
        for link in approval.candidate.links.occurrences
        if link.meaning.path == moved
    ]
    assert changed.meaning.target_identity.item_id == "leaf"
    if authored:
        (retained,) = [
            link
            for link in approval.candidate.links.occurrences
            if link.raw == canonical
        ]
        assert retained.meaning.status == "resolved"
        assert (
            retained.meaning.path == PATH and retained.meaning.target_identity is None
        )

    if not occupied:
        source = {s.path: s.incoming.data for s in final.facts.subjects if s.incoming}
        repeated = prepare_review(
            assemble_facts(
                source, source, published, proposal_id="repeated", generation=1
            ),
            preflight=preflight(),
        )
        assert repeated.ready, (repeated.blockers, repeated.requirements)
        assert comparison(repeated, "entry").result.data == corrected
