"""Exact binary alternatives and link meaning through public reconciliation seams."""

from brz2obsidian.core import reconcile
from tests.reconciliation.test_absence import facts_for


def attachment_request():
    from brz2obsidian.contracts import AttachmentFacts, AttachmentDestination, IdentityTargetFacts
    from tests.reconciliation.test_identity import with_subjects

    facts = facts_for(original=b"\x00original", current=b"\x00authored", incoming=b"abc", facet="attachment:payload")
    current = facts.subjects[0].current.model_copy(update={"path": "Assets/data.bin"})
    subject = facts.subjects[0].model_copy(update={
        "path": "Assets/data.bin", "current": current,
        "source_target": IdentityTargetFacts(normalized_path="assets/data.bin", containment="contained", status="safe"),
        "attachment": AttachmentFacts(current_target_id="resource:payload", allocation_candidates=(
            AttachmentDestination(path="Assets/data (incoming-ba7816bf).bin", target=IdentityTargetFacts(normalized_path="assets/data (incoming-ba7816bf).bin", containment="contained", status="safe")),
        )),
    })
    entry = facts.identity_inventory[0].model_copy(update={"current": current, "target": subject.source_target})
    return with_subjects(facts, (subject,), (entry,))


def test_binary_conflict_offers_exact_current_incoming_and_distinct_both_outputs():
    result = reconcile(attachment_request())
    change, = result.changes
    assert change.disposition == "unresolved" and not result.ready
    review = change.attachment_review
    current, incoming, both = review.alternatives
    assert current.choice == "current" and current.eligible
    assert [(o.target_id, o.path, o.content.data) for o in current.outputs] == [("resource:payload", "Assets/data.bin", b"\x00authored")]
    assert incoming.choice == "incoming" and incoming.eligible
    assert [(o.target_id, o.path, o.content.data) for o in incoming.outputs] == [("resource:payload", "Assets/data.bin", b"abc")]
    assert both.choice == "both" and both.eligible
    assert [(o.target_id, o.path, o.content.data) for o in both.outputs] == [
        ("resource:payload", "Assets/data.bin", b"\x00authored"),
        ("resource:payload:incoming:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", "Assets/data (incoming-ba7816bf).bin", b"abc"),
    ]
    assert change.result is None and change.requires_decision
    assert review.assumptions and review.incoming_source_path == "Assets/data.bin"


def test_note_and_two_binary_facets_share_owner_without_stealing_associations():
    from tests.reconciliation.test_identity import inventory_item, with_subjects
    from tests.reconciliation.test_proposals import request
    from brz2obsidian.contracts import AttachmentFacts, IdentityTargetFacts

    facts = attachment_request()
    note = request(original=b"note", current=b"note", incoming=b"note").subjects[0]
    second = facts.subjects[0].model_copy(update={
        "facet": "attachment:second", "path": "Assets/second.bin",
        "baseline": note.baseline.model_copy(update={"content": note.current.content}),
        "current": note.current.model_copy(update={"path": "Assets/second.bin"}),
        "incoming": note.incoming,
        "source_target": IdentityTargetFacts(normalized_path="assets/second.bin", containment="contained", status="safe"),
        "attachment": AttachmentFacts(current_target_id="resource:second", allocation_candidates=()),
    })
    facts = with_subjects(facts, (note, facts.subjects[0], second), (
        inventory_item("note", "entry:opening", "Notes/Opening.md", b"note", facet="content"),
        inventory_item("asset-one", "entry:opening", "Assets/data.bin", b"\x00authored", facet="attachment:payload"),
        inventory_item("asset-two", "entry:opening", "Assets/second.bin", b"note", facet="attachment:second"),
    ))
    proposal = reconcile(facts)
    assert [(c.facet, c.identity_review.selected_entry_id, c.disposition) for c in proposal.changes] == [
        ("content", "note", "no_change"),
        ("attachment:payload", "asset-one", "unresolved"),
        ("attachment:second", "asset-two", "no_change"),
    ]
    assert proposal.changes[0].result.data == b"note"
    assert proposal.changes[1].current.data == b"\x00authored"
    assert proposal.changes[2].result.data == b"note"


