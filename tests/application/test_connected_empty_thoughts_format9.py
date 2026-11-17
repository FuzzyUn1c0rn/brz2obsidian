"""Literal generation-9 graph and presentation at the plan and render seams."""

import hashlib
import json

from brz2obsidian.contracts import Asset, Document, ReferenceSpan
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import render
from tests.application.test_graph_modules import POLICY, edge, generated, item, snapshot
from tests.application.test_module_seams import METADATA
from tests.support.notes import note_body


def test_connected_targets_keep_assigned_paths_and_render_navigation():
    authored = "[Other twin](old)"
    body_hash = hashlib.sha256(authored.encode()).hexdigest()
    blank_hash = hashlib.sha256(b" \r\n").hexdigest()
    facts = snapshot(
        (
            item("hub", "Twin", "111111111111"),
            item("twin", "twin", "222222222222", document_ids=("authored",)),
            item("leaf", "Leaf", document_ids=("blank",)),
            item("jump-a", "Jump A"),
            item("jump-b", "Jump B"),
            item("tag", "Topic", role="tag"),
            item("tag-only", "Tag only"),
            item("authored-only", "Authored only"),
            item("isolated", "Migration report", "abcd", label="Metadata only"),
            item("system", role="system"),
            item("expired", live=False),
        ),
        (
            edge("entry-hub", "entry", "hub"),
            edge("hub-twin", "hub", "twin"),
            edge("hub-leaf", "hub", "leaf"),
            edge("hub-leaf-again", "hub", "leaf"),
            edge("leaf-hub", "leaf", "hub"),
            edge("hub-jump", "hub", "tag", "related"),
            edge("jumps", "jump-a", "jump-b", "related"),
            edge("assigned-leaf", "tag", "leaf", "tag"),
            edge("assigned-only", "tag", "tag-only", "tag"),
            edge("system-only", "system", "isolated", "system"),
        ),
        (
            Document(
                key="authored",
                owner="twin",
                text=authored,
                text_digest=body_hash,
                original_asset_id="authored",
                references=(
                    ReferenceSpan(
                        start=0,
                        end=len(authored),
                        expected_original=authored,
                        kind="item",
                        target="authored-only",
                        display_text="Other twin",
                        document_digest=body_hash,
                    ),
                ),
            ),
            Document(
                key="blank",
                owner="leaf",
                text=" \r\n",
                text_digest=blank_hash,
                original_asset_id="blank",
            ),
        ),
        (
            Asset(
                asset_id="authored",
                owner="twin",
                naming_seed="bbbb",
                original_name="Notes.md",
                role="note_original",
                availability="present",
                actual_length=len(authored),
                actual_sha256=body_hash,
            ),
            Asset(
                asset_id="blank",
                owner="leaf",
                naming_seed="cccc",
                original_name="Notes.md",
                role="note_original",
                availability="present",
                actual_length=3,
                actual_sha256=blank_hash,
            ),
        ),
    )
    analysis = analyze(facts, POLICY)
    historical = plan(analysis, output_format=8)
    migration = plan(analysis, output_format=9)
    expected_paths = {
        "entry": "Home — Entry.md",
        "hub": "Notes/Twin — 11111111.md",
        "twin": "Notes/twin — 22222222.md",
        "leaf": "Notes/Leaf.md",
        "jump-a": "Notes/Jump A.md",
        "jump-b": "Notes/Jump B.md",
        "tag": "Notes/Topic.md",
        "tag-only": "Notes/Tag only.md",
        "authored-only": "Notes/Authored only.md",
        "isolated": "Notes/Migration report — abcd.md",
    }
    for current_plan in (historical, migration):
        assert {t.item_key: t.relative_path for t in current_plan.item_targets} == (
            expected_paths
        )
    assert {t.item_key: t.creation_reasons for t in migration.item_targets} == {
        "entry": ("home",),
        "hub": ("navigation",),
        "twin": ("content",),
        "leaf": ("navigation",),
        "jump-a": ("navigation",),
        "jump-b": ("navigation",),
        "tag": ("navigation",),
        "tag-only": (),
        "authored-only": (),
        "isolated": (),
    }
    assert migration.source_identity == historical.source_identity
    historical_hub = next(t for t in historical.item_targets if t.item_key == "hub")
    assert historical_hub.creation_reasons == ("hierarchy",)
    assert len(migration.analysis.snapshot.relationships) == 10
    assert migration.counts.planned_notes == 7
    assert migration.counts.native_tag_memberships == 1
    assert migration.counts.uncreated_tag_memberships == 1

    vault = render(migration, METADATA.model_copy(update={"renderer_version": "9"}))
    assert {
        f.relative_path
        for f in vault.generated_files
        if f.relative_path.startswith("Notes/")
    } == {
        expected_paths[key]
        for key in ("hub", "twin", "leaf", "jump-a", "jump-b", "tag")
    }
    assert note_body(generated(vault, expected_paths["hub"])) == (
        "# Twin\n\n## Parents\n\n- [[Home — Entry.md|Entry]]\n"
        "- [[Notes/Leaf.md|Leaf]]\n\n## Children\n\n"
        "- [[Notes/Leaf.md|Leaf]]\n- [[Notes/twin — 22222222.md|twin]]\n"
        "\n## Related\n\n- [[Notes/Topic.md|Topic]]\n"
    )
    assert "## Related\n\n- [[Notes/Twin — 11111111.md|Twin]]\n" in generated(
        vault, expected_paths["tag"]
    )
    assert 'tags:\n  - "Topic"\n' in generated(vault, expected_paths["leaf"])
    assert "## Related\n\n- [[Notes/Jump B.md|Jump B]]\n" in generated(
        vault, expected_paths["jump-a"]
    )
    assert "## Related\n\n- [[Notes/Jump A.md|Jump A]]\n" in generated(
        vault, expected_paths["jump-b"]
    )
    assert generated(vault, "Uncreated targets.md") == (
        "# Uncreated targets\n\n## Isolated thoughts\n\n"
        "- [[Notes/Migration report — abcd.md|Migration report]]\n"
    )
    assert "Related pairs" not in generated(vault, "MIGRATION REPORT.md")
    tag_listing = generated(vault, "Tag memberships.md")
    assert "[[Notes/Tag only.md|Tag only]]" in tag_listing
    assert "[[Notes/Leaf.md|Leaf]]" not in tag_listing
    record = json.loads(generated(vault, "migration-record.json"))
    assert (record["schema_version"], record["renderer_version"]) == (9, "9")
    assert record["source_identity"] == facts.identity.model_dump()
    assert len(record["relationships"]) == 10
    system = next(r for r in record["relationships"] if r["kind"] == "system")
    assert system["presentation"] == "retained_only"


