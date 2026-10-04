import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from brz2obsidian.application.wiring import default_workflow

FIXTURE = Path(__file__).parents[1] / "fixtures" / "minimal"
PROPERTIES = (
    b"---\ncategories: []\nappearance_category:\nicon:\nforeground_color:\n"
    b"background_color:\ncreated: 2026-10-03\nupdated:\ntags: []\naliases: []\n"
    b'source_collection_id: "11111111-1111-4111-8111-111111111111"\n'
    b'source_item_id: "22222222-2222-4222-8222-222222222222"\n---\n\n'
)


def make_archive(path, *, empty=False):
    with ZipFile(path, "w") as archive:
        for file in FIXTURE.rglob("*"):
            if file.is_file():
                data = file.read_bytes()
                if empty and file.name == "Notes.md":
                    data = b""
                if empty and file.name == "attachments.json":
                    record = json.loads(data)
                    record["DataLength"] = 0
                    data = json.dumps(record).encode()
                archive.writestr(file.relative_to(FIXTURE).as_posix(), data)
    return path


def test_minimal_brain_inspects_then_converts_into_verified_home(tmp_path):
    source = make_archive(tmp_path / "brain.brz")
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean"
    assert inspected.receipt is None
    assert inspected.counts.planned_notes == 1
    assert inspected.counts.actual_notes is None
    destination = tmp_path / "vault"
    converted = workflow.convert(source, destination)
    assert converted.outcome == "clean"
    assert converted.receipt.destination == str(destination.resolve())
    assert (destination / "Home — Entry thought.md").read_bytes() == PROPERTIES + (
        b"# Entry thought\n\nAuthored body.\r\n\n"
        b"## Categories\n\n[[Categories.md|Browse categories]]\n"
    )
    record = json.loads((destination / "migration-record.json").read_bytes())
    assert record["schema"] == "brz2obsidian.migration"
    assert record["schema_version"] == 2
    assert record["original_evidence"][0]["records"][0]["Uninterpreted"] == {
        "nullable": None,
        "number": 1.5,
    }
    assert (
        record["original_evidence"][1]["records"][0]["CreationDateTime"]
        == "2026-10-03T12:34:56"
    )
    backup = destination / "Attachments" / "22222222" / "Notes.md.original"
    assert backup.read_bytes() == b"Authored body.\r\n"
    assert (
        hashlib.sha256(backup.read_bytes()).hexdigest()
        == "5ffa7716ee53174debb9b0ddfec17efa574c4e494b4bd1a321a0378c29016229"
    )
    config = json.loads((destination / ".obsidian" / "app.json").read_bytes())
    assert config["openBehavior"] == "file:Home — Entry thought.md"
    bookmarks = json.loads((destination / ".obsidian" / "bookmarks.json").read_bytes())
    assert bookmarks["items"][0]["path"] == "Home — Entry thought.md"


def test_empty_home_is_materialized_and_existing_destination_is_protected(tmp_path):
    source = make_archive(tmp_path / "brain.brz", empty=True)
    workflow = default_workflow()
    destination = tmp_path / "vault"
    destination.mkdir()
    first = workflow.convert(source, destination)
    assert first.outcome == "clean"
    assert (destination / "Home — Entry thought.md").read_bytes() == PROPERTIES + (
        b"# Entry thought\n\n## Categories\n\n[[Categories.md|Browse categories]]\n"
    )
    before = {
        p.relative_to(destination).as_posix(): p.read_bytes()
        for p in destination.rglob("*")
        if p.is_file()
    }
    refused = workflow.convert(source, destination)
    assert refused.outcome == "refused"
    assert refused.receipt is None
    assert refused.issues[0].code == "destination_not_empty"
    assert {
        p.relative_to(destination).as_posix(): p.read_bytes()
        for p in destination.rglob("*")
        if p.is_file()
    } == before
    assert list(tmp_path.glob(".brz2obsidian-*")) == []
