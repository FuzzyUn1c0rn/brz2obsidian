"""Thought-note preparation interactions through the two-phase source interface."""

from hashlib import sha256

import pytest

from brz2obsidian.contracts import Asset, Issue, MigrationRefused
from brz2obsidian.sources.thebrain.note_preparation import (
    bind_prepared_notes,
    prepare_note,
)

OWNER = "11111111-1111-4111-8111-111111111111"
ASSET = "33333333-3333-4333-8333-333333333333"
IMAGE = "44444444-4444-4444-8444-444444444444"
EXCLUDED = "00000000-0000-0000-0000-000000000000"
EXCLUDED_URI = "brain://AAAAAAAAAAAAAAAAAAAAAA/title"
INCLUDED = "00000000-0000-0000-0000-000000000001"
INCLUDED_URI = "brain://AAAAAAAAAAAAAAAAAAAAAQ/title"
POINTER = "attachments.json:0"
MEMBER = OWNER + "/Notes.md"
HELPER_GUIDANCE = "Use supported same-Brain inline Markdown references to live thoughts and archived images, then re-export."


def source_refuse(code, message, affected=(), *, evidence=(), guidance=None):
    raise MigrationRefused(
        (
            Issue(
                code=code,
                phase="source",
                message=message,
                affected=affected,
                evidence=evidence,
                guidance=guidance,
            ),
        )
    )


def prepare(text):
    return prepare_note(
        text,
        owner=OWNER,
        asset_id=ASSET,
        pointer=POINTER,
        member=MEMBER,
        excluded=(EXCLUDED,),
        scope_tokens=(EXCLUDED,),
        source_refuse=source_refuse,
    )


def image_asset(*, owner=OWNER, availability="present"):
    return Asset(
        asset_id=IMAGE,
        owner=owner,
        naming_seed="4444",
        original_name="p.png",
        role="image",
        availability=availability,
    )


def test_exclusions_precede_fresh_edits_and_remove_enclosed_images_in_reverse_order():
    text = f"<Value>[private <Secret>]({EXCLUDED_URI})A[![private](.data/md-images/missing.png)]({EXCLUDED_URI})<Tail>\n"
    document, findings = prepare(text)
    scoped = "<Value>A<Tail>\n"
    assert document.text == "\\<Value>A\\<Tail>\n"
    assert document.original_asset_id is None and document.original_copy_omitted
    assert document.key == ASSET and document.owner == OWNER
    assert document.evidence == (POINTER,)
    assert document.references == () and findings == ()
    assert [
        (e.start, e.end, e.before, e.after, e.adapted_start, e.adapted_end)
        for e in document.text_adaptations
    ] == [
        (0, 7, "<Value>", "\\<Value>", 0, 8),
        (8, 14, "<Tail>", "\\<Tail>", 9, 16),
    ]
    assert {e.source_digest for e in document.text_adaptations} == {
        sha256(scoped.encode()).hexdigest()
    }
    assert document.text_digest == sha256(document.text.encode()).hexdigest()
    assert (
        "private" not in document.model_dump_json()
        and "Secret" not in document.model_dump_json()
    )


def test_table_literals_references_and_loss_evidence_bind_final_text_after_inventory():
    document, findings = prepare(
        f'<Value>[private <Secret>]({EXCLUDED_URI})\n|One|Two|:(table="column-widths:-1,0,84;justification:default"):\n|`x|y`|![pic](.data/md-images/p.png#$width=50p$)|\n'
    )
    assert (
        document.text
        == "\\<Value>\n|One|Two|\n|---|---|\n|<code>x&#124;y</code>|![pic](.data/md-images/p.png#$width=50p$)|\n"
    )
    assert (
        document.text_digest
        == "95e87a5d1402c619e98992512927af866d9fcd23fd0126feeca1dec32471642e"
    )
    assert [
        (e.start, e.end, e.adapted_start, e.adapted_end)
        for e in document.text_adaptations
    ] == [(0, 7, 0, 8), (8, 72, 9, 28), (73, 122, 29, 94)]
    assert {e.source_digest for e in document.text_adaptations} == {
        "4cde821dda400dd3498008a9036fd0e74be3e16d26fc350c719d7cb91c766096"
    }
    assert len(document.references) == 1
    reference = document.references[0]
    assert (
        reference.start,
        reference.end,
        reference.destination_start,
        reference.destination_end,
    ) == (52, 93, 59, 92)
    assert reference.expected_original == "![pic](.data/md-images/p.png#$width=50p$)"
    assert reference.table_cell and reference.document_digest == document.text_digest
    assert reference.target == ".data/md-images/p.png#$width=50p$"
    assert reference.presentation_normalization is None
    assert len(findings) == 1
    assert findings[0].model_dump() == {
        "kind": "formatting_loss",
        "rule_id": "thebrain.markdown-inserts.v1",
        "affected": (OWNER, ASSET),
        "evidence": (POINTER,),
        "observed_json": '{"feature": "table", "declaration": ":(table=\\"column-widths:-1,0,84;justification:default\\"):", "change": "Column widths and justification become native responsive table layout; edit the table in Obsidian to adjust its presentation."}',
    }
    bound = bind_prepared_notes(
        [document], [image_asset()], {OWNER: {"Kind": 1}}, source_refuse
    )[0]
    reference = bound.references[0]
    assert (
        reference.target == IMAGE
        and reference.source_target == ".data/md-images/p.png#$width=50p$"
    )
    normalization = reference.presentation_normalization
    assert (
        normalization.declaration,
        normalization.start,
        normalization.end,
        normalization.document_digest,
    ) == ("#$width=50p$", 80, 92, document.text_digest)
    assert document.references[0].target == ".data/md-images/p.png#$width=50p$"
    assert (
        bound.text_adaptations == document.text_adaptations
        and bound.evidence == document.evidence
    )


