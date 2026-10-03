import hashlib

import pytest

from brz2obsidian.contracts import (
    Asset,
    Document,
    Item,
    MigrationRefused,
    ReferenceSpan,
    Relationship,
    SourceAccounting,
    SourceIdentity,
    SourcePolicy,
    SourceSnapshot,
)
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import render
from tests.application.test_module_seams import METADATA

POLICY = SourcePolicy(
    profile_id="synthetic",
    profile_version="1",
    module_id="synthetic",
    module_version="1",
    format_version="1",
)
IDENTITY = SourceIdentity(
    source_id="collection",
    module_id="synthetic",
    module_version="1",
    format_version="1",
    source_sha256="a" * 64,
    snapshot_digest="b" * 64,
)


def snapshot(items, relationships=(), documents=(), assets=()):
    return SourceSnapshot(
        identity=IDENTITY,
        collection_title="Graph",
        entry_key="entry",
        items=(
            Item(
                key="entry",
                original_identity="entry",
                naming_seed="ffff",
                title="Entry",
            ),
            *items,
        ),
        relationships=relationships,
        documents=documents,
        assets=assets,
        accounting=SourceAccounting(entries=()),
    )


def item(key, title=None, seed=None, **values):
    return Item(
        key=key,
        original_identity=key,
        naming_seed=seed or key.encode().hex(),
        title=title or key.upper(),
        **values,
    )


def edge(key, a, b, kind="hierarchy"):
    return Relationship(key=key, kind=kind, item_a=a, item_b=b)


def generated(artifacts, name):
    return next(
        f.content.decode("utf-8")
        for f in artifacts.generated_files
        if f.relative_path == name
    )


def test_names_reserve_all_targets_handle_natural_suffixes_and_record_adaptations():
    facts = snapshot(
        (
            item("a", "Twin", "abcdef010001"),
            item("b", "twin", "abcdef010002"),
            item("c", "Twin — abcdef01", "feed"),
            item("d", "Migration report", "abcd"),
            item("e", "NUL.txt"),
            item("f", "e\u0301:[x]/unsafe?\u0080 ."),
        )
    )
    migration = plan(analyze(facts, POLICY))
    names = {t.item_key: t.relative_path for t in migration.item_targets}
    assert names == {
        "entry": "Home — Entry.md",
        "a": "Notes/Twin — abcdef010001.md",
        "b": "Notes/twin — abcdef010002.md",
        "c": "Notes/Twin — abcdef01.md",
        "d": "Notes/Migration report — abcd.md",
        "e": "Notes/Note - NUL.txt.md",
        "f": "Notes/é - (x) unsafe.md",
    }
    assert {a.affected for a in migration.adaptations if a.kind == "item_target"} == {
        "entry",
        "a",
        "b",
        "d",
        "e",
        "f",
    }
    assert sum(t.created for t in migration.item_targets) == 1


def test_core_plans_only_unrepresented_fallbacks_and_document_links_count_as_readable():
    body = "[Uncreated](source)"
    asset = Asset(
        asset_id="note",
        owner="entry",
        naming_seed="ff",
        original_name="Notes.md",
        role="note_original",
        availability="present",
        actual_length=len(body),
        actual_sha256=hashlib.sha256(body.encode()).hexdigest(),
    )
    doc = Document(
        key="note",
        owner="entry",
        text=body,
        text_digest=asset.actual_sha256,
        original_asset_id="note",
        references=(
            ReferenceSpan(
                start=0,
                end=len(body),
                expected_original=body,
                kind="item",
                target="referenced",
                display_text="Uncreated",
                document_digest=asset.actual_sha256,
            ),
        ),
    )
    facts = snapshot(
        (item("referenced"), item("alone"), item("pair-a"), item("pair-b")),
        (edge("related", "pair-a", "pair-b", "related"),),
        (doc,),
        (asset,),
    )
    migration = plan(analyze(facts, POLICY))
    assert migration.isolated_item_keys == ("alone",)
    assert migration.uncreated_related_pairs == (("pair-a", "pair-b"),)


def test_renderer_refuses_a_plan_bound_to_another_snapshot():
    migration = plan(analyze(snapshot(()), POLICY))
    wrong_identity = IDENTITY.model_copy(update={"snapshot_digest": "c" * 64})
    with pytest.raises(MigrationRefused) as error:
        render(
            migration.model_copy(update={"source_identity": wrong_identity}), METADATA
        )
    assert error.value.issues[0].code == "source_changed"


@pytest.mark.parametrize("values", [{"live": False}, {"role": "system"}])
def test_core_refuses_navigation_relationships_to_retained_only_items(values):
    facts = snapshot((item("a", **values),), (edge("entry-a", "entry", "a"),))
    with pytest.raises(MigrationRefused) as error:
        analyze(facts, POLICY)
    assert error.value.issues[0].code == "invalid_reference"


