import json
from uuid import UUID, uuid5
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_minimal_workflow import FIXTURE
from tests.sources.test_reader import rewrite

BRAIN = "11111111-1111-4111-8111-111111111111"


def identity(number):
    return str(UUID(int=number))


def graph_archive(
    path, titles, edges=(), *, kinds=None, labels=None, reverse=False, notes=None
):
    kinds, labels = kinds or {}, labels or {}
    records = {
        file.name: file.read_bytes() for file in FIXTURE.iterdir() if file.is_file()
    }
    records["meta.json"] = json.dumps(
        {"BrainId": BRAIN, "ExchangeFormatVersion": 5, "AttachmentFileStates": {}}
    ).encode()
    thoughts = [
        {
            "Id": identity(n),
            "BrainId": BRAIN,
            "Name": title,
            "Kind": kinds.get(n, 1),
            "ACType": 0,
            "Label": labels.get(n),
            "ForgottenDateTime": "2020-01-01",
        }
        for n, title in titles.items()
    ]
    links = [
        {
            "Id": identity(1000 + i),
            "BrainId": BRAIN,
            "ThoughtIdA": identity(a),
            "ThoughtIdB": identity(b),
            "Kind": 1,
            "Relation": relation,
            "Meaning": meaning,
            "Direction": direction,
        }
        for i, (a, b, relation, meaning, direction) in enumerate(edges)
    ]
    if reverse:
        thoughts.reverse()
        links.reverse()
    records["thoughts.json"] = "\n".join(json.dumps(r) for r in thoughts).encode()
    records["links.json"] = "\n".join(json.dumps(r) for r in links).encode()
    records["settings.json"] = json.dumps(
        {"Id": str(uuid5(UUID(BRAIN), "20")), "Value": identity(1)}
    ).encode()
    attachments, states = [], {}
    for owner, (body, note_type) in (notes or {}).items():
        attachment_id = identity(2000 + owner)
        attachments.append(
            {
                "Id": attachment_id,
                "BrainId": BRAIN,
                "SourceId": identity(owner),
                "SourceType": 2,
                "Type": 1,
                "NoteType": note_type,
                "Location": "Notes.md",
                "Name": "Notes.md",
                "DataLength": len(body),
            }
        )
        states[attachment_id] = 1
        records[identity(owner) + "/Notes.md"] = body
    records["attachments.json"] = "\n".join(json.dumps(r) for r in attachments).encode()
    records["meta.json"] = json.dumps(
        {"BrainId": BRAIN, "ExchangeFormatVersion": 5, "AttachmentFileStates": states}
    ).encode()
    with ZipFile(path, "w") as archive:
        for name in sorted(records, reverse=reverse):
            archive.writestr(name, records[name])
    return path


def test_empty_chain_materializes_middle_and_renders_complete_context(tmp_path):
    source = graph_archive(
        tmp_path / "graph.brz",
        {1: "Entry", 2: "A", 3: "B", 4: "C"},
        [(2, 3, 1, 1, 7), (3, 4, 1, 1, -1)],
        labels={3: "Useful label"},
    )
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean"
    assert inspected.counts.planned_notes == 2
    assert {
        t.original_title for t in inspected.inspection.item_targets if t.created
    } == {"Entry", "B"}
    destination = tmp_path / "vault"
    result = workflow.convert(source, destination)
    assert result.outcome == "clean"
    assert (
        (destination / "Notes/B.md").read_text(encoding="utf-8")
        == "# B\n\nUseful label\n\n## Parents\n\n- [[Notes/A.md|A]]\n\n## Children\n\n- [[Notes/C.md|C]]\n"
    )
    assert not (destination / "Uncreated targets.md").exists()
    record = json.loads((destination / "migration-record.json").read_bytes())
    assert len(record["relationships"]) == 2
    assert record["relationships"][0]["target_a"] == "Notes/A.md"
    assert record["relationships"][0]["target_b"] == "Notes/B.md"
    assert record["relationships"][0]["presentation"] == "Parents/Children"
    assert {
        a["affected"]
        for a in record["adaptations"]
        if a["kind"] == "relationship_presentation"
    } == {identity(1000), identity(1001)}
    assert record["original_evidence"][2]["records"][0]["Direction"] == 7


def test_uncreated_listing_focuses_on_isolated_items_and_uncovered_related_pairs(
    tmp_path,
):
    source = graph_archive(
        tmp_path / "graph.brz",
        {
            1: "Entry",
            2: "Linked",
            3: "Orphan",
            4: "Peer.one",
            5: "Peer two",
            6: "System",
        },
        [(1, 2, 3, 1, 5), (4, 5, 3, 1, 3), (4, 5, 3, 1, -1), (6, 3, 1, 6, -1)],
        kinds={6: 5},
    )
    destination = tmp_path / "vault"
    result = default_workflow().convert(source, destination)
    assert result.outcome == "clean"
    assert result.counts.actual_notes == 1
    listing = (destination / "Uncreated targets.md").read_text(encoding="utf-8")
    assert (
        listing
        == "# Uncreated targets\n\n## Isolated thoughts\n\n- [[Notes/Orphan.md|Orphan]]\n\n## Related pairs\n\n- [[Notes/Peer.one.md|Peer.one]] — [[Notes/Peer two.md|Peer two]]\n"
    )
    assert "[[Uncreated targets.md|Uncreated targets]]" in (
        destination / "MIGRATION REPORT.md"
    ).read_text(encoding="utf-8")
    home = (destination / "Home — Entry.md").read_text(encoding="utf-8")
    assert home == "# Entry\n\n## Related\n\n- [[Notes/Linked.md|Linked]]\n"
    record = json.loads((destination / "migration-record.json").read_bytes())
    assert len(record["relationships"]) == 4
    assert len(record["item_targets"]) == 5