def test_identity_actions_are_scoped_to_facet_and_unknown_scope_requires_observed_repair():
    import pytest
    from pydantic import ValidationError
    from brz2obsidian.contracts import IdentityInventoryItem, RenamePathDecision
    from tests.reconciliation.test_identity import association, inventory_item, rename_decision
    from tests.reconciliation.test_proposals import request

    facts = request(original=b"note", current=b"note", incoming=b"note")
    unknown = inventory_item("unknown-facet", "entry:opening", "Notes/Opening.md", b"note", facet=None)
    facts = facts.model_copy(update={"identity_inventory": (unknown,)})
    unresolved = reconcile(facts)
    assert unresolved.changes[0].identity_review.status == "unresolved"
    decision = association(facts, unresolved.changes[0].identity_review, "unknown-facet")
    proposed = reconcile(facts.model_copy(update={"association_decisions": (decision,)}))
    assert proposed.changes[0].identity_review.status == "association_proposed"
    assert proposed.changes[0].identity_review.repair_required and not proposed.ready
    observed = reconcile(facts.model_copy(update={"identity_inventory": (unknown.model_copy(update={"facet": "content"}),)}))
    assert observed.ready and observed.changes[0].identity_review.status == "matched"
    asset = unknown.model_copy(update={"facet": "attachment:payload"})
    wrong = facts.model_copy(update={"identity_inventory": (asset,)})
    review = reconcile(wrong).changes[0].identity_review
    assert review.candidates[0].facet == "attachment:payload" and not review.candidates[0].eligible
    stolen = reconcile(wrong.model_copy(update={"association_decisions": (association(wrong, review, asset.entry_id),)}))
    assert not stolen.ready and stolen.changes[0].disposition == "refused"
    assert "unsafe_identity_decision" in {f.code for f in stolen.findings}
    raw = unknown.model_dump(); del raw["facet"]
    with pytest.raises(ValidationError):
        IdentityInventoryItem.model_validate(raw)
    moved = facts.model_copy(update={"identity_inventory": (inventory_item("moved", "entry:opening", "My.md", b"note", facet="content"),)})
    action = rename_decision(moved, reconcile(moved).changes[0].rename_review, "source_path")
    raw = action.model_dump(); del raw["facet"]
    with pytest.raises(ValidationError):
        RenamePathDecision.model_validate(raw)
    with pytest.raises(ValidationError):
        reconcile(moved.model_copy(update={"rename_decisions": (action.model_copy(update={"facet": "attachment:unknown"}),)}))


def test_note_rename_cannot_apply_to_same_owner_asset_and_asset_move_keeps_exact_bytes():
    from tests.reconciliation.test_identity import inventory_item, rename_decision, with_subjects
    from tests.reconciliation.test_proposals import request

    facts = attachment_request()
    asset = facts.subjects[0]
    note = request(original=b"note", current=b"note", incoming=b"note").subjects[0]
    facts = with_subjects(facts, (note, asset), (
        inventory_item("note", "entry:opening", "My.md", b"note", facet="content"),
        inventory_item("asset", "entry:opening", "Keep/data.bin", b"\x00authored", facet="attachment:payload"),
    ))
    offered = reconcile(facts)
    note_action = rename_decision(facts, offered.changes[0].rename_review, "source_path")
    reviewed = reconcile(facts.model_copy(update={"rename_decisions": (note_action,)}))
    assert reviewed.changes[0].target_path == "Notes/Opening.md"
    assert reviewed.changes[1].path == reviewed.changes[1].target_path == "Keep/data.bin"
    assert reviewed.changes[1].current.data == b"\x00authored"
    wrong_scope = note_action.model_copy(update={"facet": "attachment:payload"})
    refused = reconcile(facts.model_copy(update={"rename_decisions": (wrong_scope,)}))
    assert refused.changes[0].target_path == "My.md"
    assert refused.changes[1].target_path == "Keep/data.bin"
    assert refused.changes[1].disposition == "stale"
    assert refused.changes[1].rename_review.status == "stale" and not refused.ready


def test_outer_links_expose_literal_qualified_wiki_markdown_alias_and_fragment_meaning():
    from brz2obsidian.contracts import ExactContent, IdentityTargetFacts, ImportedItemIdentity, ReferenceTarget
    from brz2obsidian.obsidian import interpret_links, interpret_link_target

    target = ReferenceTarget(schema_id="brz2obsidian.reference-target", schema_version=1,
        target_id="note:guide", kind="note", canonical_path="Docs/Guide.md",
        identity=ImportedItemIdentity(module_id="synthetic-folio", collection_id="folio:collection", item_id="guide"),
        target=IdentityTargetFacts(normalized_path="docs/guide.md", containment="contained", status="safe"),
        representations=("Guide", "Docs/Guide", "Manual"), validation_fingerprint="guide:validated", status="safe")
    state = interpret_link_target(ExactContent(data=b"# Overview\nBody ^proof\n"), target_id="note:guide", existence="present", memberships=())
    raw = b"Text [[Docs/Guide#Overview|Read me]] and [Block](Docs/Guide.md#^proof). [[Manual|Alias]]"
    parsed = interpret_links(ExactContent(data=raw), document_id="note:owner", source_path="Notes/Owner.md", path_mode="vault", targets=(target,), target_facts=(state,), inventory="complete")
    assert parsed.status == "supported" and parsed.issues == ()
    assert [(o.syntax, o.meaning.target_id, o.meaning.path, o.meaning.display_text, None if o.meaning.fragment is None else (o.meaning.fragment.kind, o.meaning.fragment.value)) for o in parsed.occurrences] == [
        ("wiki", "note:guide", "Docs/Guide.md", "Read me", ("heading", "Overview")),
        ("markdown", "note:guide", "Docs/Guide.md", "Block", ("block", "proof")),
        ("wiki", "note:guide", "Docs/Guide.md", "Alias", None),
    ]
    assert all(o.meaning.status == "resolved" and o.meaning.target_identity.item_id == "guide" for o in parsed.occurrences)
    assert raw[parsed.occurrences[0].span.start:parsed.occurrences[0].span.end] == b"[[Docs/Guide#Overview|Read me]]"
    assert [o.occurrence_id for o in parsed.occurrences] == ["note:owner:link:0", "note:owner:link:1", "note:owner:link:2"]


