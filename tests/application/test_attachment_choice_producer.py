"""Small canonical attachment choices compile locally to full validated proofs."""

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_choices import (
    attachment_references,
    requirement_digest,
)
from brz2obsidian.core import inspect_review_choices, select_review_effects
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_attachments import linked_attachment_request


@pytest.mark.parametrize("choice", ("incoming", "both"))
def test_incoming_and_both_use_only_offered_reference_destinations(choice):
    raw = b"Keep [[Assets/data.bin|First]] and ![[Assets/data.bin|Second]]. `[[Assets/data.bin]]`\r\n"
    prepared = preparation(linked_attachment_request(raw=raw))
    offer = next(
        row
        for row in inspect_review_choices(prepared.review)
        if row.domain == "attachment"
    )
    assert choice in offer.enabled_choices
    refs = attachment_references(prepared, offer.requirement_id)
    assert len(refs) == 2
    choices = tuple(
        {
            "reference_id": token,
            "choice": "use_incoming"
            if choice == "incoming"
            else "keep_current"
            if index == 0
            else "use_secondary",
        }
        for index, (token, _, _) in enumerate(refs)
    )
    options = {
        "requirement_id": offer.requirement_id,
        "choice": choice,
        "assumptions_digest": requirement_digest(offer),
    }
    with pytest.raises(ValueError):
        Operations().resolve_update_choice(prepared, **options, references=choices[:1])
    with pytest.raises(ValueError):
        Operations().resolve_update_choice(
            prepared,
            **options,
            references=({"reference_id": "0" * 64, "choice": "use_incoming"},)
            + choices[1:],
        )
    result = Operations().resolve_update_choice(prepared, **options, references=choices)
    assert result.code == "accepted" and result.ready, result
    selected = select_review_effects(result.preparation.review)
    assert selected.status == "selected"
    files = {row.path: row.content.data for row in selected.files}
    assert files["Assets/data.bin"] == (
        b"abc" if choice == "incoming" else b"\x00authored"
    )
    expected = (
        raw
        if choice == "incoming"
        else raw.replace(
            b"![[Assets/data.bin|Second]]",
            b"![[Assets/data (incoming-ba7816bf).bin|Second]]",
        )
    )
    assert files.get("Notes/Owner.md", raw) == expected
    assert expected.endswith(b"`[[Assets/data.bin]]`\r\n")
    if choice == "both":
        assert files["Assets/data (incoming-ba7816bf).bin"] == b"abc"
    else:
        assert "Assets/data (incoming-ba7816bf).bin" not in files
    assert prepared.review.facts.link_context.current_documents[0].content.data == raw


@pytest.mark.parametrize("choice", ("incoming", "both"))
def test_bounded_reference_offers_and_wire_preserve_canonical_destinations(choice):
    from pathlib import Path

    from brz2obsidian.application.contracts import WorkerRequest
    from brz2obsidian.application.protocol import (
        REQUEST_LIMIT,
        decode_request,
        encode_request,
    )
    from brz2obsidian.application.review_choices import attachment_reference_page
    from brz2obsidian.application.update_context_contracts import UpdateContextBinding

    raw = b"[[Assets/data.bin|First]] ![[Assets/data.bin|Second]] `[[Assets/data.bin]]`\r\n"
    prepared = preparation(linked_attachment_request(raw=raw))
    offer = next(
        row
        for row in inspect_review_choices(prepared.review)
        if row.domain == "attachment"
    )

    identity = "11111111-1111-4111-8111-111111111111"
    binding = UpdateContextBinding(
        context_id=identity,
        selection_id=identity,
        vault=str(Path(prepared.vault).absolute()),
        association_id=prepared.locator.association.association_id,
        checkpoint_commit=prepared.locator.commit,
        checkpoint_generation=prepared.locator.generation,
        proposal_id=prepared.review.proposal.proposal_id,
        generation=prepared.review.proposal.generation,
        revision=1,
    )
    for index in range(2):
        references, total, following = attachment_reference_page(
            prepared, offer.requirement_id, offset=index, limit=1
        )
        assert (
            total == 2
            and len(references) == 1
            and following == (1 if index == 0 else None)
        )
        reference = references[0]
        selected = (
            "use_incoming"
            if choice == "incoming"
            else "keep_current"
            if index == 0
            else "use_secondary"
        )
        assert selected in reference.choices
        destination = next(
            row for row in reference.destinations if row.choice == selected
        )
        assert destination.meaning.status == "resolved"
        assert destination.meaning.path == (
            "Assets/data (incoming-ba7816bf).bin"
            if selected == "use_secondary"
            else "Assets/data.bin"
        )
        request = WorkerRequest(
            request_id=identity,
            sequence=index + 1,
            operation="update",
            arguments={
                "command": "stage_references",
                "binding": binding,
                "requirement_id": offer.requirement_id,
                "choices": (
                    {"reference_id": reference.reference_id, "choice": selected},
                ),
            },
        )
        wire = encode_request(request)
        assert len(wire) < REQUEST_LIMIT and b"attachment_candidate" not in wire
        decoded = decode_request(wire)
        assert decoded.arguments.choices[0].reference_id == reference.reference_id
        assert decoded.arguments.choices[0].choice == selected
        assert decoded.arguments.binding == binding
    assert prepared.review.facts.link_context.current_documents[0].content.data == raw
