"""Cold, format-specific reconciliation controls produced at 1c2c0f00."""

from pathlib import Path

import pytest

from brz2obsidian.contracts import ContentVersion, SavedReview
from brz2obsidian.core import (
    load_review,
    reconcile,
    resume_review,
    select_review_effects,
)
from brz2obsidian.obsidian import interpret_link_target, interpret_links
from tests.reconciliation.test_identity import inventory_item, with_subjects
from tests.reconciliation.test_proposals import request

FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "fixtures/saved_reviews/connected-empty-thoughts"
)
PATH = "Notes/Opening.md"
TARGET = "subject:entry:opening:content"
PROPERTIES = (
    b'---\nsource_collection_id: "folio:collection"\n'
    b'source_item_id: "entry:opening"\n---\n\n'
)
RELATIVE = b"[Back to top](./Opening.md#Opening)"
WIKI = b"[[Notes/Opening.md#Opening|Back to top]]"
CURRENT = PROPERTIES + b"# Opening\r\n\r\nLocal prose.\r\n\r\n" + RELATIVE + b"\r\n"


def assert_link(document, raw_link):
    assert document.status == "supported"
    (link,) = document.occurrences
    assert link.raw == raw_link
    assert (link.query.mode, link.query.value) == ("exact", PATH)
    meaning = link.meaning
    assert (meaning.status, meaning.target_id, meaning.path) == (
        "resolved",
        TARGET,
        PATH,
    )
    assert (
        meaning.target_identity.collection_id,
        meaning.target_identity.module_id,
        meaning.target_identity.item_id,
    ) == ("folio:collection", "synthetic-folio", "entry:opening")
    assert (meaning.fragment.kind, meaning.fragment.value) == ("heading", "Opening")


def observe_note(content, targets, structure_format, link_format, *, qualify_roles):
    state = interpret_link_target(
        content,
        target_id=TARGET,
        existence="present",
        memberships=(),
        source_path=PATH,
        output_format=structure_format,
        qualify_roles=qualify_roles,
    )
    document = interpret_links(
        content,
        document_id=TARGET,
        source_path=PATH,
        path_mode="vault",
        targets=targets,
        target_facts=(state,),
        inventory="complete",
        output_format=link_format,
    )
    return state, document


def assert_recorded_roles(plan, old_format, incoming):
    facts = plan.producer_facts
    (subject,) = facts.subjects
    comparison = subject.structure
    assert comparison is not None
    assert (
        comparison.original.output_format,
        comparison.current.output_format,
        comparison.incoming.output_format,
    ) == (old_format, old_format, 8)
    original_link = WIKI if old_format == 7 else RELATIVE
    original = (
        PROPERTIES
        + b"# Opening\r\n\r\nOriginal generated prose.\r\n\r\n"
        + original_link
        + b"\r\n"
    )
    (change,) = plan.proposal.changes
    assert change.original.data == comparison.original.content.data == original
    assert change.current.data == comparison.current.content.data == CURRENT
    assert change.incoming.data == comparison.incoming.content.data == incoming

    context = facts.link_context
    (current,) = context.current_target_facts
    (target,) = context.incoming_target_facts
    assert (current.structure.output_format, target.structure.output_format) == (
        old_format,
        8,
    )
    assert current.file_roles.path == target.file_roles.path == PATH
    (current_doc,) = context.current_documents
    (incoming_doc,) = context.incoming_documents
    assert current_doc.content.data == CURRENT
    assert incoming_doc.content.data == incoming
    assert_link(current_doc, RELATIVE)
    assert_link(incoming_doc, RELATIVE)

    _, original_doc = observe_note(
        subject.baseline.content,
        context.current_targets,
        old_format,
        old_format,
        qualify_roles=False,
    )
    assert_link(original_doc, original_link)


