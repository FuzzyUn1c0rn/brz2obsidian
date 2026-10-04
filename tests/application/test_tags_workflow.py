import json

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_resources_workflow import resource_archive, thought
from tests.sources.test_reader import rewrite
from tests.support.notes import note_body


def test_verified_assignments_use_native_tags_and_retain_hidden_memberships(tmp_path):
    source = graph_archive(
        tmp_path / "tags.brz",
        {1: "Entry", 2: "Empty", 3: "Project / Work!", 4: "Unused"},
        [(3, 1, 1, 5, -1), (3, 2, 1, 5, -1)],
        kinds={3: 4, 4: 4},
        notes={3: (b"Tag-authored text.\r\n", 4)},
    )
    workflow = default_workflow()
    inspection = workflow.inspect(source)
    assert inspection.outcome == "clean"
    assert inspection.counts.tag_memberships == 2
    assert inspection.counts.source_tags == 2
    assert inspection.counts.created_tag_items == 1
    assert inspection.counts.uncreated_tag_items == 1
    assert inspection.counts.native_tag_memberships == 1
    assert inspection.counts.uncreated_tag_memberships == 1
    assert {t.original_name: t.token for t in inspection.inspection.tag_targets} == {
        "Project / Work!": "Project-Work",
        "Unused": "Unused",
    }
    assert inspection.inspection.tag_memberships_path == "Tag memberships.md"
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "clean"
    assert result.counts.actual_notes == 2
    home = (vault / "Home — Entry.md").read_bytes()
    assert b'tags:\n  - "Project-Work"\n' in home
    assert note_body(home) == b"# Entry\n\n"
    tag_body = (vault / "Notes/Project Work!.md").read_bytes()
    assert note_body(tag_body) == b"# Project / Work!\n\nTag-authored text.\r\n"
    assert not (vault / "Notes/Empty.md").exists()
    listing = (vault / "Tag memberships.md").read_text(encoding="utf-8")
    assert "#Project-Work" in listing
    assert "[[Notes/Empty.md|Empty]]" in listing
    assert "[[Notes/Unused.md|Unused]]" in listing
    assert "Home — Entry" not in listing
    assert "[[Tag memberships.md|Tag memberships]]" in (
        vault / "MIGRATION REPORT.md"
    ).read_text(encoding="utf-8")
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert len(record["tag_memberships"]) == 2
    assert record["tag_memberships"][0]["tag_name"] == "Project / Work!"
    assert record["tag_memberships"][0]["native"] is True
    assert record["tag_memberships"][1]["listing_path"] == "Tag memberships.md"
    unused = next(t for t in record["item_targets"] if t["item_key"] == identity(4))
    assert unused["vault_tag_token"] == "Unused"
    assert (
        json.loads(result.model_dump_json(by_alias=True))["counts"]["tag_memberships"]
        == 2
    )