@pytest.mark.parametrize(
    "text, code, message, affected, evidence, guidance",
    [
        (
            "[included](brain://abc/title)",
            "invalid_reference",
            "Invalid or unsupported compact thought reference",
            (),
            (),
            HELPER_GUIDANCE,
        ),
        (
            '<a href="https://example.invalid">private</a>',
            "unsupported_feature",
            "HTML note content is outside reviewed Markdown coverage",
            (OWNER, ASSET),
            (POINTER, "payload:" + MEMBER),
            "Review the affected thought-note Markdown and its preserved source evidence; unsupported HTML or reference syntax must be resolved before retrying.",
        ),
        (
            "outside " + EXCLUDED,
            "invalid_reference",
            "Note contains an excluded association outside removable references",
            (OWNER, ASSET),
            (POINTER, "meta.json"),
            "Review this attachment's declared role and owned archive payload.",
        ),
        (
            f"<[private]({EXCLUDED_URI})a>",
            "unsupported_feature",
            "HTML note content is outside reviewed Markdown coverage",
            (OWNER, ASSET),
            (POINTER,),
            HELPER_GUIDANCE,
        ),
    ],
)
def test_preparation_refusals_preserve_each_stages_exact_context(
    text, code, message, affected, evidence, guidance
):
    # These literals were established against the accepted baseline attachment
    # interface before relocation; a blanket catch would change the first case.
    with pytest.raises(MigrationRefused) as error:
        prepare(text)
    assert error.value.issues == (
        Issue(
            code=code,
            phase="source",
            message=message,
            affected=affected,
            evidence=evidence,
            guidance=guidance,
        ),
    )


def test_safe_original_and_canonical_thought_binding_preserve_protected_examples():
    text = f"[keep]({INCLUDED_URI})\n`![example](.data/md-images/missing.png)`\n"
    document, findings = prepare(text)
    assert document.original_asset_id == ASSET and not document.original_copy_omitted
    assert document.text == text and document.text_adaptations == () and findings == ()
    bound = bind_prepared_notes([document], [], {INCLUDED: {"Kind": 1}}, source_refuse)
    assert len(bound[0].references) == 1
    assert bound[0].references[0].target == INCLUDED
    assert bound[0].references[0].source_target == INCLUDED_URI


@pytest.mark.parametrize(
    "assets",
    [
        [],
        [image_asset(owner=INCLUDED)],
        [image_asset(availability="absent")],
        [image_asset(), image_asset()],
    ],
)
def test_binding_refusals_identify_the_document_when_no_unique_owned_image_exists(
    assets,
):
    first, _ = prepare("safe first document")
    first = first.model_copy(
        update={"key": "earlier-note", "evidence": ("attachments.json:9",)}
    )
    document, _ = prepare("![pic](.data/md-images/p.png)")
    with pytest.raises(MigrationRefused) as error:
        bind_prepared_notes(
            [first, document], assets, {OWNER: {"Kind": 1}}, source_refuse
        )
    assert error.value.issues == (
        Issue(
            code="invalid_reference",
            phase="source",
            message="Local image does not identify one preserved owner image",
            affected=(OWNER, ASSET),
            evidence=(POINTER,),
            guidance="Review the affected thought-note Markdown and declared local references before retrying.",
        ),
    )
