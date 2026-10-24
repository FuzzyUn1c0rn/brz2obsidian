"""Exact binary alternatives and link meaning through public reconciliation seams."""

from brz2obsidian.core import reconcile
from tests.reconciliation.test_absence import facts_for


def attachment_request():
    from brz2obsidian.contracts import (
        AttachmentDestination,
        AttachmentFacts,
        IdentityTargetFacts,
    )
    from tests.reconciliation.test_identity import with_subjects

    facts = facts_for(
        original=b"\x00original",
        current=b"\x00authored",
        incoming=b"abc",
        facet="attachment:payload",
    )
    current = facts.subjects[0].current.model_copy(update={"path": "Assets/data.bin"})
    subject = facts.subjects[0].model_copy(
        update={
            "path": "Assets/data.bin",
            "current": current,
            "source_target": IdentityTargetFacts(
                normalized_path="assets/data.bin",
                containment="contained",
                status="safe",
            ),
            "attachment": AttachmentFacts(
                current_target_id="resource:payload",
                affected_documents=(),
                allocation_candidates=(
                    AttachmentDestination(
                        path="Assets/data (incoming-ba7816bf).bin",
                        target=IdentityTargetFacts(
                            normalized_path="assets/data (incoming-ba7816bf).bin",
                            containment="contained",
                            status="safe",
                        ),
                    ),
                ),
            ),
        }
    )
    entry = facts.identity_inventory[0].model_copy(
        update={"current": current, "target": subject.source_target}
    )
    result = with_subjects(facts, (subject,), (entry,))
    return result.model_copy(update={"link_context": binary_context(result)})


def test_binary_conflict_offers_exact_current_incoming_and_distinct_both_outputs():
    result = reconcile(attachment_request())
    (change,) = result.changes
    assert change.disposition == "unresolved" and not result.ready
    review = change.attachment_review
    current, incoming, both = review.alternatives
    assert current.choice == "current" and current.eligible
    assert [(o.target_id, o.path, o.content.data) for o in current.outputs] == [
        ("resource:payload", "Assets/data.bin", b"\x00authored")
    ]
    assert incoming.choice == "incoming" and incoming.eligible
    assert [(o.target_id, o.path, o.content.data) for o in incoming.outputs] == [
        ("resource:payload", "Assets/data.bin", b"abc")
    ]
    assert both.choice == "both" and both.eligible
    assert [(o.target_id, o.path, o.content.data) for o in both.outputs] == [
        ("resource:payload", "Assets/data.bin", b"\x00authored"),
        (
            "resource:payload:incoming:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            "Assets/data (incoming-ba7816bf).bin",
            b"abc",
        ),
    ]
    assert change.result is None and change.requires_decision
    assert review.assumptions and review.incoming_source_path == "Assets/data.bin"


