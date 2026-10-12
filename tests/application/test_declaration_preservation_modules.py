"""Protected declarations through the public source, core and renderer seams."""

import json
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

import pytest

from brz2obsidian.contracts import RunMetadata
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import render
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from tests.support.notes import note_body

HOME = "22222222-2222-4222-8222-222222222222"
BRAIN = "11111111-1111-4111-8111-111111111111"
DOCUMENT = "33333333-3333-4333-8333-333333333333"
TARGET = "01234567-89ab-4cde-8f01-23456789abcd"
IMAGE_ID = "aaaaaaaa-0000-4000-8000-000000000001"
THOUGHT_REFERENCE = "[Live](brain://Z0UjAauJ3kyPASNFZ4mrzQ/ignored)"
IMAGE_REFERENCE = '![photo](.data/md-images/a.png "caption")'
NOTE_PATH = "Home — Entry thought.md"
ORIGINAL_PATH = "Attachments/22222222/Notes.md.original"
IMAGE_PATH = "Attachments/22222222/a.png"
ROOTS = (
    "meta.json",
    "thoughts.json",
    "links.json",
    "attachments.json",
    "settings.json",
    "modificationlogs.json",
    "brainusers.json",
    "syncpoints.json",
    "tombstones.json",
    "calendarevents.json",
    "access.json",
    "fielddefinitions.json",
    "fieldinstances.json",
)
FIXTURE = Path(__file__).parents[1] / "fixtures/minimal"
ROOT_BYTES = tuple((name, (FIXTURE / name).read_bytes()) for name in ROOTS)
# One authored, immutable red 4x2 PNG; no per-case image generation.
IMAGE = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000004000000020802000000f0caea34"
    "0000001049444154789c63fccf80004c486c0600193501031b2f4b120000000049454e44ae426082"
)
PROTECTED_NEIGHBORS = [
    "`<!a>`",
    "`<!a`",
    r"\<!a>",
    r"\<!A",
    "<!é> <!1> <!_>",
    "Prose <!a\ncontinued",
    "Prose\n    <!a\ncontinued",
    "    <!a\n    > > literal code",
    "\t<!a",
    "```\n<!a\n> > literal code\n- literal code\n```",
    "~~~~\n   <!A\n> literal code\n~~~~",
    "<!--\n<!a\n> > comment data\n- comment data\n-->",
    "> ```\n> <!a\n> ```",
    "- ~~~\n  <!a\n  ~~~",
    "> ```\n> <!a",
    "- ~~~\n  <!a",
    ">     <!a",
    "-     <!a",
    "- > ```\n  > <!a\n  > ```",
    "> - ~~~\n>   <!a\n>   ~~~",
    "- > ```\n  > <!a",
    "> - <!--\n>   <!a\n>   -->",
    "-\t  <!a",
    "-\t\t<!a",
    "1.\t   <!a",
    "10. \t<!a",
    "123.\t <!a",
    "- ordinary\n\n      <!a",
    "1.    ordinary\n\n          <!a",
    "- ordinary\n\n\t\t<!a",
    "> - \t<!a",
    "Paragraph\n10. <!a",
    "> Paragraph\n> 10. <!a",
    "- Paragraph\n  10. <!a",
    "- >     <!a\n  >     code",
    "> -     <!a\n>       code",
]
NEWLINES = {"LF": "\n", "CR": "\r", "CRLF": "\r\n"}
CASES = [
    pytest.param(index, newline, id=f"P{index:02}-{name}")
    for index in range(1, 37)
    for name, newline in NEWLINES.items()
]
METADATA = RunMetadata(
    converter_version="0.3.0",
    renderer_version="7",
    run_id="44444444-4444-4444-8444-444444444444",
    run_time="2026-10-12T12:00:00+00:00",
    obsidian_version="1.13.7",
    bookmark_time=1791806400000,
)