def test_generated_endpoints_remove_fallbacks_without_releasing_support_names():
    facts = snapshot(
        (item("peer", "Uncreated targets", "aaaa"), item("tag", "Topic", role="tag")),
        (
            edge("jump", "entry", "peer", "related"),
            edge("tag-child", "entry", "tag"),
            edge("assignment", "tag", "peer", "tag"),
        ),
    )
    migration = plan(analyze(facts, POLICY), output_format=9)
    reordered = facts.model_copy(
        update={
            "items": tuple(reversed(facts.items)),
            "relationships": tuple(reversed(facts.relationships)),
        }
    )
    other = plan(analyze(reordered, POLICY), output_format=9)
    assert migration.item_targets == other.item_targets
    assert migration.counts == other.counts
    metadata = METADATA.model_copy(update={"renderer_version": "9"})
    vault, repeated = (render(planned, metadata) for planned in (migration, other))
    for path in ("Uncreated targets.md", "Tag memberships.md"):
        assert path in vault.reserved_paths and path not in vault.manifest
        assert f"[[{path}|" not in generated(vault, "MIGRATION REPORT.md")
    peer = "Notes/Uncreated targets — aaaa.md"
    assert peer in vault.manifest and repeated.manifest == vault.manifest
    assert generated(vault, peer) == generated(repeated, peer)
    assert 'tags:\n  - "Topic"\n' in generated(vault, peer)