def test_note_and_two_binary_facets_share_owner_without_stealing_associations():
    from brz2obsidian.contracts import AttachmentFacts, IdentityTargetFacts
    from tests.reconciliation.test_identity import inventory_item, with_subjects
    from tests.reconciliation.test_proposals import request

    facts = attachment_request()
    note = request(original=b"note", current=b"note", incoming=b"note").subjects[0]
    second = facts.subjects[0].model_copy(
        update={
            "facet": "attachment:second",
            "path": "Assets/second.bin",
            "baseline": note.baseline.model_copy(
                update={"content": note.current.content}
            ),
            "current": note.current.model_copy(update={"path": "Assets/second.bin"}),
            "incoming": note.incoming,
            "source_target": IdentityTargetFacts(
                normalized_path="assets/second.bin",
                containment="contained",
                status="safe",
            ),
            "attachment": AttachmentFacts(
                current_target_id="resource:second",
                affected_documents=(),
                allocation_candidates=(),
            ),
        }
    )
    facts = with_subjects(
        facts,
        (note, facts.subjects[0], second),
        (
            inventory_item(
                "note", "entry:opening", "Notes/Opening.md", b"note", facet="content"
            ),
            inventory_item(
                "asset-one",
                "entry:opening",
                "Assets/data.bin",
                b"\x00authored",
                facet="attachment:payload",
            ),
            inventory_item(
                "asset-two",
                "entry:opening",
                "Assets/second.bin",
                b"note",
                facet="attachment:second",
            ),
        ),
    )
    facts = facts.model_copy(update={"link_context": binary_context(facts)})
    proposal = reconcile(facts)
    assert [
        (c.facet, c.identity_review.selected_entry_id, c.disposition)
        for c in proposal.changes
    ] == [
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
    from tests.reconciliation.test_identity import (
        association,
        inventory_item,
        rename_decision,
    )
    from tests.reconciliation.test_proposals import request

    facts = request(original=b"note", current=b"note", incoming=b"note")
    unknown = inventory_item(
        "unknown-facet", "entry:opening", "Notes/Opening.md", b"note", facet=None
    )
    facts = facts.model_copy(update={"identity_inventory": (unknown,)})
    unresolved = reconcile(facts)
    assert unresolved.changes[0].identity_review.status == "unresolved"
    decision = association(
        facts, unresolved.changes[0].identity_review, "unknown-facet"
    )
    proposed = reconcile(
        facts.model_copy(update={"association_decisions": (decision,)})
    )
    assert proposed.changes[0].identity_review.status == "association_proposed"
    assert proposed.changes[0].identity_review.repair_required and not proposed.ready
    observed = reconcile(
        facts.model_copy(
            update={
                "identity_inventory": (unknown.model_copy(update={"facet": "content"}),)
            }
        )
    )
    assert observed.ready and observed.changes[0].identity_review.status == "matched"
    asset = unknown.model_copy(update={"facet": "attachment:payload"})
    wrong = facts.model_copy(update={"identity_inventory": (asset,)})
    review = reconcile(wrong).changes[0].identity_review
    assert (
        review.candidates[0].facet == "attachment:payload"
        and not review.candidates[0].eligible
    )
    stolen = reconcile(
        wrong.model_copy(
            update={
                "association_decisions": (association(wrong, review, asset.entry_id),)
            }
        )
    )
    assert not stolen.ready and stolen.changes[0].disposition == "refused"
    assert "unsafe_identity_decision" in {f.code for f in stolen.findings}
    raw = unknown.model_dump()
    del raw["facet"]
    with pytest.raises(ValidationError):
        IdentityInventoryItem.model_validate(raw)
    moved = facts.model_copy(
        update={
            "identity_inventory": (
                inventory_item(
                    "moved", "entry:opening", "My.md", b"note", facet="content"
                ),
            )
        }
    )
    action = rename_decision(
        moved, reconcile(moved).changes[0].rename_review, "source_path"
    )
    raw = action.model_dump()
    del raw["facet"]
    with pytest.raises(ValidationError):
        RenamePathDecision.model_validate(raw)
    with pytest.raises(ValidationError):
        reconcile(
            moved.model_copy(
                update={
                    "rename_decisions": (
                        action.model_copy(update={"facet": "attachment:unknown"}),
                    )
                }
            )
        )


def test_note_rename_cannot_apply_to_same_owner_asset_and_asset_move_keeps_exact_bytes():
    from tests.reconciliation.test_identity import (
        inventory_item,
        rename_decision,
        with_subjects,
    )
    from tests.reconciliation.test_proposals import request

    facts = attachment_request()
    asset = facts.subjects[0]
    note = request(original=b"note", current=b"note", incoming=b"note").subjects[0]
    facts = with_subjects(
        facts,
        (note, asset),
        (
            inventory_item("note", "entry:opening", "My.md", b"note", facet="content"),
            inventory_item(
                "asset",
                "entry:opening",
                "Keep/data.bin",
                b"\x00authored",
                facet="attachment:payload",
            ),
        ),
    )
    facts = facts.model_copy(update={"link_context": binary_context(facts)})
    offered = reconcile(facts)
    note_action = rename_decision(
        facts, offered.changes[0].rename_review, "source_path"
    )
    reviewed = reconcile(facts.model_copy(update={"rename_decisions": (note_action,)}))
    assert reviewed.changes[0].target_path == "Notes/Opening.md"
    assert (
        reviewed.changes[1].path == reviewed.changes[1].target_path == "Keep/data.bin"
    )
    assert reviewed.changes[1].current.data == b"\x00authored"
    wrong_scope = note_action.model_copy(update={"facet": "attachment:payload"})
    refused = reconcile(facts.model_copy(update={"rename_decisions": (wrong_scope,)}))
    assert refused.changes[0].target_path == "My.md"
    assert refused.changes[1].target_path == "Keep/data.bin"
    assert refused.changes[1].disposition == "stale"
    assert refused.changes[1].rename_review.status == "stale" and not refused.ready


def test_outer_links_expose_literal_qualified_wiki_markdown_alias_and_fragment_meaning():
    from brz2obsidian.contracts import (
        ExactContent,
        IdentityTargetFacts,
        ImportedItemIdentity,
        ReferenceTarget,
    )
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    target = ReferenceTarget(
        schema_id="brz2obsidian.reference-target",
        schema_version=1,
        target_id="note:guide",
        kind="note",
        canonical_path="Docs/Guide.md",
        identity=ImportedItemIdentity(
            module_id="synthetic-folio",
            collection_id="folio:collection",
            item_id="guide",
        ),
        target=IdentityTargetFacts(
            normalized_path="docs/guide.md", containment="contained", status="safe"
        ),
        representations=("Guide", "Docs/Guide", "Manual"),
        validation_fingerprint="guide:validated",
        status="safe",
    )
    state = interpret_link_target(
        ExactContent(data=b"# Overview\nBody ^proof\n"),
        target_id="note:guide",
        existence="present",
        memberships=(),
    )
    raw = b"Text [[Docs/Guide#Overview|Read me]] and [Block](Docs/Guide.md#^proof). [[Manual|Alias]]"
    parsed = interpret_links(
        ExactContent(data=raw),
        document_id="note:owner",
        source_path="Notes/Owner.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(state,),
        inventory="complete",
    )
    assert parsed.status == "supported" and parsed.issues == ()
    assert [
        (
            o.syntax,
            o.meaning.target_id,
            o.meaning.path,
            o.meaning.display_text,
            None
            if o.meaning.fragment is None
            else (o.meaning.fragment.kind, o.meaning.fragment.value),
        )
        for o in parsed.occurrences
    ] == [
        ("wiki", "note:guide", "Docs/Guide.md", "Read me", ("heading", "Overview")),
        ("markdown", "note:guide", "Docs/Guide.md", "Block", ("block", "proof")),
        ("wiki", "note:guide", "Docs/Guide.md", "Alias", None),
    ]
    assert all(
        o.meaning.status == "resolved" and o.meaning.target_identity.item_id == "guide"
        for o in parsed.occurrences
    )
    assert (
        raw[parsed.occurrences[0].span.start : parsed.occurrences[0].span.end]
        == b"[[Docs/Guide#Overview|Read me]]"
    )
    assert [o.occurrence_id for o in parsed.occurrences] == [
        "note:owner:link:0",
        "note:owner:link:1",
        "note:owner:link:2",
    ]


def target_for_links(
    target_id="note:guide", path="Docs/Guide.md", *, aliases=(), kind="note"
):
    from brz2obsidian.contracts import IdentityTargetFacts, ReferenceTarget

    return ReferenceTarget(
        schema_id="brz2obsidian.reference-target",
        schema_version=1,
        target_id=target_id,
        kind=kind,
        canonical_path=path,
        identity=None,
        target=IdentityTargetFacts(
            normalized_path=path.casefold(), containment="contained", status="safe"
        ),
        representations=aliases or (path,),
        validation_fingerprint=target_id + ":validated",
        status="safe",
    )


def test_relative_and_shortened_targets_use_complete_explicit_path_context():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    guide = target_for_links()
    other = target_for_links("note:other-guide", "Other/Guide.md")
    state = interpret_link_target(
        ExactContent(data=b"Guide body"),
        target_id="note:guide",
        existence="present",
        memberships=(),
    )
    other_state = state.model_copy(update={"target_id": "note:other-guide"})
    relative = interpret_links(
        ExactContent(data=b"[[../Docs/Guide|Read]] [Read](../Docs/Guide.md)"),
        document_id="note:owner",
        source_path="Notes/Owner.md",
        path_mode="relative",
        targets=(guide, other),
        target_facts=(state, other_state),
        inventory="complete",
    )
    assert [o.meaning.target_id for o in relative.occurrences] == [
        "note:guide",
        "note:guide",
    ]
    assert [o.query.value for o in relative.occurrences] == [
        "Docs/Guide",
        "Docs/Guide.md",
    ]
    short = interpret_links(
        ExactContent(data=b"[[Guide]] [[Docs/Guide|Qualified]]"),
        document_id="note:owner",
        source_path="Notes/Owner.md",
        path_mode="shortened",
        targets=(guide, other),
        target_facts=(state, other_state),
        inventory="complete",
    )
    assert short.occurrences[0].meaning.status == "ambiguous"
    assert short.occurrences[0].meaning.candidates == ("note:guide", "note:other-guide")
    assert (
        short.occurrences[1].meaning.status == "resolved"
        and short.occurrences[1].meaning.target_id == "note:guide"
    )


def test_link_interpreter_preserves_code_escaped_syntax_and_external_meaning():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    target = target_for_links()
    state = interpret_link_target(
        ExactContent(data=b"Guide"),
        target_id="note:guide",
        existence="present",
        memberships=(),
    )
    raw = b"`[[Docs/Guide]]`\n```md\n[[Docs/Guide]]\n```\n\\[[Docs/Guide]] [[Docs/Guide|Real]] [Web](https://example.com/#details)"
    parsed = interpret_links(
        ExactContent(data=raw),
        document_id="note:owner",
        source_path="Notes/Owner.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(state,),
        inventory="complete",
    )
    assert parsed.status == "supported"
    assert [(o.meaning.status, o.meaning.display_text) for o in parsed.occurrences] == [
        ("resolved", "Real"),
        ("external", "Web"),
    ]
    assert (
        parsed.occurrences[1].meaning.target_id is None
        and parsed.occurrences[1].meaning.fragment is None
    )
    assert parsed.content.data == raw


def test_encoded_markdown_angles_and_hierarchical_fragments_keep_byte_spans():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    target = target_for_links(path="Docs/With space.md")
    state = interpret_link_target(
        ExactContent(data=b"# Outer\n## Inner\nParagraph ^proof\n"),
        target_id="note:guide",
        existence="present",
        memberships=(),
    )
    raw = "é [[Docs/With space#Outer#Inner|Nested]] [Nested](<Docs/With%20space.md#Outer%23Inner>)".encode()
    parsed = interpret_links(
        ExactContent(data=raw),
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(state,),
        inventory="complete",
    )
    assert parsed.status == "supported"
    assert [o.meaning.status for o in parsed.occurrences] == ["resolved", "resolved"]
    assert [o.meaning.fragment.value for o in parsed.occurrences] == [
        "Outer#Inner",
        "Outer#Inner",
    ]
    assert parsed.occurrences[0].span.start == 3
    assert (
        raw[
            parsed.occurrences[1].destination_span.start : parsed.occurrences[
                1
            ].destination_span.end
        ]
        == b"<Docs/With%20space.md#Outer%23Inner>"
    )


def test_unsupported_link_syntax_and_incomplete_context_never_become_safe():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    target = target_for_links()
    state = interpret_link_target(
        ExactContent(data=b"# Same\n# Same\n"),
        target_id="note:guide",
        existence="present",
        memberships=(),
    )
    for raw in (
        b"[[Docs/Guide",
        b"[Nested [label]](Docs/Guide.md)",
        b'[Title](Docs/Guide.md "unsupported title")',
        b"[Bad](Docs/%GG.md)",
        b"[Bad](Docs/%FF.md)",
        b"[[Docs/Guide|Alias|Other]]",
        b"[[Docs/Guide#^]]",
        b"[Reference][guide]",
        b'<a href="Docs/Guide.md">Guide</a>',
        b"`unclosed [[Docs/Guide]]",
        b"[[../../Escape.md]]",
        b"\xff[[Docs/Guide]]",
    ):
        parsed = interpret_links(
            ExactContent(data=raw),
            document_id="owner",
            source_path="Owner.md",
            path_mode="relative",
            targets=(target,),
            target_facts=(state,),
            inventory="complete",
        )
        assert parsed.status == "unsupported" and parsed.issues, raw
        assert parsed.content.data == raw
    ambiguous = interpret_links(
        ExactContent(data=b"[[Docs/Guide#Same]]"),
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(state,),
        inventory="complete",
    )
    assert ambiguous.occurrences[0].meaning.status == "fragment_ambiguous"
    partial = interpret_links(
        ExactContent(data=b"[[Docs/Guide]]"),
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(state,),
        inventory="partial",
    )
    assert partial.occurrences[0].meaning.status == "inventory_uncertain"


def linked_attachment_request(
    *,
    payload_current=None,
    raw=b"[[Assets/data.bin|Keep first]] and [[Assets/data.bin|Redirect second]]",
):
    from brz2obsidian.contracts import ExactContent, LinkContext
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_identity import inventory_item

    facts = attachment_request()
    if payload_current is not None:
        current = facts.subjects[0].current.model_copy(
            update={"content": ExactContent(data=payload_current)}
        )
        facts = facts.model_copy(
            update={
                "subjects": (
                    facts.subjects[0].model_copy(update={"current": current}),
                ),
                "identity_inventory": (
                    facts.identity_inventory[0].model_copy(update={"current": current}),
                ),
            }
        )
    target = target_for_links("resource:payload", "Assets/data.bin", kind="resource")
    old_state = interpret_link_target(
        facts.subjects[0].current.content,
        target_id="resource:payload",
        existence="present",
        memberships=(),
    )
    new_state = interpret_link_target(
        facts.subjects[0].incoming,
        target_id="resource:payload",
        existence="present",
        memberships=(),
    )
    old_doc = interpret_links(
        ExactContent(data=raw),
        document_id="owner:note",
        source_path="Notes/Owner.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(old_state,),
        inventory="complete",
    )
    new_doc = interpret_links(
        ExactContent(data=raw),
        document_id="owner:note",
        source_path="Notes/Owner.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(new_state,),
        inventory="complete",
    )
    note_target = target_for_links("owner:note", "Notes/Owner.md").model_copy(
        update={"identity": facts.identity_inventory[0].identity}
    )
    note_state = interpret_link_target(
        ExactContent(data=raw),
        target_id="owner:note",
        existence="present",
        memberships=(),
    )
    context = LinkContext(
        schema_id="brz2obsidian.link-context",
        schema_version=1,
        inventory="complete",
        current_targets=(target, note_target),
        incoming_targets=(target, note_target),
        current_target_facts=(old_state, note_state),
        incoming_target_facts=(new_state, note_state),
        current_documents=(old_doc,),
        incoming_documents=(new_doc,),
    )
    subject = facts.subjects[0].model_copy(
        update={
            "attachment": facts.subjects[0].attachment.model_copy(
                update={"affected_documents": ("owner:note",)}
            )
        }
    )
    facts = facts.model_copy(
        update={
            "subjects": (subject,),
            "link_context": context,
            "identity_inventory": facts.identity_inventory
            + (
                inventory_item(
                    "owner-note",
                    "entry:opening",
                    "Notes/Owner.md",
                    raw,
                    facet="content",
                ),
            ),
        }
    )
    return facts


def test_associated_links_expose_each_old_incoming_and_secondary_meaning_without_redirect():
    facts = linked_attachment_request()
    (change,) = reconcile(facts).changes
    first, second = change.attachment_review.links
    assert [first.occurrence_id, second.occurrence_id] == [
        "owner:note:link:0",
        "owner:note:link:1",
    ]
    assert [first.old.display_text, second.old.display_text] == [
        "Keep first",
        "Redirect second",
    ]
    assert all(
        link.old.target_id == link.incoming.target_id == "resource:payload"
        for link in (first, second)
    )
    assert all(
        link.incoming.target_version
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        for link in (first, second)
    )
    assert (
        first.secondary.path
        == second.secondary.path
        == "Assets/data (incoming-ba7816bf).bin"
    )
    assert (
        first.secondary.target_id
        == "resource:payload:incoming:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert (
        first.secondary.display_text == "Keep first"
        and second.secondary.display_text == "Redirect second"
    )
    assert (
        first.choices
        == second.choices
        == ("keep_current", "use_incoming", "use_secondary")
    )
    assert (
        facts.link_context.current_documents[0].content.data
        == facts.link_context.incoming_documents[0].content.data
        == b"[[Assets/data.bin|Keep first]] and [[Assets/data.bin|Redirect second]]"
    )
    assert change.result is None and change.requires_decision


def test_current_link_context_binding_cannot_be_bypassed_by_safe_binary_keep():
    facts = attachment_request()
    subject = facts.subjects[0]
    unchanged = subject.model_copy(update={"incoming": subject.baseline.content})
    missing = reconcile(
        facts.model_copy(update={"subjects": (unchanged,), "link_context": None})
    )
    assert not missing.ready
    assert missing.changes[0].disposition == "refused"
    assert "link_context_unavailable" in {f.code for f in missing.findings}
    context = binary_context(facts)
    safe = reconcile(
        facts.model_copy(update={"subjects": (unchanged,), "link_context": context})
    )
    assert safe.ready and safe.changes[0].result.data == b"\x00authored"
    target = context.current_targets[0]
    unsafe = target.model_copy(
        update={"target": target.target.model_copy(update={"containment": "outside"})}
    )
    bad = context.model_copy(update={"current_targets": (unsafe,)})
    refused = reconcile(
        facts.model_copy(update={"subjects": (unchanged,), "link_context": bad})
    )
    assert not refused.ready and "link_context_invalid" in {
        f.code for f in refused.findings
    }
    discarded = context.model_copy(update={"incoming_targets": (unsafe,)})
    kept = reconcile(
        facts.model_copy(update={"subjects": (unchanged,), "link_context": discarded})
    )
    assert kept.ready and kept.changes[0].result.data == b"\x00authored"


def binary_context(facts):
    from brz2obsidian.contracts import LinkContext
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    targets, old_states, new_states = (), (), ()
    for entry in facts.identity_inventory:
        subject = next(
            (
                s
                for s in facts.subjects
                if s.item_id
                == (None if entry.identity is None else entry.identity.item_id)
                and s.facet == entry.facet
            ),
            None,
        )
        resource = subject is not None and subject.attachment is not None
        target_id = (
            subject.attachment.current_target_id
            if resource
            else "note:" + entry.entry_id
        )
        target = target_for_links(
            target_id, entry.current.path, kind="resource" if resource else "note"
        )
        if not resource:
            target = target.model_copy(update={"identity": entry.identity})
        targets += (target,)
        old_states += (
            interpret_link_target(
                entry.current.content,
                target_id=target_id,
                existence=entry.current.existence,
                memberships=(),
            ),
        )
        new_states += (
            interpret_link_target(
                entry.current.content if subject is None else subject.incoming,
                target_id=target_id,
                existence="present",
                memberships=(),
            ),
        )
    old_docs, new_docs = (), ()
    for target in targets:
        if target.kind != "resource":
            index = targets.index(target)
            old_docs += (
                interpret_links(
                    old_states[index].content,
                    document_id=target.target_id,
                    source_path=target.canonical_path,
                    path_mode="vault",
                    targets=targets,
                    target_facts=old_states,
                    inventory="complete",
                ),
            )
            new_docs += (
                interpret_links(
                    new_states[index].content,
                    document_id=target.target_id,
                    source_path=target.canonical_path,
                    path_mode="vault",
                    targets=targets,
                    target_facts=new_states,
                    inventory="complete",
                ),
            )
    return LinkContext(
        schema_id="brz2obsidian.link-context",
        schema_version=1,
        inventory="complete",
        current_targets=targets,
        incoming_targets=targets,
        current_target_facts=old_states,
        incoming_target_facts=new_states,
        current_documents=old_docs,
        incoming_documents=new_docs,
    )


def test_public_link_candidate_validation_rechecks_selected_meaning_and_separates_existing_warnings():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import validate_link_document
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    target = target_for_links()
    state = interpret_link_target(
        ExactContent(data=b"# Good\n"),
        target_id="note:guide",
        existence="present",
        memberships=(),
    )
    raw = ExactContent(data=b"[[Docs/Guide#Good|Read]] [[Missing|Old warning]]")
    old = interpret_links(
        raw,
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(state,),
        inventory="complete",
    )

    old_proof = baseline_for(old, (target,), (state,))

    def validate(document, states=(state,), baseline=old_proof):
        return validate_link_document(
            document,
            expected_content=document.content,
            expected_path="Owner.md",
            targets=(target,),
            target_facts=states,
            inventory="complete",
            baseline=baseline,
        )

    result = validate(old)
    assert result.valid
    assert [(f.code, f.blocking) for f in result.findings] == [
        ("existing_link_warning", False)
    ]
    wrong = old.occurrences[0].model_copy(
        update={
            "meaning": old.occurrences[0].meaning.model_copy(
                update={"target_id": "invented"}
            )
        }
    )
    assert not validate(
        old.model_copy(update={"occurrences": (wrong, old.occurrences[1])})
    ).valid
    changed_state = interpret_link_target(
        ExactContent(data=b"# Replaced\n"),
        target_id="note:guide",
        existence="present",
        memberships=(),
    )
    broken = interpret_links(
        raw,
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(changed_state,),
        inventory="complete",
    )
    harmed = validate(broken, (changed_state,))
    assert not harmed.valid and "link_harmed" in {f.code for f in harmed.findings}
    assert not validate(old, baseline=None).valid


def test_attachment_candidate_choices_bind_exact_offered_payloads_generation_and_registry():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import validate_attachment_candidate

    facts = attachment_request()
    for choice, payloads in (
        ("current", (b"\x00authored",)),
        ("incoming", (b"abc",)),
        ("both", (b"\x00authored", b"abc")),
    ):
        selection, candidate = attachment_candidate(facts, choice)
        result = validate_attachment_candidate(facts, selection, candidate)
        assert result.valid and not any(f.blocking for f in result.findings), (
            choice,
            result,
        )
        assert tuple(o.content.data for o in candidate.outputs) == payloads
        wrong_output = candidate.outputs[0].model_copy(
            update={
                "content": ExactContent(data=b"injected"),
                "content_version": "c6c33195e1ae7d352643ac91a36d0a6b9c4b51eaaf08cf49662ed6b1b30c39d2",
            }
        )
        assert not validate_attachment_candidate(
            facts,
            selection,
            candidate.model_copy(
                update={"outputs": (wrong_output,) + candidate.outputs[1:]}
            ),
        ).valid
    selection, candidate = attachment_candidate(facts, "current")
    assert not validate_attachment_candidate(
        facts, selection.model_copy(update={"generation": 2}), candidate
    ).valid
    assert not validate_attachment_candidate(
        facts, selection.model_copy(update={"reviewed_assumptions": ()}), candidate
    ).valid
    moved = candidate.outputs[0].model_copy(update={"path": "Arbitrary.bin"})
    assert not validate_attachment_candidate(
        facts, selection, candidate.model_copy(update={"outputs": (moved,)})
    ).valid


def attachment_candidate(facts, choice):
    from brz2obsidian.contracts import AttachmentCandidate, AttachmentSelection
    from brz2obsidian.obsidian import interpret_link_target

    proposal = reconcile(facts)
    change = next(c for c in proposal.changes if c.attachment_review is not None)
    alternative = next(
        a for a in change.attachment_review.alternatives if a.choice == choice
    )
    selection = AttachmentSelection(
        schema_id="brz2obsidian.attachment-selection",
        schema_version=1,
        proposal_id=facts.proposal_id,
        generation=facts.generation,
        item_id=change.item_id,
        facet=change.facet,
        reviewed_change_id=change.change_id,
        reviewed_assumptions=change.assumptions,
        choice=choice,
        link_choices=(),
        provenance="explicit_user",
    )
    context = facts.link_context
    base = next(t for t in context.current_targets if t.target_id == "resource:payload")
    targets = tuple(t for t in context.current_targets if t.target_id != base.target_id)
    states = tuple(
        s for s in context.current_target_facts if s.target_id != base.target_id
    )
    for output in alternative.outputs:
        from brz2obsidian.contracts import IdentityTargetFacts

        target = base.model_copy(
            update={
                "target_id": output.target_id,
                "canonical_path": output.path,
                "target": IdentityTargetFacts(
                    normalized_path=output.path.casefold(),
                    containment="contained",
                    status="safe",
                ),
                "representations": (output.path,),
            }
        )
        targets += (target,)
        states += (
            interpret_link_target(
                output.content,
                target_id=output.target_id,
                existence="present",
                memberships=(),
            ),
        )
    return selection, AttachmentCandidate(
        schema_id="brz2obsidian.attachment-candidate",
        schema_version=1,
        outputs=alternative.outputs,
        documents=context.current_documents,
        targets=targets,
        target_facts=states,
    )


def test_both_requires_each_redirect_and_validates_edited_link_tokens_without_global_replacement():
    from brz2obsidian.contracts import ExactContent, LinkOccurrenceChoice
    from brz2obsidian.core import validate_attachment_candidate
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    facts = linked_attachment_request()
    selection, candidate = attachment_candidate(facts, "both")
    assert validate_attachment_candidate(facts, selection, candidate).valid
    old = facts.link_context.current_documents[0]
    raw = b"[[Assets/data.bin|Keep first]] and [Second edited alias](Assets/data%20%28incoming-ba7816bf%29.bin)"
    doc = interpret_links(
        ExactContent(data=raw),
        document_id=old.document_id,
        source_path=old.source_path,
        path_mode="vault",
        targets=candidate.targets,
        target_facts=candidate.target_facts,
        inventory="complete",
    )
    changed_note = interpret_link_target(
        doc.content, target_id="owner:note", existence="present", memberships=()
    )
    states = tuple(
        changed_note if state.target_id == "owner:note" else state
        for state in candidate.target_facts
    )
    edited = candidate.model_copy(update={"documents": (doc,), "target_facts": states})
    assert not validate_attachment_candidate(facts, selection, edited).valid
    choice = LinkOccurrenceChoice(
        document_id=old.document_id,
        occurrence_id=old.occurrences[1].occurrence_id,
        old=old.occurrences[1].meaning,
        replacement=b"[Second edited alias](Assets/data%20%28incoming-ba7816bf%29.bin)",
        selected=doc.occurrences[1].meaning,
        expected_memberships=(),
        provenance="explicit_user",
    )
    selected = selection.model_copy(update={"link_choices": (choice,)})
    result = validate_attachment_candidate(facts, selected, edited)
    assert result.valid, result
    assert doc.occurrences[0].meaning.target_id == "resource:payload"
    assert (
        doc.occurrences[1].meaning.target_id
        == "resource:payload:incoming:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert doc.occurrences[1].meaning.display_text == "Second edited alias"
    # Extra prose changes are outside this per-occurrence choice.
    altered = doc.model_copy(
        update={"content": ExactContent(data=raw + b" injected prose")}
    )
    assert not validate_attachment_candidate(
        facts, selected, edited.model_copy(update={"documents": (altered,)})
    ).valid
    # Replacing at the original path changes meaning even when token bytes match.
    incoming_selection, incoming = attachment_candidate(facts, "incoming")
    assert not validate_attachment_candidate(facts, incoming_selection, incoming).valid


def test_complete_attachment_context_cannot_omit_known_note_or_change_unselected_state():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import validate_attachment_candidate

    facts = linked_attachment_request()
    selection, candidate = attachment_candidate(facts, "both")
    altered = tuple(
        state.model_copy(update={"content": ExactContent(data=b"unreviewed note")})
        if state.target_id == "owner:note"
        else state
        for state in candidate.target_facts
    )
    assert not validate_attachment_candidate(
        facts, selection, candidate.model_copy(update={"target_facts": altered})
    ).valid
    subject = facts.subjects[0]
    hidden = subject.model_copy(
        update={
            "attachment": subject.attachment.model_copy(
                update={"affected_documents": ()}
            )
        }
    )
    context = facts.link_context.model_copy(
        update={"current_documents": (), "incoming_documents": ()}
    )
    omitted = reconcile(
        facts.model_copy(update={"subjects": (hidden,), "link_context": context})
    )
    assert omitted.changes[0].disposition == "refused"
    assert "link_context_unavailable" in {f.code for f in omitted.findings}


def test_fragment_evidence_must_bind_available_target_bytes_and_ignore_code_headings():
    from brz2obsidian.contracts import ExactContent, LinkFragment
    from brz2obsidian.core import validate_link_document
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    target = target_for_links()
    state = interpret_link_target(
        ExactContent(data=b"```md\n# Hidden\nParagraph ^hidden\n```\n# Visible\n"),
        target_id="note:guide",
        existence="present",
        memberships=(),
    )
    assert [(f.kind, f.value) for f in state.fragments] == [("heading", "Visible")]
    forged = state.model_copy(
        update={
            "fragments": state.fragments
            + (LinkFragment(kind="heading", value="Invented"),)
        }
    )
    doc = interpret_links(
        ExactContent(data=b"[[Docs/Guide#Invented]]"),
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(forged,),
        inventory="complete",
    )
    assert not validate_link_document(
        doc,
        expected_content=doc.content,
        expected_path=doc.source_path,
        targets=(target,),
        target_facts=(forged,),
        inventory="complete",
    ).valid


def test_both_allocation_checks_inventory_ancestor_case_and_other_prospective_version_targets():
    from brz2obsidian.contracts import AttachmentDestination, IdentityTargetFacts
    from tests.reconciliation.test_identity import inventory_item, with_subjects

    facts = attachment_request()
    path = "Assets/data (incoming-ba7816bf).bin"
    for occupied in (path.upper(), "Assets", path + "/child.bin"):
        changed = facts.model_copy(
            update={
                "identity_inventory": facts.identity_inventory
                + (
                    inventory_item(
                        "occupied",
                        "different",
                        occupied,
                        b"existing",
                        facet="attachment:other",
                    ),
                )
            }
        )
        review = reconcile(changed).changes[0].attachment_review
        assert not review.alternatives[2].eligible
        assert review.alternatives[2].unavailable_reasons == ("collision",)
        assert review.alternatives[0].eligible and review.alternatives[1].eligible
    subject = facts.subjects[0]
    second = subject.model_copy(
        update={
            "facet": "attachment:second",
            "current": subject.current.model_copy(update={"path": "Assets/data.dat"}),
            "attachment": subject.attachment.model_copy(
                update={"current_target_id": "resource:second"}
            ),
        }
    )
    second_entry = facts.identity_inventory[0].model_copy(
        update={
            "entry_id": "asset-two",
            "facet": second.facet,
            "current": second.current,
            "target": IdentityTargetFacts(
                normalized_path="assets/data.dat",
                status="safe",
                containment="contained",
            ),
        }
    )
    multiple = with_subjects(
        facts, (subject, second), facts.identity_inventory + (second_entry,)
    )
    multiple = multiple.model_copy(update={"link_context": binary_context(multiple)})
    proposal = reconcile(multiple)
    assert all(
        not c.attachment_review.alternatives[2].eligible for c in proposal.changes
    )
    # A second explicitly safe version slot remains inspectable after the first collides.
    fallback = AttachmentDestination(
        path="Assets/data (incoming-ba7816bf)-2.bin",
        target=IdentityTargetFacts(
            normalized_path="assets/data (incoming-ba7816bf)-2.bin",
            status="safe",
            containment="contained",
        ),
    )
    subject = subject.model_copy(
        update={
            "attachment": subject.attachment.model_copy(
                update={
                    "allocation_candidates": subject.attachment.allocation_candidates
                    + (fallback,)
                }
            )
        }
    )
    retried = reconcile(multiple.model_copy(update={"subjects": (subject, second)}))
    assert (
        retried.changes[0].attachment_review.alternatives[2].outputs[1].path
        == "Assets/data (incoming-ba7816bf)-2.bin"
    )


def test_selected_memberships_share_file_identity_across_note_category_roles_and_refuse_unsafe_state():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import validate_link_document
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_memberships import target as membership_target

    category = membership_target("a", "category", "[[A]]", "Targets/a.md")
    note = category.model_copy(update={"kind": "note"})
    raw = ExactContent(data=b'---\ncategories:\n  - "[[A]]"\n---\n# Heading\n')
    state = interpret_link_target(
        raw,
        target_id="a",
        existence="present",
        memberships=("a",),
        membership_targets=(category,),
    )
    doc = interpret_links(
        ExactContent(data=b"[[Targets/a#Heading|Read A]]"),
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(note,),
        target_facts=(state,),
        inventory="complete",
    )

    def validate(target_state):
        return validate_link_document(
            doc,
            expected_content=doc.content,
            expected_path=doc.source_path,
            targets=(note,),
            target_facts=(target_state,),
            inventory="complete",
        )

    assert validate(state).valid
    bad_category = category.model_copy(
        update={"target": category.target.model_copy(update={"containment": "outside"})}
    )
    membership = state.structure.memberships[0]
    entry = membership.entries[0].model_copy(update={"target": bad_category})
    bad_structure = state.structure.model_copy(
        update={"memberships": (membership.model_copy(update={"entries": (entry,)}),)}
    )
    assert not validate(state.model_copy(update={"structure": bad_structure})).valid


def test_known_gaps_intentional_absence_and_unsafe_affected_warning_remain_distinct():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import validate_link_document
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    target = target_for_links()
    for existence, valid in (
        ("known_source_gap", True),
        ("intentionally_uncreated", True),
        ("missing", False),
        ("unknown", False),
    ):
        state = interpret_link_target(
            None, target_id="note:guide", existence=existence, memberships=()
        )
        doc = interpret_links(
            ExactContent(data=b"[[Docs/Guide|Read]]"),
            document_id="owner",
            source_path="Owner.md",
            path_mode="vault",
            targets=(target,),
            target_facts=(state,),
            inventory="complete",
        )
        assert doc.occurrences[0].meaning.status == existence
        result = validate_link_document(
            doc,
            expected_content=doc.content,
            expected_path=doc.source_path,
            targets=(target,),
            target_facts=(state,),
            inventory="complete",
            baseline=baseline_for(doc, (target,), (state,)),
            affected_target_ids=("note:guide",),
        )
        assert result.valid is valid
    state = interpret_link_target(
        ExactContent(data=b"# Good\n"),
        target_id="note:guide",
        existence="present",
        memberships=(),
    )
    unsafe = target.model_copy(
        update={"target": target.target.model_copy(update={"containment": "outside"})}
    )
    doc = interpret_links(
        ExactContent(data=b"[[Docs/Guide]]"),
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(unsafe,),
        target_facts=(state,),
        inventory="complete",
    )
    affected = validate_link_document(
        doc,
        expected_content=doc.content,
        expected_path=doc.source_path,
        targets=(unsafe,),
        target_facts=(state,),
        inventory="complete",
        baseline=baseline_for(doc, (unsafe,), (state,)),
        affected_target_ids=("note:guide",),
    )
    assert not affected.valid
    unrelated = validate_link_document(
        doc,
        expected_content=doc.content,
        expected_path=doc.source_path,
        targets=(unsafe,),
        target_facts=(state,),
        inventory="complete",
        baseline=baseline_for(doc, (unsafe,), (state,)),
    )
    assert unrelated.valid and all(not f.blocking for f in unrelated.findings)


def test_incoming_payload_requires_explicit_same_token_meaning_review_and_refuses_unoffered_redirect():
    from brz2obsidian.contracts import ExactContent, LinkOccurrenceChoice
    from brz2obsidian.core import validate_attachment_candidate
    from brz2obsidian.obsidian import interpret_links

    facts = linked_attachment_request()
    selection, candidate = attachment_candidate(facts, "incoming")
    old = facts.link_context.current_documents[0]
    doc = interpret_links(
        old.content,
        document_id=old.document_id,
        source_path=old.source_path,
        path_mode=old.path_mode,
        targets=candidate.targets,
        target_facts=candidate.target_facts,
        inventory="complete",
    )
    choices = tuple(
        LinkOccurrenceChoice(
            document_id=old.document_id,
            occurrence_id=before.occurrence_id,
            old=before.meaning,
            replacement=after.raw,
            selected=after.meaning,
            expected_memberships=(),
            provenance="explicit_user",
        )
        for before, after in zip(old.occurrences, doc.occurrences, strict=True)
    )
    selection = selection.model_copy(update={"link_choices": choices})
    candidate = candidate.model_copy(update={"documents": (doc,)})
    assert validate_attachment_candidate(facts, selection, candidate).valid
    assert doc.content.data == old.content.data
    assert (
        doc.occurrences[0].meaning.target_version
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    # A safe unrelated note is not an offered attachment target.
    raw = b"[[Notes/Owner|Other target]] and [[Assets/data.bin|Redirect second]]"
    changed = interpret_links(
        ExactContent(data=raw),
        document_id=old.document_id,
        source_path=old.source_path,
        path_mode=old.path_mode,
        targets=candidate.targets,
        target_facts=candidate.target_facts,
        inventory="complete",
    )
    from brz2obsidian.obsidian import interpret_link_target

    note_state = interpret_link_target(
        changed.content, target_id="owner:note", existence="present", memberships=()
    )
    states = tuple(
        note_state if s.target_id == "owner:note" else s for s in candidate.target_facts
    )
    changed = interpret_links(
        ExactContent(data=raw),
        document_id=old.document_id,
        source_path=old.source_path,
        path_mode=old.path_mode,
        targets=candidate.targets,
        target_facts=states,
        inventory="complete",
    )
    unoffered = choices[0].model_copy(
        update={
            "replacement": changed.occurrences[0].raw,
            "selected": changed.occurrences[0].meaning,
        }
    )
    result = validate_attachment_candidate(
        facts,
        selection.model_copy(update={"link_choices": (unoffered, choices[1])}),
        candidate.model_copy(update={"documents": (changed,), "target_facts": states}),
    )
    assert not result.valid and "attachment_link_choice_invalid" in {
        f.code for f in result.findings
    }


def test_attachment_choices_expose_scoped_semantic_dependencies_without_locator_churn():
    from brz2obsidian.contracts import ExactContent, ImmutableContentReference

    facts = linked_attachment_request()
    original = reconcile(facts).changes[0]
    subject = facts.subjects[0]
    incoming = ExactContent(
        data=b"abc",
        reference=ImmutableContentReference(
            content_id="different-archive-locator",
            sha256="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            size=3,
        ),
    )
    same = reconcile(
        facts.model_copy(
            update={"subjects": (subject.model_copy(update={"incoming": incoming}),)}
        )
    ).changes[0]
    assert same.change_id == original.change_id
    assert {a.kind for a in original.attachment_review.assumptions} == {
        "attachment",
        "link",
    }
    context = facts.link_context
    target = context.current_targets[0]
    unsafe = target.model_copy(
        update={"target": target.target.model_copy(update={"containment": "unknown"})}
    )
    changed = reconcile(
        facts.model_copy(
            update={
                "link_context": context.model_copy(
                    update={"current_targets": (unsafe,) + context.current_targets[1:]}
                )
            }
        )
    ).changes[0]
    assert changed.change_id != original.change_id
    assert changed.disposition == "refused"
    # Unrelated target payload changes in a complete, consistently rebound registry do not affect this choice.
    from brz2obsidian.obsidian import interpret_link_target
    from tests.reconciliation.test_identity import inventory_item

    unrelated = target_for_links(
        "resource:unrelated", "Assets/unrelated.bin", kind="resource"
    )

    def with_other(data):
        state = interpret_link_target(
            ExactContent(data=data),
            target_id=unrelated.target_id,
            existence="present",
            memberships=(),
        )
        inventory = facts.identity_inventory + (
            inventory_item(
                "unrelated",
                "other-owner",
                "Assets/unrelated.bin",
                data,
                facet="attachment:unrelated",
            ),
        )
        augmented = context.model_copy(
            update={
                "current_targets": context.current_targets + (unrelated,),
                "incoming_targets": context.incoming_targets + (unrelated,),
                "current_target_facts": context.current_target_facts + (state,),
                "incoming_target_facts": context.incoming_target_facts + (state,),
            }
        )
        return reconcile(
            facts.model_copy(
                update={"identity_inventory": inventory, "link_context": augmented}
            )
        ).changes[0]

    assert (
        with_other(b"one").change_id
        == with_other(b"two").change_id
        == original.change_id
    )


def test_unavailable_link_content_and_corrupt_or_incomplete_candidates_refuse_without_new_authority():
    import pytest
    from pydantic import ValidationError

    from brz2obsidian.contracts import AttachmentSelection, ExactContent
    from brz2obsidian.core import validate_attachment_candidate, validate_link_document
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    target = target_for_links()
    unavailable = interpret_link_target(
        None, target_id="note:guide", existence="present", memberships=()
    )
    doc = interpret_links(
        ExactContent(data=b"[[Docs/Guide]]"),
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(unavailable,),
        inventory="complete",
    )
    assert doc.occurrences[0].meaning.status == "unknown"
    assert not validate_link_document(
        doc,
        expected_content=doc.content,
        expected_path="Owner.md",
        targets=(target,),
        target_facts=(unavailable,),
        inventory="complete",
    ).valid
    facts = attachment_request()
    selection, candidate = attachment_candidate(facts, "current")
    assert not validate_attachment_candidate(
        facts, selection, candidate.model_copy(update={"targets": ()})
    ).valid
    assert not validate_attachment_candidate(
        facts,
        selection,
        candidate.model_copy(update={"target_facts": candidate.target_facts * 2}),
    ).valid
    assert not validate_attachment_candidate(
        facts, selection.model_copy(update={"facet": "attachment:other"}), candidate
    ).valid
    # Internally consistent but unoffered payload must still fail exact offered-byte comparison.
    injected = candidate.outputs[0].model_copy(
        update={
            "content": ExactContent(data=b"abc"),
            "content_version": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        }
    )
    assert not validate_attachment_candidate(
        facts, selection, candidate.model_copy(update={"outputs": (injected,)})
    ).valid
    assert not validate_attachment_candidate(
        facts.model_copy(update={"inventory": "partial"}), selection, candidate
    ).valid
    for version in (True, 1.0, "1"):
        with pytest.raises(ValidationError):
            AttachmentSelection.model_validate(
                selection.model_dump() | {"schema_version": version}
            )
    with pytest.raises(ValueError):
        AttachmentSelection.model_validate_json(
            selection.model_dump_json().replace(
                '"generation":1', '"generation":1,"generation":2'
            )
        )
    with pytest.raises(ValidationError):
        AttachmentSelection.model_validate(
            selection.model_dump() | {"choice": "edited"}
        )


def test_unavailable_both_slots_keep_current_incoming_inspectable_and_declared_incoming_extension():
    from brz2obsidian.contracts import AttachmentDestination, IdentityTargetFacts
    from brz2obsidian.core import validate_attachment_candidate

    facts = attachment_request()
    subject = facts.subjects[0]
    for slots, reason in (
        ((), "allocation_unavailable"),
        (
            (
                AttachmentDestination(
                    path="Arbitrary.bin",
                    target=IdentityTargetFacts(
                        normalized_path="arbitrary.bin",
                        status="safe",
                        containment="contained",
                    ),
                ),
            ),
            "unsafe_target",
        ),
        (
            (
                subject.attachment.allocation_candidates[0].model_copy(
                    update={
                        "target": subject.source_target.model_copy(
                            update={"containment": "unknown"}
                        )
                    }
                ),
            ),
            "unsafe_target",
        ),
    ):
        updated = subject.model_copy(
            update={
                "attachment": subject.attachment.model_copy(
                    update={"allocation_candidates": slots}
                )
            }
        )
        changed = facts.model_copy(update={"subjects": (updated,)})
        current, incoming, both = (
            reconcile(changed).changes[0].attachment_review.alternatives
        )
        assert current.eligible and incoming.eligible
        assert not both.eligible and both.unavailable_reasons == (reason,)
        selection, candidate = attachment_candidate(changed, "both")
        assert not validate_attachment_candidate(changed, selection, candidate).valid
    path = "Assets/data (incoming-ba7816bf).pdf"
    slot = AttachmentDestination(
        path=path,
        target=IdentityTargetFacts(
            normalized_path=path.casefold(), status="safe", containment="contained"
        ),
    )
    changed = subject.model_copy(
        update={
            "path": "Incoming/renamed.pdf",
            "source_target": IdentityTargetFacts(
                normalized_path="incoming/renamed.pdf",
                status="safe",
                containment="contained",
            ),
            "attachment": subject.attachment.model_copy(
                update={"allocation_candidates": (slot,)}
            ),
        }
    )
    change = reconcile(facts.model_copy(update={"subjects": (changed,)})).changes[0]
    assert (
        change.attachment_review.alternatives[2].outputs[1].path
        == "Assets/data (incoming-ba7816bf).pdf"
    )
    assert (
        change.target_path == "Assets/data.bin"
        and change.rename_review.status == "offered"
    )


def test_registry_exact_wiki_representations_resolve_without_duplicate_file_roles():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import validate_link_document
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_memberships import target

    category = target("a", "category", "[[A]]")
    state = interpret_link_target(
        ExactContent(data=b"# Heading\n"),
        target_id="a",
        existence="present",
        memberships=(),
    )
    doc = interpret_links(
        ExactContent(data=b"[[A#Heading|Display alias]]"),
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(category,),
        target_facts=(state,),
        inventory="complete",
    )
    assert (
        doc.occurrences[0].meaning.target_id == "a"
        and doc.occurrences[0].meaning.status == "resolved"
    )
    assert doc.occurrences[0].meaning.display_text == "Display alias"
    assert validate_link_document(
        doc,
        expected_content=doc.content,
        expected_path="Owner.md",
        targets=(category,),
        target_facts=(state,),
        inventory="complete",
    ).valid


def test_both_does_not_offer_old_fragment_for_secondary_payload_without_that_fragment():
    from brz2obsidian.core import validate_attachment_candidate

    facts = linked_attachment_request(
        payload_current=b"# Local\n", raw=b"[[Assets/data.bin#Local|Read]]"
    )
    review = reconcile(facts).changes[0].attachment_review
    (link,) = review.links
    assert link.old.status == "resolved" and link.old.fragment.value == "Local"
    assert link.incoming.status == "fragment_missing"
    assert link.secondary.status == "fragment_missing"
    assert link.choices == ("keep_current",)
    selection, candidate = attachment_candidate(facts, "both")
    assert validate_attachment_candidate(facts, selection, candidate).valid


def test_complete_context_refuses_unobserved_present_target_without_claiming_uncreated_target_missing():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.obsidian import interpret_link_target

    facts = attachment_request()
    context = facts.link_context
    other = target_for_links("resource:unobserved", "Assets/Other.bin", kind="resource")
    state = interpret_link_target(
        ExactContent(data=b"unobserved"),
        target_id=other.target_id,
        existence="present",
        memberships=(),
    )
    augmented = context.model_copy(
        update={
            "current_targets": context.current_targets + (other,),
            "current_target_facts": context.current_target_facts + (state,),
        }
    )
    result = reconcile(facts.model_copy(update={"link_context": augmented}))
    assert result.changes[0].disposition == "refused"
    assert "link_context_invalid" in {f.code for f in result.findings}
    uncreated = interpret_link_target(
        None,
        target_id=other.target_id,
        existence="intentionally_uncreated",
        memberships=(),
    )
    result = reconcile(
        facts.model_copy(
            update={
                "link_context": augmented.model_copy(
                    update={
                        "current_target_facts": context.current_target_facts
                        + (uncreated,)
                    }
                )
            }
        )
    )
    assert result.changes[0].disposition == "unresolved"


def test_deliberate_deletion_keeps_absence_while_link_intent_remains_independently_reported():
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    facts = linked_attachment_request(raw=b"[[Assets/data.bin|Deleted resource]]")
    subject = facts.subjects[0]
    absent = subject.current.model_copy(update={"existence": "absent", "content": None})
    subject = subject.model_copy(
        update={"current": absent, "incoming": subject.baseline.content}
    )
    inventory = (
        facts.identity_inventory[0].model_copy(update={"current": absent}),
    ) + facts.identity_inventory[1:]
    context = facts.link_context

    def compare(existence):
        state = interpret_link_target(
            None, target_id="resource:payload", existence=existence, memberships=()
        )
        states = (state,) + context.current_target_facts[1:]
        old = context.current_documents[0]
        doc = interpret_links(
            old.content,
            document_id=old.document_id,
            source_path=old.source_path,
            path_mode=old.path_mode,
            targets=context.current_targets,
            target_facts=states,
            inventory="complete",
        )
        updated = context.model_copy(
            update={"current_target_facts": states, "current_documents": (doc,)}
        )
        return reconcile(
            facts.model_copy(
                update={
                    "subjects": (subject,),
                    "identity_inventory": inventory,
                    "link_context": updated,
                }
            )
        )

    intentional = compare("intentionally_uncreated")
    assert intentional.ready and intentional.changes[0].disposition == "local_deleted"
    assert intentional.changes[0].result is None
    assert (
        intentional.changes[0].attachment_review.links[0].old.status
        == "intentionally_uncreated"
    )
    missing = compare("missing")
    assert not missing.ready and missing.changes[0].disposition == "refused"
    assert missing.changes[0].result is None
    assert missing.changes[0].attachment_review.links[0].old.status == "missing"


def test_recalled_binary_keep_never_approves_unsafe_current_target_or_active_operation():
    from tests.reconciliation.test_absence import remembered

    facts = attachment_request()
    memory = remembered(facts)
    replay = facts.model_copy(update={"source_version_memory": (memory,)})
    assert reconcile(replay).ready
    context = facts.link_context
    target = context.current_targets[0]
    unsafe = target.model_copy(
        update={"target": target.target.model_copy(update={"containment": "outside"})}
    )
    refused = reconcile(
        replay.model_copy(
            update={
                "link_context": context.model_copy(
                    update={"current_targets": (unsafe,)}
                )
            }
        )
    )
    assert not refused.ready and refused.changes[0].result is None
    operation = next(s for s in facts.safety_facts if s.kind == "operation")
    active = operation.model_copy(update={"status": "unsafe"})
    blocked = reconcile(
        replay.model_copy(
            update={
                "safety_facts": tuple(
                    active if s.key == operation.key else s for s in facts.safety_facts
                )
            }
        )
    )
    assert not blocked.ready and blocked.changes[0].result is None


def test_candidate_target_safety_and_link_choice_record_boundaries_are_independent_of_payload_equality():
    from brz2obsidian.contracts import LinkOccurrenceChoice
    from brz2obsidian.core import validate_attachment_candidate

    facts = linked_attachment_request()
    selection, candidate = attachment_candidate(facts, "both")
    secondary = candidate.targets[-1]
    unsafe = secondary.model_copy(
        update={
            "target": secondary.target.model_copy(update={"containment": "outside"})
        }
    )
    assert not validate_attachment_candidate(
        facts,
        selection,
        candidate.model_copy(update={"targets": candidate.targets[:-1] + (unsafe,)}),
    ).valid
    wrong_path = secondary.model_copy(update={"canonical_path": "Assets/data.bin"})
    assert not validate_attachment_candidate(
        facts,
        selection,
        candidate.model_copy(
            update={"targets": candidate.targets[:-1] + (wrong_path,)}
        ),
    ).valid
    assert not validate_attachment_candidate(
        facts, selection, candidate.model_copy(update={"documents": ()})
    ).valid
    old = facts.link_context.current_documents[0].occurrences[0]
    choice = LinkOccurrenceChoice(
        document_id="owner:note",
        occurrence_id=old.occurrence_id,
        old=old.meaning,
        replacement=old.raw,
        selected=old.meaning,
        expected_memberships=(),
        provenance="explicit_user",
    )
    assert validate_attachment_candidate(
        facts, selection.model_copy(update={"link_choices": (choice,)}), candidate
    ).valid
    for choices in (
        (choice, choice),
        (choice.model_copy(update={"occurrence_id": "unknown"}),),
        (choice.model_copy(update={"expected_memberships": ("invented",)}),),
        (choice.model_copy(update={"selected": None}),),
    ):
        result = validate_attachment_candidate(
            facts, selection.model_copy(update={"link_choices": choices}), candidate
        )
        assert not result.valid
        assert "attachment_link_choice_invalid" in {f.code for f in result.findings}


def test_link_document_validation_refuses_unbound_partial_unsupported_and_duplicate_context():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import validate_link_document
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    target = target_for_links()
    state = interpret_link_target(
        ExactContent(data=b"# Good\n"),
        target_id="note:guide",
        existence="present",
        memberships=(),
    )
    doc = interpret_links(
        ExactContent(data=b"[[Docs/Guide#Good]]"),
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(state,),
        inventory="complete",
    )

    def validate(document=doc, **changes):
        args = {
            "expected_content": doc.content,
            "expected_path": "Owner.md",
            "targets": (target,),
            "target_facts": (state,),
            "inventory": "complete",
        }
        args.update(changes)
        return validate_link_document(document, **args)

    assert not validate(expected_content=ExactContent(data=b"other")).valid
    assert not validate(expected_path="Other.md").valid
    assert not validate(inventory="partial").valid
    assert not validate(target_facts=(state, state)).valid
    assert not validate(targets=(target, target)).valid
    assert not validate(
        baseline=baseline_for(
            doc.model_copy(update={"document_id": "other"}), (target,), (state,)
        )
    ).valid
    unsupported = interpret_links(
        ExactContent(data=b"[[unclosed"),
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(state,),
        inventory="complete",
    )
    assert not validate(unsupported, expected_content=unsupported.content).valid


def test_unsupported_indispensable_html_shortcut_and_formatted_heading_are_never_claimed_safe():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    target = target_for_links()
    state = interpret_link_target(
        ExactContent(data=b"# **Formatted**\n"),
        target_id="note:guide",
        existence="present",
        memberships=(),
    )
    assert state.interpretation == "unsupported"
    for raw in (
        b'<img src="Docs/Guide.md">',
        b"[guide]\n[guide]: Docs/Guide.md",
        b"```md\n[[Docs/Guide]]",
    ):
        doc = interpret_links(
            ExactContent(data=raw),
            document_id="owner",
            source_path="Owner.md",
            path_mode="vault",
            targets=(target,),
            target_facts=(state,),
            inventory="complete",
        )
        assert doc.status == "unsupported" and doc.issues


def test_both_allocation_cannot_duplicate_declared_uncreated_target_meaning():
    from brz2obsidian.obsidian import interpret_link_target

    facts = attachment_request()
    target = target_for_links(
        "resource:intentionally-uncreated",
        "Assets/data (incoming-ba7816bf).bin",
        kind="resource",
    )
    state = interpret_link_target(
        None,
        target_id=target.target_id,
        existence="intentionally_uncreated",
        memberships=(),
    )
    context = facts.link_context
    context = context.model_copy(
        update={
            "current_targets": context.current_targets + (target,),
            "current_target_facts": context.current_target_facts + (state,),
        }
    )
    result = reconcile(facts.model_copy(update={"link_context": context}))
    assert result.changes[0].attachment_review.alternatives[2].unavailable_reasons == (
        "collision",
    )


def test_affected_document_target_safety_is_checked_before_preservation_or_link_editing():
    from brz2obsidian.core import validate_attachment_candidate

    facts = linked_attachment_request()
    context = facts.link_context
    note = context.current_targets[1]
    unsafe = note.model_copy(
        update={"target": note.target.model_copy(update={"containment": "outside"})}
    )
    facts = facts.model_copy(
        update={
            "link_context": context.model_copy(
                update={"current_targets": (context.current_targets[0], unsafe)}
            )
        }
    )
    result = reconcile(facts)
    assert result.changes[0].disposition == "refused"
    assert "link_current_unsafe" in {f.code for f in result.findings}
    selection, candidate = attachment_candidate(facts, "current")
    assert not validate_attachment_candidate(facts, selection, candidate).valid


def test_corrupt_external_cache_cannot_hide_retained_internal_query_from_current_preservation():
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    facts = linked_attachment_request(
        raw=b"[[Assets/data.bin#Absent|Unsafe affected fragment]]"
    )
    subject = facts.subjects[0]
    subject = subject.model_copy(
        update={
            "incoming": subject.baseline.content,
            "attachment": subject.attachment.model_copy(
                update={"affected_documents": ()}
            ),
        }
    )
    context = facts.link_context
    incoming_state = interpret_link_target(
        subject.incoming,
        target_id="resource:payload",
        existence="present",
        memberships=(),
    )
    incoming_states = (incoming_state,) + context.incoming_target_facts[1:]
    old = context.current_documents[0]
    incoming_doc = interpret_links(
        old.content,
        document_id=old.document_id,
        source_path=old.source_path,
        path_mode=old.path_mode,
        targets=context.incoming_targets,
        target_facts=incoming_states,
        inventory="complete",
    )
    context = context.model_copy(
        update={
            "incoming_target_facts": incoming_states,
            "incoming_documents": (incoming_doc,),
        }
    )
    facts = facts.model_copy(update={"subjects": (subject,), "link_context": context})
    before = reconcile(facts)
    assert not before.ready and before.changes[0].disposition == "refused"
    assert "link_current_unsafe" in {f.code for f in before.findings}
    (occurrence,) = old.occurrences
    assert (
        occurrence.query.value == "Assets/data.bin"
        and occurrence.meaning.fragment.value == "Absent"
    )
    external = occurrence.meaning.model_copy(
        update={
            "status": "external",
            "target_id": None,
            "target_identity": None,
            "path": None,
            "target_version": None,
            "candidates": (),
        }
    )
    corrupted = old.model_copy(
        update={"occurrences": (occurrence.model_copy(update={"meaning": external}),)}
    )
    result = reconcile(
        facts.model_copy(
            update={
                "link_context": context.model_copy(
                    update={"current_documents": (corrupted,)}
                )
            }
        )
    )
    assert not result.ready
    assert (
        result.changes[0].disposition == "refused" and result.changes[0].result is None
    )
    assert "link_context_invalid" in {f.code for f in result.findings}


def test_unchanged_unrelated_appearance_warning_is_reported_without_waiving_membership_safety():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import validate_link_document
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_memberships import target

    category = target("a", "category", "[[A]]")
    note = target_for_links("note:target", "Notes/Target.md")
    raw = ExactContent(
        data=b'---\ncategories:\n  - "[[A]]"\nappearance_category: "[[Absent]]"\n---\nText.\n'
    )
    state = interpret_link_target(
        raw,
        target_id=note.target_id,
        existence="present",
        memberships=("a",),
        membership_targets=(category,),
    )
    doc = interpret_links(
        ExactContent(data=b"[[Notes/Target.md]]"),
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(note, category),
        target_facts=(state,),
        inventory="complete",
    )

    def validate(selected_state):
        return validate_link_document(
            doc,
            expected_content=doc.content,
            expected_path="Owner.md",
            targets=(note, category),
            target_facts=(selected_state,),
            inventory="complete",
            baseline=baseline_for(doc, (note, category), (state,)),
            affected_target_ids=("resource:unrelated",),
        )

    result = validate(state)
    assert result.valid
    assert [(f.code, f.blocking) for f in result.findings] == [
        ("link_appearance_warning", False)
    ]
    # The same byte-bound warning cannot excuse unsafe category membership targets.
    membership = state.structure.memberships[0]
    unsafe = category.model_copy(
        update={"target": category.target.model_copy(update={"containment": "outside"})}
    )
    entry = membership.entries[0].model_copy(update={"target": unsafe})
    structure = state.structure.model_copy(
        update={"memberships": (membership.model_copy(update={"entries": (entry,)}),)}
    )
    blocked = validate(state.model_copy(update={"structure": structure}))
    assert not blocked.valid and "link_membership_invalid" in {
        f.code for f in blocked.findings
    }
    malformed = state.structure.model_copy(update={"appearance_field": "missing"})
    refused = validate(state.model_copy(update={"structure": malformed}))
    assert not refused.valid
    assert "link_membership_invalid" in {f.code for f in refused.findings}


def test_new_invalid_appearance_in_changed_affected_target_cannot_claim_existing_warning():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import validate_link_document
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_memberships import target

    category = target("a", "category", "[[A]]")
    note = target_for_links("note:target", "Notes/Target.md")
    old_bytes = ExactContent(
        data=b'---\ncategories:\n  - "[[A]]"\nappearance_category: "[[A]]"\n---\nText.\n'
    )
    new_bytes = ExactContent(
        data=b'---\ncategories:\n  - "[[A]]"\nappearance_category: "[[Absent]]"\n---\nText.\n'
    )
    old_state = interpret_link_target(
        old_bytes,
        target_id=note.target_id,
        existence="present",
        memberships=("a",),
        membership_targets=(category,),
    )
    new_state = interpret_link_target(
        new_bytes,
        target_id=note.target_id,
        existence="present",
        memberships=("a",),
        membership_targets=(category,),
    )
    token = ExactContent(data=b"[[Notes/Target.md]]")

    def document(state):
        return interpret_links(
            token,
            document_id="owner",
            source_path="Owner.md",
            path_mode="vault",
            targets=(note, category),
            target_facts=(state,),
            inventory="complete",
        )

    old_doc, selected = document(old_state), document(new_state)
    assert old_doc.content.data == selected.content.data == b"[[Notes/Target.md]]"
    assert (
        old_doc.occurrences[0].meaning.target_version
        != selected.occurrences[0].meaning.target_version
    )

    def validate(baseline):
        return validate_link_document(
            selected,
            expected_content=token,
            expected_path="Owner.md",
            targets=(note, category),
            target_facts=(new_state,),
            inventory="complete",
            baseline=baseline,
            affected_target_ids=(note.target_id,),
        )

    newly_harmful = validate(baseline_for(old_doc, (note, category), (old_state,)))
    assert not newly_harmful.valid
    assert "link_membership_invalid" in {f.code for f in newly_harmful.findings}
    # Independently bound prior semantics prove the retained issue, even for an affected file.
    retained = validate(baseline_for(selected, (note, category), (new_state,)))
    assert retained.valid and [(f.code, f.blocking) for f in retained.findings] == [
        ("link_appearance_warning", False)
    ]
    assert not validate(None).valid


def test_same_bytes_do_not_prove_retained_appearance_after_registry_alias_removal():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import validate_link_document
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_memberships import target

    old_category = target("a", "category", "[[A]]", "[[Alias]]")
    category = target("a", "category", "[[A]]")
    note = target_for_links("note:target", "Notes/Target.md")
    raw = ExactContent(
        data=b'---\ncategories:\n  - "[[A]]"\nappearance_category: "[[Alias]]"\n---\nText.\n'
    )
    old_state = interpret_link_target(
        raw,
        target_id=note.target_id,
        existence="present",
        memberships=("a",),
        membership_targets=(old_category,),
    )
    state = interpret_link_target(
        raw,
        target_id=note.target_id,
        existence="present",
        memberships=("a",),
        membership_targets=(category,),
    )
    token = ExactContent(data=b"[[Notes/Target.md]]")
    old_doc = interpret_links(
        token,
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(note, old_category),
        target_facts=(old_state,),
        inventory="complete",
    )
    selected = interpret_links(
        token,
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(note, category),
        target_facts=(state,),
        inventory="complete",
    )
    assert old_doc.occurrences[0].meaning == selected.occurrences[0].meaning
    result = validate_link_document(
        selected,
        expected_content=token,
        expected_path="Owner.md",
        targets=(note, category),
        target_facts=(state,),
        inventory="complete",
        baseline=baseline_for(old_doc, (note, old_category), (old_state,)),
        affected_target_ids=(note.target_id, category.target_id),
    )
    assert not result.valid
    assert "link_membership_invalid" in {f.code for f in result.findings}


def baseline_for(document, targets, states, *, inventory="complete"):
    from brz2obsidian.contracts import LinkValidationBaseline

    return LinkValidationBaseline(
        schema_id="brz2obsidian.link-validation-baseline",
        schema_version=1,
        document=document,
        targets=targets,
        target_facts=states,
        inventory=inventory,
    )


def test_retained_appearance_uses_prior_semantics_across_prose_edits_and_refuses_bad_proof():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import validate_link_document
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_memberships import target

    category = target("a", "category", "[[A]]")
    note = target_for_links("note:target", "Notes/Target.md")
    prefix = b'---\ncategories:\n  - "[[A]]"\nappearance_category: "[[Absent]]"\n---\n'
    old_state, state = (
        interpret_link_target(
            ExactContent(data=prefix + prose),
            target_id=note.target_id,
            existence="present",
            memberships=("a",),
            membership_targets=(category,),
        )
        for prose in (b"Original prose.\n", b"Locally revised prose.\n")
    )
    token = ExactContent(data=b"[[Notes/Target.md]]")
    old_doc, selected = (
        interpret_links(
            token,
            document_id="owner",
            source_path="Owner.md",
            path_mode="vault",
            targets=(note, category),
            target_facts=(value,),
            inventory="complete",
        )
        for value in (old_state, state)
    )
    assert (
        old_doc.occurrences[0].meaning.target_version
        != selected.occurrences[0].meaning.target_version
    )
    proof = baseline_for(old_doc, (note, category), (old_state,))

    def validate(baseline):
        return validate_link_document(
            selected,
            expected_content=token,
            expected_path="Owner.md",
            targets=(note, category),
            target_facts=(state,),
            inventory="complete",
            baseline=baseline,
            affected_target_ids=(note.target_id,),
        )

    retained = validate(proof)
    assert retained.valid
    assert [(f.code, f.blocking) for f in retained.findings] == [
        ("link_appearance_warning", False)
    ]
    assert not validate(None).valid
    assert not validate(proof.model_copy(update={"target_facts": ()})).valid
    assert not validate(proof.model_copy(update={"inventory": "partial"})).valid
    assert not validate(
        proof.model_copy(update={"targets": (note, category, category)})
    ).valid
    owner = target_for_links("note:owner", "Owner.md")
    assert not validate(
        proof.model_copy(update={"targets": (note, category, owner)})
    ).valid

    occurrence = old_doc.occurrences[0]
    forged = occurrence.model_copy(
        update={
            "meaning": occurrence.meaning.model_copy(update={"target_id": "unrelated"})
        }
    )
    corrupt = proof.model_copy(
        update={"document": old_doc.model_copy(update={"occurrences": (forged,)})}
    )
    assert not validate(corrupt).valid
    # Historical embedded membership spellings must agree with the historical registry.
    contradictory = category.model_copy(update={"representations": ("[[Other]]",)})
    assert not validate(
        proof.model_copy(update={"targets": (note, contradictory)})
    ).valid