def authored_facts(index, newline):
    """Coordinate arithmetic from the accepted P/N/T/I rule, never parsed output."""
    prefix = PROTECTED_NEIGHBORS[index - 1].replace("\n", newline)
    source = (
        prefix + newline * 2 + "<Value> é " + THOUGHT_REFERENCE + " " + IMAGE_REFERENCE
    )
    adapted = (
        prefix
        + newline * 2
        + "\\<Value> é "
        + THOUGHT_REFERENCE
        + " "
        + IMAGE_REFERENCE
    )
    start = len(prefix) + len(newline) * 2
    thought_start = start + 11
    image_start = thought_start + 47
    digest = sha256(adapted.encode()).hexdigest()
    edit = {
        "kind": "literal_text",
        "start": start,
        "end": start + 7,
        "before": "<Value>",
        "after": "\\<Value>",
        "adapted_start": start,
        "adapted_end": start + 8,
        "source_digest": sha256(source.encode()).hexdigest(),
        "source_basis": "scoped_source_text/unicode_codepoints",
        "adapted_basis": "document.text/unicode_codepoints",
    }
    references = [
        {
            "start": thought_start,
            "end": thought_start + 46,
            "expected_original": THOUGHT_REFERENCE,
            "kind": "item",
            "target": TARGET,
            "display_text": "Live",
            "table_cell": False,
            "document_digest": digest,
            "source_target": "brain://Z0UjAauJ3kyPASNFZ4mrzQ/ignored",
            "destination_start": None,
            "destination_end": None,
            "presentation_normalization": None,
        },
        {
            "start": image_start,
            "end": image_start + 41,
            "expected_original": IMAGE_REFERENCE,
            "kind": "image",
            "target": IMAGE_ID,
            "display_text": "photo",
            "table_cell": False,
            "document_digest": digest,
            "source_target": ".data/md-images/a.png",
            "destination_start": image_start + 9,
            "destination_end": image_start + 30,
            "presentation_normalization": None,
        },
    ]
    document = {
        "key": DOCUMENT,
        "owner": HOME,
        "text_digest": digest,
        "original_asset_id": DOCUMENT,
        "original_copy_omitted": False,
        "evidence": ["attachments.json:0"],
        "text_adaptations": [edit],
        "references": references,
    }
    note = (
        "# Entry thought\n\n" + prefix + newline * 2 + "\\<Value> é "
        '[[Notes/Topic.v2.md|Live]] ![photo](Attachments/22222222/a.png "caption")'
        "\n\n## Categories\n\n[[Categories.md|Browse categories]]\n"
    ).encode()
    return source, adapted, document, note


def declaration_archive(path, source_text, *, compression=ZIP_STORED):
    """Assemble authored raw members once, without a ZIP read/rewrite cycle."""
    members = dict(ROOT_BYTES)
    body = source_text.encode()
    attachments = [
        json.loads(members["attachments.json"]),
        {
            "Id": IMAGE_ID,
            "BrainId": BRAIN,
            "SourceId": HOME,
            "SourceType": 2,
            "Type": 12,
            "NoteType": 0,
            "Location": "a.png",
            "DataLength": len(IMAGE),
        },
    ]
    attachments[0]["DataLength"] = len(body)
    members["attachments.json"] = "\n".join(
        json.dumps(row) for row in attachments
    ).encode()
    meta = json.loads(members["meta.json"])
    meta["AttachmentFileStates"][IMAGE_ID] = 1
    members["meta.json"] = json.dumps(meta).encode()
    target = {
        "Id": TARGET,
        "BrainId": BRAIN,
        "Kind": 1,
        "ACType": 0,
        "Name": "Topic.v2",
        "TagIds": [],
    }
    members["thoughts.json"] += b"\n" + json.dumps(target).encode()
    members[HOME + "/Notes.md"] = body
    members[HOME + "/.data/md-images/a.png"] = IMAGE
    with ZipFile(path, "w", compression=compression) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return members


def expected_evidence(members):
    roots = []
    for name in ROOTS:
        raw = members[name].decode("utf-8-sig")
        rows = (
            raw
            if name == "meta.json"
            else ",".join(line for line in raw.splitlines() if line.strip())
        )
        roots.append("[" + rows + "]")
    payloads = [
        {
            "member": member,
            "length": len(members[member]),
            "sha256": sha256(members[member]).hexdigest(),
        }
        for member in (HOME + "/Notes.md", HOME + "/.data/md-images/a.png")
    ]
    retained_text = "".join(roots) + "".join(json.dumps(p) for p in payloads)
    digest = sha256(retained_text.encode()).hexdigest()
    return roots, payloads, digest


def assert_counts(counts, *, rendered=False, published=False):
    for name, expected in {
        "source_items": 2,
        "source_relationships": 0,
        "source_references": 2,
        "present_assets": 2,
        "planned_notes": 1,
        "planned_assets": 2,
        "planned_references": 2,
        "text_adaptations": 1,
        "source_gaps": 0,
        "generated_presentations": 0,
        "image_presentation_normalizations": 0,
        "planned_generated_embeds": 0,
        "actual_generated_embeds": 0 if rendered or published else None,
        "actual_references": 2 if rendered or published else None,
        "actual_notes": 1 if published else None,
        "actual_assets": 2 if published else None,
    }.items():
        assert counts[name] == expected, name
    if not published:
        assert counts["actual_files"] is None