@pytest.mark.parametrize(
    ("fixture_name", "kind", "old_format", "old_profile", "source_version", "incoming"),
    (
        (
            "source-update-8.json",
            "source_update",
            8,
            "11",
            "source:b",
            b"# Opening\n\nSource edit.\n",
        ),
        (
            "transition-7-to-8.json",
            "format_transition",
            7,
            "10",
            "source:a",
            b"# Opening\n\nFormat eight.\n",
        ),
    ),
)
def test_cold_review_keeps_recorded_format_roles_and_authored_choice(
    fixture_name, kind, old_format, old_profile, source_version, incoming
):
    raw = (FIXTURES / fixture_name).read_bytes()
    incoming = PROPERTIES + incoming + b"\n" + RELATIVE + b"\n"
    assert_recorded_roles(
        SavedReview.model_validate_json(raw).plan, old_format, incoming
    )
    result = load_review(raw)
    assert result.status == "loaded" and not result.ready
    loaded = result.loaded
    historical = loaded.saved.plan
    facts = historical.facts
    assert (
        facts.baseline_identity.profile_version,
        facts.baseline_identity.output_format,
    ) == (old_profile, old_format)
    assert (
        facts.incoming_identity.profile_version,
        facts.incoming_identity.output_format,
    ) == ("11", 8)
    operation = facts.format_operation
    assert (
        operation.kind,
        operation.baseline_source_version,
        operation.target_source_version,
    ) == (kind, "source:a", source_version)
    assert_recorded_roles(historical, old_format, incoming)

    context = facts.link_context
    (subject,) = facts.subjects
    current_state, current_doc = observe_note(
        subject.current.content,
        context.current_targets,
        old_format,
        8,
        qualify_roles=True,
    )
    incoming_state, incoming_doc = observe_note(
        subject.incoming, context.incoming_targets, 8, 8, qualify_roles=False
    )
    observed = facts.model_copy(
        update={
            "link_context": context.model_copy(
                update={
                    "current_target_facts": (current_state,),
                    "current_documents": (current_doc,),
                    "incoming_target_facts": (incoming_state,),
                    "incoming_documents": (incoming_doc,),
                }
            ),
        }
    )
    resumed = resume_review(loaded, observed, preflight=historical.preflight)
    assert (resumed.status, resumed.code, resumed.ready) == (
        "resumed",
        "unchanged",
        True,
    )
    assert_recorded_roles(resumed.plan, old_format, incoming)
    assert [approval.decision_id for approval in resumed.plan.approvals] == [
        "keep-authored-opening"
    ]
    effects = select_review_effects(resumed.plan)
    assert effects.status == "selected" and effects.remove_paths == ()
    assert [(row.path, row.content.data) for row in effects.files] == [(PATH, CURRENT)]


@pytest.mark.parametrize(
    ("occupant_identity", "current", "eligible"),
    (
        (None, b"", True),
        (None, b"# Opening\r\n\r\nLocal prose.\r\n", True),
        ("entry:different", b"# Opening\r\n\r\nDifferent thought.\r\n", False),
    ),
)
def test_occupied_reserved_note_path_does_not_establish_a_generated_original(
    occupant_identity, current, eligible
):
    incoming = b"# Opening\n\n## Parents\n\n- [[Home.md|Home]]\n"
    facts = request(current=current, incoming=incoming)
    subject = facts.subjects[0].model_copy(
        update={
            "baseline": ContentVersion(
                status="unknown", content=None, unavailable_digest=None
            )
        }
    )
    occupant = inventory_item(
        "reserved-path-occupant",
        occupant_identity or subject.item_id,
        "Notes/Opening.md",
        current,
        state="valid" if occupant_identity else "missing",
    )
    result = reconcile(with_subjects(facts, (subject,), (occupant,)))
    (change,) = result.changes
    assert not result.ready
    assert change.original is None and change.result is None
    assert change.incoming.data == incoming
    assert change.identity_review.selected_entry_id is None
    (candidate,) = change.identity_review.candidates
    assert candidate.current.content.data == current
    assert candidate.eligible is eligible
