"""Binary review exposes only actual offered output metadata to its consumers."""

from hashlib import sha256

from brz2obsidian.application.review_offers import choice_detail_page, choice_offers
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_attachments import attachment_request


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