def assert_record(record, document, members, archive_bytes):
    """Family-dependent evidence; generic manifest/schema audits stay in compositions."""
    roots, payloads, digest = expected_evidence(members)
    assert (
        record["source_identity"]["source_sha256"] == sha256(archive_bytes).hexdigest()
    )
    assert record["source_identity"]["snapshot_digest"] == digest
    targets = {item["item_key"]: item for item in record["item_targets"]}
    assert set(targets) == {HOME, TARGET}
    assert targets[TARGET]["relative_path"] == "Notes/Topic.v2.md"
    assert targets[TARGET]["created"] is False and targets[TARGET]["documents"] == []
    assert targets[HOME]["relative_path"] == NOTE_PATH
    assert targets[HOME]["created"] is True
    assert targets[HOME]["documents"] == [dict(document, owner_target=NOTE_PATH)]
    assert record["relationships"] == [] and record["issues"] == []
    assert record["source_gaps"] == record["generated_presentations"] == []
    evidence = {entry["key"]: entry["records"] for entry in record["original_evidence"]}
    assert evidence["attachments.json"] == json.loads(roots[3])
    for payload in payloads:
        assert evidence["payload:" + payload["member"]] == payload
    for asset, identity, role, destination, payload, pointer in zip(
        record["asset_targets"],
        (DOCUMENT, IMAGE_ID),
        ("note_original", "image"),
        (ORIGINAL_PATH, IMAGE_PATH),
        payloads,
        ("attachments.json:0", "attachments.json:1"),
        strict=True,
    ):
        assert asset["asset_id"] == identity and asset["owner"] == HOME
        assert asset["role"] == role and asset["availability"] == "present"
        assert asset["relative_path"] == destination
        assert (asset["actual_length"], asset["actual_sha256"]) == (
            payload["length"],
            payload["sha256"],
        )
        assert asset["evidence"] == [pointer]
    literal = [a for a in record["adaptations"] if a["kind"] == "literal_text"]
    assert len(literal) == 1
    fields = ("affected", "owner", "document_key", "evidence", "text_edit")
    assert {key: literal[0][key] for key in fields} == {
        "affected": f"text:{DOCUMENT}:0",
        "owner": HOME,
        "document_key": DOCUMENT,
        "evidence": ["attachments.json:0"],
        "text_edit": document["text_adaptations"][0],
    }
    reference_adaptations = [
        a for a in record["adaptations"] if a["kind"].endswith("_reference")
    ]
    assert [(a["kind"], a["affected"]) for a in reference_adaptations] == [
        ("item_reference", f"reference:{DOCUMENT}:0"),
        ("image_reference", f"reference:{DOCUMENT}:1"),
    ]
    reference_accounting = [
        entry
        for entry in record["source_accounting"]["entries"]
        if entry["identity"].startswith("reference:")
    ]
    assert reference_accounting == [
        {
            "identity": f"reference:{DOCUMENT}:0",
            "disposition": "normalized",
            "references": [DOCUMENT, TARGET],
        },
        {
            "identity": f"reference:{DOCUMENT}:1",
            "disposition": "normalized",
            "references": [DOCUMENT, IMAGE_ID],
        },
    ]


@pytest.mark.parametrize("index,newline", CASES)
def test_protected_neighbors_preserve_source_core_rendered_facts(
    tmp_path, index, newline
):
    source_text, adapted, document, note = authored_facts(index, newline)
    source = tmp_path / "source.brz"
    members = declaration_archive(source, source_text)
    before = source.read_bytes()
    _, payloads, digest = expected_evidence(members)
    with BrzSourceModule().open(source) as session:
        snapshot = session.snapshot
        assert snapshot.identity.source_sha256 == sha256(before).hexdigest()
        assert snapshot.identity.snapshot_digest == digest
        assert len(snapshot.documents) == 1
        assert snapshot.documents[0].model_dump(mode="json") == dict(
            document, text=adapted
        )
        assert snapshot.relationships == ()
        for asset, identity, role, payload, pointer in zip(
            snapshot.assets,
            (DOCUMENT, IMAGE_ID),
            ("note_original", "image"),
            payloads,
            ("attachments.json:0", "attachments.json:1"),
            strict=True,
        ):
            assert asset.asset_id == identity and asset.owner == HOME
            assert asset.role == role and asset.availability == "present"
            assert (asset.actual_length, asset.actual_sha256) == (
                payload["length"],
                payload["sha256"],
            )
            assert asset.evidence == (pointer,)
        analysis = analyze(snapshot, BRZ_POLICY)
        assert analysis.issues == ()
        migration_plan = plan(analysis)
        assert migration_plan.issues == ()
        assert_counts(migration_plan.counts.model_dump())
        rendered = render(migration_plan, METADATA)
        session.verify_consistency()
    assert source.read_bytes() == before
    # Durable returned values remain usable after the source session closes.
    generated = {file.relative_path: file.content for file in rendered.generated_files}
    assert note_body(generated[NOTE_PATH]) == note
    assert "Notes/Topic.v2.md" not in generated
    assert_counts(rendered.counts.model_dump(), rendered=True)
    assert [copy.model_dump() for copy in rendered.copies] == [
        {
            "relative_path": path,
            "asset_id": identity,
            "expected_length": payload["length"],
            "expected_sha256": payload["sha256"],
        }
        for path, identity, payload in zip(
            (ORIGINAL_PATH, IMAGE_PATH), (DOCUMENT, IMAGE_ID), payloads, strict=True
        )
    ]
    record = json.loads(generated["migration-record.json"])
    assert_record(record, document, members, before)
    assert_counts(record["counts"], rendered=True)