def target_for_links(target_id="note:guide", path="Docs/Guide.md", *, aliases=(), kind="note"):
    from brz2obsidian.contracts import IdentityTargetFacts, ReferenceTarget

    return ReferenceTarget(schema_id="brz2obsidian.reference-target", schema_version=1, target_id=target_id, kind=kind,
        canonical_path=path, identity=None,
        target=IdentityTargetFacts(normalized_path=path.casefold(), containment="contained", status="safe"),
        representations=aliases, validation_fingerprint=target_id + ":validated", status="safe")


def test_relative_and_shortened_targets_use_complete_explicit_path_context():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.obsidian import interpret_links, interpret_link_target

    guide = target_for_links()
    other = target_for_links("note:other-guide", "Other/Guide.md")
    state = interpret_link_target(ExactContent(data=b"Guide body"), target_id="note:guide", existence="present", memberships=())
    other_state = state.model_copy(update={"target_id": "note:other-guide"})
    relative = interpret_links(ExactContent(data=b"[[../Docs/Guide|Read]] [Read](../Docs/Guide.md)"), document_id="note:owner", source_path="Notes/Owner.md", path_mode="relative", targets=(guide, other), target_facts=(state, other_state), inventory="complete")
    assert [o.meaning.target_id for o in relative.occurrences] == ["note:guide", "note:guide"]
    assert [o.query.value for o in relative.occurrences] == ["Docs/Guide", "Docs/Guide.md"]
    short = interpret_links(ExactContent(data=b"[[Guide]] [[Docs/Guide|Qualified]]"), document_id="note:owner", source_path="Notes/Owner.md", path_mode="shortened", targets=(guide, other), target_facts=(state, other_state), inventory="complete")
    assert short.occurrences[0].meaning.status == "ambiguous"
    assert short.occurrences[0].meaning.candidates == ("note:guide", "note:other-guide")
    assert short.occurrences[1].meaning.status == "resolved" and short.occurrences[1].meaning.target_id == "note:guide"


def test_link_interpreter_preserves_code_escaped_syntax_and_external_meaning():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.obsidian import interpret_links, interpret_link_target

    target = target_for_links()
    state = interpret_link_target(ExactContent(data=b"Guide"), target_id="note:guide", existence="present", memberships=())
    raw = b'`[[Docs/Guide]]`\n```md\n[[Docs/Guide]]\n```\n\\[[Docs/Guide]] [[Docs/Guide|Real]] [Web](https://example.com/#details)'
    parsed = interpret_links(ExactContent(data=raw), document_id="note:owner", source_path="Notes/Owner.md", path_mode="vault", targets=(target,), target_facts=(state,), inventory="complete")
    assert parsed.status == "supported"
    assert [(o.meaning.status, o.meaning.display_text) for o in parsed.occurrences] == [("resolved", "Real"), ("external", "Web")]
    assert parsed.occurrences[1].meaning.target_id is None and parsed.occurrences[1].meaning.fragment is None
    assert parsed.content.data == raw


def test_encoded_markdown_angles_and_hierarchical_fragments_keep_byte_spans():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.obsidian import interpret_links, interpret_link_target

    target = target_for_links(path="Docs/With space.md")
    state = interpret_link_target(ExactContent(data=b"# Outer\n## Inner\nParagraph ^proof\n"), target_id="note:guide", existence="present", memberships=())
    raw = 'é [[Docs/With space#Outer#Inner|Nested]] [Nested](<Docs/With%20space.md#Outer%23Inner>)'.encode()
    parsed = interpret_links(ExactContent(data=raw), document_id="owner", source_path="Owner.md", path_mode="vault", targets=(target,), target_facts=(state,), inventory="complete")
    assert parsed.status == "supported"
    assert [o.meaning.status for o in parsed.occurrences] == ["resolved", "resolved"]
    assert [o.meaning.fragment.value for o in parsed.occurrences] == ["Outer#Inner", "Outer#Inner"]
    assert parsed.occurrences[0].span.start == 3
    assert raw[parsed.occurrences[1].destination_span.start:parsed.occurrences[1].destination_span.end] == b"<Docs/With%20space.md#Outer%23Inner>"