def test_cycles_multiple_parents_and_zip_order_keep_same_choices_and_targets(tmp_path):
    titles = {1: "Entry", 2: "A", 3: "B", 4: "C", 5: "D"}
    edges = [
        (2, 3, 1, 1, -1),
        (3, 4, 1, 1, 1),
        (4, 2, 1, 1, 7),
        (2, 5, 1, 1, -1),
        (3, 5, 1, 1, -1),
        (3, 5, 1, 1, -1),
    ]
    workflow = default_workflow()
    first = workflow.inspect(graph_archive(tmp_path / "one.brz", titles, edges))
    second = workflow.inspect(
        graph_archive(tmp_path / "two.brz", titles, edges, reverse=True)
    )
    assert first.outcome == second.outcome == "clean"
    assert first.inspection.item_targets == second.inspection.item_targets
    assert {t.original_title for t in first.inspection.item_targets if t.created} == {
        "Entry",
        "A",
        "B",
    }
    result = workflow.convert(tmp_path / "one.brz", tmp_path / "vault")
    assert result.outcome == "clean"
    body = (tmp_path / "vault/Notes/B.md").read_text(encoding="utf-8")
    assert body.count("[[Notes/D.md|D]]") == 1
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert len(record["relationships"]) == 6


def test_ordinary_parent_tag_child_keeps_hierarchy_without_forcing_tag_file(tmp_path):
    source = graph_archive(
        tmp_path / "graph.brz",
        {1: "Entry", 2: "Parent", 3: "Tag"},
        [(2, 3, 1, 1, -1)],
        kinds={3: 4},
    )
    destination = tmp_path / "vault"
    result = default_workflow().convert(source, destination)
    assert result.outcome == "clean"
    assert (destination / "Notes/Parent.md").read_text(
        encoding="utf-8"
    ) == "# Parent\n\n## Children\n\n- [[Notes/Tag.md|Tag]]\n"
    assert not (destination / "Notes/Tag.md").exists()


@pytest.mark.parametrize(
    "relation,meaning,direction",
    [(1, 1, 0), (2, 1, -1), (4, 1, -1), (1, 1, 3), (3, 6, -1)],
)
def test_unverified_relationship_signatures_are_refused(
    tmp_path, relation, meaning, direction
):
    source = graph_archive(
        tmp_path / "graph.brz",
        {1: "Entry", 2: "Other"},
        [(1, 2, relation, meaning, direction)],
    )
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "refused"
    assert result.issues[0].code == "unsupported_feature"
    assert not (tmp_path / "vault").exists()


def test_history_is_retained_without_resurrection_but_live_deleted_overlap_refuses(
    tmp_path,
):
    source = graph_archive(tmp_path / "graph.brz", {1: "Entry", 2: "Forgotten"})
    rewrite(
        source,
        "modificationlogs.json",
        json.dumps(
            {"Id": identity(900), "ThoughtId": identity(700), "OldName": "Historical"}
        ).encode(),
    )
    rewrite(
        source, "tombstones.json", json.dumps({"Id": identity(700), "Type": 2}).encode()
    )
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean"
    assert {t.item_key for t in inspected.inspection.item_targets} == {
        identity(1),
        identity(2),
    }
    rewrite(
        source, "tombstones.json", json.dumps({"Id": identity(2), "Type": 2}).encode()
    )
    refused = workflow.convert(source, tmp_path / "vault")
    assert refused.outcome == "refused"
    assert refused.issues[0].code == "invalid_source"


def test_content_already_covers_hierarchy_and_placeholder_does_not_force_note(tmp_path):
    source = graph_archive(
        tmp_path / "graph.brz",
        {1: "Entry", 2: "Parent", 3: "Child", 4: "Placeholder"},
        [(2, 3, 1, 1, -1)],
        notes={3: (b"Authored child.\r\n", 4), 4: (b"\xef\xbb\xbf", 0)},
    )
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "clean"
    assert {
        t.original_title for t in inspected.inspection.item_targets if t.created
    } == {"Entry", "Child"}


def test_inspect_leaves_path_feasibility_pending_and_convert_refuses_long_destination(
    tmp_path,
):
    source = graph_archive(tmp_path / "graph.brz", {1: "Entry", 2: "A" * 160})
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean"
    assert "destination feasibility" in inspected.inspection.pending_checks
    destination = tmp_path / ("destination" * 10)
    # The full manifest also includes conditional listings; this path exceeds
    # the accepted conservative absolute-path bound before staging is made.
    result = workflow.convert(source, destination)
    assert result.outcome == "refused"
    assert result.issues[0].code == "target_path_too_long"
    assert not destination.exists()