def test_greedy_parent_score_counts_incident_edges_then_recomputes_and_ties_by_key():
    facts = snapshot(
        tuple(item(k) for k in "abcdef"),
        (
            edge("ab", "a", "b"),
            edge("bc", "b", "c"),
            edge("db", "d", "b"),
            edge("ef", "e", "f"),
            edge("fc", "f", "c"),
        ),
    )
    migration = plan(analyze(facts, POLICY))
    assert {t.item_key for t in migration.item_targets if t.created} == {
        "entry",
        "b",
        "f",
    }
    reordered = facts.model_copy(
        update={
            "items": tuple(reversed(facts.items)),
            "relationships": tuple(reversed(facts.relationships)),
        }
    )
    assert plan(analyze(reordered, POLICY)).item_targets == migration.item_targets
    recomputed = snapshot(
        tuple(item(k) for k in ("a", "b", "c", "d", "x", "y")),
        (
            edge("ab", "a", "b"),
            edge("ba", "b", "a"),
            edge("bc", "b", "c"),
            edge("ax", "a", "x"),
            edge("ay", "a", "y"),
            edge("cd", "c", "d"),
        ),
    )
    assert {
        t.item_key for t in plan(analyze(recomputed, POLICY)).item_targets if t.created
    } == {"entry", "a", "c"}
    tied = snapshot(
        (item("a"), item("b")), (edge("ab", "a", "b"), edge("ba", "b", "a"))
    )
    assert {
        t.item_key for t in plan(analyze(tied, POLICY)).item_targets if t.created
    } == {"entry", "a"}


def test_bounded_names_keep_home_and_seed_markers_without_splitting_unicode():
    facts = snapshot(
        (
            item("a", "🙂" * 100, "ab"),
            item("b", "🙂" * 99 + "x", "abcdef"),
            item("c", "..."),
            item("d", "[x] : <> / \\ | ? * # ^ %"),
        )
    )
    facts = facts.model_copy(
        update={
            "items": tuple(
                i.model_copy(update={"title": "H" * 160}) if i.key == "entry" else i
                for i in facts.items
            )
        }
    )
    names = {
        t.item_key: t.relative_path for t in plan(analyze(facts, POLICY)).item_targets
    }
    assert names["a"] == "Notes/" + "🙂" * 57 + " — ab.md"
    assert names["b"] == "Notes/" + "🙂" * 55 + " — abcdef.md"
    assert names["c"] == "Notes/Untitled.md"
    assert names["d"] == "Notes/(x) -.md"
    assert names["entry"] == "Home — " + "H" * 113 + ".md"


def test_exhausted_short_seeds_resolve_by_suffixing_natural_name_contender():
    facts = snapshot(
        (item("a", "Foo", "ab"), item("b", "foo", "cd"), item("c", "Foo — ab", "ef"))
    )
    names = {
        t.item_key: t.relative_path for t in plan(analyze(facts, POLICY)).item_targets
    }
    assert names["a"] == "Notes/Foo — ab.md"
    assert names["b"] == "Notes/foo — cd.md"
    assert names["c"] == "Notes/Foo — ab — ef.md"


def test_indistinguishable_full_seeds_refuse_with_actionable_source_guidance():
    facts = snapshot((item("a", "Duplicate", "ab"), item("b", "duplicate", "ab")))
    with pytest.raises(MigrationRefused) as error:
        plan(analyze(facts, POLICY))
    assert error.value.issues[0].code == "invalid_source"
    assert "distinct stable naming seeds" in error.value.issues[0].guidance


def test_decorative_assets_labels_and_empty_placeholders_alone_leave_targets_uncreated():
    original = Asset(
        asset_id="empty",
        owner="empty",
        naming_seed="ee",
        original_name="Notes.md",
        role="note_original",
        availability="present",
        actual_length=3,
        actual_sha256="e" * 64,
    )
    icon = Asset(
        asset_id="icon",
        owner="decorated",
        naming_seed="dd",
        original_name="icon.png",
        role="icon",
        availability="present",
        actual_length=4,
        actual_sha256="d" * 64,
    )
    doc = Document(
        key="empty",
        owner="empty",
        text="",
        text_digest=hashlib.sha256(b"").hexdigest(),
        original_asset_id="empty",
    )
    facts = snapshot(
        (
            item("empty", document_ids=("empty",)),
            item("decorated", label="Label", resource_ids=("icon",)),
        ),
        documents=(doc,),
        assets=(original, icon),
    )
    migration = plan(analyze(facts, POLICY))
    assert {t.item_key for t in migration.item_targets if t.created} == {"entry"}


def test_rendering_preserves_authored_body_and_uses_exact_qualified_dotted_targets():
    body = "Authored.\r\n\r\n"
    original = Asset(
        asset_id="body",
        owner="a",
        naming_seed="ab",
        original_name="Notes.md",
        role="note_original",
        availability="present",
        actual_length=len(body),
        actual_sha256=hashlib.sha256(body.encode()).hexdigest(),
    )
    doc = Document(
        key="body",
        owner="a",
        text=body,
        text_digest=original.actual_sha256,
        original_asset_id="body",
    )
    facts = snapshot(
        (item("a", "[*] <Title>", document_ids=("body",)), item("b", "B.v2")),
        (edge("ab", "a", "b"), edge("duplicate", "a", "b")),
        (doc,),
        (original,),
    )
    artifacts = render(plan(analyze(facts, POLICY)), METADATA)
    assert (
        generated(artifacts, "Notes/( ) Title.md")
        == "# \\[\\*\\] \\<Title\\>\n\n"
        + body
        + "## Children\n\n- [[Notes/B.v2.md|B.v2]]\n"
    )
