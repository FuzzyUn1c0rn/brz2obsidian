"""Exact legacy semantics and byte-bound current file qualification."""

from hashlib import sha256

import pytest
from pydantic import ValidationError

from brz2obsidian.contracts import ExactContent, LinkTargetFacts
from brz2obsidian.core import prepare_review
from brz2obsidian.obsidian import interpret_link_target
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import preflight, with_review_links


def test_recorded7_omits_file_roles_and_keeps_exact_public_plan_and_link_fingerprint():
    # Independently recorded from accepted f753c9f before this contract extension.
    plan = prepare_review(with_review_links(request()), preflight=preflight())
    states = plan.facts.link_context.current_target_facts
    assert states and all("file_roles" not in row.model_dump() for row in states)
    assert [
        row.fingerprint
        for change in plan.proposal.changes
        for row in change.assumptions
        if row.kind == "link"
    ] == ["cff9a4601405ef8cfa5172698d408f982d32ec50e86aa11b753b86c262eda2ad"]
    assert sha256(plan.model_dump_json().encode()).hexdigest() == (
        "2db811e918e5b7194c2473a86022209330bf0120737f6da214c5a3063f694010"
    )


@pytest.mark.parametrize(
    "raw,digest",
    [
        (None, None),
        (b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    ],
)
def test_current_role_evidence_distinguishes_unavailable_and_empty_bytes(raw, digest):
    state = interpret_link_target(
        None if raw is None else ExactContent(data=raw),
        target_id="owned-image",
        existence="missing" if raw is None else "present",
        memberships=(),
        source_path="Attachments/Owned.PNG",
        output_format=8,
    )
    assert state.file_roles.path == "Attachments/Owned.PNG"
    assert state.file_roles.image_path and not state.file_roles.category
    assert state.file_roles.content_sha256 == digest
    assert LinkTargetFacts.model_validate_json(state.model_dump_json()) == state
    altered = state.model_dump()
    altered["file_roles"]["content_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="exact available target bytes"):
        LinkTargetFacts.model_validate(altered)
