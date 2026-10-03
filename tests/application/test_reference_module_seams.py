import hashlib

import pytest

from brz2obsidian.contracts import Asset, Document, MigrationRefused, ReferenceSpan
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import render
from tests.application.test_graph_modules import POLICY, generated, item, snapshot
from tests.application.test_module_seams import METADATA


def reference_snapshot():
    text = "Before\r\n[shown](other-format:target)\rAfter\n"
    digest = hashlib.sha256(text.encode()).hexdigest()
    reference = ReferenceSpan(
        start=8,
        end=36,
        expected_original="[shown](other-format:target)",
        kind="item",
        target="opaque:target",
        display_text="shown",
        document_digest=digest,
    )
    document = Document(
        key="opaque:document",
        owner="entry",
        text=text,
        text_digest=digest,
        original_asset_id="opaque:original",
        references=(reference,),
    )
    asset = Asset(
        asset_id="opaque:original",
        owner="entry",
        naming_seed="ab",
        original_name="note.md",
        role="note_original",
        availability="present",
        actual_length=len(text),
        actual_sha256=digest,
    )
    facts = snapshot(
        (item("opaque:target", "Dotted.v2"),), documents=(document,), assets=(asset,)
    )
    return facts.model_copy(
        update={
            "items": (
                facts.items[0].model_copy(update={"document_ids": (document.key,)}),
                facts.items[1],
            )
        }
    )


def test_public_core_and_renderer_use_canonical_opaque_keys_and_exact_document_spans():
    migration = plan(analyze(reference_snapshot(), POLICY))
    artifacts = render(migration, METADATA)
    assert (
        generated(artifacts, "Home — Entry.md")
        == "# Entry\n\nBefore\r\n[[Notes/Dotted.v2.md|shown]]\rAfter\n"
    )
    assert (
        migration.counts.planned_references == artifacts.counts.actual_references == 1
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"start": -1},
        {"end": 1000},
        {"expected_original": "altered"},
        {"document_digest": "a" * 64},
        {"target": "absent"},
    ],
)
def test_public_core_and_renderer_refuse_unapproved_or_unbound_spans(changes):
    facts = reference_snapshot()
    approved = plan(analyze(facts, POLICY))
    document = facts.documents[0]
    document = document.model_copy(
        update={"references": (document.references[0].model_copy(update=changes),)}
    )
    changed = facts.model_copy(update={"documents": (document,)})
    with pytest.raises(MigrationRefused) as error:
        analyze(changed, POLICY)
    assert error.value.issues[0].code == "invalid_reference"
    tampered = approved.model_copy(
        update={"analysis": approved.analysis.model_copy(update={"snapshot": changed})}
    )
    with pytest.raises(MigrationRefused) as error:
        render(tampered, METADATA)
    assert error.value.issues[0].code == "invalid_reference"


def test_public_core_refuses_overlapping_spans_even_when_each_substring_matches():
    facts = reference_snapshot()
    document = facts.documents[0]
    changed = facts.model_copy(
        update={
            "documents": (
                document.model_copy(update={"references": document.references * 2}),
            )
        }
    )
    with pytest.raises(MigrationRefused) as error:
        analyze(changed, POLICY)
    assert error.value.issues[0].code == "invalid_reference"


@pytest.mark.parametrize("changes", [{"live": False}, {"role": "system"}])
def test_public_core_refuses_embedded_links_to_nonlive_or_retained_only_items(changes):
    facts = reference_snapshot()
    changed = facts.model_copy(
        update={"items": (facts.items[0], facts.items[1].model_copy(update=changes))}
    )
    with pytest.raises(MigrationRefused) as error:
        analyze(changed, POLICY)
    assert error.value.issues[0].code == "invalid_reference"