def test_native_only_tags_omit_duplicate_listing_and_assignment_display(tmp_path):
    source = graph_archive(
        tmp_path / "tags.brz",
        {1: "Entry", 2: "Native label"},
        [(2, 1, 1, 5, -1), (2, 1, 1, 5, -1)],
        kinds={2: 4},
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean"
    assert result.counts.tag_memberships == result.counts.native_tag_memberships == 2
    assert not (vault / "Tag memberships.md").exists()
    assert not (vault / "Notes/Native label.md").exists()
    assert (vault / "Home — Entry.md").read_text(encoding="utf-8").count(
        '  - "Native-label"'
    ) == 1
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert len(record["tag_memberships"]) == 2
    assert all(m["item_key"] == identity(1) for m in record["tag_memberships"])
    tag_target = next(t for t in record["item_targets"] if t["item_key"] == identity(2))
    assert tag_target["created"] is False
    assert tag_target["vault_tag_token"] == "Native-label"


@pytest.mark.parametrize(
    "a,b,relation,meaning,direction",
    [
        (1, 2, 1, 5, -1),
        (2, 2, 1, 5, -1),
        (2, 3, 1, 5, -1),
        (2, 1, 1, 5, 0),
        (2, 1, 3, 5, -1),
        (2, 1, 1, 5, 1),
    ],
)
def test_unverified_tag_signatures_and_roles_refuse(
    tmp_path, a, b, relation, meaning, direction
):
    source = graph_archive(
        tmp_path / "tags.brz",
        {1: "Entry", 2: "Tag", 3: "Other tag"},
        [(a, b, relation, meaning, direction)],
        kinds={2: 4, 3: 4},
    )
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "refused"
    assert result.issues[0].code == "unsupported_feature"
    assert not (tmp_path / "vault").exists()


def test_empty_tag_ids_do_not_establish_assignments_and_nonempty_are_unverified(
    tmp_path,
):
    source = graph_archive(tmp_path / "tags.brz", {1: "Entry", 2: "Tag"}, kinds={2: 4})
    thoughts = [
        {
            "Id": identity(1),
            "BrainId": "11111111-1111-4111-8111-111111111111",
            "Name": "Entry",
            "Kind": 1,
            "ACType": 0,
            "TagIds": [],
        },
        {
            "Id": identity(2),
            "BrainId": "11111111-1111-4111-8111-111111111111",
            "Name": "Tag",
            "Kind": 4,
            "ACType": 0,
            "TagIds": [],
        },
    ]
    rewrite(
        source, "thoughts.json", "\n".join(json.dumps(t) for t in thoughts).encode()
    )
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "clean"
    assert inspected.counts.tag_memberships == 0
    assert inspected.inspection.tag_memberships == ()
    thoughts[0]["TagIds"] = [identity(2)]
    rewrite(
        source, "thoughts.json", "\n".join(json.dumps(t) for t in thoughts).encode()
    )
    assert default_workflow().inspect(source).outcome == "refused"


def test_tag_hierarchy_and_classification_keep_independent_meanings(tmp_path):
    source = graph_archive(
        tmp_path / "tags.brz",
        {1: "Entry", 2: "Tag", 3: "Parent", 4: "Assigned"},
        [(3, 2, 1, 1, -1), (2, 4, 1, 5, -1)],
        kinds={2: 4},
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean"
    assert result.counts.actual_notes == 2
    assert (
        note_body((vault / "Notes/Parent.md").read_text(encoding="utf-8"))
        == "# Parent\n\n## Children\n\n- [[Notes/Tag.md|Tag]]\n"
    )
    assert not (vault / "Notes/Tag.md").exists()
    assert not (vault / "Notes/Assigned.md").exists()
    assert "[[Notes/Assigned.md|Assigned]]" in (vault / "Tag memberships.md").read_text(
        encoding="utf-8"
    )


def test_tag_resources_create_normal_notes_but_decorations_remain_uncreated(tmp_path):
    file_tag, external_tag, decorated_tag = identity(2), identity(3), identity(4)
    tags = [
        dict(thought(key, name), Kind=4)
        for key, name in [
            (file_tag, "File tag"),
            (external_tag, "External tag"),
            (decorated_tag, "Decorated tag"),
        ]
    ]
    source = resource_archive(
        tmp_path / "tags.brz",
        [
            ({"SourceId": file_tag, "Location": "manual.pdf"}, b"PDF bytes"),
            (
                {
                    "SourceId": external_tag,
                    "Type": 3,
                    "Location": "https://example.invalid/tag",
                },
                None,
            ),
            (
                {
                    "SourceId": decorated_tag,
                    "Type": 5,
                    "IsIcon": True,
                    "Location": "icon.png",
                },
                b"icon",
            ),
        ],
        thoughts=tags,
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean"
    assert result.counts.actual_notes == 3
    assert result.counts.created_tag_items == 2
    assert result.counts.uncreated_tag_items == 1
    assert result.counts.tag_memberships == 0
    file_body = (vault / "Notes/File tag.md").read_text(encoding="utf-8")
    assert "## Resources" in file_body and "manual.pdf" in file_body
    assert "https://example.invalid/tag" in (vault / "Notes/External tag.md").read_text(
        encoding="utf-8"
    )
    assert not (vault / "Notes/Decorated tag.md").exists()
    assert file_body.startswith("---\n") and "tags: []\n" in file_body
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert record["tag_memberships"] == []
    assert (
        len([t for t in record["item_targets"] if t["vault_tag_token"] is not None])
        == 3
    )
