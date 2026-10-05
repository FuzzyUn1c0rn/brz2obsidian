import hashlib

import pytest

from brz2obsidian.contracts import Asset, Document, MigrationRefused, ReferenceSpan
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import render
from tests.application.test_graph_modules import POLICY, edge, generated, item, snapshot
from tests.application.test_module_seams import METADATA
from tests.support.notes import note_body


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
        note_body(generated(artifacts, "Home — Entry.md"))
        == "# Entry\n\nBefore\r\n[[Notes/Dotted.v2.md|shown]]\rAfter\n\n"
        "## Categories\n\n[[Categories.md|Browse categories]]\n"
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


def test_public_renderer_refuses_reference_without_its_assigned_item_target():
    migration = plan(analyze(reference_snapshot(), POLICY))
    changed = migration.model_copy(
        update={"item_targets": (migration.item_targets[0],)}
    )
    with pytest.raises(MigrationRefused) as error:
        render(changed, METADATA)
    assert error.value.issues[0].code == "invalid_reference"


@pytest.mark.parametrize(
    "body",
    [
        "~~~python\r\nprint(42)",
        "<!-- Authored comment\r\nkept open",
        "> ```python\n> print(42)",
        "- example\n\n  ```python\n  print(42)",
        "    indented example\n",
        "```python\nprint(42)\n```",
    ],
)
def test_reusable_renderer_keeps_following_documents_and_navigation_visible(body):
    from markdown_it import MarkdownIt

    bodies = (body, "# Second document\n\nAuthored follow-up.\n")
    documents, assets = [], []
    for index, text in enumerate(bodies):
        key = f"doc-{index}"
        digest = hashlib.sha256(text.encode()).hexdigest()
        documents.append(
            Document(
                key=key,
                owner="entry",
                text=text,
                text_digest=digest,
                original_asset_id=key,
            )
        )
        assets.append(
            Asset(
                asset_id=key,
                owner="entry",
                naming_seed=f"aa{index}",
                original_name=f"note-{index}.md",
                role="note_original",
                availability="present",
                actual_length=len(text.encode()),
                actual_sha256=digest,
            )
        )
    assets.append(
        Asset(
            asset_id="manual",
            owner="entry",
            naming_seed="bb",
            original_name="manual.pdf",
            role="file",
            availability="present",
            actual_length=1,
            actual_sha256=hashlib.sha256(b"x").hexdigest(),
        )
    )
    facts = snapshot(
        (item("child"),),
        relationships=(edge("parent-child", "entry", "child"),),
        documents=tuple(documents),
        assets=tuple(assets),
    )
    facts = facts.model_copy(
        update={
            "items": (
                facts.items[0].model_copy(
                    update={"document_ids": tuple(d.key for d in documents)}
                ),
                facts.items[1],
            )
        }
    )
    note = generated(render(plan(analyze(facts, POLICY)), METADATA), "Home — Entry.md")
    assert body in note
    assert bodies[1] in note
    tokens = MarkdownIt("commonmark").parse(note_body(note))
    headings = [
        tokens[index + 1].content
        for index, token in enumerate(tokens)
        if token.type == "heading_open" and token.level == 0
    ]
    assert headings == [
        "Entry",
        "Second document",
        "Resources",
        "Children",
        "Categories",
    ]
    assert "Authored follow-up." in [
        token.content for token in tokens if token.type == "inline"
    ]
    assert "[[Notes/CHILD.md|CHILD]]" in [
        token.content for token in tokens if token.type == "inline"
    ]


def test_reusable_renderer_refuses_an_unprovable_trailing_block_boundary():
    facts = reference_snapshot()
    body = "<script>\nUnclosed raw block"
    digest = hashlib.sha256(body.encode()).hexdigest()
    document = facts.documents[0].model_copy(
        update={"text": body, "text_digest": digest, "references": ()}
    )
    asset = facts.assets[0].model_copy(
        update={"actual_length": len(body), "actual_sha256": digest}
    )
    facts = facts.model_copy(
        update={
            "documents": (document,),
            "assets": (asset,),
            "relationships": (edge("context", "entry", "opaque:target"),),
        }
    )
    with pytest.raises(MigrationRefused) as caught:
        render(plan(analyze(facts, POLICY)), METADATA)
    assert caught.value.issues[0].code == "unsupported_feature"
    assert caught.value.issues[0].phase == "rendering"
    assert "Close the trailing Markdown block" in caught.value.issues[0].guidance