def test_unsupported_link_syntax_and_incomplete_context_never_become_safe():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.obsidian import interpret_links, interpret_link_target

    target = target_for_links()
    state = interpret_link_target(ExactContent(data=b"# Same\n# Same\n"), target_id="note:guide", existence="present", memberships=())
    for raw in (
        b"[[Docs/Guide", b"[Nested [label]](Docs/Guide.md)",
        b'[Title](Docs/Guide.md "unsupported title")', b"[Bad](Docs/%GG.md)",
        b"[Bad](Docs/%FF.md)", b"[[Docs/Guide|Alias|Other]]", b"[[Docs/Guide#^]]",
        b"[Reference][guide]", b'<a href="Docs/Guide.md">Guide</a>',
        b"`unclosed [[Docs/Guide]]", b"[[../../Escape.md]]", b"\xff[[Docs/Guide]]",
    ):
        parsed = interpret_links(ExactContent(data=raw), document_id="owner", source_path="Owner.md", path_mode="relative", targets=(target,), target_facts=(state,), inventory="complete")
        assert parsed.status == "unsupported" and parsed.issues, raw
        assert parsed.content.data == raw
    ambiguous = interpret_links(ExactContent(data=b"[[Docs/Guide#Same]]"), document_id="owner", source_path="Owner.md", path_mode="vault", targets=(target,), target_facts=(state,), inventory="complete")
    assert ambiguous.occurrences[0].meaning.status == "fragment_ambiguous"
    partial = interpret_links(ExactContent(data=b"[[Docs/Guide]]"), document_id="owner", source_path="Owner.md", path_mode="vault", targets=(target,), target_facts=(state,), inventory="partial")
    assert partial.occurrences[0].meaning.status == "inventory_uncertain"


def test_associated_links_expose_each_old_incoming_and_secondary_meaning_without_redirect():
    from brz2obsidian.contracts import ExactContent, LinkContext
    from brz2obsidian.obsidian import interpret_links, interpret_link_target
    from tests.reconciliation.test_identity import inventory_item

    facts = attachment_request()
    target = target_for_links("resource:payload", "Assets/data.bin", kind="resource")
    old_state = interpret_link_target(facts.subjects[0].current.content, target_id="resource:payload", existence="present", memberships=())
    new_state = interpret_link_target(facts.subjects[0].incoming, target_id="resource:payload", existence="present", memberships=())
    raw = b"[[Assets/data.bin|Keep first]] and [[Assets/data.bin|Redirect second]]"
    old_doc = interpret_links(ExactContent(data=raw), document_id="owner:note", source_path="Notes/Owner.md", path_mode="vault", targets=(target,), target_facts=(old_state,), inventory="complete")
    new_doc = interpret_links(ExactContent(data=raw), document_id="owner:note", source_path="Notes/Owner.md", path_mode="vault", targets=(target,), target_facts=(new_state,), inventory="complete")
    context = LinkContext(schema_id="brz2obsidian.link-context", schema_version=1, inventory="complete",
        current_targets=(target,), incoming_targets=(target,), current_target_facts=(old_state,), incoming_target_facts=(new_state,), current_documents=(old_doc,), incoming_documents=(new_doc,))
    subject = facts.subjects[0].model_copy(update={"attachment": facts.subjects[0].attachment.model_copy(update={"affected_documents": ("owner:note",)})})
    facts = facts.model_copy(update={"subjects": (subject,), "link_context": context, "identity_inventory": facts.identity_inventory + (inventory_item("owner-note", "entry:opening", "Notes/Owner.md", raw, facet="content"),)})
    change, = reconcile(facts).changes
    first, second = change.attachment_review.links
    assert [first.occurrence_id, second.occurrence_id] == ["owner:note:link:0", "owner:note:link:1"]
    assert [first.old.display_text, second.old.display_text] == ["Keep first", "Redirect second"]
    assert all(link.old.target_id == link.incoming.target_id == "resource:payload" for link in (first, second))
    assert all(link.incoming.target_version == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" for link in (first, second))
    assert first.secondary.path == second.secondary.path == "Assets/data (incoming-ba7816bf).bin"
    assert first.secondary.target_id == "resource:payload:incoming:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert first.secondary.display_text == "Keep first" and second.secondary.display_text == "Redirect second"
    assert first.choices == second.choices == ("keep_current", "use_incoming", "use_secondary")
    assert old_doc.content.data == new_doc.content.data == raw
    assert change.result is None and change.requires_decision
